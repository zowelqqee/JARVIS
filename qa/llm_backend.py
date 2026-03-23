"""Future-facing LLM backend placeholder for question-answer mode."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from qa.answer_backend import AnswerBackendKind

if TYPE_CHECKING:
    from context.session_context import SessionContext
    from types.answer_result import AnswerResult
    from types.question_request import QuestionRequest


_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from jarvis_error import ErrorCategory, ErrorCode, JarvisError  # type: ignore  # noqa: E402


class LlmAnswerBackend:
    """Reserved backend seam for future model-backed answers."""

    backend_kind = AnswerBackendKind.LLM

    def answer(
        self,
        question: QuestionRequest,
        *,
        session_context: SessionContext | None = None,
        runtime_snapshot: dict[str, Any] | None = None,
    ) -> AnswerResult:
        raise JarvisError(
            category=ErrorCategory.ANSWER_ERROR,
            code=ErrorCode.MODEL_BACKEND_UNAVAILABLE,
            message="LLM answer backend is not enabled in v1.",
            details={"backend": self.backend_kind.value, "question_type": getattr(getattr(question, "question_type", None), "value", None)},
            blocking=False,
            terminal=True,
        )
