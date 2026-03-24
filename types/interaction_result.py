"""Top-level interaction result contract for dual-mode handling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from interaction_kind import InteractionKind

if TYPE_CHECKING:
    from runtime.runtime_manager import RuntimeResult
    from types.answer_result import AnswerResult
    from types.clarification_request import ClarificationRequest
    from types.jarvis_error import JarvisError


InteractionMode = InteractionKind


@dataclass(slots=True)
class InteractionResult:
    """Unified result wrapper for command-mode and question-mode handling."""

    interaction_mode: InteractionKind
    normalized_input: str | None = None
    runtime_result: RuntimeResult | None = None
    answer_result: AnswerResult | None = None
    clarification_request: ClarificationRequest | None = None
    error: JarvisError | None = None
    visibility: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
