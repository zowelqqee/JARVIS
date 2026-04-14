"""
Section 4 — Prompt Zone (conditional).

Rendered ONLY when pending_prompt is not None.
Removed from widget tree when dismissed — not hidden, not zero-height.

Confirmation kind:
  [message text]
  [CONFIRM]  [CANCEL]

Clarification kind:
  [message text]
  [text input field]  [SEND]
  [CANCEL]

The text input receives focus automatically when the zone appears.
A 2px left border in accent colour draws attention to the section.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from desktop.shell.theme import BG, BORDER, ACCENT, TEXT_PRI, TEXT_SEC, SURFACE
from desktop.backend.view_models import PendingPrompt


class PromptZoneWidget(QWidget):
    """
    Emits one of three signals when the user responds.
    Parent (PanelWidget) must connect these before inserting into layout.
    """

    confirmed                = Signal()        # confirmation accepted
    cancelled                = Signal()        # any prompt dismissed
    clarification_submitted  = Signal(str)     # clarification text sent

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build()

    # ------------------------------------------------------------------ #
    # Build                                                                #
    # ------------------------------------------------------------------ #

    def _build(self) -> None:
        # Left accent border via inner margin
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 2px accent stripe
        stripe = QWidget()
        stripe.setFixedWidth(2)
        stripe.setStyleSheet(f"background-color: {ACCENT};")
        outer.addWidget(stripe)

        # Content area
        content = QWidget()
        content.setStyleSheet(f"background-color: {SURFACE}; border: none;")
        outer.addWidget(content)

        self._inner = QVBoxLayout(content)
        self._inner.setContentsMargins(10, 8, 10, 8)
        self._inner.setSpacing(6)

        # Message label (populated by set_prompt)
        self._msg_label = QLabel()
        msg_font = QFont()
        msg_font.setPointSize(11)
        self._msg_label.setFont(msg_font)
        self._msg_label.setWordWrap(True)
        self._msg_label.setStyleSheet(f"color: {TEXT_PRI}; background: transparent;")
        self._inner.addWidget(self._msg_label)

        # Clarification input (hidden by default)
        self._clari_input = QLineEdit()
        self._clari_input.setPlaceholderText("Type your answer…")
        self._clari_input.setVisible(False)
        self._clari_input.returnPressed.connect(self._on_send)
        self._inner.addWidget(self._clari_input)

        # Button row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        btn_row.setContentsMargins(0, 0, 0, 0)

        self._confirm_btn = QPushButton("CONFIRM")
        self._confirm_btn.setObjectName("confirmBtn")
        self._confirm_btn.setFixedHeight(28)
        self._confirm_btn.clicked.connect(self._on_confirm)

        self._send_btn = QPushButton("SEND")
        self._send_btn.setObjectName("sendBtn")
        self._send_btn.setFixedHeight(28)
        self._send_btn.setVisible(False)
        self._send_btn.clicked.connect(self._on_send)

        self._cancel_btn = QPushButton("CANCEL")
        self._cancel_btn.setFixedHeight(28)
        self._cancel_btn.clicked.connect(self._on_cancel)

        btn_row.addWidget(self._confirm_btn)
        btn_row.addWidget(self._send_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self._cancel_btn)

        self._inner.addLayout(btn_row)

        # Bottom separator
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {BORDER};")
        outer.layout()   # noop — just ensure sep is added via inner layout
        self._inner.addWidget(sep)

    # ------------------------------------------------------------------ #
    # Public                                                               #
    # ------------------------------------------------------------------ #

    def set_prompt(self, prompt: PendingPrompt) -> None:
        self._msg_label.setText(prompt.message)

        if prompt.kind == "confirmation":
            self._confirm_btn.setVisible(True)
            self._send_btn.setVisible(False)
            self._clari_input.setVisible(False)
        else:  # clarification
            self._confirm_btn.setVisible(False)
            self._send_btn.setVisible(True)
            self._clari_input.setVisible(True)
            self._clari_input.clear()
            # Focus the input so user can type immediately
            self._clari_input.setFocus(Qt.FocusReason.OtherFocusReason)

    # ------------------------------------------------------------------ #
    # Slots                                                                #
    # ------------------------------------------------------------------ #

    def _on_confirm(self) -> None:
        self.confirmed.emit()

    def _on_cancel(self) -> None:
        self.cancelled.emit()

    def _on_send(self) -> None:
        text = self._clari_input.text().strip()
        if text:
            self.clarification_submitted.emit(text)
