"""
SQLite database connection management and schema initialization.

Provides a singleton connection to the framework database,
auto-creates tables on first use.
"""

import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_connection: sqlite3.Connection | None = None

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    is_complete INTEGER NOT NULL DEFAULT 0,
    voice_mode INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS completions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL UNIQUE,
    agent_id TEXT NOT NULL,
    collected_fields TEXT NOT NULL,
    completed_at TEXT NOT NULL DEFAULT (datetime('now')),
    result_data TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);
"""


def get_db(db_path: str = None) -> sqlite3.Connection:
    """Get or create the singleton database connection."""
    global _connection
    if _connection is not None:
        return _connection

    if db_path is None:
        from framework.config.settings import DB_PATH
        db_path = DB_PATH

    # Ensure directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    _connection = sqlite3.connect(db_path, check_same_thread=False)
    _connection.row_factory = sqlite3.Row
    _connection.execute("PRAGMA journal_mode=WAL")
    _connection.execute("PRAGMA foreign_keys=ON")

    init_db(_connection)
    logger.info(f"Database initialized: {db_path}")
    return _connection


def init_db(conn: sqlite3.Connection):
    """Create tables if they don't exist."""
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def close_db():
    """Close the database connection."""
    global _connection
    if _connection is not None:
        _connection.close()
        _connection = None
        logger.info("Database connection closed")
