"""Input composer widget for the desktop shell."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import QLabel, QPushButton, QPlainTextEdit, QVBoxLayout, QWidget


class ComposerWidget(QWidget):
    """Multi-line text composer with an explicit submit action."""

    submitted = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build()

    @property
    def input_field(self) -> QPlainTextEdit:
        """Expose the text editor for tests and future controllers."""
        return self._input_field

    @property
    def send_button(self) -> QPushButton:
        """Expose the send button for tests and future controllers."""
        return self._send_button

    def text(self) -> str:
        """Return the normalized composer text."""
        return str(self._input_field.toPlainText()).strip()

    def clear(self) -> None:
        """Clear the current composer text."""
        self._input_field.clear()
        self._sync_submit_state()

    def set_busy(self, busy: bool) -> None:
        """Enable or disable the composer during active processing."""
        self._input_field.setReadOnly(bool(busy))
        self._send_button.setEnabled((not busy) and bool(self.text()))

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        title = QLabel("Ask JARVIS", self)
        title.setObjectName("composerTitle")

        subtitle = QLabel("Write a request and press Send. Ctrl+Enter submits.", self)
        subtitle.setObjectName("composerSubtitle")
        subtitle.setWordWrap(True)

        self._input_field = _ComposerTextEdit(self)
        self._input_field.setObjectName("composerInput")
        self._input_field.setPlaceholderText("Type a command or question...")
        self._input_field.setMinimumHeight(96)
        self._input_field.textChanged.connect(self._sync_submit_state)
        self._input_field.submit_requested.connect(self._submit_current_text)

        self._send_button = QPushButton("Send", self)
        self._send_button.setObjectName("composerSendButton")
        self._send_button.clicked.connect(self._submit_current_text)

        shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        shortcut.activated.connect(self._submit_current_text)
        shortcut_alt = QShortcut(QKeySequence("Ctrl+Enter"), self)
        shortcut_alt.activated.connect(self._submit_current_text)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self._input_field)
        layout.addWidget(self._send_button, alignment=Qt.AlignmentFlag.AlignRight)

        self._sync_submit_state()

    def _submit_current_text(self) -> None:
        text = self.text()
        if not text:
            return
        self.submitted.emit(text)
        self.clear()

    def _sync_submit_state(self) -> None:
        self._send_button.setEnabled(bool(self.text()) and not self._input_field.isReadOnly())


class _ComposerTextEdit(QPlainTextEdit):
    """Text edit that supports explicit submit gestures."""

    submit_requested = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter} and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.submit_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)
