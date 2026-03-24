"""Interaction-manager contract tests for dual-mode orchestration."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from context.session_context import SessionContext
from interaction.interaction_manager import InteractionManager
from parser.command_parser import parse_command
from qa.answer_backend import AnswerBackendKind


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
        self.assertIsNone(result.runtime_result)
        self.assertIsNone(result.answer_result)
        self.assertEqual((result.visibility or {}).get("interaction_mode"), "clarification")

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


if __name__ == "__main__":
    unittest.main()
