from __future__ import annotations

import re

DEFAULT_CHUNK_CHARS = 1_200
DEFAULT_OVERLAP_CHARS = 160
CHUNKING_VERSION = 1


def chunk_text(
    value: str,
    *,
    max_chars: int = DEFAULT_CHUNK_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> list[str]:
    """Split reference text into deterministic, slightly overlapping passages."""
    text = re.sub(r"[ \t]+", " ", value).strip()
    if not text:
        return []
    if max_chars < 200:
        raise ValueError("max_chars must be at least 200")
    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be non-negative and smaller than max_chars")

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            boundary = max(
                text.rfind("\n", start + max_chars // 2, end),
                text.rfind(". ", start + max_chars // 2, end),
                text.rfind("; ", start + max_chars // 2, end),
                text.rfind(" ", start + max_chars // 2, end),
            )
            if boundary > start:
                end = min(end, boundary + (1 if text[boundary] == "\n" else 2))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap_chars, start + 1)
    return chunks
