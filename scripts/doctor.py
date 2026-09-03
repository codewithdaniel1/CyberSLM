from __future__ import annotations

import importlib.util
import platform
import sqlite3
import sys

from cyberslm.config import settings


def mark(ok: bool) -> str:
    return "OK" if ok else "MISSING"


def main() -> int:
    settings.ensure_directories()
    checks = {
        "Python 3.11-3.13": (3, 11) <= sys.version_info[:2] < (3, 14),
        "Apple Silicon": platform.system() == "Darwin" and platform.machine() == "arm64",
        "FastAPI": importlib.util.find_spec("fastapi") is not None,
        "Streamlit": importlib.util.find_spec("streamlit") is not None,
        "MLX-VLM": importlib.util.find_spec("mlx_vlm") is not None,
        "SQLite": sqlite3.sqlite_version_info >= (3, 35),
        "Writable data directory": settings.data_dir.is_dir(),
    }

    print("CyberSLM doctor")
    print(f"Model: {settings.model_id}")
    print(f"Backend: {settings.model_backend}")
    for name, ok in checks.items():
        print(f"[{mark(ok):7}] {name}")

    required = [checks["Python 3.11-3.13"], checks["FastAPI"], checks["Streamlit"]]
    if settings.model_backend == "mlx":
        required.extend([checks["Apple Silicon"], checks["MLX-VLM"]])
    return 0 if all(required) else 1


if __name__ == "__main__":
    raise SystemExit(main())
