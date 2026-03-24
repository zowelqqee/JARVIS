"""Structured response parser for OpenAI Responses grounded answers."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from qa.grounding_verifier import parse_source_attributions, verify_grounded_answer
from qa.llm_response_parser import LlmResponseParser
from qa.openai_responses_schema import ANSWER_SCHEMA_VERSION

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from answer_result import AnswerResult  # type: ignore  # noqa: E402
from jarvis_error import ErrorCategory, ErrorCode, JarvisError  # type: ignore  # noqa: E402


class OpenAIResponsesParser(LlmResponseParser):
    """Parse the OpenAI Responses structured answer contract."""

    def parse_response(self, response_payload: dict[str, Any], *, grounding_bundle) -> AnswerResult:
        status = str(response_payload.get("status", "") or "").strip().lower()
        debug_details = _response_debug_details(response_payload)
        if status in {"failed", "incomplete"}:
            raise JarvisError(
                category=ErrorCategory.ANSWER_ERROR,
                code=ErrorCode.ANSWER_GENERATION_FAILED,
                message=f"OpenAI Responses returned status {status}.",
                details={
                    "status": status,
                    "incomplete_details": response_payload.get("incomplete_details"),
                    **debug_details,
                },
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
                details={"output_text": output_text, **debug_details},
                blocking=False,
                terminal=True,
            ) from exc
        if not isinstance(structured_output, dict):
            raise JarvisError(
                category=ErrorCategory.ANSWER_ERROR,
                code=ErrorCode.ANSWER_GENERATION_FAILED,
                message="Structured answer payload is not an object.",
                details={"output_type": type(structured_output).__name__, **debug_details},
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
                    **debug_details,
                },
                blocking=False,
                terminal=True,
            )

        answer_text = str(structured_output.get("answer_text", "") or "").strip()
        warning_text = str(structured_output.get("warning", "") or "").strip() or None
        grounded = bool(structured_output.get("grounded", False))
        raw_source_attributions = list(structured_output.get("source_attributions", []) or [])
        source_attributions = _normalize_source_attributions(
            parse_source_attributions(raw_source_attributions),
            allowed_sources=grounding_bundle.source_paths,
        )
        verified_answer = verify_grounded_answer(
            answer_text=answer_text,
            source_attributions=source_attributions,
            allowed_sources=grounding_bundle.source_paths,
            grounded=grounded,
            warning_text=warning_text,
            details={"structured_output": structured_output, **debug_details},
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
                details={"refusal": refusal_chunks, **_response_debug_details(response_payload)},
                blocking=False,
                terminal=True,
            )
        raise JarvisError(
            category=ErrorCategory.ANSWER_ERROR,
            code=ErrorCode.ANSWER_GENERATION_FAILED,
            message="OpenAI Responses did not return assistant output text.",
            details={"status": str(response_payload.get('status', '') or '').strip() or None, **_response_debug_details(response_payload)},
            blocking=False,
            terminal=True,
        )


def _response_debug_details(response_payload: dict[str, Any]) -> dict[str, Any]:
    raw_debug = response_payload.get("_jarvis_debug")
    if not isinstance(raw_debug, dict):
        return {}
    allowed_keys = ("provider", "request_id", "correlation_id", "status_code", "retryable")
    return {
        key: raw_debug[key]
        for key in allowed_keys
        if raw_debug.get(key) not in (None, "")
    }


def _normalize_source_attributions(source_attributions, *, allowed_sources: list[str]):
    allowed_source_set = {str(source).strip() for source in allowed_sources if str(source).strip()}
    normalized = []
    for attribution in source_attributions:
        source = str(attribution.source or "").strip()
        if source not in allowed_source_set and " | " in source:
            candidate = source.split(" | ", 1)[0].strip()
            if candidate in allowed_source_set:
                attribution.source = candidate
        normalized.append(attribution)
    return normalized
