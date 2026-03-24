"""Contract tests for OpenAI Responses request payload construction."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from qa.answer_backend import AnswerBackendKind
from qa.answer_config import AnswerBackendConfig, LlmBackendConfig
from qa.grounding import build_grounding_bundle
from qa.llm_provider import LlmProviderKind
from qa.openai_responses_provider import ANSWER_SCHEMA_NAME, ANSWER_SCHEMA_VERSION, OpenAIResponsesProvider
from question_request import QuestionRequest, QuestionType


class OpenAIResponsesPayloadContractTests(unittest.TestCase):
    """Lock the exact payload shape we send to the Responses API."""

    def setUp(self) -> None:
        self.question = QuestionRequest(
            raw_input="What can you do?",
            question_type=QuestionType.CAPABILITIES,
            scope="capabilities",
            confidence=0.95,
        )
        self.grounding_bundle = build_grounding_bundle(self.question)
        self.provider = OpenAIResponsesProvider()

    def test_payload_uses_string_only_metadata(self) -> None:
        payload = self.provider.build_request_payload(
            self.question,
            grounding_bundle=self.grounding_bundle,
            config=self._config(),
        )

        metadata = payload.get("metadata") or {}
        self.assertTrue(metadata)
        self.assertTrue(all(isinstance(value, str) for value in metadata.values()))
        self.assertEqual(metadata.get("source_count"), str(len(self.grounding_bundle.source_paths)))
        self.assertEqual(metadata.get("answer_schema_version"), ANSWER_SCHEMA_VERSION)

    def test_payload_does_not_inline_api_base(self) -> None:
        payload = self.provider.build_request_payload(
            self.question,
            grounding_bundle=self.grounding_bundle,
            config=self._config(api_base="https://example.invalid/v1"),
        )

        self.assertNotIn("base_url", payload)

    def test_payload_uses_strict_named_json_schema_format(self) -> None:
        payload = self.provider.build_request_payload(
            self.question,
            grounding_bundle=self.grounding_bundle,
            config=self._config(),
        )

        text_config = payload.get("text") or {}
        format_config = text_config.get("format") or {}
        self.assertEqual(format_config.get("type"), "json_schema")
        self.assertEqual(format_config.get("name"), ANSWER_SCHEMA_NAME)
        self.assertTrue(format_config.get("strict"))
        schema = format_config.get("schema") or {}
        self.assertEqual(schema.get("type"), "object")
        self.assertEqual(
            schema.get("required"),
            ["schema_version", "answer_text", "source_attributions", "warning", "grounded"],
        )
        self.assertEqual((schema.get("properties") or {}).get("schema_version", {}).get("enum"), [ANSWER_SCHEMA_VERSION])

    def test_payload_instructions_lock_grounding_and_no_execution(self) -> None:
        payload = self.provider.build_request_payload(
            self.question,
            grounding_bundle=self.grounding_bundle,
            config=self._config(),
        )

        instructions = str(payload.get("instructions", "") or "")
        self.assertIn("Answer only from the provided local grounding bundle", instructions)
        self.assertIn("do not invent sources", instructions)
        self.assertIn("do not imply that any command was executed", instructions)
        self.assertIn(ANSWER_SCHEMA_VERSION, instructions)

    def test_payload_user_input_contains_question_and_allowed_sources(self) -> None:
        payload = self.provider.build_request_payload(
            self.question,
            grounding_bundle=self.grounding_bundle,
            config=self._config(),
        )

        input_items = payload.get("input") or []
        self.assertEqual(len(input_items), 1)
        self.assertEqual(input_items[0].get("role"), "user")
        content_items = input_items[0].get("content") or []
        self.assertEqual(len(content_items), 1)
        self.assertEqual(content_items[0].get("type"), "input_text")
        input_text = str(content_items[0].get("text", "") or "")
        self.assertIn("Question type: capabilities", input_text)
        self.assertIn("Question: What can you do?", input_text)
        self.assertIn("Allowed local sources:", input_text)
        self.assertIn(self.grounding_bundle.source_paths[0], input_text)

    def _config(self, *, api_base: str | None = None) -> AnswerBackendConfig:
        return AnswerBackendConfig(
            backend_kind=AnswerBackendKind.LLM,
            llm=LlmBackendConfig(
                enabled=True,
                provider=LlmProviderKind.OPENAI_RESPONSES,
                model="gpt-5-nano",
                api_base=api_base,
            ),
        )


if __name__ == "__main__":
    unittest.main()
