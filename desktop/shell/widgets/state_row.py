"""
Section 2 — State Row (always visible, 28px fixed height).

Layout:  [MODE CHIP]  [RUNTIME STATE CHIP]

Both chips are read-only labels with coloured backgrounds.
Mode values:  COMMAND | QUESTION | VOICE | IDLE | ERROR
Runtime values: IDLE | LISTENING | PARSING | EXECUTING | WAITING |
                ANSWERING | ERROR
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from desktop.shell.theme import (
    BG, SURFACE, BORDER, TEXT_PRI, TEXT_SEC,
    CHIP_IDLE, CHIP_ACTIVE, CHIP_WAITING, CHIP_ERROR,
    state_chip_color,
)


_MODE_DISPLAY: dict[str, str] = {
    "COMMAND":  "CMD",
    "QUESTION": "QRY",
    "VOICE":    "VOICE",
    "IDLE":     "IDLE",
    "ERROR":    "ERROR",
}

_RUNTIME_DISPLAY: dict[str, str] = {
    "idle":                    "IDLE",
    "listening":               "LISTENING",
    "thinking":                "PARSING",
    "executing":               "EXECUTING",
    "answering":               "ANSWERING",
    "awaiting_clarification":  "WAITING",
    "awaiting_confirmation":   "WAITING",
    "failed":                  "ERROR",
}


def _chip_style(bg: str) -> str:
    return (
        f"background-color: {bg};"
        f"color: {TEXT_PRI};"
        f"border-radius: 4px;"
        f"padding: 1px 6px;"
        f"font-size: 9px;"
        f"letter-spacing: 0.5px;"
    )


class StateRowWidget(QWidget):
    HEIGHT = 28

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(self.HEIGHT)
        self.setStyleSheet(f"background-color: {BG};")
        self._build()

    def _build(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        chip_font = QFont()
        chip_font.setPointSize(9)
        chip_font.setBold(True)

        self._mode_chip = QLabel("IDLE")
        self._mode_chip.setFont(chip_font)
        self._mode_chip.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self._mode_chip.setStyleSheet(_chip_style(CHIP_IDLE))

        self._state_chip = QLabel("IDLE")
        self._state_chip.setFont(chip_font)
        self._state_chip.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self._state_chip.setStyleSheet(_chip_style(CHIP_IDLE))

        layout.addWidget(self._mode_chip)
        layout.addWidget(self._state_chip)
        layout.addStretch(1)

    def update_state(self, mode: str, runtime_state: str) -> None:
        mode_text = _MODE_DISPLAY.get(mode, mode)
        state_text = _RUNTIME_DISPLAY.get(runtime_state, runtime_state.upper())

        # Mode chip: dimmed unless actively running a command/query
        mode_color = (
            CHIP_ACTIVE  if mode in ("COMMAND", "QUESTION", "VOICE")
            else CHIP_ERROR if mode == "ERROR"
            else CHIP_IDLE
        )

        state_color = state_chip_color(runtime_state)

        self._mode_chip.setText(mode_text)
        self._mode_chip.setStyleSheet(_chip_style(mode_color))

        self._state_chip.setText(state_text)
        self._state_chip.setStyleSheet(_chip_style(state_color))
