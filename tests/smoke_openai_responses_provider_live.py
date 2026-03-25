"""Opt-in live smoke test for the OpenAI Responses QA provider."""

from __future__ import annotations

import json
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from answer_result import AnswerKind, AnswerResult, answer_kind_value, answer_provenance_value
from interaction_kind import InteractionKind, interaction_kind_value
from qa.debug_trace import qa_debug_enabled
from qa.grounding_verifier import support_is_meaningful
from qa.answer_backend import AnswerBackendKind
from qa.answer_config import AnswerBackendConfig, LlmBackendConfig
from qa.answer_engine import answer_question
from qa.llm_provider import LlmProviderKind

_ENV_ENABLE = "JARVIS_QA_OPENAI_LIVE_SMOKE"
_ENV_API_KEY = "OPENAI_API_KEY"
_ENV_MODEL = "JARVIS_QA_OPENAI_LIVE_MODEL"
_ENV_QUESTION = "JARVIS_QA_OPENAI_LIVE_QUESTION"
_ENV_OPEN_DOMAIN = "JARVIS_QA_OPENAI_LIVE_OPEN_DOMAIN_ENABLED"
_ENV_FALLBACK = "JARVIS_QA_OPENAI_LIVE_FALLBACK_ENABLED"
_ENV_STRICT_MODE = "JARVIS_QA_OPENAI_LIVE_STRICT_MODE"
_ENV_ARTIFACT = "JARVIS_QA_OPENAI_LIVE_ARTIFACT"
_DEFAULT_MODEL = "gpt-5-nano"
_DEFAULT_QUESTION = "What can you do?"
_DEFAULT_ARTIFACT = Path(__file__).resolve().parents[1] / "tmp" / "qa" / "openai_live_smoke.json"


def live_smoke_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Return whether the live smoke was explicitly enabled."""
    env = dict(os.environ if environ is None else environ)
    return str(env.get(_ENV_ENABLE, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def live_smoke_skip_reason(environ: Mapping[str, str] | None = None) -> str | None:
    """Return the skip reason when live smoke should not run."""
    env = dict(os.environ if environ is None else environ)
    if not live_smoke_enabled(env):
        return f"Set {_ENV_ENABLE}=1 to run the live OpenAI Responses smoke test."
    if not str(env.get(_ENV_API_KEY, "") or "").strip():
        return f"Set {_ENV_API_KEY} before running the live OpenAI Responses smoke test."
    return None


def live_smoke_config(environ: Mapping[str, str] | None = None) -> AnswerBackendConfig:
    """Build the strict no-fallback config used by the live smoke test."""
    env = dict(os.environ if environ is None else environ)
    model = str(env.get(_ENV_MODEL, _DEFAULT_MODEL) or _DEFAULT_MODEL).strip() or _DEFAULT_MODEL
    open_domain_enabled = str(env.get(_ENV_OPEN_DOMAIN, "") or "").strip().lower() in {"1", "true", "yes", "on"}
    fallback_enabled = str(env.get(_ENV_FALLBACK, "") or "").strip().lower() in {"1", "true", "yes", "on"}
    strict_mode = str(env.get(_ENV_STRICT_MODE, "1") or "1").strip().lower() in {"1", "true", "yes", "on"}
    return AnswerBackendConfig(
        backend_kind=AnswerBackendKind.LLM,
        llm=LlmBackendConfig(
            enabled=True,
            provider=LlmProviderKind.OPENAI_RESPONSES,
            model=model,
            api_key_env=_ENV_API_KEY,
            strict_mode=strict_mode,
            fallback_enabled=fallback_enabled,
            open_domain_enabled=open_domain_enabled,
        ),
    )


def live_smoke_question(environ: Mapping[str, str] | None = None) -> str:
    """Return the question used for the live smoke test."""
    env = dict(os.environ if environ is None else environ)
    return str(env.get(_ENV_QUESTION, _DEFAULT_QUESTION) or _DEFAULT_QUESTION).strip() or _DEFAULT_QUESTION


def live_smoke_artifact_path(environ: Mapping[str, str] | None = None) -> Path:
    """Return the JSON artifact path used by the live smoke script."""
    env = dict(os.environ if environ is None else environ)
    configured = str(env.get(_ENV_ARTIFACT, "") or "").strip()
    return Path(configured) if configured else _DEFAULT_ARTIFACT


def live_smoke_result_issues(result: AnswerResult) -> list[str]:
    """Return contract violations for one live smoke answer result."""
    issues: list[str] = []
    if not str(getattr(result, "answer_text", "") or "").strip():
        issues.append("answer_text must be non-empty")
    if interaction_kind_value(getattr(result, "interaction_mode", "")).strip() != InteractionKind.QUESTION.value:
        issues.append("interaction_mode must stay question")

    answer_kind = answer_kind_value(getattr(result, "answer_kind", AnswerKind.GROUNDED_LOCAL)) or AnswerKind.GROUNDED_LOCAL.value
    answer_provenance = answer_provenance_value(getattr(result, "provenance", None))
    sources = [str(source).strip() for source in list(getattr(result, "sources", []) or []) if str(source).strip()]
    source_attributions = list(getattr(result, "source_attributions", []) or [])

    if answer_kind == AnswerKind.GROUNDED_LOCAL.value:
        if not sources:
            issues.append("grounded live smoke answers must keep non-empty sources")
        if not source_attributions:
            issues.append("grounded live smoke answers must keep non-empty source_attributions")
        for attribution in source_attributions:
            source = str(getattr(attribution, "source", "") or "").strip()
            support = str(getattr(attribution, "support", "") or "").strip()
            if not source or not support:
                issues.append("each source_attribution must include source and support")
                continue
            if source not in sources:
                issues.append("each source_attribution source must be present in sources")
            if not support_is_meaningful(support, source=source):
                issues.append("each source_attribution support must be specific and claim-bearing")
    else:
        if answer_provenance != "model_knowledge":
            issues.append("open-domain live smoke answers must declare model_knowledge provenance")
        if sources:
            issues.append("open-domain live smoke answers must not claim local sources")
        if source_attributions:
            issues.append("open-domain live smoke answers must not claim source_attributions")

    warning = str(getattr(result, "warning", "") or "").strip()
    if "LLM backend fallback" in warning:
        issues.append("live smoke must not pass through deterministic fallback")
    return issues


def live_smoke_diagnostics(
    *,
    config: AnswerBackendConfig,
    result: AnswerResult | None,
    debug_trace: dict[str, object] | None = None,
) -> dict[str, object]:
    """Return safe live-smoke diagnostics for operator output."""
    source_selection = dict((debug_trace or {}).get("source_selection", {}) or {})
    fallback = dict((debug_trace or {}).get("fallback", {}) or {})
    provider_parse = dict((debug_trace or {}).get("provider_response_parse", {}) or {})
    source_count = len(list(getattr(result, "sources", []) or []))
    if source_count == 0:
        source_count = int(source_selection.get("source_count", 0) or 0)
    return {
        "model": config.llm.model,
        "provider": getattr(config.llm.provider, "value", config.llm.provider),
        "strict_mode": bool(config.llm.strict_mode),
        "fallback_enabled": bool(config.llm.fallback_enabled),
        "open_domain_enabled": bool(config.llm.open_domain_enabled),
        "answer_kind": answer_kind_value(getattr(result, "answer_kind", None)) if result is not None else None,
        "provenance": answer_provenance_value(getattr(result, "provenance", None)) if result is not None else None,
        "warning": str(getattr(result, "warning", "") or "").strip() or None if result is not None else None,
        "source_count": source_count,
        "deterministic_fallback": bool(fallback.get("deterministic_fallback")),
        "request_id": provider_parse.get("request_id"),
        "correlation_id": provider_parse.get("correlation_id"),
        "debug_enabled": qa_debug_enabled(),
    }


def live_smoke_artifact_payload(
    *,
    config: AnswerBackendConfig,
    question: str,
    result: AnswerResult | None,
    debug_trace: dict[str, object] | None = None,
    issues: list[str] | None = None,
    error: str | None = None,
) -> dict[str, object]:
    """Build the machine-readable artifact used by rollout gating."""
    diagnostics = live_smoke_diagnostics(
        config=config,
        result=result,
        debug_trace=debug_trace,
    )
    issue_list = [str(issue).strip() for issue in list(issues or []) if str(issue).strip()]
    success = not issue_list and not str(error or "").strip()
    answer_kind = str(diagnostics.get("answer_kind") or "").strip()
    open_domain_verified = bool(diagnostics.get("open_domain_enabled")) and answer_kind in {
        AnswerKind.OPEN_DOMAIN_MODEL.value,
        AnswerKind.REFUSAL.value,
    }
    return {
        "schema_version": 1,
        "runner": "tests.smoke_openai_responses_provider_live",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "question": question,
        "success": success,
        "issues": issue_list,
        "error": str(error or "").strip() or None,
        "open_domain_verified": bool(open_domain_verified and success),
        "diagnostics": diagnostics,
    }


def write_live_smoke_artifact(path: Path, payload: Mapping[str, object]) -> None:
    """Persist one live-smoke artifact for the rollout gate."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")


class OpenAIResponsesLiveSmokeTests(unittest.TestCase):
    """Manual live smoke for the real OpenAI Responses question-answer path."""

    def setUp(self) -> None:
        reason = live_smoke_skip_reason()
        if reason is not None:
            self.skipTest(reason)

    def test_live_grounded_capability_answer(self) -> None:
        config = live_smoke_config()
        debug_trace: dict[str, object] = {}
        result: AnswerResult | None = None
        issues: list[str] = []
        failure_message: str | None = None
        question = live_smoke_question()
        try:
            result = answer_question(
                question,
                backend_config=config,
                debug_trace=debug_trace,
            )
            issues = live_smoke_result_issues(result)
        except Exception as exc:
            failure_message = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            diagnostics = live_smoke_diagnostics(
                config=config,
                result=result,
                debug_trace=debug_trace,
            )
            artifact_payload = live_smoke_artifact_payload(
                config=config,
                question=question,
                result=result,
                debug_trace=debug_trace,
                issues=issues,
                error=failure_message,
            )
            write_live_smoke_artifact(live_smoke_artifact_path(), artifact_payload)
            print(f"live smoke provider: {diagnostics['provider']}")
            print(f"live smoke model: {diagnostics['model']}")
            print(f"live smoke strict mode: {diagnostics['strict_mode']}")
            print(f"live smoke fallback enabled: {diagnostics['fallback_enabled']}")
            print(f"live smoke open-domain enabled: {diagnostics['open_domain_enabled']}")
            print(f"live smoke answer kind: {diagnostics['answer_kind']}")
            print(f"live smoke provenance: {diagnostics['provenance']}")
            print(f"live smoke source count: {diagnostics['source_count']}")
            print(f"live smoke deterministic fallback: {diagnostics['deterministic_fallback']}")
            print(f"live smoke artifact: {live_smoke_artifact_path()}")

        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
