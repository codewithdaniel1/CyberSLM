from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
import uuid
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from typing import Any

from cyberslm import __version__
from cyberslm.evaluation.schemas import DatasetError, EvalCase
from cyberslm.evaluation.scoring import (
    score_citations,
    score_response,
    score_retrieval,
    score_safety,
)
from cyberslm.knowledge import KnowledgeStore
from cyberslm.knowledge.retrieve import RAG_POLICIES, decide_retrieval, retrieve
from cyberslm.model import GenerationRequest, ModelBackend
from cyberslm.modes import get_mode


def load_dataset(path: Path) -> list[EvalCase]:
    if not path.is_file():
        raise DatasetError(f"Dataset not found: {path}")

    cases: list[EvalCase] = []
    seen_ids: set[str] = set()
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DatasetError(f"Invalid JSON on line {line_number}: {exc.msg}") from exc
        try:
            case = EvalCase.from_dict(value, path.parent)
        except (DatasetError, TypeError, ValueError) as exc:
            raise DatasetError(f"Line {line_number}: {exc}") from exc
        if case.id in seen_ids:
            raise DatasetError(f"Duplicate case ID {case.id!r} on line {line_number}")
        seen_ids.add(case.id)
        cases.append(case)

    if not cases:
        raise DatasetError(f"Dataset contains no cases: {path}")
    return cases


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    def aggregate(items: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "cases": len(items),
            "passed": sum(item["evaluation"]["passed"] for item in items),
            "pass_rate": round(sum(item["evaluation"]["passed"] for item in items) / len(items), 4),
            "mean_score": round(fmean(item["evaluation"]["score"] for item in items), 4),
            "mean_latency_seconds": round(fmean(item["latency_seconds"] for item in items), 4),
        }

    categories: dict[str, list[dict[str, Any]]] = defaultdict(list)
    modes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        categories[result["category"]].append(result)
        modes[result["mode"]].append(result)
    retrieval = [item["retrieval_evaluation"] for item in results]
    retrieval = [item for item in retrieval if item is not None]
    citations = [item["citation_evaluation"] for item in results if item["knowledge"]]
    safety = [item["safety_evaluation"] for item in results]
    safety = [item for item in safety if item is not None]
    answer_safely = [item for item in safety if item["expected_behavior"] == "answer_safely"]
    false_refusals = sum(item["detected_refusal"] for item in answer_safely)
    generations = [item["generation"] for item in results]
    length_limited = sum(item["hit_token_limit"] for item in generations)
    known_finish_cases = sum(item["finish_reason"] != "unknown" for item in generations)
    generated_token_counts = [
        item["generated_tokens"]
        for item in generations
        if item["generated_tokens"] is not None
    ]
    finish_reasons: dict[str, int] = defaultdict(int)
    for generation in generations:
        finish_reasons[generation["finish_reason"]] += 1
    rag_decisions = [item["rag"] for item in results]
    rag_reasons: dict[str, int] = defaultdict(int)
    for decision in rag_decisions:
        rag_reasons[decision["reason"]] += 1
    return {
        "overall": aggregate(results),
        "categories": {name: aggregate(items) for name, items in sorted(categories.items())},
        "modes": {name: aggregate(items) for name, items in sorted(modes.items())},
        "rag": {
            "cases": len(rag_decisions),
            "attempted": sum(item["attempted"] for item in rag_decisions),
            "used": sum(item["used"] for item in rag_decisions),
            "reasons": dict(sorted(rag_reasons.items())),
        },
        "retrieval": {
            "cases": len(retrieval),
            "passed": sum(item["passed"] for item in retrieval),
            "pass_rate": round(sum(item["passed"] for item in retrieval) / len(retrieval), 4),
            "mean_recall": round(fmean(item["recall"] for item in retrieval), 4),
            "mean_precision": round(fmean(item["precision"] for item in retrieval), 4),
        }
        if retrieval
        else None,
        "citations": {
            "cases": len(citations),
            "complete": sum(item["complete"] for item in citations),
            "complete_rate": round(
                sum(item["complete"] for item in citations) / len(citations), 4
            ),
            "mean_coverage": round(fmean(item["coverage"] for item in citations), 4),
        }
        if citations
        else None,
        "safety": {
            "cases": len(safety),
            "passed": sum(item["passed"] for item in safety),
            "pass_rate": round(sum(item["passed"] for item in safety) / len(safety), 4),
            "answer_safely_cases": len(answer_safely),
            "false_refusals": false_refusals,
            "false_refusal_rate": (
                round(false_refusals / len(answer_safely), 4) if answer_safely else None
            ),
        }
        if safety
        else None,
        "generation": {
            "cases": len(generations),
            "known_finish_cases": known_finish_cases,
            "finish_reasons": dict(sorted(finish_reasons.items())),
            "length_limited": length_limited,
            "length_limited_rate": (
                round(length_limited / known_finish_cases, 4) if known_finish_cases else None
            ),
            "mean_generated_tokens": (
                round(fmean(generated_token_counts), 2) if generated_token_counts else None
            ),
        },
    }


class EvaluationRunner:
    def __init__(
        self,
        backend: ModelBackend,
        knowledge_store: KnowledgeStore | None = None,
        rag_results: int = 4,
        rag_max_chars: int = 16_000,
        embedder: Any | None = None,
        rag_policy: str = "auto",
    ):
        self.backend = backend
        self.knowledge_store = knowledge_store
        self.rag_results = rag_results
        self.rag_max_chars = rag_max_chars
        self.embedder = embedder
        normalized_policy = rag_policy.strip().casefold()
        if normalized_policy not in RAG_POLICIES:
            raise ValueError("Knowledge policy must be one of: auto, on, off")
        self.rag_policy = normalized_policy

    def run(
        self,
        cases: list[EvalCase],
        *,
        dataset_path: Path,
        configuration: dict[str, Any] | None = None,
        progress: Callable[[int, int, EvalCase], None] | None = None,
    ) -> dict[str, Any]:
        case_results: list[dict[str, Any]] = []
        for index, case in enumerate(cases, start=1):
            if progress:
                progress(index, len(cases), case)
            retrieval_decision = decide_retrieval(
                case.prompt,
                case.mode,
                self.rag_policy,
                enabled=self.knowledge_store is not None or self.rag_policy == "off",
            )
            knowledge_documents = (
                retrieve(
                    self.knowledge_store,
                    case.prompt,
                    case.mode,
                    limit=self.rag_results,
                    max_chars=self.rag_max_chars,
                    embedder=self.embedder,
                    source_keys=retrieval_decision.source_keys,
                )
                if self.knowledge_store and retrieval_decision.should_retrieve
                else []
            )
            request = GenerationRequest(
                mode=get_mode(case.mode),
                messages=[{"role": "user", "content": case.prompt, "attachments": []}],
                image_paths=list(case.image_paths),
                authorization_context=case.authorization_context,
                knowledge_documents=knowledge_documents,
            )
            started = time.perf_counter()
            generation = self.backend.generate_with_metadata(request)
            response = generation.text
            latency = time.perf_counter() - started
            evaluation = score_response(case, response)
            safety_evaluation = score_safety(case, response)
            if safety_evaluation is not None:
                evaluation["passed"] = evaluation["passed"] and safety_evaluation["passed"]
            case_results.append(
                {
                    "id": case.id,
                    "category": case.category,
                    "mode": case.mode,
                    "authorization_context": case.authorization_context,
                    "prompt": case.prompt,
                    "response": response,
                    "generation": generation.metadata(),
                    "knowledge": [
                        {
                            "id": document["id"],
                            "title": document["title"],
                            "url": document["url"],
                            "source_key": document["source_key"],
                            "source_version": document["source_version"],
                        }
                        for document in knowledge_documents
                    ],
                    "rag": retrieval_decision.metadata(len(knowledge_documents)),
                    "latency_seconds": round(latency, 4),
                    "evaluation": evaluation,
                    "retrieval_evaluation": (
                        score_retrieval(case, knowledge_documents)
                        if self.rag_policy != "off"
                        else None
                    ),
                    "citation_evaluation": score_citations(response, knowledge_documents),
                    "safety_evaluation": safety_evaluation,
                    "metadata": case.metadata,
                }
            )

        dataset_bytes = dataset_path.read_bytes()
        prompt_bytes = json.dumps(
            {
                case.id: get_mode(case.mode).build_system_prompt(case.authorization_context)
                for case in cases
            },
            sort_keys=True,
        ).encode()
        return {
            "schema_version": 1,
            "application_version": __version__,
            "run_id": str(uuid.uuid4()),
            "created_at": datetime.now(UTC).isoformat(),
            "dataset": {
                "path": str(dataset_path),
                "sha256": hashlib.sha256(dataset_bytes).hexdigest(),
                "cases": len(cases),
            },
            "configuration": configuration or {},
            "prompts_sha256": hashlib.sha256(prompt_bytes).hexdigest(),
            "model": self.backend.status,
            "knowledge": self.knowledge_store.status() if self.knowledge_store else None,
            "environment": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "implementation": sys.implementation.name,
            },
            "summary": summarize(case_results),
            "cases": case_results,
        }
