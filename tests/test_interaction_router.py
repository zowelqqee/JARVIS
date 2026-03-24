"""Deterministic interaction-router tests for command vs question routing."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

from interaction.interaction_router import RoutedInteraction, route_interaction

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

    def test_mixed_question_and_command_routes_to_clarification(self) -> None:
        decision = route_interaction("What can you do and open Safari")

        self.assertEqual(decision.kind, InteractionKind.CLARIFICATION)
        self.assertIn("answer", decision.clarification_message or "")

    def test_blocked_state_question_routes_to_question_path(self) -> None:
        decision = route_interaction("What exactly do you need me to confirm?", runtime_state="awaiting_confirmation")

        self.assertEqual(decision.kind, InteractionKind.QUESTION)
        self.assertEqual(decision.reason, "blocked_state_question")

    def test_blocked_state_priority_for_confirmation_reply_keeps_command_path(self) -> None:
        decision = route_interaction("yes", runtime_state="awaiting_confirmation")

        self.assertEqual(decision.kind, InteractionKind.COMMAND)
        self.assertEqual(decision.reason, "blocked_state_priority")


if __name__ == "__main__":
    unittest.main()
