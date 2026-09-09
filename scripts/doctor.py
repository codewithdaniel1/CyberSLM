from __future__ import annotations

import importlib.util
import platform
import shutil
import sqlite3
import sys

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
    checks = {
        "Python 3.11-3.13": (3, 11) <= sys.version_info[:2] < (3, 14),
        "Apple Silicon": platform.system() == "Darwin" and platform.machine() == "arm64",
        "Ollama CLI": shutil.which("ollama") is not None,
        "MLX-VLM": importlib.util.find_spec("mlx_vlm") is not None,
        "Transformers": importlib.util.find_spec("transformers") is not None,
        "PyTorch": importlib.util.find_spec("torch") is not None,
        "Accelerate": importlib.util.find_spec("accelerate") is not None,
        "Bitsandbytes": importlib.util.find_spec("bitsandbytes") is not None,
        "FastEmbed": importlib.util.find_spec("fastembed") is not None,
        "Semantic index": embedded == knowledge["chunk_count"] > 0,
        "SQLite": sqlite3.sqlite_version_info >= (3, 35),
        "Writable data directory": settings.data_dir.is_dir(),
    }
    print("CyberSLM doctor")
    print(f"Model: {settings.model_id}")
    print(f"Backend: {settings.model_backend}")
    if settings.model_backend == "transformers":
        print(f"Portable device: {settings.transformers_device}")
        print(f"Portable quantization: {settings.transformers_quantization}")
    print(
        f"Knowledge: {knowledge['document_count']} documents / "
        f"{knowledge['chunk_count']} passages "
        f"({'ready' if knowledge['ready'] else 'not synced'})"
    )
    for name, ok in checks.items():
        print(f"[{mark(ok):7}] {name}")

    required = [checks["Python 3.11-3.13"]]
    if settings.model_backend == "ollama":
        required.append(checks["Ollama CLI"])
    if settings.model_backend == "mlx":
        required.extend([checks["Apple Silicon"], checks["MLX-VLM"]])
    elif settings.model_backend == "transformers":
        required.extend([checks["Transformers"], checks["PyTorch"]])
        if settings.transformers_quantization != "none":
            required.extend([checks["Accelerate"], checks["Bitsandbytes"]])
    if settings.rag_semantic_enabled:
        required.extend([checks["FastEmbed"], checks["Semantic index"]])
    return 0 if all(required) else 1


if __name__ == "__main__":
    raise SystemExit(main())
