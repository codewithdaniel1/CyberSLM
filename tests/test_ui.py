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
