from __future__ import annotations

import os
import platform
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_MLX_MODEL_ID = "mlx-community/gemma-3-4b-it-4bit"
DEFAULT_TRANSFORMERS_MODEL_ID = "google/gemma-3-4b-it"
TRANSFORMERS_QUANTIZATION_MODES = ("none", "8bit", "4bit")


def default_model_backend() -> str:
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        return "mlx"
    return "transformers"


def default_model_id(backend: str) -> str:
    if backend == "transformers":
        return DEFAULT_TRANSFORMERS_MODEL_ID
    return DEFAULT_MLX_MODEL_ID


def _configured_model_backend() -> str:
    configured = os.getenv("CYBERSLM_MODEL_BACKEND", "auto").strip().lower()
    return default_model_backend() if configured in {"", "auto"} else configured


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
    embedding_cache_dir: Path = PROJECT_ROOT / "data" / "knowledge" / "models"
    model_backend: str = field(default_factory=_configured_model_backend)
    model_id: str = field(default_factory=lambda: os.getenv("CYBERSLM_MODEL_ID", "").strip())
    transformers_device: str = os.getenv("CYBERSLM_TRANSFORMERS_DEVICE", "auto").lower()
    transformers_revision: str = os.getenv("CYBERSLM_TRANSFORMERS_REVISION", "main").strip()
    transformers_quantization: str = os.getenv(
        "CYBERSLM_TRANSFORMERS_QUANTIZATION", "none"
    ).lower()
    adapter_path: Path | None = (
        Path(value).expanduser().resolve()
        if (value := os.getenv("CYBERSLM_ADAPTER_PATH", "").strip())
        else None
    )
    max_tokens: int = _int_env("CYBERSLM_MAX_TOKENS", 1024)
    temperature: float = _float_env("CYBERSLM_TEMPERATURE", 0.2)
    api_url: str = os.getenv("CYBERSLM_API_URL", "http://127.0.0.1:8000")
    api_host: str = os.getenv("CYBERSLM_API_HOST", "127.0.0.1")
    api_port: int = _int_env("CYBERSLM_API_PORT", 8000)
    ui_port: int = _int_env("CYBERSLM_UI_PORT", 8501)
    max_upload_mb: int = _int_env("CYBERSLM_MAX_UPLOAD_MB", 10)
    rag_enabled: bool = _bool_env("CYBERSLM_RAG_ENABLED", True)
    rag_semantic_enabled: bool = _bool_env("CYBERSLM_RAG_SEMANTIC_ENABLED", True)
    rag_embedding_model: str = os.getenv(
        "CYBERSLM_RAG_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"
    )
    rag_results: int = _int_env("CYBERSLM_RAG_RESULTS", 4)
    rag_max_chars: int = _int_env("CYBERSLM_RAG_MAX_CHARS", 16_000)
    code_validation_enabled: bool = _bool_env("CYBERSLM_CODE_VALIDATION_ENABLED", True)
    c_compiler: str | None = os.getenv("CYBERSLM_C_COMPILER", "").strip() or None
    code_validation_timeout: float = _float_env("CYBERSLM_CODE_VALIDATION_TIMEOUT", 4.0)

    def __post_init__(self) -> None:
        backend = self.model_backend.strip().lower()
        if backend in {"", "auto"}:
            backend = default_model_backend()
        object.__setattr__(self, "model_backend", backend)
        if not self.model_id.strip():
            object.__setattr__(self, "model_id", default_model_id(backend))
        if not self.transformers_revision:
            object.__setattr__(self, "transformers_revision", "main")
        quantization = self.transformers_quantization.strip().lower()
        if quantization not in TRANSFORMERS_QUANTIZATION_MODES:
            allowed = ", ".join(TRANSFORMERS_QUANTIZATION_MODES)
            raise ValueError(f"CYBERSLM_TRANSFORMERS_QUANTIZATION must be one of: {allowed}")
        object.__setattr__(self, "transformers_quantization", quantization)

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
