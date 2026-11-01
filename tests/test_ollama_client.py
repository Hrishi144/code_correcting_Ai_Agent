import io
import json
import unittest
from urllib.error import HTTPError, URLError
from unittest.mock import Mock

from ai_agent.config import Settings
from ai_agent.ollama_client import ModelError, OllamaClient


class OllamaClientTests(unittest.TestCase):
    def setUp(self):
        self.client = OllamaClient(Settings())
        self.client._opener = Mock()

    def respond(self, body):
        self.client._opener.open.return_value = io.BytesIO(body)

    def test_local_request_and_response(self):
        self.respond(json.dumps({"message": {"content": "print('hello')"}, "done": True}).encode())
        reply = self.client.chat([{"role": "user", "content": "Say hello"}])
        self.assertEqual(reply.text, "print('hello')")
        request = self.client._opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/chat")
        payload = json.loads(request.data)
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["model"], "qwen2.5-coder:7b")
        self.assertEqual(payload["options"]["num_ctx"], 4096)

    def test_bad_responses(self):
        for body in (b"bad json", b"[]", b"{}", b'{"error":"failed"}',
                     b'{"message":{"content":""},"done":true}',
                     b'{"message":{"content":"partial"},"done":false}'):
            with self.subTest(body=body), self.assertRaises(ModelError):
                self.respond(body)
                self.client.chat([])

    def test_connection_and_timeout_errors(self):
        for error, expected in ((URLError("refused"), "Cannot connect"),
                                (TimeoutError(), "timed out"),
                                (URLError(TimeoutError()), "timed out"),
                                (ConnectionResetError(), "interrupted")):
            with self.subTest(error=error), self.assertRaisesRegex(ModelError, expected):
                self.client._opener.open.side_effect = error
                self.client.chat([])

    def test_missing_model_and_server_error(self):
        for code, body, expected in ((404, b'{"error":"model abc not found"}', "ollama list"),
                                     (500, b"failure", "HTTP 500")):
            with self.subTest(code=code), self.assertRaisesRegex(ModelError, expected):
                self.client._opener.open.side_effect = HTTPError(
                    "http://127.0.0.1:11434/api/chat", code, "Error", {}, io.BytesIO(body)
                )
                self.client.chat([])

    def test_output_limit_is_preserved(self):
        self.respond(b'{"message":{"content":"partial"},"done":true,"done_reason":"length"}')
        self.assertTrue(self.client.chat([]).truncated)

    def test_structured_schema_is_sent(self):
        self.respond(b'{"message":{"content":"{}"},"done":true}')
        self.client.chat([], response_schema={"type": "object"})
        payload = json.loads(self.client._opener.open.call_args.args[0].data)
        self.assertEqual(payload["format"], {"type": "object"})

    def test_oversized_request_is_rejected_before_network(self):
        with self.assertRaisesRegex(ModelError, "estimated input 5004, available 2816"):
            self.client.chat([{"role": "user", "content": "x" * 5000}])
        self.client._opener.open.assert_not_called()

    def test_outer_json_escaping_does_not_reject_message_text(self):
        # Code with quotes, backslashes and newlines expands on the wire. Those
        # extra JSON escapes are removed before the model receives the message.
        messages = [{"role": "user", "content": '\\"\n' * 500}]
        self.assertGreater(len(json.dumps(messages).encode("utf-8")), 2816)
        self.respond(b'{"message":{"content":"ok"},"done":true}')
        self.client.chat(messages)
        sent = json.loads(self.client._opener.open.call_args.args[0].data)
        self.assertEqual(sent["messages"], messages)
        self.assertEqual(sent["options"]["num_ctx"], 4096)
        self.assertEqual(sent["options"]["num_predict"], 1024)

    def test_budget_boundary_and_schema_are_counted(self):
        messages = [{"role": "user", "content": "x" * 2812}]
        self.respond(b'{"message":{"content":"ok"},"done":true}')
        self.client.chat(messages)  # Exactly 2816 including the role text.
        self.client._opener.reset_mock()
        with self.assertRaisesRegex(ModelError, "available 2816"):
            self.client.chat(messages, response_schema={"type": "object"})
        self.client._opener.open.assert_not_called()

    def test_multibyte_input_counts_utf8_bytes(self):
        with self.assertRaisesRegex(ModelError, "estimated input 3604"):
            self.client.chat([{"role": "user", "content": "é" * 1800}])
        self.client._opener.open.assert_not_called()

    def test_reported_3614_byte_request_can_use_explicit_larger_context(self):
        messages = [{"role": "user", "content": "x" * 3610}]
        with self.assertRaisesRegex(ModelError, "estimated input 3614, available 2816") as error:
            self.client.chat(messages)
        self.assertIn("--context 8192", str(error.exception))
        self.client._opener.open.assert_not_called()

        self.client = OllamaClient(Settings(context_tokens=8192))
        self.client._opener = Mock()
        self.respond(b'{"message":{"content":"ok"},"done":true}')
        self.assertEqual(self.client.chat(messages).text, "ok")
        payload = json.loads(self.client._opener.open.call_args.args[0].data)
        self.assertEqual(payload["options"]["num_ctx"], 8192)
        self.assertEqual(payload["options"]["num_predict"], 1024)
        self.assertEqual(payload["messages"], messages)

        self.client._opener.reset_mock()
        with self.assertRaisesRegex(ModelError, "--context 16384"):
            self.client.chat([{"role": "user", "content": "x" * 7000}])
        self.client._opener.open.assert_not_called()
