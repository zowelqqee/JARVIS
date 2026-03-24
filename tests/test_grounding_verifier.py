"""Grounding verifier contract tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from answer_result import AnswerResult, AnswerSourceAttribution
from jarvis_error import ErrorCode, JarvisError
from qa.grounding_verifier import ensure_source_attributions, parse_source_attributions, support_is_meaningful, verify_grounded_answer


class GroundingVerifierTests(unittest.TestCase):
    """Lock shared grounding and attribution policy across QA backends."""

    def test_ensure_source_attributions_populates_generic_support(self) -> None:
        result = AnswerResult(
            answer_text="Grounded answer.",
            sources=[
                "/Users/arseniyabramidze/JARVIS/docs/question_answer_mode.md",
                "/Users/arseniyabramidze/JARVIS/qa/capability_catalog.py",
            ],
        )

        normalized = ensure_source_attributions(result)

        self.assertEqual(len(normalized.source_attributions), 2)
        self.assertEqual(normalized.source_attributions[0].source, result.sources[0])
        self.assertEqual(normalized.source_attributions[0].support, "Documentation grounding source for this answer.")
        self.assertEqual(normalized.source_attributions[1].support, "Capability metadata grounding source for this answer.")

    def test_parse_source_attributions_rejects_non_object_entry(self) -> None:
        with self.assertRaises(JarvisError) as captured:
            parse_source_attributions(["not-an-object"])

        self.assertEqual(getattr(captured.exception.code, "value", ""), ErrorCode.ANSWER_GENERATION_FAILED.value)

    def test_verify_grounded_answer_dedupes_sources_from_attributions(self) -> None:
        verified = verify_grounded_answer(
            answer_text="I support grounded answers.",
            source_attributions=[
                AnswerSourceAttribution(
                    source="/Users/arseniyabramidze/JARVIS/docs/question_answer_mode.md",
                    support="QA mode is grounded.",
                ),
                AnswerSourceAttribution(
                    source="/Users/arseniyabramidze/JARVIS/docs/question_answer_mode.md",
                    support="Answer mode is read-only.",
                ),
            ],
            allowed_sources=["/Users/arseniyabramidze/JARVIS/docs/question_answer_mode.md"],
            grounded=True,
        )

        self.assertEqual(
            verified.sources,
            ["/Users/arseniyabramidze/JARVIS/docs/question_answer_mode.md"],
        )
        self.assertEqual(len(verified.source_attributions), 2)

    def test_verify_grounded_answer_rejects_out_of_bundle_source(self) -> None:
        with self.assertRaises(JarvisError) as captured:
            verify_grounded_answer(
                answer_text="I support grounded answers.",
                source_attributions=[
                    AnswerSourceAttribution(
                        source="/tmp/not-allowed.md",
                        support="Unsupported source.",
                    )
                ],
                allowed_sources=["/Users/arseniyabramidze/JARVIS/docs/question_answer_mode.md"],
                grounded=True,
            )

        self.assertEqual(getattr(captured.exception.code, "value", ""), ErrorCode.ANSWER_NOT_GROUNDED.value)

    def test_verify_grounded_answer_rejects_execution_implication(self) -> None:
        with self.assertRaises(JarvisError) as captured:
            verify_grounded_answer(
                answer_text="I opened Safari for you.",
                source_attributions=[
                    AnswerSourceAttribution(
                        source="/Users/arseniyabramidze/JARVIS/docs/question_answer_mode.md",
                        support="QA mode must stay read-only.",
                    )
                ],
                allowed_sources=["/Users/arseniyabramidze/JARVIS/docs/question_answer_mode.md"],
                grounded=True,
            )

        self.assertEqual(getattr(captured.exception.code, "value", ""), ErrorCode.ANSWER_NOT_GROUNDED.value)

    def test_support_is_meaningful_rejects_generic_support_text(self) -> None:
        self.assertFalse(support_is_meaningful("Unsupported source."))
        self.assertFalse(
            support_is_meaningful(
                "/Users/arseniyabramidze/JARVIS/docs/question_answer_mode.md",
                source="/Users/arseniyabramidze/JARVIS/docs/question_answer_mode.md",
            )
        )
        self.assertTrue(support_is_meaningful("QA mode is read-only and grounded."))

    def test_verify_grounded_answer_rejects_weak_support_text(self) -> None:
        with self.assertRaises(JarvisError) as captured:
            verify_grounded_answer(
                answer_text="I support grounded answers.",
                source_attributions=[
                    AnswerSourceAttribution(
                        source="/Users/arseniyabramidze/JARVIS/docs/question_answer_mode.md",
                        support="Documentation source.",
                    )
                ],
                allowed_sources=["/Users/arseniyabramidze/JARVIS/docs/question_answer_mode.md"],
                grounded=True,
            )

        self.assertEqual(getattr(captured.exception.code, "value", ""), ErrorCode.ANSWER_NOT_GROUNDED.value)


if __name__ == "__main__":
    unittest.main()
