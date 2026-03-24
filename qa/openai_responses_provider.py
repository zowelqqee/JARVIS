"""OpenAI Responses API seam for future model-backed answers."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from qa.grounding_verifier import parse_source_attributions, verify_grounded_answer
from qa.llm_provider import LlmProviderKind
from qa.openai_responses_transport import OpenAIResponsesTransport

if TYPE_CHECKING:
    from context.session_context import SessionContext
    from qa.answer_config import AnswerBackendConfig
    from qa.grounding import GroundingBundle
    from types.question_request import QuestionRequest

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from jarvis_error import ErrorCategory, ErrorCode, JarvisError  # type: ignore  # noqa: E402
from answer_result import AnswerResult  # type: ignore  # noqa: E402

ANSWER_SCHEMA_NAME = "jarvis_grounded_answer"
ANSWER_SCHEMA_VERSION = "qa_answer_v1"


class OpenAIResponsesProvider:
    """Prepare grounded OpenAI Responses API requests without enabling transport in v1."""

    provider_kind = LlmProviderKind.OPENAI_RESPONSES

    def __init__(self, transport: OpenAIResponsesTransport | None = None) -> None:
        self._transport = transport or OpenAIResponsesTransport()

    def answer(
        self,
        question: QuestionRequest,
        *,
        grounding_bundle: GroundingBundle,
        config: AnswerBackendConfig,
        session_context: SessionContext | None = None,
        runtime_snapshot: dict[str, Any] | None = None,
    ) -> AnswerResult:
        request_payload = self.build_request_payload(
            question,
            grounding_bundle=grounding_bundle,
            config=config,
            session_context=session_context,
            runtime_snapshot=runtime_snapshot,
        )
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
                    "request_payload": request_payload,
                },
                blocking=False,
                terminal=True,
            )
        response_payload = self._transport.create_response(
            request_payload,
            api_key=api_key,
            api_base=config.llm.api_base,
        )
        return self._parse_answer_response(response_payload, grounding_bundle=grounding_bundle)

    def build_request_payload(
        self,
        question: QuestionRequest,
        *,
        grounding_bundle: GroundingBundle,
        config: AnswerBackendConfig,
        session_context: SessionContext | None = None,
        runtime_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        question_type = getattr(getattr(question, "question_type", None), "value", None)
        metadata = _metadata(
            jarvis_mode="question",
            question_type=question_type,
            grounding_scope=grounding_bundle.scope,
            source_count=len(grounding_bundle.source_paths),
            provider=self.provider_kind.value,
            answer_schema_version=ANSWER_SCHEMA_VERSION,
        )
        instructions = (
            "You are the JARVIS answer backend. Answer only from the provided local grounding bundle, do not invent sources, "
            "and do not imply that any command was executed. If grounding is insufficient, set grounded to false and explain that in warning. "
            f"Return schema_version exactly {ANSWER_SCHEMA_VERSION}. "
            "Return one source_attributions entry for each source actually used, and keep each support field concise and factual."
        )
        user_text = "\n\n".join(
            section for section in (
                _question_section(question),
                _sources_section(grounding_bundle.source_paths),
                _notes_section(grounding_bundle.source_notes),
                _json_section("Runtime facts", grounding_bundle.runtime_facts),
                _json_section("Session facts", grounding_bundle.session_facts),
            )
            if section
        )
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
        }
        payload["text"] = {
            "format": {
                "type": "json_schema",
                "name": ANSWER_SCHEMA_NAME,
                "schema": _ANSWER_SCHEMA,
                "strict": True,
            }
        }
        return payload

    def _parse_answer_response(self, response_payload: dict[str, Any], *, grounding_bundle: GroundingBundle) -> AnswerResult:
        status = str(response_payload.get("status", "") or "").strip().lower()
        if status in {"failed", "incomplete"}:
            raise JarvisError(
                category=ErrorCategory.ANSWER_ERROR,
                code=ErrorCode.ANSWER_GENERATION_FAILED,
                message=f"OpenAI Responses returned status {status}.",
                details={"status": status, "response": response_payload},
                blocking=False,
                terminal=True,
            )

        output_text = self._extract_output_text(response_payload)
        try:
            structured_output = json.loads(output_text)
        except json.JSONDecodeError as exc:
            raise JarvisError(
                category=ErrorCategory.ANSWER_ERROR,
                code=ErrorCode.ANSWER_GENERATION_FAILED,
                message="OpenAI Responses did not return valid structured answer JSON.",
                details={"output_text": output_text},
                blocking=False,
                terminal=True,
            ) from exc
        if not isinstance(structured_output, dict):
            raise JarvisError(
                category=ErrorCategory.ANSWER_ERROR,
                code=ErrorCode.ANSWER_GENERATION_FAILED,
                message="Structured answer payload is not an object.",
                details={"output_type": type(structured_output).__name__},
                blocking=False,
                terminal=True,
            )

        schema_version = str(structured_output.get("schema_version", "") or "").strip()
        if schema_version != ANSWER_SCHEMA_VERSION:
            raise JarvisError(
                category=ErrorCategory.ANSWER_ERROR,
                code=ErrorCode.ANSWER_GENERATION_FAILED,
                message=f"Structured answer schema_version must be {ANSWER_SCHEMA_VERSION}.",
                details={
                    "schema_version": schema_version or None,
                    "expected_schema_version": ANSWER_SCHEMA_VERSION,
                },
                blocking=False,
                terminal=True,
            )

        answer_text = str(structured_output.get("answer_text", "") or "").strip()
        warning_text = str(structured_output.get("warning", "") or "").strip() or None
        grounded = bool(structured_output.get("grounded", False))
        raw_source_attributions = list(structured_output.get("source_attributions", []) or [])
        source_attributions = parse_source_attributions(raw_source_attributions)
        verified_answer = verify_grounded_answer(
            answer_text=answer_text,
            source_attributions=source_attributions,
            allowed_sources=grounding_bundle.source_paths,
            grounded=grounded,
            warning_text=warning_text,
            details={"structured_output": structured_output},
        )

        return AnswerResult(
            answer_text=verified_answer.answer_text,
            sources=verified_answer.sources,
            source_attributions=verified_answer.source_attributions,
            confidence=0.82,
            warning=verified_answer.warning,
        )

    def _extract_output_text(self, response_payload: dict[str, Any]) -> str:
        direct_output_text = str(response_payload.get("output_text", "") or "").strip()
        if direct_output_text:
            return direct_output_text

        response_output = list(response_payload.get("output", []) or [])
        text_chunks: list[str] = []
        refusal_chunks: list[str] = []
        for item in response_output:
            if not isinstance(item, dict):
                continue
            if str(item.get("type", "")) != "message":
                continue
            if str(item.get("role", "")) != "assistant":
                continue
            for content_item in list(item.get("content", []) or []):
                if not isinstance(content_item, dict):
                    continue
                content_type = str(content_item.get("type", "") or "")
                if content_type == "output_text":
                    text = str(content_item.get("text", "") or "").strip()
                    if text:
                        text_chunks.append(text)
                elif content_type == "refusal":
                    refusal = str(content_item.get("refusal", "") or "").strip()
                    if refusal:
                        refusal_chunks.append(refusal)
        if text_chunks:
            return "\n".join(text_chunks).strip()
        if refusal_chunks:
            raise JarvisError(
                category=ErrorCategory.ANSWER_ERROR,
                code=ErrorCode.ANSWER_GENERATION_FAILED,
                message=f"Model refused structured answer generation: {' '.join(refusal_chunks)}",
                details={"refusal": refusal_chunks},
                blocking=False,
                terminal=True,
            )
        raise JarvisError(
            category=ErrorCategory.ANSWER_ERROR,
            code=ErrorCode.ANSWER_GENERATION_FAILED,
            message="OpenAI Responses did not return assistant output text.",
            details={"response": response_payload},
            blocking=False,
            terminal=True,
        )

_ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "schema_version": {
            "type": "string",
            "enum": [ANSWER_SCHEMA_VERSION],
            "description": "Versioned contract identifier for grounded answer parsing.",
        },
        "answer_text": {
            "type": "string",
            "description": "The grounded answer text for the user.",
        },
        "source_attributions": {
            "type": "array",
            "description": "Exact grounded sources plus the claim support each source backs.",
            "items": {
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                    },
                    "support": {
                        "type": "string",
                    },
                },
                "required": ["source", "support"],
                "additionalProperties": False,
            },
        },
        "warning": {
            "type": "string",
            "description": "Empty string when there is no warning, otherwise a short bounded warning.",
        },
        "grounded": {
            "type": "boolean",
            "description": "True only when the answer is fully supported by the allowed grounding bundle.",
        },
    },
    "required": ["schema_version", "answer_text", "source_attributions", "warning", "grounded"],
    "additionalProperties": False,
}


def _question_section(question: QuestionRequest) -> str:
    question_type = getattr(getattr(question, "question_type", None), "value", "question")
    return f"Question type: {question_type}\nQuestion: {getattr(question, 'raw_input', '')}"


def _sources_section(source_paths: list[str]) -> str:
    if not source_paths:
        return "Allowed local sources: none"
    source_lines = "\n".join(f"- {path}" for path in source_paths)
    return f"Allowed local sources:\n{source_lines}"


def _notes_section(source_notes: list[str]) -> str:
    if not source_notes:
        return ""
    note_lines = "\n".join(f"- {note}" for note in source_notes)
    return f"Grounding rules:\n{note_lines}"


def _json_section(title: str, data: dict[str, Any]) -> str:
    if not data:
        return ""
    return f"{title}:\n{json.dumps(data, sort_keys=True, ensure_ascii=True)}"


def _metadata(**values: object) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for key, value in values.items():
        if value is None:
            continue
        normalized = str(value).strip()
        if normalized:
            metadata[key] = normalized
    return metadata
