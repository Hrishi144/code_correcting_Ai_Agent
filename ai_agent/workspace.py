"""Explicit workspace boundaries and immutable snapshots of selected files."""

from dataclasses import dataclass
import codecs
from pathlib import Path
import stat

from .config import MAX_FILE_BYTES, PROTECTED_DIRECTORIES, SUPPORTED_SUFFIXES


class WorkspaceError(ValueError):
    """A selected file cannot be accessed under the workspace policy."""


def is_link(path: Path) -> bool:
    """Include Windows junctions and other reparse points, not just symlinks."""
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


@dataclass(frozen=True)
class FileSnapshot:
    path: Path
    raw: bytes | None
    text: str
    identity: tuple[int, int, int, int] | None

    def encode(self, content: str) -> bytes:
        """Keep UTF-8 BOM and consistent CRLF line endings for existing files."""
        content = content.replace("\r\n", "\n")
        if self.raw is not None and b"\r\n" in self.raw:
            if b"\n" not in self.raw.replace(b"\r\n", b""):
                content = content.replace("\n", "\r\n")
        encoded = content.encode("utf-8")
        if self.raw is not None and self.raw.startswith(codecs.BOM_UTF8):
            encoded = codecs.BOM_UTF8 + encoded
        return encoded


class Workspace:
    def __init__(self, root: str | Path) -> None:
        selected = Path(root).expanduser().absolute()
        # Check the selected root as well, so protected folders cannot be used
        # as a new workspace to bypass the restrictions on relative paths.
        for part in selected.parts[1:]:
            self._check_part(part)
        self.root = selected.resolve(strict=True)
        if not self.root.is_dir():
            raise WorkspaceError("Workspace must be an existing directory.")
        for part in self.root.parts[1:]:
            self._check_part(part)

    @staticmethod
    def _check_part(part: str) -> None:
        if (part in {".", ".."} or part.startswith(".")
                or part.casefold() in PROTECTED_DIRECTORIES):
            raise WorkspaceError("Hidden paths and protected directories are not accessible.")
        if any(char in part for char in ':*?"<>|\x00') or part.endswith((" ", ".")):
            raise WorkspaceError("Ambiguous or special file paths are not supported.")
        if part.split(".")[0].upper() in {
            "CON", "PRN", "AUX", "NUL",
            *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10)),
        }:
            raise WorkspaceError("Reserved device names are not supported.")

    def resolve(self, selection: str | Path) -> Path:
        path = Path(selection)
        if path.drive and not path.is_absolute():
            raise WorkspaceError("Drive-relative paths are not supported.")
        candidate = path if path.is_absolute() else self.root / path
        try:
            relative = candidate.relative_to(self.root)
        except ValueError as exc:
            raise WorkspaceError("Selected file must be inside the approved workspace.") from exc
        if not relative.parts:
            raise WorkspaceError("Select a file, not the workspace directory.")
        current = self.root
        if current.resolve(strict=True) != current:
            raise WorkspaceError("Workspace location changed; select it again.")
        for part in relative.parts:
            self._check_part(part)
            current = current / part
            if current.exists() or current.is_symlink():
                if is_link(current):
                    raise WorkspaceError("Symbolic links, junctions, and reparse points are not accessible.")
        if not current.resolve().is_relative_to(self.root):
            raise WorkspaceError("Selected file escapes the approved workspace.")
        if current.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise WorkspaceError("Select a .py, .json, or .java file.")
        if not current.parent.is_dir():
            raise WorkspaceError("The destination directory must already exist.")
        return current

    def snapshot(self, selection: str | Path, *, new: bool = False) -> FileSnapshot:
        path = self.resolve(selection)
        if new:
            if path.exists():
                raise WorkspaceError("Output already exists. Use --file to propose an edit instead.")
            return FileSnapshot(path, None, "", None)
        before = path.stat()
        if not stat.S_ISREG(before.st_mode) or before.st_nlink > 1:
            raise WorkspaceError("Select a regular file with no hard-link aliases.")
        if before.st_size > MAX_FILE_BYTES:
            raise WorkspaceError(f"File exceeds the {MAX_FILE_BYTES}-byte read limit; select a smaller file.")
        with path.open("rb") as handle:
            raw = handle.read(MAX_FILE_BYTES + 1)
        after = path.stat()
        identity = (after.st_dev, after.st_ino, after.st_mtime_ns, after.st_size)
        if ((before.st_dev, before.st_ino, before.st_mtime_ns, before.st_size) != identity
                or len(raw) > MAX_FILE_BYTES or self.resolve(selection) != path):
            raise WorkspaceError("File changed while being read. Try again.")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise WorkspaceError("Only UTF-8 text files are supported.") from exc
        if "\x00" in text:
            raise WorkspaceError("Binary files are not supported.")
        return FileSnapshot(path, raw, text.replace("\r\n", "\n"), identity)

    def assert_unchanged(self, snapshot: FileSnapshot) -> None:
        current = self.snapshot(snapshot.path, new=snapshot.raw is None)
        if current.raw != snapshot.raw or current.identity != snapshot.identity:
            raise WorkspaceError("Original file changed during review. Inspect it again before saving.")
