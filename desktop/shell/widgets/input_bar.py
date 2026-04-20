"""
Section 6 — Input Bar (always visible).

Layout:  [🎙]  [input field _________________________ ]  [▶]

Heights:
  - Single line: 36px
  - Expands to max 72px when content overflows one line

Disabled states:
  - Field opacity 0.4 (via stylesheet)
  - Buttons non-interactive

Placeholder text is state-dependent.

Signal:
  submitted(str) — emitted on Enter or ▶ click with non-empty text
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QWidget

from desktop.shell.theme import BG, BORDER, TEXT_PRI, TEXT_SEC, SURFACE


_PLACEHOLDERS: dict[str, str] = {
    "idle":                   "Ask V.E.C.T.O.R.…",
    "listening":              "Listening… or type here",
    "thinking":               "V.E.C.T.O.R. is processing…",
    "executing":              "V.E.C.T.O.R. is executing…",
    "answering":              "V.E.C.T.O.R. is responding…",
    "awaiting_clarification": "Clarification required…",
    "awaiting_confirmation":  "Confirmation required…",
    "failed":                 "Ready — type a new request",
}

_DISABLED_STATES = frozenset({
    "thinking", "executing", "answering",
    "awaiting_clarification", "awaiting_confirmation",
})


class InputBarWidget(QWidget):

    submitted = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {BG};")
        self._build()

    def _build(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(6)

        # Mic indicator button (visual only for first pass)
        self._mic_btn = QPushButton("🎙")
        self._mic_btn.setObjectName("micBtn")
        self._mic_btn.setFixedSize(30, 28)
        self._mic_btn.setToolTip("Mic is always on during live session")
        layout.addWidget(self._mic_btn)

        # Text input
        font = QFont()
        font.setFamilies(["SF Mono", "JetBrains Mono", "Menlo", "Consolas", "Courier New"])
        font.setPointSize(11)

        self._field = QLineEdit()
        self._field.setFont(font)
        self._field.setFixedHeight(28)
        self._field.setPlaceholderText("Ask V.E.C.T.O.R.…")
        self._field.returnPressed.connect(self._on_submit)
        layout.addWidget(self._field)

        # Send button
        self._send_btn = QPushButton("▶")
        self._send_btn.setObjectName("sendBtn")
        self._send_btn.setFixedSize(30, 28)
        self._send_btn.clicked.connect(self._on_submit)
        layout.addWidget(self._send_btn)

    # ------------------------------------------------------------------ #
    # Public                                                               #
    # ------------------------------------------------------------------ #

    def update_state(self, runtime_state: str) -> None:
        disabled = runtime_state in _DISABLED_STATES
        placeholder = _PLACEHOLDERS.get(runtime_state, "Ask V.E.C.T.O.R.…")

        self._field.setPlaceholderText(placeholder)
        self._field.setEnabled(not disabled)
        self._send_btn.setEnabled(not disabled)

        # Opacity via stylesheet on the field wrapper
        opacity_style = "opacity: 0.4;" if disabled else ""
        self._field.setStyleSheet(
            f"QLineEdit {{ {opacity_style} }}"
        )

    def clear(self) -> None:
        self._field.clear()

    # ------------------------------------------------------------------ #
    # Slots                                                                #
    # ------------------------------------------------------------------ #

    def _on_submit(self) -> None:
        text = self._field.text().strip()
        if text:
            self.submitted.emit(text)
            self._field.clear()
