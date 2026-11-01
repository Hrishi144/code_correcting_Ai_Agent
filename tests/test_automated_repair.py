"""Real checkout workers and simulated model proposals for the opt-in repair loop."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from ai_agent.assistant import CodingAssistant
from ai_agent.behavior import check_checkout
from ai_agent.cli import main
from ai_agent.ollama_client import ModelError, ModelReply, OllamaClient
from ai_agent.config import Settings
from ai_agent.repair import repair_checkout
from ai_agent.validation import ValidationResult
from ai_agent.workspace import Workspace
from test_checkout_example import CORRECT_SOURCE


BROKEN_SOURCE = CORRECT_SOURCE.replace('item["price"] * item["quantity"]',
                                      'item["price"] + item["quantity"]')


def reply(source):
    return ModelReply(json.dumps({"explanation": "Repair checkout calculations", "content": source}))


class InteractiveBuffer(io.StringIO):
    def isatty(self):
        return True


class AutomatedRepairTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="repair-test-")
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.path = self.root / "checkout.py"
        self.path.write_text(BROKEN_SOURCE, encoding="utf-8")
        self.workspace = Workspace(self.root)
        self.snapshot = self.workspace.snapshot(self.path.name)
        self.client = Mock()
        self.assistant = CodingAssistant(self.client)

    def test_real_worker_distinguishes_correct_and_incorrect_results(self):
        self.assertEqual(check_checkout(self.snapshot, CORRECT_SOURCE).status, "passed")
        result = check_checkout(self.snapshot, BROKEN_SOURCE)
        self.assertEqual(result.status, "failed")
        self.assertIn("test_discount_and_tax", result.detail)
        self.assertEqual(self.path.read_bytes(), self.snapshot.raw)

    def test_worker_contains_output_and_handles_load_failure_exit_and_timeout(self):
        self.assertEqual(check_checkout(self.snapshot, "print('x' * 100000)\n" + CORRECT_SOURCE).status, "passed")
        for source in ("x = 1", "raise RuntimeError('broken')", "raise SystemExit(0)", "import os; os._exit(0)"):
            with self.subTest(source=source):
                self.assertEqual(check_checkout(self.snapshot, source).status, "failed")
        result = check_checkout(self.snapshot, "while True: pass", timeout_seconds=0.3)
        self.assertEqual(result.status, "failed")
        self.assertIn("exceeded", result.detail)

    def test_candidate_self_modification_is_not_accepted(self):
        source = "from pathlib import Path\nPath(__file__).write_text('x = 1')\n" + CORRECT_SOURCE
        result = check_checkout(self.snapshot, source)
        self.assertEqual(result.status, "unavailable")
        self.assertIn("modified", result.detail)

    def test_worker_reports_require_all_checks_and_valid_schema(self):
        for report in ({}, [], {"status": [], "detail": "x", "tests_run": 8},
                       {"status": "passed", "detail": "x", "tests_run": 0}):
            def fake_run(*args, **kwargs):
                (kwargs["cwd"] / "checkout-report.json").write_text(json.dumps(report), encoding="utf-8")
                return Mock(returncode=0)
            with self.subTest(report=report), patch("ai_agent.behavior.subprocess.run", side_effect=fake_run):
                self.assertEqual(check_checkout(self.snapshot, CORRECT_SOURCE).status, "unavailable")

    def test_execution_opt_in_and_supported_file_are_required_before_work(self):
        with patch("ai_agent.repair.check_checkout") as runner:
            for options in ({}, {"allow_execution": True, "max_attempts": 0},
                            {"allow_execution": True, "max_attempts": 6}):
                with self.subTest(options=options), self.assertRaises(ValueError):
                    repair_checkout(self.assistant, self.snapshot, "Repair", **options)
            with self.assertRaises(ValueError):
                repair_checkout(self.assistant, replace(self.snapshot, path=self.root / "data.json"),
                                "Repair", allow_execution=True)
            runner.assert_not_called()
        self.client.chat.assert_not_called()

    def test_retry_uses_failed_candidate_but_diff_stays_against_original(self):
        comment_only = "# Calculate checkout\n" + BROKEN_SOURCE
        self.client.chat.side_effect = [reply(comment_only), reply(CORRECT_SOURCE)]
        outcome = repair_checkout(self.assistant, self.snapshot, "Comment corrections", allow_execution=True)
        self.assertEqual(outcome.attempts, 2)
        self.assertEqual(outcome.behavior.status, "passed")
        self.assertIs(outcome.change.original, self.snapshot)
        self.assertNotIn("-# Calculate checkout", outcome.change.diff())
        messages = self.client.chat.call_args_list[1].args[0]
        payload = json.loads(messages[1]["content"])
        self.assertEqual(payload["source"], comment_only)
        self.assertEqual(payload["request"], "Comment corrections")
        self.assertIn("test_discount_and_tax", payload["diagnostics"])
        self.assertIn("500,50,45,495", payload["diagnostics"])
        self.assertEqual(self.path.read_bytes(), self.snapshot.raw)
        self.assertFalse((self.root / ".ai_agent_backups").exists())

    def test_failed_repair_stops_at_attempt_limit_without_writing(self):
        self.client.chat.return_value = reply(BROKEN_SOURCE)
        outcome = repair_checkout(self.assistant, self.snapshot, "Repair", allow_execution=True, max_attempts=2)
        self.assertEqual(outcome.attempts, 2)
        self.assertEqual(self.client.chat.call_count, 2)
        self.assertEqual(outcome.behavior.status, "failed")
        self.assertEqual(self.path.read_bytes(), self.snapshot.raw)

    def test_syntax_failure_retries_without_executing_invalid_candidate(self):
        self.client.chat.side_effect = [reply("def broken("), reply(CORRECT_SOURCE)]
        with patch("ai_agent.repair.check_checkout", wraps=check_checkout) as runner:
            outcome = repair_checkout(self.assistant, self.snapshot, "Repair", allow_execution=True)
        self.assertEqual(outcome.behavior.status, "passed")
        self.assertEqual(runner.call_count, 2)  # Original and the valid final candidate.
        feedback = json.loads(self.client.chat.call_args.args[0][1]["content"])["diagnostics"]
        self.assertIn("Line", feedback)

    def test_already_correct_original_needs_no_model_call(self):
        original = replace(self.snapshot, text=CORRECT_SOURCE, raw=CORRECT_SOURCE.encode())
        result = repair_checkout(self.assistant, original, "Repair", allow_execution=True)
        self.assertEqual(result.attempts, 0)
        self.assertEqual(result.behavior.status, "passed")
        self.client.chat.assert_not_called()

    def test_unavailable_worker_stops_without_model_call(self):
        with patch("ai_agent.repair.check_checkout", return_value=ValidationResult("unavailable", "Cannot start worker")):
            outcome = repair_checkout(self.assistant, self.snapshot, "Repair", allow_execution=True)
        self.assertEqual(outcome.behavior.status, "unavailable")
        self.assertEqual(outcome.attempts, 0)
        self.client.chat.assert_not_called()

    def test_malformed_model_proposal_stops_without_writing(self):
        self.client.chat.return_value = ModelReply("not json")
        with self.assertRaises(ModelError):
            repair_checkout(self.assistant, self.snapshot, "Repair", allow_execution=True)
        self.assertEqual(self.path.read_bytes(), self.snapshot.raw)

    def test_checkout_feedback_fits_default_model_budget_for_example(self):
        transport = OllamaClient(Settings())
        transport._opener = Mock()
        transport._opener.open.return_value = io.BytesIO(json.dumps({
            "message": {"content": reply(CORRECT_SOURCE).text}, "done": True,
        }).encode())
        outcome = repair_checkout(CodingAssistant(transport), self.snapshot, "Comment corrections", allow_execution=True)
        self.assertEqual(outcome.behavior.status, "passed")
        transport._opener.open.assert_called_once()

    def test_expanded_retry_preserves_source_with_explicit_larger_context(self):
        expanded = "# Comment added by the first proposal: " + "x" * 1200 + "\n" + BROKEN_SOURCE
        for context in (4096, 8192):
            with self.subTest(context=context):
                transport = OllamaClient(Settings(context_tokens=context))
                transport._opener = Mock()
                transport._opener.open.side_effect = [
                    io.BytesIO(json.dumps({"message": {"content": reply(source).text}, "done": True}).encode())
                    for source in (expanded, CORRECT_SOURCE)
                ]
                with patch("ai_agent.repair.check_checkout", side_effect=[
                    ValidationResult("failed", "test_discount_and_tax"),
                    ValidationResult("failed", "test_discount_and_tax"),
                    ValidationResult("passed", "8 checks passed"),
                ]):
                    if context == 4096:
                        with self.assertRaisesRegex(ModelError, "--context 8192"):
                            repair_checkout(CodingAssistant(transport), self.snapshot, "Comment corrections",
                                            allow_execution=True, max_attempts=2)
                        transport._opener.open.assert_called_once()
                    else:
                        result = repair_checkout(CodingAssistant(transport), self.snapshot, "Comment corrections",
                                                 allow_execution=True, max_attempts=2)
                        self.assertEqual(result.attempts, 2)
                        self.assertEqual(result.behavior.status, "passed")
                        self.assertEqual(transport._opener.open.call_count, 2)
                        sent = json.loads(transport._opener.open.call_args.args[0].data)
                        self.assertEqual(sent["options"]["num_ctx"], 8192)
                        self.assertEqual(json.loads(sent["messages"][1]["content"])["source"], expanded)
                self.assertEqual(self.path.read_bytes(), self.snapshot.raw)

    def invoke(self, *, approval="", interactive=True, extra=None, candidate=CORRECT_SOURCE):
        stdout = InteractiveBuffer() if interactive else io.StringIO()
        stderr = io.StringIO()
        command = ["fix", "--workspace", str(self.root), "--file", self.path.name]
        command += extra if extra is not None else ["--check", "checkout", "--allow-execution"]
        with patch("ai_agent.cli.OllamaClient") as client, \
                patch("sys.stdin", InteractiveBuffer() if interactive else io.StringIO()), \
                patch("builtins.input", return_value=approval) as prompt, \
                redirect_stdout(stdout), redirect_stderr(stderr):
            client.return_value.chat.return_value = reply(candidate)
            status = main(command)
        return status, stdout.getvalue(), stderr.getvalue(), prompt, client

    def test_cli_requires_execution_option_and_check_selection(self):
        for options in (["--check", "checkout"], ["--allow-execution"], ["--max-attempts", "2"]):
            with self.subTest(options=options), patch("ai_agent.repair.check_checkout") as runner:
                status, _, _, prompt, client = self.invoke(extra=options)
                self.assertEqual(status, 1)
                runner.assert_not_called()
                prompt.assert_not_called()
                client.return_value.chat.assert_not_called()

    def test_cli_failed_checks_never_allow_save(self):
        status, output, _, prompt, client = self.invoke(approval="save", candidate=BROKEN_SOURCE)
        self.assertEqual(status, 1)
        self.assertIn("Saving blocked", output)
        self.assertEqual(client.return_value.chat.call_count, 3)
        prompt.assert_not_called()
        self.assertEqual(self.path.read_bytes(), self.snapshot.raw)

    def test_cli_approved_success_rechecks_and_preserves_original_backup(self):
        with patch("ai_agent.cli.check_checkout", wraps=check_checkout) as recheck:
            status, output, _, _, _ = self.invoke(approval="save")
        self.assertEqual(status, 0, output)
        self.assertIn("Saved:", output)
        recheck.assert_called_once()
        self.assertEqual(self.path.read_text(), CORRECT_SOURCE)
        self.assertEqual(next((self.root / ".ai_agent_backups").iterdir()).read_bytes(), self.snapshot.raw)

    def test_cli_rejection_or_redirected_output_does_not_save(self):
        for interactive in (True, False):
            with self.subTest(interactive=interactive), patch("ai_agent.cli.check_checkout") as recheck:
                status, _, _, prompt, _ = self.invoke(interactive=interactive)
                self.assertEqual(status, 0)
                recheck.assert_not_called()
                if not interactive:
                    prompt.assert_not_called()
                self.assertEqual(self.path.read_bytes(), self.snapshot.raw)

    def test_cli_failed_presave_recheck_blocks_save(self):
        with patch("ai_agent.cli.check_checkout", return_value=ValidationResult("failed", "Changed result")):
            status, output, _, _, _ = self.invoke(approval="save")
        self.assertEqual(status, 1)
        self.assertIn("Saving blocked", output)
        self.assertEqual(self.path.read_bytes(), self.snapshot.raw)
        self.assertFalse((self.root / ".ai_agent_backups").exists())
