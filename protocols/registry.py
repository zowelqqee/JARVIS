"""Registry and lookup helpers for built-in and user-defined protocols."""

from __future__ import annotations

import re
from typing import Any

from protocols.builtin_protocols import BUILTIN_PROTOCOLS
from protocols.models import ProtocolDefinition, ProtocolMatch
from protocols.user_protocol_loader import load_user_protocol_definitions


def list_protocols() -> tuple[ProtocolDefinition, ...]:
    """Return enabled protocol definitions with user overrides applied last."""
    merged: dict[str, ProtocolDefinition] = {}
    for definition in BUILTIN_PROTOCOLS:
        if definition.enabled:
            merged[definition.id] = definition
    for definition in load_user_protocol_definitions():
        if definition.enabled:
            merged[definition.id] = definition
    return tuple(merged.values())


def get_protocol_by_id(protocol_id: str | None) -> ProtocolDefinition | None:
    """Return one protocol by id when available."""
    normalized = _normalize_identifier(protocol_id)
    if not normalized:
        return None
    for definition in list_protocols():
        if definition.id == normalized:
            return definition
    return None


def match_protocol_trigger(text: str) -> tuple[ProtocolMatch, ...]:
    """Return all trigger matches for one normalized input surface."""
    candidate = _normalize_surface(text)
    if not candidate:
        return ()

    matches: list[ProtocolMatch] = []
    for definition in list_protocols():
        for trigger in definition.triggers:
            if _trigger_matches(candidate, trigger):
                matches.append(ProtocolMatch(definition=definition, trigger=trigger, requested_text=text))
    return tuple(matches)


def resolve_protocol_reference(reference: str) -> tuple[ProtocolMatch, ...]:
    """Return id/title matches for an explicit protocol reference like `protocol clean slate`."""
    candidate = _normalize_surface(reference)
    if not candidate:
        return ()

    matches: list[ProtocolMatch] = []
    for definition in list_protocols():
        if candidate in {
            _normalize_surface(definition.id),
            _normalize_surface(definition.title),
        }:
            matches.append(ProtocolMatch(definition=definition, trigger=None, requested_text=reference))
    return tuple(matches)


def protocol_suggestions(reference: str, *, limit: int = 5) -> list[str]:
    """Return a small list of close title/id suggestions for an unknown protocol reference."""
    candidate = _normalize_surface(reference)
    if not candidate:
        return []

    ranked: list[tuple[int, str]] = []
    for definition in list_protocols():
        options = {_normalize_surface(definition.id), _normalize_surface(definition.title)}
        best_rank = min(_distance_rank(candidate, option) for option in options if option)
        ranked.append((best_rank, definition.title))
    ranked.sort(key=lambda item: (item[0], item[1].lower()))
    suggestions: list[str] = []
    for rank, title in ranked:
        if rank > 3:
            continue
        if title not in suggestions:
            suggestions.append(title)
        if len(suggestions) >= limit:
            break
    return suggestions


def _trigger_matches(candidate: str, trigger: Any) -> bool:
    trigger_type = str(getattr(trigger, "type", "") or "").strip()
    trigger_phrase = _normalize_surface(getattr(trigger, "phrase", ""))
    if not trigger_phrase:
        return False
    if trigger_type in {"exact", "alias"}:
        return candidate == trigger_phrase
    if trigger_type == "pattern":
        try:
            return bool(re.fullmatch(getattr(trigger, "phrase", ""), candidate, flags=re.IGNORECASE))
        except re.error:
            return False
    return False


def _normalize_surface(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _normalize_identifier(value: Any) -> str:
    normalized = _normalize_surface(value)
    return "".join(char if char.isalnum() else "_" for char in normalized).strip("_")


def _distance_rank(candidate: str, option: str) -> int:
    if candidate == option:
        return 0
    if candidate in option or option in candidate:
        return 1
    candidate_tokens = set(candidate.split())
    option_tokens = set(option.split())
    overlap = candidate_tokens & option_tokens
    if overlap:
        return 2
    return 4
