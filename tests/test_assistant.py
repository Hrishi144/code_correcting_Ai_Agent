import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import Mock, patch

from ai_agent.assistant import CodingAssistant
from ai_agent.cli import main
from ai_agent.config import Settings
from ai_agent.ollama_client import ModelError, ModelReply


class AssistantTests(unittest.TestCase):
    def test_empty_request_does_not_call_model(self):
        client = Mock()
        with self.assertRaises(ValueError):
            CodingAssistant(client).ask("  ")
        client.chat.assert_not_called()

    def test_request_includes_user_prompt_and_capability_limits(self):
        client = Mock()
        client.chat.return_value = ModelReply("answer")
        self.assertEqual(CodingAssistant(client).ask(" Explain lists ").text, "answer")
        messages = client.chat.call_args.args[0]
        self.assertEqual(messages[-1], {"role": "user", "content": "Explain lists"})
        self.assertIn("cannot inspect files", messages[0]["content"])

    def test_invalid_timeout(self):
        for value in (0, -1, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Settings(timeout_seconds=value)


class TerminalTests(unittest.TestCase):
    def run_cli(self, argv, reply=None, error=None):
        output, errors = io.StringIO(), io.StringIO()
        with patch("ai_agent.cli.OllamaClient") as client:
            client.return_value.chat.return_value = reply or ModelReply("Example code")
            client.return_value.chat.side_effect = error
            with redirect_stdout(output), redirect_stderr(errors):
                status = main(argv)
        return status, output.getvalue(), errors.getvalue()

    def test_prints_response(self):
        status, output, _ = self.run_cli(["Write a Python function"])
        self.assertEqual(status, 0)
        self.assertEqual(output, "Example code\n")

    def test_error_is_actionable_without_traceback(self):
        status, output, errors = self.run_cli(["hello"], error=ModelError("Open Ollama"))
        self.assertEqual(status, 1)
        self.assertEqual(output, "")
        self.assertIn("Error: Open Ollama", errors)
        self.assertNotIn("Traceback", errors)

    def test_truncation_is_reported(self):
        status, output, errors = self.run_cli(["hello"], ModelReply("Partial", True))
        self.assertEqual(status, 1)
        self.assertIn("Partial", output)
        self.assertIn("incomplete", errors)

    def test_piped_multiline_prompt(self):
        with patch("sys.stdin", io.StringIO("Explain this:\nprint(1)")):
            status, _, _ = self.run_cli([])
        self.assertEqual(status, 0)

    def test_blank_prompt_and_invalid_settings(self):
        for args in ([" "], ["hello", "--timeout", "nan"], ["hello", "--model", ""]):
            with self.subTest(args=args):
                status, _, errors = self.run_cli(args)
                self.assertEqual(status, 1)
                self.assertIn("Error:", errors)
