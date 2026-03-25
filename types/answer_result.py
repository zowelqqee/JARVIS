"""Shared answer result contract for JARVIS question-answer mode."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from interaction_kind import InteractionKind


class AnswerKind(str, Enum):
    """Stable answer taxonomy shared across QA backends and UI."""

    GROUNDED_LOCAL = "grounded_local"
    OPEN_DOMAIN_MODEL = "open_domain_model"
    REFUSAL = "refusal"

    def __str__(self) -> str:
        return self.value


class AnswerProvenance(str, Enum):
    """Stable provenance vocabulary for question-answer results."""

    LOCAL_SOURCES = "local_sources"
    MODEL_KNOWLEDGE = "model_knowledge"

    def __str__(self) -> str:
        return self.value


def answer_kind_value(kind: AnswerKind | str | None) -> str | None:
    """Return the stable string value for an answer kind."""
    if kind is None:
        return None
    value = str(getattr(kind, "value", kind)).strip()
    return value or None


def answer_provenance_value(provenance: AnswerProvenance | str | None) -> str | None:
    """Return the stable string value for answer provenance."""
    if provenance is None:
        return None
    value = str(getattr(provenance, "value", provenance)).strip()
    return value or None


@dataclass(slots=True)
class AnswerSourceAttribution:
    """One grounded source plus the support statement it backs."""

    source: str
    support: str


@dataclass(slots=True)
class AnswerResult:
    """Answer payload returned by the answer engine."""

    answer_text: str
    sources: list[str] = field(default_factory=list)
    source_attributions: list[AnswerSourceAttribution] = field(default_factory=list)
    confidence: float = 0.0
    warning: str | None = None
    answer_kind: AnswerKind = AnswerKind.GROUNDED_LOCAL
    provenance: AnswerProvenance | None = AnswerProvenance.LOCAL_SOURCES
    interaction_mode: InteractionKind = InteractionKind.QUESTION
