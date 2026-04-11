"""Status summary widget for the desktop shell."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from desktop.backend.view_models import StatusViewModel


class StatusPanel(QWidget):
    """Compact runtime status surface for the desktop shell."""

    speech_toggled = Signal(bool)
    cancel_requested = Signal()
    reset_requested = Signal()
    retry_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build()
        self.set_status(StatusViewModel())

    def set_status(self, status: StatusViewModel) -> None:
        """Render the current backend-derived status snapshot."""
        self._set_value(self._mode_value, _humanize_mode(status.interaction_mode))
        self._set_value(self._state_value, _humanize_state(status.runtime_state))
        self._set_value(self._command_value, status.command_summary or "No active request")
        self._set_value(self._step_value, status.current_step or "No step running")
        self._set_value(self._completed_value, _completed_summary(status))
        self._set_value(self._blocked_value, status.blocked_reason or "Nothing waiting")
        self._set_value(self._next_value, status.next_required_action or status.next_step_hint or _default_next_hint(status))
        self._set_value(self._result_value, status.completion_result or status.failure_message or "No result yet")
        self._set_value(self._controls_value, _controls_summary(status))
        self._set_value(self._speech_value, _speech_summary(status))
        self._set_value(
            self._speech_backend_value,
            status.speech_backend
            or ("Unavailable" if status.speech_available is False else "Ready when enabled"),
        )
        self._set_value(
            self._speech_message_value,
            status.speech_message
            or ("Speech output is off." if not status.speech_enabled else "Speech is ready."),
        )
        self._speech_toggle_button.blockSignals(True)
        self._speech_toggle_button.setChecked(bool(status.speech_enabled))
        self._speech_toggle_button.setText("Disable Speech" if status.speech_enabled else "Enable Speech")
        self._speech_toggle_button.blockSignals(False)
        self._cancel_button.setEnabled(bool(status.can_cancel))
        self._retry_button.setEnabled(bool(status.retry_prompt_available))
        self._reset_button.setEnabled(True)

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Shell Status", self)
        title.setObjectName("statusPanelTitle")

        subtitle = QLabel("Live state from the supervised runtime and current shell session.", self)
        subtitle.setObjectName("statusPanelSubtitle")
        subtitle.setWordWrap(True)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(10)

        self._mode_value = QLabel(self)
        self._state_value = QLabel(self)
        self._command_value = QLabel(self)
        self._step_value = QLabel(self)
        self._completed_value = QLabel(self)
        self._blocked_value = QLabel(self)
        self._next_value = QLabel(self)
        self._result_value = QLabel(self)
        self._controls_value = QLabel(self)
        self._speech_value = QLabel(self)
        self._speech_backend_value = QLabel(self)
        self._speech_message_value = QLabel(self)

        for label in (
            self._mode_value,
            self._state_value,
            self._command_value,
            self._step_value,
            self._completed_value,
            self._blocked_value,
            self._next_value,
            self._result_value,
            self._controls_value,
            self._speech_value,
            self._speech_backend_value,
            self._speech_message_value,
        ):
            label.setWordWrap(True)
            label.setObjectName("statusPanelValue")

        form.addRow("Interaction", self._mode_value)
        form.addRow("State", self._state_value)
        form.addRow("Active Request", self._command_value)
        form.addRow("Current Step", self._step_value)
        form.addRow("Completed", self._completed_value)
        form.addRow("Waiting On", self._blocked_value)
        form.addRow("Required Action", self._next_value)
        form.addRow("Latest Result", self._result_value)
        form.addRow("Controls", self._controls_value)
        form.addRow("Speech", self._speech_value)
        form.addRow("Voice Backend", self._speech_backend_value)
        form.addRow("Voice Status", self._speech_message_value)

        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)

        self._cancel_button = QPushButton("Cancel Flow", self)
        self._cancel_button.setObjectName("statusActionButton")
        self._cancel_button.clicked.connect(self.cancel_requested.emit)

        self._retry_button = QPushButton("Retry Prompt", self)
        self._retry_button.setObjectName("statusActionButton")
        self._retry_button.clicked.connect(self.retry_requested.emit)

        self._reset_button = QPushButton("New Session", self)
        self._reset_button.setObjectName("statusActionButton")
        self._reset_button.clicked.connect(self.reset_requested.emit)

        controls_layout.addWidget(self._cancel_button)
        controls_layout.addWidget(self._retry_button)
        controls_layout.addWidget(self._reset_button)

        self._speech_toggle_button = QPushButton("Enable Speech", self)
        self._speech_toggle_button.setObjectName("speechToggleButton")
        self._speech_toggle_button.setCheckable(True)
        self._speech_toggle_button.toggled.connect(self.speech_toggled.emit)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(form)
        layout.addLayout(controls_layout)
        layout.addWidget(self._speech_toggle_button)
        layout.addStretch(1)

    @staticmethod
    def _set_value(label: QLabel, value: str) -> None:
        label.setText(str(value).strip())


def _humanize_mode(mode: str | None) -> str:
    normalized = str(mode or "").strip().replace("_", " ")
    if not normalized:
        return "Idle"
    mapped = {
        "question": "Question",
        "command": "Command",
        "clarification": "Clarification",
        "desktop shell": "Shell",
        "desktop_error": "Desktop Error",
    }
    return mapped.get(normalized, " ".join(word.capitalize() for word in normalized.split()))


def _humanize_state(state: str | None) -> str:
    normalized = str(state or "").strip().replace("_", " ")
    if not normalized:
        return "Ready"
    if normalized == "idle":
        return "Ready"
    return " ".join(word.capitalize() for word in normalized.split())


def _completed_summary(status: StatusViewModel) -> str:
    completed = tuple(status.completed_steps or ())
    if not completed:
        if str(status.runtime_state or "").strip() == "completed":
            return "Completed"
        return "Nothing completed yet"
    if len(completed) == 1:
        return completed[0]
    return f"{len(completed)} steps completed"


def _default_next_hint(status: StatusViewModel) -> str:
    runtime_state = str(status.runtime_state or "").strip()
    if runtime_state in {"awaiting_confirmation", "awaiting_clarification"}:
        return "Reply in the shell feed"
    if runtime_state in {"executing", "planning", "validating", "parsing"}:
        return "Follow the runtime feed"
    return "Nothing needed"


def _speech_summary(status: StatusViewModel) -> str:
    if status.speech_enabled:
        return "On"
    if status.speech_available is False:
        return "Unavailable"
    return "Off"


def _controls_summary(status: StatusViewModel) -> str:
    explicit_controls = tuple(str(control).strip() for control in status.available_controls if str(control).strip())
    if explicit_controls:
        return ", ".join(explicit_controls)
    controls = ["New Session", "Speech Toggle"]
    if status.can_cancel:
        controls.insert(0, "Cancel Flow")
    if status.retry_prompt_available:
        controls.insert(1 if status.can_cancel else 0, "Retry Prompt")
    return ", ".join(controls)
