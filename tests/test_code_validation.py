from __future__ import annotations

import shutil
import subprocess

import pytest

import cyberslm.code_validation as validation_module
from cyberslm.code_validation import CCodeValidator, extract_c_blocks, validation_footer


def test_extracts_only_fenced_c_blocks() -> None:
    markdown = """```python
print('not C')
```
```c
int main(void) { return 0; }
```
```C
int value = 1;
```"""

    assert extract_c_blocks(markdown) == [
        "int main(void) { return 0; }",
        "int value = 1;",
    ]


def test_validator_invokes_syntax_only_compiler(monkeypatch) -> None:
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(validation_module, "find_c_compiler", lambda configured=None: "/cc")
    monkeypatch.setattr(validation_module.subprocess, "run", fake_run)
    report = CCodeValidator().validate(
        "```c\nint main(void) { return 0; }\n```",
        requested=True,
    )

    assert report["status"] == "passed"
    assert "-fsyntax-only" in captured["command"]
    assert captured["command"][-1] == "-"
    assert captured["kwargs"]["input"] == "int main(void) { return 0; }"
    assert "shell" not in captured["kwargs"]


def test_validator_rejects_local_file_include_without_starting_compiler(monkeypatch) -> None:
    monkeypatch.setattr(validation_module, "find_c_compiler", lambda configured=None: "/cc")

    def unexpected_run(*args, **kwargs):
        del args, kwargs
        raise AssertionError("compiler should not run")

    monkeypatch.setattr(validation_module.subprocess, "run", unexpected_run)
    report = CCodeValidator().validate(
        '```c\n#include "/etc/passwd"\nint main(void) { return 0; }\n```',
        requested=True,
    )

    assert report["status"] == "failed"
    assert report["blocks"][0]["status"] == "unsafe_source"
    assert "never linked or run" in report["execution"]


def test_validator_reports_timeout(monkeypatch) -> None:
    monkeypatch.setattr(validation_module, "find_c_compiler", lambda configured=None: "/cc")

    def timeout(*args, **kwargs):
        del args, kwargs
        raise subprocess.TimeoutExpired("cc", 1)

    monkeypatch.setattr(validation_module.subprocess, "run", timeout)
    report = CCodeValidator(timeout_seconds=1).validate(
        "```c\nint main(void) { return 0; }\n```",
        requested=True,
    )

    assert report["status"] == "failed"
    assert report["blocks"][0]["status"] == "timed_out"


def test_validation_footer_is_explicit_about_non_execution() -> None:
    report = {
        "requested": True,
        "status": "failed",
        "blocks": [{"index": 1, "status": "failed", "diagnostics": "expected ';'"}],
    }
    footer = validation_footer(report)

    assert "generated code was not executed" in footer
    assert "Block 1: **failed**" in footer
    assert "expected ';'" in footer


def test_local_compiler_accepts_valid_c_and_rejects_invalid_c() -> None:
    if not any(shutil.which(name) for name in ("clang", "gcc", "cc")):
        pytest.skip("No local C compiler installed")
    validator = CCodeValidator(timeout_seconds=10)

    valid = validator.validate("```c\nint main(void) { return 0; }\n```", requested=True)
    invalid = validator.validate("```c\nint main(void) { return }\n```", requested=True)

    assert valid["status"] in {"passed", "passed_with_warnings"}
    assert invalid["status"] == "failed"
    assert invalid["blocks"][0]["diagnostics"]
