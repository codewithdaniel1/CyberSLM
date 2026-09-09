from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cyberslm.knowledge.sources import SOURCES, KnowledgeSource
from cyberslm.knowledge.store import KnowledgeStore

APPSEC_PRETRAINING_SOURCES = ("cwe", "capec")
SOURCE_TERMS = {
    "cwe": {
        "license": "CWE Terms of Use",
        "terms_url": "https://cwe.mitre.org/about/termsofuse.html",
    },
    "capec": {
        "license": "CAPEC Terms of Use",
        "terms_url": "https://capec.mitre.org/about/termsofuse.html",
    },
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _split(document_id: str, validation_percent: int) -> str:
    bucket = int(hashlib.sha256(document_id.encode()).hexdigest()[:8], 16) % 100
    return "validation" if bucket < validation_percent else "train"


def export_pretraining_corpus(
    store: KnowledgeStore,
    output_dir: Path,
    *,
    source_keys: tuple[str, ...] = APPSEC_PRETRAINING_SOURCES,
    validation_percent: int = 5,
    expected_sources: Mapping[str, KnowledgeSource] = SOURCES,
) -> dict[str, Any]:
    """Export verified normalized documents for raw-text continued pretraining."""
    if not source_keys:
        raise ValueError("At least one pretraining source is required")
    if not 1 <= validation_percent <= 50:
        raise ValueError("validation_percent must be between 1 and 50")
    unsupported = sorted(set(source_keys) - set(APPSEC_PRETRAINING_SOURCES))
    if unsupported:
        raise ValueError(
            "AppSec pretraining currently permits only cwe and capec; unsupported: "
            + ", ".join(unsupported)
        )

    status_sources = {item["source_key"]: item for item in store.status()["sources"]}
    for key in source_keys:
        expected = expected_sources[key]
        actual = status_sources.get(key)
        if actual is None:
            raise ValueError(f"Knowledge source {key} is not synced")
        if actual["version"] != expected.version or actual["sha256"] != expected.sha256:
            raise ValueError(
                f"Knowledge source {key} does not match pinned version/hash; run verify"
            )
        if actual["document_count"] != expected.document_count:
            raise ValueError(
                f"Knowledge source {key} has {actual['document_count']} documents; "
                f"expected {expected.document_count}"
            )

    documents = store.list_documents(source_keys=source_keys)
    if not documents:
        raise ValueError("No documents available for pretraining export")
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "train": output_dir / "train.jsonl",
        "validation": output_dir / "validation.jsonl",
    }
    streams = {split: path.open("w", encoding="utf-8") for split, path in paths.items()}
    counts = {"train": 0, "validation": 0}
    try:
        for document in documents:
            source_key = document["source_key"]
            expected = expected_sources[source_key]
            record = {
                "id": document["id"],
                "text": document["content"],
                "title": document["title"],
                "external_id": document["external_id"],
                "document_url": document["url"],
                "source": {
                    "key": source_key,
                    "name": expected.name,
                    "version": expected.version,
                    "archive_url": expected.url,
                    "archive_sha256": expected.sha256,
                    "notice": expected.notice,
                    **SOURCE_TERMS[source_key],
                },
            }
            split = _split(document["id"], validation_percent)
            streams[split].write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            counts[split] += 1
    finally:
        for stream in streams.values():
            stream.close()

    if not counts["train"] or not counts["validation"]:
        raise ValueError("Deterministic split produced an empty train or validation file")
    file_metadata = {
        split: {
            "path": path.name,
            "records": counts[split],
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for split, path in paths.items()
    }
    manifest = {
        "schema_version": 1,
        "format": "raw-text-continued-pretraining-jsonl",
        "content_field": "text",
        "split_method": f"sha256(document_id) modulo 100; < {validation_percent} validates",
        "sources": [
            {
                "key": key,
                "name": expected_sources[key].name,
                "version": expected_sources[key].version,
                "archive_sha256": expected_sources[key].sha256,
                "document_count": expected_sources[key].document_count,
                "notice": expected_sources[key].notice,
                **SOURCE_TERMS[key],
            }
            for key in source_keys
        ],
        "files": file_metadata,
        "total_records": len(documents),
    }
    manifest_path = output_dir / "pretraining-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"manifest": manifest, "manifest_path": manifest_path, "paths": paths}
