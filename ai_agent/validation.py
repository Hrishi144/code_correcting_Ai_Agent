"""Static checks only: never execute selected or generated programs."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from .config import COMPILER_TIMEOUT_SECONDS


@dataclass(frozen=True)
class ValidationResult:
    status: str  # passed, failed, or unavailable
    detail: str


def _reject_constant(value: str) -> None:
    raise ValueError(f"{value} is not a valid JSON number.")


def validate(content: str, filename: str) -> ValidationResult:
    suffix = Path(filename).suffix.lower()
    try:
        if suffix == ".py":
            # Compile in memory, without executing, importing, or writing .pyc files.
            compile(content, filename, "exec", dont_inherit=True)
            return ValidationResult("passed", "Python syntax passed; behavior was not tested.")
        if suffix == ".json":
            json.loads(content, parse_constant=_reject_constant)
            return ValidationResult("passed", "JSON parsing passed; no application schema was checked.")
        if suffix == ".java":
            return _validate_java(content, Path(filename).name)
    except SyntaxError as exc:
        return ValidationResult("failed", f"Line {exc.lineno}, column {exc.offset}: {exc.msg}")
    except (ValueError, RecursionError) as exc:
        return ValidationResult("failed", str(exc))
    return ValidationResult("unavailable", "Unsupported file type.")


def _validate_java(content: str, filename: str) -> ValidationResult:
    compiler = shutil.which("javac")
    if compiler is None:
        return ValidationResult("unavailable", "javac is not available. Install/select a JDK to verify Java.")
    try:
        with tempfile.TemporaryDirectory(prefix="ai-agent-javac-") as folder:
            root = Path(folder)
            source = root / filename
            source.write_text(content, encoding="utf-8")
            empty = root / "empty"
            output = root / "classes"
            empty.mkdir()
            output.mkdir()
            # Avoid inherited compiler options, agents, processors, and project
            # dependency discovery. The JDK's own standard library remains available.
            blocked = {"CLASSPATH", "JDK_JAVAC_OPTIONS", "JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS", "JDK_JAVA_OPTIONS"}
            environment = {key: value for key, value in os.environ.items() if key.upper() not in blocked}
            result = subprocess.run(
                [compiler, "-proc:none", "-implicit:none", "-encoding", "UTF-8",
                 "-classpath", str(empty), "-sourcepath", str(empty),
                 "--module-path", str(empty), "-d", str(output), str(source)],
                cwd=root, env=environment, capture_output=True, text=True,
                errors="replace", timeout=COMPILER_TIMEOUT_SECONDS,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode == 0:
                return ValidationResult("passed", "Java compilation passed; the program was not run.")
            diagnostics = (result.stderr or result.stdout).strip().replace(str(root), "<temporary>")
            return ValidationResult(
                "failed", diagnostics[:4000] + "\nOnly this file and JDK libraries were checked. "
                "Missing project dependencies can also cause compilation failure.",
            )
    except subprocess.TimeoutExpired:
        return ValidationResult("unavailable", "Java compilation exceeded the 20-second limit.")
    except OSError as exc:
        return ValidationResult("unavailable", f"Could not run javac: {exc}")
