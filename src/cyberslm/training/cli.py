from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from cyberslm.config import settings
from cyberslm.training.corpus import load_records, validate_corpus


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate and train reviewed CyberSLM adapters")
    commands = parser.add_subparsers(dest="command", required=True)

    inspect = commands.add_parser("inspect", help="Print corpus count and SHA-256 for review")
    inspect.add_argument("--dataset", type=Path, required=True)

    validate = commands.add_parser("validate", help="Validate a corpus against its manifest")
    validate.add_argument("--dataset", type=Path, required=True)
    validate.add_argument("--manifest", type=Path, required=True)

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
        else:
            run_training(args)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
