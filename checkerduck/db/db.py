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


project_root = os.path.abspath(os.getcwd())
DB_PATH = os.path.join(project_root, "ahrefs_data.db")

_thread_local = threading.local()
_db_initialized = False
_db_path: str = ""


def init_database(db_path: str = DB_PATH, alembic_ini_path: str = "alembic.ini"):
    print("Initializing database...")
    if not db_path:
        raise RuntimeError("Database not configured. Provide db_path during initialization.")
    alembic_cfg = Config(alembic_ini_path)
    db_url = f"sqlite:///{db_path}"
    print(alembic_cfg.get_alembic_option("script_location"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")
    global _db_path
    _db_path = db_path
    global _db_initialized
    _db_initialized = True
    print("Initialized database.")


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
        conn.execute("PRAGMA synchronous = NORMAL")  # safe under WAL
        conn.execute("PRAGMA foreign_keys = ON")
        _thread_local.conn = conn
    return conn
