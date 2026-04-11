"""Desktop-session state that sits above the JARVIS core session context."""

from __future__ import annotations

from dataclasses import replace

from context.session_context import SessionContext
from desktop.backend.view_models import PendingPromptViewModel, SessionSnapshotViewModel, StatusViewModel, TranscriptEntry, TurnViewModel


class BackendSessionService:
    """Own desktop conversation history and latest visible backend state."""

    def __init__(self, session_context: SessionContext | None = None) -> None:
        self._session_context = session_context or SessionContext()
        self._history: list[TranscriptEntry] = []
        self._status = StatusViewModel()
        self._pending_prompt: PendingPromptViewModel | None = None
        self._entry_counter = 0

    @property
    def session_context(self) -> SessionContext:
        """Return the shared short-lived core session context."""
        return self._session_context

    def record_turn(self, turn: TurnViewModel) -> None:
        """Append one user turn and its backend-produced entries to history."""
        self._history.append(
            self._with_entry_id(
                TranscriptEntry(
                    role="user",
                    text=str(turn.input_text),
                    entry_kind="input",
                    metadata={"interaction_mode": turn.interaction_mode},
                )
            )
        )
        for entry in list(turn.entries):
            self._history.append(self._with_entry_id(entry))
        self._status = replace(turn.status)
        self._pending_prompt = replace(turn.pending_prompt) if turn.pending_prompt is not None else None

    def snapshot(self) -> SessionSnapshotViewModel:
        """Return the current UI-facing session snapshot."""
        return SessionSnapshotViewModel(
            history=[replace(entry) for entry in self._history],
            status=replace(self._status),
            pending_prompt=replace(self._pending_prompt) if self._pending_prompt is not None else None,
        )

    def reset(self) -> None:
        """Clear desktop history and reset visible state to idle."""
        self._history = []
        self._status = StatusViewModel()
        self._pending_prompt = None
        self._entry_counter = 0

    def _with_entry_id(self, entry: TranscriptEntry) -> TranscriptEntry:
        self._entry_counter += 1
        return replace(entry, entry_id=f"entry-{self._entry_counter}")
