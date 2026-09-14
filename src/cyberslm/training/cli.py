from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from cyberslm.config import settings
from cyberslm.knowledge import KnowledgeStore
from cyberslm.training.corpus import export_huggingface_splits, load_records, validate_corpus
from cyberslm.training.crypto_ctf import generate_crypto_ctf_drafts, promote_crypto_ctf_drafts
from cyberslm.training.pretraining import APPSEC_PRETRAINING_SOURCES, export_pretraining_corpus


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate and train reviewed CyberSLM adapters")
    commands = parser.add_subparsers(dest="command", required=True)

    inspect = commands.add_parser("inspect", help="Print corpus count and SHA-256 for review")
    inspect.add_argument("--dataset", type=Path, required=True)

    validate = commands.add_parser("validate", help="Validate a corpus against its manifest")
    validate.add_argument("--dataset", type=Path, required=True)
    validate.add_argument("--manifest", type=Path, required=True)

    export = commands.add_parser(
        "export",
        help="Export a reviewed corpus for Hugging Face datasets and manual Unsloth training",
    )
    export.add_argument("--dataset", type=Path, required=True)
    export.add_argument("--manifest", type=Path, required=True)
    export.add_argument("--output", type=Path, required=True)

    pretraining = commands.add_parser(
        "export-pretraining",
        help="Export verified local CWE/CAPEC documents for continued pretraining",
    )
    pretraining.add_argument(
        "--knowledge-db", type=Path, default=settings.knowledge_database_path
    )

    crypto_ctf_drafts = commands.add_parser(
        "generate-crypto-ctf-drafts",
        help="Generate original, unapproved crypto-CTF training drafts for human review",
    )
    crypto_ctf_drafts.add_argument(
        "--output",
        type=Path,
        default=Path("data/training/drafts/crypto-ctf-curriculum-v1.jsonl"),
    )
    crypto_ctf_drafts.add_argument("--count", type=int, default=60)
    crypto_ctf_drafts.add_argument("--seed", type=int, default=3407)
    promote_crypto_ctf = commands.add_parser(
        "promote-crypto-ctf-drafts",
        help="Promote local synthetic drafts for an explicitly experimental Unsloth run",
    )
    promote_crypto_ctf.add_argument(
        "--drafts", type=Path, default=Path("data/training/drafts/crypto-ctf-curriculum-v1.jsonl")
    )
    promote_crypto_ctf.add_argument(
        "--output", type=Path, default=Path("data/training/crypto-ctf-sft-v0-experimental")
    )
    promote_crypto_ctf.add_argument("--reviewer", required=True)
    promote_crypto_ctf.add_argument("--confirm-experimental-training", action="store_true")
    pretraining.add_argument("--output", type=Path, required=True)
    pretraining.add_argument(
        "--source",
        action="append",
        choices=APPSEC_PRETRAINING_SOURCES,
        dest="sources",
        help="Source to export (repeatable; defaults to cwe and capec)",
    )
    pretraining.add_argument("--validation-percent", type=int, default=5)
    pretraining.add_argument(
        "--confirm-training-use",
        action="store_true",
        help="Confirm that source terms/notices were reviewed for this training use",
    )

    train = commands.add_parser("run", help="Train a local LoRA adapter after validation")
    train.add_argument("--dataset", type=Path, required=True)
    train.add_argument("--manifest", type=Path, required=True)
    train.add_argument("--output", type=Path, required=True)
    train.add_argument("--iters", type=int, default=200)
    train.add_argument("--batch-size", type=int, default=1)
    train.add_argument("--learning-rate", type=float, default=2e-5)
    train.add_argument("--lora-rank", type=int, default=8)
    train.add_argument("--confirm-reviewed", action="store_true")
    return parser


def run_training(args: argparse.Namespace) -> None:
    if not args.confirm_reviewed:
        raise ValueError("Training requires --confirm-reviewed after human license/privacy review")
    corpus = validate_corpus(args.dataset, args.manifest)
    if corpus.manifest["base_model"] != settings.model_id:
        raise ValueError(
            "Manifest base_model does not match CYBERSLM_MODEL_ID: "
            f"{corpus.manifest['base_model']} != {settings.model_id}"
        )
    try:
        from datasets import Dataset
        from mlx_vlm import lora
    except ImportError as exc:
        raise RuntimeError(
            "Install training dependencies with `uv sync --extra mlx --extra train`"
        ) from exc

    train_records = [
        {"messages": record["messages"]}
        for record in corpus.records
        if record["split"] == "train"
    ]
    dataset = Dataset.from_list(train_records)
    lora.load_dataset = lambda *unused_args, **unused_kwargs: dataset
    args.output.mkdir(parents=True, exist_ok=True)
    training_args = argparse.Namespace(
        model_path=settings.model_id,
        full_finetune=False,
        train_vision=False,
        dataset="reviewed-local-corpus",
        split="train",
        dataset_config=None,
        image_resize_shape=None,
        custom_prompt_format=None,
        learning_rate=args.learning_rate,
        batch_size=args.batch_size,
        iters=args.iters,
        epochs=None,
        steps_per_report=10,
        steps_per_eval=200,
        steps_per_save=100,
        val_batches=0,
        max_seq_length=2048,
        grad_checkpoint=True,
        grad_clip=None,
        train_on_completions=True,
        gradient_accumulation_steps=4,
        assistant_id=77091,
        lora_alpha=16,
        lora_rank=args.lora_rank,
        lora_dropout=0.0,
        train_mode="sft",
        beta=0.1,
        eps=1e-8,
        output_path=str(args.output),
        adapter_path=None,
    )
    lora.main(training_args)
    metadata = {
        "corpus_sha256": corpus.sha256,
        "dataset_version": corpus.manifest["dataset_version"],
        "base_model": settings.model_id,
        "examples": len(train_records),
        "training": {
            "iters": args.iters,
            "batch_size": args.batch_size,
            "learning_rate": args.learning_rate,
            "lora_rank": args.lora_rank,
        },
    }
    (args.output / "cyberslm-training.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n"
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "inspect":
            records, digest = load_records(args.dataset)
            print(f"Examples: {len(records)}")
            print(f"SHA-256: {digest}")
        elif args.command == "validate":
            corpus = validate_corpus(args.dataset, args.manifest)
            print(
                f"Valid reviewed corpus: {len(corpus.records)} examples, "
                f"SHA-256 {corpus.sha256}"
            )
        elif args.command == "export":
            corpus = validate_corpus(args.dataset, args.manifest)
            paths = export_huggingface_splits(corpus, args.output)
            print(f"Exported train split: {paths['train']}")
            print(f"Exported validation split: {paths['validation']}")
            print(f"Exported metadata: {paths['metadata']}")
        elif args.command == "export-pretraining":
            if not args.confirm_training_use:
                raise ValueError(
                    "Pretraining export requires --confirm-training-use after reviewing source "
                    "terms and notices"
                )
            result = export_pretraining_corpus(
                KnowledgeStore(args.knowledge_db),
                args.output,
                source_keys=tuple(args.sources or APPSEC_PRETRAINING_SOURCES),
                validation_percent=args.validation_percent,
            )
            manifest = result["manifest"]
            print(f"Exported pretraining records: {manifest['total_records']}")
            print(f"Train: {result['paths']['train']}")
            print(f"Validation: {result['paths']['validation']}")
            print(f"Manifest: {result['manifest_path']}")
        elif args.command == "generate-crypto-ctf-drafts":
            records = generate_crypto_ctf_drafts(args.output, count=args.count, seed=args.seed)
            print(f"Generated {len(records)} unapproved crypto-CTF drafts: {args.output}")
            print("Review and promote selected records before any training run.")
        elif args.command == "promote-crypto-ctf-drafts":
            if not args.confirm_experimental_training:
                raise ValueError(
                    "Promotion requires --confirm-experimental-training; "
                    "this corpus is not release-ready"
                )
            paths = promote_crypto_ctf_drafts(args.drafts, args.output, reviewer=args.reviewer)
            print(f"Experimental corpus: {paths['corpus']}")
            print(f"Experimental manifest: {paths['manifest']}")
        else:
            run_training(args)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
