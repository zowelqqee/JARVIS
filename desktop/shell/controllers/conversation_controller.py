"""Controller that connects the desktop UI shell to the JARVIS backend facade."""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from desktop.backend import EngineFacade, build_default_engine_facade
from desktop.backend.view_models import SessionSnapshotViewModel, StatusViewModel

_WELCOME_TEXT = "JARVIS desktop is connected. Ask a question or enter a command."


class _StatusSink(Protocol):
    def showMessage(self, message: str) -> None: ...  # noqa: N802


class ConversationController:
    """Own the data flow between the shell widgets and the backend facade."""

    def __init__(
        self,
        *,
        engine_facade: EngineFacade | None = None,
        conversation_view: object,
        composer: object,
        status_panel: object,
        status_sink: _StatusSink | None = None,
    ) -> None:
        self._engine_facade = engine_facade or build_default_engine_facade()
        self._conversation_view = conversation_view
        self._composer = composer
        self._status_panel = status_panel
        self._status_sink = status_sink

    @property
    def engine_facade(self) -> EngineFacade:
        """Expose the backend facade for tests and future actions."""
        return self._engine_facade

    def bind(self) -> None:
        """Connect UI events and render the initial backend snapshot."""
        self._composer.submitted.connect(self.submit_text)
        speech_toggle = getattr(self._status_panel, "speech_toggled", None)
        if hasattr(speech_toggle, "connect"):
            speech_toggle.connect(self.set_speech_enabled)
        self._render_snapshot(self._engine_facade.snapshot())
        self._show_message("Connected to JARVIS core")

    def submit_text(self, text: str) -> None:
        """Submit one UI text input through the JARVIS backend facade."""
        normalized_text = str(text or "").strip()
        if not normalized_text:
            return

        self._composer.set_busy(True)
        self._show_message("Processing request...")

        try:
            self._engine_facade.submit_text(normalized_text)
        except Exception as exc:
            self._composer.set_busy(False)
            self._conversation_view.add_entry(role="user", text=normalized_text, entry_kind="input")
            speech_status = getattr(self._engine_facade.snapshot(), "status", StatusViewModel())
            self._conversation_view.add_entry(
                role="system",
                text=f"Desktop integration error: {exc}",
                entry_kind="error",
            )
            self._status_panel.set_status(
                replace(
                    speech_status,
                    interaction_mode="desktop_error",
                    runtime_state="failed",
                    failure_message=str(exc),
                )
            )
            self._show_message("Desktop integration error")
            return

        self._composer.set_busy(False)
        snapshot = self._engine_facade.snapshot()
        self._render_snapshot(snapshot)
        self._show_message(_status_bar_message(snapshot))

    def set_speech_enabled(self, enabled: bool) -> None:
        """Update desktop speech-output mode from the status panel."""
        snapshot = self._engine_facade.set_speech_enabled(bool(enabled))
        self._render_snapshot(snapshot)
        self._show_message(snapshot.status.speech_message or ("Speech output enabled" if enabled else "Speech output disabled"))

    def _render_snapshot(self, snapshot: SessionSnapshotViewModel) -> None:
        self._conversation_view.clear_entries()
        if snapshot.history:
            self._conversation_view.set_entries(snapshot.history)
        else:
            self._conversation_view.add_entry(role="assistant", text=_WELCOME_TEXT, entry_kind="result")
        self._status_panel.set_status(snapshot.status)

    def _show_message(self, message: str) -> None:
        if self._status_sink is not None:
            self._status_sink.showMessage(str(message or "").strip())


def _status_bar_message(snapshot: SessionSnapshotViewModel) -> str:
    status = snapshot.status
    if snapshot.pending_prompt is not None:
        return f"Awaiting {snapshot.pending_prompt.kind}"
    if status.failure_message:
        return "Request failed"
    if status.completion_result:
        return "Request complete"
    if status.blocked_reason:
        return "Waiting for your reply"
    if status.interaction_mode == "desktop_shell" and status.speech_message:
        return status.speech_message
    return "Ready"
