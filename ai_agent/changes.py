"""Reviewable file changes, backups, and explicit approval before saving."""

from dataclasses import dataclass
import difflib
import os
from pathlib import Path
import tempfile
import uuid

from .config import BACKUP_DIRECTORY, MAX_FILE_BYTES
from .validation import ValidationResult, validate
from .workspace import FileSnapshot, Workspace, WorkspaceError, is_link


@dataclass(frozen=True)
class ProposedChange:
    original: FileSnapshot
    explanation: str
    content: str
    validation: ValidationResult

    @property
    def changed(self) -> bool:
        return self.original.raw != self.original.encode(self.content)

    def diff(self) -> str:
        before = self.original.text.splitlines(keepends=True)
        after = self.content.splitlines(keepends=True)
        lines = difflib.unified_diff(
            before, after,
            fromfile=str(self.original.path) if self.original.raw is not None else "/dev/null",
            tofile=str(self.original.path),
        )
        # Preserve visibility of changes to the final newline.
        return "".join(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n"
                       for line in lines)


def save_change(workspace: Workspace, change: ProposedChange, *, approved: bool = False) -> Path | None:
    if not approved:
        raise WorkspaceError("Saving requires explicit approval after reviewing the proposal.")
    if change.validation.status != "passed":
        raise WorkspaceError("Saving is blocked because validation did not pass.")
    if validate(change.content, change.original.path.name).status != "passed":
        raise WorkspaceError("Validation no longer passes. Nothing was saved.")
    workspace.assert_unchanged(change.original)
    if not change.changed:
        return None
    data = change.original.encode(change.content)
    if len(data) > MAX_FILE_BYTES:
        raise WorkspaceError("Proposed content exceeds the file size limit.")
    backup = None
    if change.original.raw is not None:
        backup_root = workspace.root / BACKUP_DIRECTORY
        if backup_root.exists() or backup_root.is_symlink():
            if is_link(backup_root) or not backup_root.is_dir():
                raise WorkspaceError("Backup directory must be a regular directory inside the workspace.")
        else:
            backup_root.mkdir()
        backup = backup_root / f"{change.original.path.name}.{uuid.uuid4().hex}.bak"
        with backup.open("xb") as handle:
            handle.write(change.original.raw)
            handle.flush()
            os.fsync(handle.fileno())

    # Stage a complete replacement before committing it. A new destination uses
    # exclusive creation, so a file created during review cannot be overwritten.
    destination = change.original.path
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".ai-agent-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        workspace.assert_unchanged(change.original)
        if change.original.raw is None:
            # A hard link publishes the complete staged file without replacing an
            # existing destination. Removing the temporary name leaves one link.
            os.link(temporary, destination)
        else:
            os.chmod(temporary, destination.stat().st_mode)
            os.replace(temporary, destination)
        return backup
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
