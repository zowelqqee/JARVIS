"""Future-facing model backend orchestration for question-answer mode."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from qa.answer_backend import AnswerBackendKind
from qa.answer_config import AnswerBackendConfig
from qa.deterministic_backend import DeterministicAnswerBackend
from qa.grounding import GroundingBundle, build_grounding_bundle
from qa.llm_provider import LlmProvider, LlmProviderKind
from qa.openai_responses_provider import OpenAIResponsesProvider

if TYPE_CHECKING:
    from context.session_context import SessionContext
    from types.answer_result import AnswerResult
    from types.question_request import QuestionRequest

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from jarvis_error import ErrorCategory, ErrorCode, JarvisError  # type: ignore  # noqa: E402


_PROVIDERS: dict[LlmProviderKind, LlmProvider] = {
    LlmProviderKind.OPENAI_RESPONSES: OpenAIResponsesProvider(),
}


class LlmAnswerBackend:
    """Resolve the configured provider and delegate grounded answer requests."""

    backend_kind = AnswerBackendKind.LLM

    def __init__(self) -> None:
        self._fallback_backend = DeterministicAnswerBackend()

    def answer(
        self,
        question: QuestionRequest,
        *,
        session_context: SessionContext | None = None,
        runtime_snapshot: dict[str, object] | None = None,
        grounding_bundle: GroundingBundle | None = None,
        config: AnswerBackendConfig | None = None,
    ) -> AnswerResult:
        resolved_config = config or AnswerBackendConfig(backend_kind=AnswerBackendKind.LLM)
        resolved_grounding = grounding_bundle or build_grounding_bundle(
            question,
            session_context=session_context,
            runtime_snapshot=runtime_snapshot,
        )
        if not resolved_config.llm.enabled:
            error = JarvisError(
                category=ErrorCategory.ANSWER_ERROR,
                code=ErrorCode.MODEL_BACKEND_UNAVAILABLE,
                message="LLM answer backend is disabled by default in v1.",
                details={
                    "backend": self.backend_kind.value,
                    "provider": resolved_config.llm.provider.value,
                    "model": resolved_config.llm.model,
                },
                blocking=False,
                terminal=True,
            )
            return self._handle_provider_failure(
                error,
                question=question,
                session_context=session_context,
                runtime_snapshot=runtime_snapshot,
                grounding_bundle=resolved_grounding,
                config=resolved_config,
            )

        provider = self._resolve_provider(resolved_config.llm.provider)
        try:
            return provider.answer(
                question,
                grounding_bundle=resolved_grounding,
                config=resolved_config,
                session_context=session_context,
                runtime_snapshot=runtime_snapshot,
            )
        except JarvisError as error:
            return self._handle_provider_failure(
                error,
                question=question,
                session_context=session_context,
                runtime_snapshot=runtime_snapshot,
                grounding_bundle=resolved_grounding,
                config=resolved_config,
            )

    def _resolve_provider(self, provider_kind: LlmProviderKind | str) -> LlmProvider:
        kind_value = getattr(provider_kind, "value", provider_kind)
        try:
            kind = LlmProviderKind(kind_value)
        except ValueError as exc:
            raise JarvisError(
                category=ErrorCategory.ANSWER_ERROR,
                code=ErrorCode.MODEL_BACKEND_UNAVAILABLE,
                message=f"Unknown LLM provider: {kind_value!r}.",
                details={"provider": kind_value},
                blocking=False,
                terminal=True,
            ) from exc
        return _PROVIDERS[kind]

    def _handle_provider_failure(
        self,
        error: JarvisError,
        *,
        question: QuestionRequest,
        session_context: SessionContext | None,
        runtime_snapshot: dict[str, object] | None,
        grounding_bundle: GroundingBundle,
        config: AnswerBackendConfig,
    ) -> AnswerResult:
        if not config.llm.fallback_enabled:
            raise error
        fallback_result = self._fallback_backend.answer(
            question,
            session_context=session_context,
            runtime_snapshot=runtime_snapshot,
            grounding_bundle=grounding_bundle,
            config=config,
        )
        warning_parts = [str(fallback_result.warning or "").strip(), self._fallback_warning(error)]
        warning = " ".join(part for part in warning_parts if part).strip() or None
        fallback_result.warning = warning
        return fallback_result

    def _fallback_warning(self, error: JarvisError) -> str:
        code_value = str(getattr(getattr(error, "code", ""), "value", getattr(error, "code", ""))).strip()
        message = str(getattr(error, "message", "")).strip()
        if code_value and message:
            return f"LLM backend fallback: {code_value}: {message}"
        if message:
            return f"LLM backend fallback: {message}"
        if code_value:
            return f"LLM backend fallback: {code_value}"
        return "LLM backend fallback: provider answer was unavailable."
