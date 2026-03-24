"""Future-facing LLM backend seam tests."""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from jarvis_error import ErrorCode, JarvisError
from qa.answer_backend import AnswerBackendKind
from qa.answer_config import AnswerBackendConfig, LlmBackendConfig
from qa.grounding import build_grounding_bundle
from qa.llm_backend import LlmAnswerBackend
from qa.llm_provider import LlmProviderKind
from qa.openai_responses_provider import ANSWER_SCHEMA_VERSION, OpenAIResponsesProvider
from question_request import QuestionRequest, QuestionType


class _FakeTransport:
    def __init__(self, response_payload: dict | None = None, error: Exception | None = None) -> None:
        self.response_payload = response_payload or {}
        self.error = error
        self.calls: list[dict] = []

    def create_response(self, request_payload: dict, *, api_key: str, api_base: str | None = None, timeout_seconds: float = 30.0) -> dict:
        self.calls.append(
            {
                "request_payload": request_payload,
                "api_key": api_key,
                "api_base": api_base,
                "timeout_seconds": timeout_seconds,
            }
        )
        if self.error is not None:
            raise self.error
        return self.response_payload


class LlmBackendTests(unittest.TestCase):
    """Lock the disabled-by-default model backend seam."""

    def setUp(self) -> None:
        self.question = QuestionRequest(
            raw_input="What can you do?",
            question_type=QuestionType.CAPABILITIES,
            scope="capabilities",
            confidence=0.95,
        )
        self.grounding_bundle = build_grounding_bundle(self.question)

    def test_openai_provider_builds_grounded_responses_payload(self) -> None:
        provider = OpenAIResponsesProvider()
        config = AnswerBackendConfig(
            backend_kind=AnswerBackendKind.LLM,
            llm=LlmBackendConfig(enabled=True, provider=LlmProviderKind.OPENAI_RESPONSES, model="gpt-4o-mini"),
        )

        payload = provider.build_request_payload(self.question, grounding_bundle=self.grounding_bundle, config=config)

        self.assertEqual(payload.get("model"), "gpt-4o-mini")
        self.assertIn("instructions", payload)
        self.assertIn("input", payload)
        self.assertEqual((((payload.get("text") or {}).get("format") or {}).get("type")), "json_schema")
        input_items = payload.get("input") or []
        self.assertEqual(len(input_items), 1)
        content_items = input_items[0].get("content") or []
        self.assertEqual(content_items[0].get("type"), "input_text")
        self.assertIn("Allowed local sources", content_items[0].get("text", ""))
        self.assertEqual((payload.get("metadata") or {}).get("provider"), "openai_responses")
        self.assertEqual((payload.get("metadata") or {}).get("source_count"), str(len(self.grounding_bundle.source_paths)))
        self.assertTrue(all(isinstance(value, str) for value in (payload.get("metadata") or {}).values()))

    def test_openai_provider_parses_structured_response_into_answer_result(self) -> None:
        fake_transport = _FakeTransport(
            response_payload={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "schema_version": ANSWER_SCHEMA_VERSION,
                                        "answer_text": "I support open_app and grounded question answering.",
                                        "source_attributions": [
                                            {
                                                "source": self.grounding_bundle.source_paths[0],
                                                "support": "Capability catalog grounds supported action coverage.",
                                            },
                                            {
                                                "source": self.grounding_bundle.source_paths[1],
                                                "support": "Product rules ground command and safety boundaries.",
                                            },
                                        ],
                                        "warning": "",
                                        "grounded": True,
                                    }
                                ),
                            }
                        ],
                    }
                ],
            }
        )
        provider = OpenAIResponsesProvider(transport=fake_transport)
        config = AnswerBackendConfig(
            backend_kind=AnswerBackendKind.LLM,
            llm=LlmBackendConfig(
                enabled=True,
                provider=LlmProviderKind.OPENAI_RESPONSES,
                model="gpt-4o-mini",
                api_key_env="TEST_OPENAI_KEY",
            ),
        )

        with patch.dict(os.environ, {"TEST_OPENAI_KEY": "test-key"}, clear=False):
            result = provider.answer(self.question, grounding_bundle=self.grounding_bundle, config=config)

        self.assertIn("open_app", result.answer_text)
        self.assertEqual(result.sources, self.grounding_bundle.source_paths[:2])
        self.assertEqual(len(result.source_attributions), 2)
        self.assertEqual(result.source_attributions[0].support, "Capability catalog grounds supported action coverage.")
        self.assertIsNone(result.warning)
        self.assertEqual(fake_transport.calls[0]["api_key"], "test-key")

    def test_enabled_llm_backend_falls_back_to_deterministic_when_api_key_missing(self) -> None:
        backend = LlmAnswerBackend()
        config = AnswerBackendConfig(
            backend_kind=AnswerBackendKind.LLM,
            llm=LlmBackendConfig(
                enabled=True,
                provider=LlmProviderKind.OPENAI_RESPONSES,
                model="gpt-4o-mini",
                api_key_env="MISSING_KEY",
                fallback_enabled=True,
            ),
        )

        with patch.dict(os.environ, {}, clear=False):
            result = backend.answer(self.question, grounding_bundle=self.grounding_bundle, config=config)

        self.assertIn("open_app", result.answer_text)
        self.assertIn("LLM backend fallback", str(result.warning))
        self.assertIn("MODEL_BACKEND_UNAVAILABLE", str(result.warning))

    def test_enabled_llm_backend_can_fail_strictly_when_fallback_disabled(self) -> None:
        backend = LlmAnswerBackend()
        config = AnswerBackendConfig(
            backend_kind=AnswerBackendKind.LLM,
            llm=LlmBackendConfig(
                enabled=True,
                provider=LlmProviderKind.OPENAI_RESPONSES,
                model="gpt-4o-mini",
                api_key_env="MISSING_KEY",
                fallback_enabled=False,
            ),
        )

        with patch.dict(os.environ, {}, clear=False), self.assertRaises(JarvisError) as captured:
            backend.answer(self.question, grounding_bundle=self.grounding_bundle, config=config)

        self.assertEqual(getattr(captured.exception.code, "value", ""), ErrorCode.MODEL_BACKEND_UNAVAILABLE.value)

    def test_ungrounded_provider_response_falls_back_to_deterministic(self) -> None:
        fake_transport = _FakeTransport(
            response_payload={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "schema_version": ANSWER_SCHEMA_VERSION,
                                        "answer_text": "I support open_app.",
                                        "source_attributions": [
                                            {
                                                "source": "/tmp/not-allowed.md",
                                                "support": "Unsupported source.",
                                            }
                                        ],
                                        "warning": "",
                                        "grounded": True,
                                    }
                                ),
                            }
                        ],
                    }
                ],
            }
        )
        backend = LlmAnswerBackend()
        backend._resolve_provider = lambda provider_kind: OpenAIResponsesProvider(transport=fake_transport)  # type: ignore[method-assign]
        config = AnswerBackendConfig(
            backend_kind=AnswerBackendKind.LLM,
            llm=LlmBackendConfig(
                enabled=True,
                provider=LlmProviderKind.OPENAI_RESPONSES,
                model="gpt-4o-mini",
                api_key_env="TEST_OPENAI_KEY",
                fallback_enabled=True,
            ),
        )

        with patch.dict(os.environ, {"TEST_OPENAI_KEY": "test-key"}, clear=False):
            result = backend.answer(self.question, grounding_bundle=self.grounding_bundle, config=config)

        self.assertIn("open_app", result.answer_text)
        self.assertIn("ANSWER_NOT_GROUNDED", str(result.warning))


if __name__ == "__main__":
    unittest.main()
