"""Configuration shared by the terminal and model client."""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Settings:
    model: str = "qwen2.5-coder:3b"
    timeout_seconds: float = 120.0
    context_tokens: int = 4096
    output_tokens: int = 1024

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("Model name cannot be empty.")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("Timeout must be a positive, finite number of seconds.")
        if self.context_tokens <= 0 or self.output_tokens <= 0:
            raise ValueError("Token limits must be positive.")


OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"

# File operations deliberately support small, explicitly selected text files.
SUPPORTED_SUFFIXES = frozenset({".py", ".json", ".java"})
PROTECTED_DIRECTORIES = frozenset({"node_modules", "venv", "__pycache__"})
MAX_FILE_BYTES = 16_384
COMPILER_TIMEOUT_SECONDS = 20
BACKUP_DIRECTORY = ".ai_agent_backups"
