"""Contract tests for repeated rollout-gate stability reporting."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from evals.run_qa_eval import QaEvalCaseResult, QaEvalComparisonReport, QaEvalProfileSummary, QaEvalReport
from qa.rollout_stability import _write_rollout_stability_artifact, format_rollout_stability_report, run_rollout_stability


class RolloutStabilityTests(unittest.TestCase):
    """Keep repeated-gate stability aggregation deterministic and inspectable."""

    def test_run_rollout_stability_aggregates_blockers_and_failed_cases(self) -> None:
        comparisons = iter(
            [
                self._comparison(
                    candidate_profile="llm_env_strict",
                    default_switch_allowed=False,
                    blockers=["grounding pass rate is below threshold"],
                    failed_case_ids=["route_docs_clarification_question"],
                    fallback_case_ids=[],
                    grounding=(10, 12),
                    open_domain=(5, 5),
                ),
                self._comparison(
                    candidate_profile="llm_env_strict",
                    default_switch_allowed=True,
                    blockers=[],
                    failed_case_ids=[],
                    fallback_case_ids=["route_answer_follow_up_explain_more"],
                    grounding=(12, 12),
                    open_domain=(5, 5),
                ),
                self._comparison(
                    candidate_profile="llm_env_strict",
                    default_switch_allowed=False,
                    blockers=["open-domain answer pass rate is below threshold"],
                    failed_case_ids=["open_domain_explanation_answer"],
                    fallback_case_ids=[],
                    grounding=(12, 12),
                    open_domain=(4, 5),
                ),
            ]
        )

        def _fake_runner(*args, **kwargs):  # type: ignore[no-untyped-def]
            del args, kwargs
            return next(comparisons)

        report = run_rollout_stability("llm_env_strict", runs=3, comparison_runner=_fake_runner)

        self.assertEqual(report.gate_passes, 1)
        self.assertEqual(len(report.runs), 3)
        self.assertEqual(report.runs[0].grounding_passed, 10)
        self.assertEqual(report.runs[2].open_domain_passed, 4)
        self.assertEqual(report.runs[0].failed_case_ids, ["route_docs_clarification_question"])

        payload = report.to_dict()
        self.assertEqual(payload["gate_passes"], 1)
        self.assertEqual(payload["blocker_counts"]["grounding pass rate is below threshold"], 1)
        self.assertEqual(payload["blocker_counts"]["open-domain answer pass rate is below threshold"], 1)
        self.assertEqual(payload["failed_case_counts"]["route_docs_clarification_question"], 1)
        self.assertEqual(payload["failed_case_counts"]["open_domain_explanation_answer"], 1)
        self.assertEqual(payload["fallback_case_counts"]["route_answer_follow_up_explain_more"], 1)

    def test_format_rollout_stability_report_includes_per_run_summary_and_frequencies(self) -> None:
        comparisons = iter(
            [
                self._comparison(
                    candidate_profile="llm_env",
                    default_switch_allowed=False,
                    blockers=["grounding pass rate is below threshold"],
                    failed_case_ids=["route_answer_follow_up_explain_more"],
                    fallback_case_ids=["route_answer_follow_up_explain_more"],
                    grounding=(11, 12),
                    open_domain=(4, 5),
                ),
                self._comparison(
                    candidate_profile="llm_env",
                    default_switch_allowed=True,
                    blockers=[],
                    failed_case_ids=[],
                    fallback_case_ids=[],
                    grounding=(12, 12),
                    open_domain=(5, 5),
                ),
            ]
        )

        def _fake_runner(*args, **kwargs):  # type: ignore[no-untyped-def]
            del args, kwargs
            return next(comparisons)

        report = run_rollout_stability("llm_env", runs=2, comparison_runner=_fake_runner)
        text = format_rollout_stability_report(report)

        self.assertIn("JARVIS QA Gate Stability", text)
        self.assertIn("gate passes: 1/2 (50.0%)", text)
        self.assertIn("run 1: pass=no; grounding=11/12; open-domain=4/5", text)
        self.assertIn("blocker frequency:", text)
        self.assertIn("grounding pass rate is below threshold: 1/2", text)
        self.assertIn("route_answer_follow_up_explain_more: 1/2", text)
        self.assertIn("fallback-case frequency:", text)

    def test_write_rollout_stability_artifact_persists_report_payload(self) -> None:
        comparisons = iter(
            [
                self._comparison(
                    candidate_profile="llm_env",
                    default_switch_allowed=True,
                    blockers=[],
                    failed_case_ids=[],
                    fallback_case_ids=[],
                    grounding=(12, 12),
                    open_domain=(5, 5),
                ),
                self._comparison(
                    candidate_profile="llm_env",
                    default_switch_allowed=True,
                    blockers=[],
                    failed_case_ids=[],
                    fallback_case_ids=[],
                    grounding=(12, 12),
                    open_domain=(5, 5),
                ),
            ]
        )

        def _fake_runner(*args, **kwargs):  # type: ignore[no-untyped-def]
            del args, kwargs
            return next(comparisons)

        report = run_rollout_stability("llm_env", runs=2, comparison_runner=_fake_runner)

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "rollout_stability_llm_env.json"
            _write_rollout_stability_artifact(report, artifact_path=artifact_path)
            payload = json.loads(artifact_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["runner"], "qa.rollout_stability")
        self.assertEqual(payload["report"]["candidate_profile"], "llm_env")
        self.assertEqual(payload["report"]["gate_passes"], 2)
        self.assertEqual(payload["report"]["runs_requested"], 2)

    def test_run_rollout_stability_ignores_override_profile_fallback_cases(self) -> None:
        comparison = self._comparison(
            candidate_profile="llm_env",
            default_switch_allowed=True,
            blockers=[],
            failed_case_ids=[],
            fallback_case_ids=[],
            grounding=(12, 12),
            open_domain=(5, 5),
        )
        comparison.summaries[1].report.results.append(
            QaEvalCaseResult(
                case_id="route_llm_missing_key_fallback",
                case_type="interaction",
                category="test",
                passed=True,
                checks={},
                details={
                    "profile": "llm_missing_key_fallback",
                    "answer_calls": 1,
                    "actual_error_code": None,
                    "fallback_used": True,
                },
            )
        )

        def _fake_runner(*args, **kwargs):  # type: ignore[no-untyped-def]
            del args, kwargs
            return comparison

        report = run_rollout_stability("llm_env", runs=1, comparison_runner=_fake_runner)

        self.assertEqual(report.to_dict()["fallback_case_counts"], {})

    def _comparison(
        self,
        *,
        candidate_profile: str,
        default_switch_allowed: bool,
        blockers: list[str],
        failed_case_ids: list[str],
        fallback_case_ids: list[str],
        grounding: tuple[int, int],
        open_domain: tuple[int, int],
    ) -> QaEvalComparisonReport:
        baseline_summary = self._profile_summary(
            "deterministic",
            failed_case_ids=[],
            fallback_case_ids=[],
            grounding=(12, 12),
            open_domain=(0, 0),
            fallback=(0, 12),
            env_backed=False,
            open_domain_enabled=False,
        )
        candidate_summary = self._profile_summary(
            candidate_profile,
            failed_case_ids=failed_case_ids,
            fallback_case_ids=fallback_case_ids,
            grounding=grounding,
            open_domain=open_domain,
            fallback=(0, 19),
            env_backed=True,
            open_domain_enabled=True,
        )
        return QaEvalComparisonReport(
            baseline_profile="deterministic",
            candidate_profile=candidate_profile,
            summaries=[baseline_summary, candidate_summary],
            routing_safety_regressions=0,
            default_switch_allowed=default_switch_allowed,
            recommended_default_profile=candidate_profile if default_switch_allowed else "deterministic",
            thresholds={},
            blockers=list(blockers),
        )

    def _profile_summary(
        self,
        profile: str,
        *,
        failed_case_ids: list[str],
        fallback_case_ids: list[str],
        grounding: tuple[int, int],
        open_domain: tuple[int, int],
        fallback: tuple[int, int],
        env_backed: bool,
        open_domain_enabled: bool,
    ) -> QaEvalProfileSummary:
        failed_case_id_set = set(failed_case_ids)
        results = [
            QaEvalCaseResult(
                case_id=case_id,
                case_type="interaction",
                category="test",
                passed=False,
                checks={"answer_text": False},
                details={
                    "profile": profile,
                    "answer_calls": 1,
                    "actual_error_code": None,
                    "fallback_used": case_id in set(fallback_case_ids),
                },
            )
            for case_id in failed_case_ids
        ]
        for case_id in fallback_case_ids:
            if case_id in failed_case_id_set:
                continue
            results.append(
                QaEvalCaseResult(
                    case_id=case_id,
                    case_type="interaction",
                    category="test",
                    passed=True,
                    checks={},
                    details={
                        "profile": profile,
                        "answer_calls": 1,
                        "actual_error_code": None,
                        "fallback_used": True,
                    },
                )
            )
        report = QaEvalReport(
            default_profile=profile,
            total_cases=len(results),
            passed_cases=0,
            failed_cases=len(results),
            routing_total=1,
            routing_passed=1,
            grounding_total=grounding[1],
            grounding_passed=grounding[0],
            command_regression_total=1,
            command_regression_passed=1,
            results=results,
        )
        return QaEvalProfileSummary(
            profile=profile,
            report=report,
            routing_total=1,
            routing_passed=1,
            grounding_total=grounding[1],
            grounding_passed=grounding[0],
            command_regression_total=1,
            command_regression_passed=1,
            unsupported_total=0,
            unsupported_passed=0,
            source_attribution_total=1,
            source_attribution_passed=1,
            open_domain_total=open_domain[1],
            open_domain_passed=open_domain[0],
            refusal_total=1,
            refusal_passed=1,
            provenance_total=1,
            provenance_passed=1,
            answer_total=fallback[1],
            fallback_total=fallback[0],
            avg_interaction_latency_ms=1.0,
            usage_sample_count=1,
            usage_input_tokens_total=1,
            usage_output_tokens_total=1,
            usage_total_tokens_total=2,
            env_backed_profile=env_backed,
            llm_provider="openai_responses",
            llm_model="gpt-5-nano",
            open_domain_enabled=open_domain_enabled,
            live_smoke_artifact_path="tmp/qa/artifact.json" if env_backed else None,
            live_smoke_artifact_present=env_backed,
            live_smoke_artifact_success=True if env_backed else None,
            live_smoke_artifact_created_at="2026-03-25T00:00:00+00:00" if env_backed else None,
            live_smoke_artifact_age_hours=1.0 if env_backed else None,
            live_smoke_artifact_fresh=True if env_backed else None,
            live_smoke_artifact_fresh_reason=None,
            live_smoke_artifact_profile_match=True if env_backed else None,
            live_smoke_artifact_match_reason=None,
            live_smoke_artifact_open_domain_verified=True if env_backed else None,
            live_smoke_artifact_error=None,
        )


if __name__ == "__main__":
    unittest.main()
