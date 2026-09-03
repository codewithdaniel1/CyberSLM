from dataclasses import replace
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

import cyberslm.api as api_module
from cyberslm.database import Database
from cyberslm.knowledge import KnowledgeStore
from cyberslm.model import MockBackend


def test_chat_api_round_trip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(api_module, "db", Database(tmp_path / "api.db"))
    monkeypatch.setattr(api_module, "model_backend", MockBackend())
    knowledge = KnowledgeStore(tmp_path / "knowledge.db")
    knowledge.replace_source(
        source_key="attack",
        source_name="MITRE ATT&CK",
        source_version="19.1",
        source_url="https://example.test/attack",
        source_sha256="abc",
        notice="Test",
        documents=[
            {
                "id": "attack:T1110",
                "external_id": "T1110",
                "title": "T1110 — Brute Force",
                "url": "https://attack.mitre.org/techniques/T1110/",
                "content": "Failed SSH logins can indicate password guessing and brute force.",
            }
        ],
    )
    monkeypatch.setattr(api_module, "knowledge_store", knowledge)
    client = TestClient(api_module.app)

    created = client.post(
        "/api/conversations",
        json={"mode": "defensive", "authorization_context": "defensive_operations"},
    )
    assert created.status_code == 201
    conversation_id = created.json()["id"]

    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        data={
            "content": "Triage these failed SSH logins",
            "mode": "defensive",
            "authorization_context": "defensive_operations",
        },
    )
    assert response.status_code == 200
    assert "Mock Defensive response" in response.json()["assistant"]["content"]
    assert "Local references consulted" in response.json()["assistant"]["content"]
    assert response.json()["knowledge"][0]["id"] == "attack:T1110"

    loaded = client.get(f"/api/conversations/{conversation_id}").json()
    assert loaded["title"] == "Triage these failed SSH logins"
    assert loaded["authorization_context"] == "defensive_operations"
    assert len(loaded["messages"]) == 2

    health = client.get("/api/health").json()
    assert health["knowledge"]["document_count"] == 1


def test_rejects_unknown_mode(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(api_module, "db", Database(tmp_path / "api.db"))
    client = TestClient(api_module.app)
    response = client.post("/api/conversations", json={"mode": "invalid"})
    assert response.status_code == 422

    contexts = client.get("/api/authorization-contexts")
    assert contexts.status_code == 200
    assert any(item["key"] == "owned_lab" for item in contexts.json())

    invalid_context = client.post(
        "/api/conversations",
        json={"mode": "general", "authorization_context": "self-declared-root"},
    )
    assert invalid_context.status_code == 422


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
