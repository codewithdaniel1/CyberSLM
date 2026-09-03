from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cyberslm.modes import AUTHORIZATION_CONTEXTS, MODES


class DatasetError(ValueError):
    """Raised when an evaluation dataset does not match the expected schema."""


@dataclass(frozen=True, slots=True)
class EvalCase:
    id: str
    category: str
    mode: str
    prompt: str
    expected_concepts: tuple[tuple[str, ...], ...]
    expected_references: tuple[str, ...] | None = None
    prohibited_terms: tuple[str, ...] = ()
    minimum_score: float = 0.67
    image_paths: tuple[Path, ...] = ()
    authorization_context: str = "unspecified"
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any], dataset_dir: Path) -> EvalCase:
        required = ("id", "category", "mode", "prompt", "expected_concepts")
        missing = [key for key in required if key not in value]
        if missing:
            raise DatasetError(f"Missing required field(s): {', '.join(missing)}")
        for key in ("id", "category", "prompt"):
            if not isinstance(value[key], str) or not value[key].strip():
                raise DatasetError(f"{key} must be a non-empty string")
        if value["mode"] not in MODES:
            raise DatasetError(f"Unknown mode {value['mode']!r} in case {value['id']!r}")

        raw_concepts = value["expected_concepts"]
        if not isinstance(raw_concepts, list) or not raw_concepts:
            raise DatasetError(f"Case {value['id']!r} must define expected_concepts")
        concepts: list[tuple[str, ...]] = []
        for concept in raw_concepts:
            alternatives = [concept] if isinstance(concept, str) else concept
            if not isinstance(alternatives, list) or not alternatives:
                raise DatasetError(f"Invalid expected concept in case {value['id']!r}")
            if not all(isinstance(term, str) and term.strip() for term in alternatives):
                raise DatasetError("Expected concept terms must be non-empty strings")
            concepts.append(tuple(term.strip() for term in alternatives))

        minimum_score = float(value.get("minimum_score", 0.67))
        if not 0 <= minimum_score <= 1:
            raise DatasetError(f"minimum_score must be between 0 and 1 in {value['id']!r}")

        image_paths = tuple((dataset_dir / item).resolve() for item in value.get("images", []))
        missing_images = [str(path) for path in image_paths if not path.is_file()]
        if missing_images:
            raise DatasetError(
                f"Missing image(s) in case {value['id']!r}: {', '.join(missing_images)}"
            )

        prohibited = value.get("prohibited_terms", [])
        if not isinstance(prohibited, list) or not all(
            isinstance(item, str) for item in prohibited
        ):
            raise DatasetError(f"prohibited_terms must be a list of strings in {value['id']!r}")
        raw_references = value.get("expected_references")
        if raw_references is not None and (
            not isinstance(raw_references, list)
            or not all(isinstance(item, str) and item.strip() for item in raw_references)
        ):
            raise DatasetError(
                f"expected_references must be a list of non-empty strings in {value['id']!r}"
            )
        authorization_context = value.get("authorization_context", "unspecified")
        if authorization_context not in AUTHORIZATION_CONTEXTS:
            raise DatasetError(
                f"Unknown authorization context {authorization_context!r} in {value['id']!r}"
            )

        return cls(
            id=str(value["id"]),
            category=str(value["category"]),
            mode=str(value["mode"]),
            prompt=str(value["prompt"]),
            expected_concepts=tuple(concepts),
            expected_references=(
                tuple(item.strip().upper() for item in raw_references)
                if raw_references is not None
                else None
            ),
            prohibited_terms=tuple(prohibited),
            minimum_score=minimum_score,
            image_paths=image_paths,
            authorization_context=authorization_context,
            metadata=dict(value.get("metadata", {})),
        )
