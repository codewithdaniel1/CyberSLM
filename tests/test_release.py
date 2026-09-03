from pathlib import Path
from tomllib import loads

from cyberslm import __version__

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_project_version_is_consistent() -> None:
    project = loads((PROJECT_ROOT / "pyproject.toml").read_text())
    lock = (PROJECT_ROOT / "uv.lock").read_text()
    api = (PROJECT_ROOT / "src" / "cyberslm" / "api.py").read_text()

    assert project["project"]["version"] == __version__
    assert f'version="{__version__}"' in api
    assert f'name = "cyberslm"\nversion = "{__version__}"' in lock


def test_generated_data_stays_ignored() -> None:
    ignore = (PROJECT_ROOT / ".gitignore").read_text().splitlines()
    assert "data/knowledge/*" in ignore
    assert "evals/results/*" in ignore
