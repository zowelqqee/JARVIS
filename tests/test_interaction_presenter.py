"""Presenter contract tests for top-level interaction visibility."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from jarvis_error import ErrorCategory, ErrorCode, JarvisError
from interaction_kind import InteractionKind
from ui.interaction_presenter import interaction_output_lines, interaction_speech_message


class InteractionPresenterTests(unittest.TestCase):
    """Protect rendering and speech selection over unified interaction visibility."""

    def test_question_output_uses_visibility_fields(self) -> None:
        result = SimpleNamespace(
            interaction_mode=InteractionKind.QUESTION,
            visibility={
                "interaction_mode": "question",
                "answer_text": "I can open apps and answer grounded questions.",
                "answer_sources": ["/tmp/docs/product_rules.md", "/tmp/docs/question_answer_mode.md"],
                "answer_source_attributions": [
                    {
                        "source": "/tmp/docs/product_rules.md",
                        "support": "Product rules define supported command families.",
                    }
                ],
                "answer_warning": "Answer is limited to grounded local sources.",
            },
        )

        self.assertEqual(
            interaction_output_lines(result),
            [
                "mode: question",
                "answer: I can open apps and answer grounded questions.",
                "sources: /tmp/docs/product_rules.md, /tmp/docs/question_answer_mode.md",
                "evidence: /tmp/docs/product_rules.md -> Product rules define supported command families.",
                "warning: Answer is limited to grounded local sources.",
            ],
        )
        self.assertEqual(
            interaction_speech_message(result),
            "I can open apps and answer grounded questions.",
        )

    def test_question_failure_falls_back_to_structured_error(self) -> None:
        error = JarvisError(
            category=ErrorCategory.ANSWER_ERROR,
            code=ErrorCode.UNSUPPORTED_QUESTION,
            message="Question is outside the supported v1 grounded QA scope.",
            details=None,
            blocking=False,
            terminal=True,
        )
        result = SimpleNamespace(
            interaction_mode=InteractionKind.QUESTION,
            visibility={"interaction_mode": "question"},
            error=error,
        )

        self.assertEqual(
            interaction_output_lines(result),
            [
                "mode: question",
                "error: UNSUPPORTED_QUESTION: Question is outside the supported v1 grounded QA scope.",
            ],
        )
        self.assertEqual(
            interaction_speech_message(result),
            "UNSUPPORTED_QUESTION: Question is outside the supported v1 grounded QA scope.",
        )

    def test_clarification_output_uses_visibility_fields(self) -> None:
        result = SimpleNamespace(
            interaction_mode=InteractionKind.CLARIFICATION,
            visibility={
                "interaction_mode": "clarification",
                "clarification_question": "Do you want an answer first or should I execute the command?",
            },
        )

        self.assertEqual(
            interaction_output_lines(result),
            [
                "mode: clarification",
                "clarify: Do you want an answer first or should I execute the command?",
            ],
        )
        self.assertEqual(
            interaction_speech_message(result),
            "Do you want an answer first or should I execute the command?",
        )

    def test_command_output_uses_wrapped_interaction_visibility(self) -> None:
        result = SimpleNamespace(
            interaction_mode=InteractionKind.COMMAND,
            visibility={
                "interaction_mode": "command",
                "runtime_state": "completed",
                "command_summary": "open_app: Telegram",
                "completed_steps": ["step_1 open_app Telegram"],
                "completion_result": "Completed open_app with 1 step(s).",
            },
        )

        self.assertEqual(
            interaction_output_lines(result),
            [
                "state: completed",
                "command: open_app: Telegram",
                "done: step_1 open_app Telegram",
                "result: Completed open_app with 1 step(s).",
            ],
        )
        self.assertEqual(interaction_speech_message(result), "Completed open_app with 1 step(s).")

    def test_command_output_falls_back_to_runtime_visibility_when_needed(self) -> None:
        result = SimpleNamespace(
            interaction_mode=InteractionKind.COMMAND,
            visibility=None,
            runtime_result=SimpleNamespace(
                visibility={
                    "runtime_state": "awaiting_confirmation",
                    "confirmation_request": {"message": "Approve close_app for Telegram before execution."},
                }
            ),
        )

        self.assertEqual(
            interaction_output_lines(result),
            [
                "state: awaiting_confirmation",
                "confirm: Approve close_app for Telegram before execution.",
            ],
        )
        self.assertEqual(
            interaction_speech_message(result),
            "Approve close_app for Telegram before execution.",
        )


if __name__ == "__main__":
    unittest.main()
