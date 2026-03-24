"""Unit tests for the OpenAI Responses transport adapter."""

from __future__ import annotations

import ssl
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from jarvis_error import ErrorCode, JarvisError
from qa.openai_responses_transport import OpenAIResponsesTransport, _ca_bundle_path


class _FakeResponse:
    def __init__(self, body: str) -> None:
        self._body = body.encode("utf-8")

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self._body


class OpenAIResponsesTransportTests(unittest.TestCase):
    """Lock TLS bundle selection and error handling for live provider calls."""

    def test_ca_bundle_path_prefers_explicit_env(self) -> None:
        bundle_path = _ca_bundle_path(
            {
                "JARVIS_QA_OPENAI_CA_BUNDLE": "/tmp/jarvis.pem",
                "SSL_CERT_FILE": "/tmp/python.pem",
                "REQUESTS_CA_BUNDLE": "/tmp/requests.pem",
            }
        )

        self.assertEqual(bundle_path, "/tmp/jarvis.pem")

    def test_ca_bundle_path_falls_back_to_certifi(self) -> None:
        bundle_path = _ca_bundle_path({})

        self.assertTrue(bundle_path)
        self.assertTrue(bundle_path.endswith(".pem"))

    def test_transport_passes_ssl_context_to_urlopen(self) -> None:
        transport = OpenAIResponsesTransport()

        with patch("qa.openai_responses_transport.urllib.request.urlopen", return_value=_FakeResponse("{}")) as mocked_urlopen:
            payload = transport.create_response({}, api_key="test-key")

        self.assertEqual(payload, {})
        self.assertIn("context", mocked_urlopen.call_args.kwargs)
        self.assertIsInstance(mocked_urlopen.call_args.kwargs["context"], ssl.SSLContext)

    def test_transport_wraps_ssl_cert_error_with_actionable_message(self) -> None:
        transport = OpenAIResponsesTransport()
        ssl_error = ssl.SSLCertVerificationError("unable to get local issuer certificate")
        url_error = urllib.error.URLError(ssl_error)

        with patch("qa.openai_responses_transport.urllib.request.urlopen", side_effect=url_error):
            with self.assertRaises(JarvisError) as captured:
                transport.create_response({}, api_key="test-key")

        self.assertEqual(getattr(captured.exception.code, "value", ""), ErrorCode.ANSWER_GENERATION_FAILED.value)
        self.assertIn("TLS certificate verification", str(captured.exception.message))
        self.assertIn("SSL_CERT_FILE", str(captured.exception.message))


if __name__ == "__main__":
    unittest.main()
