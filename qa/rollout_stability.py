"""Repeated rollout-gate stability checks for env-backed QA candidates."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from evals.run_qa_eval import DEFAULT_CORPUS_PATH, QaEvalComparisonReport, compare_eval_profiles, load_qa_eval_cases
from qa.rollout_profiles import live_smoke_artifact_path_for_candidate, rollout_stability_artifact_path_for_candidate

_LIVE_SMOKE_ARTIFACT_ENV = "JARVIS_QA_OPENAI_LIVE_ARTIFACT"
_ROLLOUT_STABILITY_ARTIFACT_ENV = "JARVIS_QA_ROLLOUT_STABILITY_ARTIFACT"
_BASELINE_PROFILE = "deterministic"
_CANDIDATE_PROFILES = ("llm_env", "llm_env_strict")


@dataclass(slots=True)
class RolloutStabilityRunSummary:
    """One repeated comparative-gate run summarized for operator review."""

    run_index: int
    default_switch_allowed: bool
    recommended_default_profile: str
    blockers: list[str] = field(default_factory=list)
    failed_case_ids: list[str] = field(default_factory=list)
    fallback_case_ids: list[str] = field(default_factory=list)
    grounding_passed: int = 0
    grounding_total: int = 0
    open_domain_passed: int = 0
    open_domain_total: int = 0
    refusal_passed: int = 0
    refusal_total: int = 0
    fallback_total: int = 0
    answer_total: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_index": self.run_index,
            "default_switch_allowed": self.default_switch_allowed,
            "recommended_default_profile": self.recommended_default_profile,
            "blockers": list(self.blockers),
            "failed_case_ids": list(self.failed_case_ids),
            "fallback_case_ids": list(self.fallback_case_ids),
            "grounding_passed": self.grounding_passed,
            "grounding_total": self.grounding_total,
            "open_domain_passed": self.open_domain_passed,
            "open_domain_total": self.open_domain_total,
            "refusal_passed": self.refusal_passed,
            "refusal_total": self.refusal_total,
            "fallback_total": self.fallback_total,
            "answer_total": self.answer_total,
        }


@dataclass(slots=True)
class RolloutStabilityReport:
    """Aggregate stability picture over repeated env-backed gate runs."""

    baseline_profile: str
    candidate_profile: str
    runs_requested: int
    runs: list[RolloutStabilityRunSummary] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        blocker_counts = Counter()
        failed_case_counts = Counter()
        fallback_case_counts = Counter()
        for run in self.runs:
            blocker_counts.update(run.blockers)
            failed_case_counts.update(run.failed_case_ids)
            fallback_case_counts.update(run.fallback_case_ids)
        return {
            "baseline_profile": self.baseline_profile,
            "candidate_profile": self.candidate_profile,
            "runs_requested": self.runs_requested,
            "gate_passes": self.gate_passes,
            "runs": [run.to_dict() for run in self.runs],
            "blocker_counts": dict(blocker_counts),
            "failed_case_counts": dict(failed_case_counts),
            "fallback_case_counts": dict(fallback_case_counts),
        }

    @property
    def gate_passes(self) -> int:
        return sum(1 for run in self.runs if run.default_switch_allowed)


def run_rollout_stability(
    candidate_profile: str,
    *,
    runs: int = 3,
    comparison_runner: Callable[..., QaEvalComparisonReport] | None = None,
) -> RolloutStabilityReport:
    """Run the comparative gate repeatedly and summarize stability."""
    candidate = str(candidate_profile or "").strip()
    if candidate not in _CANDIDATE_PROFILES:
        raise ValueError(f"Unsupported rollout candidate profile: {candidate_profile!r}.")
    normalized_runs = int(runs)
    if normalized_runs <= 0:
        raise ValueError("runs must be positive.")
    cases = load_qa_eval_cases(DEFAULT_CORPUS_PATH)
    runner = comparison_runner or compare_eval_profiles
    run_summaries: list[RolloutStabilityRunSummary] = []
    for run_index in range(1, normalized_runs + 1):
        comparison = runner(
            cases,
            profiles=[_BASELINE_PROFILE, candidate],
            baseline_profile=_BASELINE_PROFILE,
            candidate_profile=candidate,
        )
        candidate_summary = _candidate_summary(comparison, candidate)
        candidate_interaction_results = _candidate_interaction_results(candidate_summary)
        candidate_answer_results = _candidate_answer_results(candidate_summary)
        failed_case_ids = [result.case_id for result in candidate_interaction_results if not result.passed]
        fallback_case_ids = [
            result.case_id
            for result in candidate_answer_results
            if bool((result.details or {}).get("fallback_used"))
        ]
        run_summaries.append(
            RolloutStabilityRunSummary(
                run_index=run_index,
                default_switch_allowed=bool(comparison.default_switch_allowed),
                recommended_default_profile=str(comparison.recommended_default_profile or "").strip(),
                blockers=list(comparison.blockers),
                failed_case_ids=failed_case_ids,
                fallback_case_ids=fallback_case_ids,
                grounding_passed=int(candidate_summary.grounding_passed),
                grounding_total=int(candidate_summary.grounding_total),
                open_domain_passed=int(candidate_summary.open_domain_passed),
                open_domain_total=int(candidate_summary.open_domain_total),
                refusal_passed=int(candidate_summary.refusal_passed),
                refusal_total=int(candidate_summary.refusal_total),
                fallback_total=int(candidate_summary.fallback_total),
                answer_total=int(candidate_summary.answer_total),
            )
        )
    return RolloutStabilityReport(
        baseline_profile=_BASELINE_PROFILE,
        candidate_profile=candidate,
        runs_requested=normalized_runs,
        runs=run_summaries,
    )


def format_rollout_stability_report(report: RolloutStabilityReport) -> str:
    """Render one operator-friendly repeated-gate stability summary."""
    lines = [
        "JARVIS QA Gate Stability",
        f"baseline: {report.baseline_profile}",
        f"candidate: {report.candidate_profile}",
        f"runs: {report.runs_requested}",
        f"gate passes: {report.gate_passes}/{report.runs_requested} ({_percent(report.gate_passes, report.runs_requested)})",
    ]
    if report.runs:
        lines.append("run summaries:")
        for run in report.runs:
            blockers_text = ", ".join(run.blockers) if run.blockers else "none"
            lines.append(
                "  - "
                f"run {run.run_index}: "
                f"pass={'yes' if run.default_switch_allowed else 'no'}; "
                f"grounding={run.grounding_passed}/{run.grounding_total}; "
                f"open-domain={run.open_domain_passed}/{run.open_domain_total}; "
                f"refusal={run.refusal_passed}/{run.refusal_total}; "
                f"fallback={run.fallback_total}/{run.answer_total}; "
                f"blockers={blockers_text}"
            )
    blocker_counts = Counter()
    failed_case_counts = Counter()
    fallback_case_counts = Counter()
    for run in report.runs:
        blocker_counts.update(run.blockers)
        failed_case_counts.update(run.failed_case_ids)
        fallback_case_counts.update(run.fallback_case_ids)
    if blocker_counts:
        lines.append("blocker frequency:")
        for blocker, count in blocker_counts.most_common():
            lines.append(f"  - {blocker}: {count}/{report.runs_requested}")
    else:
        lines.append("blocker frequency: none")
    if failed_case_counts:
        lines.append("failed-case frequency:")
        for case_id, count in failed_case_counts.most_common():
            lines.append(f"  - {case_id}: {count}/{report.runs_requested}")
    else:
        lines.append("failed-case frequency: none")
    if fallback_case_counts:
        lines.append("fallback-case frequency:")
        for case_id, count in fallback_case_counts.most_common():
            lines.append(f"  - {case_id}: {count}/{report.runs_requested}")
    else:
        lines.append("fallback-case frequency: none")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Run repeated rollout-gate stability checks from the command line."""
    parser = argparse.ArgumentParser(description="Run repeated env-backed QA rollout-gate checks.")
    parser.add_argument("candidate_profile", choices=list(_CANDIDATE_PROFILES))
    parser.add_argument("--runs", type=int, default=3, help="How many repeated comparative-gate runs to execute.")
    parser.add_argument("--json", action="store_true", help="Print the aggregated report as JSON.")
    args = parser.parse_args(argv)

    os.environ.setdefault(_LIVE_SMOKE_ARTIFACT_ENV, str(live_smoke_artifact_path_for_candidate(args.candidate_profile)))
    stability_artifact_path = Path(
        str(
            os.environ.get(
                _ROLLOUT_STABILITY_ARTIFACT_ENV,
                str(rollout_stability_artifact_path_for_candidate(args.candidate_profile)),
            )
        ).strip()
    )
    report = run_rollout_stability(args.candidate_profile, runs=args.runs)
    _write_rollout_stability_artifact(report, artifact_path=stability_artifact_path)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(format_rollout_stability_report(report))
    return 0 if report.gate_passes == report.runs_requested else 1


def _candidate_summary(comparison: QaEvalComparisonReport, candidate_profile: str):
    for summary in comparison.summaries:
        if summary.profile == candidate_profile:
            return summary
    raise ValueError(f"Candidate profile {candidate_profile!r} is missing from comparison summaries.")


def _candidate_interaction_results(candidate_summary: Any) -> list[Any]:
    default_profile = str(getattr(candidate_summary.report, "default_profile", "") or "")
    return [
        result
        for result in list(getattr(candidate_summary.report, "results", []) or [])
        if getattr(result, "case_type", None) == "interaction"
        and str((getattr(result, "details", {}) or {}).get("profile") or "") == default_profile
    ]


def _candidate_answer_results(candidate_summary: Any) -> list[Any]:
    return [
        result
        for result in _candidate_interaction_results(candidate_summary)
        if bool((getattr(result, "details", {}) or {}).get("answer_calls"))
        and not str((getattr(result, "details", {}) or {}).get("actual_error_code") or "").strip()
    ]


def _percent(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "n/a"
    return f"{(float(numerator) / float(denominator)) * 100.0:.1f}%"


def _write_rollout_stability_artifact(report: RolloutStabilityReport, *, artifact_path: Path) -> None:
    payload = {
        "schema_version": 1,
        "runner": "qa.rollout_stability",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "report": report.to_dict(),
    }
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
