"""Shared answer-summary helpers for question-mode presentation."""

from __future__ import annotations

import re

_SOURCE_PREFIX_PATTERN = (
    r"(?:"
    r"Relevant sources?(?::|\s*[-\u2013\u2014])\s*"
    r"|Sources?(?::|\s*[-\u2013\u2014])\s*"
    r"|(?:The relevant source is|Relevant source)\s+"
    r"|Источники?(?::|\s*[-\u2013\u2014])\s*"
    r"|Источник(?::|\s*[-\u2013\u2014])\s*"
    r")"
)
_EMBEDDED_SOURCE_LIST_ANSWER_RE = re.compile(
    rf"(?:{_SOURCE_PREFIX_PATTERN})(?P<body>.+)$",
    flags=re.IGNORECASE,
)
_SUMMARY_SOURCE_CUE_TRIM_SUFFIX = " \t;,:-([{<'\"`«“\u2013\u2014"


def build_answer_summary(answer_text: str | None, *, max_sentences: int = 2) -> str | None:
    """Return one normalized question summary capped to the leading sentences."""
    normalized = _summary_text_without_embedded_source(answer_text)
    if not normalized:
        return None
    if max_sentences <= 0:
        return normalized

    sentences: list[str] = []
    start = 0
    index = 0
    text_length = len(normalized)
    while index < text_length and len(sentences) < max_sentences:
        character = normalized[index]
        if character in ".!?" and (index == text_length - 1 or normalized[index + 1].isspace()):
            sentence = normalized[start : index + 1].strip()
            if sentence:
                sentences.append(sentence)
            index += 1
            while index < text_length and normalized[index].isspace():
                index += 1
            start = index
            continue
        index += 1

    if not sentences:
        return normalized
    if start < text_length and len(sentences) < max_sentences:
        remainder = normalized[start:].strip()
        if remainder:
            sentences.append(remainder)
    return " ".join(sentences[:max_sentences]).strip() or normalized


def _summary_text_without_embedded_source(answer_text: str | None) -> str:
    normalized = " ".join(str(answer_text or "").split()).strip()
    if not normalized:
        return ""
    match = _EMBEDDED_SOURCE_LIST_ANSWER_RE.search(normalized)
    if match is None or match.start() <= 0:
        return normalized
    trimmed = normalized[: match.start()].rstrip(_SUMMARY_SOURCE_CUE_TRIM_SUFFIX)
    return trimmed or normalized
