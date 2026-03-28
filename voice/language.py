"""Small locale detection helpers for the voice layer."""

from __future__ import annotations

import re

_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")


def detect_spoken_locale(text: str | None) -> str:
    """Detect the coarse spoken locale needed by the local MVP voice stack."""
    if _CYRILLIC_RE.search(str(text or "")):
        return "ru-RU"
    return "en-US"


def prefers_russian_locale(preferred_locale: str | None, *parts: str) -> bool:
    """Return whether the current spoken rendering should prefer Russian phrasing."""
    locale_text = str(preferred_locale or "").strip().lower()
    if locale_text.startswith("ru"):
        return True
    return _CYRILLIC_RE.search(" ".join(str(part or "") for part in parts)) is not None
