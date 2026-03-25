"""Shared question-request contract for JARVIS question-answer mode."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class QuestionType(str, Enum):
    """Supported question families for deterministic QA routing."""

    BLOCKED_STATE = "blocked_state"
    RECENT_RUNTIME = "recent_runtime"
    ANSWER_FOLLOW_UP = "answer_follow_up"
    CAPABILITIES = "capabilities"
    RUNTIME_STATUS = "runtime_status"
    DOCS_RULES = "docs_rules"
    REPO_STRUCTURE = "repo_structure"
    SAFETY_EXPLANATIONS = "safety_explanations"
    OPEN_DOMAIN_GENERAL = "open_domain_general"


@dataclass(slots=True)
class QuestionRequest:
    """Structured question request used by the answer engine."""

    raw_input: str
    question_type: QuestionType
    scope: str
    context_refs: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    requires_grounding: bool = True
