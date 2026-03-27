"""Config loading tests for answer backend selection."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from jarvis_error import ErrorCode, JarvisError
from qa.answer_config import load_answer_backend_config


class AnswerConfigTests(unittest.TestCase):
    """Lock env-driven backend selection and validation."""

    def test_default_env_keeps_deterministic_backend(self) -> None:
        config = load_answer_backend_config({})

        self.assertEqual(getattr(config.backend_kind, "value", ""), "deterministic")
        self.assertEqual(config.rollout_stage, "alpha_opt_in")
        self.assertEqual(config.backend_selection_source, "builtin_default")
        self.assertFalse(config.llm.enabled)
        self.assertFalse(config.llm.open_domain_enabled)
        self.assertEqual(getattr(config.llm.provider, "value", ""), "openai_responses")
        self.assertEqual(config.llm.model, "gpt-5-nano")
        self.assertEqual(config.llm.timeout_seconds, 30.0)
        self.assertEqual(config.llm.max_output_tokens, 800)
        self.assertEqual(config.llm.reasoning_effort, "minimal")
        self.assertTrue(config.llm.strict_mode)
        self.assertEqual(config.llm.max_retries, 1)
        self.assertTrue(config.llm.fallback_enabled)

    def test_llm_env_config_is_loaded_explicitly(self) -> None:
        config = load_answer_backend_config(
            {
                "JARVIS_QA_BACKEND": "llm",
                "JARVIS_QA_LLM_ENABLED": "true",
                "JARVIS_QA_LLM_PROVIDER": "openai_responses",
                "JARVIS_QA_LLM_MODEL": "gpt-4o-mini",
                "JARVIS_QA_LLM_API_BASE": "https://api.openai.com/v1",
                "JARVIS_QA_LLM_TIMEOUT_SECONDS": "12.5",
                "JARVIS_QA_LLM_MAX_OUTPUT_TOKENS": "222",
                "JARVIS_QA_LLM_REASONING_EFFORT": "low",
                "JARVIS_QA_LLM_STRICT_MODE": "false",
                "JARVIS_QA_LLM_MAX_RETRIES": "3",
                "JARVIS_QA_LLM_FALLBACK_ENABLED": "false",
            }
        )

        self.assertEqual(getattr(config.backend_kind, "value", ""), "llm")
        self.assertEqual(config.backend_selection_source, "explicit_backend_env")
        self.assertTrue(config.llm.enabled)
        self.assertEqual(getattr(config.llm.provider, "value", ""), "openai_responses")
        self.assertEqual(config.llm.model, "gpt-4o-mini")
        self.assertEqual(config.llm.api_base, "https://api.openai.com/v1")
        self.assertEqual(config.llm.timeout_seconds, 12.5)
        self.assertEqual(config.llm.max_output_tokens, 222)
        self.assertEqual(config.llm.reasoning_effort, "low")
        self.assertFalse(config.llm.strict_mode)
        self.assertEqual(config.llm.max_retries, 3)
        self.assertFalse(config.llm.fallback_enabled)

    def test_llm_env_can_enable_open_domain_explicitly(self) -> None:
        config = load_answer_backend_config(
            {
                "JARVIS_QA_BACKEND": "llm",
                "JARVIS_QA_LLM_ENABLED": "true",
                "JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED": "true",
            }
        )

        self.assertEqual(getattr(config.backend_kind, "value", ""), "llm")
        self.assertTrue(config.llm.enabled)
        self.assertTrue(config.llm.open_domain_enabled)

    def test_open_domain_hybrid_flags_can_enable_model_questions_without_backend_override(self) -> None:
        config = load_answer_backend_config(
            {
                "JARVIS_QA_LLM_ENABLED": "true",
                "JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED": "true",
            }
        )

        self.assertEqual(getattr(config.backend_kind, "value", ""), "deterministic")
        self.assertEqual(config.backend_selection_source, "builtin_default")
        self.assertTrue(config.llm.enabled)
        self.assertTrue(config.llm.open_domain_enabled)
        self.assertTrue(config.llm.fallback_enabled)

    def test_beta_question_default_stage_enables_strict_llm_question_default(self) -> None:
        config = load_answer_backend_config(
            {
                "JARVIS_QA_ROLLOUT_STAGE": "beta_question_default",
            }
        )

        self.assertEqual(config.rollout_stage, "beta_question_default")
        self.assertEqual(config.backend_selection_source, "rollout_stage_default")
        self.assertEqual(getattr(config.backend_kind, "value", ""), "llm")
        self.assertTrue(config.llm.enabled)
        self.assertTrue(config.llm.open_domain_enabled)
        self.assertFalse(config.llm.fallback_enabled)

    def test_explicit_backend_override_wins_over_beta_question_default_stage(self) -> None:
        config = load_answer_backend_config(
            {
                "JARVIS_QA_ROLLOUT_STAGE": "beta_question_default",
                "JARVIS_QA_BACKEND": "deterministic",
            }
        )

        self.assertEqual(config.rollout_stage, "beta_question_default")
        self.assertEqual(config.backend_selection_source, "explicit_backend_env")
        self.assertEqual(getattr(config.backend_kind, "value", ""), "deterministic")
        self.assertFalse(config.llm.enabled)
        self.assertFalse(config.llm.open_domain_enabled)
        self.assertTrue(config.llm.fallback_enabled)

    def test_invalid_boolean_raises_structured_error(self) -> None:
        with self.assertRaises(JarvisError) as captured:
            load_answer_backend_config({"JARVIS_QA_LLM_ENABLED": "maybe"})

        self.assertEqual(getattr(captured.exception.code, "value", ""), ErrorCode.MODEL_BACKEND_UNAVAILABLE.value)

    def test_invalid_provider_raises_structured_error(self) -> None:
        with self.assertRaises(JarvisError) as captured:
            load_answer_backend_config({"JARVIS_QA_LLM_PROVIDER": "unknown"})

        self.assertEqual(getattr(captured.exception.code, "value", ""), ErrorCode.MODEL_BACKEND_UNAVAILABLE.value)

    def test_invalid_numeric_value_raises_structured_error(self) -> None:
        with self.assertRaises(JarvisError) as captured:
            load_answer_backend_config({"JARVIS_QA_LLM_TIMEOUT_SECONDS": "0"})

        self.assertEqual(getattr(captured.exception.code, "value", ""), ErrorCode.MODEL_BACKEND_UNAVAILABLE.value)

    def test_invalid_rollout_stage_raises_structured_error(self) -> None:
        with self.assertRaises(JarvisError) as captured:
            load_answer_backend_config({"JARVIS_QA_ROLLOUT_STAGE": "beta-ish"})

        self.assertEqual(getattr(captured.exception.code, "value", ""), ErrorCode.MODEL_BACKEND_UNAVAILABLE.value)


if __name__ == "__main__":
    unittest.main()
