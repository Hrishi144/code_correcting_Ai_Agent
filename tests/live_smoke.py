"""Opt-in integration checks. Explicitly contacts the installed local model.

Run: python -m unittest discover -s tests -p live_smoke.py -v
Generated programs are validated but never executed or saved to project files.
"""

import ast
import json
from pathlib import Path
import tempfile
import unittest

from ai_agent.assistant import CodingAssistant
from ai_agent.config import Settings
from ai_agent.ollama_client import OllamaClient
from ai_agent.validation import validate
from ai_agent.workspace import Workspace


class LiveSmokeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="agent-live-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = Workspace(self.root)
        self.assistant = CodingAssistant(OllamaClient(Settings()))

    def test_repairs_python_json_java(self):
        examples = (
            ("sample.py", "def is_even(n)\n    return n % 2 == 0\n", "Fix only the missing colon."),
            ("data.json", '{"ready": true,}', "Remove the invalid trailing comma; preserve the ready value."),
            ("Sample.java", "public class Sample { public static int value() { return 1 } }\n",
             "Fix the missing semicolon. Preserve the Sample class and value method."),
        )
        for name, content, request in examples:
            with self.subTest(file=name):
                path = self.root / name
                path.write_text(content, encoding="utf-8")
                snapshot = self.workspace.snapshot(name)
                checks = validate(snapshot.text, name)
                self.assertEqual(checks.status, "failed", checks.detail)
                proposal = self.assistant.propose(snapshot, checks, request, operation="fix")
                self.assertEqual(proposal.validation.status, "passed", proposal.validation.detail)
                self.assertTrue(proposal.changed)
                self.assertEqual(path.read_bytes(), snapshot.raw)
                if name.endswith(".json"):
                    self.assertEqual(json.loads(proposal.content), {"ready": True})
                elif name.endswith(".py"):
                    tree = ast.parse(proposal.content)
                    self.assertEqual(tree.body[0].name, "is_even")
                else:
                    self.assertIn("class Sample", proposal.content)
                    self.assertIn("return 1;", proposal.content)

    def test_generates_python_json_java(self):
        examples = (
            ("add.py", "Create only a Python function add(a, b) that returns a + b."),
            ("new.json", 'Create a JSON object with exactly one field: "ready" set to true.'),
            ("Hello.java", "Create public class Hello with public static int value() returning 42. No main method."),
        )
        for name, request in examples:
            with self.subTest(file=name):
                snapshot = self.workspace.snapshot(name, new=True)
                proposal = self.assistant.propose(snapshot, None, request, operation="code")
                self.assertEqual(proposal.validation.status, "passed", proposal.validation.detail)
                self.assertFalse(snapshot.path.exists())
                if name.endswith(".json"):
                    self.assertEqual(json.loads(proposal.content), {"ready": True})
                elif name.endswith(".py"):
                    self.assertEqual(ast.parse(proposal.content).body[0].name, "add")
                else:
                    self.assertIn("class Hello", proposal.content)
                    self.assertIn("return 42;", proposal.content)

    def test_inspects_selected_file(self):
        path = self.root / "inspect.py"
        path.write_text("def value()\n    return 1\n", encoding="utf-8")
        snapshot = self.workspace.snapshot(path.name)
        reply = self.assistant.inspect(snapshot, validate(snapshot.text, path.name))
        self.assertFalse(reply.truncated)
        self.assertTrue(reply.text)
        self.assertIn("colon", reply.text.lower())
        self.assertEqual(path.read_bytes(), snapshot.raw)
