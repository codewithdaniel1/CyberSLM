from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from cyberslm.config import settings
from cyberslm.evaluation.compare import compare_reports, comparison_markdown, load_report
from cyberslm.evaluation.runner import EvaluationRunner, load_dataset
from cyberslm.model import create_backend

DEFAULT_DATASET = Path("evals/datasets/smoke.jsonl")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run reproducible CyberSLM evaluations")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate a JSONL evaluation dataset")
    validate.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)

    run = subparsers.add_parser("run", help="Run a model against an evaluation dataset")
    run.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    run.add_argument("--output", type=Path)
    run.add_argument("--backend", choices=("mlx", "mock"), default=settings.model_backend)
    run.add_argument("--model", default=settings.model_id)
    run.add_argument("--max-tokens", type=int, default=settings.max_tokens)
    run.add_argument("--temperature", type=float, default=0.0)

    compare = subparsers.add_parser("compare", help="Compare two saved evaluation reports")
    compare.add_argument("baseline", type=Path)
    compare.add_argument("candidate", type=Path)
    compare.add_argument("--json", action="store_true", help="Print JSON instead of Markdown")
    return parser


def default_output_path(backend: str) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return Path("evals/results") / f"{timestamp}-{backend}.json"


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate":
        cases = load_dataset(args.dataset)
        print(f"Valid dataset: {args.dataset} ({len(cases)} cases)")
        return 0

    if args.command == "compare":
        comparison = compare_reports(load_report(args.baseline), load_report(args.candidate))
        print(json.dumps(comparison, indent=2) if args.json else comparison_markdown(comparison))
        return 0

    cases = load_dataset(args.dataset)
    run_settings = replace(
        settings,
        model_backend=args.backend,
        model_id=args.model,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
    )
    backend = create_backend(run_settings)
    report = EvaluationRunner(backend).run(
        cases,
        dataset_path=args.dataset,
        configuration={
            "backend": args.backend,
            "model_id": args.model,
            "max_tokens": args.max_tokens,
            "temperature": args.temperature,
        },
        progress=lambda index, total, case: print(
            f"[{index}/{total}] {case.id} ({case.mode})", flush=True
        ),
    )
    output = args.output or default_output_path(args.backend)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    overall = report["summary"]["overall"]
    print(f"Saved: {output}")
    print(
        f"Cases: {overall['cases']} | Pass rate: {overall['pass_rate']:.1%} | "
        f"Mean score: {overall['mean_score']:.4f} | "
        f"Mean latency: {overall['mean_latency_seconds']:.2f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
