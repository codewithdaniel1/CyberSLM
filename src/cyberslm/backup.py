from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import tempfile
import zipfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from cyberslm import __version__
from cyberslm.config import settings


def copy_sqlite(source: Path, destination: Path) -> None:
    with sqlite3.connect(source) as source_connection, sqlite3.connect(
        destination
    ) as destination_connection:
        source_connection.backup(destination_connection)
    with sqlite3.connect(destination) as connection:
        result = connection.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise RuntimeError(f"Backup integrity check failed for {source}: {result}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_backup(output: Path, *, overwrite: bool = False) -> dict:
    output = output.resolve()
    if output.exists() and not overwrite:
        raise FileExistsError(f"Backup already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    files: list[tuple[Path, str]] = []
    with tempfile.TemporaryDirectory(prefix="cyberslm-backup-") as temporary:
        temporary_dir = Path(temporary)
        for source, archive_name in (
            (settings.database_path, "data/cyberslm.db"),
            (settings.knowledge_database_path, "data/knowledge/knowledge.db"),
        ):
            if source.is_file():
                copy = temporary_dir / source.name
                copy_sqlite(source, copy)
                files.append((copy, archive_name))
        for upload in sorted(settings.upload_dir.glob("*")):
            if upload.is_file() and upload.name != ".gitkeep":
                files.append((upload, f"data/uploads/{upload.name}"))
        manifest = {
            "schema_version": 1,
            "application_version": __version__,
            "created_at": datetime.now(UTC).isoformat(),
            "files": [
                {"path": archive_name, "sha256": sha256(path), "bytes": path.stat().st_size}
                for path, archive_name in files
            ],
        }
        mode = "w" if overwrite else "x"
        with zipfile.ZipFile(output, mode, compression=zipfile.ZIP_DEFLATED) as archive:
            for path, archive_name in files:
                archive.write(path, archive_name)
            archive.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a verified private CyberSLM backup")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--force", action="store_true", help="Overwrite an existing backup")
    args = parser.parse_args(argv)
    try:
        manifest = create_backup(args.output, overwrite=args.force)
    except (FileExistsError, OSError, RuntimeError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(f"Created {args.output.resolve()} with {len(manifest['files'])} verified files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
