from pathlib import Path

from cyberslm.config import Settings


def test_data_directory_override_moves_all_runtime_data(
    tmp_path: Path,
    monkeypatch,
) -> None:
    data_dir = tmp_path / "isolated data"
    monkeypatch.setenv("CYBERSLM_DATA_DIR", str(data_dir))

    configured = Settings()

    assert configured.data_dir == data_dir
    assert configured.training_dir == data_dir / "training"
    assert configured.adapter_dir == data_dir / "adapters"
    assert configured.knowledge_dir == data_dir / "knowledge"
    assert configured.knowledge_database_path == data_dir / "knowledge" / "knowledge.db"
    assert configured.embedding_cache_dir == data_dir / "knowledge" / "models"


def test_data_directory_defaults_to_repository_data(monkeypatch) -> None:
    monkeypatch.delenv("CYBERSLM_DATA_DIR", raising=False)

    configured = Settings()

    assert configured.data_dir == configured.project_root / "data"
