"""Contract tests for the opt-in OpenAI live smoke path."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from answer_result import AnswerResult, AnswerSourceAttribution
from qa.answer_backend import AnswerBackendKind
from tests.smoke_openai_responses_provider_live import (
    live_smoke_config,
    live_smoke_enabled,
    live_smoke_question,
    live_smoke_result_issues,
    live_smoke_skip_reason,
)


class OpenAILiveSmokeContractTests(unittest.TestCase):
    """Protect gating and config for the manual live smoke script."""

    def test_live_smoke_is_disabled_by_default(self) -> None:
        self.assertFalse(live_smoke_enabled({}))
        self.assertIn("JARVIS_QA_OPENAI_LIVE_SMOKE", str(live_smoke_skip_reason({})))

    def test_live_smoke_requires_api_key_when_enabled(self) -> None:
        reason = live_smoke_skip_reason({"JARVIS_QA_OPENAI_LIVE_SMOKE": "1"})

        self.assertIsNotNone(reason)
        self.assertIn("OPENAI_API_KEY", str(reason))

    def test_live_smoke_config_is_strict_llm_mode(self) -> None:
        config = live_smoke_config(
            {
                "JARVIS_QA_OPENAI_LIVE_SMOKE": "1",
                "OPENAI_API_KEY": "test-key",
                "JARVIS_QA_OPENAI_LIVE_QUESTION": "How does clarification work?",
            }
        )

        self.assertEqual(getattr(config.backend_kind, "value", ""), AnswerBackendKind.LLM.value)
        self.assertTrue(config.llm.enabled)
        self.assertFalse(config.llm.fallback_enabled)
        self.assertEqual(config.llm.api_key_env, "OPENAI_API_KEY")
        self.assertEqual(config.llm.model, "gpt-5-nano")
        self.assertEqual(config.llm.reasoning_effort, "minimal")
        self.assertTrue(config.llm.strict_mode)
        self.assertEqual(live_smoke_question({"JARVIS_QA_OPENAI_LIVE_QUESTION": "How does clarification work?"}), "How does clarification work?")

    def test_live_smoke_result_contract_accepts_grounded_llm_answer(self) -> None:
        issues = live_smoke_result_issues(
            AnswerResult(
                answer_text="I can answer grounded capability and runtime questions.",
                sources=["/Users/arseniyabramidze/JARVIS/docs/question_answer_mode.md"],
                source_attributions=[
                    AnswerSourceAttribution(
                        source="/Users/arseniyabramidze/JARVIS/docs/question_answer_mode.md",
                        support="QA mode is read-only and grounded.",
                    )
                ],
            )
        )

        self.assertEqual(issues, [])

    def test_live_smoke_result_contract_rejects_missing_source_attributions(self) -> None:
        issues = live_smoke_result_issues(
            AnswerResult(
                answer_text="I can answer grounded capability questions.",
                sources=["/Users/arseniyabramidze/JARVIS/docs/question_answer_mode.md"],
            )
        )

        self.assertIn("source_attributions must be non-empty", issues)

    def test_live_smoke_result_contract_rejects_fallback_warning(self) -> None:
        issues = live_smoke_result_issues(
            AnswerResult(
                answer_text="I can answer grounded capability questions.",
                sources=["/Users/arseniyabramidze/JARVIS/docs/question_answer_mode.md"],
                source_attributions=[
                    AnswerSourceAttribution(
                        source="/Users/arseniyabramidze/JARVIS/docs/question_answer_mode.md",
                        support="QA mode is grounded.",
                    )
                ],
                warning="LLM backend fallback: ANSWER_NOT_GROUNDED",
            )
        )

        self.assertIn("live smoke must not pass through deterministic fallback", issues)

    def test_live_smoke_result_contract_rejects_attribution_outside_sources(self) -> None:
        issues = live_smoke_result_issues(
            AnswerResult(
                answer_text="I can answer grounded capability questions.",
                sources=["/Users/arseniyabramidze/JARVIS/docs/question_answer_mode.md"],
                source_attributions=[
                    AnswerSourceAttribution(
                        source="/Users/arseniyabramidze/JARVIS/docs/runtime_flow.md",
                        support="Routing is defined here.",
                    )
                ],
            )
        )

        self.assertIn("each source_attribution source must be present in sources", issues)

    def test_live_smoke_result_contract_rejects_generic_support_text(self) -> None:
        issues = live_smoke_result_issues(
            AnswerResult(
                answer_text="I can answer grounded capability questions.",
                sources=["/Users/arseniyabramidze/JARVIS/docs/question_answer_mode.md"],
                source_attributions=[
                    AnswerSourceAttribution(
                        source="/Users/arseniyabramidze/JARVIS/docs/question_answer_mode.md",
                        support="Documentation source.",
                    )
                ],
            )
        )

        self.assertIn("each source_attribution support must be specific and claim-bearing", issues)


if __name__ == "__main__":
    unittest.main()
