from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from cyberslm.evaluation.compare import load_report
from cyberslm.model import SOURCE_FOOTER_MARKER, reference_attribution_statuses

SUPPORT_REVIEW_SCHEMA_VERSION = 1
SUPPORT_VERDICTS = {
    "supported",
    "partially_supported",
    "unsupported",
    "not_a_factual_claim",
    "unable_to_assess",
}
NOTE_REQUIRED_VERDICTS = SUPPORT_VERDICTS - {"supported"}


class SupportReviewError(ValueError):
    """Raised when a claim-support worksheet is incomplete or inconsistent."""


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _identifier_pattern(external_id: str) -> re.Pattern[str]:
    return re.compile(
        rf"(?<![A-Za-z0-9]){re.escape(external_id.strip())}(?![A-Za-z0-9])",
        re.IGNORECASE,
    )


def _response_segments(response: str) -> list[str]:
    body = response.split(SOURCE_FOOTER_MARKER, maxsplit=1)[0]
    segments: list[str] = []
    for line in body.splitlines():
        cleaned = line.strip()
        if not cleaned or cleaned.startswith("```"):
            continue
        for segment in re.split(r"(?<=[.!?])\s+", cleaned):
            if segment.strip():
                segments.append(segment.strip())
    return segments


def collect_support_candidates(
    response: str,
    documents: list[dict[str, Any]],
) -> dict[str, Any]:
    """Extract source-linked answer spans for review without assigning support verdicts."""
    statuses = reference_attribution_statuses(response, documents)
    segments = _response_segments(response)
    claims: list[dict[str, Any]] = []
    references_with_claims: set[int] = set()
    per_reference_count: dict[int, int] = {}

    for status in statuses:
        index = status["index"]
        external_id = status["external_id"]
        identifier = (
            _identifier_pattern(external_id)
            if isinstance(external_id, str) and external_id.strip()
            else None
        )
        citation = re.compile(rf"\[{index}]")
        for segment in segments:
            has_identifier = bool(identifier and identifier.search(segment))
            has_citation = bool(citation.search(segment))
            if not has_identifier and not has_citation:
                continue
            per_reference_count[index] = per_reference_count.get(index, 0) + 1
            references_with_claims.add(index)
            claims.append(
                {
                    "id": f"reference-{index}-claim-{per_reference_count[index]}",
                    "reference_index": index,
                    "external_id": external_id,
                    "attribution_status": status["status"],
                    "link_basis": (
                        "identifier_and_citation"
                        if has_identifier and has_citation
                        else "identifier"
                        if has_identifier
                        else "citation"
                    ),
                    "text": segment,
                }
            )

    unlinked = [
        {
            "reference_index": status["index"],
            "external_id": status["external_id"],
            "attribution_status": status["status"],
        }
        for status in statuses
        if status["index"] not in references_with_claims
    ]
    return {
        "references": len(documents),
        "claims": claims,
        "claim_count": len(claims),
        "references_with_claims": len(references_with_claims),
        "references_without_claims": unlinked,
        "review_required": bool(claims),
    }


def default_support_review_path(report_path: Path) -> Path:
    return report_path.with_name(f"{report_path.stem}-support-review.json")


def _review_cases(report: dict[str, Any]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for case in report["cases"]:
        documents = case.get("knowledge", [])
        if not documents:
            continue
        missing_evidence = [
            document.get("external_id", document.get("id", "unknown"))
            for document in documents
            if not isinstance(document.get("content"), str)
        ]
        if missing_evidence:
            joined = ", ".join(str(value) for value in missing_evidence)
            raise SupportReviewError(
                "The source report predates exact-passage capture for: "
                f"{joined}. Run a new evaluation before creating a support review."
            )
        candidates = collect_support_candidates(case["response"], documents)
        references = {
            index: {
                "index": index,
                "id": document.get("id"),
                "external_id": document.get("external_id"),
                "title": document.get("title"),
                "url": document.get("url"),
                "source_key": document.get("source_key"),
                "source_version": document.get("source_version"),
                "content_sha256": document.get("content_sha256")
                or _text_sha256(document["content"]),
                "retrieved_content": document["content"],
            }
            for index, document in enumerate(documents, start=1)
        }
        cases.append(
            {
                "id": case["id"],
                "prompt": case["prompt"],
                "response": case["response"],
                "claims": [
                    {
                        **claim,
                        "reference": references[claim["reference_index"]],
                        "verdict": None,
                        "notes": "",
                    }
                    for claim in candidates["claims"]
                ],
                "references_without_claims": candidates["references_without_claims"],
            }
        )
    return cases


def build_support_review_template(report_path: Path) -> dict[str, Any]:
    report = load_report(report_path)
    cases = _review_cases(report)
    if not cases:
        raise SupportReviewError("The report contains no retrieved references to review")
    if not any(case["claims"] for case in cases):
        raise SupportReviewError("The report contains no source-linked claims to review")
    return {
        "schema_version": SUPPORT_REVIEW_SCHEMA_VERSION,
        "source_report": {
            "path": str(report_path.resolve()),
            "sha256": _file_sha256(report_path),
            "run_id": report["run_id"],
        },
        "reviewer": "",
        "reviewed_at": None,
        "instructions": {
            "verdicts": {
                "supported": "The retrieved passage supports the complete factual claim.",
                "partially_supported": "The passage supports only part of the factual claim.",
                "unsupported": "The passage does not support the factual claim.",
                "not_a_factual_claim": "The extracted span makes no reviewable factual claim.",
                "unable_to_assess": "The passage is insufficient to decide support.",
            },
            "note_rule": "Explain every verdict except supported.",
            "scope": (
                "Judge only whether the exact retrieved passage supports the extracted claim. "
                "Do not infer support from the framework ID or URL alone."
            ),
        },
        "cases": cases,
    }


def write_support_review_template(
    report_path: Path,
    output_path: Path | None = None,
    *,
    force: bool = False,
) -> Path:
    destination = output_path or default_support_review_path(report_path)
    if destination.exists() and not force:
        raise SupportReviewError(
            f"Support-review worksheet already exists: {destination}; use --force to replace"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(build_support_review_template(report_path), indent=2) + "\n",
        encoding="utf-8",
    )
    return destination


def _load_source_report(review: dict[str, Any], review_path: Path) -> tuple[Path, dict[str, Any]]:
    source = review.get("source_report")
    if not isinstance(source, dict):
        raise SupportReviewError("source_report must be an object")
    raw_path = source.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        raise SupportReviewError("source_report.path must be a non-empty string")
    report_path = Path(raw_path)
    if not report_path.is_absolute():
        project_relative = Path.cwd() / report_path
        review_relative = review_path.parent / report_path
        report_path = project_relative if project_relative.is_file() else review_relative
    if not report_path.is_file():
        raise SupportReviewError(f"Source report not found: {raw_path}")
    if source.get("sha256") != _file_sha256(report_path):
        raise SupportReviewError("Source report SHA-256 mismatch")
    report = load_report(report_path)
    if source.get("run_id") != report.get("run_id"):
        raise SupportReviewError("Source report run_id does not match the worksheet")
    return report_path, report


def _validate_review_time(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SupportReviewError("reviewed_at must be filled in before summarizing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SupportReviewError("reviewed_at must be a valid ISO-8601 timestamp") from exc
    if parsed.utcoffset() is None:
        raise SupportReviewError("reviewed_at must include a timezone")
    return value.strip()


def summarize_support_review(review_path: Path) -> dict[str, Any]:
    try:
        review = json.loads(review_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SupportReviewError(f"Unable to read support review {review_path}: {exc}") from exc
    if (
        not isinstance(review, dict)
        or review.get("schema_version") != SUPPORT_REVIEW_SCHEMA_VERSION
    ):
        raise SupportReviewError(
            f"Support review schema_version must be {SUPPORT_REVIEW_SCHEMA_VERSION}"
        )
    reviewer = review.get("reviewer")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise SupportReviewError("reviewer must be filled in before summarizing")
    reviewed_at = _validate_review_time(review.get("reviewed_at"))
    report_path, report = _load_source_report(review, review_path)
    expected_cases = build_support_review_template(report_path)["cases"]
    actual_cases = review.get("cases")
    if not isinstance(actual_cases, list) or len(actual_cases) != len(expected_cases):
        raise SupportReviewError("Support-review cases do not match the source report")

    verdict_counts = {verdict: 0 for verdict in sorted(SUPPORT_VERDICTS)}
    claim_results: list[dict[str, Any]] = []
    for actual_case, expected_case in zip(actual_cases, expected_cases, strict=True):
        if not isinstance(actual_case, dict):
            raise SupportReviewError("Every support-review case must be an object")
        immutable_case = {key: actual_case.get(key) for key in ("id", "prompt", "response")}
        if immutable_case != {key: expected_case[key] for key in immutable_case}:
            raise SupportReviewError("Support-review case content differs from the source report")
        if actual_case.get("references_without_claims") != expected_case[
            "references_without_claims"
        ]:
            raise SupportReviewError("Unlinked-reference data differs from the source report")
        actual_claims = actual_case.get("claims")
        expected_claims = expected_case["claims"]
        if not isinstance(actual_claims, list) or len(actual_claims) != len(expected_claims):
            raise SupportReviewError(f"Claim count differs for case {expected_case['id']!r}")
        for actual_claim, expected_claim in zip(actual_claims, expected_claims, strict=True):
            if not isinstance(actual_claim, dict):
                raise SupportReviewError(
                    f"Every claim in case {expected_case['id']!r} must be an object"
                )
            immutable_keys = (
                "id",
                "reference_index",
                "external_id",
                "attribution_status",
                "link_basis",
                "text",
                "reference",
            )
            if {key: actual_claim.get(key) for key in immutable_keys} != {
                key: expected_claim[key] for key in immutable_keys
            }:
                raise SupportReviewError(
                    f"Claim {expected_claim['id']!r} differs from the source report"
                )
            verdict = actual_claim.get("verdict")
            if verdict not in SUPPORT_VERDICTS:
                raise SupportReviewError(
                    f"Claim {expected_claim['id']!r} needs a valid support verdict"
                )
            notes = actual_claim.get("notes")
            if verdict in NOTE_REQUIRED_VERDICTS and (
                not isinstance(notes, str) or not notes.strip()
            ):
                raise SupportReviewError(
                    f"Claim {expected_claim['id']!r} needs notes for verdict {verdict!r}"
                )
            verdict_counts[verdict] += 1
            claim_results.append(
                {
                    "case_id": expected_case["id"],
                    "claim_id": expected_claim["id"],
                    "external_id": expected_claim["external_id"],
                    "verdict": verdict,
                }
            )

    assessable = sum(
        verdict_counts[verdict]
        for verdict in ("supported", "partially_supported", "unsupported")
    )
    references_without_claims = sum(
        len(case["references_without_claims"]) for case in expected_cases
    )
    return {
        "schema_version": SUPPORT_REVIEW_SCHEMA_VERSION,
        "reviewer": reviewer.strip(),
        "reviewed_at": reviewed_at,
        "source_report": review["source_report"],
        "cases": len(expected_cases),
        "claims": len(claim_results),
        "assessable_claims": assessable,
        "verdicts": verdict_counts,
        "fully_supported_rate": (
            round(verdict_counts["supported"] / assessable, 4) if assessable else None
        ),
        "references_without_claims": references_without_claims,
        "claim_results": claim_results,
        "source_run_id": report["run_id"],
    }
