"""
Section 1 — Titlebar (always visible, 32px fixed height).

Layout:  [●] V.E.C.T.O.R.         [–] [×]

The ● dot colour reflects runtime_state.
Drag region: the full titlebar width (left of the buttons).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from desktop.shell.theme import dot_color, SURFACE, BORDER, TEXT_PRI


class TitlebarWidget(QWidget):
    HEIGHT = 32

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(self.HEIGHT)
        self._drag_offset: QPoint | None = None
        self._build()

    # ------------------------------------------------------------------ #
    # Build                                                                #
    # ------------------------------------------------------------------ #

    def _build(self) -> None:
        self.setStyleSheet(
            f"background-color: {SURFACE};"
            f"border-bottom: 1px solid {BORDER};"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 6, 0)
        layout.setSpacing(4)

        # ● dot indicator
        self._dot = QLabel("●")
        dot_font = QFont()
        dot_font.setPointSize(10)
        self._dot.setFont(dot_font)
        self._dot.setFixedWidth(14)
        self._dot.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._dot)

        # Title
        title = QLabel("V.E.C.T.O.R.")
        title_font = QFont()
        title_font.setPointSize(11)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        title.setStyleSheet(f"color: {TEXT_PRI};")
        layout.addWidget(title)

        layout.addStretch(1)  # pushes buttons to the right

        # Minimise button
        self._min_btn = QPushButton("−")
        self._min_btn.setObjectName("minBtn")
        self._min_btn.setFixedSize(24, 20)
        self._min_btn.clicked.connect(lambda: self.window().showMinimized())
        layout.addWidget(self._min_btn)

        # Close button
        self._close_btn = QPushButton("×")
        self._close_btn.setObjectName("closeBtn")
        self._close_btn.setFixedSize(24, 20)
        self._close_btn.clicked.connect(lambda: self.window().close())
        layout.addWidget(self._close_btn)

        self._update_dot("idle")

    # ------------------------------------------------------------------ #
    # Public                                                               #
    # ------------------------------------------------------------------ #

    def update_state(self, runtime_state: str) -> None:
        self._update_dot(runtime_state)

    # ------------------------------------------------------------------ #
    # Drag support                                                         #
    # ------------------------------------------------------------------ #

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            )

    def mouseMoveEvent(self, event) -> None:
        if (
            event.buttons() & Qt.MouseButton.LeftButton
            and self._drag_offset is not None
        ):
            self.window().move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_offset = None

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _update_dot(self, runtime_state: str) -> None:
        color = dot_color(runtime_state)
        self._dot.setStyleSheet(f"color: {color};")
