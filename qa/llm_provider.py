"""Provider interfaces for future model-backed answers."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from context.session_context import SessionContext
    from qa.answer_config import AnswerBackendConfig
    from qa.grounding import GroundingBundle
    from types.answer_result import AnswerResult
    from types.question_request import QuestionRequest


class LlmProviderKind(str, Enum):
    """Supported LLM provider backends behind the QA seam."""

    OPENAI_RESPONSES = "openai_responses"


class LlmProvider(Protocol):
    """Protocol implemented by concrete model providers."""

    provider_kind: LlmProviderKind

    def answer(
        self,
        question: QuestionRequest,
        *,
        grounding_bundle: GroundingBundle,
        config: AnswerBackendConfig,
        session_context: SessionContext | None = None,
        runtime_snapshot: dict[str, Any] | None = None,
    ) -> AnswerResult:
        """Return an answer or raise a structured JarvisError."""

    def build_request_payload(
        self,
        question: QuestionRequest,
        *,
        grounding_bundle: GroundingBundle,
        config: AnswerBackendConfig,
        session_context: SessionContext | None = None,
        runtime_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build a provider-specific request payload for inspection or transport."""
