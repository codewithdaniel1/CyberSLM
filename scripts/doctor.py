from __future__ import annotations

import importlib.util
import platform
import sqlite3
import sys

from cyberslm.code_validation import CCodeValidator
from cyberslm.config import settings
from cyberslm.knowledge import KnowledgeStore


def mark(ok: bool) -> str:
    return "OK" if ok else "MISSING"


def main() -> int:
    settings.ensure_directories()
    knowledge = KnowledgeStore(settings.knowledge_database_path).status()
    embedding_counts = {
        item["model"]: item["count"] for item in knowledge["embedding_models"]
    }
    embedded = embedding_counts.get(settings.rag_embedding_model, 0)
    code_validation = CCodeValidator(
        enabled=settings.code_validation_enabled,
        configured_compiler=settings.c_compiler,
        timeout_seconds=max(0.5, settings.code_validation_timeout),
    ).status
    checks = {
        "Python 3.11-3.13": (3, 11) <= sys.version_info[:2] < (3, 14),
        "Apple Silicon": platform.system() == "Darwin" and platform.machine() == "arm64",
        "FastAPI": importlib.util.find_spec("fastapi") is not None,
        "Streamlit": importlib.util.find_spec("streamlit") is not None,
        "MLX-VLM": importlib.util.find_spec("mlx_vlm") is not None,
        "FastEmbed": importlib.util.find_spec("fastembed") is not None,
        "Semantic index": embedded == knowledge["chunk_count"] > 0,
        "SQLite": sqlite3.sqlite_version_info >= (3, 35),
        "Writable data directory": settings.data_dir.is_dir(),
    }
    if code_validation["enabled"]:
        checks["C syntax checker (optional)"] = code_validation["available"]

    print("CyberSLM doctor")
    print(f"Model: {settings.model_id}")
    print(f"Backend: {settings.model_backend}")
    if code_validation["enabled"]:
        print(f"C compiler: {code_validation['compiler'] or 'not found'} (syntax-only)")
    else:
        print("C compiler: validation disabled")
    print(
        f"Knowledge: {knowledge['document_count']} documents / "
        f"{knowledge['chunk_count']} passages "
        f"({'ready' if knowledge['ready'] else 'not synced'})"
    )
    for name, ok in checks.items():
        print(f"[{mark(ok):7}] {name}")

    required = [checks["Python 3.11-3.13"], checks["FastAPI"], checks["Streamlit"]]
    if settings.model_backend == "mlx":
        required.extend([checks["Apple Silicon"], checks["MLX-VLM"]])
    if settings.rag_semantic_enabled:
        required.extend([checks["FastEmbed"], checks["Semantic index"]])
    return 0 if all(required) else 1


if __name__ == "__main__":
    raise SystemExit(main())
