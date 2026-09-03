from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from cyberslm.knowledge.store import KnowledgeStore

# Official ONNX Runtime builds enable telemetry by default on non-Windows platforms.
# CyberSLM is local-first, so disable it before FastEmbed imports ONNX Runtime.
os.environ["ORT_DISABLE_TELEMETRY"] = "1"

DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"


class LocalEmbedder:
    """Lazy FastEmbed wrapper; the ONNX model is downloaded only when explicitly used."""

    def __init__(
        self,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        cache_dir: Path | None = None,
        *,
        allow_download: bool = False,
    ):
        self.model_name = model_name
        self.cache_dir = cache_dir
        self.allow_download = allow_download
        self._model: Any = None

    def _load(self) -> Any:
        if self._model is None:
            try:
                from fastembed import TextEmbedding
            except ImportError as exc:  # pragma: no cover - installation-specific
                raise RuntimeError(
                    "Semantic retrieval requires FastEmbed. Run `uv sync` and rebuild "
                    "knowledge embeddings."
                ) from exc
            kwargs: dict[str, Any] = {"model_name": self.model_name}
            if self.cache_dir is not None:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                kwargs["cache_dir"] = str(self.cache_dir)
            kwargs["local_files_only"] = not self.allow_download
            self._model = TextEmbedding(**kwargs)
        return self._model

    def embed_query(self, query: str) -> list[float]:
        model = self._load()
        vector = next(iter(model.embed([query])))
        return vector.astype("float32").tolist()

    def embed_passages(self, passages: Iterable[str]) -> Iterable[list[float]]:
        model = self._load()
        inputs = (f"passage: {passage}" for passage in passages)
        for vector in model.embed(inputs, batch_size=64):
            yield vector.astype("float32").tolist()


def rebuild_embeddings(
    store: KnowledgeStore,
    embedder: LocalEmbedder,
    *,
    source_keys: tuple[str, ...] | None = None,
    progress: Any | None = None,
) -> int:
    chunks = store.list_chunks(
        source_keys=source_keys,
        missing_embedding_model=embedder.model_name,
    )
    completed = 0
    batch_size = 64
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        vectors = list(
            embedder.embed_passages(
                f"{chunk['title']}\n{chunk['content']}" for chunk in batch
            )
        )
        completed += store.upsert_embeddings(
            embedder.model_name,
            (
                (chunk["chunk_id"], vector)
                for chunk, vector in zip(batch, vectors, strict=True)
            ),
        )
        if progress:
            progress(completed, len(chunks))
    return completed
