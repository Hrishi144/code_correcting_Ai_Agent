"""Terminal commands, review previews, and explicit save approval."""

import argparse
import sys
import unicodedata

from .assistant import CodingAssistant
from .behavior import check_checkout
from .changes import save_change
from .config import Settings
from .ollama_client import ModelError, OllamaClient
from .repair import repair_checkout
from .validation import validate
from .workspace import Workspace


def safe_text(text: str) -> str:
    """Render controls visibly so source/model text cannot control the terminal."""
    return "".join(char if char in "\n\t" or not unicodedata.category(char).startswith("C")
                   else f"\\u{ord(char):04x}" for char in text)


def _model_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--model", default=Settings.model, help="Installed Ollama model name")
    parser.add_argument("--timeout", type=float, default=Settings.timeout_seconds,
                        help="Network timeout in seconds (default: 120)")
    parser.add_argument("--context", type=int, default=Settings.context_tokens,
                        help="Model context size in tokens (default: 4096); larger values need more memory")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m ai_agent", description="Local coding assistant with reviewed file changes.")
    commands = parser.add_subparsers(dest="command", required=True)
    ask = commands.add_parser("ask", help="Ask one coding question")
    ask.add_argument("prompt", nargs="?", help="Coding request, enclosed in quotes")
    _model_options(ask)
    for operation in ("inspect", "fix", "code"):
        command = commands.add_parser(operation, help={
            "inspect": "Read and analyze one selected file",
            "fix": "Propose a repair for one selected file",
            "code": "Create or edit one file from instructions",
        }[operation])
        _model_options(command)
        command.add_argument("--workspace", required=True, help="Approved workspace directory")
        if operation == "code":
            selection = command.add_mutually_exclusive_group(required=True)
            selection.add_argument("--file", help="Existing file to edit")
            selection.add_argument("--output", help="New file; must not already exist")
        else:
            command.add_argument("--file", required=True, help="Selected .py, .json, or .java file")
        command.add_argument("--request", required=operation == "code",
                             help="Instructions, observed error, or expected behavior")
        if operation == "fix":
            command.add_argument("--check", choices=["checkout"],
                                 help="Run the fixed checkout tests and retry repairs; standalone Python only")
            command.add_argument("--allow-execution", action="store_true",
                                 help="Allow original and model-proposed Python to execute with your permissions (not sandboxed)")
            command.add_argument("--max-attempts", type=int, choices=range(1, 6),
                                 help="Maximum model proposals with --check (default: 3)")
    return parser


def _ask(args: argparse.Namespace, assistant: CodingAssistant) -> int:
    prompt = args.prompt
    if prompt is None:
        if sys.stdin.isatty():
            print(f"Local coding assistant | {safe_text(args.model)}", file=sys.stderr)
            prompt = input("Your request: ")
        else:
            prompt = sys.stdin.read()
    if not prompt.strip():
        raise ValueError("Enter a coding request; the prompt cannot be empty.")
    print("Asking the local model...", file=sys.stderr, flush=True)
    reply = assistant.ask(prompt)
    print(safe_text(reply.text))
    if reply.truncated:
        print("Warning: response reached the output limit and may be incomplete. Try a smaller request.", file=sys.stderr)
        return 1
    return 0


def _file_operation(args: argparse.Namespace, assistant: CodingAssistant) -> int:
    automated = getattr(args, "check", None) == "checkout"
    if automated and not args.allow_execution:
        raise ValueError("--check checkout requires --allow-execution; original and proposed code will run with your permissions.")
    if not automated and (getattr(args, "allow_execution", False) or getattr(args, "max_attempts", None) is not None):
        raise ValueError("--allow-execution and --max-attempts require --check checkout.")
    workspace = Workspace(args.workspace)
    new_path = getattr(args, "output", None)
    snapshot = workspace.snapshot(new_path if new_path is not None else args.file, new=new_path is not None)
    print(f"Selected file: {safe_text(str(snapshot.path))}")
    checks = None
    if snapshot.raw is not None:
        checks = validate(snapshot.text, snapshot.path.name)
        print(f"Original validation: {checks.status}\n{safe_text(checks.detail)}")
    if args.command == "inspect":
        print("Asking the local model for analysis...", file=sys.stderr, flush=True)
        reply = assistant.inspect(snapshot, checks, args.request or "")
        print(f"\nModel analysis (not behavior verification):\n{safe_text(reply.text)}")
        if reply.truncated:
            print("Warning: analysis is incomplete because it reached the output limit.", file=sys.stderr)
        return 0 if checks.status == "passed" and not reply.truncated else 1

    request = args.request if args.request is not None else "Correct errors with the smallest necessary change."
    if not request.strip():
        raise ValueError("Describe the requested change.")
    print("Preparing a proposed change...", file=sys.stderr, flush=True)
    behavior = None
    if automated:
        print("Execution enabled: testing temporary copies of original and proposed Python with your permissions. "
              "This is not an OS sandbox.", file=sys.stderr, flush=True)
        outcome = repair_checkout(
            assistant, snapshot, request, allow_execution=args.allow_execution,
            max_attempts=args.max_attempts or 3,
            progress=lambda message: print(safe_text(message), file=sys.stderr, flush=True),
        )
        change, behavior = outcome.change, outcome.behavior
        workspace.assert_unchanged(snapshot)
        print(f"Repair attempts used: {outcome.attempts}")
        if outcome.attempts == 0 and behavior.status == "passed":
            print(f"Checkout checks: passed\n{safe_text(behavior.detail)}")
            print("Existing file passes the selected checks. No model call or save was needed.")
            return 0
    else:
        change = assistant.propose(snapshot, checks, request, operation=args.command)
    print(f"\nModel explanation (not verified):\n{safe_text(change.explanation)}")
    print(f"\nProposed validation: {change.validation.status}\n{safe_text(change.validation.detail)}")
    if behavior is None:
        print("Behavior verification: not run. Correct results and instruction compliance have not been checked.")
    else:
        print(f"Checkout checks: {behavior.status}\n{safe_text(behavior.detail)}")
        if behavior.status != "passed":
            if change.changed:
                print(f"\nLast proposed changes:\n{safe_text(change.diff())}")
            print("Saving blocked: checkout checks did not pass. Nothing was saved.")
            return 1
    if not change.changed:
        print("No content changes proposed. Nothing was saved.")
        return 0 if change.validation.status == "passed" else 1
    print(f"\nChanges (- original, + proposed):\n{safe_text(change.diff())}")
    if args.command == "fix" and change.python_structure_unchanged:
        print("Warning: Python code structure is unchanged; this proposal only changes comments or formatting. "
              "It does not demonstrate a logic repair. Review the diff before saving.")
    if change.validation.status != "passed":
        print("Saving blocked: proposed content did not pass validation. Nothing was saved.")
        return 1
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("Preview only: saving requires an interactive terminal for review and approval.")
        return 0
    approval = input("Type 'save' to approve this exact change, or press Enter to reject: ")
    if approval.strip() != "save":
        print("Rejected. Nothing was saved.")
        return 0
    if automated:
        workspace.assert_unchanged(snapshot)
        print("Rechecking checkout behavior before saving...", file=sys.stderr, flush=True)
        final_check = check_checkout(snapshot, change.content)
        if final_check.status != "passed":
            print(f"Saving blocked: checkout recheck {final_check.status}.\n{safe_text(final_check.detail)}")
            return 1
    backup = save_change(workspace, change, approved=True)
    print(f"Saved: {safe_text(str(snapshot.path))}")
    if backup is not None:
        print(f"Original backup: {safe_text(str(backup))}")
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    # Preserve the original one-question command while adding explicit subcommands.
    if not arguments or arguments[0] not in {"ask", "inspect", "fix", "code", "-h", "--help"}:
        arguments.insert(0, "ask")
    args = _parser().parse_args(arguments)
    try:
        settings = Settings(model=args.model, timeout_seconds=args.timeout, context_tokens=args.context)
        assistant = CodingAssistant(OllamaClient(settings))
        if args.command == "ask":
            return _ask(args, assistant)
        return _file_operation(args, assistant)
    except (ValueError, ModelError, OSError, RecursionError) as exc:
        print(f"Error: {safe_text(str(exc))}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.", file=sys.stderr)
        return 130
