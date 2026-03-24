"""Versioned schema builder for OpenAI Responses grounded answers."""

from __future__ import annotations

from typing import Any

ANSWER_SCHEMA_NAME = "jarvis_grounded_answer"
ANSWER_SCHEMA_VERSION = "qa_answer_v1"


def build_answer_schema() -> dict[str, Any]:
    """Return the frozen structured answer schema."""
    return {
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


def build_text_format(*, strict_mode: bool) -> dict[str, Any]:
    """Return the OpenAI Responses text format block for the frozen schema."""
    return {
        "type": "json_schema",
        "name": ANSWER_SCHEMA_NAME,
        "schema": build_answer_schema(),
        "strict": bool(strict_mode),
    }
