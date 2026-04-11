"""Status summary widget for the desktop shell."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFormLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from desktop.backend.view_models import StatusViewModel


class StatusPanel(QWidget):
    """Compact runtime status surface for the desktop shell."""

    speech_toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build()
        self.set_status(StatusViewModel())

    def set_status(self, status: StatusViewModel) -> None:
        """Render the current backend-derived status snapshot."""
        self._set_value(self._mode_value, status.interaction_mode or "idle")
        self._set_value(self._state_value, status.runtime_state or "idle")
        self._set_value(self._command_value, status.command_summary or "No active command")
        self._set_value(self._step_value, status.current_step or "No active step")
        self._set_value(self._blocked_value, status.blocked_reason or "Nothing pending")
        self._set_value(self._result_value, status.completion_result or status.failure_message or "No result yet")
        self._set_value(self._speech_value, "On" if status.speech_enabled else "Off")
        self._set_value(
            self._speech_backend_value,
            status.speech_backend
            or ("Unavailable" if status.speech_available is False else "Not initialized"),
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

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        title = QLabel("Status", self)
        title.setObjectName("statusPanelTitle")

        subtitle = QLabel("Current interaction and runtime summary.", self)
        subtitle.setObjectName("statusPanelSubtitle")
        subtitle.setWordWrap(True)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(10)

        self._mode_value = QLabel(self)
        self._state_value = QLabel(self)
        self._command_value = QLabel(self)
        self._step_value = QLabel(self)
        self._blocked_value = QLabel(self)
        self._result_value = QLabel(self)
        self._speech_value = QLabel(self)
        self._speech_backend_value = QLabel(self)
        self._speech_message_value = QLabel(self)

        for label in (
            self._mode_value,
            self._state_value,
            self._command_value,
            self._step_value,
            self._blocked_value,
            self._result_value,
            self._speech_value,
            self._speech_backend_value,
            self._speech_message_value,
        ):
            label.setWordWrap(True)

        form.addRow("Mode", self._mode_value)
        form.addRow("Runtime", self._state_value)
        form.addRow("Command", self._command_value)
        form.addRow("Step", self._step_value)
        form.addRow("Blocked", self._blocked_value)
        form.addRow("Result", self._result_value)
        form.addRow("Speech", self._speech_value)
        form.addRow("Audio Backend", self._speech_backend_value)
        form.addRow("Audio Status", self._speech_message_value)

        self._speech_toggle_button = QPushButton("Enable Speech", self)
        self._speech_toggle_button.setObjectName("speechToggleButton")
        self._speech_toggle_button.setCheckable(True)
        self._speech_toggle_button.toggled.connect(self.speech_toggled.emit)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(form)
        layout.addWidget(self._speech_toggle_button)
        layout.addStretch(1)

    @staticmethod
    def _set_value(label: QLabel, value: str) -> None:
        label.setText(str(value).strip())
