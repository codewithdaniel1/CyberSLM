from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from cyberslm.config import settings
from cyberslm.model import GenerationRequest, TransformersGemmaBackend
from cyberslm.modes import MODES

TINY_MODEL_ID = "tiny-random/gemma-3"
TINY_MODEL_REVISION = "69a78d1ad0ad66620c43579acd1327553713e22a"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a real portable Gemma generation smoke test without the 4B weights"
    )
    parser.add_argument("--model", default=TINY_MODEL_ID)
    parser.add_argument("--revision", default=TINY_MODEL_REVISION)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda", "mps"), default="cpu")
    parser.add_argument("--quantization", choices=("none", "8bit", "4bit"), default="none")
    parser.add_argument("--max-tokens", type=int, default=2)
    parser.add_argument("--text-only", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    smoke_settings = replace(
        settings,
        model_backend="transformers",
        model_id=args.model,
        transformers_device=args.device,
        transformers_revision=args.revision,
        transformers_quantization=args.quantization,
        adapter_path=None,
        max_tokens=args.max_tokens,
        temperature=0,
    )
    backend = TransformersGemmaBackend(smoke_settings)

    with TemporaryDirectory(prefix="cyberslm-transformers-smoke-") as directory:
        image_paths: list[Path] = []
        if not args.text_only:
            image_path = Path(directory) / "smoke.png"
            Image.new("RGB", (32, 32), color=(24, 70, 120)).save(image_path)
            image_paths.append(image_path)
        output = backend.generate_with_metadata(
            GenerationRequest(
                mode=MODES["general"],
                messages=[{"role": "user", "content": "Reply briefly."}],
                image_paths=image_paths,
            )
        )

    if output.generated_tokens is None or output.generated_tokens < 1:
        raise RuntimeError("Portable backend did not generate a token")
    print(
        json.dumps(
            {
                "status": "ok",
                "model": backend.status,
                "generation": output.metadata(),
                "multimodal": not args.text_only,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
