"""
Section 3 — Current Action Display (always visible).

Shows what V.E.C.T.O.R. is doing right now.
Height: min 48px, expands to 3 lines max.
Text truncates at 3 lines; no scrolling within this section.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from desktop.shell.theme import BG, BORDER, TEXT_PRI, TEXT_SEC, ACCENT


_MIN_HEIGHT = 48
_MAX_LINES  = 3


def _elide_to_lines(text: str, fm: QFontMetrics, max_width: int, max_lines: int) -> str:
    """Wrap text and truncate at max_lines, appending … on the last line."""
    words = text.split()
    lines: list[str] = []
    current = ""

    for word in words:
        candidate = f"{current} {word}".strip() if current else word
        if fm.horizontalAdvance(candidate) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            if len(lines) >= max_lines:
                break
            current = word

    if current and len(lines) < max_lines:
        lines.append(current)

    if len(lines) == max_lines and (
        fm.horizontalAdvance(lines[-1]) > max_width
        or len(" ".join(words)) > len(" ".join(lines))
    ):
        last = lines[-1]
        while last and fm.horizontalAdvance(last + "…") > max_width:
            last = last[:-1]
        lines[-1] = last + "…"

    return "\n".join(lines)


class CurrentActionWidget(QWidget):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(_MIN_HEIGHT)
        self.setStyleSheet(f"background-color: {BG};")
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(0)

        font = QFont()
        font.setFamilies(["SF Mono", "JetBrains Mono", "Menlo", "Consolas", "Courier New"])
        font.setPointSize(12)
        font.setBold(True)

        self._label = QLabel("Ready.")
        self._label.setFont(font)
        self._label.setWordWrap(True)
        self._label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._label.setStyleSheet(f"color: {TEXT_PRI};")

        # Constrain to max 3 lines
        fm = QFontMetrics(font)
        line_h = fm.height()
        self._label.setMaximumHeight(line_h * _MAX_LINES + 4)

        layout.addWidget(self._label)

        # Thin separator at bottom
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {BORDER};")
        layout.addWidget(sep)

    def update_text(self, text: str, runtime_state: str) -> None:
        # Dim the text when idle
        color = TEXT_SEC if runtime_state == "idle" else TEXT_PRI
        self._label.setStyleSheet(f"color: {color};")
        self._label.setText(text or "Ready.")
