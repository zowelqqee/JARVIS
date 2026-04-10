"""Small helpers for keeping model-backed answers in the user's language."""

from __future__ import annotations

import re

_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё]+")
_NEUTRAL_LATIN_TOKENS = {
    "api",
    "asr",
    "cli",
    "docker",
    "faq",
    "github",
    "gui",
    "http",
    "https",
    "jarvis",
    "json",
    "llm",
    "macos",
    "mvp",
    "ok",
    "okay",
    "openai",
    "piper",
    "postgres",
    "python",
    "qa",
    "swift",
    "toml",
    "tts",
    "url",
    "yaml",
}


def answer_language_guidance_section(text: str | None) -> str:
    """Return a prompt section that locks answer_text to the user's main language."""
    language = preferred_answer_language(text)
    label = "Russian" if language == "ru" else "English"
    return (
        "Answer language preference:\n"
        f"- Preferred answer language: {label}.\n"
        "- Choose it from the user's first meaningful words, falling back to the dominant alphabet in the message.\n"
        "- Use this language for answer_text; keep exact proper nouns, acronyms, commands, paths, and code tokens unchanged."
    )


def question_request_language(question: object | None) -> str:
    """Resolve the user's preferred answer language from one question request."""
    context_refs = getattr(question, "context_refs", {}) or {}
    if isinstance(context_refs, dict):
        explicit = str(context_refs.get("request_language", "") or "").strip().lower()
        if explicit in {"ru", "en"}:
            return explicit
    return preferred_answer_language(getattr(question, "raw_input", ""))


def preferred_answer_language(text: str | None) -> str:
    """Detect a coarse answer language from first meaningful words, then majority script."""
    current = str(text or "")
    first_signal = _first_meaningful_language_signal(current)
    if first_signal:
        return first_signal

    latin_letters = sum(1 for char in current if _LATIN_RE.fullmatch(char))
    cyrillic_letters = sum(1 for char in current if _CYRILLIC_RE.fullmatch(char))
    if cyrillic_letters > latin_letters:
        return "ru"
    return "en"


def _first_meaningful_language_signal(text: str) -> str:
    for match in _WORD_RE.finditer(text):
        token = match.group(0)
        if _CYRILLIC_RE.search(token):
            return "ru"
        if _LATIN_RE.search(token):
            normalized = token.lower()
            if normalized in _NEUTRAL_LATIN_TOKENS:
                continue
            return "en"
    return ""
