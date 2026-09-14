from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_BASE_MODEL = "unsloth/gemma-3-4b-it-unsloth-bnb-4bit"
PACKAGE_NAMES = (
    "accelerate",
    "bitsandbytes",
    "datasets",
    "peft",
    "torch",
    "transformers",
    "trl",
    "unsloth",
    "unsloth_zoo",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_pretraining_export(manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError("Pretraining manifest schema_version must be 1")
    if manifest.get("format") != "raw-text-continued-pretraining-jsonl":
        raise ValueError("Manifest is not a CyberSLM raw-text pretraining export")
    if manifest.get("content_field") != "text":
        raise ValueError("Pretraining manifest content_field must be text")
    files = manifest.get("files")
    if not isinstance(files, dict) or set(files) != {"train", "validation"}:
        raise ValueError("Pretraining manifest must describe train and validation files")
    total_records = 0
    for split in ("train", "validation"):
        metadata = files[split]
        path = manifest_path.parent / metadata["path"]
        if not path.is_file():
            raise ValueError(f"Missing {split} corpus file: {path}")
        if path.stat().st_size != metadata["bytes"]:
            raise ValueError(f"{split} corpus byte count does not match manifest")
        if sha256_file(path) != metadata["sha256"]:
            raise ValueError(f"{split} corpus SHA-256 does not match manifest")
        with path.open(encoding="utf-8") as stream:
            records = [json.loads(line) for line in stream if line.strip()]
        if len(records) != metadata["records"]:
            raise ValueError(f"{split} corpus record count does not match manifest")
        invalid_text = any(
            not isinstance(record.get("text"), str) or not record["text"].strip()
            for record in records
        )
        if invalid_text:
            raise ValueError(f"{split} corpus contains an empty or invalid text record")
        total_records += len(records)
    if total_records != manifest.get("total_records"):
        raise ValueError("Total corpus record count does not match manifest")
    return manifest


def package_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in PACKAGE_NAMES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run CyberSLM-Crypto continued pretraining with Unsloth"
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/training/crypto-pretraining-v1/pretraining-manifest.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/adapters/gemma3-4b-cyberslm-crypto-cpt-v1"),
    )
    parser.add_argument("--base-model", default=DEFAULT_BASE_MODEL)
    parser.add_argument(
        "--base-revision",
        required=True,
        help="Exact immutable Hugging Face commit used for the training base",
    )
    parser.add_argument("--max-seq-length", type=int, default=2048)
    parser.add_argument("--epochs", type=float, default=1.0)
    parser.add_argument(
        "--max-steps",
        type=int,
        help="Stop after this many optimizer steps (use a small value for a smoke run)",
    )
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=5e-5)
    parser.add_argument("--lora-rank", type=int, default=16)
    parser.add_argument("--seed", type=int, default=3407)
    parser.add_argument("--confirm-reviewed", action="store_true")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Verify corpus and arguments without importing Unsloth or loading a model",
    )
    parser.add_argument(
        "--skip-merge",
        action="store_true",
        help="Save only the PEFT adapter when storage is insufficient for merged weights",
    )
    return parser


def _positive(value: int | float, name: str) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be positive")


def run(args: argparse.Namespace) -> dict[str, Any]:
    if not args.confirm_reviewed:
        raise ValueError(
            "Training requires --confirm-reviewed after corpus, license, and evaluation review"
        )
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
    manifest = validate_pretraining_export(args.manifest)
    preflight = {
        "base_model": args.base_model,
        "base_revision": args.base_revision,
        "corpus_manifest": str(args.manifest),
        "corpus_manifest_sha256": sha256_file(args.manifest),
        "records": manifest["total_records"],
    }
    if args.validate_only:
        return {"status": "validated", **preflight}

    output_root = args.output.resolve()
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError(
            f"Output directory is not empty: {output_root}; choose a new output path"
        )

    try:
        import torch
        from datasets import load_dataset
        from trl import SFTConfig, SFTTrainer
        from unsloth import FastModel, is_bfloat16_supported
    except ImportError as exc:
        raise RuntimeError(
            "Install Unsloth in its supported NVIDIA environment before training"
        ) from exc
    if not torch.cuda.is_available():
        raise RuntimeError("CyberSLM Unsloth training requires an available CUDA GPU")

    train_path = args.manifest.parent / manifest["files"]["train"]["path"]
    validation_path = args.manifest.parent / manifest["files"]["validation"]["path"]
    dataset = load_dataset(
        "json",
        data_files={"train": str(train_path), "validation": str(validation_path)},
    )
    model, tokenizer = FastModel.from_pretrained(
        model_name=args.base_model,
        revision=args.base_revision,
        max_seq_length=args.max_seq_length,
        load_in_4bit=True,
        load_in_8bit=False,
        full_finetuning=False,
    )
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

    adapter_dir = output_root / "adapter"
    merged_dir = output_root / "merged"
    checkpoints_dir = output_root / "checkpoints"
    output_root.mkdir(parents=True, exist_ok=True)
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset["train"],
        eval_dataset=dataset["validation"],
        args=SFTConfig(
            output_dir=str(checkpoints_dir),
            dataset_text_field="text",
            max_seq_length=args.max_seq_length,
            packing=True,
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
            logging_steps=5,
            eval_strategy="epoch",
            save_strategy="epoch",
            save_total_limit=2,
            seed=args.seed,
            fp16=not is_bfloat16_supported(),
            bf16=is_bfloat16_supported(),
            report_to="none",
        ),
    )
    train_result = trainer.train()
    evaluation = trainer.evaluate()
    model.save_pretrained(adapter_dir)
    tokenizer.save_pretrained(adapter_dir)
    if not args.skip_merge:
        model.save_pretrained_merged(
            merged_dir,
            tokenizer,
            save_method="merged_16bit",
        )

    metadata = {
        "schema_version": 1,
        "model_name": "CyberSLM-Crypto",
        "stage": "continued-pretraining",
        "created_at": datetime.now(UTC).isoformat(),
        **preflight,
        "corpus_files": manifest["files"],
        "sources": manifest["sources"],
        "training": {
            "max_seq_length": args.max_seq_length,
            "epochs": args.epochs,
            "max_steps": args.max_steps,
            "batch_size": args.batch_size,
            "gradient_accumulation_steps": args.gradient_accumulation_steps,
            "learning_rate": args.learning_rate,
            "lora_rank": args.lora_rank,
            "seed": args.seed,
            "load_in_4bit": True,
            "train_vision": False,
        },
        "metrics": {
            "train": train_result.metrics,
            "validation": evaluation,
        },
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
        json.dumps(metadata, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
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
