"""Visibility payload contract tests for top-level dual-mode interactions."""

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
from ui.visibility_mapper import map_interaction_visibility


class InteractionVisibilityContractTests(unittest.TestCase):
    """Lock additive visibility rules for question and clarification modes."""

    def test_question_answer_payload_contains_answer_fields(self) -> None:
        visibility = map_interaction_visibility(
            interaction_mode=InteractionKind.QUESTION,
            answer_result=SimpleNamespace(
                answer_text="I can open apps and answer grounded questions.",
                sources=["/tmp/docs/product_rules.md"],
                source_attributions=[
                    SimpleNamespace(
                        source="/tmp/docs/product_rules.md",
                        support="Product rules ground the supported capability boundary.",
                    )
                ],
                warning="Answer is limited to grounded local sources.",
            ),
        )

        self.assertEqual(visibility.get("interaction_mode"), "question")
        self.assertEqual(visibility.get("answer_text"), "I can open apps and answer grounded questions.")
        self.assertEqual(visibility.get("answer_summary"), "I can open apps and answer grounded questions.")
        self.assertEqual(visibility.get("answer_kind"), "grounded_local")
        self.assertEqual(visibility.get("answer_provenance"), "local_sources")
        self.assertEqual(visibility.get("answer_sources"), ["/tmp/docs/product_rules.md"])
        self.assertEqual(visibility.get("answer_source_labels"), ["Product Rules"])
        self.assertEqual(
            visibility.get("answer_source_attributions"),
            [
                {
                    "source": "/tmp/docs/product_rules.md",
                    "support": "Product rules ground the supported capability boundary.",
                }
            ],
        )
        self.assertEqual(visibility.get("answer_warning"), "Answer is limited to grounded local sources.")
        self.assertEqual(visibility.get("can_cancel"), False)
        self.assertNotIn("runtime_state", visibility)

    def test_question_answer_payload_supports_model_answer_without_local_sources(self) -> None:
        visibility = map_interaction_visibility(
            interaction_mode=InteractionKind.QUESTION,
            answer_result=SimpleNamespace(
                answer_text="Blue light scatters more strongly in the atmosphere than red light.",
                answer_kind="open_domain_model",
                provenance="model_knowledge",
                sources=[],
                source_attributions=[],
                warning="This answer is based on model knowledge, not local sources.",
            ),
        )

        self.assertEqual(visibility.get("interaction_mode"), "question")
        self.assertEqual(visibility.get("answer_kind"), "open_domain_model")
        self.assertEqual(visibility.get("answer_provenance"), "model_knowledge")
        self.assertNotIn("answer_sources", visibility)
        self.assertNotIn("answer_source_labels", visibility)
        self.assertNotIn("answer_source_attributions", visibility)
        self.assertEqual(
            visibility.get("answer_warning"),
            "This answer is based on model knowledge, not local sources.",
        )

    def test_question_failure_payload_contains_failure_message(self) -> None:
        error = JarvisError(
            category=ErrorCategory.ANSWER_ERROR,
            code=ErrorCode.UNSUPPORTED_QUESTION,
            message="Question is outside the supported v1 grounded QA scope.",
            details=None,
            blocking=False,
            terminal=True,
        )

        visibility = map_interaction_visibility(
            interaction_mode=InteractionKind.QUESTION,
            error=error,
        )

        self.assertEqual(visibility.get("interaction_mode"), "question")
        self.assertEqual(
            visibility.get("failure_message"),
            "UNSUPPORTED_QUESTION: Question is outside the supported v1 grounded QA scope.",
        )
        self.assertEqual(visibility.get("can_cancel"), False)
        self.assertNotIn("answer_text", visibility)

    def test_clarification_payload_contains_blocked_reason_and_question(self) -> None:
        visibility = map_interaction_visibility(
            interaction_mode=InteractionKind.CLARIFICATION,
            clarification_request=SimpleNamespace(
                message="Do you want an answer first or should I open Safari?"
            ),
        )

        self.assertEqual(visibility.get("interaction_mode"), "clarification")
        self.assertEqual(
            visibility.get("clarification_question"),
            "Do you want an answer first or should I open Safari?",
        )
        self.assertEqual(
            visibility.get("blocked_reason"),
            "Do you want an answer first or should I open Safari?",
        )
        self.assertEqual(visibility.get("can_cancel"), False)

    def test_command_payload_wraps_existing_runtime_visibility(self) -> None:
        runtime_result = SimpleNamespace(
            runtime_state="completed",
            visibility={
                "runtime_state": "completed",
                "command_summary": "open_app: Telegram",
                "completed_steps": ["step_1 open_app Telegram"],
                "completion_result": "Completed open_app with 1 step(s).",
                "can_cancel": False,
            },
        )

        visibility = map_interaction_visibility(
            interaction_mode=InteractionKind.COMMAND,
            runtime_result=runtime_result,
        )

        self.assertEqual(visibility.get("interaction_mode"), "command")
        self.assertEqual(visibility.get("runtime_state"), "completed")
        self.assertEqual(visibility.get("command_summary"), "open_app: Telegram")
        self.assertEqual(visibility.get("completed_steps"), ["step_1 open_app Telegram"])
        self.assertEqual(visibility.get("completion_result"), "Completed open_app with 1 step(s).")
        self.assertNotIn("answer_text", visibility)


if __name__ == "__main__":
    unittest.main()
