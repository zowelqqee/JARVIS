"""Contract tests for the shared interaction-kind vocabulary."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

from interaction.interaction_router import RoutedInteraction

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from answer_result import AnswerKind, AnswerProvenance, AnswerResult
from interaction_kind import InteractionKind
from interaction_result import InteractionMode


class InteractionKindContractTests(unittest.TestCase):
    """Freeze the shared interaction vocabulary and compatibility aliases."""

    def test_vocabulary_is_frozen(self) -> None:
        self.assertEqual([kind.value for kind in InteractionKind], ["command", "question", "clarification"])

    def test_router_and_result_aliases_use_shared_type(self) -> None:
        self.assertIs(RoutedInteraction, InteractionKind)
        self.assertIs(InteractionMode, InteractionKind)

    def test_answer_result_defaults_to_shared_question_kind(self) -> None:
        result = AnswerResult(answer_text="Grounded answer.")

        self.assertIsInstance(result.interaction_mode, InteractionKind)
        self.assertEqual(str(result.interaction_mode), "question")
        self.assertEqual(result.answer_kind, AnswerKind.GROUNDED_LOCAL)
        self.assertEqual(result.provenance, AnswerProvenance.LOCAL_SOURCES)


if __name__ == "__main__":
    unittest.main()
