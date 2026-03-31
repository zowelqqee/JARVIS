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
    QaEvalCase,
    QaEvalProfileSummary,
    QaEvalReport,
    _case_applies_to_profile,
    _build_backend_config,
    _default_switch_blockers,
    _run_interaction_case,
    _text_contains_fragment,
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

    def test_voice_eval_case_can_validate_routing_after_normalization(self) -> None:
        cases = load_qa_eval_cases(DEFAULT_CORPUS_PATH)
        selected = select_eval_cases(cases, ["voice_ru_capabilities_question"])

        report = run_eval_cases(selected)

        self.assertEqual(report.total_cases, 1)
        self.assertEqual(report.failed_cases, 0)
        result = report.results[0]
        self.assertEqual(result.case_type, "voice")
        self.assertTrue(result.checks["normalized_input"])
        self.assertTrue(result.checks["interaction_kind"])
        self.assertTrue(result.checks["question_type"])
        self.assertEqual(result.details.get("actual_normalized_input"), "what can you do")
        self.assertEqual(result.details.get("actual_interaction_kind"), "question")

    def test_voice_eval_case_can_cover_open_domain_mock_path(self) -> None:
        cases = load_qa_eval_cases(DEFAULT_CORPUS_PATH)
        selected = select_eval_cases(cases, ["voice_ru_open_domain_question"])

        report = run_eval_cases(selected, default_profile="llm_open_domain_mock")

        self.assertEqual(report.total_cases, 1)
        self.assertEqual(report.failed_cases, 0)
        result = report.results[0]
        self.assertEqual(result.case_type, "voice")
        self.assertTrue(result.checks["normalized_input"])
        self.assertTrue(result.checks["question_type"])
        self.assertTrue(result.checks["answer_kind"])
        self.assertEqual(result.details.get("profile"), "llm_open_domain_mock")
        self.assertEqual(result.details.get("actual_question_type"), "open_domain_general")

    def test_voice_eval_cases_cover_english_routing_and_follow_up_surface(self) -> None:
        cases = load_qa_eval_cases(DEFAULT_CORPUS_PATH)
        selected = select_eval_cases(
            cases,
            [
                "voice_en_open_app_command",
                "voice_en_capabilities_question",
                "voice_en_mixed_question_command_clarification",
                "voice_en_mixed_answer_reply",
                "voice_en_mixed_execute_reply",
                "voice_en_confirmation_deny_reply",
                "voice_en_answer_follow_up_repeat",
            ],
        )

        report = run_eval_cases(selected)

        self.assertEqual(report.total_cases, 7)
        self.assertEqual(report.failed_cases, 0)
        result_by_id = {result.case_id: result for result in report.results}
        self.assertEqual(result_by_id["voice_en_open_app_command"].details.get("actual_normalized_input"), "open Safari")
        self.assertEqual(
            result_by_id["voice_en_mixed_question_command_clarification"].details.get("actual_interaction_kind"),
            "clarification",
        )
        self.assertEqual(result_by_id["voice_en_confirmation_deny_reply"].details.get("actual_normalized_input"), "no")
        self.assertEqual(result_by_id["voice_en_answer_follow_up_repeat"].details.get("actual_normalized_input"), "Repeat that")

    def test_voice_eval_case_can_cover_english_open_domain_mock_path(self) -> None:
        cases = load_qa_eval_cases(DEFAULT_CORPUS_PATH)
        selected = select_eval_cases(cases, ["voice_en_open_domain_question"])

        report = run_eval_cases(selected, default_profile="llm_open_domain_mock")

        self.assertEqual(report.total_cases, 1)
        self.assertEqual(report.failed_cases, 0)
        result = report.results[0]
        self.assertEqual(result.case_type, "voice")
        self.assertTrue(result.checks["normalized_input"])
        self.assertTrue(result.checks["question_type"])
        self.assertTrue(result.checks["answer_kind"])
        self.assertEqual(result.details.get("profile"), "llm_open_domain_mock")
        self.assertEqual(result.details.get("actual_normalized_input"), "Why is the sky blue?")
        self.assertEqual(result.details.get("actual_question_type"), "open_domain_general")

    def test_voice_eval_cases_cover_russian_answer_follow_up_surface(self) -> None:
        cases = load_qa_eval_cases(DEFAULT_CORPUS_PATH)
        selected = select_eval_cases(
            cases,
            [
                "voice_ru_answer_follow_up_explain_more",
                "voice_ru_answer_follow_up_sources",
                "voice_ru_answer_follow_up_where_written",
                "voice_ru_answer_follow_up_why",
                "voice_ru_answer_follow_up_repeat",
            ],
        )

        report = run_eval_cases(selected)

        self.assertEqual(report.total_cases, 5)
        self.assertEqual(report.failed_cases, 0)
        result_by_id = {result.case_id: result for result in report.results}
        self.assertEqual(
            result_by_id["voice_ru_answer_follow_up_explain_more"].details.get("actual_normalized_input"),
            "Explain more",
        )
        self.assertEqual(
            result_by_id["voice_ru_answer_follow_up_explain_more"].details.get("actual_question_type"),
            "answer_follow_up",
        )
        self.assertEqual(
            result_by_id["voice_ru_answer_follow_up_sources"].details.get("actual_normalized_input"),
            "Which source?",
        )
        self.assertEqual(
            result_by_id["voice_ru_answer_follow_up_where_written"].details.get("actual_normalized_input"),
            "Where is that written",
        )
        self.assertEqual(
            result_by_id["voice_ru_answer_follow_up_why"].details.get("actual_normalized_input"),
            "Why is that",
        )
        self.assertEqual(
            result_by_id["voice_ru_answer_follow_up_repeat"].details.get("actual_normalized_input"),
            "Repeat that",
        )

    def test_voice_eval_case_can_cover_permission_denied_capture_error(self) -> None:
        cases = load_qa_eval_cases(DEFAULT_CORPUS_PATH)
        selected = select_eval_cases(cases, ["voice_permission_denied_error"])

        report = run_eval_cases(selected)

        self.assertEqual(report.total_cases, 1)
        self.assertEqual(report.failed_cases, 0)
        result = report.results[0]
        self.assertEqual(result.case_type, "voice")
        self.assertTrue(result.checks["error_code"])
        self.assertTrue(result.checks["error_message"])
        self.assertTrue(result.checks["error_hint"])
        self.assertEqual(result.details.get("actual_error_code"), "PERMISSION_DENIED")

    def test_voice_eval_case_can_cover_empty_recognition_capture_error(self) -> None:
        cases = load_qa_eval_cases(DEFAULT_CORPUS_PATH)
        selected = select_eval_cases(cases, ["voice_empty_recognition_error"])

        report = run_eval_cases(selected)

        self.assertEqual(report.total_cases, 1)
        self.assertEqual(report.failed_cases, 0)
        result = report.results[0]
        self.assertEqual(result.case_type, "voice")
        self.assertTrue(result.checks["error_code"])
        self.assertTrue(result.checks["error_message"])
        self.assertTrue(result.checks["error_hint"])
        self.assertEqual(result.details.get("actual_error_code"), "EMPTY_RECOGNITION")

    def test_voice_eval_case_can_cover_microphone_unavailable_capture_error(self) -> None:
        cases = load_qa_eval_cases(DEFAULT_CORPUS_PATH)
        selected = select_eval_cases(cases, ["voice_microphone_unavailable_error"])

        report = run_eval_cases(selected)

        self.assertEqual(report.total_cases, 1)
        self.assertEqual(report.failed_cases, 0)
        result = report.results[0]
        self.assertEqual(result.case_type, "voice")
        self.assertTrue(result.checks["error_code"])
        self.assertTrue(result.checks["error_message"])
        self.assertTrue(result.checks["error_hint"])
        self.assertEqual(result.details.get("actual_error_code"), "MICROPHONE_UNAVAILABLE")

    def test_voice_eval_case_can_cover_voice_helper_crash_error(self) -> None:
        cases = load_qa_eval_cases(DEFAULT_CORPUS_PATH)
        selected = select_eval_cases(cases, ["voice_helper_crash_error"])

        report = run_eval_cases(selected)

        self.assertEqual(report.total_cases, 1)
        self.assertEqual(report.failed_cases, 0)
        result = report.results[0]
        self.assertEqual(result.case_type, "voice")
        self.assertTrue(result.checks["error_code"])
        self.assertTrue(result.checks["error_message"])
        self.assertTrue(result.checks["error_hint"])
        self.assertEqual(result.details.get("actual_error_code"), "VOICE_HELPER_CRASH")

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

    def test_interaction_results_keep_answer_text_preview_for_operator_diagnostics(self) -> None:
        cases = load_qa_eval_cases(DEFAULT_CORPUS_PATH)
        selected = select_eval_cases(cases, ["route_docs_clarification_question"])

        report = run_eval_cases(selected, default_profile="deterministic")

        result = report.results[0]
        self.assertIn("actual_answer_text_preview", result.details)
        self.assertTrue(str(result.details.get("actual_answer_text_preview") or "").strip())

    def test_expected_answer_contains_any_matches_case_insensitively(self) -> None:
        case = QaEvalCase(
            id="synthetic_docs_rules_answer_text_any",
            case_type="interaction",
            category="test",
            raw_input="How does clarification work?",
            expected_interaction_kind="question",
            expected_question_type="docs_rules",
            should_call_runtime=False,
            should_call_answer_engine=True,
            expected_sources_count_min=2,
            expected_answer_contains_any=["missing phrase", "clarification is a hard boundary"],
        )

        result = _run_interaction_case(case, default_profile="deterministic")

        self.assertTrue(result.checks["answer_text"])

    def test_text_fragment_matching_normalizes_typographic_punctuation(self) -> None:
        self.assertTrue(_text_contains_fragment("I can’t help with that request.", "can't help"))

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

    def test_open_domain_cases_apply_to_env_profiles_only_when_open_domain_is_enabled(self) -> None:
        cases = load_qa_eval_cases(DEFAULT_CORPUS_PATH)
        case = select_eval_cases(cases, ["open_domain_explanation_answer"])[0]

        with patch.dict("os.environ", {"JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED": "false"}, clear=False):
            self.assertFalse(_case_applies_to_profile(case, "llm_env"))

        with patch.dict(
            "os.environ",
            {
                "JARVIS_QA_BACKEND": "llm",
                "JARVIS_QA_LLM_ENABLED": "true",
                "JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED": "true",
            },
            clear=False,
        ):
            self.assertTrue(_case_applies_to_profile(case, "llm_env"))

    def test_unsupported_world_question_does_not_apply_when_open_domain_is_enabled(self) -> None:
        cases = load_qa_eval_cases(DEFAULT_CORPUS_PATH)
        case = select_eval_cases(cases, ["route_unsupported_world_question"])[0]

        with patch.dict("os.environ", {"JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED": "false"}, clear=False):
            self.assertTrue(_case_applies_to_profile(case, "llm_env"))

        with patch.dict(
            "os.environ",
            {
                "JARVIS_QA_BACKEND": "llm",
                "JARVIS_QA_LLM_ENABLED": "true",
                "JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED": "true",
            },
            clear=False,
        ):
            self.assertFalse(_case_applies_to_profile(case, "llm_env"))

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

    def test_default_switch_blockers_ignore_unsupported_honesty_when_metric_is_not_applicable(self) -> None:
        report = QaEvalReport(
            default_profile="deterministic",
            total_cases=0,
            passed_cases=0,
            failed_cases=0,
            routing_total=1,
            routing_passed=1,
            grounding_total=1,
            grounding_passed=1,
            command_regression_total=1,
            command_regression_passed=1,
            results=[],
        )
        baseline_summary = QaEvalProfileSummary(
            profile="deterministic",
            report=report,
            routing_total=1,
            routing_passed=1,
            grounding_total=1,
            grounding_passed=1,
            command_regression_total=1,
            command_regression_passed=1,
            unsupported_total=1,
            unsupported_passed=1,
            source_attribution_total=1,
            source_attribution_passed=1,
            open_domain_total=0,
            open_domain_passed=0,
            refusal_total=0,
            refusal_passed=0,
            provenance_total=0,
            provenance_passed=0,
            answer_total=1,
            fallback_total=0,
            avg_interaction_latency_ms=1.0,
            usage_sample_count=1,
            usage_input_tokens_total=1,
            usage_output_tokens_total=1,
            usage_total_tokens_total=2,
            env_backed_profile=False,
            llm_provider="openai_responses",
            llm_model="gpt-5-nano",
            open_domain_enabled=False,
            live_smoke_artifact_path=None,
            live_smoke_artifact_present=False,
            live_smoke_artifact_success=None,
            live_smoke_artifact_created_at=None,
            live_smoke_artifact_age_hours=None,
            live_smoke_artifact_fresh=None,
            live_smoke_artifact_fresh_reason=None,
            live_smoke_artifact_profile_match=None,
            live_smoke_artifact_match_reason=None,
            live_smoke_artifact_open_domain_verified=None,
            live_smoke_artifact_error=None,
        )
        candidate_summary = QaEvalProfileSummary(
            profile="llm_open_domain_mock",
            report=report,
            routing_total=1,
            routing_passed=1,
            grounding_total=1,
            grounding_passed=1,
            command_regression_total=1,
            command_regression_passed=1,
            unsupported_total=0,
            unsupported_passed=0,
            source_attribution_total=1,
            source_attribution_passed=1,
            open_domain_total=1,
            open_domain_passed=1,
            refusal_total=1,
            refusal_passed=1,
            provenance_total=2,
            provenance_passed=2,
            answer_total=2,
            fallback_total=0,
            avg_interaction_latency_ms=1.0,
            usage_sample_count=2,
            usage_input_tokens_total=1,
            usage_output_tokens_total=1,
            usage_total_tokens_total=2,
            env_backed_profile=False,
            llm_provider="openai_responses",
            llm_model="gpt-5-nano",
            open_domain_enabled=True,
            live_smoke_artifact_path=None,
            live_smoke_artifact_present=False,
            live_smoke_artifact_success=None,
            live_smoke_artifact_created_at=None,
            live_smoke_artifact_age_hours=None,
            live_smoke_artifact_fresh=None,
            live_smoke_artifact_fresh_reason=None,
            live_smoke_artifact_profile_match=None,
            live_smoke_artifact_match_reason=None,
            live_smoke_artifact_open_domain_verified=None,
            live_smoke_artifact_error=None,
        )

        blockers = _default_switch_blockers(
            baseline_summary=baseline_summary,
            candidate_summary=candidate_summary,
            routing_safety_regressions=0,
        )

        self.assertNotIn("unsupported-question honesty is below threshold", blockers)

    def test_comparison_report_includes_failing_case_samples_for_non_green_profile(self) -> None:
        cases = load_qa_eval_cases(DEFAULT_CORPUS_PATH)
        selected = select_eval_cases(cases, ["route_capabilities_question"])

        comparison = compare_eval_profiles(
            selected,
            profiles=["deterministic", "llm_open_domain_missing_key"],
            candidate_profile="llm_open_domain_missing_key",
        )

        report_text = format_comparison_report(comparison)

        self.assertIn("failing case samples (1/1):", report_text)
        self.assertIn("route_capabilities_question [deterministic_grounded_answers]", report_text)

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

    def test_non_env_backed_baseline_does_not_report_candidate_artifact_mismatch(self) -> None:
        cases = load_qa_eval_cases(DEFAULT_CORPUS_PATH)
        selected = select_eval_cases(cases, ["route_capabilities_question"])
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "openai_live_smoke_llm_env_strict.json"
            artifact_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-25T00:00:00+00:00",
                        "question": "What can you do?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": False,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": False,
                            "open_domain_enabled": False,
                            "answer_kind": "grounded_local",
                            "provenance": "local_sources",
                            "source_count": 1,
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
                        "JARVIS_QA_OPENAI_LIVE_ARTIFACT": str(artifact_path),
                    },
                    clear=False,
                ):
                    comparison = compare_eval_profiles(
                        selected,
                        profiles=["deterministic", "llm_env_strict"],
                        candidate_profile="llm_env_strict",
                    )

        baseline_summary = next(summary for summary in comparison.summaries if summary.profile == "deterministic")
        report_text = format_comparison_report(comparison)

        self.assertFalse(baseline_summary.env_backed_profile)
        self.assertIsNone(baseline_summary.live_smoke_artifact_path)
        self.assertFalse(baseline_summary.live_smoke_artifact_present)
        self.assertIsNone(baseline_summary.live_smoke_artifact_profile_match)
        self.assertIn("profile: deterministic", report_text)
        self.assertIn("  live smoke artifact: n/a", report_text)
        self.assertIn("  live smoke artifact matches profile: n/a", report_text)


if __name__ == "__main__":
    unittest.main()
