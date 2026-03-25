"""Deterministic question-answer engine contract tests."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from context.session_context import SessionContext
from qa.answer_backend import AnswerBackendKind
from qa.answer_config import AnswerBackendConfig, LlmBackendConfig
from qa.answer_engine import answer_question, classify_question
from jarvis_error import ErrorCode, JarvisError
from target import Target, TargetType


class AnswerEngineTests(unittest.TestCase):
    """Lock question classification and backend behavior for the new QA layer."""

    @property
    def repo_root(self) -> Path:
        return Path(__file__).resolve().parents[1]

    def test_capability_question_routes_to_capabilities_family(self) -> None:
        question = classify_question("What can you do?")

        self.assertEqual(getattr(question.question_type, "value", ""), "capabilities")
        self.assertEqual(question.scope, "capabilities")

    def test_capability_answer_mentions_command_support(self) -> None:
        result = answer_question("What can you do?")

        self.assertEqual(result.interaction_mode, "question")
        self.assertIn("open_app", result.answer_text)
        self.assertTrue(result.sources)
        self.assertTrue(result.source_attributions)
        self.assertEqual(result.source_attributions[0].source, result.sources[0])
        self.assertIn("Capability catalog", result.source_attributions[0].support)

    def test_runtime_status_answer_reports_no_active_command(self) -> None:
        result = answer_question("What are you doing now?")

        self.assertIn("No active command", result.answer_text)
        self.assertTrue(result.sources)

    def test_blocked_state_question_routes_to_blocked_state_family(self) -> None:
        question = classify_question("What exactly do you need me to confirm?")

        self.assertEqual(getattr(question.question_type, "value", ""), "blocked_state")

    def test_blocked_state_answer_uses_confirmation_snapshot(self) -> None:
        result = answer_question(
            "What exactly do you need me to confirm?",
            runtime_snapshot={
                "runtime_state": "awaiting_confirmation",
                "blocked_kind": "confirmation",
                "blocked_reason": "Approve close_app for Telegram before execution.",
                "confirmation_message": "Approve close_app for Telegram before execution.",
            },
        )

        self.assertIn("confirm", result.answer_text.lower())
        self.assertIn("Telegram", result.answer_text)
        self.assertGreaterEqual(len(result.sources), 3)

    def test_blocked_state_without_active_command_reports_no_active_command_reason(self) -> None:
        with self.assertRaises(JarvisError) as captured:
            answer_question("What exactly do you need me to confirm?")

        self.assertEqual(getattr(captured.exception.code, "value", ""), ErrorCode.INSUFFICIENT_CONTEXT.value)
        self.assertEqual((captured.exception.details or {}).get("reason"), "no_active_command")

    def test_recent_runtime_answer_reports_last_command(self) -> None:
        result = answer_question(
            "What command did you run last?",
            runtime_snapshot={
                "runtime_state": "idle",
                "command_summary": "open_app: Safari",
            },
        )

        self.assertIn("open_app: Safari", result.answer_text)
        self.assertGreaterEqual(len(result.sources), 2)

    def test_recent_runtime_answer_can_report_last_target_from_session_context(self) -> None:
        session_context = SessionContext()
        session_context.set_recent_primary_target(
            Target(type=TargetType.APPLICATION, name="Safari"),
            action="open_app",
        )

        result = answer_question(
            "What app did you open last?",
            session_context=session_context,
        )

        self.assertIn("Safari", result.answer_text)
        self.assertGreaterEqual(len(result.sources), 2)

    def test_recent_runtime_missing_target_reports_no_recent_target_reason(self) -> None:
        with self.assertRaises(JarvisError) as captured:
            answer_question("What app did you open last?")

        self.assertEqual(getattr(captured.exception.code, "value", ""), ErrorCode.INSUFFICIENT_CONTEXT.value)
        self.assertEqual((captured.exception.details or {}).get("reason"), "no_recent_target")

    def test_answer_follow_up_requires_recent_answer_context(self) -> None:
        with self.assertRaises(JarvisError) as captured:
            answer_question("Which source?")

        self.assertEqual(getattr(captured.exception.code, "value", ""), ErrorCode.INSUFFICIENT_CONTEXT.value)
        self.assertEqual((captured.exception.details or {}).get("reason"), "no_recent_answer")

    def test_answer_follow_up_classification_uses_recent_answer_context(self) -> None:
        session_context = SessionContext()
        session_context.set_recent_answer_context(
            topic="clarification",
            scope="docs",
            sources=[
                str(self.repo_root / "docs/clarification_rules.md"),
                str(self.repo_root / "docs/runtime_flow.md"),
            ],
        )

        question = classify_question("Why?", session_context=session_context)

        self.assertEqual(getattr(question.question_type, "value", ""), "answer_follow_up")
        self.assertEqual(question.scope, "docs")
        self.assertEqual((question.context_refs or {}).get("answer_topic"), "clarification")

    def test_answer_follow_up_can_point_to_recent_sources(self) -> None:
        session_context = SessionContext()
        session_context.set_recent_answer_context(
            topic="clarification",
            scope="docs",
            sources=[
                str(self.repo_root / "docs/clarification_rules.md"),
                str(self.repo_root / "docs/runtime_flow.md"),
            ],
        )

        result = answer_question("Which source?", session_context=session_context)

        self.assertIn("docs/clarification_rules.md", result.answer_text)
        self.assertTrue(any(source.endswith("docs/clarification_rules.md") for source in result.sources))

    def test_answer_follow_up_explain_more_stays_grounded(self) -> None:
        session_context = SessionContext()
        session_context.set_recent_answer_context(
            topic="clarification",
            scope="docs",
            sources=[
                str(self.repo_root / "docs/clarification_rules.md"),
                str(self.repo_root / "docs/runtime_flow.md"),
            ],
        )

        result = answer_question("Explain more", session_context=session_context)

        self.assertIn("clarification happens", result.answer_text.lower())
        self.assertGreaterEqual(len(result.sources), 2)

    def test_runtime_status_can_use_recent_folder_context(self) -> None:
        session_context = SessionContext()
        session_context.set_recent_project_context("/tmp/demo")

        result = answer_question("What folder are you using?", session_context=session_context)

        self.assertIn("/tmp/demo", result.answer_text)

    def test_docs_rule_answer_is_grounded(self) -> None:
        result = answer_question("How does clarification work?")

        self.assertIn("Clarification", result.answer_text)
        self.assertGreaterEqual(len(result.sources), 2)
        self.assertIn("Clarification rules define", result.source_attributions[0].support)

    def test_repo_structure_answer_points_to_planner_file(self) -> None:
        result = answer_question("Where is the planner?")

        self.assertIn("planner/execution_planner.py", result.answer_text)
        self.assertTrue(any(source.endswith("planner/execution_planner.py") for source in result.sources))

    def test_open_domain_question_routes_to_general_family_when_enabled(self) -> None:
        question = classify_question(
            "Who is the president of France?",
            backend_config=AnswerBackendConfig(
                backend_kind=AnswerBackendKind.LLM,
                llm=LlmBackendConfig(enabled=True, open_domain_enabled=True),
            ),
        )

        self.assertEqual(getattr(question.question_type, "value", ""), "open_domain_general")
        self.assertEqual(question.scope, "open_domain")
        self.assertFalse(question.requires_grounding)

    def test_open_domain_question_fails_honestly_when_provider_is_unavailable(self) -> None:
        config = AnswerBackendConfig(
            backend_kind=AnswerBackendKind.LLM,
            llm=LlmBackendConfig(
                enabled=True,
                open_domain_enabled=True,
                api_key_env="MISSING_KEY",
                fallback_enabled=True,
            ),
        )

        with patch.dict(os.environ, {}, clear=False), self.assertRaises(JarvisError) as captured:
            answer_question("Who is the president of France?", backend_config=config)

        self.assertEqual(getattr(captured.exception.code, "value", ""), ErrorCode.MODEL_BACKEND_UNAVAILABLE.value)

    def test_llm_backend_falls_back_to_deterministic_with_warning(self) -> None:
        result = answer_question("What can you do?", backend_kind=AnswerBackendKind.LLM)

        self.assertIn("open_app", result.answer_text)
        self.assertTrue(result.sources)
        self.assertTrue(result.source_attributions)
        self.assertIn("LLM backend fallback", str(result.warning))


if __name__ == "__main__":
    unittest.main()
