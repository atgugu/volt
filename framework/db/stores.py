"""
Data store classes for sessions, conversations, and completions.

Each store wraps a shared sqlite3.Connection and provides typed
CRUD operations for its table.
"""

import json
import logging
import sqlite3
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SessionStore:
    """Manages session metadata in SQLite."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, session_id: str, agent_id: str, voice_mode: bool = False):
        """Create a new session record."""
        self.conn.execute(
            "INSERT INTO sessions (session_id, agent_id, voice_mode) VALUES (?, ?, ?)",
            (session_id, agent_id, int(voice_mode)),
        )
        self.conn.commit()

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session metadata by ID."""
        row = self.conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        return {
            "session_id": row["session_id"],
            "agent_id": row["agent_id"],
            "created_at": row["created_at"],
            "is_complete": bool(row["is_complete"]),
            "voice_mode": bool(row["voice_mode"]),
        }

    def mark_complete(self, session_id: str):
        """Mark a session as complete."""
        self.conn.execute(
            "UPDATE sessions SET is_complete = 1 WHERE session_id = ?",
            (session_id,),
        )
        self.conn.commit()

    def list_active(self) -> List[Dict[str, Any]]:
        """List all active (incomplete) sessions."""
        rows = self.conn.execute(
            "SELECT * FROM sessions WHERE is_complete = 0 ORDER BY created_at DESC"
        ).fetchall()
        return [
            {
                "session_id": row["session_id"],
                "agent_id": row["agent_id"],
                "created_at": row["created_at"],
                "voice_mode": bool(row["voice_mode"]),
            }
            for row in rows
        ]

    def count_active(self) -> int:
        """Count active sessions."""
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM sessions WHERE is_complete = 0"
        ).fetchone()
        return row["cnt"]


class ConversationStore:
    """Manages conversation message history in SQLite."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add_message(self, session_id: str, role: str, content: str):
        """Add a message to the conversation history."""
        self.conn.execute(
            "INSERT INTO conversations (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, role, content),
        )
        self.conn.commit()

    def get_history(self, session_id: str) -> List[Dict[str, str]]:
        """Get the full conversation history for a session."""
        rows = self.conn.execute(
            "SELECT role, content, timestamp FROM conversations "
            "WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
        return [
            {"role": row["role"], "content": row["content"], "timestamp": row["timestamp"]}
            for row in rows
        ]


class CompletionStore:
    """Manages completed conversation data in SQLite."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save(
        self,
        session_id: str,
        agent_id: str,
        collected_fields: Dict[str, Any],
        result_data: Optional[Dict[str, Any]] = None,
    ):
        """Save completion data for a session."""
        self.conn.execute(
            "INSERT OR REPLACE INTO completions "
            "(session_id, agent_id, collected_fields, result_data) "
            "VALUES (?, ?, ?, ?)",
            (
                session_id,
                agent_id,
                json.dumps(collected_fields),
                json.dumps(result_data) if result_data else None,
            ),
        )
        self.conn.commit()

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get completion data for a session."""
        row = self.conn.execute(
            "SELECT * FROM completions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        return {
            "session_id": row["session_id"],
            "agent_id": row["agent_id"],
            "collected_fields": json.loads(row["collected_fields"]),
            "completed_at": row["completed_at"],
            "result_data": json.loads(row["result_data"]) if row["result_data"] else None,
        }

    def list_all(self) -> List[Dict[str, Any]]:
        """List all completions."""
        rows = self.conn.execute(
            "SELECT * FROM completions ORDER BY completed_at DESC"
        ).fetchall()
        return [
            {
                "session_id": row["session_id"],
                "agent_id": row["agent_id"],
                "collected_fields": json.loads(row["collected_fields"]),
                "completed_at": row["completed_at"],
                "result_data": json.loads(row["result_data"]) if row["result_data"] else None,
            }
            for row in rows
        ]
