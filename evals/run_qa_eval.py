"""Centralized eval runner for QA routing and answer behavior."""

from __future__ import annotations

import argparse
import json
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
from qa.answer_engine import classify_question
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


@dataclass(slots=True)
class QaEvalCase:
    """One eval case loaded from the centralized QA corpus."""

    id: str
    case_type: str
    category: str
    raw_input: str | None = None
    runtime_state: str | None = None
    session_context: dict[str, Any] = field(default_factory=dict)
    backend_profile: str | None = None
    expected_interaction_kind: str | None = None
    expected_question_type: str | None = None
    expected_command_intent: str | None = None
    should_call_runtime: bool | None = None
    should_call_answer_engine: bool | None = None
    expected_sources_count_min: int | None = None
    expected_warning_contains: str | None = None
    expected_error_code: str | None = None
    expected_answer_contains: str | None = None
    expected_clarification_contains: str | None = None
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
        choices=["deterministic", "llm_missing_key_fallback", "llm_env"],
        help="Default answer-backend profile for interaction cases that do not override it.",
    )
    parser.add_argument("--json", action="store_true", help="Print the report as JSON.")
    args = parser.parse_args(argv)

    cases = select_eval_cases(load_qa_eval_cases(args.corpus), args.case_id)
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

    with patch("interaction.interaction_manager.answer_question", side_effect=_spy_answer_question):
        manager = InteractionManager(runtime_manager=runtime_manager, answer_backend_config=config)
        result = manager.handle_input(case.raw_input or "", session_context=session_context)

    actual_interaction_kind = _enum_value(getattr(result, "interaction_mode", ""))
    actual_error_code = _enum_value(getattr(getattr(result, "error", None), "code", ""))
    actual_warning = str(getattr(getattr(result, "answer_result", None), "warning", "") or "").strip()
    actual_answer_text = str(getattr(getattr(result, "answer_result", None), "answer_text", "") or "").strip()
    actual_sources = list(getattr(getattr(result, "answer_result", None), "sources", []) or [])
    actual_clarification = str(getattr(getattr(result, "clarification_request", None), "message", "") or "").strip()

    checks: dict[str, bool] = {}
    details = {
        "profile": profile,
        "actual_interaction_kind": actual_interaction_kind,
        "runtime_calls": len(runtime_manager.handle_calls),
        "answer_calls": len(answer_calls),
        "actual_error_code": actual_error_code or None,
        "actual_warning": actual_warning or None,
        "actual_sources_count": len(actual_sources),
    }

    if case.expected_interaction_kind is not None:
        checks["interaction_kind"] = actual_interaction_kind == case.expected_interaction_kind
    if case.should_call_runtime is not None:
        checks["runtime_called"] = bool(runtime_manager.handle_calls) is case.should_call_runtime
    if case.should_call_answer_engine is not None:
        checks["answer_engine_called"] = bool(answer_calls) is case.should_call_answer_engine
    if case.expected_question_type is not None:
        try:
            actual_question_type = _enum_value(classify_question(case.raw_input or "", session_context=session_context).question_type)
        except Exception:
            actual_question_type = None
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
    if case.expected_sources_count_min is not None:
        checks["grounding"] = getattr(result, "error", None) is None and len(actual_sources) >= case.expected_sources_count_min
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
    actual_normalized = cli._normalize_voice_command(case.voice_input or "")  # noqa: SLF001
    checks = {"normalized_input": actual_normalized == (case.expected_normalized_input or "")}
    return QaEvalCaseResult(
        case_id=case.id,
        case_type=case.case_type,
        category=case.category,
        passed=all(checks.values()),
        checks=checks,
        details={"actual_normalized_input": actual_normalized},
    )


def _run_live_smoke_case(case: QaEvalCase) -> QaEvalCaseResult:
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
        details=details,
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
    if case.case_type == "interaction" and not str(case.raw_input or "").strip():
        raise ValueError(f"Interaction eval case {case.id} must define raw_input.")
    if case.case_type == "voice" and not str(case.voice_input or "").strip():
        raise ValueError(f"Voice eval case {case.id} must define voice_input.")
    if case.case_type == "live_smoke" and not isinstance(case.env, dict):
        raise ValueError(f"Live smoke eval case {case.id} must define env as an object.")


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


if __name__ == "__main__":
    raise SystemExit(main())
