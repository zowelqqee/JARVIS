"""Controller that connects the desktop UI shell to the JARVIS backend facade."""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from desktop.backend import EngineFacade, build_default_engine_facade
from desktop.backend.view_models import PendingPromptViewModel, SessionSnapshotViewModel, StatusViewModel
from input.voice_input import VoiceInputError

_WELCOME_TEXT = "JARVIS shell is ready. Ask a question or enter a command."


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
        self._last_snapshot = SessionSnapshotViewModel()
        self._last_prompt_signature: tuple[str, str] | None = None
        self._last_prompt_reply_text: str | None = None

    @property
    def engine_facade(self) -> EngineFacade:
        """Expose the backend facade for tests and future actions."""
        return self._engine_facade

    def bind(self) -> None:
        """Connect UI events and render the initial backend snapshot."""
        self._composer.submitted.connect(self.submit_text)
        voice_request_signal = getattr(self._composer, "voice_requested", None)
        if hasattr(voice_request_signal, "connect"):
            voice_request_signal.connect(self.start_voice_capture)
        prompt_action_signal = getattr(self._conversation_view, "prompt_action_requested", None)
        if hasattr(prompt_action_signal, "connect"):
            prompt_action_signal.connect(self.submit_prompt_action)
        speech_toggle = getattr(self._status_panel, "speech_toggled", None)
        if hasattr(speech_toggle, "connect"):
            speech_toggle.connect(self.set_speech_enabled)
        cancel_requested = getattr(self._status_panel, "cancel_requested", None)
        if hasattr(cancel_requested, "connect"):
            cancel_requested.connect(self.cancel_current_flow)
        reset_requested = getattr(self._status_panel, "reset_requested", None)
        if hasattr(reset_requested, "connect"):
            reset_requested.connect(self.reset_session)
        retry_requested = getattr(self._status_panel, "retry_requested", None)
        if hasattr(retry_requested, "connect"):
            retry_requested.connect(self.retry_last_prompt)
        self._render_snapshot(self._engine_facade.snapshot())
        self._reset_composer_voice_state()
        self._show_message("JARVIS shell connected")

    def submit_text(self, text: str) -> None:
        """Submit one UI text input through the JARVIS backend facade."""
        normalized_text = str(text or "").strip()
        if not normalized_text:
            return
        self._remember_prompt_reply(normalized_text)
        self._submit_via_shell(normalized_text)

    def submit_prompt_action(self, submit_text: str) -> None:
        """Route one prompt-action click through the normal text submission path."""
        self.submit_text(submit_text)

    def cancel_current_flow(self) -> None:
        """Cancel the current supervised flow through the standard input path."""
        if not bool(getattr(self._last_snapshot.status, "can_cancel", False)):
            return
        self.submit_text("cancel")

    def reset_session(self) -> None:
        """Start a clean desktop shell session via the existing facade hook."""
        snapshot = self._engine_facade.reset_session()
        self._last_prompt_signature = None
        self._last_prompt_reply_text = None
        self._render_snapshot(snapshot)
        self._reset_composer_voice_state()
        self._show_message("New session ready")

    def retry_last_prompt(self) -> None:
        """Replay the last explicit prompt reply when the same prompt is still active."""
        if not self._can_retry_prompt():
            return
        retry_text = str(self._last_prompt_reply_text or "").strip()
        if not retry_text:
            return
        self._submit_via_shell(retry_text)

    def start_voice_capture(self) -> None:
        """Capture one spoken request and submit it through the normal shell path."""
        capture_voice_text = getattr(self._engine_facade, "capture_voice_text", None)
        if not callable(capture_voice_text):
            return
        self._composer.set_busy(True)
        self._set_composer_voice_state("listening")
        self._show_message("Listening for a spoken request...")
        _flush_ui_updates()

        try:
            transcript = str(capture_voice_text() or "").strip()
        except Exception as exc:
            self._composer.set_busy(False)
            self._handle_voice_capture_error(exc)
            return

        if not transcript:
            self._composer.set_busy(False)
            self._handle_voice_capture_error(VoiceInputError("EMPTY_RECOGNITION", "No speech was recognized. Try again."))
            return

        self._remember_prompt_reply(transcript)
        self._set_composer_voice_state(
            "routing",
            detail=f'Heard: "{_shorten_voice_transcript(transcript)}"',
        )
        self._show_message("Submitting voice request...")
        self._submit_via_shell(transcript, already_busy=True)
        self._reset_composer_voice_state(detail=f'Last heard: "{_shorten_voice_transcript(transcript)}"')

    def _submit_via_shell(self, normalized_text: str, *, already_busy: bool = False) -> None:
        if not already_busy:
            self._composer.set_busy(True)
        self._show_message("Running request...")

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
            error_status = replace(
                speech_status,
                interaction_mode="desktop_error",
                runtime_state="failed",
                failure_message=str(exc),
            )
            self._status_panel.set_status(
                _status_with_shell_actions(
                    SessionSnapshotViewModel(status=error_status),
                    retry_prompt_available=False,
                )
            )
            self._show_message("Desktop shell error")
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
        self._last_snapshot = snapshot
        self._conversation_view.clear_entries()
        if snapshot.history:
            self._conversation_view.set_entries(snapshot.history)
        else:
            self._conversation_view.add_entry(role="assistant", text=_WELCOME_TEXT, entry_kind="result")
        self._status_panel.set_status(_status_with_shell_actions(snapshot, retry_prompt_available=self._can_retry_prompt(snapshot)))

    def _show_message(self, message: str) -> None:
        if self._status_sink is not None:
            self._status_sink.showMessage(str(message or "").strip())

    def _remember_prompt_reply(self, text: str) -> None:
        prompt_signature = _prompt_signature(self._last_snapshot.pending_prompt)
        if prompt_signature is None:
            return
        self._last_prompt_signature = prompt_signature
        self._last_prompt_reply_text = str(text or "").strip() or None

    def _handle_voice_capture_error(self, exc: Exception) -> None:
        detail = _voice_error_detail(exc)
        state = "unavailable" if isinstance(exc, VoiceInputError) and exc.code == "UNSUPPORTED_PLATFORM" else "error"
        self._set_composer_voice_state(state, detail=detail)
        self._show_message(str(getattr(exc, "args", ["Voice input failed."])[0]).strip() or "Voice input failed.")

    def _reset_composer_voice_state(self, *, detail: str | None = None) -> None:
        reset_voice_state = getattr(self._composer, "reset_voice_state", None)
        if callable(reset_voice_state):
            reset_voice_state(detail=detail)

    def _set_composer_voice_state(self, state: str, *, detail: str | None = None) -> None:
        set_voice_state = getattr(self._composer, "set_voice_state", None)
        if callable(set_voice_state):
            set_voice_state(state, detail=detail)

    def _can_retry_prompt(self, snapshot: SessionSnapshotViewModel | None = None) -> bool:
        active_snapshot = snapshot or self._last_snapshot
        prompt_signature = _prompt_signature(active_snapshot.pending_prompt)
        if prompt_signature is None:
            return False
        if not self._last_prompt_reply_text:
            return False
        return prompt_signature == self._last_prompt_signature


def _status_bar_message(snapshot: SessionSnapshotViewModel) -> str:
    status = snapshot.status
    if snapshot.pending_prompt is not None:
        return f"Waiting for {snapshot.pending_prompt.kind}"
    if status.failure_message:
        return "Request failed"
    if status.completion_result:
        if status.interaction_mode == "question":
            return "Answer ready"
        if status.interaction_mode == "command":
            return "Command complete"
        return "Request complete"
    if status.blocked_reason:
        return "Waiting for your reply"
    if status.interaction_mode == "desktop_shell" and status.speech_message:
        return status.speech_message
    return "Shell ready"


def _status_with_shell_actions(
    snapshot: SessionSnapshotViewModel,
    *,
    retry_prompt_available: bool,
) -> StatusViewModel:
    status = snapshot.status
    pending_prompt = snapshot.pending_prompt
    available_controls = ["New Session", "Speech Toggle"]
    if status.can_cancel:
        available_controls.insert(0, "Cancel Flow")
    if retry_prompt_available:
        insert_index = 1 if status.can_cancel else 0
        available_controls.insert(insert_index, "Retry Prompt")
    if pending_prompt is not None and pending_prompt.actions:
        available_controls.append("Reply Chips")
    return replace(
        status,
        next_required_action=_next_required_action(snapshot),
        available_controls=tuple(available_controls),
        retry_prompt_available=retry_prompt_available,
    )


def _next_required_action(snapshot: SessionSnapshotViewModel) -> str:
    status = snapshot.status
    pending_prompt = snapshot.pending_prompt
    if pending_prompt is not None:
        if pending_prompt.kind == "confirmation":
            if pending_prompt.actions:
                return "Choose Confirm or Cancel in the shell feed, or type your reply."
            return "Type confirm or cancel in the shell feed."
        if pending_prompt.actions:
            return "Choose a reply chip in the shell feed, or type the missing detail."
        return "Type the requested clarification in the shell feed."
    if status.failure_message:
        return "Review the failure, then retry or start a new session."
    if status.completion_result:
        return "Enter a follow-up question or command."
    if status.busy:
        return "Wait for the current request to finish."
    return "Enter a question or command."


def _prompt_signature(prompt: PendingPromptViewModel | None) -> tuple[str, str] | None:
    if prompt is None:
        return None
    kind = str(getattr(prompt, "kind", "") or "").strip()
    message = str(getattr(prompt, "message", "") or "").strip()
    if not kind or not message:
        return None
    return kind, message


def _voice_error_detail(exc: Exception) -> str:
    message = str(exc).strip() or "Voice input failed."
    hint = str(getattr(exc, "hint", "") or "").strip()
    if hint:
        return f"{message} {hint}"
    return message


def _shorten_voice_transcript(transcript: str, *, max_chars: int = 72) -> str:
    normalized = " ".join(str(transcript or "").split())
    if len(normalized) <= max_chars:
        return normalized
    return f"{normalized[: max_chars - 3].rstrip()}..."


def _flush_ui_updates() -> None:
    try:
        from PySide6.QtWidgets import QApplication
    except Exception:
        return
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
