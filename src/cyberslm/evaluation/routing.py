from __future__ import annotations

import hashlib
import time
import uuid
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cyberslm import __version__
from cyberslm.evaluation.schemas import EvalCase
from cyberslm.knowledge.retrieve import decide_retrieval


def evaluate_rag_gate(
    cases: list[EvalCase],
    *,
    dataset_path: Path,
    progress: Callable[[int, int, EvalCase], None] | None = None,
) -> dict[str, Any]:
    """Evaluate Auto RAG routing without querying the index or running a model."""
    results: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        if progress:
            progress(index, len(cases), case)
        if case.expected_retrieval is None:
            raise ValueError(f"RAG gate case {case.id!r} has no expected_retrieval label")

        started = time.perf_counter()
        decision = decide_retrieval(case.prompt, case.mode, "auto")
        latency = time.perf_counter() - started
        results.append(
            {
                "id": case.id,
                "category": case.category,
                "mode": case.mode,
                "prompt": case.prompt,
                "expected_retrieval": case.expected_retrieval,
                "predicted_retrieval": decision.should_retrieve,
                "passed": decision.should_retrieve == case.expected_retrieval,
                "decision": {
                    "policy": decision.policy,
                    "should_retrieve": decision.should_retrieve,
                    "reason": decision.reason,
                    "source_keys": list(decision.source_keys),
                },
                "latency_seconds": round(latency, 6),
                "metadata": case.metadata,
            }
        )

    true_positive = sum(
        item["expected_retrieval"] and item["predicted_retrieval"] for item in results
    )
    true_negative = sum(
        not item["expected_retrieval"] and not item["predicted_retrieval"] for item in results
    )
    false_positive = sum(
        not item["expected_retrieval"] and item["predicted_retrieval"] for item in results
    )
    false_negative = sum(
        item["expected_retrieval"] and not item["predicted_retrieval"] for item in results
    )
    positives = true_positive + false_negative
    negatives = true_negative + false_positive
    predicted_positives = true_positive + false_positive
    reason_counts = Counter(item["decision"]["reason"] for item in results)

    return {
        "schema_version": 1,
        "application_version": __version__,
        "run_id": str(uuid.uuid4()),
        "created_at": datetime.now(UTC).isoformat(),
        "dataset": {
            "path": str(dataset_path),
            "sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
            "cases": len(cases),
        },
        "configuration": {"policy": "auto", "requires_knowledge_index": False},
        "summary": {
            "cases": len(results),
            "passed": true_positive + true_negative,
            "accuracy": round((true_positive + true_negative) / len(results), 4),
            "precision": round(
                true_positive / predicted_positives if predicted_positives else 1.0,
                4,
            ),
            "recall": round(true_positive / positives if positives else 1.0, 4),
            "false_positive_rate": round(false_positive / negatives if negatives else 0.0, 4),
            "false_negative_rate": round(false_negative / positives if positives else 0.0, 4),
            "confusion_matrix": {
                "true_positive": true_positive,
                "true_negative": true_negative,
                "false_positive": false_positive,
                "false_negative": false_negative,
            },
            "reason_counts": dict(sorted(reason_counts.items())),
        },
        "cases": results,
        "report_sha256": "",
    }
