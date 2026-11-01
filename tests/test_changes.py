from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ai_agent.changes import ProposedChange, save_change
from ai_agent.validation import validate, ValidationResult
from ai_agent.workspace import Workspace, WorkspaceError


class ChangeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="agent-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = Workspace(self.root)
        self.file = self.root / "sample.py"
        self.file.write_bytes(b"value = 1\r\n")
        self.snapshot = self.workspace.snapshot("sample.py")
        self.change = ProposedChange(self.snapshot, "Update value", "value = 2\n", validate("value = 2\n", "sample.py"))

    def test_approval_is_required_and_preview_does_not_write(self):
        self.assertIn("-value = 1", self.change.diff())
        self.assertIn("+value = 2", self.change.diff())
        with self.assertRaises(WorkspaceError):
            save_change(self.workspace, self.change)
        self.assertEqual(self.file.read_bytes(), self.snapshot.raw)
        self.assertFalse((self.root / ".ai_agent_backups").exists())

    def test_approved_save_preserves_original_backup_and_newlines(self):
        backup = save_change(self.workspace, self.change, approved=True)
        self.assertEqual(backup.read_bytes(), self.snapshot.raw)
        self.assertEqual(self.file.read_bytes(), b"value = 2\r\n")
        self.assertEqual(list(self.root.glob(".ai-agent-*")), [])

    def test_changed_original_is_not_overwritten(self):
        self.file.write_bytes(b"external = 3\n")
        with self.assertRaises(WorkspaceError):
            save_change(self.workspace, self.change, approved=True)
        self.assertEqual(self.file.read_bytes(), b"external = 3\n")

    def test_invalid_or_unverified_proposal_cannot_save(self):
        for check in (ValidationResult("failed", "invalid"), ValidationResult("unavailable", "missing")):
            change = ProposedChange(self.snapshot, "test", "value = 2", check)
            with self.subTest(check=check), self.assertRaises(WorkspaceError):
                save_change(self.workspace, change, approved=True)
        forged = ProposedChange(self.snapshot, "test", "def broken(", ValidationResult("passed", "fake"))
        with self.assertRaises(WorkspaceError):
            save_change(self.workspace, forged, approved=True)

    def test_new_file_save_and_collision(self):
        snapshot = self.workspace.snapshot("new.json", new=True)
        change = ProposedChange(snapshot, "create", '{"ready":true}', validate('{"ready":true}', "new.json"))
        self.assertIsNone(save_change(self.workspace, change, approved=True))
        self.assertEqual(snapshot.path.read_text(), '{"ready":true}')
        with self.assertRaises(WorkspaceError):
            save_change(self.workspace, change, approved=True)

    def test_failed_replace_keeps_original_and_backup(self):
        with patch("ai_agent.changes.os.replace", side_effect=OSError("locked")):
            with self.assertRaises(OSError):
                save_change(self.workspace, self.change, approved=True)
        self.assertEqual(self.file.read_bytes(), self.snapshot.raw)
        backups = list((self.root / ".ai_agent_backups").iterdir())
        self.assertEqual(backups[0].read_bytes(), self.snapshot.raw)
        self.assertEqual(list(self.root.glob(".ai-agent-*")), [])

    def test_changed_during_staging_is_not_overwritten(self):
        original_check = self.workspace.assert_unchanged
        calls = 0
        def mutate_before_second_check(snapshot):
            nonlocal calls
            calls += 1
            if calls == 2:
                self.file.write_bytes(b"other = 99")
            return original_check(snapshot)
        with patch.object(self.workspace, "assert_unchanged", side_effect=mutate_before_second_check):
            with self.assertRaises(WorkspaceError):
                save_change(self.workspace, self.change, approved=True)
        self.assertEqual(self.file.read_bytes(), b"other = 99")

    def test_diff_marks_final_newline(self):
        change = ProposedChange(self.snapshot, "newline", "value = 1", validate("value = 1", "sample.py"))
        self.assertIn("No newline at end of file", change.diff())
