"""
One place that decides where SmartixCut keeps its data.

  - DATABASE_URL set   -> Postgres in the cloud (Neon, Supabase, Render Postgres...). Survives
                          restarts, redeploys and spin-downs. Use this on Render.
  - DATABASE_URL empty -> a local SQLite file (data/smartix.db). Fine on your laptop.

The rest of the code just does `with db() as c: c.execute("... WHERE id=?", (x,))` and never
cares which one it is. (This file turns `?` into `%s` for Postgres and makes rows readable as
row["name"] or row[0], the same as SQLite.)
"""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if DATABASE_URL.startswith("postgres://"):                 # some providers still hand out this old form
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]
USE_PG = bool(DATABASE_URL)

SQLITE_PATH = None
_pool = None
IntegrityErrors = (sqlite3.IntegrityError,)

if USE_PG:
    try:
        import psycopg
        from psycopg_pool import ConnectionPool
    except ImportError:
        raise SystemExit("DATABASE_URL is set but Postgres drivers are missing. Run:  "
                         "pip install \"psycopg[binary]\" psycopg-pool")
    IntegrityErrors = (sqlite3.IntegrityError, psycopg.IntegrityError)

    class Row:
        """Behaves like sqlite3.Row: row["col"], row[0], iteration over values."""
        __slots__ = ("_names", "_values")

        def __init__(self, names, values):
            self._names, self._values = names, values

        def __getitem__(self, key):
            if isinstance(key, str):
                return self._values[self._names.index(key)]
            return self._values[key]

        def __iter__(self):
            return iter(self._values)

        def keys(self):
            return list(self._names)

    def _row_factory(cursor):
        names = [c.name for c in cursor.description] if cursor.description else []
        return lambda values: Row(names, values)

    class _Conn:
        """Lets the shared code keep writing `?` placeholders."""

        def __init__(self, conn):
            self._conn = conn

        def execute(self, sql, params=()):
            return self._conn.execute(sql.replace("%", "%%").replace("?", "%s"), params)


def init(data_dir):
    """Call once at startup, before the first db() call."""
    global _pool, SQLITE_PATH
    if USE_PG:
        if _pool is None:
            _pool = ConnectionPool(
                DATABASE_URL,
                min_size=1,
                max_size=int(os.getenv("DB_POOL", "10")),
                # prepare_threshold=None keeps it working behind Neon's pooled (pgbouncer) endpoint
                kwargs={"row_factory": _row_factory, "prepare_threshold": None},
                check=ConnectionPool.check_connection,      # replaces connections the host closed while idle
                open=True,
            )
            _pool.wait(timeout=30)
    else:
        SQLITE_PATH = Path(data_dir) / "smartix.db"


@contextmanager
def db():
    if USE_PG:
        with _pool.connection() as conn:        # commits on success, rolls back on error
            yield _Conn(conn)
    else:
        conn = sqlite3.connect(SQLITE_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def close():
    """Call at shutdown so the connection pool stops cleanly."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None