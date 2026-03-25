"""Contract tests for OpenAI Responses response parsing."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from jarvis_error import ErrorCode, JarvisError
from qa.grounding import build_grounding_bundle
from qa.openai_responses_general_schema import GENERAL_ANSWER_SCHEMA_VERSION
from qa.openai_responses_provider import ANSWER_SCHEMA_VERSION, OpenAIResponsesProvider
from question_request import QuestionRequest, QuestionType


class OpenAIResponsesParsingContractTests(unittest.TestCase):
    """Lock the accepted and rejected response shapes from the Responses API."""

    def setUp(self) -> None:
        self.question = QuestionRequest(
            raw_input="What can you do?",
            question_type=QuestionType.CAPABILITIES,
            scope="capabilities",
            confidence=0.95,
        )
        self.grounding_bundle = build_grounding_bundle(self.question)
        self.open_domain_question = QuestionRequest(
            raw_input="Who is Ada Lovelace?",
            question_type=QuestionType.OPEN_DOMAIN_GENERAL,
            scope="open_domain",
            confidence=0.7,
            requires_grounding=False,
        )
        self.medical_question = QuestionRequest(
            raw_input="Should I stop taking my medication if I have chest pain?",
            question_type=QuestionType.OPEN_DOMAIN_GENERAL,
            scope="open_domain",
            confidence=0.7,
            requires_grounding=False,
        )
        self.open_domain_grounding_bundle = build_grounding_bundle(self.open_domain_question)
        self.medical_grounding_bundle = build_grounding_bundle(self.medical_question)
        self.provider = OpenAIResponsesProvider()

    def test_parse_answer_response_accepts_direct_output_text(self) -> None:
        result = self.provider._parse_answer_response(  # noqa: SLF001
            {
                "status": "completed",
                "output_text": self._valid_output_text(),
            },
            grounding_bundle=self.grounding_bundle,
        )

        self.assertIn("open_app", result.answer_text)
        self.assertEqual(result.sources, self.grounding_bundle.source_paths[:2])

    def test_parse_answer_response_accepts_assistant_output_text_item(self) -> None:
        result = self.provider._parse_answer_response(  # noqa: SLF001
            {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": self._valid_output_text(),
                            }
                        ],
                    }
                ],
            },
            grounding_bundle=self.grounding_bundle,
        )

        self.assertIn("grounded question answering", result.answer_text)
        self.assertEqual(len(result.source_attributions), 2)

    def test_parse_answer_response_normalizes_prompt_annotated_source_path(self) -> None:
        result = self.provider._parse_answer_response(  # noqa: SLF001
            {
                "status": "completed",
                "output_text": json.dumps(
                    {
                        "schema_version": ANSWER_SCHEMA_VERSION,
                        "answer_text": "I support open_app and grounded question answering.",
                        "source_attributions": [
                            {
                                "source": f"{self.grounding_bundle.source_paths[0]} | kind=capability_metadata",
                                "support": "Capability catalog grounds supported action coverage.",
                            }
                        ],
                        "warning": "",
                        "grounded": True,
                    }
                ),
            },
            grounding_bundle=self.grounding_bundle,
        )

        self.assertEqual(result.sources, [self.grounding_bundle.source_paths[0]])

    def test_parse_answer_response_rejects_failed_status(self) -> None:
        with self.assertRaises(JarvisError) as captured:
            self.provider._parse_answer_response(  # noqa: SLF001
                {"status": "failed"},
                grounding_bundle=self.grounding_bundle,
            )

        self.assertEqual(getattr(captured.exception.code, "value", ""), ErrorCode.ANSWER_GENERATION_FAILED.value)

    def test_parse_answer_response_reports_incomplete_details(self) -> None:
        with self.assertRaises(JarvisError) as captured:
            self.provider._parse_answer_response(  # noqa: SLF001
                {
                    "status": "incomplete",
                    "incomplete_details": {"reason": "max_output_tokens"},
                },
                grounding_bundle=self.grounding_bundle,
            )

        self.assertEqual(getattr(captured.exception.code, "value", ""), ErrorCode.ANSWER_GENERATION_FAILED.value)
        self.assertEqual((captured.exception.details or {}).get("incomplete_details"), {"reason": "max_output_tokens"})

    def test_parse_answer_response_rejects_invalid_json(self) -> None:
        with self.assertRaises(JarvisError) as captured:
            self.provider._parse_answer_response(  # noqa: SLF001
                {"status": "completed", "output_text": "not-json"},
                grounding_bundle=self.grounding_bundle,
            )

        self.assertEqual(getattr(captured.exception.code, "value", ""), ErrorCode.ANSWER_GENERATION_FAILED.value)

    def test_parse_answer_response_rejects_non_object_json(self) -> None:
        with self.assertRaises(JarvisError) as captured:
            self.provider._parse_answer_response(  # noqa: SLF001
                {"status": "completed", "output_text": "[]"},
                grounding_bundle=self.grounding_bundle,
            )

        self.assertEqual(getattr(captured.exception.code, "value", ""), ErrorCode.ANSWER_GENERATION_FAILED.value)

    def test_parse_answer_response_rejects_unknown_schema_version(self) -> None:
        with self.assertRaises(JarvisError) as captured:
            self.provider._parse_answer_response(  # noqa: SLF001
                {
                    "status": "completed",
                    "output_text": json.dumps(
                        {
                            "schema_version": "qa_answer_v0",
                            "answer_text": "I support open_app.",
                            "source_attributions": [
                                {
                                    "source": self.grounding_bundle.source_paths[0],
                                    "support": "Capability catalog grounds supported action coverage.",
                                }
                            ],
                            "warning": "",
                            "grounded": True,
                        }
                    ),
                },
                grounding_bundle=self.grounding_bundle,
            )

        self.assertEqual(getattr(captured.exception.code, "value", ""), ErrorCode.ANSWER_GENERATION_FAILED.value)

    def test_parse_answer_response_rejects_refusal_only_output(self) -> None:
        with self.assertRaises(JarvisError) as captured:
            self.provider._parse_answer_response(  # noqa: SLF001
                {
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "refusal",
                                    "refusal": "I cannot comply.",
                                }
                            ],
                        }
                    ],
                },
                grounding_bundle=self.grounding_bundle,
            )

        self.assertEqual(getattr(captured.exception.code, "value", ""), ErrorCode.ANSWER_GENERATION_FAILED.value)
        self.assertIn("refused structured answer generation", str(captured.exception.message))

    def test_parse_answer_response_rejects_missing_assistant_text(self) -> None:
        with self.assertRaises(JarvisError) as captured:
            self.provider._parse_answer_response(  # noqa: SLF001
                {"status": "completed", "output": []},
                grounding_bundle=self.grounding_bundle,
            )

        self.assertEqual(getattr(captured.exception.code, "value", ""), ErrorCode.ANSWER_GENERATION_FAILED.value)

    def test_parse_answer_response_rejects_ungrounded_structured_output(self) -> None:
        with self.assertRaises(JarvisError) as captured:
            self.provider._parse_answer_response(  # noqa: SLF001
                {
                    "status": "completed",
                    "output_text": json.dumps(
                        {
                            "schema_version": ANSWER_SCHEMA_VERSION,
                            "answer_text": "I support open_app.",
                            "source_attributions": [
                                {
                                    "source": self.grounding_bundle.source_paths[0],
                                    "support": "Capability catalog grounds supported action coverage.",
                                }
                            ],
                            "warning": "Grounding was insufficient.",
                            "grounded": False,
                        }
                    ),
                },
                grounding_bundle=self.grounding_bundle,
            )

        self.assertEqual(getattr(captured.exception.code, "value", ""), ErrorCode.ANSWER_NOT_GROUNDED.value)

    def test_parse_answer_response_rejects_generic_support_text(self) -> None:
        with self.assertRaises(JarvisError) as captured:
            self.provider._parse_answer_response(  # noqa: SLF001
                {
                    "status": "completed",
                    "output_text": json.dumps(
                        {
                            "schema_version": ANSWER_SCHEMA_VERSION,
                            "answer_text": "I support open_app.",
                            "source_attributions": [
                                {
                                    "source": self.grounding_bundle.source_paths[0],
                                    "support": "Documentation source.",
                                }
                            ],
                            "warning": "",
                            "grounded": True,
                        }
                    ),
                },
                grounding_bundle=self.grounding_bundle,
            )

        self.assertEqual(getattr(captured.exception.code, "value", ""), ErrorCode.ANSWER_NOT_GROUNDED.value)

    def test_parse_answer_response_accepts_open_domain_structured_output(self) -> None:
        result = self.provider._parse_answer_response(  # noqa: SLF001
            {
                "status": "completed",
                "output_text": json.dumps(
                    {
                        "schema_version": GENERAL_ANSWER_SCHEMA_VERSION,
                        "answer_text": "Ada Lovelace is widely regarded as an early computing pioneer.",
                        "answer_kind": "open_domain_model",
                        "warning": "May be out of date for changing facts.",
                    }
                ),
            },
            question=self.open_domain_question,
            grounding_bundle=self.open_domain_grounding_bundle,
        )

        self.assertIn("Ada Lovelace", result.answer_text)
        self.assertEqual(result.sources, [])
        self.assertEqual(getattr(result.answer_kind, "value", ""), "open_domain_model")
        self.assertEqual(getattr(result.provenance, "value", ""), "model_knowledge")
        self.assertEqual(result.warning, "May be out of date for changing facts.")

    def test_parse_answer_response_backfills_policy_warning_hint_for_bounded_open_domain_answer(self) -> None:
        result = self.provider._parse_answer_response(  # noqa: SLF001
            {
                "status": "completed",
                "output_text": json.dumps(
                    {
                        "schema_version": GENERAL_ANSWER_SCHEMA_VERSION,
                        "answer_text": "Chest pain can be serious, so seek urgent medical help.",
                        "answer_kind": "open_domain_model",
                        "warning": "",
                    }
                ),
            },
            question=self.medical_question,
            grounding_bundle=self.medical_grounding_bundle,
        )

        self.assertEqual(getattr(result.answer_kind, "value", ""), "open_domain_model")
        self.assertEqual(result.warning, "This is general information, not medical advice.")

    def test_parse_answer_response_accepts_open_domain_refusal_output(self) -> None:
        result = self.provider._parse_answer_response(  # noqa: SLF001
            {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "refusal",
                                "refusal": "I can't help with that request.",
                            }
                        ],
                    }
                ],
            },
            question=self.open_domain_question,
            grounding_bundle=self.open_domain_grounding_bundle,
        )

        self.assertEqual(getattr(result.answer_kind, "value", ""), "refusal")
        self.assertEqual(getattr(result.provenance, "value", ""), "model_knowledge")
        self.assertEqual(result.answer_text, "I can't help with that request.")

    def _valid_output_text(self) -> str:
        return json.dumps(
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
        )


if __name__ == "__main__":
    unittest.main()
