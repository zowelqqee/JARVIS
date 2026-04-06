"""Contract tests for topic-aware QA source selection."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from jarvis_error import ErrorCode, JarvisError
from qa.answer_engine import classify_question
from qa.grounding import build_grounding_bundle
from question_request import QuestionRequest, QuestionType


class SourceSelectorTests(unittest.TestCase):
    """Lock the grounded source registry and selector behavior."""

    def test_clarification_docs_question_uses_section_aware_source_metadata(self) -> None:
        question = classify_question("How does clarification work?")

        bundle = build_grounding_bundle(question)

        self.assertGreaterEqual(len(bundle.sources), 2)
        self.assertTrue(bundle.source_paths[0].endswith("docs/clarification_rules.md"))
        self.assertEqual(bundle.sources[0].section_hint, "When Clarification Is Required")
        self.assertIn("Clarification rules define", bundle.sources[0].support)

    def test_repo_structure_answer_engine_question_uses_registry_backed_sources(self) -> None:
        question = classify_question("Which module handles question-answer mode?")

        bundle = build_grounding_bundle(question)

        self.assertTrue(any(source.path.endswith("qa/source_selector.py") for source in bundle.sources))
        self.assertTrue(any(source.path.endswith("qa/source_registry.py") for source in bundle.sources))

    def test_explicit_unmapped_topic_reports_source_not_mapped_reason(self) -> None:
        question = QuestionRequest(
            raw_input="How does routing work?",
            question_type=QuestionType.DOCS_RULES,
            scope="docs",
            context_refs={"topic": "routing"},
            confidence=0.88,
        )

        with self.assertRaises(JarvisError) as captured:
            build_grounding_bundle(question)

        self.assertEqual(getattr(captured.exception.code, "value", ""), ErrorCode.SOURCE_NOT_AVAILABLE.value)
        self.assertEqual((captured.exception.details or {}).get("reason"), "source_not_mapped")

    def test_answer_follow_up_reuses_recent_answer_source_metadata(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        question = QuestionRequest(
            raw_input="Which source?",
            question_type=QuestionType.ANSWER_FOLLOW_UP,
            scope="docs",
            context_refs={
                "follow_up_kind": "which_source",
                "answer_topic": "clarification",
                "answer_scope": "docs",
                "answer_sources": [
                    str(repo_root / "docs/clarification_rules.md"),
                    str(repo_root / "docs/runtime_flow.md"),
                ],
            },
            confidence=0.9,
        )

        bundle = build_grounding_bundle(question)

        self.assertGreaterEqual(len(bundle.sources), 2)
        self.assertTrue(bundle.source_paths[0].endswith("docs/clarification_rules.md"))
        self.assertEqual(bundle.sources[0].section_hint, "When Clarification Is Required")

    def test_model_knowledge_explain_more_follow_up_can_build_empty_grounding_bundle(self) -> None:
        question = QuestionRequest(
            raw_input="Explain more",
            question_type=QuestionType.ANSWER_FOLLOW_UP,
            scope="open_domain",
            context_refs={
                "follow_up_kind": "explain_more",
                "answer_topic": "open_domain_general",
                "answer_scope": "open_domain",
                "answer_sources": [],
                "answer_kind": "open_domain_model",
                "answer_provenance": "model_knowledge",
                "answer_text": "Tony Stark is a fictional Marvel character.",
            },
            confidence=0.9,
        )

        bundle = build_grounding_bundle(question)

        self.assertEqual(bundle.scope, "open_domain")
        self.assertEqual(bundle.source_paths, [])


if __name__ == "__main__":
    unittest.main()
