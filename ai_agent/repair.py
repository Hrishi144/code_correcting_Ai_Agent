"""Bounded checkout repair loop; every proposal remains anchored to the original."""

from dataclasses import dataclass, replace
from typing import Callable

from .assistant import CodingAssistant
from .behavior import check_checkout
from .changes import ProposedChange
from .checkout_checks import CHECKOUT_CONTRACT
from .validation import ValidationResult, validate
from .workspace import FileSnapshot


@dataclass(frozen=True)
class RepairResult:
    change: ProposedChange
    behavior: ValidationResult
    attempts: int


def repair_checkout(assistant: CodingAssistant, original: FileSnapshot, request: str, *,
                    allow_execution: bool = False, max_attempts: int = 3,
                    progress: Callable[[str], None] | None = None) -> RepairResult:
    if not allow_execution:
        raise ValueError("Checkout automation requires --allow-execution: original and proposed code will execute.")
    if original.path.suffix.lower() != ".py" or original.raw is None:
        raise ValueError("Checkout automation requires an existing standalone .py file.")
    if type(max_attempts) is not int or not 1 <= max_attempts <= 5:
        raise ValueError("Repair attempts must be between 1 and 5.")
    if not request.strip():
        raise ValueError("Describe the requested change.")

    def report(label, result):
        if progress:
            progress(f"{label}: {result.status}\n{result.detail}")

    checks = validate(original.text, original.path.name)
    behavior = (check_checkout(original, original.text) if checks.status == "passed" else
                ValidationResult("not_run", "Checkout checks skipped because syntax did not pass."))
    report("Original checkout checks", behavior)
    change = ProposedChange(original, "No repair attempted.", original.text, checks)
    if behavior.status in {"passed", "unavailable"}:
        if behavior.status == "passed":
            change = replace(change, explanation="Existing file passes the checkout checks; no repair needed.")
        return RepairResult(change, behavior, 0)

    current = original
    for attempt in range(1, max_attempts + 1):
        if progress:
            progress(f"Repair attempt {attempt}/{max_attempts}")
        diagnostic = checks.detail if checks.status != "passed" else behavior.detail
        feedback = ValidationResult("failed", diagnostic + "\nRequired: " + CHECKOUT_CONTRACT)
        proposed = assistant.propose(current, feedback, request, operation="fix")
        # Later attempts use the previous candidate as model input, but saving and
        # the final diff always refer to the actual original file and its bytes.
        change = replace(proposed, original=original)
        checks = change.validation
        behavior = (check_checkout(original, change.content) if checks.status == "passed" else
                    ValidationResult("not_run", "Checkout checks skipped because syntax did not pass."))
        report(f"Attempt {attempt} checkout checks", behavior)
        if behavior.status in {"passed", "unavailable"}:
            return RepairResult(change, behavior, attempt)
        current = replace(original, text=change.content)
    return RepairResult(change, behavior, max_attempts)
