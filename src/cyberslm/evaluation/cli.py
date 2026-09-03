from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from cyberslm.config import settings
from cyberslm.evaluation.compare import compare_reports, comparison_markdown, load_report
from cyberslm.evaluation.retrieval import evaluate_retrieval, finalize_report
from cyberslm.evaluation.runner import EvaluationRunner, load_dataset
from cyberslm.knowledge import KnowledgeStore
from cyberslm.knowledge.embeddings import LocalEmbedder
from cyberslm.model import create_backend

DEFAULT_DATASET = Path("evals/datasets/smoke.jsonl")
DEFAULT_RETRIEVAL_DATASET = Path("evals/datasets/retrieval.jsonl")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run reproducible CyberSLM evaluations")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate a JSONL evaluation dataset")
    validate.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)

    retrieval = subparsers.add_parser(
        "retrieve", help="Evaluate local knowledge retrieval without running the language model"
    )
    retrieval.add_argument("--dataset", type=Path, default=DEFAULT_RETRIEVAL_DATASET)
    retrieval.add_argument("--output", type=Path)
    retrieval.add_argument("--limit", type=int, default=settings.rag_results)
    retrieval.add_argument("--lexical-only", action="store_true")

    run = subparsers.add_parser("run", help="Run a model against an evaluation dataset")
    run.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    run.add_argument("--output", type=Path)
    run.add_argument("--backend", choices=("mlx", "mock"), default=settings.model_backend)
    run.add_argument("--model", default=settings.model_id)
    run.add_argument("--max-tokens", type=int, default=settings.max_tokens)
    run.add_argument("--temperature", type=float, default=0.0)
    run.add_argument("--no-rag", action="store_true", help="Evaluate without local retrieval")
    run.add_argument("--rag-results", type=int, default=settings.rag_results)

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

    cases = load_dataset(args.dataset)
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
    if not args.no_rag:
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
    ).run(
        cases,
        dataset_path=args.dataset,
        configuration={
            "backend": args.backend,
            "model_id": args.model,
            "max_tokens": args.max_tokens,
            "temperature": args.temperature,
            "rag_enabled": knowledge_store is not None,
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
