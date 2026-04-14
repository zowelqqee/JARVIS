"""
Section 5 — Last Exchange Strip (always visible).

Fixed 2-row display:
  ▸ {last user input}     (truncated, dimmed)
  ▸ {last JARVIS reply}   (truncated, dimmed)

If no exchange yet: single dimmed "No previous exchange." line.
Content never overflows — each line elides with … at max_width.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from desktop.shell.theme import BG, BORDER, TEXT_SEC


_MAX_CHARS = 68   # soft char limit before Python elision


def _elide(text: str, max_chars: int = _MAX_CHARS) -> str:
    if len(text) > max_chars:
        return text[:max_chars - 1] + "…"
    return text


class LastExchangeWidget(QWidget):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {BG};")
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(2)

        font = QFont()
        font.setFamilies(["SF Mono", "JetBrains Mono", "Menlo", "Consolas", "Courier New"])
        font.setPointSize(9)

        self._user_label = self._make_label(font)
        self._jarvis_label = self._make_label(font)

        layout.addWidget(self._user_label)
        layout.addWidget(self._jarvis_label)

        # Top separator
        self.setContentsMargins(0, 0, 0, 0)
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {BORDER};")

        # Insert separator at the top via the parent's layout — handled in panel_widget.py
        # Here we add it at the top of this widget's own layout
        layout.insertWidget(0, sep)

        self._set_no_exchange()

    def _make_label(self, font: QFont) -> QLabel:
        label = QLabel()
        label.setFont(font)
        label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        label.setStyleSheet(f"color: {TEXT_SEC}; background: transparent;")
        label.setWordWrap(False)
        return label

    def _set_no_exchange(self) -> None:
        self._user_label.setText("No previous exchange.")
        self._jarvis_label.setText("")
        self._jarvis_label.setVisible(False)

    def update_exchange(self, last_user: str | None, last_jarvis: str | None) -> None:
        if last_user is None and last_jarvis is None:
            self._set_no_exchange()
            return

        self._jarvis_label.setVisible(True)

        user_text = f"▸ You: {_elide(last_user)}" if last_user else "▸ You: —"
        self._user_label.setText(user_text)

        if last_jarvis:
            self._jarvis_label.setText(f"▸ JARVIS: {_elide(last_jarvis)}")
        else:
            self._jarvis_label.setText("▸ JARVIS: …")
