"""View-model contracts for the desktop backend facade."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class TranscriptEntry:
    """One user-visible history entry for the desktop conversation."""

    role: str
    text: str
    entry_kind: str = "message"
    metadata: dict[str, Any] = field(default_factory=dict)
    entry_id: str | None = None


@dataclass(slots=True)
class PendingPromptViewModel:
    """One pending clarification or confirmation prompt."""

    kind: str
    message: str
    options: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class StatusViewModel:
    """Desktop-friendly status snapshot derived from the JARVIS core."""

    interaction_mode: str | None = None
    runtime_state: str = "idle"
    command_summary: str | None = None
    current_step: str | None = None
    blocked_reason: str | None = None
    next_step_hint: str | None = None
    completion_result: str | None = None
    failure_message: str | None = None
    can_cancel: bool = False
    busy: bool = False
    speech_enabled: bool = False
    speech_available: bool | None = None
    speech_backend: str | None = None
    speech_message: str | None = None


@dataclass(slots=True)
class TurnViewModel:
    """Desktop-facing result of one submitted user input."""

    input_text: str
    interaction_mode: str
    entries: list[TranscriptEntry] = field(default_factory=list)
    status: StatusViewModel = field(default_factory=StatusViewModel)
    pending_prompt: PendingPromptViewModel | None = None
    visibility: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SessionSnapshotViewModel:
    """Current desktop session state for the UI layer."""

    history: list[TranscriptEntry] = field(default_factory=list)
    status: StatusViewModel = field(default_factory=StatusViewModel)
    pending_prompt: PendingPromptViewModel | None = None
