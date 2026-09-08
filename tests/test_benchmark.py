from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from cyberslm.benchmark import build_parser, default_output_path, main, run_benchmark
from cyberslm.config import settings
from cyberslm.evaluation.runner import load_dataset
from cyberslm.model import GenerationOutput, GenerationRequest, ModelBackend


class BenchmarkBackend(ModelBackend):
    def __init__(self) -> None:
        self.loaded = False

    def load(self) -> None:
        self.loaded = True

    def generate(self, request: GenerationRequest) -> str:
        return self.generate_with_metadata(request).text

    def generate_with_metadata(self, request: GenerationRequest) -> GenerationOutput:
        assert self.loaded
        del request
        time.sleep(0.001)
        return GenerationOutput(
            text="Brute force activity maps to T1110. Check for successful logins.",
            finish_reason="stop",
            prompt_tokens=20,
            generated_tokens=10,
            max_tokens=32,
        )

    @property
    def status(self) -> dict[str, Any]:
        return {
            "backend": "benchmark-test",
            "loaded": self.loaded,
            "memory_footprint_bytes": 2048,
        }


def _write_dataset(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "id": "ssh",
                "category": "soc",
                "mode": "defensive",
                "prompt": "Triage failed SSH logins",
                "expected_concepts": [["brute force"], ["T1110"], ["successful login"]],
                "minimum_score": 1.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_run_benchmark_captures_load_quality_throughput_and_memory(tmp_path: Path) -> None:
    dataset = tmp_path / "benchmark.jsonl"
    _write_dataset(dataset)
    backend = BenchmarkBackend()
    clock_values = iter((10.0, 11.25))
    memory_values = iter(
        (
            {"process_rss_bytes": 1000, "system_total_bytes": 8000},
            {"process_rss_bytes": 3000, "system_total_bytes": 8000},
            {"process_rss_bytes": 3500, "system_total_bytes": 8000},
        )
    )

    report = run_benchmark(
        backend,
        cases=load_dataset(dataset),
        dataset_path=dataset,
        configuration={"quantization": "none"},
        clock=lambda: next(clock_values),
        memory_snapshot=lambda: next(memory_values),
    )

    assert report["report_type"] == "model_benchmark"
    assert report["benchmark_schema_version"] == 1
    assert report["model"]["loaded"] is True
    assert report["summary"]["overall"]["pass_rate"] == 1
    assert report["performance"]["load_seconds"] == 1.25
    assert report["performance"]["model_memory_footprint_bytes"] == 2048
    assert report["performance"]["process_rss_load_delta_bytes"] == 2000
    assert report["performance"]["generated_tokens"] == 10
    assert report["cases"][0]["performance"]["tokens_per_second"] is not None
    assert len(report["report_sha256"]) == 64


def test_default_benchmark_output_identifies_runtime_mode() -> None:
    transformer_path = default_output_path("transformers", "4bit")
    mlx_path = default_output_path("mlx", "none")

    assert transformer_path.name.endswith("-transformers-4bit-benchmark.json")
    assert mlx_path.name.endswith("-mlx-mlx-benchmark.json")


def test_benchmark_uses_normal_chat_token_limit_by_default() -> None:
    assert build_parser().parse_args([]).max_tokens == settings.max_tokens


def test_benchmark_rejects_transformers_quantization_for_mlx() -> None:
    with pytest.raises(SystemExit, match="applies only"):
        main(["--backend", "mlx", "--quantization", "4bit"])
