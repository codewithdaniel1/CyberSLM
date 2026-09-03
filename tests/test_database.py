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
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[0]["attachments"][0]["name"] == "screen.png"

    assert database.delete_conversation(conversation["id"])
    assert database.get_conversation(conversation["id"]) is None
    assert database.list_messages(conversation["id"]) == []


def test_update_conversation(tmp_path: Path) -> None:
    database = Database(tmp_path / "test.db")
    conversation = database.create_conversation()
    updated = database.update_conversation(conversation["id"], title="SSH triage", mode="defensive")

    assert updated is not None
    assert updated["title"] == "SSH triage"
    assert updated["mode"] == "defensive"
