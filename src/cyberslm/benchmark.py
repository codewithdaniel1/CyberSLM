from __future__ import annotations

import argparse
import json
import os
import platform
import time
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from statistics import fmean, median
from typing import Any

from cyberslm.config import (
    TRANSFORMERS_QUANTIZATION_MODES,
    default_model_backend,
    default_model_id,
    settings,
)
from cyberslm.evaluation.retrieval import finalize_report
from cyberslm.evaluation.runner import EvaluationRunner, load_dataset
from cyberslm.model import ModelBackend, create_backend

DEFAULT_BENCHMARK_DATASET = Path("evals/datasets/smoke.jsonl")
BENCHMARK_BACKENDS = ("mlx", "transformers")


def _package_version(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def _memory_snapshot() -> dict[str, int | None]:
    try:
        import psutil

        process_rss = int(psutil.Process().memory_info().rss)
        system_total = int(psutil.virtual_memory().total)
    except (ImportError, OSError):
        process_rss = None
        system_total = None
    return {
        "process_rss_bytes": process_rss,
        "system_total_bytes": system_total,
    }


def _environment() -> dict[str, Any]:
    return {
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "packages": {
            name: _package_version(name)
            for name in ("torch", "transformers", "accelerate", "bitsandbytes", "mlx-vlm")
        },
    }


def _rate(tokens: int | None, seconds: float) -> float | None:
    if tokens is None or seconds <= 0:
        return None
    return round(tokens / seconds, 4)


def run_benchmark(
    backend: ModelBackend,
    *,
    cases: list[Any],
    dataset_path: Path,
    configuration: dict[str, Any],
    clock: Callable[[], float] = time.perf_counter,
    memory_snapshot: Callable[[], dict[str, int | None]] = _memory_snapshot,
    progress: Callable[[int, int, Any], None] | None = None,
) -> dict[str, Any]:
    before_load = memory_snapshot()
    load_started = clock()
    backend.load()
    load_seconds = clock() - load_started
    after_load = memory_snapshot()

    report = EvaluationRunner(backend, rag_policy="off").run(
        cases,
        dataset_path=dataset_path,
        configuration=configuration,
        progress=progress,
    )
    after_generation = memory_snapshot()

    rates: list[float] = []
    generated_tokens = 0
    generation_seconds = 0.0
    for case in report["cases"]:
        seconds = float(case["latency_seconds"])
        tokens = case["generation"]["generated_tokens"]
        tokens_per_second = _rate(tokens, seconds)
        case["performance"] = {"tokens_per_second": tokens_per_second}
        generation_seconds += seconds
        if tokens is not None:
            generated_tokens += int(tokens)
        if tokens_per_second is not None:
            rates.append(tokens_per_second)

    rss_before = before_load["process_rss_bytes"]
    rss_after_load = after_load["process_rss_bytes"]
    model_status = backend.status
    report.update(
        {
            "report_type": "model_benchmark",
            "benchmark_schema_version": 1,
            "environment": {**report["environment"], **_environment()},
            "performance": {
                "load_seconds": round(load_seconds, 4),
                "generation_seconds": round(generation_seconds, 4),
                "generated_tokens": generated_tokens,
                "aggregate_tokens_per_second": _rate(generated_tokens, generation_seconds),
                "mean_case_tokens_per_second": round(fmean(rates), 4) if rates else None,
                "median_case_tokens_per_second": round(median(rates), 4) if rates else None,
                "model_memory_footprint_bytes": model_status.get("memory_footprint_bytes"),
                "process_rss_before_load_bytes": rss_before,
                "process_rss_after_load_bytes": rss_after_load,
                "process_rss_load_delta_bytes": (
                    rss_after_load - rss_before
                    if rss_before is not None and rss_after_load is not None
                    else None
                ),
                "process_rss_after_generation_bytes": after_generation["process_rss_bytes"],
                "system_total_memory_bytes": after_load["system_total_bytes"],
            },
        }
    )
    return finalize_report(report)


def default_output_path(backend: str, quantization: str) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    mode = quantization if backend == "transformers" else "mlx"
    return Path("evals/results") / f"{timestamp}-{backend}-{mode}-benchmark.json"


def build_parser() -> argparse.ArgumentParser:
    backend = settings.model_backend
    if backend not in BENCHMARK_BACKENDS:
        backend = default_model_backend()
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark a full local CyberSLM model with the reproducible cyber smoke suite"
        )
    )
    parser.add_argument("--backend", choices=BENCHMARK_BACKENDS, default=backend)
    parser.add_argument("--model")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_BENCHMARK_DATASET)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--label", help="Optional machine or run label recorded in the report")
    parser.add_argument("--limit", type=int, default=0, help="Run only the first N cases")
    parser.add_argument("--max-tokens", type=int, default=settings.max_tokens)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument(
        "--device",
        choices=("auto", "cpu", "cuda", "mps"),
        default=settings.transformers_device,
    )
    parser.add_argument("--revision", default=settings.transformers_revision)
    parser.add_argument(
        "--quantization",
        choices=TRANSFORMERS_QUANTIZATION_MODES,
        default=None,
        help=(
            "Transformers weight mode (default: configured value for Transformers; none for MLX)"
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.limit < 0:
        raise SystemExit("--limit cannot be negative")
    if args.max_tokens < 1:
        raise SystemExit("--max-tokens must be at least 1")
    quantization = args.quantization or (
        settings.transformers_quantization if args.backend == "transformers" else "none"
    )
    if args.backend == "mlx" and quantization != "none":
        raise SystemExit("--quantization applies only to the transformers backend")

    model_id = args.model or (
        settings.model_id
        if args.backend == settings.model_backend
        else default_model_id(args.backend)
    )
    run_settings = replace(
        settings,
        model_backend=args.backend,
        model_id=model_id,
        transformers_device=args.device,
        transformers_revision=args.revision,
        transformers_quantization=quantization,
        adapter_path=settings.adapter_path if args.backend == "mlx" else None,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
    )
    cases = load_dataset(args.dataset)
    if args.limit:
        cases = cases[: args.limit]
    configuration = {
        "backend": args.backend,
        "model_id": model_id,
        "revision": args.revision if args.backend == "transformers" else None,
        "device": args.device if args.backend == "transformers" else "mps",
        "quantization": quantization if args.backend == "transformers" else "mlx",
        "adapter_path": (
            str(run_settings.adapter_path) if run_settings.adapter_path is not None else None
        ),
        "max_tokens": args.max_tokens,
        "temperature": args.temperature,
        "rag_policy": "off",
        "label": args.label,
        "limit": args.limit or None,
    }
    report = run_benchmark(
        create_backend(run_settings),
        cases=cases,
        dataset_path=args.dataset,
        configuration=configuration,
        progress=lambda index, total, case: print(
            f"[{index}/{total}] {case.id} ({case.mode})", flush=True
        ),
    )
    output = args.output or default_output_path(args.backend, quantization)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    quality = report["summary"]["overall"]
    performance = report["performance"]
    print(f"Saved: {output}")
    print(
        f"Quality: {quality['passed']}/{quality['cases']} passed | "
        f"Mean score: {quality['mean_score']:.4f}"
    )
    print(
        f"Load: {performance['load_seconds']:.2f}s | "
        f"Generation: {performance['generation_seconds']:.2f}s | "
        f"Throughput: {performance['aggregate_tokens_per_second'] or 0:.2f} tokens/s"
    )
    print(f"Report SHA-256: {report['report_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
