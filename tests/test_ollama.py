from pathlib import Path

import pytest

from cyberslm.ollama import main, publish_local


def test_publish_local_uses_tracked_modelfile(tmp_path: Path, monkeypatch) -> None:
    modelfile = tmp_path / "Modelfile"
    modelfile.write_text("FROM gemma3:4b\n", encoding="utf-8")
    commands: list[list[str]] = []

    def fake_run(command: list[str], check: bool) -> None:
        assert check is True
        commands.append(command)

    monkeypatch.setattr("cyberslm.ollama.subprocess.run", fake_run)

    command = publish_local("gemma3-4b-cyberslm-crypto:dev", modelfile)

    assert command == ["ollama", "create", "gemma3-4b-cyberslm-crypto:dev", "-f", str(modelfile)]
    assert commands == [command]


def test_publish_local_refuses_missing_modelfile(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Modelfile not found"):
        publish_local("test", tmp_path / "missing")


def test_ollama_publish_dry_run_does_not_call_ollama(tmp_path: Path, capsys) -> None:
    modelfile = tmp_path / "Modelfile"
    modelfile.write_text("FROM gemma3:4b\n", encoding="utf-8")

    exit_code = main(["publish-local", "--modelfile", str(modelfile), "--dry-run"])

    assert exit_code == 0
    assert "Would run: ollama create" in capsys.readouterr().out
