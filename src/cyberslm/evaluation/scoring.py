from __future__ import annotations

import re
from typing import Any

from cyberslm.evaluation.schemas import EvalCase


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def score_response(case: EvalCase, response: str) -> dict[str, Any]:
    normalized = normalize(response)
    matched: list[list[str]] = []
    missing: list[list[str]] = []
    for alternatives in case.expected_concepts:
        destination = (
            matched if any(normalize(term) in normalized for term in alternatives) else missing
        )
        destination.append(list(alternatives))

    prohibited_hits = [term for term in case.prohibited_terms if normalize(term) in normalized]
    score = len(matched) / len(case.expected_concepts)
    return {
        "score": round(score, 4),
        "passed": score >= case.minimum_score and not prohibited_hits,
        "minimum_score": case.minimum_score,
        "matched_concepts": matched,
        "missing_concepts": missing,
        "prohibited_hits": prohibited_hits,
    }
