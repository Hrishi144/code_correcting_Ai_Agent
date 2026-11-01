"""Terminal commands, review previews, and explicit save approval."""

import argparse
import sys
import unicodedata

from .assistant import CodingAssistant
from .changes import save_change
from .config import Settings
from .ollama_client import ModelError, OllamaClient
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
    change = assistant.propose(snapshot, checks, request, operation=args.command)
    print(f"\nExplanation:\n{safe_text(change.explanation)}")
    print(f"\nProposed validation: {change.validation.status}\n{safe_text(change.validation.detail)}")
    if not change.changed:
        print("No content changes proposed. Nothing was saved.")
        return 0 if change.validation.status == "passed" else 1
    print(f"\nChanges (- original, + proposed):\n{safe_text(change.diff())}")
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
        settings = Settings(model=args.model, timeout_seconds=args.timeout)
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
