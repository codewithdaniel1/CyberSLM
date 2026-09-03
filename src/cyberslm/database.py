from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT 'general',
                    authorization_context TEXT NOT NULL DEFAULT 'unspecified',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    attachments TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_messages_conversation_created
                    ON messages(conversation_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_conversations_updated
                    ON conversations(updated_at DESC);
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(conversations)").fetchall()
            }
            if "authorization_context" not in columns:
                connection.execute(
                    """ALTER TABLE conversations
                       ADD COLUMN authorization_context TEXT NOT NULL DEFAULT 'unspecified'"""
                )

    @staticmethod
    def _conversation(row: sqlite3.Row) -> dict[str, Any]:
        return dict(row)

    @staticmethod
    def _message(row: sqlite3.Row) -> dict[str, Any]:
        message = dict(row)
        message["attachments"] = json.loads(message["attachments"])
        return message

    def list_conversations(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM conversations ORDER BY updated_at DESC"
            ).fetchall()
        return [self._conversation(row) for row in rows]

    def get_conversation(self, conversation_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
        return self._conversation(row) if row else None

    def create_conversation(
        self,
        mode: str = "general",
        title: str = "New conversation",
        authorization_context: str = "unspecified",
    ) -> dict[str, Any]:
        conversation_id = str(uuid.uuid4())
        timestamp = utc_now()
        with self._lock, self._connect() as connection:
            connection.execute(
                """INSERT INTO conversations
                   (id, title, mode, authorization_context, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    conversation_id,
                    title,
                    mode,
                    authorization_context,
                    timestamp,
                    timestamp,
                ),
            )
        return self.get_conversation(conversation_id)  # type: ignore[return-value]

    def update_conversation(
        self,
        conversation_id: str,
        *,
        title: str | None = None,
        mode: str | None = None,
        authorization_context: str | None = None,
    ) -> dict[str, Any] | None:
        fields: list[str] = []
        values: list[str] = []
        if title is not None:
            fields.append("title = ?")
            values.append(title)
        if mode is not None:
            fields.append("mode = ?")
            values.append(mode)
        if authorization_context is not None:
            fields.append("authorization_context = ?")
            values.append(authorization_context)
        if not fields:
            return self.get_conversation(conversation_id)
        fields.append("updated_at = ?")
        values.append(utc_now())
        values.append(conversation_id)
        with self._lock, self._connect() as connection:
            connection.execute(f"UPDATE conversations SET {', '.join(fields)} WHERE id = ?", values)
        return self.get_conversation(conversation_id)

    def delete_conversation(self, conversation_id: str) -> bool:
        with self._lock, self._connect() as connection:
            result = connection.execute(
                "DELETE FROM conversations WHERE id = ?", (conversation_id,)
            )
        return result.rowcount > 0

    def list_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at, rowid",
                (conversation_id,),
            ).fetchall()
        return [self._message(row) for row in rows]

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        attachments: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        message_id = str(uuid.uuid4())
        timestamp = utc_now()
        serialized = json.dumps(attachments or [])
        with self._lock, self._connect() as connection:
            connection.execute(
                """INSERT INTO messages
                   (id, conversation_id, role, content, attachments, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (message_id, conversation_id, role, content, serialized, timestamp),
            )
            connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (timestamp, conversation_id),
            )
            row = connection.execute(
                "SELECT * FROM messages WHERE id = ?", (message_id,)
            ).fetchone()
        return self._message(row)
