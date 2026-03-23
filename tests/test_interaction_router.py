"""Deterministic interaction-router tests for command vs question routing."""

from __future__ import annotations

import unittest

from interaction.interaction_router import RoutedInteraction, route_interaction


class InteractionRouterTests(unittest.TestCase):
    """Lock routing precedence for command mode and question mode."""

    def test_imperative_open_routes_to_command(self) -> None:
        decision = route_interaction("Open Safari.")

        self.assertEqual(decision.kind, RoutedInteraction.COMMAND)

    def test_polite_execution_question_still_routes_to_command(self) -> None:
        decision = route_interaction("Can you open Safari?")

        self.assertEqual(decision.kind, RoutedInteraction.COMMAND)

    def test_how_to_question_routes_to_question(self) -> None:
        decision = route_interaction("How do you open Safari?")

        self.assertEqual(decision.kind, RoutedInteraction.QUESTION)

    def test_mixed_question_and_command_routes_to_clarification(self) -> None:
        decision = route_interaction("What can you do and open Safari")

        self.assertEqual(decision.kind, RoutedInteraction.CLARIFICATION)
        self.assertIn("answer", decision.clarification_message or "")

    def test_blocked_state_priority_for_confirmation_keeps_command_path(self) -> None:
        decision = route_interaction("Why are you waiting?", runtime_state="awaiting_confirmation")

        self.assertEqual(decision.kind, RoutedInteraction.COMMAND)
        self.assertEqual(decision.reason, "blocked_state_priority")


if __name__ == "__main__":
    unittest.main()
