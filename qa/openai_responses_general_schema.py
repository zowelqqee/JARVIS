"""Versioned schema builder for OpenAI Responses open-domain answers."""

from __future__ import annotations

from typing import Any

GENERAL_ANSWER_SCHEMA_NAME = "jarvis_open_domain_answer"
GENERAL_ANSWER_SCHEMA_VERSION = "qa_general_answer_v1"


def build_general_answer_schema() -> dict[str, Any]:
    """Return the frozen structured schema for open-domain model answers."""
    return {
        "type": "object",
        "properties": {
            "schema_version": {
                "type": "string",
                "enum": [GENERAL_ANSWER_SCHEMA_VERSION],
                "description": "Versioned contract identifier for open-domain answer parsing.",
            },
            "answer_text": {
                "type": "string",
                "description": "The read-only open-domain answer text for the user.",
            },
            "answer_kind": {
                "type": "string",
                "enum": ["open_domain_model", "refusal"],
                "description": "Open-domain answer vs model-backed refusal result.",
            },
            "warning": {
                "type": "string",
                "description": "Empty string when there is no warning, otherwise a short bounded warning.",
            },
        },
        "required": ["schema_version", "answer_text", "answer_kind", "warning"],
        "additionalProperties": False,
    }


def build_general_text_format(*, strict_mode: bool) -> dict[str, Any]:
    """Return the OpenAI Responses text format block for the open-domain schema."""
    return {
        "type": "json_schema",
        "name": GENERAL_ANSWER_SCHEMA_NAME,
        "schema": build_general_answer_schema(),
        "strict": bool(strict_mode),
    }
