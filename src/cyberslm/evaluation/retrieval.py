from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from typing import Any

from cyberslm import __version__
from cyberslm.evaluation.schemas import EvalCase
from cyberslm.evaluation.scoring import score_retrieval
from cyberslm.knowledge import KnowledgeStore
from cyberslm.knowledge.retrieve import QueryEmbedder, retrieve


def evaluate_retrieval(
    cases: list[EvalCase],
    *,
    dataset_path: Path,
    store: KnowledgeStore,
    embedder: QueryEmbedder | None,
    limit: int,
    max_chars: int,
    progress: Callable[[int, int, EvalCase], None] | None = None,
) -> dict[str, Any]:
    results = []
    for index, case in enumerate(cases, start=1):
        if progress:
            progress(index, len(cases), case)
        started = time.perf_counter()
        documents = retrieve(
            store,
            case.prompt,
            case.mode,
            limit=limit,
            max_chars=max_chars,
            embedder=embedder,
        )
        latency = time.perf_counter() - started
        evaluation = score_retrieval(case, documents)
        if evaluation is None:
            raise ValueError(f"Retrieval case {case.id!r} has no expected_references")
        results.append(
            {
                "id": case.id,
                "category": case.category,
                "mode": case.mode,
                "prompt": case.prompt,
                "expected_references": list(case.expected_references or ()),
                "retrieved": [
                    {
                        "id": document["id"],
                        "external_id": document["external_id"],
                        "title": document["title"],
                        "source_key": document["source_key"],
                        "source_version": document["source_version"],
                        "retrieval_method": document["retrieval_method"],
                        "relevance": document["relevance"],
                    }
                    for document in documents
                ],
                "latency_seconds": round(latency, 4),
                "evaluation": evaluation,
                "metadata": case.metadata,
            }
        )

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
        "configuration": {
            "limit": limit,
            "max_chars": max_chars,
            "semantic": embedder is not None,
            "embedding_model": embedder.model_name if embedder else None,
        },
        "knowledge": store.status(),
        "summary": {
            "cases": len(results),
            "passed": sum(item["evaluation"]["passed"] for item in results),
            "pass_rate": round(
                sum(item["evaluation"]["passed"] for item in results) / len(results), 4
            ),
            "mean_recall": round(
                fmean(item["evaluation"]["recall"] for item in results), 4
            ),
            "mean_precision": round(
                fmean(item["evaluation"]["precision"] for item in results), 4
            ),
            "mean_latency_seconds": round(fmean(item["latency_seconds"] for item in results), 4),
        },
        "cases": results,
        "report_sha256": "",
    }


def finalize_report(report: dict[str, Any]) -> dict[str, Any]:
    canonical = json.dumps({**report, "report_sha256": ""}, sort_keys=True).encode()
    report["report_sha256"] = hashlib.sha256(canonical).hexdigest()
    return report
