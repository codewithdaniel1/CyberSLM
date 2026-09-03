from dataclasses import replace
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

import cyberslm.api as api_module
from cyberslm.database import Database
from cyberslm.model import MockBackend


def test_chat_api_round_trip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(api_module, "db", Database(tmp_path / "api.db"))
    monkeypatch.setattr(api_module, "model_backend", MockBackend())
    client = TestClient(api_module.app)

    created = client.post("/api/conversations", json={"mode": "defensive"})
    assert created.status_code == 201
    conversation_id = created.json()["id"]

    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        data={"content": "Triage these failed SSH logins", "mode": "defensive"},
    )
    assert response.status_code == 200
    assert "Mock Defensive response" in response.json()["assistant"]["content"]

    loaded = client.get(f"/api/conversations/{conversation_id}").json()
    assert loaded["title"] == "Triage these failed SSH logins"
    assert len(loaded["messages"]) == 2


def test_rejects_unknown_mode(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(api_module, "db", Database(tmp_path / "api.db"))
    client = TestClient(api_module.app)
    response = client.post("/api/conversations", json={"mode": "invalid"})
    assert response.status_code == 422


def test_image_upload_is_saved_and_deleted(tmp_path: Path, monkeypatch) -> None:
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    test_settings = replace(
        api_module.settings,
        data_dir=tmp_path,
        upload_dir=upload_dir,
        database_path=tmp_path / "api.db",
    )
    monkeypatch.setattr(api_module, "settings", test_settings)
    monkeypatch.setattr(api_module, "db", Database(test_settings.database_path))
    monkeypatch.setattr(api_module, "model_backend", MockBackend())
    client = TestClient(api_module.app)

    image_bytes = BytesIO()
    Image.new("RGB", (4, 4), color="red").save(image_bytes, format="PNG")
    conversation = client.post("/api/conversations", json={"mode": "forensics"}).json()
    response = client.post(
        f"/api/conversations/{conversation['id']}/messages",
        data={"content": "Inspect this artifact", "mode": "forensics"},
        files=[("images", ("evidence.png", image_bytes.getvalue(), "image/png"))],
    )

    assert response.status_code == 200
    saved_path = Path(response.json()["user"]["attachments"][0]["path"])
    assert saved_path.is_file()
    assert saved_path.parent == upload_dir

    deleted = client.delete(f"/api/conversations/{conversation['id']}")
    assert deleted.status_code == 204
    assert not saved_path.exists()
