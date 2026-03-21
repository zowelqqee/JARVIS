"""Input adapter interface for JARVIS MVP."""

from __future__ import annotations


def normalize_input(raw_input: str) -> str:
    """Normalize incoming user input into a canonical raw string."""
    raise NotImplementedError("Input normalization is not implemented in MVP skeleton.")

