"""Interaction-manager contract tests for dual-mode orchestration."""

from __future__ import annotations

import unittest

from context.session_context import SessionContext
from interaction.interaction_manager import InteractionManager
from jarvis_error import ErrorCode
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

    def test_command_input_delegates_to_runtime_manager(self) -> None:
        result = self.manager.handle_input("open telegram", session_context=self.session_context)

        self.assertEqual(getattr(result.interaction_mode, "value", ""), "command")
        self.assertIsNotNone(result.runtime_result)
        self.assertIsNone(result.answer_result)

    def test_mixed_input_returns_clarification_without_execution(self) -> None:
        result = self.manager.handle_input("What can you do and open Safari", session_context=self.session_context)

        self.assertEqual(getattr(result.interaction_mode, "value", ""), "clarification")
        self.assertIsNotNone(result.clarification_request)
        self.assertIsNone(result.runtime_result)
        self.assertIsNone(result.answer_result)

    def test_llm_backend_error_is_wrapped_as_question_failure(self) -> None:
        manager = InteractionManager(answer_backend_kind=AnswerBackendKind.LLM)

        result = manager.handle_input("What can you do?", session_context=self.session_context)

        self.assertEqual(getattr(result.interaction_mode, "value", ""), "question")
        self.assertIsNone(result.answer_result)
        self.assertIsNotNone(result.error)
        self.assertEqual(getattr(result.error.code, "value", ""), ErrorCode.MODEL_BACKEND_UNAVAILABLE.value)


if __name__ == "__main__":
    unittest.main()
