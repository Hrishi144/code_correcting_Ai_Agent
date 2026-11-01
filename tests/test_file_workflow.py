from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from ai_agent.assistant import CodingAssistant
from ai_agent.cli import main, safe_text
from ai_agent.ollama_client import ModelError, ModelReply
from ai_agent.validation import validate
from ai_agent.workspace import Workspace


class TerminalBuffer(io.StringIO):
    def isatty(self):
        return True


class FileWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="agent-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.file = self.root / "sample.py"
        self.file.write_text("def value()\n    return 1\n", encoding="utf-8")
        self.source = self.file.read_bytes()
        self.reply = ModelReply(json.dumps({"explanation": "Add missing colon", "content": "def value():\n    return 1\n"}))

    def invoke(self, command, *, reply=None, approval="", interactive=True):
        output = TerminalBuffer() if interactive else io.StringIO()
        errors = io.StringIO()
        with patch("ai_agent.cli.OllamaClient") as client, \
                patch("sys.stdin", TerminalBuffer() if interactive else io.StringIO()), \
                patch("builtins.input", return_value=approval) as input_mock, \
                redirect_stdout(output), redirect_stderr(errors):
            client.return_value.chat.return_value = reply or self.reply
            status = main(command + ["--workspace", str(self.root)])
        return status, output.getvalue(), errors.getvalue(), input_mock, client

    def test_reject_and_approve_fix(self):
        status, output, _, _, _ = self.invoke(["fix", "--file", "sample.py"])
        self.assertEqual(status, 0)
        self.assertIn("Rejected", output)
        self.assertEqual(self.file.read_bytes(), self.source)
        status, output, _, _, _ = self.invoke(["fix", "--file", "sample.py"], approval="save")
        self.assertEqual(status, 0)
        self.assertIn("Saved:", output)
        self.assertIn("def value():", self.file.read_text())
        self.assertEqual(next((self.root / ".ai_agent_backups").iterdir()).read_bytes(), self.source)

    def test_noninteractive_input_cannot_approve(self):
        status, output, _, prompt, _ = self.invoke(["fix", "--file", "sample.py"], approval="save", interactive=False)
        self.assertEqual(status, 0)
        self.assertIn("Preview only", output)
        prompt.assert_not_called()
        self.assertEqual(self.file.read_bytes(), self.source)

    def test_validation_failure_cannot_approve(self):
        bad = ModelReply(json.dumps({"explanation": "bad", "content": "def still_broken("}))
        status, output, _, prompt, _ = self.invoke(["fix", "--file", "sample.py"], reply=bad, approval="save")
        self.assertEqual(status, 1)
        self.assertIn("Saving blocked", output)
        prompt.assert_not_called()
        self.assertEqual(self.file.read_bytes(), self.source)

    def test_inspect_never_asks_to_save(self):
        status, output, _, prompt, _ = self.invoke(["inspect", "--file", "sample.py"], reply=ModelReply("Missing colon"))
        self.assertEqual(status, 1)  # Existing source failed syntax validation.
        self.assertIn("Missing colon", output)
        prompt.assert_not_called()
        self.assertEqual(self.file.read_bytes(), self.source)

    def test_create_new_file(self):
        reply = ModelReply(json.dumps({"explanation": "New data", "content": '{"ready":true}'}))
        status, output, _, _, _ = self.invoke(
            ["code", "--output", "new.json", "--request", "Create readiness data"], reply=reply, approval="save")
        self.assertEqual(status, 0, output)
        self.assertEqual(json.loads((self.root / "new.json").read_text()), {"ready": True})

    def test_access_denied_before_model_call(self):
        status, _, _, prompt, client = self.invoke(["fix", "--file", "../outside.py"])
        self.assertEqual(status, 1)
        prompt.assert_not_called()
        client.return_value.chat.assert_not_called()

    def test_structured_proposals_reject_extra_paths_invalid_json_and_truncation(self):
        snapshot = Workspace(self.root).snapshot("sample.py")
        for reply in (ModelReply("not JSON"), ModelReply("[]"), ModelReply('{"explanation":"x","content":"x=1","path":"outside.py"}'),
                      ModelReply('{"explanation":"x","content":""}'), ModelReply("partial", True)):
            client = Mock()
            client.chat.return_value = reply
            with self.subTest(reply=reply), self.assertRaises(ModelError):
                CodingAssistant(client).propose(snapshot, validate(snapshot.text, "sample.py"), "fix", operation="fix")

    def test_terminal_control_characters_are_visible(self):
        self.assertEqual(safe_text("a\x1b[2J\u202eb"), "a\\u001b[2J\\u202eb")

    def test_empty_output_path_is_rejected_before_model_call(self):
        status, _, _, prompt, client = self.invoke(["code", "--output", "", "--request", "Create code"])
        self.assertEqual(status, 1)
        prompt.assert_not_called()
        client.return_value.chat.assert_not_called()
