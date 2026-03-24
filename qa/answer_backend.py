"""Shared answer-backend interfaces for question-answer mode."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from context.session_context import SessionContext
    from qa.answer_config import AnswerBackendConfig
    from qa.grounding import GroundingBundle
    from types.answer_result import AnswerResult
    from types.question_request import QuestionRequest


class AnswerBackendKind(str, Enum):
    """Supported answer backend kinds."""

    DETERMINISTIC = "deterministic"
    LLM = "llm"


class AnswerBackend(Protocol):
    """Protocol implemented by concrete answer-generation backends."""

    backend_kind: AnswerBackendKind

    def answer(
        self,
        question: QuestionRequest,
        *,
        session_context: SessionContext | None = None,
        runtime_snapshot: dict[str, Any] | None = None,
        grounding_bundle: GroundingBundle | None = None,
        config: AnswerBackendConfig | None = None,
    ) -> AnswerResult:
        """Return a grounded answer or raise a structured JarvisError."""
