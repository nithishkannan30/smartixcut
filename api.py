"""
SmartixCut API + web host (one process).

Run:   uvicorn api:app --reload --port 8000
Open:  http://localhost:8000   (serves the React build from web/dist, see README)

Every /api endpoint except /api/health and /api/auth/* needs a logged-in user (cookie).
    POST   /api/auth/signup | /api/auth/login | /api/auth/logout      GET /api/auth/me
    GET    /api/health
    POST   /api/uploads                      multipart file  -> {video_key, ...}
    POST   /api/jobs                         {video_key, prompt, language, platform, num_clips, quality, captions}
    GET    /api/jobs/{id}                    status + clips
    GET    /api/jobs                         your past jobs
    DELETE /api/jobs/{id}
    GET    /api/jobs/{id}/clips/{n}/video    stream a finished clip (only when not on Cloudinary)
    GET    /api/jobs/{id}/clips/{n}/download

Job states: uploaded -> transcribing -> finding_moments -> rendering -> done | failed
"""
import os
import re
import sys
import json
import time
import uuid
import shutil
import sqlite3
import subprocess
from pathlib import Path
from typing import Literal
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")

import auth                                        # noqa: E402  (needs .env loaded first)
from pricing import estimate_cost, usd_to_inr      # noqa: E402

# ---------------- settings ----------------
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE / "data")))
UPLOAD_DIR = DATA_DIR / "uploads"
JOBS_DIR = DATA_DIR / "jobs"
DB_PATH = DATA_DIR / "smartix.db"
SCRIPTS_DIR = Path(os.getenv("SCRIPTS_DIR", str(BASE)))   # where transcribe/find_moments/render live
FONTS_SRC = Path(os.getenv("FONTS_SRC", str(BASE / "fonts")))
WEB_DIST = Path(os.getenv("WEB_DIST", str(BASE / "web" / "dist")))   # output of `npm run build`

MAX_UPLOAD_BYTES = int(float(os.getenv("MAX_UPLOAD_GB", "2")) * 1024 ** 3)
MAX_VIDEO_MINUTES = float(os.getenv("MAX_VIDEO_MINUTES", "30"))
MAX_PARALLEL_JOBS = int(os.getenv("MAX_PARALLEL_JOBS", "2"))
STAGE_TIMEOUT_SECS = int(os.getenv("STAGE_TIMEOUT_SECS", "1200"))
UPLOAD_TTL_DAYS = float(os.getenv("UPLOAD_TTL_DAYS", "3"))     # originals are deleted after this
MIN_CLIP_SECS = os.getenv("MIN_CLIP_SECS", "20")
MAX_CLIP_SECS = os.getenv("MAX_CLIP_SECS", "60")
JOBS_PER_DAY = int(os.getenv("JOBS_PER_DAY", "20"))            # per user, protects your API bill
MAX_RUNNING_PER_USER = int(os.getenv("MAX_RUNNING_PER_USER", "2"))
# Only needed if the browser talks to the API from a different address (not the case with the
# Vite proxy or the built app). Use real origins, e.g. https://smartixcut.com, never *.
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip() and o.strip() != "*"]

# Cloudinary stores the finished clips (and optionally originals) so your server disk stays small.
CLOUD_VARS = ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET")
CLOUD_ON = all(os.getenv(v) for v in CLOUD_VARS)
CLOUD_STORE_ORIGINALS = os.getenv("CLOUDINARY_STORE_ORIGINALS", "0") == "1"
if CLOUD_ON:
    try:
        import cloudinary
        import cloudinary.uploader
        cloudinary.config(cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"), api_key=os.getenv("CLOUDINARY_API_KEY"),
                          api_secret=os.getenv("CLOUDINARY_API_SECRET"), secure=True)
    except ImportError:
        cloudinary = None

ALLOWED_EXT = {".mp4", ".mov", ".m4v"}
LANGUAGES = {"ta", "hi", "mr", "en"}
PLATFORMS = {"reels": "Instagram Reels", "shorts": "YouTube Shorts", "tiktok": "TikTok"}
RUNNING_STATES = ("uploaded", "transcribing", "finding_moments", "rendering")
STATUS_PROGRESS = {"uploaded": 5, "transcribing": 20, "finding_moments": 70,
                   "rendering": 82, "done": 100, "failed": 100}

ID_RE = re.compile(r"^[0-9a-f]{32}$")

STAGE_ERRORS = {
    "transcribing": "Couldn't transcribe the audio. Check GROQ_API_KEY and your internet connection, then try again.",
    "finding_moments": "Couldn't pick clips from the transcript. The AI service may be busy or the model name may be wrong. Try again.",
    "rendering": "Couldn't render the clips. Check that FFmpeg is installed and the fonts folder exists (python get_fonts.py).",
}

executor = ThreadPoolExecutor(max_workers=MAX_PARALLEL_JOBS)


# ---------------- database ----------------
@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_storage():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    with db() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                created_at REAL, updated_at REAL,
                status TEXT, error TEXT, error_detail TEXT,
                video_key TEXT, video_name TEXT, video_path TEXT,
                prompt TEXT, language TEXT, platform TEXT, num_clips INTEGER,
                audio_seconds REAL, total_seconds REAL,
                stage_seconds TEXT, clips TEXT, cost_usd REAL,
                user_id TEXT
            )""")
        cols = {r["name"] for r in c.execute("PRAGMA table_info(jobs)")}
        if "user_id" not in cols:                       # database made before accounts existed
            c.execute("ALTER TABLE jobs ADD COLUMN user_id TEXT")
        c.execute("CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs (user_id, created_at)")
        # a restart kills running jobs: mark them failed instead of leaving them stuck
        c.execute(
            "UPDATE jobs SET status='failed', updated_at=?, error=? WHERE status IN (?,?,?,?)",
            (time.time(), "The server restarted while this job was running. Please try again.")
            + RUNNING_STATES)
    auth.setup(db, DATA_DIR)


def cleanup_old_uploads():
    cutoff = time.time() - UPLOAD_TTL_DAYS * 86400
    with db() as c:
        busy = {r["video_key"] for r in c.execute(
            "SELECT video_key FROM jobs WHERE status IN (?,?,?,?)", RUNNING_STATES)}
    for f in UPLOAD_DIR.iterdir():
        try:
            if f.stem not in busy and f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            pass


def update_job(job_id, **fields):
    allowed = {"status", "error", "error_detail", "audio_seconds", "total_seconds",
               "stage_seconds", "clips", "cost_usd"}
    sets, vals = ["updated_at=?"], [time.time()]
    for k, v in fields.items():
        if k not in allowed:
            raise ValueError(k)
        sets.append(k + "=?")
        vals.append(json.dumps(v) if isinstance(v, (dict, list)) else v)
    vals.append(job_id)
    with db() as c:
        c.execute("UPDATE jobs SET " + ", ".join(sets) + " WHERE id=?", vals)


def get_row(job_id, user):
    """The job, but only if it belongs to this user. Anyone else gets a plain 404."""
    if not ID_RE.match(job_id):
        raise HTTPException(404, "Job not found")
    with db() as c:
        row = c.execute("SELECT * FROM jobs WHERE id=? AND user_id=?", (job_id, user["id"])).fetchone()
    if not row:
        raise HTTPException(404, "Job not found")
    return row


def job_public(row):
    clips = json.loads(row["clips"] or "[]")
    for c in clips:
        base = "/api/jobs/{}/clips/{}".format(row["id"], c["n"])
        if c.get("cloudinary_url"):
            c["video_url"] = c["download_url"] = c["cloudinary_url"]
        else:
            c["video_url"], c["download_url"] = base + "/video", base + "/download"
        c.pop("cloudinary_url", None)
        c.pop("cloudinary_id", None)
    cost = row["cost_usd"]
    try:                                               # the quality + caption style this job was made with
        options = json.loads((JOBS_DIR / row["id"] / "options.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        options = None
    return {
        "id": row["id"],
        "status": row["status"],
        "progress": STATUS_PROGRESS.get(row["status"], 0),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "video_name": row["video_name"],
        "video_key": row["video_key"],
        "prompt": row["prompt"],
        "language": row["language"],
        "platform": row["platform"],
        "num_clips": row["num_clips"],
        "audio_seconds": row["audio_seconds"],
        "total_seconds": row["total_seconds"],
        "stage_seconds": json.loads(row["stage_seconds"] or "{}"),
        "error": row["error"],
        "error_detail": row["error_detail"],
        "cost_usd": cost,
        "cost_inr": round(cost * usd_to_inr(), 2) if cost is not None else None,
        "options": options,
        "clips": clips,
    }


# ---------------- cloudinary ----------------
def cloud_upload(path, folder, public_id):
    """Upload one video file. Returns (https url, cloudinary public id)."""
    r = cloudinary.uploader.upload_large(
        str(path), resource_type="video", folder=folder, public_id=public_id,
        overwrite=True, use_filename=False, unique_filename=False)
    return r["secure_url"], r["public_id"]


def cloud_delete(public_id):
    cloudinary.uploader.destroy(public_id, resource_type="video", invalidate=True)


# ---------------- the pipeline job ----------------
def log_tail(path, chars=600):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")[-chars:].strip()
    except OSError:
        return ""


def run_job(job_id):
    t_start = time.time()
    with db() as c:
        row = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    jdir = JOBS_DIR / job_id
    jdir.mkdir(parents=True, exist_ok=True)
    log_path = jdir / "job.log"
    stage_secs = {}

    try:
        # the render step looks for ./fonts, so each job gets its own copy
        if FONTS_SRC.is_dir() and not (jdir / "fonts").exists():
            shutil.copytree(FONTS_SRC, jdir / "fonts")

        brief = (row["prompt"] or "").strip() or "the best hooks and most interesting moments"
        env = os.environ.copy()
        env.update({
            "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",   # Tamil/Hindi text in pipes on Windows
            "CLIP_PROMPT": "{} (format: {})".format(brief, PLATFORMS.get(row["platform"], "short vertical video")),
            "NUM_CLIPS": str(row["num_clips"]),
            "MIN_LEN": MIN_CLIP_SECS, "MAX_LEN": MAX_CLIP_SECS,
        })
        video = row["video_path"]
        stages = [
            ("transcribing", ["transcribe_chunked.py", video, row["language"]]),
            ("finding_moments", ["find_moments.py"]),
            ("rendering", ["render.py", video]),          # render.py reads options.json in the job folder
        ]

        for status, args in stages:
            update_job(job_id, status=status)
            t = time.time()
            with open(log_path, "a", encoding="utf-8") as log:
                log.write("\n===== {} =====\n".format(status))
                log.flush()
                try:
                    r = subprocess.run(
                        [sys.executable, str(SCRIPTS_DIR / args[0])] + args[1:],
                        cwd=str(jdir), env=env, stdout=log, stderr=subprocess.STDOUT,
                        timeout=STAGE_TIMEOUT_SECS)
                    code = r.returncode
                except subprocess.TimeoutExpired:
                    code = -1
                    log.write("\nTIMEOUT after {}s\n".format(STAGE_TIMEOUT_SECS))
            stage_secs[status] = round(time.time() - t, 1)

            if code != 0:
                tail = log_tail(log_path)
                msg = STAGE_ERRORS[status]
                if status == "finding_moments" and "No valid clips" in tail:
                    msg = "No good clips were found in this video. Try a longer video or a different brief."
                update_job(job_id, status="failed", error=msg, error_detail=tail,
                           stage_seconds=stage_secs, total_seconds=round(time.time() - t_start, 1))
                return

        # ---- success: collect the clips and the cost ----
        result = json.loads((jdir / "result.json").read_text(encoding="utf-8"))
        picked = json.loads((jdir / "clips.json").read_text(encoding="utf-8"))
        clips = []
        for c in picked.get("clips", []):
            n = c["rank"]
            if (jdir / "clips_out" / "clip_{}.mp4".format(n)).exists():
                clips.append({"n": n, "title": c.get("title", ""), "reason": c.get("reason", ""),
                              "hashtags": c.get("hashtags", []), "start": c["start"], "end": c["end"],
                              "duration": c["duration"], "text": c.get("text", "")})
        if not clips:
            update_job(job_id, status="failed", error=STAGE_ERRORS["rendering"],
                       error_detail=log_tail(log_path), stage_seconds=stage_secs,
                       total_seconds=round(time.time() - t_start, 1))
            return

        if CLOUD_ON and cloudinary is not None:        # push the clips to Cloudinary, all at once
            t = time.time()

            def push(c):
                local = jdir / "clips_out" / "clip_{}.mp4".format(c["n"])
                try:
                    c["cloudinary_url"], c["cloudinary_id"] = cloud_upload(
                        local, "smartixcut/clips/" + job_id, "clip_{}".format(c["n"]))
                    local.unlink(missing_ok=True)          # keep the server disk small
                except Exception as e:                     # clip stays on disk and is served from there
                    with open(log_path, "a", encoding="utf-8") as log:
                        log.write("\nCloudinary upload failed for clip {}: {}\n".format(c["n"], str(e)[:300]))

            with ThreadPoolExecutor(max_workers=min(4, len(clips))) as pool:
                list(pool.map(push, clips))
            stage_secs["cloud_upload"] = round(time.time() - t, 1)

        cost = estimate_cost(
            result.get("stt_model", "whisper-large-v3"),
            result.get("billed_audio_seconds", result.get("audio_seconds", 0)),
            os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
            picked.get("provider", "groq"), picked.get("usage", {}))
        update_job(job_id, status="done", clips=clips, stage_seconds=stage_secs,
                   audio_seconds=result.get("audio_seconds"), cost_usd=cost["total"],
                   total_seconds=round(time.time() - t_start, 1), error=None)

    except Exception as e:   # anything unexpected must not leave the job stuck
        update_job(job_id, status="failed", error="Something went wrong while processing this video.",
                   error_detail=str(e)[:600], stage_seconds=stage_secs,
                   total_seconds=round(time.time() - t_start, 1))


# ---------------- app ----------------
app = FastAPI(title="SmartixCut API")
if CORS_ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"],
                       allow_headers=["*"], allow_credentials=True)
app.include_router(auth.router)


@app.on_event("startup")
def on_startup():
    init_storage()
    cleanup_old_uploads()


@app.on_event("shutdown")
def on_shutdown():
    executor.shutdown(wait=False, cancel_futures=True)


@app.get("/api/health")
def health():
    problems = []
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            problems.append("{} is not installed or not on PATH".format(tool))
    if not os.getenv("GROQ_API_KEY"):
        problems.append("GROQ_API_KEY is missing in .env")
    if not FONTS_SRC.is_dir() or not any(FONTS_SRC.glob("*.ttf")):
        problems.append("fonts folder is missing: run  python get_fonts.py")
    for s in ("transcribe_chunked.py", "find_moments.py", "render.py"):
        if not (SCRIPTS_DIR / s).exists():
            problems.append("{} not found in {}".format(s, SCRIPTS_DIR))
    some = [v for v in CLOUD_VARS if os.getenv(v)]
    if some and not CLOUD_ON:
        problems.append("Cloudinary is half set up: missing " + ", ".join(v for v in CLOUD_VARS if not os.getenv(v)))
    if CLOUD_ON and cloudinary is None:
        problems.append("Cloudinary is configured but not installed: run  pip install cloudinary")
    return {"ok": not problems, "problems": problems,
            "languages": sorted(LANGUAGES), "platforms": PLATFORMS,
            "storage": "cloudinary" if CLOUD_ON else "local",
            "max_upload_gb": MAX_UPLOAD_BYTES / 1024 ** 3,
            "max_video_minutes": MAX_VIDEO_MINUTES}


def probe_video(path):
    """Returns the duration in seconds if the file has a video AND an audio track, else a reason string."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type:format=duration",
             "-of", "json", str(path)], capture_output=True, text=True, timeout=60)
        data = json.loads(r.stdout or "{}")
        kinds = {s.get("codec_type") for s in data.get("streams", [])}
        if "video" not in kinds:
            return "This file doesn't look like a valid video."
        if "audio" not in kinds:
            return "This video has no audio track, so there is nothing to transcribe."
        return float(data["format"]["duration"])
    except Exception:
        return "This file doesn't look like a valid video."


@app.post("/api/uploads", status_code=201)
async def upload(file: UploadFile = File(...), user: dict = Depends(auth.current_user)):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, "Please upload an MP4 or MOV video.")

    key = uuid.uuid4().hex
    dest = UPLOAD_DIR / (key + ext)
    size = 0
    try:
        with open(dest, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "That file is larger than {:g} GB.".format(MAX_UPLOAD_BYTES / 1024 ** 3))
                f.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    except Exception:
        dest.unlink(missing_ok=True)
        raise HTTPException(500, "Upload failed. Please try again.")

    info = probe_video(dest)
    if isinstance(info, str):
        dest.unlink(missing_ok=True)
        raise HTTPException(400, info)
    if info > MAX_VIDEO_MINUTES * 60:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "Videos can be up to {:g} minutes long for now.".format(MAX_VIDEO_MINUTES))

    meta = {"name": file.filename, "duration": round(info, 1), "size": size, "ext": ext}
    if CLOUD_ON and cloudinary is not None and CLOUD_STORE_ORIGINALS:     # optional backup copy
        try:
            meta["cloudinary_url"], _ = cloud_upload(dest, "smartixcut/uploads/" + user["id"], key)
        except Exception:
            pass
    (UPLOAD_DIR / (key + ".json")).write_text(json.dumps({**meta, "user_id": user["id"]}), encoding="utf-8")
    return {"video_key": key, **{k: v for k, v in meta.items() if k != "cloudinary_url"}}


class CaptionOpts(BaseModel):
    enabled: bool = True
    style: Literal["outline", "box", "karaoke"] = "outline"
    size: Literal["small", "medium", "large"] = "medium"
    position: Literal["bottom", "middle", "top"] = "bottom"
    color: str = Field(default="#FFFFFF", pattern=r"^#[0-9a-fA-F]{6}$")
    highlight: str = Field(default="#FFE600", pattern=r"^#[0-9a-fA-F]{6}$")
    uppercase: bool = False


class JobIn(BaseModel):
    video_key: str = Field(pattern=r"^[0-9a-f]{32}$")
    prompt: str = Field(default="", max_length=600)
    language: str = "ta"
    platform: str = "reels"
    num_clips: int = Field(default=3, ge=1, le=5)
    quality: Literal["hd", "fast"] = "hd"
    captions: CaptionOpts = Field(default_factory=CaptionOpts)


@app.post("/api/jobs", status_code=201)
def create_job(body: JobIn, user: dict = Depends(auth.current_user)):
    if body.language not in LANGUAGES:
        raise HTTPException(422, "Language must be one of: " + ", ".join(sorted(LANGUAGES)))
    if body.platform not in PLATFORMS:
        raise HTTPException(422, "Platform must be one of: " + ", ".join(PLATFORMS))

    gone = "That upload was not found (it may have expired). Please upload the video again."
    meta_file = UPLOAD_DIR / (body.video_key + ".json")
    if not meta_file.exists():
        raise HTTPException(404, gone)
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    if meta.get("user_id") != user["id"]:             # somebody else's upload
        raise HTTPException(404, gone)
    video_path = UPLOAD_DIR / (body.video_key + meta["ext"])
    if not video_path.exists():
        raise HTTPException(404, gone)

    now = time.time()
    with db() as c:
        today = c.execute("SELECT COUNT(*) FROM jobs WHERE user_id=? AND created_at>?",
                          (user["id"], now - 86400)).fetchone()[0]
        running = c.execute("SELECT COUNT(*) FROM jobs WHERE user_id=? AND status IN (?,?,?,?)",
                            (user["id"],) + RUNNING_STATES).fetchone()[0]
    if today >= JOBS_PER_DAY:
        raise HTTPException(429, "You've reached today's limit of {} videos. Try again tomorrow.".format(JOBS_PER_DAY))
    if running >= MAX_RUNNING_PER_USER:
        raise HTTPException(429, "You already have {} videos processing. Wait for one to finish.".format(running))

    job_id = uuid.uuid4().hex
    with db() as c:
        c.execute(
            """INSERT INTO jobs (id, created_at, updated_at, status, video_key, video_name, video_path,
                                 prompt, language, platform, num_clips, user_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (job_id, now, now, "uploaded", body.video_key, meta["name"], str(video_path),
             body.prompt.strip(), body.language, body.platform, body.num_clips, user["id"]))
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "options.json").write_text(
        json.dumps({"quality": body.quality, "captions": body.captions.model_dump()}), encoding="utf-8")
    executor.submit(run_job, job_id)
    return {"job_id": job_id, "status": "uploaded"}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, user: dict = Depends(auth.current_user)):
    return job_public(get_row(job_id, user))


@app.get("/api/jobs")
def list_jobs(limit: int = Query(20, ge=1, le=100), user: dict = Depends(auth.current_user)):
    with db() as c:
        rows = c.execute("SELECT * FROM jobs WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                         (user["id"], limit)).fetchall()
    return {"jobs": [job_public(r) for r in rows]}


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str, user: dict = Depends(auth.current_user)):
    row = get_row(job_id, user)
    if row["status"] in RUNNING_STATES:
        raise HTTPException(409, "This job is still running.")
    if CLOUD_ON and cloudinary is not None:           # free the Cloudinary storage too
        for c in json.loads(row["clips"] or "[]"):
            if c.get("cloudinary_id"):
                try:
                    cloud_delete(c["cloudinary_id"])
                except Exception:
                    pass
    shutil.rmtree(JOBS_DIR / job_id, ignore_errors=True)
    with db() as c:
        c.execute("DELETE FROM jobs WHERE id=?", (job_id,))
    return {"deleted": job_id}


def clip_path(job_id, n, user):
    row = get_row(job_id, user)
    path = JOBS_DIR / row["id"] / "clips_out" / "clip_{}.mp4".format(int(n))
    if not path.exists():
        raise HTTPException(404, "Clip not found")
    return path


@app.get("/api/jobs/{job_id}/clips/{n}/video")
def clip_video(job_id: str, n: int, user: dict = Depends(auth.current_user)):
    return FileResponse(clip_path(job_id, n, user), media_type="video/mp4")


@app.get("/api/jobs/{job_id}/clips/{n}/download")
def clip_download(job_id: str, n: int, user: dict = Depends(auth.current_user)):
    return FileResponse(clip_path(job_id, n, user), media_type="video/mp4",
                        filename="smartixcut_clip_{}.mp4".format(n))


# ---------------- the React app (built files), registered last so /api wins ----------------
if (WEB_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def web_app(path: str):
    if path.startswith("api/"):
        raise HTTPException(404, "Not found")
    index = WEB_DIST / "index.html"
    if not index.exists():
        return HTMLResponse(
            "<h2>SmartixCut API is running</h2><p>The web app isn't built yet. In the <code>web</code> folder run "
            "<code>npm run build</code>, or use <code>npm run dev</code> and open http://localhost:5173</p>")
    f = (WEB_DIST / path).resolve()
    if path and f.is_file() and WEB_DIST.resolve() in f.parents:      # favicon etc.
        return FileResponse(f)
    return FileResponse(index)                                        # any app route: let React decide