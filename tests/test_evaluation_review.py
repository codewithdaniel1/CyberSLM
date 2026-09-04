from __future__ import annotations

import json
from pathlib import Path

import pytest

from cyberslm.evaluation.review import ReviewError, summarize_review, write_review_template


def write_report(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": "review-run",
                "dataset": {"path": "cases.jsonl", "sha256": "dataset", "cases": 2},
                "model": {"backend": "scripted"},
                "configuration": {"temperature": 0},
                "summary": {"overall": {"cases": 2}},
                "cases": [
                    {"id": "one", "prompt": "Prompt one", "response": "Response one"},
                    {"id": "two", "prompt": "Prompt two", "response": "Response two"},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def complete_review(path: Path) -> None:
    review = json.loads(path.read_text(encoding="utf-8"))
    review["reviewer"] = "Human reviewer"
    review["reviewed_at"] = "2026-09-04T00:00:00Z"
    review["cases"][0]["scores"] = {
        "correctness": 4,
        "task_completion": 3,
        "operational_safety": 4,
    }
    review["cases"][0]["label_quality"] = "valid"
    review["cases"][1]["scores"] = {
        "correctness": 2,
        "task_completion": 1,
        "operational_safety": 3,
    }
    review["cases"][1]["label_quality"] = "questionable"
    review["cases"][1]["label_notes"] = "The expected behavior conflicts with the prompt."
    review["cases"][1]["notes"] = "The response does not complete the task."
    path.write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")


def test_create_and_summarize_review(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    review_path = tmp_path / "review.json"
    write_report(report_path)

    assert write_review_template(report_path, review_path) == review_path
    template = json.loads(review_path.read_text(encoding="utf-8"))
    assert template["cases"][0]["response"] == "Response one"
    assert template["cases"][0]["scores"]["correctness"] is None
    complete_review(review_path)

    summary = summarize_review(review_path)
    assert summary["cases"] == 2
    assert summary["eligible_cases"] == 1
    assert summary["questionable_cases"] == ["two"]
    assert summary["passing_cases"] == 1
    assert summary["failing_cases"] == []
    assert summary["pass_rate"] == 1
    assert summary["dimension_means"]["task_completion"] == 3
    assert summary["case_results"][1]["passed"] is False


def test_review_rejects_incomplete_scores(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    review_path = tmp_path / "review.json"
    write_report(report_path)
    write_review_template(report_path, review_path)

    with pytest.raises(ReviewError, match="reviewer must be filled"):
        summarize_review(review_path)


def test_review_requires_timezone_in_reviewed_at(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    review_path = tmp_path / "review.json"
    write_report(report_path)
    write_review_template(report_path, review_path)
    complete_review(review_path)
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["reviewed_at"] = "2026-09-04T12:00:00"
    review_path.write_text(json.dumps(review), encoding="utf-8")

    with pytest.raises(ReviewError, match="include a timezone"):
        summarize_review(review_path)


def test_review_rejects_changed_source_report(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    review_path = tmp_path / "review.json"
    write_report(report_path)
    write_review_template(report_path, review_path)
    complete_review(review_path)
    report_path.write_text(report_path.read_text() + " ", encoding="utf-8")

    with pytest.raises(ReviewError, match="SHA-256 mismatch"):
        summarize_review(review_path)


def test_review_does_not_overwrite_without_force(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    review_path = tmp_path / "review.json"
    write_report(report_path)
    write_review_template(report_path, review_path)

    with pytest.raises(ReviewError, match="already exists"):
        write_review_template(report_path, review_path)

    assert write_review_template(report_path, review_path, force=True) == review_path
