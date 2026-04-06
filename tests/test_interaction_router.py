"""Deterministic interaction-router tests for command vs question routing."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from interaction.interaction_router import (
    RoutedInteraction,
    resolve_interaction_clarification_choice,
    route_interaction,
    split_mixed_interaction_input,
)

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from interaction_kind import InteractionKind


class InteractionRouterTests(unittest.TestCase):
    """Lock routing precedence for command mode and question mode."""

    def test_router_kind_alias_uses_shared_interaction_kind(self) -> None:
        self.assertIs(RoutedInteraction, InteractionKind)

    def test_imperative_open_routes_to_command(self) -> None:
        decision = route_interaction("Open Safari.")

        self.assertEqual(decision.kind, InteractionKind.COMMAND)

    def test_polite_execution_question_still_routes_to_command(self) -> None:
        decision = route_interaction("Can you open Safari?")

        self.assertEqual(decision.kind, InteractionKind.COMMAND)

    def test_how_to_question_routes_to_question(self) -> None:
        decision = route_interaction("How do you open Safari?")

        self.assertEqual(decision.kind, InteractionKind.QUESTION)

    def test_russian_open_domain_question_routes_to_question(self) -> None:
        decision = route_interaction("Кто президент Франции")

        self.assertEqual(decision.kind, InteractionKind.QUESTION)

    def test_russian_quantitative_question_routes_to_question(self) -> None:
        decision = route_interaction("Сколько планет во вселенной")

        self.assertEqual(decision.kind, InteractionKind.QUESTION)

    def test_repeat_that_routes_to_question(self) -> None:
        decision = route_interaction("Repeat that")

        self.assertEqual(decision.kind, InteractionKind.QUESTION)

    def test_greeting_routes_to_question_instead_of_fallback_command(self) -> None:
        decision = route_interaction("hello jarvis")

        self.assertEqual(decision.kind, InteractionKind.QUESTION)

    def test_bare_wake_word_routes_to_question_instead_of_fallback_command(self) -> None:
        decision = route_interaction("Джарвис")

        self.assertEqual(decision.kind, InteractionKind.QUESTION)

    def test_short_jarvis_greeting_misrecognition_routes_to_question(self) -> None:
        decision = route_interaction("Previous Jarvis")

        self.assertEqual(decision.kind, InteractionKind.QUESTION)

    def test_compare_request_routes_to_question(self) -> None:
        decision = route_interaction("Сравни ChatGPT с Claude")

        self.assertEqual(decision.kind, InteractionKind.QUESTION)

    def test_mixed_question_and_command_routes_to_clarification(self) -> None:
        decision = route_interaction("What can you do and open Safari")

        self.assertEqual(decision.kind, InteractionKind.CLARIFICATION)
        self.assertEqual(
            decision.clarification_message,
            "Do you want an answer first or should I open Safari?",
        )
        self.assertEqual(decision.question_input, "What can you do")
        self.assertEqual(decision.command_input, "open Safari")

    def test_russian_question_with_normalized_embedded_command_routes_to_clarification(self) -> None:
        decision = route_interaction("Что ты умеешь and open Safari")

        self.assertEqual(decision.kind, InteractionKind.CLARIFICATION)
        self.assertEqual(decision.question_input, "Что ты умеешь")
        self.assertEqual(decision.command_input, "open Safari")

    def test_split_mixed_interaction_input_extracts_question_and_command(self) -> None:
        question_input, command_input = split_mixed_interaction_input("Why are you blocked and open Safari.")

        self.assertEqual(question_input, "Why are you blocked")
        self.assertEqual(command_input, "open Safari")

    def test_clarification_choice_resolves_answer_and_execute_replies(self) -> None:
        self.assertEqual(resolve_interaction_clarification_choice("answer"), "answer")
        self.assertEqual(resolve_interaction_clarification_choice("Answer first"), "answer")
        self.assertEqual(resolve_interaction_clarification_choice("just answer"), "answer")
        self.assertEqual(resolve_interaction_clarification_choice("please answer"), "answer")
        self.assertEqual(resolve_interaction_clarification_choice("ответить"), "answer")
        self.assertEqual(resolve_interaction_clarification_choice("сначала ответ"), "answer")
        self.assertEqual(resolve_interaction_clarification_choice("execute the command"), "execute")
        self.assertEqual(resolve_interaction_clarification_choice("please run the command"), "execute")
        self.assertEqual(resolve_interaction_clarification_choice("go ahead"), "execute")
        self.assertEqual(resolve_interaction_clarification_choice("do it"), "execute")
        self.assertEqual(resolve_interaction_clarification_choice("open it"), "execute")
        self.assertEqual(resolve_interaction_clarification_choice("выполнить"), "execute")
        self.assertEqual(resolve_interaction_clarification_choice("команду"), "execute")
        self.assertIsNone(resolve_interaction_clarification_choice("yes"))

    def test_blocked_state_question_routes_to_question_path(self) -> None:
        decision = route_interaction("What exactly do you need me to confirm?", runtime_state="awaiting_confirmation")

        self.assertEqual(decision.kind, InteractionKind.QUESTION)
        self.assertEqual(decision.reason, "blocked_state_question")

    def test_russian_blocked_state_question_routes_to_question_path(self) -> None:
        decision = route_interaction("Что именно тебе нужно подтвердить?", runtime_state="awaiting_confirmation")

        self.assertEqual(decision.kind, InteractionKind.QUESTION)
        self.assertEqual(decision.reason, "blocked_state_question")

    def test_generic_question_escapes_clarification_blocked_state(self) -> None:
        decision = route_interaction("What can you do?", runtime_state="awaiting_clarification")

        self.assertEqual(decision.kind, InteractionKind.QUESTION)
        self.assertEqual(decision.reason, "blocked_state_question")

    def test_greeting_escapes_clarification_blocked_state(self) -> None:
        decision = route_interaction("hello", runtime_state="awaiting_clarification")

        self.assertEqual(decision.kind, InteractionKind.QUESTION)
        self.assertEqual(decision.reason, "blocked_state_question")

    def test_short_target_like_safari_question_mark_stays_command_in_clarification_state(self) -> None:
        decision = route_interaction("Safari?", runtime_state="awaiting_clarification")

        self.assertEqual(decision.kind, InteractionKind.COMMAND)
        self.assertEqual(decision.reason, "blocked_state_priority")

    def test_recent_answer_follow_up_routes_to_question_when_recent_context_exists(self) -> None:
        session_context = SimpleNamespace(get_recent_answer_context=lambda: {"topic": "capabilities"})

        decision = route_interaction("подробнее", session_context=session_context)

        self.assertEqual(decision.kind, InteractionKind.QUESTION)
        self.assertEqual(decision.reason, "recent_answer_follow_up")

    def test_recent_answer_follow_up_stays_fallback_without_recent_context(self) -> None:
        session_context = SimpleNamespace(get_recent_answer_context=lambda: None)

        decision = route_interaction("подробнее", session_context=session_context)

        self.assertEqual(decision.kind, InteractionKind.COMMAND)
        self.assertEqual(decision.reason, "fallback_command")

    def test_blocked_state_priority_for_confirmation_reply_keeps_command_path(self) -> None:
        decision = route_interaction("yes", runtime_state="awaiting_confirmation")

        self.assertEqual(decision.kind, InteractionKind.COMMAND)
        self.assertEqual(decision.reason, "blocked_state_priority")

    def test_blocked_state_priority_for_russian_confirmation_reply_keeps_command_path(self) -> None:
        decision = route_interaction("да", runtime_state="awaiting_confirmation")

        self.assertEqual(decision.kind, InteractionKind.COMMAND)
        self.assertEqual(decision.reason, "blocked_state_priority")


if __name__ == "__main__":
    unittest.main()
