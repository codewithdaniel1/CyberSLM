import json
import sqlite3
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

import cyberslm.backup as backup_module
from cyberslm.backup import create_backup


def test_backup_copies_consistent_databases_and_uploads(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    upload_dir = data_dir / "uploads"
    knowledge_dir = data_dir / "knowledge"
    upload_dir.mkdir(parents=True)
    knowledge_dir.mkdir()
    database = data_dir / "cyberslm.db"
    knowledge = knowledge_dir / "knowledge.db"
    for path in (database, knowledge):
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE sample (value TEXT)")
            connection.execute("INSERT INTO sample VALUES ('verified')")
    (upload_dir / "evidence.png").write_bytes(b"test attachment")
    monkeypatch.setattr(
        backup_module,
        "settings",
        replace(
            backup_module.settings,
            data_dir=data_dir,
            upload_dir=upload_dir,
            database_path=database,
            knowledge_dir=knowledge_dir,
            knowledge_database_path=knowledge,
        ),
    )

    output = tmp_path / "backup.zip"
    manifest = create_backup(output)
    assert len(manifest["files"]) == 3
    with zipfile.ZipFile(output) as archive:
        stored = json.loads(archive.read("manifest.json"))
        assert stored["application_version"] == "0.5.0"
        assert "data/cyberslm.db" in archive.namelist()
        assert "data/knowledge/knowledge.db" in archive.namelist()
        assert "data/uploads/evidence.png" in archive.namelist()

    with pytest.raises(FileExistsError):
        create_backup(output)
