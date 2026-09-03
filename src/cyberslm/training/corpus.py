from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from cyberslm.modes import MODES

PLACEHOLDER_VALUES = {"", "unknown", "unreviewed", "todo", "tbd"}


@dataclass(frozen=True, slots=True)
class ValidatedCorpus:
    records: list[dict[str, Any]]
    manifest: dict[str, Any]
    sha256: str


def _required_text(value: Any, field: str, record_id: str) -> str:
    if not isinstance(value, str) or value.strip().casefold() in PLACEHOLDER_VALUES:
        raise ValueError(f"{record_id}: {field} must be a reviewed, non-placeholder string")
    return value.strip()


def load_records(path: Path) -> tuple[list[dict[str, Any]], str]:
    payload = path.read_bytes()
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(payload.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: each line must be a JSON object")
        records.append(value)
    return records, hashlib.sha256(payload).hexdigest()


def validate_corpus(dataset_path: Path, manifest_path: Path) -> ValidatedCorpus:
    records, digest = load_records(dataset_path)
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema_version") != 1:
        raise ValueError("Manifest schema_version must be 1")
    if manifest.get("sha256") != digest:
        raise ValueError(
            "Corpus SHA-256 does not match the reviewed manifest; review the changed file again"
        )
    _required_text(manifest.get("dataset_version"), "dataset_version", "manifest")
    _required_text(manifest.get("base_model"), "base_model", "manifest")
    _required_text(manifest.get("reviewer"), "reviewer", "manifest")
    reviewed_at = _required_text(manifest.get("reviewed_at"), "reviewed_at", "manifest")
    try:
        datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("manifest: reviewed_at must be an ISO-8601 timestamp") from exc
    allowed_licenses = manifest.get("allowed_licenses")
    if not isinstance(allowed_licenses, list) or not allowed_licenses:
        raise ValueError("manifest: allowed_licenses must be a non-empty list")
    allowed = {_required_text(value, "allowed_licenses", "manifest") for value in allowed_licenses}
    minimum_examples = manifest.get("minimum_examples", 50)
    if not isinstance(minimum_examples, int) or minimum_examples < 1:
        raise ValueError("manifest: minimum_examples must be a positive integer")
    if len(records) < minimum_examples:
        raise ValueError(
            f"Corpus has {len(records)} examples; reviewed minimum is {minimum_examples}"
        )

    seen: set[str] = set()
    splits: set[str] = set()
    for position, record in enumerate(records, start=1):
        record_id = _required_text(record.get("id"), "id", f"record {position}")
        if record_id in seen:
            raise ValueError(f"Duplicate training record id: {record_id}")
        seen.add(record_id)
        if record.get("mode") not in MODES:
            raise ValueError(f"{record_id}: mode must be one of {', '.join(MODES)}")
        split = record.get("split")
        if split not in {"train", "validation"}:
            raise ValueError(f"{record_id}: split must be train or validation")
        splits.add(split)
        license_name = _required_text(record.get("license"), "license", record_id)
        if license_name not in allowed:
            raise ValueError(
                f"{record_id}: license {license_name!r} is not allowed by the manifest"
            )
        _required_text(record.get("source"), "source", record_id)
        if record.get("approved_for_training") is not True:
            raise ValueError(f"{record_id}: approved_for_training must be true")
        if record.get("contains_private_data") is not False:
            raise ValueError(f"{record_id}: contains_private_data must be false")
        messages = record.get("messages")
        if not isinstance(messages, list) or len(messages) < 2:
            raise ValueError(f"{record_id}: messages must contain at least one user/assistant pair")
        if messages[-1].get("role") != "assistant":
            raise ValueError(f"{record_id}: final message must be from the assistant")
        for message in messages:
            if message.get("role") not in {"system", "user", "assistant"}:
                raise ValueError(f"{record_id}: unsupported message role")
            _required_text(message.get("content"), "message content", record_id)
    if splits != {"train", "validation"}:
        raise ValueError("Corpus must contain both train and validation splits")
    return ValidatedCorpus(records=records, manifest=manifest, sha256=digest)
