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
from cyberslm.evaluation.scoring import score_response
from cyberslm.model import GenerationRequest, ModelBackend
from cyberslm.modes import MODES, get_mode


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
    for result in results:
        categories[result["category"]].append(result)
    return {
        "overall": aggregate(results),
        "categories": {name: aggregate(items) for name, items in sorted(categories.items())},
    }


class EvaluationRunner:
    def __init__(self, backend: ModelBackend):
        self.backend = backend

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
            request = GenerationRequest(
                mode=get_mode(case.mode),
                messages=[{"role": "user", "content": case.prompt, "attachments": []}],
                image_paths=list(case.image_paths),
            )
            started = time.perf_counter()
            response = self.backend.generate(request)
            latency = time.perf_counter() - started
            case_results.append(
                {
                    "id": case.id,
                    "category": case.category,
                    "mode": case.mode,
                    "prompt": case.prompt,
                    "response": response,
                    "latency_seconds": round(latency, 4),
                    "evaluation": score_response(case, response),
                    "metadata": case.metadata,
                }
            )

        dataset_bytes = dataset_path.read_bytes()
        prompt_bytes = json.dumps(
            {key: mode.system_prompt for key, mode in MODES.items()}, sort_keys=True
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
            "environment": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "implementation": sys.implementation.name,
            },
            "summary": summarize(case_results),
            "cases": case_results,
        }
