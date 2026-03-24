"""Topic-aware source selection for grounded question answering."""

from __future__ import annotations

import sys
from pathlib import Path

from qa.source_registry import GroundingSource, get_registered_sources, get_registered_sources_for_paths

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from jarvis_error import ErrorCategory, ErrorCode, JarvisError  # type: ignore  # noqa: E402
from question_request import QuestionRequest, QuestionType  # type: ignore  # noqa: E402


def select_sources(question: QuestionRequest) -> list[GroundingSource]:
    """Return the grounded sources allowed for one question."""
    question_type = getattr(question, "question_type", None)
    lowered = str(getattr(question, "raw_input", "")).lower()
    topic = _question_topic(question, lowered)

    if question_type == QuestionType.ANSWER_FOLLOW_UP:
        sources = get_registered_sources_for_paths(_follow_up_sources(question))
        if not sources:
            follow_up_question_type = _follow_up_question_type(question)
            follow_up_topic = _follow_up_topic(question)
            if follow_up_question_type is not None:
                sources = get_registered_sources(follow_up_question_type, topic=follow_up_topic)
        if not sources:
            raise _source_error(
                question,
                reason="no_recent_answer_sources",
                message="No grounded recent-answer sources are available for that follow-up.",
            )
        return _dedupe_sources(sources)

    if question_type in {QuestionType.DOCS_RULES, QuestionType.REPO_STRUCTURE} and topic:
        sources = get_registered_sources(question_type, topic=topic)
        if not sources:
            raise _source_error(
                question,
                reason="source_not_mapped",
                message=f"No grounded source mapping exists for topic {topic!r}.",
            )
        return _dedupe_sources(sources)

    sources = list(get_registered_sources(question_type, topic="default"))

    if question_type == QuestionType.RUNTIME_STATUS and "folder" in lowered:
        sources.extend(get_registered_sources(question_type, topic="workspace_context"))

    if question_type == QuestionType.RECENT_RUNTIME and any(token in lowered for token in ("folder", "project", "workspace")):
        sources.extend(get_registered_sources(QuestionType.RUNTIME_STATUS, topic="workspace_context"))

    return _dedupe_sources(sources)


def infer_docs_topic(text: str) -> str | None:
    """Infer a supported docs topic from normalized question text."""
    lowered = str(text or "").lower()
    if "clarification" in lowered:
        return "clarification"
    if "confirmation" in lowered:
        return "confirmation"
    if "session context" in lowered:
        return "session_context"
    if "runtime" in lowered or "state" in lowered:
        return "runtime"
    return None


def infer_repo_topic(text: str) -> str | None:
    """Infer a supported repo-structure topic from normalized question text."""
    lowered = str(text or "").lower()
    if "planner" in lowered or "execution plan" in lowered:
        return "planner"
    if "parser" in lowered or "parse command" in lowered:
        return "parser"
    if "validator" in lowered or "validate command" in lowered:
        return "validator"
    if "runtime" in lowered or "state machine" in lowered or "runtime state" in lowered:
        return "runtime"
    if "visibility" in lowered or "ui" in lowered:
        return "visibility"
    if "interaction" in lowered or "route interaction" in lowered:
        return "interaction"
    if "answer engine" in lowered or "qa" in lowered or "question-answer" in lowered:
        return "answer_engine"
    return None


def _question_topic(question: QuestionRequest, lowered: str) -> str | None:
    raw_context_refs = getattr(question, "context_refs", {}) or {}
    if isinstance(raw_context_refs, dict):
        hinted_topic = str(raw_context_refs.get("topic", "") or "").strip()
        if hinted_topic:
            return hinted_topic

    question_type = getattr(question, "question_type", None)
    if question_type == QuestionType.DOCS_RULES:
        return infer_docs_topic(lowered)
    if question_type == QuestionType.REPO_STRUCTURE:
        return infer_repo_topic(lowered)
    return None


def _follow_up_sources(question: QuestionRequest) -> list[str]:
    raw_context_refs = getattr(question, "context_refs", {}) or {}
    if not isinstance(raw_context_refs, dict):
        return []
    raw_sources = raw_context_refs.get("answer_sources")
    if not isinstance(raw_sources, (list, tuple)):
        return []
    return [str(source).strip() for source in raw_sources if str(source).strip()]


def _follow_up_topic(question: QuestionRequest) -> str:
    raw_context_refs = getattr(question, "context_refs", {}) or {}
    if not isinstance(raw_context_refs, dict):
        return "default"
    topic = str(raw_context_refs.get("answer_topic", "") or "").strip()
    if not topic:
        return "default"
    if topic in {member.value for member in QuestionType}:
        return "default"
    return topic


def _follow_up_question_type(question: QuestionRequest) -> QuestionType | None:
    raw_context_refs = getattr(question, "context_refs", {}) or {}
    if not isinstance(raw_context_refs, dict):
        return None

    scope = str(raw_context_refs.get("answer_scope", "") or "").strip()
    if scope == "blocked_state":
        return QuestionType.BLOCKED_STATE
    if scope == "recent_runtime":
        return QuestionType.RECENT_RUNTIME
    if scope == "capabilities":
        return QuestionType.CAPABILITIES
    if scope == "runtime":
        return QuestionType.RUNTIME_STATUS
    if scope == "docs":
        return QuestionType.DOCS_RULES
    if scope == "repo_structure":
        return QuestionType.REPO_STRUCTURE
    if scope == "safety":
        return QuestionType.SAFETY_EXPLANATIONS

    topic = str(raw_context_refs.get("answer_topic", "") or "").strip()
    try:
        return QuestionType(topic)
    except ValueError:
        return None


def _dedupe_sources(sources: list[GroundingSource]) -> list[GroundingSource]:
    ordered_sources = sorted(sources, key=lambda source: (source.priority, source.path))
    deduped: list[GroundingSource] = []
    seen_paths: set[str] = set()
    for source in ordered_sources:
        if source.path in seen_paths:
            continue
        deduped.append(source)
        seen_paths.add(source.path)
    return deduped


def _source_error(question: QuestionRequest, *, reason: str, message: str) -> JarvisError:
    return JarvisError(
        category=ErrorCategory.ANSWER_ERROR,
        code=ErrorCode.SOURCE_NOT_AVAILABLE,
        message=message,
        details={
            "reason": reason,
            "question_type": str(getattr(getattr(question, "question_type", None), "value", getattr(question, "question_type", ""))),
            "raw_input": str(getattr(question, "raw_input", "") or ""),
        },
        blocking=False,
        terminal=True,
    )
