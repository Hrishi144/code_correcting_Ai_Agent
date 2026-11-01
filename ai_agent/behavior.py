"""Opt-in execution of standalone checkout code in a timed child process.

A temporary directory and isolated Python imports are NOT a security sandbox.
Executed code retains the user's filesystem, network, and process permissions.
"""

import json
from pathlib import Path
import subprocess
import sys
import tempfile

from .validation import ValidationResult
from .workspace import FileSnapshot


CHECK_TIMEOUT_SECONDS = 10


def check_checkout(snapshot: FileSnapshot, content: str, *,
                   timeout_seconds: float = CHECK_TIMEOUT_SECONDS) -> ValidationResult:
    if snapshot.path.suffix.lower() != ".py":
        raise ValueError("Checkout checks support standalone Python files only.")
    worker = Path(__file__).with_name("checkout_checks.py").resolve()
    data = snapshot.encode(content)
    try:
        with tempfile.TemporaryDirectory(prefix="ai-agent-checkout-") as folder:
            root = Path(folder)
            source = root / snapshot.path.name
            report_path = root / "checkout-report.json"
            source.write_bytes(data)
            completed = subprocess.run(
                [sys.executable, "-I", "-B", str(worker), str(source), str(report_path)],
                cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=timeout_seconds,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            with source.open("rb") as handle:
                staged = handle.read(len(data) + 1)
            if staged != data:
                return ValidationResult("unavailable", "Candidate modified its staged source during execution.")
            if completed.returncode != 0 or not report_path.is_file():
                return ValidationResult("failed", "Checkout worker exited without completing the checks.")
            with report_path.open("rb") as handle:
                raw = handle.read(4097)
            if len(raw) > 4096:
                return ValidationResult("unavailable", "Checkout worker report exceeded its size limit.")
            report = json.loads(raw)
            if (not isinstance(report, dict) or not isinstance(report.get("status"), str)
                    or report["status"] not in {"passed", "failed"}
                    or not isinstance(report.get("detail"), str)
                    or type(report.get("tests_run")) is not int
                    or not 0 <= report["tests_run"] <= 8
                    or (report["status"] == "passed" and report["tests_run"] != 8)):
                return ValidationResult("unavailable", "Checkout worker returned an invalid report.")
            return ValidationResult(report["status"], report["detail"])
    except subprocess.TimeoutExpired:
        return ValidationResult("failed", f"Checkout execution exceeded {timeout_seconds:g} seconds.")
    except (OSError, ValueError) as exc:
        return ValidationResult("unavailable", f"Checkout checks could not complete: {exc}")
