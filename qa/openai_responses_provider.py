"""OpenAI Responses API seam for future model-backed answers."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from qa.llm_provider import LlmProviderKind
from qa.openai_responses_general_parser import OpenAIResponsesGeneralParser
from qa.openai_responses_general_prompt import (
    build_general_instructions,
    build_general_request_metadata,
    build_general_user_text,
)
from qa.openai_responses_general_schema import build_general_text_format
from qa.openai_responses_parser import OpenAIResponsesParser
from qa.openai_responses_prompt import build_instructions, build_request_metadata, build_user_text
from qa.openai_responses_schema import ANSWER_SCHEMA_NAME, ANSWER_SCHEMA_VERSION, build_text_format
from qa.openai_responses_transport import OpenAIResponsesTransport

if TYPE_CHECKING:
    from context.session_context import SessionContext
    from qa.answer_config import AnswerBackendConfig
    from qa.grounding import GroundingBundle
    from qa.llm_response_parser import LlmResponseParser
    from types.question_request import QuestionRequest

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from jarvis_error import ErrorCategory, ErrorCode, JarvisError  # type: ignore  # noqa: E402


class OpenAIResponsesProvider:
    """Prepare grounded OpenAI Responses API requests without enabling transport by default."""

    provider_kind = LlmProviderKind.OPENAI_RESPONSES

    def __init__(
        self,
        transport: OpenAIResponsesTransport | None = None,
        parser: LlmResponseParser | None = None,
    ) -> None:
        self._transport = transport or OpenAIResponsesTransport()
        self._parser_override = parser
        self._grounded_parser = OpenAIResponsesParser()
        self._general_parser = OpenAIResponsesGeneralParser()

    def answer(
        self,
        question: QuestionRequest,
        *,
        grounding_bundle: GroundingBundle,
        config: AnswerBackendConfig,
        session_context: SessionContext | None = None,
        runtime_snapshot: dict[str, Any] | None = None,
        debug_trace: dict[str, Any] | None = None,
    ):
        request_payload = self.build_request_payload(
            question,
            grounding_bundle=grounding_bundle,
            config=config,
            session_context=session_context,
            runtime_snapshot=runtime_snapshot,
        )
        request_debug = _safe_request_debug(request_payload)
        api_key_env = str(config.llm.api_key_env).strip() or "OPENAI_API_KEY"
        api_key = str(os.environ.get(api_key_env, "") or "").strip()
        if not api_key:
            raise JarvisError(
                category=ErrorCategory.ANSWER_ERROR,
                code=ErrorCode.MODEL_BACKEND_UNAVAILABLE,
                message=f"OpenAI Responses provider requires {api_key_env} before model-backed answers can be enabled.",
                details={
                    "provider": self.provider_kind.value,
                    "model": config.llm.model,
                    "api_key_env": api_key_env,
                    **request_debug,
                },
                blocking=False,
                terminal=True,
            )

        max_attempts = int(getattr(config.llm, "max_retries", 0) or 0) + 1
        last_error: JarvisError | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                response_payload = self._transport.create_response(
                    request_payload,
                    api_key=api_key,
                    api_base=config.llm.api_base,
                    timeout_seconds=config.llm.timeout_seconds,
                )
                return self._parse_answer_response(
                    response_payload,
                    question=question,
                    grounding_bundle=grounding_bundle,
                    debug_trace=debug_trace,
                )
            except JarvisError as error:
                enriched_error = self._enrich_error(
                    error,
                    request_payload=request_payload,
                    config=config,
                    attempt=attempt,
                    max_attempts=max_attempts,
                )
                if attempt < max_attempts and _is_retryable_error(enriched_error):
                    last_error = enriched_error
                    continue
                raise enriched_error

        if last_error is not None:
            raise last_error
        raise JarvisError(
            category=ErrorCategory.ANSWER_ERROR,
            code=ErrorCode.ANSWER_GENERATION_FAILED,
            message="OpenAI Responses provider exhausted retries without a terminal error.",
            details={
                "provider": self.provider_kind.value,
                "model": config.llm.model,
                **request_debug,
            },
            blocking=False,
            terminal=True,
        )

    def build_request_payload(
        self,
        question: QuestionRequest,
        *,
        grounding_bundle: GroundingBundle,
        config: AnswerBackendConfig,
        session_context: SessionContext | None = None,
        runtime_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if _uses_open_domain_contract(question):
            metadata = build_general_request_metadata(
                question=question,
                grounding_bundle=grounding_bundle,
                provider=self.provider_kind.value,
            )
            instructions = build_general_instructions(config=config)
            user_text = build_general_user_text(question, grounding_bundle=grounding_bundle)
            text_format = build_general_text_format(strict_mode=config.llm.strict_mode)
        else:
            metadata = build_request_metadata(
                question=question,
                grounding_bundle=grounding_bundle,
                provider=self.provider_kind.value,
            )
            instructions = build_instructions(config=config)
            user_text = build_user_text(question, grounding_bundle=grounding_bundle)
            text_format = build_text_format(strict_mode=config.llm.strict_mode)
        payload: dict[str, Any] = {
            "model": config.llm.model,
            "instructions": instructions,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": user_text,
                        }
                    ],
                }
            ],
            "metadata": metadata,
            "max_output_tokens": int(config.llm.max_output_tokens),
            "reasoning": {
                "effort": str(config.llm.reasoning_effort),
            },
        }
        payload["text"] = {
            "format": text_format,
        }
        return payload

    def _parse_answer_response(
        self,
        response_payload: dict[str, Any],
        *,
        question: QuestionRequest | None = None,
        grounding_bundle: GroundingBundle,
        debug_trace: dict[str, Any] | None = None,
    ):
        return self._select_parser(question).parse_response(
            response_payload,
            grounding_bundle=grounding_bundle,
            debug_trace=debug_trace,
        )

    def _select_parser(self, question: QuestionRequest | None) -> LlmResponseParser:
        if self._parser_override is not None:
            return self._parser_override
        if _uses_open_domain_contract(question):
            return self._general_parser
        return self._grounded_parser

    def _enrich_error(
        self,
        error: JarvisError,
        *,
        request_payload: dict[str, Any],
        config: AnswerBackendConfig,
        attempt: int,
        max_attempts: int,
    ) -> JarvisError:
        raw_details = dict(getattr(error, "details", {}) or {})
        request_debug = _safe_request_debug(request_payload)
        if "body" in raw_details and isinstance(raw_details.get("body"), str):
            raw_details["body"] = _truncate(raw_details["body"], limit=500)
        details = {
            **raw_details,
            "provider": self.provider_kind.value,
            "model": config.llm.model,
            "attempt": attempt,
            "max_attempts": max_attempts,
            **request_debug,
        }
        return JarvisError(
            category=error.category,
            code=error.code,
            message=error.message,
            details=details,
            blocking=error.blocking,
            terminal=error.terminal,
        )


def _safe_request_debug(request_payload: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(request_payload.get("metadata", {}) or {})
    text_format = dict((request_payload.get("text") or {}).get("format", {}) or {})
    safe_keys = (
        "correlation_id",
        "question_type",
        "grounding_scope",
        "source_count",
        "answer_mode",
        "policy_tags",
        "policy_response_mode",
        "policy_warning_hint",
        "answer_schema_version",
    )
    return {
        **{key: metadata[key] for key in safe_keys if metadata.get(key) not in (None, "")},
        "strict_mode": bool(text_format.get("strict")),
        "max_output_tokens": int(request_payload.get("max_output_tokens", 0) or 0),
        "reasoning_effort": str(((request_payload.get("reasoning") or {}).get("effort", "")) or "").strip() or None,
    }


def _is_retryable_error(error: JarvisError) -> bool:
    details = dict(getattr(error, "details", {}) or {})
    return bool(details.get("retryable"))


def _truncate(text: str, *, limit: int) -> str:
    compact = str(text or "").strip()
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit]}..."


def _uses_open_domain_contract(question: QuestionRequest | None) -> bool:
    question_type = getattr(getattr(question, "question_type", None), "value", getattr(question, "question_type", None))
    return str(question_type or "").strip() == "open_domain_general"
