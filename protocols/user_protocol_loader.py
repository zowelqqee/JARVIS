"""Load user-defined declarative protocol definitions from disk."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from protocols.models import (
    ProtocolActionDefinition,
    ProtocolConfirmationPolicy,
    ProtocolDefinition,
    ProtocolTrigger,
)

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback
    tomllib = None  # type: ignore[assignment]


_PROTOCOLS_DIR_ENV = "JARVIS_PROTOCOLS_DIR"
_DEFAULT_PROTOCOLS_DIR = Path.home() / ".jarvis" / "protocols"
_SUPPORTED_SUFFIXES = {".json", ".toml"}
_SUPPORTED_PROTOCOL_ACTIONS = frozenset(
    {
        "open_app",
        "open_file",
        "open_folder",
        "open_website",
        "close_app",
        "search_local",
        "list_windows",
        "play_music",
        "open_last_workspace",
    }
)


def load_user_protocol_definitions(protocol_dir: Path | None = None) -> tuple[ProtocolDefinition, ...]:
    """Return validated user-defined protocol definitions from disk."""
    directory = protocol_dir or _configured_protocols_dir()
    if not directory.is_dir():
        return ()

    definitions: list[ProtocolDefinition] = []
    for path in sorted(directory.iterdir()):
        if not path.is_file() or path.suffix.lower() not in _SUPPORTED_SUFFIXES:
            continue
        payload = _load_protocol_mapping(path)
        if payload is None:
            continue
        definition = _definition_from_mapping(payload, source=str(path))
        if definition is not None:
            definitions.append(definition)
    return tuple(definitions)


def _configured_protocols_dir() -> Path:
    override = str(os.environ.get(_PROTOCOLS_DIR_ENV, "") or "").strip()
    if override:
        return Path(override).expanduser()
    return _DEFAULT_PROTOCOLS_DIR


def _load_protocol_mapping(path: Path) -> dict[str, Any] | None:
    try:
        if path.suffix.lower() == ".json":
            loaded = json.loads(path.read_text(encoding="utf-8"))
        elif path.suffix.lower() == ".toml" and tomllib is not None:
            loaded = tomllib.loads(path.read_text(encoding="utf-8"))
        else:
            return None
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return None

    if not isinstance(loaded, dict):
        return None
    return loaded


def _definition_from_mapping(payload: dict[str, Any], *, source: str) -> ProtocolDefinition | None:
    protocol_id = _normalized_identifier(payload.get("id"))
    title = str(payload.get("title", "") or "").strip()
    if not protocol_id or not title:
        return None

    enabled = bool(payload.get("enabled", True))
    triggers = tuple(_trigger_from_mapping(item) for item in list(payload.get("triggers", []) or []))
    triggers = tuple(trigger for trigger in triggers if trigger is not None)
    steps = tuple(_step_from_mapping(item) for item in list(payload.get("steps", []) or []))
    steps = tuple(step for step in steps if step is not None)
    if not steps:
        return None

    confirmation_policy = _confirmation_policy(payload.get("confirmation_policy"))
    if confirmation_policy is None:
        return None

    completion_message = str(payload.get("completion_message", "") or "").strip() or None
    completion_message_ru = str(payload.get("completion_message_ru", "") or "").strip() or None
    description = str(payload.get("description", "") or "").strip()
    version = str(payload.get("version", "") or "1").strip() or "1"
    tags = tuple(
        str(tag).strip()
        for tag in list(payload.get("tags", []) or [])
        if str(tag).strip()
    )
    return ProtocolDefinition(
        id=protocol_id,
        title=title,
        description=description,
        version=version,
        triggers=triggers,
        steps=steps,
        confirmation_policy=confirmation_policy,
        enabled=enabled,
        tags=tags,
        completion_message=completion_message,
        completion_message_ru=completion_message_ru,
        source=source,
    )


def _trigger_from_mapping(raw_trigger: Any) -> ProtocolTrigger | None:
    if isinstance(raw_trigger, str):
        phrase = " ".join(raw_trigger.split()).strip()
        if not phrase:
            return None
        return ProtocolTrigger(type="exact", phrase=phrase)

    if not isinstance(raw_trigger, dict):
        return None

    phrase = " ".join(str(raw_trigger.get("phrase", "") or "").split()).strip()
    trigger_type = str(raw_trigger.get("type", "") or "exact").strip() or "exact"
    if not phrase or trigger_type not in {"exact", "alias", "pattern"}:
        return None

    locale = str(raw_trigger.get("locale", "") or "").strip() or None
    wake_word_optional = bool(raw_trigger.get("wake_word_optional", True))
    return ProtocolTrigger(
        type=trigger_type,
        phrase=phrase,
        locale=locale,
        wake_word_optional=wake_word_optional,
    )


def _step_from_mapping(raw_step: Any) -> ProtocolActionDefinition | None:
    if not isinstance(raw_step, dict):
        return None

    action_type = str(raw_step.get("action_type", "") or "").strip()
    if action_type not in _SUPPORTED_PROTOCOL_ACTIONS:
        return None

    inputs = raw_step.get("inputs") if isinstance(raw_step.get("inputs"), dict) else {}
    requires_confirmation_raw = raw_step.get("requires_confirmation")
    requires_confirmation = (
        bool(requires_confirmation_raw)
        if isinstance(requires_confirmation_raw, bool)
        else None
    )
    on_failure = str(raw_step.get("on_failure", "") or "stop").strip() or "stop"
    if on_failure not in {"stop", "continue_if_safe"}:
        return None

    speak_before = str(raw_step.get("speak_before", "") or "").strip() or None
    speak_after = str(raw_step.get("speak_after", "") or "").strip() or None
    return ProtocolActionDefinition(
        action_type=action_type,
        inputs=dict(inputs),
        requires_confirmation=requires_confirmation,
        on_failure=on_failure,
        speak_before=speak_before,
        speak_after=speak_after,
    )


def _confirmation_policy(raw_policy: Any) -> ProtocolConfirmationPolicy | None:
    if isinstance(raw_policy, str):
        mode = str(raw_policy).strip() or "never"
    elif isinstance(raw_policy, dict):
        mode = str(raw_policy.get("mode", "") or "never").strip() or "never"
    else:
        mode = "never"

    if mode not in {"never", "always", "if_sensitive_steps_present", "per_step"}:
        return None
    return ProtocolConfirmationPolicy(mode=mode)


def _normalized_identifier(value: Any) -> str:
    text = " ".join(str(value or "").split()).strip().lower()
    if not text:
        return ""
    return "".join(char if char.isalnum() else "_" for char in text).strip("_")
