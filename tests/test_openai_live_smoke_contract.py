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
    live_smoke_artifact_path,
    live_smoke_artifact_payload,
    live_smoke_config,
    live_smoke_diagnostics,
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

    def test_live_smoke_config_can_enable_open_domain_explicitly(self) -> None:
        config = live_smoke_config(
            {
                "JARVIS_QA_OPENAI_LIVE_SMOKE": "1",
                "OPENAI_API_KEY": "test-key",
                "JARVIS_QA_OPENAI_LIVE_OPEN_DOMAIN_ENABLED": "1",
                "JARVIS_QA_OPENAI_LIVE_QUESTION": "Who is the president of France?",
            }
        )

        self.assertTrue(config.llm.open_domain_enabled)

    def test_live_smoke_config_can_enable_fallback_explicitly(self) -> None:
        config = live_smoke_config(
            {
                "JARVIS_QA_OPENAI_LIVE_SMOKE": "1",
                "OPENAI_API_KEY": "test-key",
                "JARVIS_QA_OPENAI_LIVE_FALLBACK_ENABLED": "1",
            }
        )

        self.assertTrue(config.llm.fallback_enabled)

    def test_live_smoke_artifact_path_defaults_under_repo_tmp(self) -> None:
        path = live_smoke_artifact_path({})

        self.assertTrue(str(path).endswith("tmp/qa/openai_live_smoke.json"))

    def test_live_smoke_artifact_payload_marks_green_open_domain_verification(self) -> None:
        config = live_smoke_config(
            {
                "JARVIS_QA_OPENAI_LIVE_SMOKE": "1",
                "OPENAI_API_KEY": "test-key",
                "JARVIS_QA_OPENAI_LIVE_OPEN_DOMAIN_ENABLED": "1",
            }
        )

        payload = live_smoke_artifact_payload(
            config=config,
            question="Who is the president of France?",
            result=AnswerResult(
                answer_text="France's president is Emmanuel Macron, but this may be out of date.",
                warning="This answer may be out of date for changing public facts.",
                answer_kind="open_domain_model",
                provenance="model_knowledge",
            ),
            debug_trace={"fallback": {"deterministic_fallback": False}},
            issues=[],
        )

        self.assertTrue(bool(payload.get("success")))
        self.assertTrue(bool(payload.get("open_domain_verified")))
        self.assertEqual(str(payload.get("question")), "Who is the president of France?")
        diagnostics = dict(payload.get("diagnostics") or {})
        self.assertTrue(bool(diagnostics.get("strict_mode")))
        self.assertFalse(bool(diagnostics.get("fallback_enabled")))

    def test_live_smoke_artifact_payload_rejects_failed_or_grounded_open_domain_claim(self) -> None:
        config = live_smoke_config(
            {
                "JARVIS_QA_OPENAI_LIVE_SMOKE": "1",
                "OPENAI_API_KEY": "test-key",
                "JARVIS_QA_OPENAI_LIVE_OPEN_DOMAIN_ENABLED": "1",
            }
        )

        payload = live_smoke_artifact_payload(
            config=config,
            question="Who is the president of France?",
            result=AnswerResult(
                answer_text="I can answer grounded capability questions.",
                sources=["/Users/arseniyabramidze/JARVIS/docs/question_answer_mode.md"],
                source_attributions=[
                    AnswerSourceAttribution(
                        source="/Users/arseniyabramidze/JARVIS/docs/question_answer_mode.md",
                        support="QA mode is grounded and read-only.",
                    )
                ],
            ),
            debug_trace={"fallback": {"deterministic_fallback": False}},
            issues=["grounded answer for open-domain smoke"],
        )

        self.assertFalse(bool(payload.get("success")))
        self.assertFalse(bool(payload.get("open_domain_verified")))

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

    def test_live_smoke_result_contract_accepts_open_domain_llm_answer(self) -> None:
        issues = live_smoke_result_issues(
            AnswerResult(
                answer_text="France's president is Emmanuel Macron, but this may be out of date.",
                warning="This answer may be out of date for changing public facts.",
                answer_kind="open_domain_model",
                provenance="model_knowledge",
            )
        )

        self.assertEqual(issues, [])

    def test_live_smoke_result_contract_accepts_refusal_without_sources(self) -> None:
        issues = live_smoke_result_issues(
            AnswerResult(
                answer_text="I can't help with instructions for stealing a car.",
                answer_kind="refusal",
                provenance="model_knowledge",
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

        self.assertIn("grounded live smoke answers must keep non-empty source_attributions", issues)

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

    def test_live_smoke_result_contract_rejects_open_domain_answer_with_fake_sources(self) -> None:
        issues = live_smoke_result_issues(
            AnswerResult(
                answer_text="France's president is Emmanuel Macron.",
                sources=["/Users/arseniyabramidze/JARVIS/docs/question_answer_mode.md"],
                answer_kind="open_domain_model",
                provenance="model_knowledge",
            )
        )

        self.assertIn("open-domain live smoke answers must not claim local sources", issues)

    def test_live_smoke_diagnostics_include_provider_model_source_count_and_config_flags(self) -> None:
        config = live_smoke_config(
            {
                "JARVIS_QA_OPENAI_LIVE_SMOKE": "1",
                "OPENAI_API_KEY": "test-key",
                "JARVIS_QA_OPENAI_LIVE_FALLBACK_ENABLED": "1",
            }
        )

        diagnostics = live_smoke_diagnostics(
            config=config,
            result=AnswerResult(
                answer_text="I can answer grounded capability questions.",
                sources=[
                    "/Users/arseniyabramidze/JARVIS/docs/question_answer_mode.md",
                    "/Users/arseniyabramidze/JARVIS/docs/product_rules.md",
                ],
                source_attributions=[
                    AnswerSourceAttribution(
                        source="/Users/arseniyabramidze/JARVIS/docs/question_answer_mode.md",
                        support="QA mode is grounded and read-only.",
                    )
                ],
            ),
            debug_trace={"fallback": {"deterministic_fallback": False}},
        )

        self.assertEqual(diagnostics.get("provider"), "openai_responses")
        self.assertEqual(diagnostics.get("model"), "gpt-5-nano")
        self.assertTrue(bool(diagnostics.get("strict_mode")))
        self.assertTrue(bool(diagnostics.get("fallback_enabled")))
        self.assertFalse(bool(diagnostics.get("open_domain_enabled")))
        self.assertEqual(diagnostics.get("source_count"), 2)
        self.assertFalse(bool(diagnostics.get("deterministic_fallback")))

    def test_live_smoke_diagnostics_include_answer_kind_and_provenance(self) -> None:
        config = live_smoke_config(
            {
                "JARVIS_QA_OPENAI_LIVE_SMOKE": "1",
                "OPENAI_API_KEY": "test-key",
                "JARVIS_QA_OPENAI_LIVE_OPEN_DOMAIN_ENABLED": "1",
            }
        )

        diagnostics = live_smoke_diagnostics(
            config=config,
            result=AnswerResult(
                answer_text="France's president is Emmanuel Macron, but this may be out of date.",
                warning="This answer may be out of date for changing public facts.",
                answer_kind="open_domain_model",
                provenance="model_knowledge",
            ),
            debug_trace={"fallback": {"deterministic_fallback": False}},
        )

        self.assertTrue(bool(diagnostics.get("open_domain_enabled")))
        self.assertEqual(diagnostics.get("answer_kind"), "open_domain_model")
        self.assertEqual(diagnostics.get("provenance"), "model_knowledge")


if __name__ == "__main__":
    unittest.main()
