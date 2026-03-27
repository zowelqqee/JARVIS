"""Answer engine for dual-mode question handling."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from input.adapter import normalize_input
from qa.answer_backend import AnswerBackendKind
from qa.answer_config import AnswerBackendConfig, load_answer_backend_config, open_domain_general_enabled
from qa.debug_trace import set_debug_payload
from qa.deterministic_backend import DeterministicAnswerBackend
from qa.grounding import build_grounding_bundle
from qa.grounding_verifier import ensure_source_attributions
from qa.llm_backend import LlmAnswerBackend
from qa.source_selector import infer_docs_topic, infer_repo_topic

if TYPE_CHECKING:
    from context.session_context import SessionContext
    from types.answer_result import AnswerResult
    from types.question_request import QuestionRequest


_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from jarvis_error import ErrorCategory, ErrorCode, JarvisError  # type: ignore  # noqa: E402
from question_request import QuestionRequest, QuestionType  # type: ignore  # noqa: E402


_BACKENDS = {
    AnswerBackendKind.DETERMINISTIC: DeterministicAnswerBackend(),
    AnswerBackendKind.LLM: LlmAnswerBackend(),
}


def classify_question(
    raw_input: str,
    session_context: SessionContext | None = None,
    backend_config: AnswerBackendConfig | None = None,
    debug_trace: dict[str, Any] | None = None,
) -> QuestionRequest:
    """Classify a normalized question into one supported question family."""
    normalized = normalize_input(raw_input)
    lowered = normalized.lower()
    follow_up_question = _classify_answer_follow_up(normalized, lowered, session_context=session_context, debug_trace=debug_trace)
    if follow_up_question is not None:
        _record_question_classification(follow_up_question, debug_trace=debug_trace)
        return follow_up_question

    if _looks_like_blocked_state_question(lowered):
        question = QuestionRequest(raw_input=normalized, question_type=QuestionType.BLOCKED_STATE, scope="blocked_state", confidence=0.96)
        _record_question_classification(question, debug_trace=debug_trace)
        return question
    if _looks_like_recent_runtime_question(lowered):
        question = QuestionRequest(raw_input=normalized, question_type=QuestionType.RECENT_RUNTIME, scope="recent_runtime", confidence=0.94)
        _record_question_classification(question, debug_trace=debug_trace)
        return question
    if _looks_like_runtime_status_question(lowered):
        question = QuestionRequest(raw_input=normalized, question_type=QuestionType.RUNTIME_STATUS, scope="runtime", confidence=0.94)
        _record_question_classification(question, debug_trace=debug_trace)
        return question
    if _looks_like_capabilities_question(lowered):
        question = QuestionRequest(raw_input=normalized, question_type=QuestionType.CAPABILITIES, scope="capabilities", confidence=0.95)
        _record_question_classification(question, debug_trace=debug_trace)
        return question
    if _looks_like_repo_structure_question(lowered):
        topic = infer_repo_topic(lowered)
        context_refs = {"topic": topic} if topic else {}
        question = QuestionRequest(
            raw_input=normalized,
            question_type=QuestionType.REPO_STRUCTURE,
            scope="repo_structure",
            context_refs=context_refs,
            confidence=0.9,
        )
        _record_question_classification(question, debug_trace=debug_trace)
        return question
    if _looks_like_safety_question(lowered):
        question = QuestionRequest(raw_input=normalized, question_type=QuestionType.SAFETY_EXPLANATIONS, scope="safety", confidence=0.9)
        _record_question_classification(question, debug_trace=debug_trace)
        return question
    if _looks_like_docs_rules_question(lowered):
        topic = infer_docs_topic(lowered)
        context_refs = {"topic": topic} if topic else {}
        question = QuestionRequest(
            raw_input=normalized,
            question_type=QuestionType.DOCS_RULES,
            scope="docs",
            context_refs=context_refs,
            confidence=0.88,
        )
        _record_question_classification(question, debug_trace=debug_trace)
        return question

    if open_domain_general_enabled(backend_config):
        question = QuestionRequest(
            raw_input=normalized,
            question_type=QuestionType.OPEN_DOMAIN_GENERAL,
            scope="open_domain",
            confidence=0.7,
            requires_grounding=False,
        )
        _record_question_classification(question, debug_trace=debug_trace)
        return question

    set_debug_payload(
        debug_trace,
        "question_classification",
        {
            "result": "failed",
            "error_code": ErrorCode.UNSUPPORTED_QUESTION.value,
        },
    )
    raise JarvisError(
        category=ErrorCategory.ANSWER_ERROR,
        code=ErrorCode.UNSUPPORTED_QUESTION,
        message="Question is outside the supported v1 grounded QA scope.",
        details={"raw_input": normalized},
        blocking=False,
        terminal=True,
    )


def answer_question(
    raw_input: str,
    session_context: SessionContext | None = None,
    runtime_snapshot: dict[str, Any] | None = None,
    backend_kind: AnswerBackendKind | str | None = None,
    backend_config: AnswerBackendConfig | None = None,
    debug_trace: dict[str, Any] | None = None,
) -> AnswerResult:
    """Route one question through the configured answer backend."""
    resolved_config = _resolve_answer_backend_config(backend_kind=backend_kind, backend_config=backend_config)
    question = classify_question(
        raw_input,
        session_context=session_context,
        backend_config=resolved_config,
        debug_trace=debug_trace,
    )
    grounding_bundle = build_grounding_bundle(
        question,
        session_context=session_context,
        runtime_snapshot=runtime_snapshot,
        debug_trace=debug_trace,
    )
    backend = _resolve_backend(_backend_kind_for_question(question, resolved_config))
    answer_result = backend.answer(
        question,
        session_context=session_context,
        runtime_snapshot=runtime_snapshot,
        grounding_bundle=grounding_bundle,
        config=resolved_config,
        debug_trace=debug_trace,
    )
    return ensure_source_attributions(answer_result)


def _resolve_backend(backend_kind: AnswerBackendKind | str) -> object:
    kind_value = getattr(backend_kind, "value", backend_kind)
    try:
        kind = AnswerBackendKind(kind_value)
    except ValueError as exc:
        raise JarvisError(
            category=ErrorCategory.ANSWER_ERROR,
            code=ErrorCode.MODEL_BACKEND_UNAVAILABLE,
            message=f"Unknown answer backend: {kind_value!r}.",
            details={"backend": kind_value},
            blocking=False,
            terminal=True,
        ) from exc
    return _BACKENDS[kind]


def _resolve_answer_backend_config(
    *,
    backend_kind: AnswerBackendKind | str | None,
    backend_config: AnswerBackendConfig | None,
) -> AnswerBackendConfig:
    resolved_config = backend_config or load_answer_backend_config()
    return resolved_config.with_backend_kind(backend_kind)


def _backend_kind_for_question(question: QuestionRequest, config: AnswerBackendConfig) -> AnswerBackendKind | str:
    configured_backend = getattr(getattr(config, "backend_kind", None), "value", getattr(config, "backend_kind", None))
    if str(configured_backend or "").strip() == AnswerBackendKind.LLM.value:
        return config.backend_kind
    if getattr(question, "question_type", None) == QuestionType.OPEN_DOMAIN_GENERAL and open_domain_general_enabled(config):
        return AnswerBackendKind.LLM
    return config.backend_kind


def _looks_like_runtime_status_question(text: str) -> bool:
    phrases = (
        "what are you doing",
        "current state",
        "current step",
        "what folder are you using",
    )
    return any(phrase in text for phrase in phrases)


def _looks_like_blocked_state_question(text: str) -> bool:
    phrases = (
        "what are you waiting",
        "what are you waiting for",
        "why are you waiting",
        "why are you blocked",
        "why did you stop",
        "what do you need from me",
        "what exactly do you need me to confirm",
        "what do you need me to confirm",
        "что ты ждешь",
        "что тебе нужно",
        "что тебе нужно от меня",
        "что именно тебе нужно подтвердить",
        "что тебе нужно подтвердить",
    )
    return any(phrase in text for phrase in phrases)


def _looks_like_recent_runtime_question(text: str) -> bool:
    phrases = (
        "what did you just do",
        "what did you do last",
        "what command did you run last",
        "what was the last command",
        "which target were you working with",
        "what target were you working with",
        "what app did you open last",
        "what file did you just open",
        "which file did you just open",
        "what was the last target",
        "what app was last",
        "what file was last",
    )
    return any(phrase in text for phrase in phrases)


def _looks_like_capabilities_question(text: str) -> bool:
    phrases = (
        "what can you do",
        "which commands do you support",
        "what do you support",
        "supported commands",
        "capabilities",
        "что ты умеешь",
        "какие команды ты поддерживаешь",
        "что ты поддерживаешь",
    )
    return any(phrase in text for phrase in phrases)


def _looks_like_repo_structure_question(text: str) -> bool:
    phrases = (
        "where is",
        "where does",
        "which file",
        "which module",
        "where does runtime state live",
        "where is the parser",
        "where is the planner",
    )
    return any(phrase in text for phrase in phrases)


def _looks_like_safety_question(text: str) -> bool:
    phrases = (
        "why do you need confirmation",
        "why didn't you execute",
        "why do you need approval",
        "why won't you execute",
        "почему тебе нужно подтверждение",
        "почему ты не выполнил команду",
    )
    return any(phrase in text for phrase in phrases)


def _looks_like_docs_rules_question(text: str) -> bool:
    phrases = (
        "how does clarification",
        "how does confirmation",
        "what is session context",
        "how does runtime flow",
        "how do you route",
        "how does question-answer mode",
        "how does runtime work",
        "what is clarification",
        "what is confirmation",
        "как работает уточнение",
        "как работает подтверждение",
        "что такое session context",
        "как работает runtime",
    )
    return any(phrase in text for phrase in phrases)


def _classify_answer_follow_up(
    normalized: str,
    lowered: str,
    *,
    session_context: SessionContext | None,
    debug_trace: dict[str, Any] | None,
) -> QuestionRequest | None:
    follow_up_kind = _follow_up_kind(lowered)
    if follow_up_kind is None:
        return None

    recent_answer_context = session_context.get_recent_answer_context() if session_context is not None else None
    if recent_answer_context is None:
        set_debug_payload(
            debug_trace,
            "question_classification",
            {
                "result": "failed",
                "error_code": ErrorCode.INSUFFICIENT_CONTEXT.value,
                "reason": "no_recent_answer",
                "follow_up_kind": follow_up_kind,
            },
        )
        raise JarvisError(
            category=ErrorCategory.ANSWER_ERROR,
            code=ErrorCode.INSUFFICIENT_CONTEXT,
            message="No recent answer context is available for that follow-up.",
            details={"reason": "no_recent_answer", "raw_input": normalized},
            blocking=False,
            terminal=True,
        )

    answer_topic = str(recent_answer_context.get("topic", "") or "").strip() or None
    answer_scope = str(recent_answer_context.get("scope", "") or "").strip() or None
    answer_sources = [
        str(source).strip()
        for source in list(recent_answer_context.get("sources", []) or [])
        if str(source).strip()
    ]
    context_refs: dict[str, Any] = {
        "follow_up_kind": follow_up_kind,
        "answer_topic": answer_topic,
        "answer_scope": answer_scope,
        "answer_sources": answer_sources,
    }
    return QuestionRequest(
        raw_input=normalized,
        question_type=QuestionType.ANSWER_FOLLOW_UP,
        scope=answer_scope or "answer_follow_up",
        context_refs=context_refs,
        confidence=0.9,
    )


def _follow_up_kind(text: str) -> str | None:
    normalized = str(text or "").strip().lower().rstrip("?.! ")
    if normalized in {
        "explain more",
        "explain that more",
        "explain it more",
        "go deeper",
        "more detail",
        "more details",
        "elaborate",
    }:
        return "explain_more"
    if normalized in {
        "which source",
        "which sources",
        "what source",
        "what sources",
    }:
        return "which_source"
    if normalized in {
        "where is that written",
        "where is it written",
        "where is that documented",
        "where is it documented",
    }:
        return "where_written"
    if normalized in {
        "why",
        "why is that",
        "why so",
        "why does that apply",
    }:
        return "why"
    return None


def _record_question_classification(question: QuestionRequest, *, debug_trace: dict[str, Any] | None) -> None:
    context_refs = getattr(question, "context_refs", {}) or {}
    context_ref_keys = sorted(str(key) for key in context_refs.keys()) if isinstance(context_refs, dict) else []
    payload = {
        "result": "passed",
        "question_type": getattr(getattr(question, "question_type", None), "value", getattr(question, "question_type", None)),
        "scope": getattr(question, "scope", None),
        "confidence": round(float(getattr(question, "confidence", 0.0) or 0.0), 3),
        "requires_grounding": bool(getattr(question, "requires_grounding", False)),
        "context_ref_keys": context_ref_keys,
    }
    if isinstance(context_refs, dict):
        payload["topic"] = str(context_refs.get("topic", "") or context_refs.get("answer_topic", "") or "").strip() or None
        payload["follow_up_kind"] = str(context_refs.get("follow_up_kind", "") or "").strip() or None
    set_debug_payload(debug_trace, "question_classification", payload)
