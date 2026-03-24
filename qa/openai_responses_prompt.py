"""Prompt and request-content builders for OpenAI Responses QA answers."""

from __future__ import annotations

import json
import uuid
from typing import Any

from qa.openai_responses_schema import ANSWER_SCHEMA_VERSION

if False:  # pragma: no cover
    from qa.answer_config import AnswerBackendConfig
    from qa.grounding import GroundingBundle
    from types.question_request import QuestionRequest


def build_request_metadata(
    *,
    question: QuestionRequest,
    grounding_bundle: GroundingBundle,
    provider: str,
) -> dict[str, str]:
    """Build stable string-only metadata for one provider request."""
    question_type = getattr(getattr(question, "question_type", None), "value", None)
    return _metadata(
        jarvis_mode="question",
        question_type=question_type,
        grounding_scope=grounding_bundle.scope,
        source_count=len(grounding_bundle.source_paths),
        provider=provider,
        answer_schema_version=ANSWER_SCHEMA_VERSION,
        correlation_id=str(uuid.uuid4()),
    )


def build_instructions(*, config: AnswerBackendConfig) -> str:
    """Build the provider instruction block for grounded structured answers."""
    strict_text = "strictly follow the JSON schema" if config.llm.strict_mode else "follow the JSON schema"
    return (
        "You are the JARVIS answer backend. Answer only from the provided local grounding bundle, do not invent sources, "
        "and do not imply that any command was executed. If grounding is insufficient, set grounded to false and explain that in warning. "
        f"Return schema_version exactly {ANSWER_SCHEMA_VERSION}. "
        "Keep answer_text concise and under 80 words. Use at most 2 source_attributions unless a third source is strictly necessary. "
        "In each source_attributions.source field, return only the raw source path, not the annotated kind/section text. "
        f"Keep each support field to one short factual sentence, and {strict_text}."
    )


def build_user_text(question: QuestionRequest, *, grounding_bundle: GroundingBundle) -> str:
    """Build the user-visible grounding bundle section for one provider request."""
    prompt_source_lines = [_source_line(source) for source in grounding_bundle.sources]
    return "\n\n".join(
        section for section in (
            _question_section(question),
            _sources_section(prompt_source_lines),
            _notes_section(grounding_bundle.source_notes),
            _json_section("Runtime facts", grounding_bundle.runtime_facts),
            _json_section("Session facts", grounding_bundle.session_facts),
        )
        if section
    )


def _question_section(question: QuestionRequest) -> str:
    question_type = getattr(getattr(question, "question_type", None), "value", "question")
    return f"Question type: {question_type}\nQuestion: {getattr(question, 'raw_input', '')}"


def _sources_section(source_lines: list[str]) -> str:
    if not source_lines:
        return "Allowed local sources: none"
    rendered = "\n".join(f"- {line}" for line in source_lines)
    return f"Allowed local sources:\n{rendered}"


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


def _source_line(source) -> str:
    parts = [source.path, f"kind={source.kind}"]
    if source.section_hint:
        parts.append(f"section={source.section_hint}")
    return " | ".join(parts)
