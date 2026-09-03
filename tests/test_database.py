import sqlite3
from pathlib import Path

from cyberslm.database import Database


def test_conversation_and_message_lifecycle(tmp_path: Path) -> None:
    database = Database(tmp_path / "test.db")
    conversation = database.create_conversation(mode="ctf")

    database.add_message(
        conversation["id"],
        "user",
        "Inspect this challenge",
        [{"name": "screen.png", "content_type": "image/png", "path": "/tmp/screen.png"}],
    )
    database.add_message(conversation["id"], "assistant", "Start with the headers.")

    loaded = database.get_conversation(conversation["id"])
    messages = database.list_messages(conversation["id"])
    assert loaded is not None
    assert loaded["mode"] == "ctf"
    assert loaded["authorization_context"] == "unspecified"
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[0]["attachments"][0]["name"] == "screen.png"

    assert database.delete_conversation(conversation["id"])
    assert database.get_conversation(conversation["id"]) is None
    assert database.list_messages(conversation["id"]) == []


def test_update_conversation(tmp_path: Path) -> None:
    database = Database(tmp_path / "test.db")
    conversation = database.create_conversation()
    updated = database.update_conversation(
        conversation["id"],
        title="SSH triage",
        mode="defensive",
        authorization_context="defensive_operations",
    )

    assert updated is not None
    assert updated["title"] == "SSH triage"
    assert updated["mode"] == "defensive"
    assert updated["authorization_context"] == "defensive_operations"


def test_existing_database_is_migrated(tmp_path: Path) -> None:
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """CREATE TABLE conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'general',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        connection.execute(
            """INSERT INTO conversations
               (id, title, mode, created_at, updated_at)
               VALUES ('legacy', 'Existing chat', 'general', 'now', 'now')"""
        )

    database = Database(path)
    migrated = database.get_conversation("legacy")
    assert migrated is not None
    assert migrated["authorization_context"] == "unspecified"
