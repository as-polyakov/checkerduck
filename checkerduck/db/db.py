import logging
import os
import sqlite3
import threading
from enum import Enum
from sqlite3 import Connection

from alembic import command
from alembic.config import Config


class LinkDirection(str, Enum):
    IN = "in"
    OUT = "out"


log = logging.getLogger(__name__)

DB_PATH = os.environ.get("CHECKERDUCK_DB", os.path.join(os.path.abspath(os.getcwd()), "ahrefs_data.db"))

_thread_local = threading.local()
_db_initialized = False
_db_path: str = ""


def init_database(db_path: str = DB_PATH, alembic_ini_path: str = "alembic.ini"):
    log.info("initializing database")
    if not db_path:
        raise RuntimeError("Database not configured. Provide db_path during initialization.")
    db_url = f"sqlite:///{db_path}"
    if os.environ.get("CHECKERDUCK_SKIP_MIGRATIONS") is None:
        alembic_cfg = Config(alembic_ini_path)
        # package_dir = Path(checkerduck.__file__).resolve().parent
        # alembic_cfg.set_main_option(
        #     "script_location",
        #     str(package_dir / "migrations"),
        # )
        log.debug("alembic script_location=%s", alembic_cfg.get_alembic_option("script_location"))
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)
        command.upgrade(alembic_cfg, "head")
    global _db_path
    _db_path = db_path
    global _db_initialized
    _db_initialized = True
    log.info("database ready: %s", db_path)


def get_thread_connection() -> Connection:
    if not _db_initialized:
        raise RuntimeError("Database not initialized.")
    conn = getattr(_thread_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(_db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")  # readers concurrent with writer
        conn.execute("PRAGMA busy_timeout = 5000")  # wait instead of SQLITE_BUSY
        conn.execute("PRAGMA synchronous = OFF")  # safe under WAL
        _thread_local.conn = conn
    return conn
