from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    project_root: Path = PROJECT_ROOT
    data_dir: Path = PROJECT_ROOT / "data"
    upload_dir: Path = PROJECT_ROOT / "data" / "uploads"
    database_path: Path = PROJECT_ROOT / "data" / "cyberslm.db"
    knowledge_dir: Path = PROJECT_ROOT / "data" / "knowledge"
    knowledge_database_path: Path = PROJECT_ROOT / "data" / "knowledge" / "knowledge.db"
    model_backend: str = os.getenv("CYBERSLM_MODEL_BACKEND", "mlx").lower()
    model_id: str = os.getenv("CYBERSLM_MODEL_ID", "mlx-community/gemma-3-4b-it-4bit")
    max_tokens: int = _int_env("CYBERSLM_MAX_TOKENS", 768)
    temperature: float = _float_env("CYBERSLM_TEMPERATURE", 0.2)
    api_url: str = os.getenv("CYBERSLM_API_URL", "http://127.0.0.1:8000")
    api_host: str = os.getenv("CYBERSLM_API_HOST", "127.0.0.1")
    api_port: int = _int_env("CYBERSLM_API_PORT", 8000)
    ui_port: int = _int_env("CYBERSLM_UI_PORT", 8501)
    max_upload_mb: int = _int_env("CYBERSLM_MAX_UPLOAD_MB", 10)
    rag_enabled: bool = _bool_env("CYBERSLM_RAG_ENABLED", True)
    rag_results: int = _int_env("CYBERSLM_RAG_RESULTS", 4)
    rag_max_chars: int = _int_env("CYBERSLM_RAG_MAX_CHARS", 16_000)

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
