from __future__ import annotations

import argparse
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

from cyberslm.config import settings

DEFAULT_MODEL_NAME = "gemma3-4b-cyberslm-crypto:dev"
DEFAULT_CANDIDATE_NAME = "gemma3-4b-cyberslm-crypto:0.1.0-rc1"


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
    import_gguf = commands.add_parser(
        "import-gguf",
        help="Create or update a local Ollama model from a verified GGUF candidate",
    )
    import_gguf.add_argument("--gguf", type=Path, required=True)
    import_gguf.add_argument("--model", default=DEFAULT_CANDIDATE_NAME)
    import_gguf.add_argument(
        "--template",
        type=Path,
        default=settings.project_root / "ollama" / "Modelfile.gemma3-4b",
        help="Tracked parameters and system-prompt template to apply to the GGUF",
    )
    import_gguf.add_argument("--dry-run", action="store_true")
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


def _gguf_modelfile(gguf: Path, template: Path) -> str:
    if not gguf.is_file() or gguf.suffix != ".gguf":
        raise ValueError(f"GGUF model file not found: {gguf}")
    if not template.is_file():
        raise ValueError(f"Modelfile template not found: {template}")
    resolved = gguf.resolve()
    if any(character.isspace() for character in str(resolved)):
        raise ValueError("GGUF path must not contain whitespace for Ollama import")
    lines = template.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.startswith("FROM "):
            lines[index] = f"FROM {resolved}"
            return "\n".join(lines) + "\n"
    raise ValueError("Modelfile template must contain a FROM line")


def import_gguf(model: str, gguf: Path, template: Path, *, dry_run: bool = False) -> list[str]:
    content = _gguf_modelfile(gguf, template)
    if dry_run:
        return ["ollama", "create", model, "-f", "<generated-modelfile>"]
    with tempfile.TemporaryDirectory(prefix="cyberslm-ollama-") as directory:
        modelfile = Path(directory) / "Modelfile"
        modelfile.write_text(content, encoding="utf-8")
        return publish_local(model, modelfile)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "publish-local":
            command = publish_local(args.model, args.modelfile, dry_run=args.dry_run)
        else:
            command = import_gguf(args.model, args.gguf, args.template, dry_run=args.dry_run)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1
    if args.dry_run:
        print("Would run:", " ".join(command))
    else:
        print(f"Published local Ollama model: {args.model}")
    return 0
