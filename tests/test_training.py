import hashlib
import json
from pathlib import Path

import pytest

from cyberslm.training.corpus import validate_corpus


def write_corpus(tmp_path: Path, *, private: bool = False) -> tuple[Path, Path]:
    records = [
        {
            "id": "train-1",
            "mode": "defensive",
            "split": "train",
            "source": "Synthetic test fixture",
            "license": "CC0-1.0",
            "approved_for_training": True,
            "contains_private_data": private,
            "messages": [
                {"role": "user", "content": "Triage failed logins"},
                {
                    "role": "assistant",
                    "content": "Preserve and correlate authentication logs.",
                },
            ],
        },
        {
            "id": "validation-1",
            "mode": "secure_code",
            "split": "validation",
            "source": "Synthetic test fixture",
            "license": "CC0-1.0",
            "approved_for_training": True,
            "contains_private_data": False,
            "messages": [
                {"role": "user", "content": "Fix SQL injection"},
                {"role": "assistant", "content": "Use a parameterized query."},
            ],
        },
    ]
    dataset = tmp_path / "corpus.jsonl"
    payload = "".join(json.dumps(record) + "\n" for record in records).encode()
    dataset.write_bytes(payload)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "dataset_version": "test-v1",
                "base_model": "mlx-community/gemma-3-4b-it-4bit",
                "reviewer": "Test reviewer",
                "reviewed_at": "2026-09-03T12:00:00Z",
                "allowed_licenses": ["CC0-1.0"],
                "minimum_examples": 2,
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    )
    return dataset, manifest


def test_reviewed_training_corpus_validates(tmp_path: Path) -> None:
    dataset, manifest = write_corpus(tmp_path)
    corpus = validate_corpus(dataset, manifest)
    assert len(corpus.records) == 2
    assert corpus.manifest["dataset_version"] == "test-v1"


def test_training_corpus_rejects_private_data(tmp_path: Path) -> None:
    dataset, manifest = write_corpus(tmp_path, private=True)
    with pytest.raises(ValueError, match="contains_private_data"):
        validate_corpus(dataset, manifest)


def test_training_corpus_rejects_changes_after_review(tmp_path: Path) -> None:
    dataset, manifest = write_corpus(tmp_path)
    dataset.write_text(dataset.read_text() + "\n")
    with pytest.raises(ValueError, match="SHA-256"):
        validate_corpus(dataset, manifest)
