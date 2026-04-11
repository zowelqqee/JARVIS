"""Tests for the desktop conversation controller."""

from __future__ import annotations

from dataclasses import dataclass, field
import unittest

from desktop.backend.view_models import PendingPromptViewModel, SessionSnapshotViewModel, StatusViewModel, TranscriptEntry, TurnViewModel
from desktop.shell.controllers.conversation_controller import ConversationController


class _FakeSignal:
    def __init__(self) -> None:
        self._callbacks: list[object] = []

    def connect(self, callback: object) -> None:
        self._callbacks.append(callback)

    def emit(self, *args: object) -> None:
        for callback in list(self._callbacks):
            callback(*args)


class _FakeComposer:
    def __init__(self) -> None:
        self.submitted = _FakeSignal()
        self.voice_requested = _FakeSignal()
        self.busy_states: list[bool] = []
        self.voice_states: list[tuple[str, str | None]] = []
        self.voice_resets: list[str | None] = []

    def set_busy(self, busy: bool) -> None:
        self.busy_states.append(bool(busy))

    def set_voice_state(self, state: str, *, detail: str | None = None) -> None:
        self.voice_states.append((state, detail))

    def reset_voice_state(self, *, detail: str | None = None) -> None:
        self.voice_resets.append(detail)


class _FakeConversationView:
    def __init__(self) -> None:
        self.entries: list[TranscriptEntry] = []
        self.prompt_action_requested = _FakeSignal()

    def clear_entries(self) -> None:
        self.entries = []

    def set_entries(self, entries: list[TranscriptEntry]) -> None:
        self.entries = list(entries)

    def add_entry(
        self,
        *,
        role: str,
        text: str,
        entry_kind: str = "message",
        metadata: dict | None = None,
        surface: object | None = None,
    ) -> None:
        self.entries.append(
            TranscriptEntry(role=role, text=text, entry_kind=entry_kind, metadata=dict(metadata or {}), surface=surface)
        )


class _FakeStatusPanel:
    def __init__(self) -> None:
        self.statuses: list[StatusViewModel] = []
        self.speech_toggled = _FakeSignal()
        self.cancel_requested = _FakeSignal()
        self.reset_requested = _FakeSignal()
        self.retry_requested = _FakeSignal()

    def set_status(self, status: StatusViewModel) -> None:
        self.statuses.append(status)


class _FakeStatusSink:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def showMessage(self, message: str) -> None:  # noqa: N802
        self.messages.append(message)


@dataclass
class _FakeFacade:
    initial_snapshot: SessionSnapshotViewModel = field(default_factory=SessionSnapshotViewModel)
    current_snapshot: SessionSnapshotViewModel = field(default_factory=SessionSnapshotViewModel)
    reset_snapshot: SessionSnapshotViewModel = field(default_factory=SessionSnapshotViewModel)
    submitted_texts: list[str] = field(default_factory=list)
    speech_enabled_changes: list[bool] = field(default_factory=list)
    capture_voice_calls: int = 0
    captured_voice_text: str | None = "Open Safari"
    capture_voice_error: Exception | None = None
    reset_calls: int = 0
    error_on_submit: Exception | None = None

    def snapshot(self) -> SessionSnapshotViewModel:
        if self.submitted_texts:
            return self.current_snapshot
        return self.initial_snapshot

    def submit_text(self, raw_input: str) -> TurnViewModel:
        self.submitted_texts.append(raw_input)
        if self.error_on_submit is not None:
            raise self.error_on_submit
        return TurnViewModel(input_text=raw_input, interaction_mode="question")

    def set_speech_enabled(self, enabled: bool) -> SessionSnapshotViewModel:
        self.speech_enabled_changes.append(bool(enabled))
        self.current_snapshot.status.speech_enabled = bool(enabled)
        self.current_snapshot.status.speech_message = "Speech output enabled." if enabled else "Speech output disabled."
        return self.current_snapshot

    def capture_voice_text(self) -> str:
        self.capture_voice_calls += 1
        if self.capture_voice_error is not None:
            raise self.capture_voice_error
        return str(self.captured_voice_text or "")

    def reset_session(self) -> SessionSnapshotViewModel:
        self.reset_calls += 1
        return self.reset_snapshot


class ConversationControllerTests(unittest.TestCase):
    def test_bind_renders_welcome_message_for_empty_backend_history(self) -> None:
        controller, conversation_view, _composer, status_panel, status_sink, _facade = _build_controller()

        controller.bind()

        self.assertEqual(len(conversation_view.entries), 1)
        self.assertEqual(conversation_view.entries[0].role, "assistant")
        self.assertEqual(status_panel.statuses[-1].runtime_state, "idle")
        self.assertEqual(status_sink.messages[-1], "JARVIS shell connected")

    def test_submit_text_renders_backend_snapshot_and_updates_status(self) -> None:
        snapshot_after_submit = SessionSnapshotViewModel(
            history=[
                TranscriptEntry(role="user", text="What can you do?", entry_kind="input"),
                TranscriptEntry(role="assistant", text="I can answer grounded questions.", entry_kind="answer"),
            ],
            status=StatusViewModel(
                interaction_mode="question",
                runtime_state="idle",
                completion_result="Answer ready.",
            ),
        )
        controller, conversation_view, composer, status_panel, status_sink, facade = _build_controller(
            current_snapshot=snapshot_after_submit
        )
        controller.bind()

        controller.submit_text("What can you do?")

        self.assertEqual(facade.submitted_texts, ["What can you do?"])
        self.assertEqual([entry.text for entry in conversation_view.entries], ["What can you do?", "I can answer grounded questions."])
        self.assertEqual(composer.busy_states, [True, False])
        self.assertEqual(status_panel.statuses[-1].completion_result, "Answer ready.")
        self.assertEqual(status_sink.messages[-1], "Answer ready")

    def test_submit_text_handles_backend_errors_without_crashing(self) -> None:
        controller, conversation_view, composer, status_panel, status_sink, _facade = _build_controller(
            error_on_submit=RuntimeError("backend offline")
        )
        controller.bind()

        controller.submit_text("Hello")

        self.assertEqual([entry.role for entry in conversation_view.entries[-2:]], ["user", "system"])
        self.assertEqual(conversation_view.entries[-1].entry_kind, "error")
        self.assertEqual(composer.busy_states, [True, False])
        self.assertEqual(status_panel.statuses[-1].runtime_state, "failed")
        self.assertEqual(status_sink.messages[-1], "Desktop shell error")

    def test_status_panel_toggle_updates_speech_state(self) -> None:
        snapshot_after_toggle = SessionSnapshotViewModel(
            status=StatusViewModel(
                interaction_mode="desktop_shell",
                runtime_state="idle",
                speech_enabled=True,
                speech_message="Speech output enabled.",
            )
        )
        controller, _conversation_view, _composer, status_panel, status_sink, facade = _build_controller(
            current_snapshot=snapshot_after_toggle
        )
        controller.bind()

        status_panel.speech_toggled.emit(True)

        self.assertEqual(facade.speech_enabled_changes, [True])
        self.assertTrue(status_panel.statuses[-1].speech_enabled)
        self.assertEqual(status_sink.messages[-1], "Speech output enabled.")

    def test_prompt_action_uses_same_submit_path_as_typed_input(self) -> None:
        snapshot_after_submit = SessionSnapshotViewModel(
            pending_prompt=PendingPromptViewModel(kind="confirmation", message="Approve command for Safari?"),
            status=StatusViewModel(interaction_mode="command", runtime_state="awaiting_confirmation", can_cancel=True),
        )
        controller, _conversation_view, _composer, _status_panel, status_sink, facade = _build_controller(
            initial_snapshot=snapshot_after_submit,
            current_snapshot=snapshot_after_submit,
        )
        controller.bind()

        controller.submit_prompt_action("confirm")

        self.assertEqual(facade.submitted_texts, ["confirm"])
        self.assertEqual(status_sink.messages[-1], "Waiting for confirmation")

    def test_cancel_control_routes_through_standard_submission_path(self) -> None:
        blocked_snapshot = SessionSnapshotViewModel(
            pending_prompt=PendingPromptViewModel(kind="clarification", message="Which app do you want?"),
            status=StatusViewModel(
                interaction_mode="command",
                runtime_state="awaiting_clarification",
                can_cancel=True,
            ),
        )
        controller, _conversation_view, _composer, status_panel, _status_sink, facade = _build_controller(
            initial_snapshot=blocked_snapshot,
            current_snapshot=blocked_snapshot,
        )
        controller.bind()

        status_panel.cancel_requested.emit()

        self.assertEqual(facade.submitted_texts, ["cancel"])

    def test_reset_control_uses_facade_reset_hook(self) -> None:
        initial_snapshot = SessionSnapshotViewModel(
            history=[TranscriptEntry(role="assistant", text="Earlier turn", entry_kind="result")],
            status=StatusViewModel(interaction_mode="question", runtime_state="idle"),
        )
        reset_snapshot = SessionSnapshotViewModel()
        controller, conversation_view, _composer, status_panel, status_sink, facade = _build_controller(
            initial_snapshot=initial_snapshot,
            reset_snapshot=reset_snapshot,
        )
        controller.bind()

        status_panel.reset_requested.emit()

        self.assertEqual(facade.reset_calls, 1)
        self.assertEqual(len(conversation_view.entries), 1)
        self.assertEqual(conversation_view.entries[0].text, "JARVIS shell is ready. Ask a question or enter a command.")
        self.assertEqual(status_panel.statuses[-1].runtime_state, "idle")
        self.assertEqual(status_sink.messages[-1], "New session ready")

    def test_retry_prompt_replays_last_reply_for_same_active_prompt(self) -> None:
        blocked_snapshot = SessionSnapshotViewModel(
            pending_prompt=PendingPromptViewModel(kind="confirmation", message="Approve command for Safari?"),
            status=StatusViewModel(
                interaction_mode="command",
                runtime_state="awaiting_confirmation",
                can_cancel=True,
            ),
        )
        controller, _conversation_view, _composer, status_panel, _status_sink, facade = _build_controller(
            initial_snapshot=blocked_snapshot,
            current_snapshot=blocked_snapshot,
        )
        controller.bind()

        controller.submit_prompt_action("confirm")
        status_panel.retry_requested.emit()

        self.assertEqual(facade.submitted_texts, ["confirm", "confirm"])
        self.assertTrue(status_panel.statuses[-1].retry_prompt_available)

    def test_voice_request_submits_captured_transcript_through_normal_path(self) -> None:
        snapshot_after_submit = SessionSnapshotViewModel(
            history=[
                TranscriptEntry(role="user", text="Open Safari", entry_kind="input"),
                TranscriptEntry(role="assistant", text="Ready.", entry_kind="result"),
            ],
            status=StatusViewModel(
                interaction_mode="command",
                runtime_state="completed",
                completion_result="Ready.",
            ),
        )
        controller, _conversation_view, composer, _status_panel, _status_sink, facade = _build_controller(
            current_snapshot=snapshot_after_submit,
        )
        controller.bind()

        composer.voice_requested.emit()

        self.assertEqual(facade.capture_voice_calls, 1)
        self.assertEqual(facade.submitted_texts, ["Open Safari"])
        self.assertEqual(composer.busy_states, [True, False])
        self.assertEqual(composer.voice_states[0][0], "listening")
        self.assertEqual(composer.voice_states[1][0], "routing")
        self.assertEqual(composer.voice_resets[-1], 'Last heard: "Open Safari"')

    def test_voice_request_surfaces_capture_error_without_submitting_text(self) -> None:
        controller, _conversation_view, composer, _status_panel, status_sink, facade = _build_controller(
            capture_voice_error=RuntimeError("microphone unavailable")
        )
        controller.bind()

        composer.voice_requested.emit()

        self.assertEqual(facade.capture_voice_calls, 1)
        self.assertEqual(facade.submitted_texts, [])
        self.assertEqual(composer.busy_states, [True, False])
        self.assertEqual(composer.voice_states[-1], ("error", "microphone unavailable"))
        self.assertEqual(status_sink.messages[-1], "microphone unavailable")


def _build_controller(
    *,
    initial_snapshot: SessionSnapshotViewModel | None = None,
    current_snapshot: SessionSnapshotViewModel | None = None,
    reset_snapshot: SessionSnapshotViewModel | None = None,
    error_on_submit: Exception | None = None,
    capture_voice_error: Exception | None = None,
) -> tuple[ConversationController, _FakeConversationView, _FakeComposer, _FakeStatusPanel, _FakeStatusSink, _FakeFacade]:
    facade = _FakeFacade(
        initial_snapshot=initial_snapshot or SessionSnapshotViewModel(),
        current_snapshot=current_snapshot or SessionSnapshotViewModel(),
        reset_snapshot=reset_snapshot or SessionSnapshotViewModel(),
        error_on_submit=error_on_submit,
        capture_voice_error=capture_voice_error,
    )
    conversation_view = _FakeConversationView()
    composer = _FakeComposer()
    status_panel = _FakeStatusPanel()
    status_sink = _FakeStatusSink()
    controller = ConversationController(
        engine_facade=facade,
        conversation_view=conversation_view,
        composer=composer,
        status_panel=status_panel,
        status_sink=status_sink,
    )
    return controller, conversation_view, composer, status_panel, status_sink, facade
