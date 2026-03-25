"""Centralized eval runner for QA routing and answer behavior."""

from __future__ import annotations

import argparse
import json
import time
from contextlib import ExitStack, nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import cli
from context.session_context import SessionContext
from interaction.interaction_manager import InteractionManager
from parser.command_parser import parse_command
from qa.answer_backend import AnswerBackendKind
from qa.answer_config import AnswerBackendConfig, LlmBackendConfig, load_answer_backend_config
from qa.answer_engine import ErrorCategory, ErrorCode, JarvisError, classify_question
from qa.deterministic_backend import DeterministicAnswerBackend
from qa.grounding_verifier import support_is_meaningful
from qa.llm_provider import LlmProviderKind
from target import Target, TargetType

_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS_PATH = _REPO_ROOT / "evals" / "qa_cases.json"
_LIVE_SMOKE_ENABLE_ENV = "JARVIS_QA_OPENAI_LIVE_SMOKE"
_LIVE_SMOKE_API_KEY_ENV = "OPENAI_API_KEY"
_LIVE_SMOKE_MODEL_ENV = "JARVIS_QA_OPENAI_LIVE_MODEL"
_LIVE_SMOKE_QUESTION_ENV = "JARVIS_QA_OPENAI_LIVE_QUESTION"
_LIVE_SMOKE_DEFAULT_MODEL = "gpt-5-nano"
_LIVE_SMOKE_DEFAULT_QUESTION = "What can you do?"
_EVAL_MISSING_KEY_ENV = "JARVIS_QA_EVAL_MISSING_API_KEY_DO_NOT_SET"
_PROFILE_CHOICES = (
    "deterministic",
    "llm_missing_key_fallback",
    "llm_open_domain_mock",
    "llm_open_domain_missing_key",
    "llm_env",
    "llm_env_strict",
)
_DEFAULT_GATE_BASELINE_PROFILE = "deterministic"
_DEFAULT_GATE_CANDIDATE_PROFILE = "llm_env"
_DEFAULT_GATE_THRESHOLDS = {
    "routing_safety_regressions_max": 0,
    "command_regression_pass_rate_min": 1.0,
    "grounding_pass_rate_min": 1.0,
    "unsupported_honesty_rate_min": 1.0,
    "source_attribution_quality_rate_min": 0.95,
    "open_domain_answer_pass_rate_min": 1.0,
    "refusal_pass_rate_min": 1.0,
    "provenance_pass_rate_min": 1.0,
    "fallback_frequency_max": 0.05,
    "usage_measurement_required": True,
}


@dataclass(slots=True)
class QaEvalCase:
    """One eval case loaded from the centralized QA corpus."""

    id: str
    case_type: str
    category: str
    profiles: list[str] = field(default_factory=list)
    raw_input: str | None = None
    runtime_state: str | None = None
    session_context: dict[str, Any] = field(default_factory=dict)
    backend_profile: str | None = None
    expected_interaction_kind: str | None = None
    expected_question_type: str | None = None
    expected_command_intent: str | None = None
    should_call_runtime: bool | None = None
    should_call_answer_engine: bool | None = None
    expected_answer_kind: str | None = None
    expected_answer_provenance: str | None = None
    expected_sources_count_min: int | None = None
    expected_sources_count_max: int | None = None
    expected_warning_contains: str | None = None
    expected_error_code: str | None = None
    expected_answer_contains: str | None = None
    expected_clarification_contains: str | None = None
    mock_answer_result: dict[str, Any] = field(default_factory=dict)
    voice_input: str | None = None
    expected_normalized_input: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    expected_enabled: bool | None = None
    expected_skip_reason_contains: str | None = None
    expected_backend_kind: str | None = None
    expected_model: str | None = None
    expected_api_key_env: str | None = None
    expected_question: str | None = None


@dataclass(slots=True)
class QaEvalCaseResult:
    """Per-case eval outcome with explicit checks."""

    case_id: str
    case_type: str
    category: str
    passed: bool
    checks: dict[str, bool]
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class QaEvalReport:
    """Top-level eval report over one corpus run."""

    default_profile: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    routing_total: int
    routing_passed: int
    grounding_total: int
    grounding_passed: int
    command_regression_total: int
    command_regression_passed: int
    results: list[QaEvalCaseResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of the report."""
        return {
            "default_profile": self.default_profile,
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "failed_cases": self.failed_cases,
            "routing_total": self.routing_total,
            "routing_passed": self.routing_passed,
            "routing_accuracy": _rate(self.routing_passed, self.routing_total),
            "grounding_total": self.grounding_total,
            "grounding_passed": self.grounding_passed,
            "grounding_pass_rate": _rate(self.grounding_passed, self.grounding_total),
            "command_regression_total": self.command_regression_total,
            "command_regression_passed": self.command_regression_passed,
            "command_regression_pass_rate": _rate(self.command_regression_passed, self.command_regression_total),
            "results": [
                {
                    "case_id": result.case_id,
                    "case_type": result.case_type,
                    "category": result.category,
                    "passed": result.passed,
                    "checks": dict(result.checks),
                    "details": dict(result.details),
                }
                for result in self.results
            ],
        }


@dataclass(slots=True)
class QaEvalProfileSummary:
    """Aggregated quality and safety summary for one eval profile."""

    profile: str
    report: QaEvalReport
    routing_total: int
    routing_passed: int
    grounding_total: int
    grounding_passed: int
    command_regression_total: int
    command_regression_passed: int
    unsupported_total: int
    unsupported_passed: int
    source_attribution_total: int
    source_attribution_passed: int
    open_domain_total: int
    open_domain_passed: int
    refusal_total: int
    refusal_passed: int
    provenance_total: int
    provenance_passed: int
    answer_total: int
    fallback_total: int
    avg_interaction_latency_ms: float | None
    usage_sample_count: int
    usage_input_tokens_total: int | None
    usage_output_tokens_total: int | None
    usage_total_tokens_total: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "report": self.report.to_dict(),
            "routing_total": self.routing_total,
            "routing_passed": self.routing_passed,
            "routing_accuracy": _rate(self.routing_passed, self.routing_total),
            "grounding_total": self.grounding_total,
            "grounding_passed": self.grounding_passed,
            "grounding_pass_rate": _rate(self.grounding_passed, self.grounding_total),
            "command_regression_total": self.command_regression_total,
            "command_regression_passed": self.command_regression_passed,
            "command_regression_pass_rate": _rate(self.command_regression_passed, self.command_regression_total),
            "unsupported_total": self.unsupported_total,
            "unsupported_passed": self.unsupported_passed,
            "unsupported_honesty_rate": _rate(self.unsupported_passed, self.unsupported_total),
            "source_attribution_total": self.source_attribution_total,
            "source_attribution_passed": self.source_attribution_passed,
            "source_attribution_quality_rate": _rate(self.source_attribution_passed, self.source_attribution_total),
            "open_domain_total": self.open_domain_total,
            "open_domain_passed": self.open_domain_passed,
            "open_domain_answer_pass_rate": _rate(self.open_domain_passed, self.open_domain_total),
            "refusal_total": self.refusal_total,
            "refusal_passed": self.refusal_passed,
            "refusal_pass_rate": _rate(self.refusal_passed, self.refusal_total),
            "provenance_total": self.provenance_total,
            "provenance_passed": self.provenance_passed,
            "provenance_pass_rate": _rate(self.provenance_passed, self.provenance_total),
            "answer_total": self.answer_total,
            "fallback_total": self.fallback_total,
            "fallback_frequency": _rate(self.fallback_total, self.answer_total),
            "avg_interaction_latency_ms": self.avg_interaction_latency_ms,
            "usage_sample_count": self.usage_sample_count,
            "usage_input_tokens_total": self.usage_input_tokens_total,
            "usage_output_tokens_total": self.usage_output_tokens_total,
            "usage_total_tokens_total": self.usage_total_tokens_total,
        }


@dataclass(slots=True)
class QaEvalComparisonReport:
    """Comparative report used for the LLM default-decision gate."""

    baseline_profile: str
    candidate_profile: str
    summaries: list[QaEvalProfileSummary]
    routing_safety_regressions: int
    default_switch_allowed: bool
    recommended_default_profile: str
    thresholds: dict[str, Any]
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline_profile": self.baseline_profile,
            "candidate_profile": self.candidate_profile,
            "routing_safety_regressions": self.routing_safety_regressions,
            "default_switch_allowed": self.default_switch_allowed,
            "recommended_default_profile": self.recommended_default_profile,
            "thresholds": dict(self.thresholds),
            "blockers": list(self.blockers),
            "summaries": [summary.to_dict() for summary in self.summaries],
        }


@dataclass(slots=True)
class _EvalRuntimeManager:
    """Minimal runtime stub used by the eval harness to avoid desktop execution."""

    current_state: str = "idle"
    active_command: object | None = None
    current_step: object | None = None
    clarification_request: object | None = None
    confirmation_request: object | None = None
    last_error: object | None = None
    completed_steps: list[object] = field(default_factory=list)
    completed_step_results: dict[str, Any] = field(default_factory=dict)
    blocked_reason: str | None = None
    handle_calls: list[str] = field(default_factory=list)

    def handle_input(self, raw_input: str, session_context: SessionContext | None = None) -> object:
        """Record the command path call and return a minimal runtime-like result."""
        self.handle_calls.append(raw_input)
        command_summary = None
        try:
            parsed = parse_command(raw_input, session_context)
        except Exception:
            parsed = None
        if parsed is not None:
            intent_value = _enum_value(getattr(parsed, "intent", ""))
            targets = [str(getattr(target, "name", "") or "").strip() for target in list(getattr(parsed, "targets", []) or [])]
            targets = [target for target in targets if target]
            command_summary = f"{intent_value}: {', '.join(targets)}" if targets else intent_value or None
        return SimpleNamespace(
            runtime_state="completed",
            visibility={
                "runtime_state": "completed",
                "command_summary": command_summary,
                "completed_steps": [],
                "can_cancel": False,
            },
        )


class _EvalMockLlmProvider:
    """Deterministic mock provider used for profile-scoped open-domain evals."""

    provider_kind = LlmProviderKind.OPENAI_RESPONSES

    def __init__(self, case: QaEvalCase) -> None:
        self._case = case
        self._fallback_backend = DeterministicAnswerBackend()

    def answer(
        self,
        question: object,
        *,
        grounding_bundle: object,
        config: object,
        session_context: SessionContext | None = None,
        runtime_snapshot: dict[str, Any] | None = None,
        debug_trace: dict[str, Any] | None = None,
    ) -> object:
        question_type = _enum_value(getattr(question, "question_type", ""))
        if question_type != "open_domain_general":
            return self._fallback_backend.answer(
                question,
                session_context=session_context,
                runtime_snapshot=runtime_snapshot,
                grounding_bundle=grounding_bundle,
                config=config,
                debug_trace=debug_trace,
            )
        del question, grounding_bundle, config, session_context, runtime_snapshot
        if debug_trace is not None:
            debug_trace["provider_response_parse"] = {
                "provider": "eval_mock_open_domain",
                "result": "passed",
                "request_id": "eval-mock-request",
                "correlation_id": self._case.id,
            }
        payload = dict(self._case.mock_answer_result or {})
        if not payload:
            raise JarvisError(
                category=ErrorCategory.ANSWER_ERROR,
                code=ErrorCode.UNSUPPORTED_QUESTION,
                message="No mock open-domain answer was configured for this eval case.",
                details={"case_id": self._case.id},
                blocking=False,
                terminal=True,
            )
        raw_attributions = list(payload.get("source_attributions", []) or [])
        source_attributions = [
            SimpleNamespace(
                source=str((entry or {}).get("source", "") or "").strip(),
                support=str((entry or {}).get("support", "") or "").strip(),
            )
            for entry in raw_attributions
            if isinstance(entry, dict)
        ]
        return SimpleNamespace(
            answer_text=str(payload.get("answer_text", "") or "").strip(),
            sources=[str(source).strip() for source in list(payload.get("sources", []) or []) if str(source).strip()],
            source_attributions=source_attributions,
            confidence=float(payload.get("confidence", 0.72) or 0.72),
            warning=str(payload.get("warning", "") or "").strip() or None,
            answer_kind=str(payload.get("answer_kind", "") or "").strip() or "open_domain_model",
            provenance=str(payload.get("provenance", "") or "").strip() or "model_knowledge",
            interaction_mode="question",
        )

    def build_request_payload(
        self,
        question: object,
        *,
        grounding_bundle: object,
        config: object,
        session_context: SessionContext | None = None,
        runtime_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del question, grounding_bundle, config, session_context, runtime_snapshot
        return {"provider": "eval_mock_open_domain", "case_id": self._case.id}


def load_qa_eval_cases(path: Path | str = DEFAULT_CORPUS_PATH) -> list[QaEvalCase]:
    """Load and validate the centralized QA eval corpus."""
    corpus_path = Path(path)
    payload = json.loads(corpus_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("QA eval corpus must be a JSON list.")

    cases: list[QaEvalCase] = []
    seen_ids: set[str] = set()
    for raw_case in payload:
        if not isinstance(raw_case, dict):
            raise ValueError("Each QA eval case must be a JSON object.")
        case = QaEvalCase(**raw_case)
        _validate_case(case)
        if case.id in seen_ids:
            raise ValueError(f"Duplicate QA eval case id: {case.id}.")
        seen_ids.add(case.id)
        cases.append(case)
    return cases


def select_eval_cases(cases: list[QaEvalCase], case_ids: list[str] | None = None) -> list[QaEvalCase]:
    """Return either the full corpus or the explicitly selected case ids."""
    if not case_ids:
        return list(cases)
    wanted = {case_id.strip() for case_id in case_ids if case_id.strip()}
    return [case for case in cases if case.id in wanted]


def run_eval_cases(cases: list[QaEvalCase], *, default_profile: str = "deterministic") -> QaEvalReport:
    """Run the selected QA eval cases and return a reproducible report."""
    results: list[QaEvalCaseResult] = []
    for case in cases:
        if not _case_applies_to_profile(case, default_profile):
            continue
        if case.case_type == "interaction":
            results.append(_run_interaction_case(case, default_profile=default_profile))
            continue
        if case.case_type == "voice":
            results.append(_run_voice_case(case))
            continue
        if case.case_type == "live_smoke":
            results.append(_run_live_smoke_case(case))
            continue
        raise ValueError(f"Unsupported QA eval case_type: {case.case_type!r}.")

    passed_cases = sum(1 for result in results if result.passed)
    routing_results = [result for result in results if result.case_type == "interaction" and "interaction_kind" in result.checks]
    grounding_results = [result for result in results if result.case_type == "interaction" and "grounding" in result.checks]
    command_results = [result for result in results if result.case_type == "interaction" and "command_intent" in result.checks]

    return QaEvalReport(
        default_profile=default_profile,
        total_cases=len(results),
        passed_cases=passed_cases,
        failed_cases=len(results) - passed_cases,
        routing_total=len(routing_results),
        routing_passed=sum(1 for result in routing_results if result.checks["interaction_kind"]),
        grounding_total=len(grounding_results),
        grounding_passed=sum(1 for result in grounding_results if result.checks["grounding"]),
        command_regression_total=len(command_results),
        command_regression_passed=sum(1 for result in command_results if result.checks["command_intent"]),
        results=results,
    )


def format_report(report: QaEvalReport) -> str:
    """Return a compact human-readable eval report."""
    failed_results = [result for result in report.results if not result.passed]
    lines = [
        "JARVIS QA Eval Report",
        f"profile: {report.default_profile}",
        f"total cases: {report.total_cases}",
        f"passed: {report.passed_cases}",
        f"failed: {report.failed_cases}",
        f"routing accuracy: {report.routing_passed}/{report.routing_total} ({_percent(report.routing_passed, report.routing_total)})",
        f"grounding pass rate: {report.grounding_passed}/{report.grounding_total} ({_percent(report.grounding_passed, report.grounding_total)})",
        (
            "command-regression pass rate: "
            f"{report.command_regression_passed}/{report.command_regression_total} "
            f"({_percent(report.command_regression_passed, report.command_regression_total)})"
        ),
    ]
    if not failed_results:
        lines.append("failed cases: none")
        return "\n".join(lines)

    lines.append("failed cases:")
    for result in failed_results:
        failed_checks = ", ".join(name for name, passed in result.checks.items() if not passed) or "unknown"
        lines.append(f"- {result.case_id} [{result.category}] -> {failed_checks}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Run the QA eval corpus from the command line."""
    parser = argparse.ArgumentParser(description="Run the JARVIS QA eval corpus.")
    parser.add_argument("--corpus", default=str(DEFAULT_CORPUS_PATH), help="Path to the eval corpus JSON file.")
    parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        help="Optional case id filter. May be passed multiple times.",
    )
    parser.add_argument(
        "--default-profile",
        default="deterministic",
        choices=list(_PROFILE_CHOICES),
        help="Default answer-backend profile for interaction cases that do not override it.",
    )
    parser.add_argument(
        "--compare-profile",
        action="append",
        default=[],
        choices=list(_PROFILE_CHOICES),
        help="Compare multiple eval profiles on the same corpus. Pass multiple times.",
    )
    parser.add_argument(
        "--gate-candidate-profile",
        default=None,
        choices=list(_PROFILE_CHOICES),
        help="Run the LLM default-decision gate against the selected candidate profile.",
    )
    parser.add_argument("--json", action="store_true", help="Print the report as JSON.")
    args = parser.parse_args(argv)

    cases = select_eval_cases(load_qa_eval_cases(args.corpus), args.case_id)
    if args.compare_profile or args.gate_candidate_profile:
        compare_profiles = list(dict.fromkeys(args.compare_profile or []))
        if args.gate_candidate_profile is not None and args.gate_candidate_profile not in compare_profiles:
            compare_profiles.append(args.gate_candidate_profile)
        if _DEFAULT_GATE_BASELINE_PROFILE not in compare_profiles:
            compare_profiles.insert(0, _DEFAULT_GATE_BASELINE_PROFILE)
        comparison = compare_eval_profiles(
            cases,
            profiles=compare_profiles,
            baseline_profile=_DEFAULT_GATE_BASELINE_PROFILE,
            candidate_profile=args.gate_candidate_profile or _default_candidate_profile(compare_profiles),
        )
        if args.json:
            print(json.dumps(comparison.to_dict(), indent=2, sort_keys=True))
        else:
            print(format_comparison_report(comparison))
        return 0 if comparison.default_switch_allowed else 1
    report = run_eval_cases(cases, default_profile=args.default_profile)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(format_report(report))
    return 0 if report.failed_cases == 0 else 1


def _run_interaction_case(case: QaEvalCase, *, default_profile: str) -> QaEvalCaseResult:
    runtime_manager = _EvalRuntimeManager(current_state=case.runtime_state or "idle")
    session_context = _build_session_context(case.session_context)
    answer_calls: list[dict[str, Any]] = []
    profile = case.backend_profile or default_profile
    config = _build_backend_config(profile)

    import interaction.interaction_manager as interaction_manager_module

    real_answer_question = interaction_manager_module.answer_question

    def _spy_answer_question(*args: Any, **kwargs: Any) -> object:
        answer_calls.append({"args": args, "kwargs": kwargs})
        return real_answer_question(*args, **kwargs)

    started_at = time.perf_counter()
    with ExitStack() as stack:
        stack.enter_context(patch("interaction.interaction_manager.answer_question", side_effect=_spy_answer_question))
        stack.enter_context(patch.dict("os.environ", {"JARVIS_QA_DEBUG": "1"}, clear=False))
        stack.enter_context(_provider_patch_for_profile(profile, case))
        manager = InteractionManager(runtime_manager=runtime_manager, answer_backend_config=config)
        result = manager.handle_input(case.raw_input or "", session_context=session_context)
    latency_ms = round((time.perf_counter() - started_at) * 1000.0, 3)

    actual_interaction_kind = _enum_value(getattr(result, "interaction_mode", ""))
    actual_error_code = _enum_value(getattr(getattr(result, "error", None), "code", ""))
    actual_answer_kind = _enum_value(getattr(getattr(result, "answer_result", None), "answer_kind", ""))
    actual_answer_provenance = _enum_value(getattr(getattr(result, "answer_result", None), "provenance", ""))
    actual_warning = str(getattr(getattr(result, "answer_result", None), "warning", "") or "").strip()
    actual_answer_text = str(getattr(getattr(result, "answer_result", None), "answer_text", "") or "").strip()
    actual_sources = list(getattr(getattr(result, "answer_result", None), "sources", []) or [])
    actual_source_attributions = list(getattr(getattr(result, "answer_result", None), "source_attributions", []) or [])
    actual_clarification = str(getattr(getattr(result, "clarification_request", None), "message", "") or "").strip()
    debug_trace = dict((getattr(result, "metadata", None) or {}).get("debug", {}) or {})
    provider_parse_debug = dict(debug_trace.get("provider_response_parse", {}) or {})
    fallback_debug = dict(debug_trace.get("fallback", {}) or {})

    checks: dict[str, bool] = {}
    details = {
        "profile": profile,
        "actual_interaction_kind": actual_interaction_kind,
        "runtime_calls": len(runtime_manager.handle_calls),
        "answer_calls": len(answer_calls),
        "actual_error_code": actual_error_code or None,
        "actual_answer_kind": actual_answer_kind or None,
        "actual_answer_provenance": actual_answer_provenance or None,
        "actual_warning": actual_warning or None,
        "actual_sources_count": len(actual_sources),
        "actual_source_attribution_count": len(actual_source_attributions),
        "actual_source_attribution_quality": _source_attribution_quality(
            actual_sources,
            actual_source_attributions,
        ),
        "fallback_used": bool(fallback_debug.get("deterministic_fallback")) or "LLM backend fallback" in actual_warning,
        "latency_ms": latency_ms,
        "expected_error_code": case.expected_error_code,
        "expected_answer_kind": case.expected_answer_kind,
        "expected_answer_provenance": case.expected_answer_provenance,
        "usage_input_tokens": _int_or_none(provider_parse_debug.get("input_tokens")),
        "usage_output_tokens": _int_or_none(provider_parse_debug.get("output_tokens")),
        "usage_total_tokens": _int_or_none(provider_parse_debug.get("total_tokens")),
    }

    if case.expected_interaction_kind is not None:
        checks["interaction_kind"] = actual_interaction_kind == case.expected_interaction_kind
    if case.should_call_runtime is not None:
        checks["runtime_called"] = bool(runtime_manager.handle_calls) is case.should_call_runtime
    if case.should_call_answer_engine is not None:
        checks["answer_engine_called"] = bool(answer_calls) is case.should_call_answer_engine
    if case.expected_question_type is not None:
        classified_input = case.raw_input or ""
        if answer_calls:
            classified_input = str(answer_calls[0].get("args", [""])[0] or "")
        try:
            actual_question_type = _enum_value(
                classify_question(
                    classified_input,
                    session_context=session_context,
                    backend_config=config,
                ).question_type
            )
        except Exception:
            actual_question_type = None
        details["actual_question_input"] = classified_input or None
        details["actual_question_type"] = actual_question_type
        checks["question_type"] = actual_question_type == case.expected_question_type
    if case.expected_command_intent is not None:
        actual_command_intent = None
        if runtime_manager.handle_calls:
            try:
                actual_command_intent = _enum_value(parse_command(runtime_manager.handle_calls[0], session_context).intent)
            except Exception:
                actual_command_intent = None
        details["actual_command_intent"] = actual_command_intent
        checks["command_intent"] = actual_command_intent == case.expected_command_intent
    if case.expected_answer_kind is not None:
        checks["answer_kind"] = actual_answer_kind == case.expected_answer_kind
    if case.expected_answer_provenance is not None:
        checks["answer_provenance"] = actual_answer_provenance == case.expected_answer_provenance
    if case.expected_sources_count_min is not None:
        checks["grounding"] = getattr(result, "error", None) is None and len(actual_sources) >= case.expected_sources_count_min
    if case.expected_sources_count_max is not None:
        checks["sources_count_max"] = getattr(result, "error", None) is None and len(actual_sources) <= case.expected_sources_count_max
    if case.expected_warning_contains is not None:
        checks["warning"] = case.expected_warning_contains in actual_warning
    if case.expected_error_code is not None:
        checks["error_code"] = actual_error_code == case.expected_error_code
    elif getattr(result, "error", None) is not None:
        checks["unexpected_error"] = False
    if case.expected_answer_contains is not None:
        checks["answer_text"] = case.expected_answer_contains in actual_answer_text
    if case.expected_clarification_contains is not None:
        checks["clarification"] = case.expected_clarification_contains in actual_clarification

    return QaEvalCaseResult(
        case_id=case.id,
        case_type=case.case_type,
        category=case.category,
        passed=all(checks.values()) if checks else True,
        checks=checks,
        details=details,
    )


def _run_voice_case(case: QaEvalCase) -> QaEvalCaseResult:
    started_at = time.perf_counter()
    actual_normalized = cli._normalize_voice_command(case.voice_input or "")  # noqa: SLF001
    checks = {"normalized_input": actual_normalized == (case.expected_normalized_input or "")}
    return QaEvalCaseResult(
        case_id=case.id,
        case_type=case.case_type,
        category=case.category,
        passed=all(checks.values()),
        checks=checks,
        details={"actual_normalized_input": actual_normalized, "latency_ms": round((time.perf_counter() - started_at) * 1000.0, 3)},
    )


def _run_live_smoke_case(case: QaEvalCase) -> QaEvalCaseResult:
    started_at = time.perf_counter()
    env = dict(case.env or {})
    enabled = _live_smoke_enabled(env)
    skip_reason = _live_smoke_skip_reason(env)
    checks: dict[str, bool] = {}
    details = {
        "enabled": enabled,
        "skip_reason": skip_reason,
    }

    if case.expected_enabled is not None:
        checks["enabled"] = enabled is case.expected_enabled
    if case.expected_skip_reason_contains is not None:
        checks["skip_reason"] = case.expected_skip_reason_contains in str(skip_reason)
    elif case.expected_enabled:
        checks["skip_reason"] = skip_reason is None
    if case.expected_backend_kind or case.expected_model or case.expected_api_key_env or case.expected_question:
        config = _live_smoke_config(env)
        question = _live_smoke_question(env)
        details["backend_kind"] = _enum_value(getattr(config, "backend_kind", ""))
        details["model"] = str(getattr(config.llm, "model", "") or "")
        details["api_key_env"] = str(getattr(config.llm, "api_key_env", "") or "")
        details["question"] = question
        if case.expected_backend_kind is not None:
            checks["backend_kind"] = details["backend_kind"] == case.expected_backend_kind
        if case.expected_model is not None:
            checks["model"] = details["model"] == case.expected_model
        if case.expected_api_key_env is not None:
            checks["api_key_env"] = details["api_key_env"] == case.expected_api_key_env
        if case.expected_question is not None:
            checks["question"] = details["question"] == case.expected_question

    return QaEvalCaseResult(
        case_id=case.id,
        case_type=case.case_type,
        category=case.category,
        passed=all(checks.values()) if checks else True,
        checks=checks,
        details={**details, "latency_ms": round((time.perf_counter() - started_at) * 1000.0, 3)},
    )


def _build_session_context(payload: dict[str, Any]) -> SessionContext:
    session_context = SessionContext()
    recent_project_context = str(payload.get("recent_project_context", "") or "").strip()
    if recent_project_context:
        session_context.set_recent_project_context(recent_project_context)
    recent_primary_target = payload.get("recent_primary_target")
    if isinstance(recent_primary_target, dict):
        target_type = _target_type(recent_primary_target.get("type"))
        target_name = str(recent_primary_target.get("name", "") or "").strip()
        target_path = str(recent_primary_target.get("path", "") or "").strip() or None
        if target_type is not None and (target_name or target_path):
            session_context.set_recent_primary_target(
                Target(type=target_type, name=target_name or (target_path or ""), path=target_path),
                action=str(payload.get("recent_primary_action", "") or "").strip() or None,
            )
    recent_answer_topic = str(payload.get("recent_answer_topic", "") or "").strip()
    recent_answer_scope = str(payload.get("recent_answer_scope", "") or "").strip()
    raw_recent_answer_sources = payload.get("recent_answer_sources")
    recent_answer_sources: list[str] = []
    if isinstance(raw_recent_answer_sources, list):
        for source in raw_recent_answer_sources:
            source_text = str(source or "").strip()
            if not source_text:
                continue
            source_path = Path(source_text)
            if not source_path.is_absolute():
                source_text = str((_REPO_ROOT / source_path).resolve())
            recent_answer_sources.append(source_text)
    if recent_answer_topic or recent_answer_scope or recent_answer_sources:
        session_context.set_recent_answer_context(
            topic=recent_answer_topic or None,
            scope=recent_answer_scope or None,
            sources=recent_answer_sources,
        )
    pending_interaction_question_input = str(payload.get("pending_interaction_question_input", "") or "").strip()
    pending_interaction_command_input = str(payload.get("pending_interaction_command_input", "") or "").strip()
    if pending_interaction_question_input or pending_interaction_command_input:
        session_context.set_pending_interaction_clarification(
            question_input=pending_interaction_question_input or None,
            command_input=pending_interaction_command_input or None,
        )
    return session_context


def _build_backend_config(profile: str) -> AnswerBackendConfig:
    if profile == "deterministic":
        return AnswerBackendConfig(backend_kind=AnswerBackendKind.DETERMINISTIC)
    if profile == "llm_missing_key_fallback":
        return AnswerBackendConfig(
            backend_kind=AnswerBackendKind.LLM,
            llm=LlmBackendConfig(
                enabled=True,
                provider=LlmProviderKind.OPENAI_RESPONSES,
                model=_LIVE_SMOKE_DEFAULT_MODEL,
                api_key_env=_EVAL_MISSING_KEY_ENV,
                fallback_enabled=True,
            ),
        )
    if profile == "llm_open_domain_mock":
        return AnswerBackendConfig(
            backend_kind=AnswerBackendKind.LLM,
            llm=LlmBackendConfig(
                enabled=True,
                provider=LlmProviderKind.OPENAI_RESPONSES,
                model=_LIVE_SMOKE_DEFAULT_MODEL,
                fallback_enabled=False,
                open_domain_enabled=True,
            ),
        )
    if profile == "llm_open_domain_missing_key":
        return AnswerBackendConfig(
            backend_kind=AnswerBackendKind.LLM,
            llm=LlmBackendConfig(
                enabled=True,
                provider=LlmProviderKind.OPENAI_RESPONSES,
                model=_LIVE_SMOKE_DEFAULT_MODEL,
                api_key_env=_EVAL_MISSING_KEY_ENV,
                fallback_enabled=False,
                open_domain_enabled=True,
            ),
        )
    if profile == "llm_env":
        env_config = load_answer_backend_config()
        return AnswerBackendConfig(
            backend_kind=AnswerBackendKind.LLM,
            llm=LlmBackendConfig(
                enabled=True,
                provider=env_config.llm.provider,
                model=env_config.llm.model,
                api_key_env=env_config.llm.api_key_env,
                api_base=env_config.llm.api_base,
                fallback_enabled=True,
                open_domain_enabled=env_config.llm.open_domain_enabled,
            ),
        )
    if profile == "llm_env_strict":
        env_config = load_answer_backend_config()
        return AnswerBackendConfig(
            backend_kind=AnswerBackendKind.LLM,
            llm=LlmBackendConfig(
                enabled=True,
                provider=env_config.llm.provider,
                model=env_config.llm.model,
                api_key_env=env_config.llm.api_key_env,
                api_base=env_config.llm.api_base,
                timeout_seconds=env_config.llm.timeout_seconds,
                max_output_tokens=env_config.llm.max_output_tokens,
                reasoning_effort=env_config.llm.reasoning_effort,
                strict_mode=env_config.llm.strict_mode,
                max_retries=env_config.llm.max_retries,
                fallback_enabled=False,
                open_domain_enabled=env_config.llm.open_domain_enabled,
            ),
        )
    raise ValueError(f"Unsupported QA eval backend profile: {profile!r}.")


def _live_smoke_enabled(environ: dict[str, str] | None = None) -> bool:
    env = dict(environ or {})
    return str(env.get(_LIVE_SMOKE_ENABLE_ENV, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _live_smoke_skip_reason(environ: dict[str, str] | None = None) -> str | None:
    env = dict(environ or {})
    if not _live_smoke_enabled(env):
        return f"Set {_LIVE_SMOKE_ENABLE_ENV}=1 to run the live OpenAI Responses smoke test."
    if not str(env.get(_LIVE_SMOKE_API_KEY_ENV, "") or "").strip():
        return f"Set {_LIVE_SMOKE_API_KEY_ENV} before running the live OpenAI Responses smoke test."
    return None


def _live_smoke_config(environ: dict[str, str] | None = None) -> AnswerBackendConfig:
    env = dict(environ or {})
    model = str(env.get(_LIVE_SMOKE_MODEL_ENV, _LIVE_SMOKE_DEFAULT_MODEL) or _LIVE_SMOKE_DEFAULT_MODEL).strip() or _LIVE_SMOKE_DEFAULT_MODEL
    return AnswerBackendConfig(
        backend_kind=AnswerBackendKind.LLM,
        llm=LlmBackendConfig(
            enabled=True,
            provider=LlmProviderKind.OPENAI_RESPONSES,
            model=model,
            api_key_env=_LIVE_SMOKE_API_KEY_ENV,
            fallback_enabled=False,
        ),
    )


def _live_smoke_question(environ: dict[str, str] | None = None) -> str:
    env = dict(environ or {})
    return str(env.get(_LIVE_SMOKE_QUESTION_ENV, _LIVE_SMOKE_DEFAULT_QUESTION) or _LIVE_SMOKE_DEFAULT_QUESTION).strip() or _LIVE_SMOKE_DEFAULT_QUESTION


def _validate_case(case: QaEvalCase) -> None:
    if not case.id.strip():
        raise ValueError("QA eval case id must be non-empty.")
    if case.case_type not in {"interaction", "voice", "live_smoke"}:
        raise ValueError(f"Unsupported QA eval case_type: {case.case_type!r}.")
    if case.backend_profile is not None and case.backend_profile not in _PROFILE_CHOICES:
        raise ValueError(f"Unsupported QA eval backend profile override: {case.backend_profile!r}.")
    if case.profiles and any(profile not in _PROFILE_CHOICES for profile in case.profiles):
        raise ValueError(f"QA eval case {case.id} references unsupported profile scoping.")
    if case.case_type == "interaction" and not str(case.raw_input or "").strip():
        raise ValueError(f"Interaction eval case {case.id} must define raw_input.")
    if case.case_type == "voice" and not str(case.voice_input or "").strip():
        raise ValueError(f"Voice eval case {case.id} must define voice_input.")
    if case.case_type == "live_smoke" and not isinstance(case.env, dict):
        raise ValueError(f"Live smoke eval case {case.id} must define env as an object.")
    if case.expected_sources_count_min is not None and case.expected_sources_count_min < 0:
        raise ValueError(f"QA eval case {case.id} must not use a negative expected_sources_count_min.")
    if case.expected_sources_count_max is not None and case.expected_sources_count_max < 0:
        raise ValueError(f"QA eval case {case.id} must not use a negative expected_sources_count_max.")
    effective_profiles = set(case.profiles or [])
    if case.backend_profile is not None:
        effective_profiles.add(case.backend_profile)
    if "llm_open_domain_mock" in effective_profiles and not isinstance(case.mock_answer_result, dict):
        raise ValueError(f"QA eval case {case.id} must define mock_answer_result for llm_open_domain_mock.")


def _case_applies_to_profile(case: QaEvalCase, default_profile: str) -> bool:
    if not case.profiles:
        return True
    effective_profile = case.backend_profile or default_profile
    return effective_profile in set(case.profiles)


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value or "")).strip()


def _target_type(value: Any) -> TargetType | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return TargetType(text)
    except ValueError:
        return None


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def _percent(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "n/a"
    return f"{(numerator / denominator) * 100:.1f}%"


def summarize_eval_report(report: QaEvalReport) -> QaEvalProfileSummary:
    """Aggregate one eval report into gate-friendly quality metrics."""
    interaction_results = [
        result
        for result in report.results
        if result.case_type == "interaction" and str(result.details.get("profile") or "") == report.default_profile
    ]
    answer_results = [
        result
        for result in interaction_results
        if bool(result.details.get("answer_calls")) and not str(result.details.get("actual_error_code") or "").strip()
    ]
    routing_results = [result for result in interaction_results if "interaction_kind" in result.checks]
    grounding_results = [result for result in interaction_results if "grounding" in result.checks]
    command_results = [result for result in interaction_results if "command_intent" in result.checks]
    unsupported_results = [
        result
        for result in interaction_results
        if str(result.details.get("expected_error_code") or "").strip() == "UNSUPPORTED_QUESTION"
    ]
    source_quality_results = [
        result
        for result in answer_results
        if result.details.get("actual_source_attribution_quality") is not None
    ]
    open_domain_results = [
        result
        for result in interaction_results
        if str(result.details.get("expected_answer_kind") or "").strip() == "open_domain_model"
    ]
    refusal_results = [
        result
        for result in interaction_results
        if str(result.details.get("expected_answer_kind") or "").strip() == "refusal"
    ]
    provenance_results = [result for result in interaction_results if "answer_provenance" in result.checks]
    latency_values = [
        float(result.details.get("latency_ms"))
        for result in interaction_results
        if isinstance(result.details.get("latency_ms"), (int, float))
    ]
    usage_input_values = [_int_or_none(result.details.get("usage_input_tokens")) for result in interaction_results]
    usage_output_values = [_int_or_none(result.details.get("usage_output_tokens")) for result in interaction_results]
    usage_total_values = [_int_or_none(result.details.get("usage_total_tokens")) for result in interaction_results]
    usage_input_values = [value for value in usage_input_values if value is not None]
    usage_output_values = [value for value in usage_output_values if value is not None]
    usage_total_values = [value for value in usage_total_values if value is not None]
    return QaEvalProfileSummary(
        profile=report.default_profile,
        report=report,
        routing_total=len(routing_results),
        routing_passed=sum(1 for result in routing_results if bool(result.checks.get("interaction_kind"))),
        grounding_total=len(grounding_results),
        grounding_passed=sum(1 for result in grounding_results if bool(result.checks.get("grounding"))),
        command_regression_total=len(command_results),
        command_regression_passed=sum(1 for result in command_results if bool(result.checks.get("command_intent"))),
        unsupported_total=len(unsupported_results),
        unsupported_passed=sum(1 for result in unsupported_results if result.passed),
        source_attribution_total=len(source_quality_results),
        source_attribution_passed=sum(
            1 for result in source_quality_results if bool(result.details.get("actual_source_attribution_quality"))
        ),
        open_domain_total=len(open_domain_results),
        open_domain_passed=sum(1 for result in open_domain_results if bool(result.checks.get("answer_kind")) and result.passed),
        refusal_total=len(refusal_results),
        refusal_passed=sum(1 for result in refusal_results if bool(result.checks.get("answer_kind")) and result.passed),
        provenance_total=len(provenance_results),
        provenance_passed=sum(1 for result in provenance_results if bool(result.checks.get("answer_provenance"))),
        answer_total=len(answer_results),
        fallback_total=sum(1 for result in answer_results if bool(result.details.get("fallback_used"))),
        avg_interaction_latency_ms=round(sum(latency_values) / len(latency_values), 3) if latency_values else None,
        usage_sample_count=len(usage_total_values or usage_input_values or usage_output_values),
        usage_input_tokens_total=sum(usage_input_values) if usage_input_values else None,
        usage_output_tokens_total=sum(usage_output_values) if usage_output_values else None,
        usage_total_tokens_total=sum(usage_total_values) if usage_total_values else None,
    )


def compare_eval_profiles(
    cases: list[QaEvalCase],
    *,
    profiles: list[str],
    baseline_profile: str = _DEFAULT_GATE_BASELINE_PROFILE,
    candidate_profile: str | None = None,
) -> QaEvalComparisonReport:
    """Run multiple profiles on one corpus and return the default-decision gate summary."""
    ordered_profiles = list(dict.fromkeys(profile.strip() for profile in profiles if profile.strip()))
    if baseline_profile not in ordered_profiles:
        ordered_profiles.insert(0, baseline_profile)
    if not ordered_profiles:
        ordered_profiles = [baseline_profile]

    profile_reports = [run_eval_cases(cases, default_profile=profile) for profile in ordered_profiles]
    summaries = [summarize_eval_report(report) for report in profile_reports]
    summaries_by_profile = {summary.profile: summary for summary in summaries}
    baseline_summary = summaries_by_profile[baseline_profile]
    resolved_candidate_profile = candidate_profile or _default_candidate_profile(ordered_profiles)
    if resolved_candidate_profile not in summaries_by_profile:
        raise ValueError(f"Candidate profile {resolved_candidate_profile!r} was not included in compare_eval_profiles().")
    candidate_summary = summaries_by_profile[resolved_candidate_profile]

    routing_safety_regressions = _routing_safety_regressions(
        baseline_summary.report,
        candidate_summary.report,
    )
    blockers = _default_switch_blockers(
        baseline_summary=baseline_summary,
        candidate_summary=candidate_summary,
        routing_safety_regressions=routing_safety_regressions,
    )
    default_switch_allowed = not blockers
    return QaEvalComparisonReport(
        baseline_profile=baseline_profile,
        candidate_profile=resolved_candidate_profile,
        summaries=summaries,
        routing_safety_regressions=routing_safety_regressions,
        default_switch_allowed=default_switch_allowed,
        recommended_default_profile=resolved_candidate_profile if default_switch_allowed else baseline_profile,
        thresholds=dict(_DEFAULT_GATE_THRESHOLDS),
        blockers=blockers,
    )


def format_comparison_report(comparison: QaEvalComparisonReport) -> str:
    """Return a compact human-readable product-gate comparison report."""
    lines = [
        "JARVIS QA Profile Comparison",
        f"baseline: {comparison.baseline_profile}",
        f"candidate: {comparison.candidate_profile}",
        f"routing safety regressions: {comparison.routing_safety_regressions}",
        f"default switch allowed: {'yes' if comparison.default_switch_allowed else 'no'}",
        f"recommended default profile: {comparison.recommended_default_profile}",
    ]
    for summary in comparison.summaries:
        unsupported_rate = _percent(summary.unsupported_passed, summary.unsupported_total)
        source_quality_rate = _percent(summary.source_attribution_passed, summary.source_attribution_total)
        open_domain_rate = _percent(summary.open_domain_passed, summary.open_domain_total)
        refusal_rate = _percent(summary.refusal_passed, summary.refusal_total)
        provenance_rate = _percent(summary.provenance_passed, summary.provenance_total)
        fallback_rate = _percent(summary.fallback_total, summary.answer_total)
        lines.extend(
            [
                f"profile: {summary.profile}",
                f"  routing accuracy: {summary.routing_passed}/{summary.routing_total} ({_percent(summary.routing_passed, summary.routing_total)})",
                f"  grounding pass rate: {summary.grounding_passed}/{summary.grounding_total} ({_percent(summary.grounding_passed, summary.grounding_total)})",
                f"  command-regression pass rate: {summary.command_regression_passed}/{summary.command_regression_total} ({_percent(summary.command_regression_passed, summary.command_regression_total)})",
                f"  unsupported honesty: {summary.unsupported_passed}/{summary.unsupported_total} ({unsupported_rate})",
                f"  source attribution quality: {summary.source_attribution_passed}/{summary.source_attribution_total} ({source_quality_rate})",
                f"  open-domain answer pass rate: {summary.open_domain_passed}/{summary.open_domain_total} ({open_domain_rate})",
                f"  refusal pass rate: {summary.refusal_passed}/{summary.refusal_total} ({refusal_rate})",
                f"  provenance correctness: {summary.provenance_passed}/{summary.provenance_total} ({provenance_rate})",
                f"  fallback frequency: {summary.fallback_total}/{summary.answer_total} ({fallback_rate})",
                f"  avg interaction latency ms: {summary.avg_interaction_latency_ms if summary.avg_interaction_latency_ms is not None else 'n/a'}",
                f"  usage samples: {summary.usage_sample_count}",
            ]
        )
    if comparison.blockers:
        lines.append("default-switch blockers:")
        for blocker in comparison.blockers:
            lines.append(f"- {blocker}")
    else:
        lines.append("default-switch blockers: none")
    return "\n".join(lines)


def _routing_safety_regressions(baseline_report: QaEvalReport, candidate_report: QaEvalReport) -> int:
    baseline_by_case = {
        result.case_id: result
        for result in baseline_report.results
        if result.case_type == "interaction"
    }
    regressions = 0
    for result in candidate_report.results:
        if result.case_type != "interaction":
            continue
        baseline_result = baseline_by_case.get(result.case_id)
        if baseline_result is None:
            continue
        baseline_kind = str(baseline_result.details.get("actual_interaction_kind") or "")
        candidate_kind = str(result.details.get("actual_interaction_kind") or "")
        if baseline_kind and candidate_kind and baseline_kind != candidate_kind:
            regressions += 1
    return regressions


def _default_switch_blockers(
    *,
    baseline_summary: QaEvalProfileSummary,
    candidate_summary: QaEvalProfileSummary,
    routing_safety_regressions: int,
) -> list[str]:
    blockers: list[str] = []
    if routing_safety_regressions > int(_DEFAULT_GATE_THRESHOLDS["routing_safety_regressions_max"]):
        blockers.append(f"routing safety regressions > {_DEFAULT_GATE_THRESHOLDS['routing_safety_regressions_max']}")
    if _rate(candidate_summary.command_regression_passed, candidate_summary.command_regression_total) != _DEFAULT_GATE_THRESHOLDS["command_regression_pass_rate_min"]:
        blockers.append("command regression suite is not fully green for candidate profile")
    if _rate(candidate_summary.grounding_passed, candidate_summary.grounding_total) != _DEFAULT_GATE_THRESHOLDS["grounding_pass_rate_min"]:
        blockers.append("grounding pass rate is below threshold")
    if _rate(candidate_summary.unsupported_passed, candidate_summary.unsupported_total) != _DEFAULT_GATE_THRESHOLDS["unsupported_honesty_rate_min"]:
        blockers.append("unsupported-question honesty is below threshold")
    source_quality_rate = _rate(candidate_summary.source_attribution_passed, candidate_summary.source_attribution_total)
    if source_quality_rate is None or source_quality_rate < float(_DEFAULT_GATE_THRESHOLDS["source_attribution_quality_rate_min"]):
        blockers.append("source attribution quality is below threshold")
    open_domain_rate = _rate(candidate_summary.open_domain_passed, candidate_summary.open_domain_total)
    if open_domain_rate is not None and open_domain_rate < float(_DEFAULT_GATE_THRESHOLDS["open_domain_answer_pass_rate_min"]):
        blockers.append("open-domain answer pass rate is below threshold")
    refusal_rate = _rate(candidate_summary.refusal_passed, candidate_summary.refusal_total)
    if refusal_rate is not None and refusal_rate < float(_DEFAULT_GATE_THRESHOLDS["refusal_pass_rate_min"]):
        blockers.append("refusal pass rate is below threshold")
    provenance_rate = _rate(candidate_summary.provenance_passed, candidate_summary.provenance_total)
    if provenance_rate is not None and provenance_rate < float(_DEFAULT_GATE_THRESHOLDS["provenance_pass_rate_min"]):
        blockers.append("provenance correctness is below threshold")
    fallback_frequency = _rate(candidate_summary.fallback_total, candidate_summary.answer_total)
    if fallback_frequency is None or fallback_frequency > float(_DEFAULT_GATE_THRESHOLDS["fallback_frequency_max"]):
        blockers.append("fallback frequency is above threshold")
    if candidate_summary.avg_interaction_latency_ms is None:
        blockers.append("latency was not measured for candidate profile")
    if bool(_DEFAULT_GATE_THRESHOLDS["usage_measurement_required"]) and candidate_summary.usage_sample_count == 0:
        blockers.append("usage/cost proxy is unavailable for candidate profile")
    if _rate(candidate_summary.grounding_passed, candidate_summary.grounding_total) < _rate(
        baseline_summary.grounding_passed,
        baseline_summary.grounding_total,
    ):
        blockers.append("candidate grounding quality regressed versus deterministic baseline")
    return blockers


def _default_candidate_profile(profiles: list[str]) -> str:
    for profile in profiles:
        if profile != _DEFAULT_GATE_BASELINE_PROFILE:
            return profile
    return _DEFAULT_GATE_BASELINE_PROFILE


def _source_attribution_quality(actual_sources: list[Any], actual_source_attributions: list[Any]) -> bool | None:
    sources = [str(source).strip() for source in actual_sources if str(source).strip()]
    if not sources:
        return None
    attributions = list(actual_source_attributions or [])
    if not attributions:
        return False
    source_set = set(sources)
    for attribution in attributions:
        source = str(getattr(attribution, "source", "") or "").strip()
        support = str(getattr(attribution, "support", "") or "").strip()
        if not source or source not in source_set:
            return False
        if not support_is_meaningful(support, source=source):
            return False
    return True


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    return None


def _provider_patch_for_profile(profile: str, case: QaEvalCase):
    if profile == "llm_open_domain_mock":
        return patch.dict(
            "qa.llm_backend._PROVIDERS",
            {LlmProviderKind.OPENAI_RESPONSES: _EvalMockLlmProvider(case)},
            clear=False,
        )
    return nullcontext()


if __name__ == "__main__":
    raise SystemExit(main())
