"""Input adapter interface for JARVIS MVP."""

from __future__ import annotations

import re


class InputNormalizationError(ValueError):
    """Raised when raw input cannot be normalized into usable command text."""

    def __init__(self, code: str, message: str) -> None:
        self.category = "INPUT_ERROR"
        self.code = code
        super().__init__(message)


def normalize_input(raw_input: str) -> str:
    """Normalize incoming user input into a canonical raw string."""
    if not isinstance(raw_input, str):
        raise InputNormalizationError("UNREADABLE_INPUT", "Input must be text.")

    normalized = re.sub(r"\s+", " ", raw_input).strip()
    if not normalized:
        raise InputNormalizationError("EMPTY_INPUT", "Input is empty after normalization.")

    if not any(char.isalnum() for char in normalized):
        raise InputNormalizationError("UNREADABLE_INPUT", "Input does not contain usable text.")

    return normalized
