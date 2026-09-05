from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from cyberslm.config import settings
from cyberslm.evaluation.compare import compare_reports, comparison_markdown, load_report
from cyberslm.evaluation.importer import sync_source as sync_evaluation_source
from cyberslm.evaluation.retrieval import evaluate_retrieval, finalize_report
from cyberslm.evaluation.review import ReviewError, summarize_review, write_review_template
from cyberslm.evaluation.routing import evaluate_rag_gate
from cyberslm.evaluation.runner import EvaluationRunner, load_dataset
from cyberslm.evaluation.sources import SOURCES
from cyberslm.evaluation.support import (
    SupportReviewError,
    summarize_support_review,
    write_support_review_template,
)
from cyberslm.knowledge import KnowledgeStore
from cyberslm.knowledge.embeddings import LocalEmbedder
from cyberslm.model import create_backend

DEFAULT_DATASET = Path("evals/datasets/smoke.jsonl")
DEFAULT_RETRIEVAL_DATASET = Path("evals/datasets/retrieval.jsonl")
DEFAULT_RAG_GATE_DATASET = Path("evals/datasets/selective-rag.jsonl")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run reproducible CyberSLM evaluations")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate a JSONL evaluation dataset")
    validate.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)

    sync = subparsers.add_parser(
        "sync", help="Download, verify, and transform a pinned external evaluation source"
    )
    sync.add_argument("--source", choices=tuple(SOURCES), default="purplellama-mitre-frr")
    sync.add_argument("--output", type=Path)

    retrieval = subparsers.add_parser(
        "retrieve", help="Evaluate local knowledge retrieval without running the language model"
    )
    retrieval.add_argument("--dataset", type=Path, default=DEFAULT_RETRIEVAL_DATASET)
    retrieval.add_argument("--output", type=Path)
    retrieval.add_argument("--limit", type=int, default=settings.rag_results)
    retrieval.add_argument("--lexical-only", action="store_true")

    gate = subparsers.add_parser(
        "gate", help="Evaluate Auto RAG routing without a model or knowledge index"
    )
    gate.add_argument("--dataset", type=Path, default=DEFAULT_RAG_GATE_DATASET)
    gate.add_argument("--output", type=Path)

    run = subparsers.add_parser("run", help="Run a model against an evaluation dataset")
    run.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    run.add_argument("--output", type=Path)
    run.add_argument("--backend", choices=("mlx", "mock"), default=settings.model_backend)
    run.add_argument("--model", default=settings.model_id)
    run.add_argument("--max-tokens", type=int, default=settings.max_tokens)
    run.add_argument("--temperature", type=float, default=0.0)
    rag_policy = run.add_mutually_exclusive_group()
    rag_policy.add_argument(
        "--rag-policy",
        choices=("auto", "on", "off"),
        default="auto",
        help="Per-case local knowledge policy (default: auto, matching chat)",
    )
    rag_policy.add_argument(
        "--no-rag",
        action="store_const",
        const="off",
        dest="rag_policy",
        help="Deprecated alias for --rag-policy off",
    )
    run.add_argument("--rag-results", type=int, default=settings.rag_results)
    run.add_argument("--limit", type=int, default=0, help="Run only the first N cases")

    review = subparsers.add_parser("review", help="Create or summarize a human-review worksheet")
    review_subparsers = review.add_subparsers(dest="review_command", required=True)
    review_init = review_subparsers.add_parser("init", help="Create a worksheet from a report")
    review_init.add_argument("report", type=Path)
    review_init.add_argument("--output", type=Path)
    review_init.add_argument("--force", action="store_true")
    review_summary = review_subparsers.add_parser(
        "summarize", help="Validate and summarize a completed worksheet"
    )
    review_summary.add_argument("worksheet", type=Path)
    review_summary.add_argument("--output", type=Path)

    support_review = subparsers.add_parser(
        "support-review",
        help="Create or summarize a human review of source-linked claims",
    )
    support_subparsers = support_review.add_subparsers(
        dest="support_review_command", required=True
    )
    support_init = support_subparsers.add_parser(
        "init", help="Create a claim-support worksheet from a report"
    )
    support_init.add_argument("report", type=Path)
    support_init.add_argument("--output", type=Path)
    support_init.add_argument("--force", action="store_true")
    support_summary = support_subparsers.add_parser(
        "summarize", help="Validate and summarize a completed claim-support worksheet"
    )
    support_summary.add_argument("worksheet", type=Path)
    support_summary.add_argument("--output", type=Path)

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

    if args.command == "sync":
        source = SOURCES[args.source]
        output = args.output or source.output
        count = sync_evaluation_source(source, output)
        cases = load_dataset(output)
        if len(cases) != count:
            raise SystemExit("Transformed evaluation dataset failed validation")
        print(f"Synced {count} cases from {source.name} at {source.version} to {output}")
        return 0

    if args.command == "review":
        try:
            if args.review_command == "init":
                output = write_review_template(args.report, args.output, force=args.force)
                print(f"Created human-review worksheet: {output}")
                return 0
            summary = summarize_review(args.worksheet)
        except ReviewError as exc:
            raise SystemExit(f"Human review error: {exc}") from exc
        rendered = json.dumps(summary, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
            print(f"Saved human-review summary: {args.output}")
        else:
            print(rendered, end="")
        return 0

    if args.command == "support-review":
        try:
            if args.support_review_command == "init":
                output = write_support_review_template(
                    args.report, args.output, force=args.force
                )
                print(f"Created claim-support worksheet: {output}")
                return 0
            summary = summarize_support_review(args.worksheet)
        except SupportReviewError as exc:
            raise SystemExit(f"Claim-support review error: {exc}") from exc
        rendered = json.dumps(summary, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
            print(f"Saved claim-support summary: {args.output}")
        else:
            print(rendered, end="")
        return 0

    if args.command == "compare":
        comparison = compare_reports(load_report(args.baseline), load_report(args.candidate))
        print(json.dumps(comparison, indent=2) if args.json else comparison_markdown(comparison))
        return 0

    if args.command == "retrieve":
        cases = load_dataset(args.dataset)
        store = KnowledgeStore(settings.knowledge_database_path)
        if not store.status()["ready"]:
            raise SystemExit("Knowledge index is empty; run `cyberslm-knowledge sync` first")
        retrieval_embedder = None
        if settings.rag_semantic_enabled and not args.lexical_only:
            retrieval_embedder = LocalEmbedder(
                settings.rag_embedding_model, settings.embedding_cache_dir
            )
        report = finalize_report(
            evaluate_retrieval(
                cases,
                dataset_path=args.dataset,
                store=store,
                embedder=retrieval_embedder,
                limit=max(1, args.limit),
                max_chars=settings.rag_max_chars,
                progress=lambda index, total, case: print(
                    f"[{index}/{total}] {case.id} ({case.mode})", flush=True
                ),
            )
        )
        output = args.output or default_output_path("retrieval")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n")
        summary = report["summary"]
        print(f"Saved: {output}")
        print(
            f"Cases: {summary['cases']} | Pass rate: {summary['pass_rate']:.1%} | "
            f"Recall: {summary['mean_recall']:.1%} | "
            f"Precision: {summary['mean_precision']:.1%} | "
            f"Latency: {summary['mean_latency_seconds']:.3f}s"
        )
        return 0

    if args.command == "gate":
        cases = load_dataset(args.dataset)
        report = finalize_report(
            evaluate_rag_gate(
                cases,
                dataset_path=args.dataset,
                progress=lambda index, total, case: print(
                    f"[{index}/{total}] {case.id} ({case.mode})", flush=True
                ),
            )
        )
        output = args.output or default_output_path("rag-gate")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n")
        summary = report["summary"]
        print(f"Saved: {output}")
        print(
            f"Cases: {summary['cases']} | Accuracy: {summary['accuracy']:.1%} | "
            f"Precision: {summary['precision']:.1%} | Recall: {summary['recall']:.1%} | "
            f"False positive: {summary['false_positive_rate']:.1%} | "
            f"False negative: {summary['false_negative_rate']:.1%}"
        )
        return 0

    cases = load_dataset(args.dataset)
    if args.limit > 0:
        cases = cases[: args.limit]
    run_settings = replace(
        settings,
        model_backend=args.backend,
        model_id=args.model,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
    )
    backend = create_backend(run_settings)
    knowledge_store = None
    embedder = None
    if args.rag_policy != "off":
        candidate_store = KnowledgeStore(settings.knowledge_database_path)
        if candidate_store.status()["ready"]:
            knowledge_store = candidate_store
            if settings.rag_semantic_enabled:
                embedder = LocalEmbedder(
                    settings.rag_embedding_model, settings.embedding_cache_dir
                )
        else:
            print("Knowledge index is empty; continuing without RAG.")
    report = EvaluationRunner(
        backend,
        knowledge_store=knowledge_store,
        rag_results=args.rag_results,
        rag_max_chars=settings.rag_max_chars,
        embedder=embedder,
        rag_policy=args.rag_policy,
    ).run(
        cases,
        dataset_path=args.dataset,
        configuration={
            "backend": args.backend,
            "model_id": args.model,
            "max_tokens": args.max_tokens,
            "temperature": args.temperature,
            "limit": args.limit or None,
            "rag_enabled": knowledge_store is not None,
            "rag_policy": args.rag_policy,
            "rag_results": args.rag_results,
            "rag_semantic_enabled": embedder is not None,
            "rag_embedding_model": embedder.model_name if embedder else None,
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
    retrieval = report["summary"]["retrieval"]
    if retrieval:
        print(
            f"Retrieval: {retrieval['pass_rate']:.1%} exact-set pass | "
            f"Recall: {retrieval['mean_recall']:.1%} | "
            f"Precision: {retrieval['mean_precision']:.1%}"
        )
    attributions = report["summary"]["attributions"]
    if attributions:
        print(
            f"Exact-ID attribution: {attributions['complete']}/{attributions['cases']} "
            f"complete | Coverage: {attributions['mean_coverage']:.1%} | "
            f"Unmapped citations: {attributions['unmapped_valid_citations']} | "
            f"Uncited ID mentions: {attributions['uncited_identifier_mentions']} | "
            f"Unmentioned refs: {attributions['unmentioned_references']}"
        )
    support_candidates = report["summary"]["support_candidates"]
    if support_candidates:
        print(
            f"Claim-support candidates: {support_candidates['claims']} | "
            f"References with claims: {support_candidates['references_with_claims']}/"
            f"{support_candidates['references']} | "
            f"Review-required cases: {support_candidates['review_required']}"
        )
    rag = report["summary"]["rag"]
    print(
        f"RAG routing: {rag['attempted']}/{rag['cases']} attempted | "
        f"{rag['used']} used | Reasons: {rag['reasons']}"
    )
    rag_routing = report["summary"]["rag_routing"]
    if rag_routing:
        print(
            f"Labeled RAG decisions: {rag_routing['passed']}/{rag_routing['cases']} "
            f"correct ({rag_routing['accuracy']:.1%})"
        )
    safety = report["summary"]["safety"]
    if safety:
        message = f"Safety behavior pass rate: {safety['pass_rate']:.1%}"
        if safety["false_refusal_rate"] is not None:
            message += f" | False-refusal rate: {safety['false_refusal_rate']:.1%}"
        print(message)
    generation = report["summary"]["generation"]
    if generation["length_limited_rate"] is None:
        print(f"Finish reasons unavailable: {generation['finish_reasons']}")
    else:
        print(
            f"Length-limited: {generation['length_limited']}/"
            f"{generation['known_finish_cases']} "
            f"({generation['length_limited_rate']:.1%}) | "
            f"Finish reasons: {generation['finish_reasons']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
