"""Shared answer result contract for JARVIS question-answer mode."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class AnswerResult:
    """Grounded answer payload returned by the answer engine."""

    answer_text: str
    sources: list[str] = field(default_factory=list)
    confidence: float = 0.0
    warning: str | None = None
    interaction_mode: str = "question"
