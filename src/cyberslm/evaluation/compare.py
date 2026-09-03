from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_report(path: Path) -> dict[str, Any]:
    report = json.loads(path.read_text())
    if report.get("schema_version") != 1 or "summary" not in report or "cases" not in report:
        raise ValueError(f"Not a CyberSLM evaluation report: {path}")
    return report


def compare_reports(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    baseline_cases = {case["id"]: case for case in baseline["cases"]}
    candidate_cases = {case["id"]: case for case in candidate["cases"]}
    shared_ids = sorted(baseline_cases.keys() & candidate_cases.keys())
    cases = []
    for case_id in shared_ids:
        before = baseline_cases[case_id]["evaluation"]
        after = candidate_cases[case_id]["evaluation"]
        cases.append(
            {
                "id": case_id,
                "baseline_score": before["score"],
                "candidate_score": after["score"],
                "score_delta": round(after["score"] - before["score"], 4),
                "baseline_passed": before["passed"],
                "candidate_passed": after["passed"],
            }
        )

    baseline_summary = baseline["summary"]["overall"]
    candidate_summary = candidate["summary"]["overall"]
    return {
        "baseline_run_id": baseline["run_id"],
        "candidate_run_id": candidate["run_id"],
        "shared_cases": len(shared_ids),
        "missing_from_candidate": sorted(baseline_cases.keys() - candidate_cases.keys()),
        "new_in_candidate": sorted(candidate_cases.keys() - baseline_cases.keys()),
        "score_delta": round(candidate_summary["mean_score"] - baseline_summary["mean_score"], 4),
        "pass_rate_delta": round(candidate_summary["pass_rate"] - baseline_summary["pass_rate"], 4),
        "cases": cases,
    }


def comparison_markdown(comparison: dict[str, Any]) -> str:
    lines = [
        "# CyberSLM evaluation comparison",
        "",
        f"Shared cases: {comparison['shared_cases']}",
        f"Mean score change: {comparison['score_delta']:+.4f}",
        f"Pass-rate change: {comparison['pass_rate_delta']:+.4f}",
        "",
        "| Case | Baseline | Candidate | Delta | Pass change |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for case in comparison["cases"]:
        pass_change = f"{case['baseline_passed']} → {case['candidate_passed']}"
        lines.append(
            f"| {case['id']} | {case['baseline_score']:.4f} | "
            f"{case['candidate_score']:.4f} | {case['score_delta']:+.4f} | {pass_change} |"
        )
    return "\n".join(lines)
