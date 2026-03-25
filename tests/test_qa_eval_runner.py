"""Eval-harness contract tests for centralized QA cases."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from evals.run_qa_eval import (
    DEFAULT_CORPUS_PATH,
    _build_backend_config,
    compare_eval_profiles,
    format_comparison_report,
    format_report,
    load_qa_eval_cases,
    run_eval_cases,
    select_eval_cases,
    summarize_eval_report,
)


class QaEvalRunnerTests(unittest.TestCase):
    """Lock the centralized corpus and eval runner behavior."""

    def test_corpus_loads_with_unique_ids_and_expected_case_types(self) -> None:
        cases = load_qa_eval_cases(DEFAULT_CORPUS_PATH)

        self.assertTrue(cases)
        self.assertEqual(len({case.id for case in cases}), len(cases))
        self.assertTrue(any(case.case_type == "interaction" for case in cases))
        self.assertTrue(any(case.case_type == "voice" for case in cases))
        self.assertTrue(any(case.case_type == "live_smoke" for case in cases))

    def test_full_corpus_runs_green_under_default_profile(self) -> None:
        report = run_eval_cases(load_qa_eval_cases(DEFAULT_CORPUS_PATH))

        self.assertEqual(report.failed_cases, 0)
        self.assertEqual(report.total_cases, len(report.results))
        self.assertGreater(report.routing_total, 0)
        self.assertGreater(report.grounding_total, 0)
        self.assertGreater(report.command_regression_total, 0)
        self.assertIn("failed cases: none", format_report(report))

    def test_case_selection_filters_corpus(self) -> None:
        cases = load_qa_eval_cases(DEFAULT_CORPUS_PATH)

        selected = select_eval_cases(cases, ["route_open_app_command", "voice_repeat_question"])
        report = run_eval_cases(selected)

        self.assertEqual([case.id for case in selected], ["route_open_app_command", "voice_repeat_question"])
        self.assertEqual(report.total_cases, 2)
        self.assertEqual(report.failed_cases, 0)

    def test_default_profile_can_force_llm_fallback_path(self) -> None:
        cases = load_qa_eval_cases(DEFAULT_CORPUS_PATH)
        selected = select_eval_cases(cases, ["route_capabilities_question"])

        report = run_eval_cases(selected, default_profile="llm_missing_key_fallback")

        self.assertEqual(report.failed_cases, 0)
        self.assertIn("LLM backend fallback", str(report.results[0].details.get("actual_warning", "")))

    def test_profile_summary_tracks_fallback_and_source_quality_metrics(self) -> None:
        cases = load_qa_eval_cases(DEFAULT_CORPUS_PATH)
        report = run_eval_cases(cases, default_profile="llm_missing_key_fallback")

        summary = summarize_eval_report(report)

        self.assertEqual(summary.profile, "llm_missing_key_fallback")
        self.assertGreater(summary.answer_total, 0)
        self.assertEqual(summary.fallback_total, summary.answer_total)
        self.assertGreater(summary.source_attribution_passed, 0)

    def test_open_domain_mock_profile_tracks_answer_kind_provenance_and_refusal_metrics(self) -> None:
        cases = load_qa_eval_cases(DEFAULT_CORPUS_PATH)
        selected = select_eval_cases(
            cases,
            [
                "open_domain_explanation_answer",
                "open_domain_temporal_warning_answer",
                "open_domain_refusal_answer",
            ],
        )

        report = run_eval_cases(selected, default_profile="llm_open_domain_mock")
        summary = summarize_eval_report(report)

        self.assertEqual(report.failed_cases, 0)
        self.assertEqual(report.total_cases, 3)
        self.assertEqual(summary.open_domain_total, 2)
        self.assertEqual(summary.open_domain_passed, 2)
        self.assertEqual(summary.refusal_total, 1)
        self.assertEqual(summary.refusal_passed, 1)
        self.assertEqual(summary.provenance_total, 3)
        self.assertEqual(summary.provenance_passed, 3)

    def test_open_domain_mock_profile_supports_sensitive_and_refusal_boundary_cases(self) -> None:
        cases = load_qa_eval_cases(DEFAULT_CORPUS_PATH)
        selected = select_eval_cases(
            cases,
            [
                "open_domain_self_harm_refusal_answer",
                "open_domain_medical_bounded_answer",
                "open_domain_legal_bounded_answer",
                "open_domain_financial_bounded_answer",
            ],
        )

        report = run_eval_cases(selected, default_profile="llm_open_domain_mock")

        self.assertEqual(report.failed_cases, 0)
        self.assertEqual(report.total_cases, 4)

    def test_llm_env_profile_uses_current_env_settings_but_forces_fallback_on(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "JARVIS_QA_BACKEND": "llm",
                "JARVIS_QA_LLM_ENABLED": "true",
                "JARVIS_QA_LLM_MODEL": "gpt-4o-mini",
                "JARVIS_QA_LLM_REASONING_EFFORT": "high",
                "JARVIS_QA_LLM_STRICT_MODE": "false",
                "JARVIS_QA_LLM_MAX_OUTPUT_TOKENS": "1200",
                "JARVIS_QA_LLM_MAX_RETRIES": "3",
                "JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED": "true",
                "JARVIS_QA_LLM_FALLBACK_ENABLED": "false",
            },
            clear=False,
        ):
            config = _build_backend_config("llm_env")

        self.assertEqual(str(getattr(config.llm.provider, "value", config.llm.provider)), "openai_responses")
        self.assertEqual(config.llm.model, "gpt-4o-mini")
        self.assertEqual(config.llm.reasoning_effort, "high")
        self.assertFalse(config.llm.strict_mode)
        self.assertEqual(config.llm.max_output_tokens, 1200)
        self.assertEqual(config.llm.max_retries, 3)
        self.assertTrue(config.llm.open_domain_enabled)
        self.assertTrue(config.llm.fallback_enabled)

    def test_compare_profiles_keeps_deterministic_default_when_candidate_falls_back(self) -> None:
        cases = load_qa_eval_cases(DEFAULT_CORPUS_PATH)

        comparison = compare_eval_profiles(
            cases,
            profiles=["deterministic", "llm_missing_key_fallback"],
            candidate_profile="llm_missing_key_fallback",
        )

        self.assertFalse(comparison.default_switch_allowed)
        self.assertEqual(comparison.recommended_default_profile, "deterministic")
        self.assertEqual(comparison.routing_safety_regressions, 0)
        self.assertTrue(any("fallback frequency" in blocker for blocker in comparison.blockers))
        self.assertIn("default switch allowed: no", format_comparison_report(comparison))

    def test_compare_profiles_block_env_candidate_without_live_smoke_artifact(self) -> None:
        cases = load_qa_eval_cases(DEFAULT_CORPUS_PATH)
        selected = select_eval_cases(cases, ["route_capabilities_question"])
        missing_artifact = str(Path(tempfile.gettempdir()) / "jarvis_missing_live_smoke_artifact.json")

        with patch.dict(
            "os.environ",
            {
                "OPENAI_API_KEY": "",
                "JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED": "true",
                "JARVIS_QA_OPENAI_LIVE_ARTIFACT": missing_artifact,
            },
            clear=False,
        ):
            comparison = compare_eval_profiles(
                selected,
                profiles=["deterministic", "llm_env"],
                candidate_profile="llm_env",
            )

        self.assertFalse(comparison.default_switch_allowed)
        self.assertTrue(any("live smoke artifact is missing" in blocker for blocker in comparison.blockers))
        self.assertIn("live smoke artifact:", format_comparison_report(comparison))

    def test_compare_profiles_require_open_domain_live_smoke_verification_for_env_candidate(self) -> None:
        cases = load_qa_eval_cases(DEFAULT_CORPUS_PATH)
        selected = select_eval_cases(cases, ["route_capabilities_question"])
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "openai_live_smoke.json"
            artifact_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-25T00:00:00+00:00",
                        "question": "Who is the president of France?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": False,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "grounded_local",
                            "provenance": "local_sources",
                            "source_count": 1,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "",
                    "JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED": "true",
                    "JARVIS_QA_OPENAI_LIVE_ARTIFACT": str(artifact_path),
                },
                clear=False,
            ):
                comparison = compare_eval_profiles(
                    selected,
                    profiles=["deterministic", "llm_env"],
                    candidate_profile="llm_env",
                )

        self.assertFalse(comparison.default_switch_allowed)
        self.assertTrue(
            any("open-domain live smoke verification is missing" in blocker for blocker in comparison.blockers)
        )

    def test_compare_profiles_require_fresh_live_smoke_artifact_for_env_candidate(self) -> None:
        cases = load_qa_eval_cases(DEFAULT_CORPUS_PATH)
        selected = select_eval_cases(cases, ["route_capabilities_question"])
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "openai_live_smoke.json"
            artifact_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-20T00:00:00+00:00",
                        "question": "Who is the president of France?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            with patch("evals.run_qa_eval._artifact_now", return_value=datetime(2026, 3, 25, tzinfo=timezone.utc)):
                with patch.dict(
                    "os.environ",
                    {
                        "OPENAI_API_KEY": "",
                        "JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED": "true",
                        "JARVIS_QA_OPENAI_LIVE_ARTIFACT": str(artifact_path),
                    },
                    clear=False,
                ):
                    comparison = compare_eval_profiles(
                        selected,
                        profiles=["deterministic", "llm_env"],
                        candidate_profile="llm_env",
                    )

        self.assertFalse(comparison.default_switch_allowed)
        self.assertTrue(any("live smoke artifact is stale" in blocker for blocker in comparison.blockers))

    def test_compare_profiles_require_matching_live_smoke_artifact_for_env_candidate(self) -> None:
        cases = load_qa_eval_cases(DEFAULT_CORPUS_PATH)
        selected = select_eval_cases(cases, ["route_capabilities_question"])
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "openai_live_smoke.json"
            artifact_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-25T00:00:00+00:00",
                        "question": "Who is the president of France?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-4o-mini",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            with patch("evals.run_qa_eval._artifact_now", return_value=datetime(2026, 3, 25, tzinfo=timezone.utc)):
                with patch.dict(
                    "os.environ",
                    {
                        "OPENAI_API_KEY": "",
                        "JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED": "true",
                        "JARVIS_QA_OPENAI_LIVE_ARTIFACT": str(artifact_path),
                    },
                    clear=False,
                ):
                    comparison = compare_eval_profiles(
                        selected,
                        profiles=["deterministic", "llm_env"],
                        candidate_profile="llm_env",
                    )

        self.assertFalse(comparison.default_switch_allowed)
        self.assertTrue(
            any(
                "live smoke artifact does not match candidate provider/model/strict/fallback/open-domain config" in blocker
                for blocker in comparison.blockers
            )
        )

    def test_compare_profiles_require_matching_live_smoke_fallback_flag_for_strict_candidate(self) -> None:
        cases = load_qa_eval_cases(DEFAULT_CORPUS_PATH)
        selected = select_eval_cases(cases, ["route_capabilities_question"])
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "openai_live_smoke.json"
            artifact_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-25T00:00:00+00:00",
                        "question": "Who is the president of France?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            with patch("evals.run_qa_eval._artifact_now", return_value=datetime(2026, 3, 25, tzinfo=timezone.utc)):
                with patch.dict(
                    "os.environ",
                    {
                        "OPENAI_API_KEY": "",
                        "JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED": "true",
                        "JARVIS_QA_OPENAI_LIVE_ARTIFACT": str(artifact_path),
                    },
                    clear=False,
                ):
                    comparison = compare_eval_profiles(
                        selected,
                        profiles=["deterministic", "llm_env_strict"],
                        candidate_profile="llm_env_strict",
                    )

        self.assertFalse(comparison.default_switch_allowed)
        self.assertTrue(
            any(
                "live smoke artifact does not match candidate provider/model/strict/fallback/open-domain config" in blocker
                for blocker in comparison.blockers
            )
        )

    def test_compare_profiles_uses_candidate_default_artifact_path_without_env_override(self) -> None:
        cases = load_qa_eval_cases(DEFAULT_CORPUS_PATH)
        selected = select_eval_cases(cases, ["route_capabilities_question"])
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "openai_live_smoke_llm_env.json"
            artifact_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-25T00:00:00+00:00",
                        "question": "Who is the president of France?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            with patch("evals.run_qa_eval._artifact_now", return_value=datetime(2026, 3, 25, tzinfo=timezone.utc)):
                with patch("evals.run_qa_eval.live_smoke_artifact_path_for_candidate", return_value=artifact_path):
                    with patch.dict(
                        "os.environ",
                        {
                            "OPENAI_API_KEY": "",
                            "JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED": "true",
                        },
                        clear=False,
                    ):
                        comparison = compare_eval_profiles(
                            selected,
                            profiles=["deterministic", "llm_env"],
                            candidate_profile="llm_env",
                        )

        self.assertFalse(any("live smoke artifact is missing" in blocker for blocker in comparison.blockers))


if __name__ == "__main__":
    unittest.main()
