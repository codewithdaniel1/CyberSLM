from pathlib import Path
from tomllib import loads

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_streamlit_theme_is_always_light() -> None:
    config = loads((PROJECT_ROOT / ".streamlit" / "config.toml").read_text())
    assert config["theme"]["base"] == "light"
    assert config["theme"]["backgroundColor"] == "#F7FAFC"


def test_ui_css_declares_light_color_scheme() -> None:
    source = (PROJECT_ROOT / "ui" / "app.py").read_text()
    assert "color-scheme: light" in source


def test_sidebar_has_confirmed_conversation_deletion() -> None:
    source = (PROJECT_ROOT / "ui" / "app.py").read_text()
    assert "Delete current conversation" in source
    assert "confirm-delete-conversation" in source
    assert 'api_request("DELETE"' in source


def test_ui_records_authorization_context() -> None:
    source = (PROJECT_ROOT / "ui" / "app.py").read_text()
    assert "Environment / authorization context" in source
    assert "/api/authorization-contexts" in source
    assert "does not verify permission or override safety boundaries" in source


def test_ui_displays_local_knowledge_status() -> None:
    source = (PROJECT_ROOT / "ui" / "app.py").read_text()
    assert "Hybrid RAG ready" in source
    assert "Lexical RAG ready" in source
    assert "RAG empty" in source
    assert "local source(s) selected" in source
    assert "retrieval_method" in source
    assert "Sync verified knowledge" in source
    assert 'options=["Auto", "On", "Off"]' in source
    assert '"rag_policy": (rag_policy or "Auto").lower()' in source


def test_ui_uses_cancellable_streaming_generation() -> None:
    source = (PROJECT_ROOT / "ui" / "app.py").read_text()
    assert "/messages/stream" in source
    assert "Stop generating" in source
    assert "/api/generations/" in source
