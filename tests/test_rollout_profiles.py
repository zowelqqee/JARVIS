"""Contract tests for shared QA rollout profile helpers."""

from __future__ import annotations

import unittest

from qa.rollout_profiles import (
    live_smoke_artifact_path_for_candidate,
    resolve_rollout_candidate_settings,
    rollout_compare_command,
    rollout_smoke_command,
    rollout_stability_command,
)


class RolloutProfilesTests(unittest.TestCase):
    """Keep rollout candidate helpers aligned with gate/smoke workflows."""

    def test_candidate_artifact_paths_are_profile_scoped(self) -> None:
        self.assertTrue(str(live_smoke_artifact_path_for_candidate("llm_env")).endswith("openai_live_smoke_llm_env.json"))
        self.assertTrue(
            str(live_smoke_artifact_path_for_candidate("llm_env_strict")).endswith(
                "openai_live_smoke_llm_env_strict.json"
            )
        )
        self.assertTrue(str(live_smoke_artifact_path_for_candidate()).endswith("openai_live_smoke.json"))

    def test_candidate_commands_are_profile_scoped(self) -> None:
        self.assertEqual(rollout_smoke_command("llm_env"), "scripts/run_openai_live_smoke.sh llm_env")
        self.assertEqual(rollout_smoke_command("llm_env_strict"), "scripts/run_openai_live_smoke.sh llm_env_strict")
        self.assertEqual(rollout_compare_command("llm_env"), "scripts/run_qa_rollout_gate.sh llm_env")
        self.assertEqual(rollout_compare_command("llm_env_strict"), "scripts/run_qa_rollout_gate.sh llm_env_strict")
        self.assertEqual(rollout_stability_command("llm_env"), "scripts/run_qa_rollout_stability.sh llm_env 3")
        self.assertEqual(
            rollout_stability_command("llm_env_strict", runs=5),
            "scripts/run_qa_rollout_stability.sh llm_env_strict 5",
        )

    def test_resolve_rollout_candidate_settings_use_current_env_and_force_profile_fallback(self) -> None:
        settings = resolve_rollout_candidate_settings(
            "llm_env",
            environ={
                "JARVIS_QA_BACKEND": "llm",
                "JARVIS_QA_LLM_ENABLED": "true",
                "JARVIS_QA_LLM_MODEL": "gpt-4o-mini",
                "JARVIS_QA_LLM_STRICT_MODE": "false",
                "JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED": "true",
                "JARVIS_QA_LLM_API_KEY_ENV": "CUSTOM_OPENAI_KEY",
                "JARVIS_QA_LLM_FALLBACK_ENABLED": "false",
            },
        )

        self.assertEqual(settings.candidate_profile, "llm_env")
        self.assertEqual(settings.model, "gpt-4o-mini")
        self.assertFalse(settings.strict_mode)
        self.assertTrue(settings.open_domain_enabled)
        self.assertEqual(settings.api_key_env, "CUSTOM_OPENAI_KEY")
        self.assertTrue(settings.fallback_enabled)

    def test_strict_candidate_forces_no_fallback(self) -> None:
        settings = resolve_rollout_candidate_settings(
            "llm_env_strict",
            environ={
                "JARVIS_QA_BACKEND": "llm",
                "JARVIS_QA_LLM_ENABLED": "true",
                "JARVIS_QA_LLM_FALLBACK_ENABLED": "true",
            },
        )

        self.assertEqual(settings.candidate_profile, "llm_env_strict")
        self.assertFalse(settings.fallback_enabled)


if __name__ == "__main__":
    unittest.main()
