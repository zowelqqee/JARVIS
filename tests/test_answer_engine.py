"""Deterministic question-answer engine contract tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from context.session_context import SessionContext
from jarvis_error import ErrorCode, JarvisError
from qa.answer_backend import AnswerBackendKind
from qa.answer_engine import answer_question, classify_question


class AnswerEngineTests(unittest.TestCase):
    """Lock question classification and backend behavior for the new QA layer."""

    def test_capability_question_routes_to_capabilities_family(self) -> None:
        question = classify_question("What can you do?")

        self.assertEqual(getattr(question.question_type, "value", ""), "capabilities")
        self.assertEqual(question.scope, "capabilities")

    def test_capability_answer_mentions_command_support(self) -> None:
        result = answer_question("What can you do?")

        self.assertEqual(result.interaction_mode, "question")
        self.assertIn("open_app", result.answer_text)
        self.assertTrue(result.sources)

    def test_runtime_status_answer_reports_no_active_command(self) -> None:
        result = answer_question("What are you doing now?")

        self.assertIn("No active command", result.answer_text)
        self.assertTrue(result.sources)

    def test_runtime_status_can_use_recent_folder_context(self) -> None:
        session_context = SessionContext()
        session_context.set_recent_project_context("/tmp/demo")

        result = answer_question("What folder are you using?", session_context=session_context)

        self.assertIn("/tmp/demo", result.answer_text)

    def test_docs_rule_answer_is_grounded(self) -> None:
        result = answer_question("How does clarification work?")

        self.assertIn("Clarification", result.answer_text)
        self.assertGreaterEqual(len(result.sources), 2)

    def test_repo_structure_answer_points_to_planner_file(self) -> None:
        result = answer_question("Where is the planner?")

        self.assertIn("planner/execution_planner.py", result.answer_text)
        self.assertTrue(any(source.endswith("planner/execution_planner.py") for source in result.sources))

    def test_llm_backend_is_reserved_but_unavailable_in_v1(self) -> None:
        with self.assertRaises(JarvisError) as captured:
            answer_question("What can you do?", backend_kind=AnswerBackendKind.LLM)

        self.assertEqual(getattr(captured.exception.code, "value", ""), ErrorCode.MODEL_BACKEND_UNAVAILABLE.value)


if __name__ == "__main__":
    unittest.main()
