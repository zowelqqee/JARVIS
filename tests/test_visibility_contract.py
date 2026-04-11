"""Deterministic visibility payload contract tests for MVP runtime states."""

from __future__ import annotations

import unittest

from clarification_request import ClarificationRequest
from command import Command, IntentType
from confirmation_request import ConfirmationBoundaryType, ConfirmationRequest
from jarvis_error import ErrorCategory, ErrorCode, JarvisError
from step import Step, StepAction, StepStatus
from target import Target, TargetType
from ui.visibility_mapper import map_visibility


class VisibilityContractTests(unittest.TestCase):
    """Lock visibility field-presence and summary/hint determinism."""

    def _base_command(self) -> Command:
        return Command(
            raw_input="open telegram",
            intent=IntentType.OPEN_APP,
            targets=[Target(type=TargetType.APPLICATION, name="Telegram")],
            parameters={},
            confidence=0.9,
            requires_confirmation=False,
            execution_steps=[],
            status_message="Parsed",
        )

    def _russian_command(self) -> Command:
        return Command(
            raw_input="открой Telegram",
            intent=IntentType.OPEN_APP,
            targets=[Target(type=TargetType.APPLICATION, name="Telegram")],
            parameters={},
            confidence=0.9,
            requires_confirmation=False,
            execution_steps=[],
            status_message="Parsed",
        )

    def test_completed_payload_omits_failure_and_hint_fields(self) -> None:
        step = Step(
            id="step_1",
            action=StepAction.OPEN_APP,
            target=Target(type=TargetType.APPLICATION, name="Telegram"),
            status=StepStatus.DONE,
            requires_confirmation=False,
        )
        visibility = map_visibility(
            state="completed",
            command=self._base_command(),
            completed_steps=[step],
            completion_result="Completed open_app with 1 step(s).",
        )

        self.assertEqual(visibility.get("runtime_state"), "completed")
        self.assertIn("completion_result", visibility)
        self.assertNotIn("failure_message", visibility)
        self.assertNotIn("next_step_hint", visibility)
        self.assertNotIn("clarification_question", visibility)
        self.assertNotIn("confirmation_request", visibility)

    def test_awaiting_confirmation_payload_contains_single_blocked_hint(self) -> None:
        confirmation = ConfirmationRequest(
            message="Approve close_app for Telegram before execution.",
            affected_targets=[Target(type=TargetType.APPLICATION, name="Telegram")],
            boundary_type=ConfirmationBoundaryType.STEP,
        )
        visibility = map_visibility(
            state="awaiting_confirmation",
            command=self._base_command(),
            confirmation=confirmation,
        )

        self.assertEqual(visibility.get("runtime_state"), "awaiting_confirmation")
        self.assertIn("confirmation_request", visibility)
        self.assertIn("next_step_hint", visibility)
        self.assertEqual(visibility.get("next_step_hint"), "Reply yes to continue or no to cancel.")
        self.assertNotIn("failure_message", visibility)
        self.assertNotIn("completion_result", visibility)

    def test_awaiting_clarification_payload_contains_question_and_hint(self) -> None:
        clarification = ClarificationRequest(
            message="Which app do you want?",
            code=ErrorCode.TARGET_NOT_FOUND.value,
            options=["Telegram", "Safari"],
        )
        error = JarvisError(
            category=ErrorCategory.VALIDATION_ERROR,
            code=ErrorCode.MULTIPLE_MATCHES,
            message="Multiple matching targets require clarification.",
            details=None,
            blocking=True,
            terminal=False,
        )
        visibility = map_visibility(
            state="awaiting_clarification",
            command=self._base_command(),
            clarification=clarification,
            error=error,
        )

        self.assertEqual(visibility.get("runtime_state"), "awaiting_clarification")
        self.assertEqual(visibility.get("clarification_question"), "Which app do you want?")
        self.assertEqual(visibility.get("next_step_hint"), "Try a more specific app or file name.")
        self.assertNotIn("failure_message", visibility)
        self.assertNotIn("completion_result", visibility)

    def test_failed_payload_prefers_specific_structured_hint(self) -> None:
        error = JarvisError(
            category=ErrorCategory.EXECUTION_ERROR,
            code=ErrorCode.UNSUPPORTED_ACTION,
            message="Window action unsupported.",
            details=None,
            blocking=False,
            terminal=True,
        )
        step = Step(
            id="step_1",
            action=StepAction.CLOSE_WINDOW,
            target=Target(type=TargetType.WINDOW, name="Main"),
            status=StepStatus.FAILED,
            requires_confirmation=False,
        )
        visibility = map_visibility(
            state="failed",
            command=Command(
                raw_input="close window main",
                intent=IntentType.CLOSE_WINDOW,
                targets=[Target(type=TargetType.WINDOW, name="Main")],
                parameters={},
                confidence=0.9,
                requires_confirmation=True,
                execution_steps=[step],
                status_message="Parsed",
            ),
            current_step=step,
            error=error,
        )

        self.assertIn("failure_message", visibility)
        self.assertEqual(visibility.get("next_step_hint"), "Try using the app name instead of a window reference.")
        self.assertNotIn("completion_result", visibility)

    def test_russian_completed_payload_localizes_generic_completion_result(self) -> None:
        step = Step(
            id="step_1",
            action=StepAction.OPEN_APP,
            target=Target(type=TargetType.APPLICATION, name="Telegram"),
            status=StepStatus.DONE,
            requires_confirmation=False,
        )
        visibility = map_visibility(
            state="completed",
            command=self._russian_command(),
            completed_steps=[step],
            completion_result="Completed open_app with 1 step(s).",
        )

        self.assertEqual(visibility.get("completion_result"), "Завершил open_app: 1 шаг.")

    def test_russian_awaiting_clarification_payload_localizes_question_and_hint(self) -> None:
        clarification = ClarificationRequest(
            message="Which app do you want?",
            code=ErrorCode.TARGET_NOT_FOUND.value,
            options=["Telegram", "Safari"],
        )
        error = JarvisError(
            category=ErrorCategory.VALIDATION_ERROR,
            code=ErrorCode.MULTIPLE_MATCHES,
            message="Multiple matching targets require clarification.",
            details=None,
            blocking=True,
            terminal=False,
        )
        visibility = map_visibility(
            state="awaiting_clarification",
            command=self._russian_command(),
            clarification=clarification,
            error=error,
        )

        self.assertEqual(visibility.get("clarification_question"), "Какое приложение ты имеешь в виду?")
        self.assertEqual(visibility.get("next_step_hint"), "Назови приложение или файл точнее.")

    def test_russian_awaiting_confirmation_payload_localizes_message_and_hint(self) -> None:
        confirmation = ConfirmationRequest(
            message="Approve close_app for Telegram?",
            affected_targets=[Target(type=TargetType.APPLICATION, name="Telegram")],
            boundary_type=ConfirmationBoundaryType.STEP,
        )
        visibility = map_visibility(
            state="awaiting_confirmation",
            command=Command(
                raw_input="закрой Telegram",
                intent=IntentType.CLOSE_APP,
                targets=[Target(type=TargetType.APPLICATION, name="Telegram")],
                parameters={},
                confidence=0.9,
                requires_confirmation=True,
                execution_steps=[],
                status_message="Parsed",
            ),
            confirmation=confirmation,
        )

        self.assertEqual(
            (visibility.get("confirmation_request") or {}).get("message"),
            "Подтвердить close_app для Telegram?",
        )
        self.assertEqual(visibility.get("next_step_hint"), "Скажи да, чтобы продолжить, или нет, чтобы отменить.")


if __name__ == "__main__":
    unittest.main()
