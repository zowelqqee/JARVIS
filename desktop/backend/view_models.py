"""View-model contracts for the desktop backend facade."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class PromptActionViewModel:
    """One explicit desktop action derived from a pending prompt."""

    action_id: str
    label: str
    submit_text: str


@dataclass(slots=True)
class AnswerSourceViewModel:
    """One grounded answer source exposed to the desktop shell."""

    path: str
    label: str


@dataclass(slots=True)
class SourceAttributionViewModel:
    """One explicit support statement for a grounded answer source."""

    source_path: str
    source_label: str | None
    support: str


@dataclass(slots=True)
class ResultListItemViewModel:
    """One search/window result item for a structured desktop surface."""

    item_id: str
    title: str
    subtitle: str | None = None
    detail: str | None = None


@dataclass(slots=True)
class ResultListViewModel:
    """One structured result list such as search matches or visible windows."""

    kind: str
    title: str
    summary: str | None = None
    items: tuple[ResultListItemViewModel, ...] = ()


@dataclass(slots=True)
class CommandProgressViewModel:
    """Command-mode runtime details exposed to desktop result surfaces."""

    runtime_state: str
    command_summary: str | None = None
    current_step: str | None = None
    completed_steps: tuple[str, ...] = ()
    blocked_reason: str | None = None
    next_step_hint: str | None = None


@dataclass(slots=True)
class EntrySurfaceViewModel:
    """Structured desktop surface metadata attached to one transcript entry."""

    surface_kind: str
    answer_summary: str | None = None
    answer_kind: str | None = None
    answer_provenance: str | None = None
    command_progress: CommandProgressViewModel | None = None
    result_lists: tuple[ResultListViewModel, ...] = ()
    sources: tuple[AnswerSourceViewModel, ...] = ()
    source_attributions: tuple[SourceAttributionViewModel, ...] = ()
    actions: tuple[PromptActionViewModel, ...] = ()


@dataclass(slots=True)
class TranscriptEntry:
    """One user-visible history entry for the desktop conversation."""

    role: str
    text: str
    entry_kind: str = "message"
    metadata: dict[str, Any] = field(default_factory=dict)
    entry_id: str | None = None
    surface: EntrySurfaceViewModel | None = None


@dataclass(slots=True)
class PendingPromptViewModel:
    """One pending clarification or confirmation prompt."""

    kind: str
    message: str
    options: list[str] = field(default_factory=list)
    actions: tuple[PromptActionViewModel, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class StatusViewModel:
    """Desktop-friendly status snapshot derived from the JARVIS core."""

    interaction_mode: str | None = None
    runtime_state: str = "idle"
    command_summary: str | None = None
    current_step: str | None = None
    completed_steps: tuple[str, ...] = ()
    blocked_reason: str | None = None
    next_step_hint: str | None = None
    next_required_action: str | None = None
    completion_result: str | None = None
    failure_message: str | None = None
    result_lists: tuple[ResultListViewModel, ...] = ()
    available_controls: tuple[str, ...] = ()
    can_cancel: bool = False
    retry_prompt_available: bool = False
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
