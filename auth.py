"""
Accounts for SmartixCut: sign up, log in, who am I, log out.

How it works (the plain-English version):
  - Passwords are never stored. We store a salted scrypt hash, so even you can't read them.
  - After login the server gives the browser a signed token in an httpOnly cookie. JavaScript
    can't read that cookie (so a stolen script can't steal the login), and the browser sends it
    automatically with every request, including <video> and download links.
  - Every other endpoint asks `current_user` "who is this?" and answers 401 if nobody.

Settings (.env):
    SECRET_KEY      long random string that signs the login cookie. If you don't set it, one is
                    generated and saved (in the cloud database if DATABASE_URL is set, else in
                    data/.secret). Still best to set it yourself on a server.
    SESSION_DAYS    how long a login lasts (default 14)
    COOKIE_SECURE   set to 1 once the site runs on https
"""
import os
import re
import time
import uuid
import hmac
import base64
import hashlib
import secrets
from pathlib import Path

import jwt
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

import database

router = APIRouter(prefix="/api/auth", tags=["auth"])

COOKIE = "smartix_session"
SESSION_DAYS = float(os.getenv("SESSION_DAYS", "14"))
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0") == "1"
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")

_db = None          # set by setup(): a context manager that yields a sqlite connection
_secret = ""


# ---------------- setup ----------------
def setup(db_ctx, data_dir):
    """Create the users table and load the signing secret. Called once at startup."""
    global _db, _secret
    _db = db_ctx
    with _db() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                pw_hash TEXT NOT NULL,
                created_at DOUBLE PRECISION NOT NULL
            )""")
    _secret = os.getenv("SECRET_KEY", "").strip()
    if _secret:
        return
    if database.USE_PG:
        # cloud servers lose local files on restart, so keep the signing key in the database instead
        with _db() as c:
            c.execute("CREATE TABLE IF NOT EXISTS app_secret (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
            c.execute("INSERT INTO app_secret (id, value) VALUES (1, ?) ON CONFLICT (id) DO NOTHING",
                      (secrets.token_hex(32),))
            _secret = c.execute("SELECT value FROM app_secret WHERE id=1").fetchone()["value"]
        return
    f = Path(data_dir) / ".secret"
    if f.exists():
        _secret = f.read_text(encoding="utf-8").strip()
    else:
        _secret = secrets.token_hex(32)
        f.write_text(_secret, encoding="utf-8")
        try:
            f.chmod(0o600)
        except OSError:
            pass


# ---------------- passwords ----------------
def _b64(b):
    return base64.b64encode(b).decode("ascii")


def hash_password(password):
    salt = os.urandom(16)
    n, r, p = 2 ** 14, 8, 1
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=32)
    return "scrypt${}${}${}${}${}".format(n, r, p, _b64(salt), _b64(digest))


def verify_password(password, stored):
    try:
        _, n, r, p, salt, digest = stored.split("$")
        got = hashlib.scrypt(password.encode("utf-8"), salt=base64.b64decode(salt),
                             n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(got, base64.b64decode(digest))
    except Exception:
        return False


_DUMMY_HASH = hash_password("not-a-real-password")   # so unknown emails take as long as real ones


# ---------------- tokens and cookies ----------------
def _make_token(user_id):
    now = int(time.time())
    return jwt.encode({"sub": user_id, "iat": now, "exp": now + int(SESSION_DAYS * 86400)},
                      _secret, algorithm="HS256")


def _set_cookie(response, user_id):
    response.set_cookie(COOKIE, _make_token(user_id), max_age=int(SESSION_DAYS * 86400),
                        httponly=True, samesite="lax", secure=COOKIE_SECURE, path="/")


def _public(row):
    return {"id": row["id"], "email": row["email"], "name": row["name"]}


def current_user(request: Request):
    """FastAPI dependency: the logged-in user as a dict, or a 401."""
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "Please log in.")
    try:
        user_id = jwt.decode(token, _secret, algorithms=["HS256"])["sub"]
    except jwt.PyJWTError:
        raise HTTPException(401, "Your session has expired. Please log in again.")
    with _db() as c:
        row = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        raise HTTPException(401, "Please log in.")
    return _public(row)


# ---------------- brute-force protection (in memory, one server process) ----------------
_attempts = {}


def _blocked(key, limit, window):
    now = time.time()
    recent = [t for t in _attempts.get(key, []) if now - t < window]
    _attempts[key] = recent
    return len(recent) >= limit


def _note(key):
    _attempts.setdefault(key, []).append(time.time())


def _ip(request):
    return request.client.host if request.client else "?"


# ---------------- endpoints ----------------
class SignupIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    email: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


@router.post("/signup", status_code=201)
def signup(body: SignupIn, request: Request, response: Response):
    email = body.email.strip().lower()
    name = re.sub(r"[\x00-\x1f\x7f]", "", body.name).strip()
    if not EMAIL_RE.match(email):
        raise HTTPException(422, "Enter a valid email address.")
    if not name:
        raise HTTPException(422, "Enter your name.")
    if _blocked("signup|" + _ip(request), 10, 3600):
        raise HTTPException(429, "Too many sign-ups from this network. Try again later.")

    row = {"id": uuid.uuid4().hex, "email": email, "name": name}
    try:
        with _db() as c:
            c.execute("INSERT INTO users (id, email, name, pw_hash, created_at) VALUES (?,?,?,?,?)",
                      (row["id"], email, name, hash_password(body.password), time.time()))
    except database.IntegrityErrors:
        raise HTTPException(409, "An account with this email already exists. Log in instead.")
    _note("signup|" + _ip(request))
    _set_cookie(response, row["id"])
    return row


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response):
    email = body.email.strip().lower()
    key = "login|{}|{}".format(_ip(request), email)
    if _blocked(key, 8, 900):
        raise HTTPException(429, "Too many attempts. Wait a few minutes and try again.")
    with _db() as c:
        row = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    ok = verify_password(body.password, row["pw_hash"] if row else _DUMMY_HASH)
    if not (row and ok):
        _note(key)
        raise HTTPException(401, "Incorrect email or password.")
    _attempts.pop(key, None)
    _set_cookie(response, row["id"])
    return _public(row)


@router.get("/me")
def me(request: Request):
    return current_user(request)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}