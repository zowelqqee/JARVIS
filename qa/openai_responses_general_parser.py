"""Structured response parser for OpenAI Responses open-domain answers."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from qa.debug_trace import set_debug_payload, update_debug_payload
from qa.general_qa_safety import inspect_general_qa_safety
from qa.grounding_verifier import implies_execution
from qa.llm_response_parser import LlmResponseParser
from qa.openai_responses_general_schema import GENERAL_ANSWER_SCHEMA_VERSION
from qa.openai_responses_shared import extract_response_output, response_debug_details, response_usage_summary

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from answer_result import AnswerKind, AnswerProvenance, AnswerResult  # type: ignore  # noqa: E402
from jarvis_error import ErrorCategory, ErrorCode, JarvisError  # type: ignore  # noqa: E402


class OpenAIResponsesGeneralParser(LlmResponseParser):
    """Parse the OpenAI Responses structured contract for open-domain answers."""

    def parse_response(
        self,
        response_payload: dict[str, Any],
        *,
        question=None,
        grounding_bundle,
        debug_trace: dict[str, Any] | None = None,
    ) -> AnswerResult:
        del grounding_bundle
        status = str(response_payload.get("status", "") or "").strip().lower()
        debug_details = response_debug_details(response_payload)
        set_debug_payload(
            debug_trace,
            "provider_response_parse",
            {
                "provider": debug_details.get("provider", "openai_responses"),
                "status": status or None,
                "request_id": debug_details.get("request_id"),
                "correlation_id": debug_details.get("correlation_id"),
                "retryable": debug_details.get("retryable"),
                **response_usage_summary(response_payload),
                "result": "started",
            },
        )
        if status in {"failed", "incomplete"}:
            update_debug_payload(
                debug_trace,
                "provider_response_parse",
                {
                    "result": "failed",
                    "stage": "status_check",
                    "error_code": ErrorCode.ANSWER_GENERATION_FAILED.value,
                },
            )
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

        output_text, refusal_chunks = extract_response_output(response_payload)
        if not output_text and refusal_chunks:
            refusal_text = " ".join(refusal_chunks).strip()
            update_debug_payload(
                debug_trace,
                "provider_response_parse",
                {
                    "result": "passed",
                    "stage": "refusal_output",
                    "answer_kind": AnswerKind.REFUSAL.value,
                },
            )
            return AnswerResult(
                answer_text=refusal_text or "I can't help with that request.",
                confidence=0.7,
                answer_kind=AnswerKind.REFUSAL,
                provenance=AnswerProvenance.MODEL_KNOWLEDGE,
            )
        if not output_text:
            update_debug_payload(
                debug_trace,
                "provider_response_parse",
                {
                    "result": "failed",
                    "stage": "missing_output",
                    "error_code": ErrorCode.ANSWER_GENERATION_FAILED.value,
                },
            )
            raise JarvisError(
                category=ErrorCategory.ANSWER_ERROR,
                code=ErrorCode.ANSWER_GENERATION_FAILED,
                message="OpenAI Responses did not return assistant output text.",
                details={"status": status or None, **debug_details},
                blocking=False,
                terminal=True,
            )

        update_debug_payload(
            debug_trace,
            "provider_response_parse",
            {
                "output_text_present": True,
            },
        )
        try:
            structured_output = json.loads(output_text)
        except json.JSONDecodeError as exc:
            update_debug_payload(
                debug_trace,
                "provider_response_parse",
                {
                    "result": "failed",
                    "stage": "json_decode",
                    "error_code": ErrorCode.ANSWER_GENERATION_FAILED.value,
                },
            )
            raise JarvisError(
                category=ErrorCategory.ANSWER_ERROR,
                code=ErrorCode.ANSWER_GENERATION_FAILED,
                message="OpenAI Responses did not return valid structured open-domain answer JSON.",
                details={"output_text": output_text, **debug_details},
                blocking=False,
                terminal=True,
            ) from exc
        if not isinstance(structured_output, dict):
            update_debug_payload(
                debug_trace,
                "provider_response_parse",
                {
                    "result": "failed",
                    "stage": "payload_type",
                    "error_code": ErrorCode.ANSWER_GENERATION_FAILED.value,
                },
            )
            raise JarvisError(
                category=ErrorCategory.ANSWER_ERROR,
                code=ErrorCode.ANSWER_GENERATION_FAILED,
                message="Structured open-domain answer payload is not an object.",
                details={"output_type": type(structured_output).__name__, **debug_details},
                blocking=False,
                terminal=True,
            )

        schema_version = str(structured_output.get("schema_version", "") or "").strip()
        update_debug_payload(
            debug_trace,
            "provider_response_parse",
            {
                "schema_version": schema_version or None,
            },
        )
        if schema_version != GENERAL_ANSWER_SCHEMA_VERSION:
            update_debug_payload(
                debug_trace,
                "provider_response_parse",
                {
                    "result": "failed",
                    "stage": "schema_version",
                    "error_code": ErrorCode.ANSWER_GENERATION_FAILED.value,
                },
            )
            raise JarvisError(
                category=ErrorCategory.ANSWER_ERROR,
                code=ErrorCode.ANSWER_GENERATION_FAILED,
                message=f"Structured open-domain answer schema_version must be {GENERAL_ANSWER_SCHEMA_VERSION}.",
                details={
                    "schema_version": schema_version or None,
                    "expected_schema_version": GENERAL_ANSWER_SCHEMA_VERSION,
                    **debug_details,
                },
                blocking=False,
                terminal=True,
            )

        answer_text = str(structured_output.get("answer_text", "") or "").strip()
        if not answer_text:
            update_debug_payload(
                debug_trace,
                "provider_response_parse",
                {
                    "result": "failed",
                    "stage": "missing_answer_text",
                    "error_code": ErrorCode.ANSWER_GENERATION_FAILED.value,
                },
            )
            raise JarvisError(
                category=ErrorCategory.ANSWER_ERROR,
                code=ErrorCode.ANSWER_GENERATION_FAILED,
                message="Structured open-domain answer is missing answer_text.",
                details={"structured_output": structured_output, **debug_details},
                blocking=False,
                terminal=True,
            )
        if implies_execution(answer_text):
            update_debug_payload(
                debug_trace,
                "provider_response_parse",
                {
                    "result": "failed",
                    "stage": "implied_execution",
                    "error_code": ErrorCode.ANSWER_GENERATION_FAILED.value,
                },
            )
            raise JarvisError(
                category=ErrorCategory.ANSWER_ERROR,
                code=ErrorCode.ANSWER_GENERATION_FAILED,
                message="Open-domain answer implied command execution in question mode.",
                details={"answer_text": answer_text, **debug_details},
                blocking=False,
                terminal=True,
            )

        raw_answer_kind = str(structured_output.get("answer_kind", "") or "").strip()
        try:
            answer_kind = AnswerKind(raw_answer_kind)
        except ValueError as exc:
            update_debug_payload(
                debug_trace,
                "provider_response_parse",
                {
                    "result": "failed",
                    "stage": "answer_kind",
                    "error_code": ErrorCode.ANSWER_GENERATION_FAILED.value,
                },
            )
            raise JarvisError(
                category=ErrorCategory.ANSWER_ERROR,
                code=ErrorCode.ANSWER_GENERATION_FAILED,
                message="Structured open-domain answer has invalid answer_kind.",
                details={"answer_kind": raw_answer_kind or None, **debug_details},
                blocking=False,
                terminal=True,
            ) from exc
        if answer_kind == AnswerKind.GROUNDED_LOCAL:
            raise JarvisError(
                category=ErrorCategory.ANSWER_ERROR,
                code=ErrorCode.ANSWER_GENERATION_FAILED,
                message="Structured open-domain answer cannot claim grounded_local answer_kind.",
                details={"answer_kind": raw_answer_kind, **debug_details},
                blocking=False,
                terminal=True,
            )

        warning = str(structured_output.get("warning", "") or "").strip() or None
        policy_warning_hint = inspect_general_qa_safety(getattr(question, "raw_input", "")).warning_hint if question is not None else None
        warning_filled_from_policy = False
        if answer_kind == AnswerKind.OPEN_DOMAIN_MODEL and not warning and policy_warning_hint:
            warning = str(policy_warning_hint).strip() or None
            warning_filled_from_policy = bool(warning)
        update_debug_payload(
            debug_trace,
            "provider_response_parse",
            {
                "result": "passed",
                "stage": "completed",
                "answer_kind": answer_kind.value,
                "parsed_source_count": 0,
                "warning_filled_from_policy": warning_filled_from_policy,
            },
        )
        return AnswerResult(
            answer_text=answer_text,
            confidence=0.72,
            warning=warning,
            answer_kind=answer_kind,
            provenance=AnswerProvenance.MODEL_KNOWLEDGE,
        )
