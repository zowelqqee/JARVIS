"""Answer engine for dual-mode question handling."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from input.adapter import normalize_input
from qa.answer_backend import AnswerBackendKind
from qa.deterministic_backend import DeterministicAnswerBackend
from qa.llm_backend import LlmAnswerBackend

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


def classify_question(raw_input: str) -> QuestionRequest:
    """Classify a normalized question into one supported question family."""
    normalized = normalize_input(raw_input)
    lowered = normalized.lower()

    if _looks_like_runtime_status_question(lowered):
        return QuestionRequest(raw_input=normalized, question_type=QuestionType.RUNTIME_STATUS, scope="runtime", confidence=0.94)
    if _looks_like_capabilities_question(lowered):
        return QuestionRequest(raw_input=normalized, question_type=QuestionType.CAPABILITIES, scope="capabilities", confidence=0.95)
    if _looks_like_repo_structure_question(lowered):
        return QuestionRequest(raw_input=normalized, question_type=QuestionType.REPO_STRUCTURE, scope="repo_structure", confidence=0.9)
    if _looks_like_safety_question(lowered):
        return QuestionRequest(raw_input=normalized, question_type=QuestionType.SAFETY_EXPLANATIONS, scope="safety", confidence=0.9)
    if _looks_like_docs_rules_question(lowered):
        return QuestionRequest(raw_input=normalized, question_type=QuestionType.DOCS_RULES, scope="docs", confidence=0.88)

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
    backend_kind: AnswerBackendKind | str = AnswerBackendKind.DETERMINISTIC,
) -> AnswerResult:
    """Route one question through the configured answer backend."""
    question = classify_question(raw_input)
    backend = _resolve_backend(backend_kind)
    return backend.answer(question, session_context=session_context, runtime_snapshot=runtime_snapshot)


def _resolve_backend(backend_kind: AnswerBackendKind | str) -> Any:
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


def _looks_like_runtime_status_question(text: str) -> bool:
    phrases = (
        "what are you doing",
        "what are you waiting",
        "why are you waiting",
        "why are you blocked",
        "current state",
        "current step",
        "what folder are you using",
        "which file did you just open",
    )
    return any(phrase in text for phrase in phrases)


def _looks_like_capabilities_question(text: str) -> bool:
    phrases = (
        "what can you do",
        "which commands do you support",
        "what do you support",
        "supported commands",
        "capabilities",
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
        "why did you stop",
        "why do you need approval",
        "why won't you execute",
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
    )
    if any(phrase in text for phrase in phrases):
        return True
    return text.endswith("?") and text.startswith(("what ", "how ", "why ", "which ", "where ", "when ", "who ", "explain "))
