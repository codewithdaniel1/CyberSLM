import json
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
    assert (
        "Local references retrieved — inline citations: 0/1; exact-ID citations: 0/1"
        in response.json()["assistant"]["content"]
    )
    assert "— not explicitly referenced" in response.json()["assistant"]["content"]
    assert response.json()["knowledge"][0]["id"] == "attack:T1110"
    assert response.json()["rag"] == {
        "policy": "auto",
        "attempted": True,
        "used": True,
        "reason": "source_relevant",
        "source_keys": ["attack"],
        "document_count": 1,
    }

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


def test_chat_api_streams_ndjson_and_persists_on_completion(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(api_module, "db", Database(tmp_path / "api.db"))
    monkeypatch.setattr(api_module, "model_backend", MockBackend())
    monkeypatch.setattr(api_module, "knowledge_store", KnowledgeStore(tmp_path / "knowledge.db"))
    client = TestClient(api_module.app)
    conversation = client.post("/api/conversations", json={"mode": "general"}).json()

    response = client.post(
        f"/api/conversations/{conversation['id']}/messages/stream",
        data={"content": "Explain a firewall", "mode": "general"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[0]["type"] == "start"
    assert events[0]["rag"]["policy"] == "auto"
    assert events[0]["rag"]["attempted"] is False
    assert events[0]["rag"]["reason"] == "not_source_relevant"
    assert any(event["type"] == "token" for event in events)
    assert events[-1]["type"] == "done"

    loaded = client.get(f"/api/conversations/{conversation['id']}").json()
    assert [message["role"] for message in loaded["messages"]] == ["user", "assistant"]


def test_chat_api_validates_and_honors_rag_policy(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(api_module, "db", Database(tmp_path / "api.db"))
    monkeypatch.setattr(api_module, "model_backend", MockBackend())
    monkeypatch.setattr(api_module, "knowledge_store", KnowledgeStore(tmp_path / "knowledge.db"))
    client = TestClient(api_module.app)
    conversation = client.post("/api/conversations", json={"mode": "general"}).json()
    endpoint = f"/api/conversations/{conversation['id']}/messages"

    invalid = client.post(endpoint, data={"content": "Hello", "rag_policy": "sometimes"})
    assert invalid.status_code == 422

    forced = client.post(endpoint, data={"content": "Hello", "rag_policy": "on"})
    assert forced.status_code == 200
    assert forced.json()["rag"]["attempted"] is True
    assert forced.json()["rag"]["reason"] == "forced_for_message"

    second_conversation = client.post("/api/conversations", json={"mode": "general"}).json()
    disabled = client.post(
        f"/api/conversations/{second_conversation['id']}/messages",
        data={"content": "Explain T1110", "rag_policy": "off"},
    )
    assert disabled.status_code == 200
    assert disabled.json()["rag"]["attempted"] is False
    assert disabled.json()["rag"]["reason"] == "disabled_for_message"


def test_chat_api_can_request_non_executing_code_validation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(api_module, "db", Database(tmp_path / "api.db"))
    monkeypatch.setattr(api_module, "model_backend", MockBackend())
    monkeypatch.setattr(api_module, "knowledge_store", KnowledgeStore(tmp_path / "knowledge.db"))
    client = TestClient(api_module.app)
    conversation = client.post("/api/conversations", json={"mode": "secure_code"}).json()

    response = client.post(
        f"/api/conversations/{conversation['id']}/messages",
        data={"content": "Write C", "validate_code": "true"},
    )

    assert response.status_code == 200
    assert response.json()["code_validation"]["requested"] is True
    assert response.json()["code_validation"]["status"] == "no_c_blocks"
    assert "generated code was not executed" in response.json()["assistant"]["content"]
    assert "syntax-only" in client.get("/api/health").json()["code_validation"]["execution"]


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
