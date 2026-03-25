"""Prompt and request-content builders for OpenAI Responses open-domain answers."""

from __future__ import annotations

import json
import uuid
from typing import Any

from qa.openai_responses_general_schema import GENERAL_ANSWER_SCHEMA_VERSION

if False:  # pragma: no cover
    from qa.answer_config import AnswerBackendConfig
    from qa.grounding import GroundingBundle
    from types.question_request import QuestionRequest


def build_general_request_metadata(
    *,
    question: QuestionRequest,
    grounding_bundle: GroundingBundle,
    provider: str,
) -> dict[str, str]:
    """Build stable string-only metadata for one open-domain provider request."""
    question_type = getattr(getattr(question, "question_type", None), "value", None)
    return _metadata(
        jarvis_mode="question",
        answer_mode="open_domain",
        question_type=question_type,
        grounding_scope=grounding_bundle.scope,
        source_count=len(grounding_bundle.source_paths),
        provider=provider,
        answer_schema_version=GENERAL_ANSWER_SCHEMA_VERSION,
        correlation_id=str(uuid.uuid4()),
    )


def build_general_instructions(*, config: AnswerBackendConfig) -> str:
    """Build the provider instruction block for open-domain read-only answers."""
    strict_text = "strictly follow the JSON schema" if config.llm.strict_mode else "follow the JSON schema"
    return (
        "You are the JARVIS open-domain question backend. Answer the user directly in read-only mode. "
        "Do not claim that you executed commands, clicked UI, opened apps, or changed runtime state. "
        "Do not pretend to quote local docs or local sources because this answer mode is model knowledge, not local grounding. "
        "If the question depends on current or changing real-world facts, add a short warning that the answer may be out of date. "
        "If the request is unsafe or disallowed, return answer_kind refusal with a short refusal answer_text. "
        f"Return schema_version exactly {GENERAL_ANSWER_SCHEMA_VERSION}. "
        "Keep answer_text concise and under 120 words, and keep warning empty unless it is needed. "
        f"{strict_text}."
    )


def build_general_user_text(question: QuestionRequest, *, grounding_bundle: GroundingBundle) -> str:
    """Build the user-visible prompt content for one open-domain provider request."""
    return "\n\n".join(
        section
        for section in (
            _question_section(question),
            "Local grounded sources: none for this answer mode. Do not invent citations.",
            _json_section("Runtime facts", grounding_bundle.runtime_facts),
            _json_section("Session facts", grounding_bundle.session_facts),
        )
        if section
    )


def _question_section(question: QuestionRequest) -> str:
    question_type = getattr(getattr(question, "question_type", None), "value", "question")
    return f"Question type: {question_type}\nQuestion: {getattr(question, 'raw_input', '')}"


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
