"""Contract tests for OpenAI Responses request payload construction."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from context.session_context import SessionContext
from qa.answer_backend import AnswerBackendKind
from qa.answer_config import AnswerBackendConfig, LlmBackendConfig
from qa.grounding import build_grounding_bundle
from qa.llm_provider import LlmProviderKind
from qa.openai_responses_general_schema import GENERAL_ANSWER_SCHEMA_NAME, GENERAL_ANSWER_SCHEMA_VERSION
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
        self.open_domain_question = QuestionRequest(
            raw_input="Who is Ada Lovelace?",
            question_type=QuestionType.OPEN_DOMAIN_GENERAL,
            scope="open_domain",
            confidence=0.7,
            requires_grounding=False,
        )
        self.temporal_question = QuestionRequest(
            raw_input="Who is the current president of France?",
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
        self.self_harm_question = QuestionRequest(
            raw_input="What is the quickest painless way to kill myself?",
            question_type=QuestionType.OPEN_DOMAIN_GENERAL,
            scope="open_domain",
            confidence=0.7,
            requires_grounding=False,
        )
        self.open_domain_grounding_bundle = build_grounding_bundle(self.open_domain_question)
        self.temporal_grounding_bundle = build_grounding_bundle(self.temporal_question)
        self.medical_grounding_bundle = build_grounding_bundle(self.medical_question)
        self.self_harm_grounding_bundle = build_grounding_bundle(self.self_harm_question)
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
        self.assertTrue(str(metadata.get("correlation_id", "")).strip())

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
        self.assertEqual(payload.get("max_output_tokens"), 800)
        self.assertEqual(((payload.get("reasoning") or {}).get("effort")), "minimal")

    def test_payload_can_disable_strict_mode_explicitly(self) -> None:
        payload = self.provider.build_request_payload(
            self.question,
            grounding_bundle=self.grounding_bundle,
            config=self._config(strict_mode=False, max_output_tokens=256),
        )

        format_config = ((payload.get("text") or {}).get("format") or {})
        self.assertFalse(format_config.get("strict"))
        self.assertEqual(payload.get("max_output_tokens"), 256)

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
        self.assertIn("use those concrete values explicitly", instructions)
        self.assertIn("do not artificially cap citations", instructions)
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
        self.assertIn("Question-specific guidance:", input_text)
        self.assertIn("supported command families", input_text)
        self.assertIn("answer questions or explain capabilities in read-only grounded mode", input_text)
        self.assertIn("open_app", input_text)
        self.assertIn("at least three distinct source_attributions", input_text)
        self.assertIn("Allowed local sources:", input_text)
        self.assertIn(self.grounding_bundle.source_paths[0], input_text)
        self.assertIn("kind=capability_metadata", input_text)
        self.assertNotIn("support=", input_text)

    def test_clarification_docs_payload_includes_question_specific_guidance(self) -> None:
        clarification_question = QuestionRequest(
            raw_input="How does clarification work?",
            question_type=QuestionType.DOCS_RULES,
            scope="docs",
            confidence=0.9,
        )
        clarification_bundle = build_grounding_bundle(clarification_question)

        payload = self.provider.build_request_payload(
            clarification_question,
            grounding_bundle=clarification_bundle,
            config=self._config(),
        )

        input_text = str((((payload.get("input") or [])[0].get("content") or [])[0].get("text")) or "")
        self.assertIn("Question-specific guidance:", input_text)
        self.assertIn("ambiguity, missing data, low confidence, or routing ambiguity", input_text)

    def test_repo_structure_payload_requires_both_code_and_doc_citations(self) -> None:
        repo_question = QuestionRequest(
            raw_input="Where is the planner?",
            question_type=QuestionType.REPO_STRUCTURE,
            scope="repo_structure",
            confidence=0.9,
            context_refs={"topic": "planner"},
        )
        repo_bundle = build_grounding_bundle(repo_question)

        payload = self.provider.build_request_payload(
            repo_question,
            grounding_bundle=repo_bundle,
            config=self._config(),
        )

        input_text = str((((payload.get("input") or [])[0].get("content") or [])[0].get("text")) or "")
        self.assertIn("name that exact file path in answer_text", input_text)
        self.assertIn("keep both sources in source_attributions", input_text)

    def test_answer_follow_up_payload_includes_clarification_expansion_guidance(self) -> None:
        session_context = SessionContext()
        session_context.set_recent_answer_context(
            topic="clarification",
            scope="docs",
            sources=[
                str((Path(__file__).resolve().parents[1] / "docs/clarification_rules.md").resolve()),
                str((Path(__file__).resolve().parents[1] / "docs/runtime_flow.md").resolve()),
            ],
        )
        follow_up_question = QuestionRequest(
            raw_input="Explain more",
            question_type=QuestionType.ANSWER_FOLLOW_UP,
            scope="answer_follow_up",
            confidence=0.92,
            context_refs={
                "answer_topic": "clarification",
                "answer_scope": "docs",
                "answer_sources": list(session_context.get_recent_answer_context().get("sources", [])),
            },
        )
        follow_up_bundle = build_grounding_bundle(follow_up_question, session_context=session_context)

        payload = self.provider.build_request_payload(
            follow_up_question,
            grounding_bundle=follow_up_bundle,
            config=self._config(),
        )

        input_text = str((((payload.get("input") or [])[0].get("content") or [])[0].get("text")) or "")
        self.assertIn("Reuse both recent-answer source paths in source_attributions", input_text)
        self.assertIn(
            "clarification happens before planning or execution when ambiguity, missing data, low confidence, or mixed question-and-command intent is present",
            input_text,
        )
        self.assertIn("Open the explanation with wording close to", input_text)
        self.assertIn("hard-boundary framing", input_text)

    def test_model_knowledge_answer_follow_up_uses_open_domain_contract(self) -> None:
        session_context = SessionContext()
        session_context.set_recent_answer_context(
            topic="open_domain_general",
            scope="open_domain",
            sources=[],
            answer_text="Tony Stark is a fictional Marvel character.",
            answer_warning="May be out of date for changing facts.",
            answer_kind="open_domain_model",
            answer_provenance="model_knowledge",
        )
        follow_up_question = QuestionRequest(
            raw_input="Explain more",
            question_type=QuestionType.ANSWER_FOLLOW_UP,
            scope="open_domain",
            confidence=0.92,
            context_refs={
                "follow_up_kind": "explain_more",
                "answer_topic": "open_domain_general",
                "answer_scope": "open_domain",
                "answer_sources": [],
                "answer_text": "Tony Stark is a fictional Marvel character.",
                "answer_warning": "May be out of date for changing facts.",
                "answer_kind": "open_domain_model",
                "answer_provenance": "model_knowledge",
            },
        )
        follow_up_bundle = build_grounding_bundle(follow_up_question, session_context=session_context)

        payload = self.provider.build_request_payload(
            follow_up_question,
            grounding_bundle=follow_up_bundle,
            config=self._config(),
        )

        metadata = payload.get("metadata") or {}
        format_config = ((payload.get("text") or {}).get("format") or {})
        input_text = str((((payload.get("input") or [])[0].get("content") or [])[0].get("text")) or "")
        self.assertEqual(metadata.get("answer_mode"), "open_domain")
        self.assertEqual(format_config.get("name"), GENERAL_ANSWER_SCHEMA_NAME)
        self.assertIn("Question-specific follow-up guidance:", input_text)
        self.assertIn("This follow-up continues the previous model-knowledge answer", input_text)
        self.assertIn("answer directly instead of asking what the user wants explained", input_text)
        self.assertIn("For explain_more, provide a fuller explanation of the same subject", input_text)
        self.assertIn("Recent answer anchor: Tony Stark is a fictional Marvel character.", input_text)
        self.assertIn("Answer fully in English because the recent answer anchor is in English.", input_text)
        self.assertIn("Local grounded sources: none for this answer mode. Do not invent citations.", input_text)
        self.assertIn('"recent_answer_context"', input_text)

    def test_russian_model_knowledge_follow_up_locks_response_language_to_russian(self) -> None:
        session_context = SessionContext()
        session_context.set_recent_answer_context(
            topic="open_domain_general",
            scope="open_domain",
            sources=[],
            answer_text=(
                "Интернет вещей — это сеть устройств, которые подключаются к интернету и обмениваются данными без участия человека."
            ),
            answer_kind="open_domain_model",
            answer_provenance="model_knowledge",
        )
        follow_up_question = QuestionRequest(
            raw_input="Explain more",
            question_type=QuestionType.ANSWER_FOLLOW_UP,
            scope="open_domain",
            confidence=0.92,
            context_refs={
                "follow_up_kind": "explain_more",
                "answer_topic": "open_domain_general",
                "answer_scope": "open_domain",
                "answer_sources": [],
                "answer_text": (
                    "Интернет вещей — это сеть устройств, которые подключаются к интернету и обмениваются данными без участия человека."
                ),
                "answer_kind": "open_domain_model",
                "answer_provenance": "model_knowledge",
            },
        )
        follow_up_bundle = build_grounding_bundle(follow_up_question, session_context=session_context)

        payload = self.provider.build_request_payload(
            follow_up_question,
            grounding_bundle=follow_up_bundle,
            config=self._config(),
        )

        instructions = str(payload.get("instructions", "") or "")
        input_text = str((((payload.get("input") or [])[0].get("content") or [])[0].get("text")) or "")
        self.assertIn("Keep answer_text in one language only", instructions)
        self.assertIn("Answer fully in Russian because the recent answer anchor is in Russian.", input_text)
        self.assertIn("Do not switch languages mid-answer", input_text)

    def test_open_domain_payload_uses_general_schema_and_metadata(self) -> None:
        payload = self.provider.build_request_payload(
            self.open_domain_question,
            grounding_bundle=self.open_domain_grounding_bundle,
            config=self._config(),
        )

        metadata = payload.get("metadata") or {}
        self.assertEqual(metadata.get("answer_mode"), "open_domain")
        self.assertEqual(metadata.get("answer_schema_version"), GENERAL_ANSWER_SCHEMA_VERSION)
        format_config = ((payload.get("text") or {}).get("format") or {})
        self.assertEqual(format_config.get("name"), GENERAL_ANSWER_SCHEMA_NAME)
        schema = format_config.get("schema") or {}
        self.assertEqual(schema.get("required"), ["schema_version", "answer_text", "answer_kind", "warning"])
        self.assertEqual((schema.get("properties") or {}).get("answer_kind", {}).get("enum"), ["open_domain_model", "refusal"])

    def test_open_domain_payload_uses_model_knowledge_instructions_without_fake_sources(self) -> None:
        payload = self.provider.build_request_payload(
            self.open_domain_question,
            grounding_bundle=self.open_domain_grounding_bundle,
            config=self._config(),
        )

        instructions = str(payload.get("instructions", "") or "")
        self.assertIn("model knowledge", instructions)
        self.assertIn("current or changing real-world facts", instructions)
        self.assertIn("copy that warning into the warning field verbatim", instructions)
        input_items = payload.get("input") or []
        content_items = input_items[0].get("content") or []
        input_text = str(content_items[0].get("text", "") or "")
        self.assertIn("Question type: open_domain_general", input_text)
        self.assertIn("Local grounded sources: none for this answer mode.", input_text)
        self.assertNotIn("Allowed local sources:", input_text)

    def test_open_domain_payload_includes_temporal_boundary_metadata_and_warning_hint(self) -> None:
        payload = self.provider.build_request_payload(
            self.temporal_question,
            grounding_bundle=self.temporal_grounding_bundle,
            config=self._config(),
        )

        metadata = payload.get("metadata") or {}
        self.assertEqual(metadata.get("policy_tags"), "temporally_unstable")
        self.assertEqual(metadata.get("policy_response_mode"), "bounded_answer")
        self.assertIn("out of date", str(metadata.get("policy_warning_hint")))
        input_text = str((((payload.get("input") or [])[0].get("content") or [])[0].get("text")) or "")
        self.assertIn("Expected boundary: bounded_answer", input_text)
        self.assertIn("Policy tags: temporally_unstable", input_text)
        self.assertIn("Warning hint: This answer may be out of date", input_text)

    def test_open_domain_payload_includes_sensitive_domain_guidance(self) -> None:
        payload = self.provider.build_request_payload(
            self.medical_question,
            grounding_bundle=self.medical_grounding_bundle,
            config=self._config(),
        )

        metadata = payload.get("metadata") or {}
        self.assertEqual(metadata.get("policy_tags"), "medical_sensitive")
        self.assertEqual(metadata.get("policy_response_mode"), "bounded_answer")
        self.assertIn("medical advice", str(metadata.get("policy_warning_hint")))
        input_text = str((((payload.get("input") or [])[0].get("content") or [])[0].get("text")) or "")
        self.assertIn("Policy guidance:", input_text)
        self.assertIn("avoid diagnosis, prescriptions, dosing, or certainty", input_text)

    def test_open_domain_payload_includes_refusal_boundary_guidance(self) -> None:
        payload = self.provider.build_request_payload(
            self.self_harm_question,
            grounding_bundle=self.self_harm_grounding_bundle,
            config=self._config(),
        )

        instructions = str(payload.get("instructions", "") or "")
        self.assertIn("set answer_kind to refusal", instructions)
        self.assertIn("supportive safety language", instructions)
        metadata = payload.get("metadata") or {}
        self.assertEqual(metadata.get("policy_tags"), "self_harm")
        self.assertEqual(metadata.get("policy_response_mode"), "refusal")
        input_text = str((((payload.get("input") or [])[0].get("content") or [])[0].get("text")) or "")
        self.assertIn("Expected boundary: refusal", input_text)
        self.assertIn("Policy tags: self_harm", input_text)
        self.assertIn("crisis resources such as 988", input_text)

    def test_follow_up_source_payload_includes_exact_source_path_guidance(self) -> None:
        follow_up_question = QuestionRequest(
            raw_input="Which source?",
            question_type=QuestionType.ANSWER_FOLLOW_UP,
            scope="answer_follow_up",
            context_refs={
                "topic": "clarification",
                "answer_sources": ["docs/clarification_rules.md", "docs/runtime_flow.md"],
            },
            confidence=0.9,
        )
        session_context = SessionContext()
        session_context.set_recent_answer_context(
            topic="clarification",
            scope="docs",
            sources=["docs/clarification_rules.md", "docs/runtime_flow.md"],
        )
        follow_up_bundle = build_grounding_bundle(follow_up_question, session_context=session_context)

        payload = self.provider.build_request_payload(
            follow_up_question,
            grounding_bundle=follow_up_bundle,
            config=self._config(),
        )

        input_text = str((((payload.get("input") or [])[0].get("content") or [])[0].get("text")) or "")
        self.assertIn("exact raw source path(s) verbatim", input_text)
        self.assertIn("keep at least two source_attributions", input_text)
        self.assertIn("source_attributions", input_text)

    def test_blocked_state_payload_repeats_concrete_boundary_guidance(self) -> None:
        blocked_question = QuestionRequest(
            raw_input="What exactly do you need me to confirm?",
            question_type=QuestionType.BLOCKED_STATE,
            scope="blocked_state",
            confidence=0.96,
        )
        blocked_bundle = build_grounding_bundle(
            blocked_question,
            runtime_snapshot={"confirmation_message": "explicit confirmation before execution can continue"},
        )

        payload = self.provider.build_request_payload(
            blocked_question,
            grounding_bundle=blocked_bundle,
            config=self._config(),
        )

        input_text = str((((payload.get("input") or [])[0].get("content") or [])[0].get("text")) or "")
        self.assertIn("Preserve the concrete blocked-state boundary", input_text)
        self.assertIn("Repeat that concrete blocked-state boundary verbatim", input_text)

    def test_blocked_state_payload_requires_read_only_confirmation_boundary_when_message_missing(self) -> None:
        blocked_question = QuestionRequest(
            raw_input="What exactly do you need me to confirm?",
            question_type=QuestionType.BLOCKED_STATE,
            scope="blocked_state",
            confidence=0.96,
        )
        blocked_bundle = build_grounding_bundle(
            blocked_question,
            runtime_snapshot={"runtime_state": "awaiting_confirmation"},
        )

        payload = self.provider.build_request_payload(
            blocked_question,
            grounding_bundle=blocked_bundle,
            config=self._config(),
        )

        input_text = str((((payload.get("input") or [])[0].get("content") or [])[0].get("text")) or "")
        self.assertIn("explicit confirmation before execution can continue", input_text)
        self.assertIn("do not invent a different item or option", input_text)
        self.assertIn("keep at least three source_attributions", input_text)

    def test_runtime_status_workspace_payload_requires_multi_source_grounding(self) -> None:
        runtime_status_question = QuestionRequest(
            raw_input="What folder are you using?",
            question_type=QuestionType.RUNTIME_STATUS,
            scope="runtime",
            confidence=0.94,
        )
        session_context = SessionContext()
        session_context.set_recent_project_context("/tmp/demo")
        runtime_status_bundle = build_grounding_bundle(runtime_status_question, session_context=session_context)

        payload = self.provider.build_request_payload(
            runtime_status_question,
            grounding_bundle=runtime_status_bundle,
            config=self._config(),
        )

        input_text = str((((payload.get("input") or [])[0].get("content") or [])[0].get("text")) or "")
        self.assertIn("Use the exact recent workspace or folder path", input_text)
        self.assertIn("keep at least two source_attributions", input_text)

    def _config(
        self,
        *,
        api_base: str | None = None,
        strict_mode: bool = True,
        max_output_tokens: int = 800,
    ) -> AnswerBackendConfig:
        return AnswerBackendConfig(
            backend_kind=AnswerBackendKind.LLM,
            llm=LlmBackendConfig(
                enabled=True,
                provider=LlmProviderKind.OPENAI_RESPONSES,
                model="gpt-5-nano",
                api_base=api_base,
                strict_mode=strict_mode,
                max_output_tokens=max_output_tokens,
            ),
        )


if __name__ == "__main__":
    unittest.main()
