"""Local Ollama transport; no terminal interaction or file editing."""

from dataclasses import dataclass
from http.client import HTTPException
import json
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from .config import OLLAMA_CHAT_URL, TEMPLATE_RESERVE_TOKENS, Settings


class ModelError(Exception):
    """An actionable failure while requesting a model response."""


@dataclass(frozen=True)
class ModelReply:
    text: str
    truncated: bool = False


class OllamaClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        # Local prompts should not pass through an environment-configured proxy.
        self._opener = build_opener(ProxyHandler({}))

    def chat(self, messages: list[dict[str, str]], *, response_schema: dict | None = None) -> ModelReply:
        # Count the text supplied to the model, not outer HTTP JSON escaping.
        # One UTF-8 byte per estimated token remains intentionally conservative;
        # the reserve covers chat-template overhead. Never trim source to fit.
        estimated_input = sum(
            len(message["role"].encode("utf-8")) + len(message["content"].encode("utf-8"))
            for message in messages
        )
        if response_schema is not None:
            estimated_input += len(json.dumps(response_schema, ensure_ascii=False).encode("utf-8"))
        input_budget = self.settings.context_tokens - self.settings.output_tokens - TEMPLATE_RESERVE_TOKENS
        if estimated_input > input_budget:
            required_context = estimated_input + self.settings.output_tokens + TEMPLATE_RESERVE_TOKENS
            suggested_context = 1 << (required_context - 1).bit_length()
            raise ModelError(
                f"Request exceeds the conservative context budget: estimated input {estimated_input}, "
                f"available {input_budget} (byte-based estimate, not an exact token count). "
                f"Context: {self.settings.context_tokens}; output reserve: {self.settings.output_tokens}; "
                f"template reserve: {TEMPLATE_RESERVE_TOKENS}. "
                f"Rerun with --context {suggested_context} if your model and available memory support it, "
                "or select a smaller file or shorten the instructions. "
                "No content was silently truncated."
            )
        payload = {
            "model": self.settings.model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_ctx": self.settings.context_tokens,
                "num_predict": self.settings.output_tokens,
                "temperature": 0,
            },
        }
        if response_schema is not None:
            payload["format"] = response_schema
        request = Request(
            OLLAMA_CHAT_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._opener.open(
                request, timeout=self.settings.timeout_seconds
            ) as response:
                raw = response.read()
        except HTTPError as exc:
            with exc:
                detail = exc.read().decode("utf-8", errors="replace")
            if exc.code == 404 and "model" in detail.lower() and "not found" in detail.lower():
                raise ModelError(
                    f"Model '{self.settings.model}' is unavailable. Check 'ollama list' "
                    "and select an installed model with --model."
                ) from exc
            raise ModelError(
                f"Ollama returned HTTP {exc.code}. Check the Ollama server and model."
            ) from exc
        except TimeoutError as exc:
            raise ModelError("Ollama timed out. Try again or increase --timeout.") from exc
        except URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise ModelError("Ollama timed out. Try again or increase --timeout.") from exc
            raise ModelError(
                "Cannot connect to local Ollama at 127.0.0.1:11434. "
                "Open Ollama or run 'ollama serve', then try again."
            ) from exc
        except (OSError, HTTPException) as exc:
            raise ModelError("The Ollama connection was interrupted. Try again.") from exc

        try:
            result = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            raise ModelError("Ollama returned invalid JSON. Check the server and try again.") from exc
        if not isinstance(result, dict):
            raise ModelError("Ollama returned an unexpected response format.")
        if result.get("error"):
            raise ModelError("Ollama could not generate a response. Check its server logs.")
        message = result.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise ModelError("Ollama returned no response text. Try again.")
        if result.get("done") is not True:
            raise ModelError("Ollama returned an incomplete response. Try again.")
        return ModelReply(content.strip(), result.get("done_reason") == "length")
