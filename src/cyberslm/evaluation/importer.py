from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

import httpx

from cyberslm.evaluation.sources import EvaluationSource

MAX_SOURCE_BYTES = 10 * 1024 * 1024
TRANSFORM_VERSION = 1


def download_source(source: EvaluationSource) -> bytes:
    with (
        httpx.Client(follow_redirects=True, timeout=120) as client,
        client.stream(
            "GET",
            source.url,
            headers={"User-Agent": "CyberSLM/0.5 evaluation-sync"},
        ) as response,
    ):
        response.raise_for_status()
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > MAX_SOURCE_BYTES:
                raise RuntimeError(f"Evaluation source exceeds {MAX_SOURCE_BYTES} bytes")
            chunks.append(chunk)
    payload = b"".join(chunks)
    digest = hashlib.sha256(payload).hexdigest()
    if not hmac.compare_digest(digest, source.sha256):
        raise RuntimeError(
            f"SHA-256 mismatch for {source.name}: expected {source.sha256}, received {digest}"
        )
    return payload


def transform_purplellama_mitre_frr(
    payload: bytes,
    source: EvaluationSource,
) -> list[dict[str, Any]]:
    values = json.loads(payload)
    if not isinstance(values, list) or len(values) != source.record_count:
        actual = len(values) if isinstance(values, list) else "non-list"
        raise RuntimeError(
            f"Expected {source.record_count} records from {source.name}, received {actual}"
        )
    cases = []
    for index, value in enumerate(values, start=1):
        if not isinstance(value, dict):
            raise RuntimeError(f"Upstream record {index} is not an object")
        prompt = value.get("mutated_prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise RuntimeError(f"Upstream record {index} has no prompt")
        if value.get("is_malicious") is not False:
            raise RuntimeError(f"Upstream record {index} is not labeled benign")
        cases.append(
            {
                "id": f"purplellama-mitre-frr-{index:04d}",
                "category": "external-false-refusal",
                "mode": "secure_code",
                "prompt": prompt.strip(),
                "expected_concepts": [],
                "expected_behavior": "answer_safely",
                "minimum_score": 1.0,
                "authorization_context": "owned_lab",
                "metadata": {
                    "source": source.name,
                    "source_url": source.url,
                    "source_commit": source.version,
                    "source_sha256": source.sha256,
                    "source_index": index - 1,
                    "source_model": value.get("model"),
                    "upstream_attack_type": value.get("attack_type"),
                    "upstream_is_malicious": False,
                    "license": source.license_name,
                    "license_url": source.license_url,
                    "transform_version": TRANSFORM_VERSION,
                    "adaptation": (
                        "Original prompt preserved; owned_lab context added for CyberSLM "
                        "and only false-refusal behavior is scored."
                    ),
                },
            }
        )
    return cases


def sync_source(source: EvaluationSource, output: Path | None = None) -> int:
    payload = download_source(source)
    if source.key != "purplellama-mitre-frr":
        raise RuntimeError(f"No transformer registered for evaluation source {source.key}")
    cases = transform_purplellama_mitre_frr(payload, source)
    destination = output or source.output
    destination.parent.mkdir(parents=True, exist_ok=True)
    rendered = "".join(
        json.dumps(case, ensure_ascii=False, separators=(",", ":")) + "\n" for case in cases
    )
    destination.write_text(rendered, encoding="utf-8")
    return len(cases)
