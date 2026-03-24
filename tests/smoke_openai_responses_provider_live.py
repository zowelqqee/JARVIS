"""Opt-in live smoke test for the OpenAI Responses QA provider."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from typing import Mapping

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from answer_result import AnswerResult
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
_DEFAULT_MODEL = "gpt-5-nano"
_DEFAULT_QUESTION = "What can you do?"


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
    return AnswerBackendConfig(
        backend_kind=AnswerBackendKind.LLM,
        llm=LlmBackendConfig(
            enabled=True,
            provider=LlmProviderKind.OPENAI_RESPONSES,
            model=model,
            api_key_env=_ENV_API_KEY,
            fallback_enabled=False,
        ),
    )


def live_smoke_question(environ: Mapping[str, str] | None = None) -> str:
    """Return the question used for the live smoke test."""
    env = dict(os.environ if environ is None else environ)
    return str(env.get(_ENV_QUESTION, _DEFAULT_QUESTION) or _DEFAULT_QUESTION).strip() or _DEFAULT_QUESTION


def live_smoke_result_issues(result: AnswerResult) -> list[str]:
    """Return contract violations for one live smoke answer result."""
    issues: list[str] = []
    if not str(getattr(result, "answer_text", "") or "").strip():
        issues.append("answer_text must be non-empty")
    if interaction_kind_value(getattr(result, "interaction_mode", "")).strip() != InteractionKind.QUESTION.value:
        issues.append("interaction_mode must stay question")

    sources = [str(source).strip() for source in list(getattr(result, "sources", []) or []) if str(source).strip()]
    if not sources:
        issues.append("sources must be non-empty")

    source_attributions = list(getattr(result, "source_attributions", []) or [])
    if not source_attributions:
        issues.append("source_attributions must be non-empty")
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
        "source_count": source_count,
        "deterministic_fallback": bool(fallback.get("deterministic_fallback")),
        "request_id": provider_parse.get("request_id"),
        "correlation_id": provider_parse.get("correlation_id"),
        "debug_enabled": qa_debug_enabled(),
    }


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
        try:
            result = answer_question(
                live_smoke_question(),
                backend_config=config,
                debug_trace=debug_trace,
            )
        finally:
            diagnostics = live_smoke_diagnostics(
                config=config,
                result=result,
                debug_trace=debug_trace,
            )
            print(f"live smoke provider: {diagnostics['provider']}")
            print(f"live smoke model: {diagnostics['model']}")
            print(f"live smoke source count: {diagnostics['source_count']}")
            print(f"live smoke deterministic fallback: {diagnostics['deterministic_fallback']}")

        self.assertEqual(live_smoke_result_issues(result), [])


if __name__ == "__main__":
    unittest.main()
