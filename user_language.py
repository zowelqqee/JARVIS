"""Small helpers for choosing RU vs EN user-facing phrasing."""

from __future__ import annotations

import re
from collections.abc import Sequence

_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")


def prefers_russian_text(*parts: str, locale_hint: str | None = None) -> bool:
    """Return whether one visible surface should prefer Russian phrasing."""
    normalized_locale = str(locale_hint or "").strip().lower().replace("_", "-")
    if normalized_locale.startswith("ru"):
        return True
    return _CYRILLIC_RE.search(" ".join(str(part or "") for part in parts)) is not None


def preferred_language_from_locales(locales: Sequence[str] | None) -> str:
    """Pick one coarse language from a locale preference chain."""
    for locale in list(locales or []):
        normalized = str(locale or "").strip().lower().replace("_", "-")
        if not normalized:
            continue
        if normalized.startswith("ru"):
            return "ru"
        if normalized.startswith("en"):
            return "en"
    return "en"
