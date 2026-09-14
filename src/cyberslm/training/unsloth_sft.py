from __future__ import annotations

import argparse
import json
import platform
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cyberslm.training.corpus import ValidatedCorpus, validate_corpus
from cyberslm.training.unsloth_run import DEFAULT_BASE_MODEL, package_versions, sha256_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fine-tune CyberSLM-Crypto chat behavior with Unsloth supervised training"
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/adapters/gemma3-4b-cyberslm-crypto-ctf-sft-v0"),
    )
    parser.add_argument("--base-model", default=DEFAULT_BASE_MODEL)
    parser.add_argument("--base-revision", required=True)
    parser.add_argument("--max-seq-length", type=int, default=2048)
    parser.add_argument("--epochs", type=float, default=1.0)
    parser.add_argument("--max-steps", type=int)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--lora-rank", type=int, default=16)
    parser.add_argument("--seed", type=int, default=3407)
    parser.add_argument(
        "--confirm-experimental-training",
        action="store_true",
        help="Confirm this is an experimental synthetic-curriculum run, not a release run",
    )
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--skip-merge", action="store_true")
    return parser


def _positive(value: int | float, name: str) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be positive")


def _validate_args(args: argparse.Namespace) -> ValidatedCorpus:
    if not args.confirm_experimental_training:
        raise ValueError("Training requires --confirm-experimental-training")
    for value, name in (
        (args.max_seq_length, "max_seq_length"),
        (args.epochs, "epochs"),
        (args.batch_size, "batch_size"),
        (args.gradient_accumulation_steps, "gradient_accumulation_steps"),
        (args.learning_rate, "learning_rate"),
        (args.lora_rank, "lora_rank"),
    ):
        _positive(value, name)
    if args.max_steps is not None:
        _positive(args.max_steps, "max_steps")
    if len(args.base_revision.strip()) < 7:
        raise ValueError("base_revision must be an immutable commit identifier")
    corpus = validate_corpus(args.dataset, args.manifest)
    if corpus.manifest.get("experimental") is not True:
        raise ValueError("This runner accepts only explicitly experimental corpus manifests")
    return corpus


def _preflight(args: argparse.Namespace, corpus: ValidatedCorpus) -> dict[str, Any]:
    return {
        "base_model": args.base_model,
        "base_revision": args.base_revision,
        "corpus": str(args.dataset),
        "corpus_sha256": corpus.sha256,
        "corpus_manifest": str(args.manifest),
        "corpus_manifest_sha256": sha256_file(args.manifest),
        "records": len(corpus.records),
        "experimental": True,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    corpus = _validate_args(args)
    preflight = _preflight(args, corpus)
    if args.validate_only:
        return {"status": "validated", **preflight}

    output_root = args.output.resolve()
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError(f"Output directory is not empty: {output_root}; choose a new output path")
    try:
        import torch
        from datasets import Dataset
        from trl import SFTConfig, SFTTrainer
        from unsloth import FastModel, is_bfloat16_supported
        from unsloth.chat_templates import get_chat_template, train_on_responses_only
    except ImportError as exc:
        raise RuntimeError(
            "Install Unsloth in its supported NVIDIA environment before training"
        ) from exc
    if not torch.cuda.is_available():
        raise RuntimeError("CyberSLM Unsloth training requires an available CUDA GPU")

    model, tokenizer = FastModel.from_pretrained(
        model_name=args.base_model,
        revision=args.base_revision,
        max_seq_length=args.max_seq_length,
        load_in_4bit=True,
        load_in_8bit=False,
        full_finetuning=False,
    )
    tokenizer = get_chat_template(tokenizer, chat_template="gemma-3")
    model = FastModel.get_peft_model(
        model,
        finetune_vision_layers=False,
        finetune_language_layers=True,
        finetune_attention_modules=True,
        finetune_mlp_modules=True,
        r=args.lora_rank,
        lora_alpha=args.lora_rank,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=args.seed,
        use_rslora=False,
        loftq_config=None,
    )

    def format_examples(examples: dict[str, list[list[dict[str, str]]]]) -> dict[str, list[str]]:
        return {
            "text": [
                tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
                for messages in examples["messages"]
            ]
        }

    train_rows = [record for record in corpus.records if record["split"] == "train"]
    validation_rows = [record for record in corpus.records if record["split"] == "validation"]
    train_data = Dataset.from_list(train_rows).map(format_examples, batched=True)
    validation_data = Dataset.from_list(validation_rows).map(format_examples, batched=True)
    adapter_dir = output_root / "adapter"
    merged_dir = output_root / "merged"
    checkpoints_dir = output_root / "checkpoints"
    output_root.mkdir(parents=True, exist_ok=True)
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_data,
        eval_dataset=validation_data,
        args=SFTConfig(
            output_dir=str(checkpoints_dir),
            dataset_text_field="text",
            max_seq_length=args.max_seq_length,
            packing=False,
            num_train_epochs=args.epochs,
            max_steps=args.max_steps if args.max_steps is not None else -1,
            per_device_train_batch_size=args.batch_size,
            per_device_eval_batch_size=args.batch_size,
            gradient_accumulation_steps=args.gradient_accumulation_steps,
            learning_rate=args.learning_rate,
            warmup_ratio=0.05,
            weight_decay=0.01,
            lr_scheduler_type="cosine",
            optim="adamw_8bit",
            logging_steps=1,
            eval_strategy="epoch",
            save_strategy="epoch",
            save_total_limit=2,
            seed=args.seed,
            fp16=not is_bfloat16_supported(),
            bf16=is_bfloat16_supported(),
            report_to="none",
        ),
    )
    trainer = train_on_responses_only(
        trainer,
        instruction_part="<start_of_turn>user\n",
        response_part="<start_of_turn>model\n",
    )
    train_result = trainer.train()
    evaluation = trainer.evaluate()
    model.save_pretrained(adapter_dir)
    tokenizer.save_pretrained(adapter_dir)
    if not args.skip_merge:
        model.save_pretrained_merged(merged_dir, tokenizer, save_method="merged_16bit")

    metadata = {
        "schema_version": 1,
        "model_name": "CyberSLM-Crypto",
        "stage": "supervised-fine-tuning",
        "status": "experimental-candidate",
        "created_at": datetime.now(UTC).isoformat(),
        **preflight,
        "training": {
            "max_seq_length": args.max_seq_length,
            "epochs": args.epochs,
            "max_steps": args.max_steps,
            "batch_size": args.batch_size,
            "gradient_accumulation_steps": args.gradient_accumulation_steps,
            "learning_rate": args.learning_rate,
            "lora_rank": args.lora_rank,
            "seed": args.seed,
            "chat_template": "gemma-3",
            "response_only_loss": True,
            "load_in_4bit": True,
        },
        "metrics": {"train": train_result.metrics, "validation": evaluation},
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "cuda_device": torch.cuda.get_device_name(0),
            "packages": package_versions(),
        },
        "artifacts": {
            "adapter": str(adapter_dir),
            "merged": None if args.skip_merge else str(merged_dir),
        },
    }
    metadata_path = output_root / "cyberslm-training.json"
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"status": "trained", "metadata": str(metadata_path), **preflight}


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run(args)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
