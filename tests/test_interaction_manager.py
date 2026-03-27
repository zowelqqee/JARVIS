"""Interaction-manager contract tests for dual-mode orchestration."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from context.session_context import SessionContext
from interaction.interaction_manager import InteractionManager
from parser.command_parser import parse_command
from qa.answer_backend import AnswerBackendKind
from qa.answer_config import AnswerBackendConfig, LlmBackendConfig
from qa.llm_provider import LlmProviderKind


class _FakeOpenDomainProvider:
    provider_kind = LlmProviderKind.OPENAI_RESPONSES

    def answer(
        self,
        question,
        *,
        grounding_bundle,
        config,
        session_context=None,
        runtime_snapshot=None,
        debug_trace=None,
    ):
        del question, grounding_bundle, config, session_context, runtime_snapshot, debug_trace
        return SimpleNamespace(
            answer_text="Ada Lovelace is commonly described as an early computing pioneer.",
            sources=[],
            source_attributions=[],
            confidence=0.72,
            warning="May be out of date for changing facts.",
            answer_kind="open_domain_model",
            provenance="model_knowledge",
            interaction_mode="question",
        )

    def build_request_payload(
        self,
        question,
        *,
        grounding_bundle,
        config,
        session_context=None,
        runtime_snapshot=None,
    ):
        del question, grounding_bundle, config, session_context, runtime_snapshot
        return {}


class InteractionManagerTests(unittest.TestCase):
    """Protect the non-invasive interaction layer before CLI integration."""

    def setUp(self) -> None:
        self.manager = InteractionManager()
        self.session_context = SessionContext()

    def test_question_input_returns_answer_result(self) -> None:
        result = self.manager.handle_input("What can you do?", session_context=self.session_context)

        self.assertEqual(getattr(result.interaction_mode, "value", ""), "question")
        self.assertIsNotNone(result.answer_result)
        self.assertIsNone(result.runtime_result)
        self.assertEqual((result.visibility or {}).get("interaction_mode"), "question")

    def test_command_input_delegates_to_runtime_manager(self) -> None:
        result = self.manager.handle_input("open telegram", session_context=self.session_context)

        self.assertEqual(getattr(result.interaction_mode, "value", ""), "command")
        self.assertIsNotNone(result.runtime_result)
        self.assertIsNone(result.answer_result)
        self.assertEqual((result.visibility or {}).get("interaction_mode"), "command")

    def test_mixed_input_returns_clarification_without_execution(self) -> None:
        result = self.manager.handle_input("What can you do and open Safari", session_context=self.session_context)

        self.assertEqual(getattr(result.interaction_mode, "value", ""), "clarification")
        self.assertIsNotNone(result.clarification_request)
        self.assertEqual(
            getattr(result.clarification_request, "message", ""),
            "Do you want an answer first or should I open Safari?",
        )
        self.assertIsNone(result.runtime_result)
        self.assertIsNone(result.answer_result)
        self.assertEqual((result.visibility or {}).get("interaction_mode"), "clarification")
        pending = self.session_context.get_pending_interaction_clarification()
        self.assertEqual((pending or {}).get("question_input"), "What can you do")
        self.assertEqual((pending or {}).get("command_input"), "open Safari")

    def test_mixed_input_answer_reply_routes_to_question_branch(self) -> None:
        self.manager.handle_input("What can you do and open Safari", session_context=self.session_context)

        result = self.manager.handle_input("Answer first", session_context=self.session_context)

        self.assertEqual(getattr(result.interaction_mode, "value", ""), "question")
        self.assertIsNotNone(result.answer_result)
        self.assertIsNone(result.runtime_result)
        self.assertIn("open_app", getattr(result.answer_result, "answer_text", ""))
        self.assertIsNone(self.session_context.get_pending_interaction_clarification())

    def test_mixed_input_execute_reply_routes_to_command_branch(self) -> None:
        self.manager.handle_input("What can you do and open Safari", session_context=self.session_context)

        result = self.manager.handle_input("Execute the command", session_context=self.session_context)

        self.assertEqual(getattr(result.interaction_mode, "value", ""), "command")
        self.assertIsNotNone(result.runtime_result)
        self.assertIsNone(result.answer_result)
        self.assertIn("open_app", getattr(result.runtime_result, "command_summary", "") or "")
        self.assertIsNone(self.session_context.get_pending_interaction_clarification())

    def test_mixed_input_unclear_reply_repeats_narrower_clarification(self) -> None:
        self.manager.handle_input("What can you do and open Safari", session_context=self.session_context)

        result = self.manager.handle_input("yes", session_context=self.session_context)

        self.assertEqual(getattr(result.interaction_mode, "value", ""), "clarification")
        self.assertEqual(getattr(result.clarification_request, "message", ""), "Please reply with answer or execute.")
        pending = self.session_context.get_pending_interaction_clarification()
        self.assertEqual((pending or {}).get("command_input"), "open Safari")

    def test_blocked_state_question_returns_grounded_answer_without_runtime_execution(self) -> None:
        self.manager.runtime_manager.current_state = "awaiting_confirmation"
        self.manager.runtime_manager.blocked_reason = "Approve close_app for Telegram before execution."
        self.manager.runtime_manager.confirmation_request = SimpleNamespace(
            message="Approve close_app for Telegram before execution.",
            boundary_type="step",
            affected_targets=[],
        )

        result = self.manager.handle_input("What exactly do you need me to confirm?", session_context=self.session_context)

        self.assertEqual(getattr(result.interaction_mode, "value", ""), "question")
        self.assertIsNotNone(result.answer_result)
        self.assertIsNone(result.runtime_result)
        self.assertIn("confirm", getattr(result.answer_result, "answer_text", "").lower())

    def test_recent_runtime_question_reports_last_command_summary(self) -> None:
        self.manager.runtime_manager.current_state = "completed"
        self.manager.runtime_manager.active_command = parse_command("open Safari", self.session_context)

        result = self.manager.handle_input("What command did you run last?", session_context=self.session_context)

        self.assertEqual(getattr(result.interaction_mode, "value", ""), "question")
        self.assertIsNotNone(result.answer_result)
        self.assertIn("open_app: Safari", getattr(result.answer_result, "answer_text", ""))

    def test_question_answer_updates_recent_answer_context(self) -> None:
        self.manager.handle_input("How does clarification work?", session_context=self.session_context)

        recent_answer_context = self.session_context.get_recent_answer_context()

        self.assertIsNotNone(recent_answer_context)
        self.assertEqual((recent_answer_context or {}).get("topic"), "clarification")
        self.assertEqual((recent_answer_context or {}).get("scope"), "docs")
        self.assertTrue((recent_answer_context or {}).get("sources"))

    def test_safe_follow_up_question_reuses_recent_answer_context(self) -> None:
        self.manager.handle_input("How does clarification work?", session_context=self.session_context)

        result = self.manager.handle_input("Which source?", session_context=self.session_context)

        self.assertEqual(getattr(result.interaction_mode, "value", ""), "question")
        self.assertIsNotNone(result.answer_result)
        self.assertIn("docs/clarification_rules.md", getattr(result.answer_result, "answer_text", ""))
        self.assertIsNone(result.runtime_result)

    def test_debug_mode_attaches_structured_question_debug_metadata(self) -> None:
        with patch.dict("os.environ", {"JARVIS_QA_DEBUG": "1"}, clear=False):
            result = self.manager.handle_input("How does clarification work?", session_context=self.session_context)

        debug = dict((result.metadata or {}).get("debug", {}) or {})
        self.assertEqual(debug.get("routing_decision", {}).get("interaction_kind"), "question")
        self.assertEqual(debug.get("question_classification", {}).get("question_type"), "docs_rules")
        self.assertEqual(debug.get("source_selection", {}).get("source_count"), 2)
        self.assertIn("docs/clarification_rules.md", " ".join(debug.get("source_selection", {}).get("sources", [])))

    def test_debug_mode_attaches_routing_debug_for_command_path(self) -> None:
        with patch.dict("os.environ", {"JARVIS_QA_DEBUG": "1"}, clear=False):
            result = self.manager.handle_input("open telegram", session_context=self.session_context)

        debug = dict((result.metadata or {}).get("debug", {}) or {})
        self.assertEqual(debug.get("routing_decision", {}).get("interaction_kind"), "command")
        self.assertNotIn("question_classification", debug)

    def test_llm_backend_falls_back_to_question_answer(self) -> None:
        manager = InteractionManager(answer_backend_kind=AnswerBackendKind.LLM)

        result = manager.handle_input("What can you do?", session_context=self.session_context)

        self.assertEqual(getattr(result.interaction_mode, "value", ""), "question")
        self.assertIsNotNone(result.answer_result)
        self.assertIsNone(result.error)
        self.assertIn("open_app", getattr(result.answer_result, "answer_text", ""))
        self.assertIn("LLM backend fallback", str(getattr(result.answer_result, "warning", "")))

    def test_open_domain_question_updates_recent_answer_context_without_sources(self) -> None:
        manager = InteractionManager(
            answer_backend_config=AnswerBackendConfig(
                backend_kind=AnswerBackendKind.LLM,
                llm=LlmBackendConfig(
                    enabled=True,
                    provider=LlmProviderKind.OPENAI_RESPONSES,
                    open_domain_enabled=True,
                    fallback_enabled=False,
                ),
            )
        )

        with patch.dict("qa.llm_backend._PROVIDERS", {LlmProviderKind.OPENAI_RESPONSES: _FakeOpenDomainProvider()}, clear=False):
            result = manager.handle_input("Who is Ada Lovelace?", session_context=self.session_context)

        self.assertEqual(getattr(result.interaction_mode, "value", ""), "question")
        self.assertIsNotNone(result.answer_result)
        self.assertIsNone(result.error)
        self.assertEqual(getattr(result.answer_result, "answer_kind", ""), "open_domain_model")
        recent_answer_context = self.session_context.get_recent_answer_context()
        self.assertEqual((recent_answer_context or {}).get("topic"), "open_domain_general")
        self.assertEqual((recent_answer_context or {}).get("scope"), "open_domain")
        self.assertEqual((recent_answer_context or {}).get("sources"), [])

    def test_russian_quantitative_open_domain_question_routes_to_model_answer(self) -> None:
        manager = InteractionManager(
            answer_backend_config=AnswerBackendConfig(
                backend_kind=AnswerBackendKind.LLM,
                llm=LlmBackendConfig(
                    enabled=True,
                    provider=LlmProviderKind.OPENAI_RESPONSES,
                    open_domain_enabled=True,
                    fallback_enabled=False,
                ),
            )
        )

        with patch.dict("qa.llm_backend._PROVIDERS", {LlmProviderKind.OPENAI_RESPONSES: _FakeOpenDomainProvider()}, clear=False):
            result = manager.handle_input("Сколько планет во вселенной", session_context=self.session_context)

        self.assertEqual(getattr(result.interaction_mode, "value", ""), "question")
        self.assertIsNotNone(result.answer_result)
        self.assertIsNone(result.error)
        self.assertEqual(getattr(result.answer_result, "answer_kind", ""), "open_domain_model")

    def test_beta_question_default_stage_can_answer_open_domain_without_explicit_backend_override(self) -> None:
        with patch.dict(
            os.environ,
            {
                "JARVIS_QA_ROLLOUT_STAGE": "beta_question_default",
                "OPENAI_API_KEY": "test-key",
            },
            clear=False,
        ), patch.dict(
            "qa.llm_backend._PROVIDERS",
            {LlmProviderKind.OPENAI_RESPONSES: _FakeOpenDomainProvider()},
            clear=False,
        ):
            manager = InteractionManager()
            result = manager.handle_input("Who is Ada Lovelace?", session_context=self.session_context)

        self.assertEqual(getattr(result.interaction_mode, "value", ""), "question")
        self.assertIsNotNone(result.answer_result)
        self.assertEqual(getattr(result.answer_result, "answer_kind", ""), "open_domain_model")
        self.assertEqual((result.metadata or {}).get("answer_backend"), "llm")

    def test_hybrid_open_domain_flags_can_answer_without_explicit_backend_override(self) -> None:
        manager = InteractionManager(
            answer_backend_config=AnswerBackendConfig(
                backend_kind=AnswerBackendKind.DETERMINISTIC,
                llm=LlmBackendConfig(
                    enabled=True,
                    provider=LlmProviderKind.OPENAI_RESPONSES,
                    open_domain_enabled=True,
                    fallback_enabled=True,
                ),
            )
        )

        with patch.dict("qa.llm_backend._PROVIDERS", {LlmProviderKind.OPENAI_RESPONSES: _FakeOpenDomainProvider()}, clear=False):
            result = manager.handle_input("Who is Ada Lovelace?", session_context=self.session_context)

        self.assertEqual(getattr(result.interaction_mode, "value", ""), "question")
        self.assertIsNotNone(result.answer_result)
        self.assertEqual(getattr(result.answer_result, "answer_kind", ""), "open_domain_model")
        self.assertEqual((result.metadata or {}).get("answer_backend"), "llm")


if __name__ == "__main__":
    unittest.main()
