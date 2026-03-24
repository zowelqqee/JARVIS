"""Transport-level retryability contract for OpenAI Responses."""

from __future__ import annotations

import io
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from jarvis_error import ErrorCode, JarvisError
from qa.openai_responses_transport import OpenAIResponsesTransport


class OpenAIResponsesTransportTests(unittest.TestCase):
    """Lock which transport failures are marked retryable."""

    def setUp(self) -> None:
        self.transport = OpenAIResponsesTransport()
        self.request_payload = {
            "model": "gpt-5-nano",
            "metadata": {
                "correlation_id": "corr-test",
            },
        }

    def test_timeout_is_marked_retryable(self) -> None:
        with patch("urllib.request.urlopen", side_effect=TimeoutError("read timed out")), self.assertRaises(JarvisError) as captured:
            self.transport.create_response(self.request_payload, api_key="test-key")

        self.assertEqual(getattr(captured.exception.code, "value", ""), ErrorCode.ANSWER_GENERATION_FAILED.value)
        self.assertTrue(bool((captured.exception.details or {}).get("retryable")))
        self.assertEqual((captured.exception.details or {}).get("correlation_id"), "corr-test")

    def test_http_429_is_marked_retryable_and_carries_request_id(self) -> None:
        http_error = urllib.error.HTTPError(
            url="https://api.openai.com/v1/responses",
            code=429,
            msg="Too Many Requests",
            hdrs={"x-request-id": "req_429"},
            fp=io.BytesIO(b'{"error":"rate_limited"}'),
        )

        with patch("urllib.request.urlopen", side_effect=http_error), self.assertRaises(JarvisError) as captured:
            self.transport.create_response(self.request_payload, api_key="test-key")

        self.assertEqual(getattr(captured.exception.code, "value", ""), ErrorCode.ANSWER_GENERATION_FAILED.value)
        self.assertEqual((captured.exception.details or {}).get("status_code"), 429)
        self.assertTrue(bool((captured.exception.details or {}).get("retryable")))
        self.assertEqual((captured.exception.details or {}).get("request_id"), "req_429")


if __name__ == "__main__":
    unittest.main()
