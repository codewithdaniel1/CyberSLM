import hashlib
import json
from pathlib import Path

import pytest

from cyberslm.knowledge.sources import KnowledgeSource
from cyberslm.knowledge.store import KnowledgeStore
from cyberslm.training.corpus import export_huggingface_splits, validate_corpus
from cyberslm.training.crypto_ctf import generate_crypto_ctf_drafts, promote_crypto_ctf_drafts
from cyberslm.training.pretraining import export_pretraining_corpus
from cyberslm.training.unsloth_run import (
    build_parser as build_unsloth_parser,
)
from cyberslm.training.unsloth_run import run as run_unsloth
from cyberslm.training.unsloth_run import validate_pretraining_export
from cyberslm.training.unsloth_sft import (
    build_parser as build_unsloth_sft_parser,
)
from cyberslm.training.unsloth_sft import run as run_unsloth_sft


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


def test_reviewed_corpus_exports_framework_neutral_chat_splits(tmp_path: Path) -> None:
    dataset, manifest = write_corpus(tmp_path)
    corpus = validate_corpus(dataset, manifest)

    paths = export_huggingface_splits(corpus, tmp_path / "export")

    train = [json.loads(line) for line in paths["train"].read_text().splitlines()]
    validation = [
        json.loads(line) for line in paths["validation"].read_text().splitlines()
    ]
    metadata = json.loads(paths["metadata"].read_text())
    assert [record["id"] for record in train] == ["train-1"]
    assert [record["id"] for record in validation] == ["validation-1"]
    assert train[0]["messages"][-1]["role"] == "assistant"
    assert metadata["format"] == "huggingface-chat-messages-jsonl"
    assert metadata["source_corpus_sha256"] == corpus.sha256
    assert metadata["splits"] == {"train": 1, "validation": 1}


def test_verified_knowledge_exports_deterministic_pretraining_splits(tmp_path: Path) -> None:
    source = KnowledgeSource(
        key="cwe",
        name="Test CWE",
        version="test-1",
        url="https://example.test/cwe.zip",
        filename="cwe.zip",
        sha256="a" * 64,
        document_count=20,
        notice="Test notice",
    )
    store = KnowledgeStore(tmp_path / "knowledge.db")
    store.replace_source(
        source_key=source.key,
        source_name=source.name,
        source_version=source.version,
        source_url=source.url,
        source_sha256=source.sha256,
        notice=source.notice,
        documents=[
            {
                "id": f"cwe:{index}",
                "external_id": f"CWE-{index}",
                "title": f"Weakness {index}",
                "url": f"https://example.test/cwe/{index}",
                "content": f"Reviewed weakness description {index}.",
            }
            for index in range(20)
        ],
    )

    first = export_pretraining_corpus(
        store,
        tmp_path / "first",
        source_keys=("cwe",),
        validation_percent=50,
        expected_sources={"cwe": source},
    )
    second = export_pretraining_corpus(
        store,
        tmp_path / "second",
        source_keys=("cwe",),
        validation_percent=50,
        expected_sources={"cwe": source},
    )

    assert first["manifest"]["total_records"] == 20
    assert first["manifest"]["files"] == second["manifest"]["files"]
    assert first["paths"]["train"].read_bytes() == second["paths"]["train"].read_bytes()
    assert first["paths"]["validation"].read_bytes() == second["paths"][
        "validation"
    ].read_bytes()
    record = json.loads(first["paths"]["train"].read_text().splitlines()[0])
    assert record["source"]["archive_sha256"] == source.sha256
    assert record["source"]["license"] == "CWE Terms of Use"
    validated = validate_pretraining_export(first["manifest_path"])
    assert validated["total_records"] == 20

    first["paths"]["train"].write_text(
        first["paths"]["train"].read_text() + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="byte count"):
        validate_pretraining_export(first["manifest_path"])


def test_pretraining_export_rejects_unverified_source_metadata(tmp_path: Path) -> None:
    expected = KnowledgeSource(
        key="cwe",
        name="Test CWE",
        version="expected",
        url="https://example.test/cwe.zip",
        filename="cwe.zip",
        sha256="a" * 64,
        document_count=1,
        notice="Test notice",
    )
    store = KnowledgeStore(tmp_path / "knowledge.db")
    store.replace_source(
        source_key="cwe",
        source_name="Test CWE",
        source_version="unexpected",
        source_url=expected.url,
        source_sha256="b" * 64,
        notice=expected.notice,
        documents=[
            {
                "id": "cwe:1",
                "external_id": "CWE-1",
                "title": "Weakness",
                "url": "https://example.test/cwe/1",
                "content": "Description.",
            }
        ],
    )

    with pytest.raises(ValueError, match="pinned version/hash"):
        export_pretraining_corpus(
            store,
            tmp_path / "output",
            source_keys=("cwe",),
            expected_sources={"cwe": expected},
        )


def test_unsloth_run_requires_explicit_review_confirmation() -> None:
    args = build_unsloth_parser().parse_args(
        ["--base-revision", "1234567890abcdef", "--validate-only"]
    )

    with pytest.raises(ValueError, match="--confirm-reviewed"):
        run_unsloth(args)


def test_unsloth_run_rejects_invalid_smoke_step_count() -> None:
    args = build_unsloth_parser().parse_args(
        [
            "--base-revision",
            "1234567890abcdef",
            "--max-steps",
            "0",
            "--confirm-reviewed",
            "--validate-only",
        ]
    )

    with pytest.raises(ValueError, match="max_steps must be positive"):
        run_unsloth(args)


def test_crypto_ctf_draft_generator_is_deterministic_and_unapproved(tmp_path: Path) -> None:
    first_path = tmp_path / "first.jsonl"
    second_path = tmp_path / "second.jsonl"

    first = generate_crypto_ctf_drafts(first_path, count=24, seed=7)
    generate_crypto_ctf_drafts(second_path, count=24, seed=7)

    assert first_path.read_bytes() == second_path.read_bytes()
    assert len(first) == 24
    assert {record["skill"] for record in first} == {
        "base64",
        "hex",
        "layered-base64-url",
        "base64-gzip",
        "safe-abstention-ambiguous",
        "hash-safe-abstention",
        "aes-safe-abstention",
        "pgp-safe-abstention",
        "toy-rsa",
        "repeating-key-xor",
        "jwt-recognition",
        "aead-nonce-reuse",
    }
    assert all(record["approved_for_training"] is False for record in first)
    assert all(record["review_status"] == "draft" for record in first)


def test_crypto_ctf_drafts_can_be_promoted_only_as_experimental(tmp_path: Path) -> None:
    drafts = tmp_path / "drafts.jsonl"
    generate_crypto_ctf_drafts(drafts, count=24, seed=7)

    paths = promote_crypto_ctf_drafts(drafts, tmp_path / "promoted", reviewer="Test operator")
    corpus = validate_corpus(paths["corpus"], paths["manifest"])

    assert len(corpus.records) == 24
    assert corpus.manifest["experimental"] is True
    assert all(record["approved_for_training"] is True for record in corpus.records)
    assert all(
        record["review_status"] == "experimental-operator-approved"
        for record in corpus.records
    )
    assert {record["split"] for record in corpus.records} == {"train", "validation"}


def test_unsloth_sft_preflight_validates_experimental_corpus(tmp_path: Path) -> None:
    drafts = tmp_path / "drafts.jsonl"
    generate_crypto_ctf_drafts(drafts, count=24, seed=7)
    paths = promote_crypto_ctf_drafts(drafts, tmp_path / "promoted", reviewer="Test operator")
    args = build_unsloth_sft_parser().parse_args(
        [
            "--dataset",
            str(paths["corpus"]),
            "--manifest",
            str(paths["manifest"]),
            "--base-revision",
            "1234567890abcdef",
            "--confirm-experimental-training",
            "--validate-only",
        ]
    )

    result = run_unsloth_sft(args)

    assert result["status"] == "validated"
    assert result["records"] == 24
    assert result["experimental"] is True
