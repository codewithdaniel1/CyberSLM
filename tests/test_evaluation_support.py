from __future__ import annotations

import json
from pathlib import Path

import pytest

from cyberslm.evaluation.support import (
    SupportReviewError,
    collect_support_candidates,
    summarize_support_review,
    write_support_review_template,
)
from cyberslm.model import source_footer


def document() -> dict[str, str]:
    return {
        "id": "attack:T1110",
        "external_id": "T1110",
        "title": "T1110 — Brute Force",
        "url": "https://attack.mitre.org/techniques/T1110/",
        "source_key": "attack",
        "source_version": "19.1",
        "content": "Adversaries may use brute-force techniques to gain access to accounts.",
    }


def write_report(path: Path, *, include_content: bool = True) -> None:
    knowledge = document()
    if not include_content:
        knowledge.pop("content")
    response_body = "T1110 [1] covers brute-force attempts. Check for successful logins."
    response = response_body + source_footer([document()], response_body)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": "support-run",
                "summary": {"overall": {"cases": 1}},
                "cases": [
                    {
                        "id": "ssh",
                        "prompt": "Investigate failed SSH logins",
                        "response": response,
                        "knowledge": [knowledge],
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_collect_support_candidates_ignores_footer_and_tracks_unlinked_sources() -> None:
    first = document()
    second = {
        **document(),
        "id": "attack:T1071.004",
        "external_id": "T1071.004",
        "title": "T1071.004 — DNS",
    }
    response_body = "T1110 [1] covers brute-force attempts."
    response = response_body + source_footer([first, second], response_body)

    candidates = collect_support_candidates(response, [first, second])

    assert candidates["claim_count"] == 1
    assert candidates["claims"][0]["text"] == "T1110 [1] covers brute-force attempts."
    assert candidates["claims"][0]["link_basis"] == "identifier_and_citation"
    assert candidates["references_without_claims"] == [
        {
            "reference_index": 2,
            "external_id": "T1071.004",
            "attribution_status": "not_explicitly_referenced",
        }
    ]


def test_create_and_summarize_support_review(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    review_path = tmp_path / "support-review.json"
    write_report(report_path)

    assert write_support_review_template(report_path, review_path) == review_path
    review = json.loads(review_path.read_text(encoding="utf-8"))
    claim = review["cases"][0]["claims"][0]
    assert claim["reference"]["retrieved_content"].startswith("Adversaries may use")
    assert claim["reference"]["content_sha256"]
    claim["verdict"] = "supported"
    review["reviewer"] = "Human reviewer"
    review["reviewed_at"] = "2026-09-05T06:00:00Z"
    review_path.write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")

    summary = summarize_support_review(review_path)

    assert summary["claims"] == 1
    assert summary["assessable_claims"] == 1
    assert summary["verdicts"]["supported"] == 1
    assert summary["fully_supported_rate"] == 1
    assert summary["references_without_claims"] == 0


def test_support_review_requires_notes_for_non_supported_verdict(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    review_path = tmp_path / "support-review.json"
    write_report(report_path)
    write_support_review_template(report_path, review_path)
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["reviewer"] = "Human reviewer"
    review["reviewed_at"] = "2026-09-05T06:00:00Z"
    review["cases"][0]["claims"][0]["verdict"] = "unsupported"
    review_path.write_text(json.dumps(review), encoding="utf-8")

    with pytest.raises(SupportReviewError, match="needs notes"):
        summarize_support_review(review_path)


def test_support_review_rejects_reports_without_exact_passages(tmp_path: Path) -> None:
    report_path = tmp_path / "legacy-report.json"
    write_report(report_path, include_content=False)

    with pytest.raises(SupportReviewError, match="predates exact-passage capture"):
        write_support_review_template(report_path)
