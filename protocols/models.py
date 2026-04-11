"""Shared protocol models for named JARVIS scenarios."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ProtocolTrigger:
    """One spoken or typed surface that activates a protocol."""

    type: str
    phrase: str
    locale: str | None = None
    wake_word_optional: bool = True


@dataclass(frozen=True, slots=True)
class ProtocolConfirmationPolicy:
    """Protocol-level confirmation policy."""

    mode: str = "never"


@dataclass(frozen=True, slots=True)
class ProtocolActionDefinition:
    """Declarative protocol action before expansion to runtime steps."""

    action_type: str
    inputs: dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool | None = None
    on_failure: str = "stop"
    speak_before: str | None = None
    speak_after: str | None = None


@dataclass(frozen=True, slots=True)
class ProtocolDefinition:
    """Named reusable scenario definition."""

    id: str
    title: str
    description: str = ""
    version: str = "1"
    triggers: tuple[ProtocolTrigger, ...] = ()
    steps: tuple[ProtocolActionDefinition, ...] = ()
    confirmation_policy: ProtocolConfirmationPolicy = field(default_factory=ProtocolConfirmationPolicy)
    enabled: bool = True
    tags: tuple[str, ...] = ()
    completion_message: str | None = None
    completion_message_ru: str | None = None
    source: str = "builtin"


@dataclass(frozen=True, slots=True)
class ProtocolMatch:
    """Resolved protocol match for a user input."""

    definition: ProtocolDefinition
    trigger: ProtocolTrigger | None = None
    requested_text: str | None = None
