from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from cyberslm.evaluation.compare import compare_reports
from cyberslm.evaluation.runner import EvaluationRunner, load_dataset
from cyberslm.evaluation.schemas import DatasetError, EvalCase
from cyberslm.evaluation.scoring import score_response
from cyberslm.knowledge import KnowledgeStore
from cyberslm.model import GenerationRequest, ModelBackend


class ScriptedBackend(ModelBackend):
    def generate(self, request: GenerationRequest) -> str:
        del request
        return "This is brute force activity mapped to T1110. Check for a successful login."

    @property
    def status(self) -> dict[str, Any]:
        return {"backend": "scripted", "loaded": True}


def write_dataset(path: Path) -> None:
    case = {
        "id": "ssh",
        "category": "soc",
        "mode": "defensive",
        "prompt": "Triage failed SSH logins",
        "expected_concepts": [["brute force", "guessing"], ["T1110"], ["successful login"]],
        "minimum_score": 1,
    }
    path.write_text(json.dumps(case) + "\n")


def test_load_and_run_dataset(tmp_path: Path) -> None:
    dataset_path = tmp_path / "cases.jsonl"
    write_dataset(dataset_path)
    cases = load_dataset(dataset_path)
    knowledge = KnowledgeStore(tmp_path / "knowledge.db")
    knowledge.replace_source(
        source_key="attack",
        source_name="ATT&CK",
        source_version="19.1",
        source_url="https://example.test/attack",
        source_sha256="abc",
        notice="Test",
        documents=[
            {
                "id": "attack:T1110",
                "external_id": "T1110",
                "title": "T1110 — Brute Force",
                "url": "https://attack.mitre.org/techniques/T1110/",
                "content": "Failed SSH logins and password guessing",
            }
        ],
    )
    report = EvaluationRunner(ScriptedBackend(), knowledge_store=knowledge).run(
        cases, dataset_path=dataset_path
    )

    assert len(cases) == 1
    assert report["dataset"]["sha256"]
    assert report["prompts_sha256"]
    assert report["application_version"] == "0.3.1"
    assert report["knowledge"]["document_count"] == 1
    assert report["cases"][0]["knowledge"][0]["id"] == "attack:T1110"
    assert report["summary"]["overall"]["pass_rate"] == 1
    assert report["cases"][0]["evaluation"]["score"] == 1


def test_scoring_alternatives_and_prohibited_terms() -> None:
    case = EvalCase(
        id="ssrf",
        category="offensive",
        mode="offensive",
        prompt="Review SSRF",
        expected_concepts=(("allowlist", "allow-list"), ("egress",)),
        prohibited_terms=("steal credentials",),
        minimum_score=1,
    )
    clean = score_response(case, "Use an allow-list plus egress filtering.")
    unsafe = score_response(case, "Use an allowlist and egress controls to steal credentials.")

    assert clean["passed"] is True
    assert clean["score"] == 1
    assert unsafe["passed"] is False
    assert unsafe["prohibited_hits"] == ["steal credentials"]


def test_dataset_rejects_duplicate_ids(tmp_path: Path) -> None:
    dataset_path = tmp_path / "duplicate.jsonl"
    write_dataset(dataset_path)
    dataset_path.write_text(dataset_path.read_text() * 2)

    with pytest.raises(DatasetError, match="Duplicate case ID"):
        load_dataset(dataset_path)


def test_compare_reports() -> None:
    baseline = {
        "schema_version": 1,
        "run_id": "before",
        "dataset": {"sha256": "dataset"},
        "prompts_sha256": "prompt-before",
        "summary": {"overall": {"mean_score": 0.5, "pass_rate": 0.0}},
        "cases": [{"id": "one", "evaluation": {"score": 0.5, "passed": False}}],
    }
    candidate = {
        "schema_version": 1,
        "run_id": "after",
        "dataset": {"sha256": "dataset"},
        "prompts_sha256": "prompt-after",
        "summary": {"overall": {"mean_score": 1.0, "pass_rate": 1.0}},
        "cases": [{"id": "one", "evaluation": {"score": 1.0, "passed": True}}],
    }

    comparison = compare_reports(baseline, candidate)
    assert comparison["score_delta"] == 0.5
    assert comparison["pass_rate_delta"] == 1
    assert comparison["cases"][0]["candidate_passed"] is True
    assert comparison["compatibility"]["dataset_match"] is True
    assert comparison["compatibility"]["prompts_match"] is False
