from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

C_FENCE = re.compile(r"```[ \t]*(?:c|C)[ \t]*\r?\n(.*?)```", re.DOTALL)
ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
INCLUDE_DIRECTIVE = re.compile(
    r"^\s*#\s*(?:include|include_next|import)\s+(.+?)\s*$",
    re.MULTILINE,
)


def extract_c_blocks(markdown: str, *, limit: int = 4) -> list[str]:
    return [match.group(1).strip() for match in C_FENCE.finditer(markdown)][:limit]


def find_c_compiler(configured: str | None = None) -> str | None:
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.is_absolute() and candidate.is_file():
            return str(candidate)
        return shutil.which(configured)
    for name in ("clang", "gcc", "cc"):
        if compiler := shutil.which(name):
            return compiler
    return None


def unsafe_preprocessor_reason(source: str) -> str | None:
    if "__has_include" in source:
        return "__has_include is not allowed in local validation"
    for match in INCLUDE_DIRECTIVE.finditer(source):
        operand = match.group(1).split("//", 1)[0].strip()
        if len(operand) < 3 or operand[0] not in {'"', "<"}:
            return "computed include paths are not allowed in local validation"
        closing = '"' if operand[0] == '"' else ">"
        end = operand.find(closing, 1)
        if end < 0:
            continue
        include_path = operand[1:end]
        parts = Path(include_path).parts
        if Path(include_path).is_absolute() or ".." in parts:
            return "absolute and parent-relative include paths are not allowed"
    return None


@dataclass(frozen=True, slots=True)
class CCodeValidator:
    enabled: bool = True
    configured_compiler: str | None = None
    timeout_seconds: float = 4.0
    max_source_chars: int = 50_000
    max_diagnostic_chars: int = 4_000
    max_blocks: int = 4

    @property
    def compiler(self) -> str | None:
        return find_c_compiler(self.configured_compiler)

    @property
    def status(self) -> dict[str, Any]:
        compiler = self.compiler
        return {
            "enabled": self.enabled,
            "available": compiler is not None,
            "compiler": Path(compiler).name if compiler else None,
            "execution": "syntax-only; generated programs are never linked or run",
        }

    def validate(self, markdown: str, *, requested: bool) -> dict[str, Any]:
        compiler = self.compiler
        report: dict[str, Any] = {
            "requested": requested,
            **self.status,
            "status": "not_requested",
            "blocks": [],
        }
        if not requested:
            return report
        if not self.enabled:
            report["status"] = "disabled"
            return report

        blocks = extract_c_blocks(markdown, limit=self.max_blocks)
        if not blocks:
            report["status"] = "no_c_blocks"
            return report
        if compiler is None:
            report["status"] = "compiler_unavailable"
            return report

        with tempfile.TemporaryDirectory(prefix="cyberslm-c-check-") as workdir:
            results = [
                self._validate_block(compiler, block, index, workdir)
                for index, block in enumerate(blocks, start=1)
            ]
        report["blocks"] = results
        failures = {"failed", "timed_out", "too_large", "unsafe_source", "error"}
        if any(item["status"] in failures for item in results):
            report["status"] = "failed"
        elif any(item["status"] == "passed_with_warnings" for item in results):
            report["status"] = "passed_with_warnings"
        else:
            report["status"] = "passed"
        return report

    def _validate_block(
        self,
        compiler: str,
        source: str,
        index: int,
        workdir: str,
    ) -> dict[str, Any]:
        if len(source) > self.max_source_chars:
            return {
                "index": index,
                "status": "too_large",
                "diagnostics": (
                    f"Block has {len(source):,} characters; the local limit is "
                    f"{self.max_source_chars:,}."
                ),
            }
        if unsafe_reason := unsafe_preprocessor_reason(source):
            return {
                "index": index,
                "status": "unsafe_source",
                "diagnostics": f"Syntax check was not started: {unsafe_reason}.",
            }
        command = [
            compiler,
            "-x",
            "c",
            "-std=c17",
            "-fsyntax-only",
            "-Wall",
            "-Wextra",
            "-Wpedantic",
            "-fno-diagnostics-color",
            "-",
        ]
        try:
            completed = subprocess.run(
                command,
                input=source,
                text=True,
                capture_output=True,
                check=False,
                cwd=workdir,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return {
                "index": index,
                "status": "timed_out",
                "diagnostics": f"Syntax check exceeded {self.timeout_seconds:g} seconds.",
            }
        except OSError as exc:
            return {
                "index": index,
                "status": "error",
                "diagnostics": f"Unable to start the compiler: {type(exc).__name__}: {exc}",
            }

        diagnostics = ANSI_ESCAPE.sub(
            "", "\n".join((completed.stderr, completed.stdout)).strip()
        )
        if len(diagnostics) > self.max_diagnostic_chars:
            diagnostics = (
                diagnostics[: self.max_diagnostic_chars].rstrip() + "\n…diagnostics truncated"
            )
        if completed.returncode:
            status = "failed"
        elif diagnostics:
            status = "passed_with_warnings"
        else:
            status = "passed"
        return {"index": index, "status": status, "diagnostics": diagnostics}


def validation_footer(report: dict[str, Any]) -> str:
    if not report.get("requested"):
        return ""
    status = report["status"]
    heading = "\n\n---\n**Local C syntax check — generated code was not executed**"
    if status == "disabled":
        return f"{heading}\n\nValidation is disabled by the server configuration."
    if status == "compiler_unavailable":
        return f"{heading}\n\nNo compatible local C compiler was found; validation was not run."
    if status == "no_c_blocks":
        return f"{heading}\n\nNo fenced C code block was found."

    lines = [heading]
    for block in report["blocks"]:
        readable = block["status"].replace("_", " ")
        lines.append(f"\nBlock {block['index']}: **{readable}**")
        if block["diagnostics"]:
            safe_diagnostics = block["diagnostics"].replace("```", "``\u200b`")
            lines.append(f"```text\n{safe_diagnostics}\n```")
    return "\n".join(lines)
