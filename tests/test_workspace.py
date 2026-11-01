import codecs
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ai_agent.config import MAX_FILE_BYTES
from ai_agent.workspace import Workspace, WorkspaceError


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="agent-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = Workspace(self.root)
        self.file = self.root / "sample.py"
        self.file.write_text("value = 1\n", encoding="utf-8")

    def test_reads_only_selected_file(self):
        (self.root / "other.py").write_bytes(b"\xff")
        snapshot = self.workspace.snapshot("sample.py")
        self.assertEqual(snapshot.text, "value = 1\n")

    def test_rejects_escape_protected_and_unsupported_paths(self):
        for selection in ("../escape.py", str(self.root.parent / "outside.py"),
                          ".git/config.json", ".aws/credentials.json", "node_modules/file.py",
                          "venv/file.py", "sample.txt", "sample.py:stream", "NUL.py"):
            with self.subTest(selection=selection), self.assertRaises(WorkspaceError):
                self.workspace.resolve(selection)

    def test_protected_workspace_cannot_bypass_policy(self):
        directory = self.root / ".git"
        directory.mkdir()
        with self.assertRaises(WorkspaceError):
            Workspace(directory)

    def test_rejects_large_and_non_utf8_files(self):
        for raw in (b"a" * (MAX_FILE_BYTES + 1), b"\xff", b"a\x00b"):
            self.file.write_bytes(raw)
            with self.subTest(raw=raw[:10]), self.assertRaises(WorkspaceError):
                self.workspace.snapshot("sample.py")

    def test_preserves_bom_and_crlf(self):
        raw = codecs.BOM_UTF8 + b"x = 1\r\n"
        self.file.write_bytes(raw)
        snapshot = self.workspace.snapshot("sample.py")
        self.assertEqual(snapshot.text, "x = 1\n")
        self.assertEqual(snapshot.encode("x = 2\n"), codecs.BOM_UTF8 + b"x = 2\r\n")

    def test_new_file_refuses_existing_destination(self):
        with self.assertRaises(WorkspaceError):
            self.workspace.snapshot("sample.py", new=True)
        self.assertIsNone(self.workspace.snapshot("new.py", new=True).raw)

    def test_detects_changed_content_and_new_destination(self):
        snapshot = self.workspace.snapshot("sample.py")
        self.file.write_text("value = 2\n", encoding="utf-8")
        with self.assertRaisesRegex(WorkspaceError, "changed"):
            self.workspace.assert_unchanged(snapshot)
        new = self.workspace.snapshot("new.py", new=True)
        new.path.write_text("x = 1", encoding="utf-8")
        with self.assertRaises(WorkspaceError):
            self.workspace.assert_unchanged(new)

    def test_rejects_link_components(self):
        with patch("ai_agent.workspace.is_link", return_value=True):
            with self.assertRaisesRegex(WorkspaceError, "links"):
                self.workspace.snapshot("sample.py")

    def test_rejects_real_symlink(self):
        target = self.root / "alias.py"
        try:
            target.symlink_to(self.file)
        except OSError:
            self.skipTest("Creating symlinks is not permitted on this host")
        with self.assertRaises(WorkspaceError):
            self.workspace.snapshot("alias.py")

    def test_rejects_hardlink(self):
        alias = self.root / "alias.py"
        os.link(self.file, alias)
        with self.assertRaises(WorkspaceError):
            self.workspace.snapshot("sample.py")
