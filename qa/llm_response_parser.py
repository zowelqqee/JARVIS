"""Shared parser interface for model-backed answer providers."""

from __future__ import annotations

from typing import Protocol

if False:  # pragma: no cover
    from qa.grounding import GroundingBundle
    from types.answer_result import AnswerResult


class LlmResponseParser(Protocol):
    """Protocol for provider-specific structured answer parsers."""

    def parse_response(
        self,
        response_payload: dict,
        *,
        grounding_bundle: GroundingBundle,
        debug_trace: dict | None = None,
    ) -> AnswerResult:
        """Parse one provider response into the shared AnswerResult contract."""
