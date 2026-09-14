from __future__ import annotations

import argparse
import subprocess
from collections.abc import Sequence
from pathlib import Path

from cyberslm.config import settings

DEFAULT_MODEL_NAME = "gemma3-4b-cyberslm-crypto:dev"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Publish CyberSLM model definitions to local Ollama"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    publish = commands.add_parser(
        "publish-local",
        help="Create or update a local Ollama model from a tracked Modelfile",
    )
    publish.add_argument("--model", default=DEFAULT_MODEL_NAME)
    publish.add_argument(
        "--modelfile",
        type=Path,
        default=settings.project_root / "ollama" / "Modelfile.gemma3-4b",
    )
    publish.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the Ollama command without changing the local model alias",
    )
    return parser


def publish_local(model: str, modelfile: Path, *, dry_run: bool = False) -> list[str]:
    if not modelfile.is_file():
        raise ValueError(f"Modelfile not found: {modelfile}")
    command = ["ollama", "create", model, "-f", str(modelfile)]
    if not dry_run:
        try:
            subprocess.run(command, check=True)
        except FileNotFoundError as exc:
            raise RuntimeError("Ollama is not installed or is not on PATH") from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"Ollama could not publish {model}") from exc
    return command


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        command = publish_local(args.model, args.modelfile, dry_run=args.dry_run)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1
    if args.dry_run:
        print("Would run:", " ".join(command))
    else:
        print(f"Published local Ollama model: {args.model}")
    return 0
