"""Unified voice-first composer widget for the desktop shell."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ComposerWidget(QWidget):
    """Voice-first composer that keeps text input available in the same surface."""

    submitted = Signal(str)
    voice_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._busy = False
        self._voice_available = sys.platform == "darwin"
        self._voice_state = "ready" if self._voice_available else "unavailable"
        self._voice_detail = _default_voice_detail(self._voice_state, available=self._voice_available)
        self._build()
        self.reset_voice_state()

    @property
    def input_field(self) -> QPlainTextEdit:
        """Expose the text editor for tests and future controllers."""
        return self._input_field

    @property
    def send_button(self) -> QPushButton:
        """Expose the text submit button for tests and future controllers."""
        return self._send_button

    @property
    def voice_button(self) -> QPushButton:
        """Expose the primary voice-action button for tests and future controllers."""
        return self._voice_button

    def text(self) -> str:
        """Return the normalized composer text."""
        return str(self._input_field.toPlainText()).strip()

    def clear(self) -> None:
        """Clear the current composer text."""
        self._input_field.clear()
        self._sync_controls()

    def set_busy(self, busy: bool) -> None:
        """Enable or disable the composer during active listening or processing."""
        self._busy = bool(busy)
        self._input_field.setReadOnly(self._busy)
        self._sync_controls()

    def set_voice_state(self, state: str, *, detail: str | None = None) -> None:
        """Render one explicit voice-input state inside the composer."""
        normalized_state = str(state or "").strip().lower() or ("ready" if self._voice_available else "unavailable")
        if normalized_state not in {"ready", "listening", "routing", "error", "unavailable"}:
            normalized_state = "ready" if self._voice_available else "unavailable"
        self._voice_state = normalized_state
        self._voice_detail = str(detail or "").strip() or _default_voice_detail(
            normalized_state,
            available=self._voice_available,
        )
        self._voice_state_pill.setText(_voice_state_label(normalized_state))
        self._voice_state_pill.setProperty("voiceState", normalized_state)
        self._voice_button.setText(_voice_button_label(normalized_state, available=self._voice_available))
        self._voice_detail_label.setText(self._voice_detail)
        _refresh_widget_style(self._voice_state_pill)
        _refresh_widget_style(self._voice_button)
        self._sync_controls()

    def reset_voice_state(self, *, detail: str | None = None) -> None:
        """Return the composer voice lane to its default ready or unavailable state."""
        default_state = "ready" if self._voice_available else "unavailable"
        self.set_voice_state(default_state, detail=detail)

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Speak or Type", self)
        title.setObjectName("composerTitle")

        subtitle = QLabel(
            "Voice is the default action here. Text stays available in the same composer and follows the same supervised shell path.",
            self,
        )
        subtitle.setObjectName("composerSubtitle")
        subtitle.setWordWrap(True)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(12)

        voice_panel = QWidget(self)
        voice_panel.setObjectName("composerVoicePanel")
        voice_layout = QVBoxLayout(voice_panel)
        voice_layout.setContentsMargins(16, 16, 16, 16)
        voice_layout.setSpacing(10)

        voice_header = QLabel("Voice Input", voice_panel)
        voice_header.setObjectName("composerSectionLabel")

        self._voice_state_pill = QLabel(voice_panel)
        self._voice_state_pill.setObjectName("composerVoiceStatePill")

        self._voice_detail_label = QLabel(voice_panel)
        self._voice_detail_label.setObjectName("composerVoiceDetail")
        self._voice_detail_label.setWordWrap(True)

        self._voice_support_label = QLabel("One spoken request at a time. No background listening.", voice_panel)
        self._voice_support_label.setObjectName("composerSupportText")
        self._voice_support_label.setWordWrap(True)

        self._voice_button = QPushButton(voice_panel)
        self._voice_button.setObjectName("composerVoiceButton")
        self._voice_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._voice_button.clicked.connect(self.voice_requested.emit)

        voice_layout.addWidget(voice_header)
        voice_layout.addWidget(self._voice_state_pill, alignment=Qt.AlignmentFlag.AlignLeft)
        voice_layout.addWidget(self._voice_detail_label)
        voice_layout.addWidget(self._voice_support_label)
        voice_layout.addStretch(1)
        voice_layout.addWidget(self._voice_button)

        divider = QLabel("OR", self)
        divider.setObjectName("composerDivider")
        divider.setAlignment(Qt.AlignmentFlag.AlignCenter)

        text_panel = QWidget(self)
        text_panel.setObjectName("composerTextPanel")
        text_layout = QVBoxLayout(text_panel)
        text_layout.setContentsMargins(16, 16, 16, 16)
        text_layout.setSpacing(10)

        text_header = QLabel("Text Input", text_panel)
        text_header.setObjectName("composerSectionLabel")

        text_hint = QLabel("Type a command or question. Ctrl+Enter submits.", text_panel)
        text_hint.setObjectName("composerTextHint")
        text_hint.setWordWrap(True)

        self._input_field = _ComposerTextEdit(text_panel)
        self._input_field.setObjectName("composerInput")
        self._input_field.setPlaceholderText("Type a command or question...")
        self._input_field.setMinimumHeight(104)
        self._input_field.textChanged.connect(self._sync_controls)
        self._input_field.submit_requested.connect(self._submit_current_text)

        self._send_button = QPushButton("Send Text", text_panel)
        self._send_button.setObjectName("composerSendButton")
        self._send_button.clicked.connect(self._submit_current_text)

        send_row = QHBoxLayout()
        send_row.setContentsMargins(0, 0, 0, 0)
        send_row.addStretch(1)
        send_row.addWidget(self._send_button)

        shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        shortcut.activated.connect(self._submit_current_text)
        shortcut_alt = QShortcut(QKeySequence("Ctrl+Enter"), self)
        shortcut_alt.activated.connect(self._submit_current_text)

        text_layout.addWidget(text_header)
        text_layout.addWidget(text_hint)
        text_layout.addWidget(self._input_field)
        text_layout.addLayout(send_row)

        body.addWidget(voice_panel, stretch=3)
        body.addWidget(divider, stretch=0)
        body.addWidget(text_panel, stretch=4)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(body)

        self._sync_controls()

    def _submit_current_text(self) -> None:
        text = self.text()
        if not text:
            return
        self.submitted.emit(text)
        self.clear()

    def _sync_controls(self) -> None:
        self._send_button.setEnabled(bool(self.text()) and not self._input_field.isReadOnly())
        voice_enabled = (
            self._voice_available
            and not self._busy
            and self._voice_state not in {"listening", "routing", "unavailable"}
        )
        self._voice_button.setEnabled(voice_enabled)


class _ComposerTextEdit(QPlainTextEdit):
    """Text edit that supports explicit submit gestures."""

    submit_requested = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter} and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.submit_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


def _default_voice_detail(state: str, *, available: bool) -> str:
    if not available or state == "unavailable":
        return "Voice input is available only on macOS."
    if state == "listening":
        return "Listening for one spoken request."
    if state == "routing":
        return "Submitting the captured request through the supervised shell."
    if state == "error":
        return "Voice input could not complete. Try again or type the request below."
    return "Click Listen to capture one spoken request on macOS."


def _voice_state_label(state: str) -> str:
    return {
        "ready": "Ready",
        "listening": "Listening",
        "routing": "Submitting",
        "error": "Issue",
        "unavailable": "Unavailable",
    }.get(str(state or "").strip().lower(), "Ready")


def _voice_button_label(state: str, *, available: bool) -> str:
    if not available or state == "unavailable":
        return "Voice Unavailable"
    if state == "listening":
        return "Listening..."
    if state == "routing":
        return "Submitting..."
    if state == "error":
        return "Listen Again"
    return "Start Listening"


def _refresh_widget_style(widget: QWidget) -> None:
    style = widget.style()
    if style is None:
        return
    style.unpolish(widget)
    style.polish(widget)
    widget.update()
