from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class EvaluationSource:
    key: str
    name: str
    version: str
    url: str
    sha256: str
    record_count: int
    output: Path
    license_name: str
    license_url: str


PURPLELLAMA_COMMIT = "4be64c3a24442b51c76175e6ec67722cc3f5fe38"

SOURCES = {
    "purplellama-mitre-frr": EvaluationSource(
        key="purplellama-mitre-frr",
        name="Meta PurpleLlama CyberSecEval MITRE False Refusal Rate",
        version=PURPLELLAMA_COMMIT,
        url=(
            "https://raw.githubusercontent.com/meta-llama/PurpleLlama/"
            f"{PURPLELLAMA_COMMIT}/CybersecurityBenchmarks/datasets/"
            "mitre_frr/mitre_frr.json"
        ),
        sha256="7a9b400bdf5ddbb36d5e7c3e8f6b5adb5d13125b8d03be66fd252a0f20b79d15",
        record_count=750,
        output=Path("evals/datasets/cyberseceval-mitre-frr.jsonl"),
        license_name="MIT",
        license_url=(
            "https://github.com/meta-llama/PurpleLlama/blob/"
            f"{PURPLELLAMA_COMMIT}/CybersecurityBenchmarks/LICENSE"
        ),
    )
}
