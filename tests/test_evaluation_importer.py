from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from cyberslm.evaluation.importer import (
    download_source,
    sync_source,
    transform_purplellama_mitre_frr,
)
from cyberslm.evaluation.runner import load_dataset
from cyberslm.evaluation.sources import SOURCES


def source_for(payload: bytes, output: Path, record_count: int = 1):
    source = SOURCES["purplellama-mitre-frr"]
    return replace(
        source,
        url="https://example.test/mitre_frr.json",
        sha256=hashlib.sha256(payload).hexdigest(),
        record_count=record_count,
        output=output,
    )


def benign_payload() -> bytes:
    return json.dumps(
        [
            {
                "attack_type": "state-changing code",
                "is_malicious": False,
                "model": "upstream-model",
                "mutated_prompt": "Write a safe input-validation example.",
            }
        ]
    ).encode()


def test_transform_preserves_prompt_and_provenance(tmp_path: Path) -> None:
    payload = benign_payload()
    source = source_for(payload, tmp_path / "external.jsonl")

    cases = transform_purplellama_mitre_frr(payload, source)

    assert cases[0]["prompt"] == "Write a safe input-validation example."
    assert cases[0]["expected_concepts"] == []
    assert cases[0]["expected_behavior"] == "answer_safely"
    assert cases[0]["metadata"]["source_sha256"] == source.sha256
    assert cases[0]["metadata"]["upstream_is_malicious"] is False


def test_sync_writes_a_valid_behavior_dataset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = benign_payload()
    output = tmp_path / "external.jsonl"
    source = source_for(payload, output)
    monkeypatch.setattr(
        "cyberslm.evaluation.importer.download_source", lambda requested: payload
    )

    assert sync_source(source) == 1
    assert len(load_dataset(output)) == 1


def test_download_rejects_sha_mismatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    payload = benign_payload()
    source = replace(source_for(payload, tmp_path / "external.jsonl"), sha256="0" * 64)

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def raise_for_status(self) -> None:
            return None

        def iter_bytes(self):
            yield payload

    class Client:
        def __init__(self, **kwargs):
            del kwargs

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def stream(self, *args, **kwargs):
            del args, kwargs
            return Response()

    monkeypatch.setattr("cyberslm.evaluation.importer.httpx.Client", Client)

    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        download_source(source)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (json.dumps([]).encode(), "Expected 1 records"),
        (
            json.dumps(
                [
                    {
                        "is_malicious": True,
                        "mutated_prompt": "Malicious upstream label",
                    }
                ]
            ).encode(),
            "not labeled benign",
        ),
    ],
)
def test_transform_rejects_changed_upstream_data(
    payload: bytes, message: str, tmp_path: Path
) -> None:
    source = source_for(payload, tmp_path / "external.jsonl")

    with pytest.raises(RuntimeError, match=message):
        transform_purplellama_mitre_frr(payload, source)
