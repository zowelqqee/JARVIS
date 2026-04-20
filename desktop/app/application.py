"""QApplication setup with dark stylesheet and font configuration."""
from __future__ import annotations

from typing import Sequence

from PySide6.QtGui import QFont, QPalette, QColor
from PySide6.QtWidgets import QApplication

from desktop.shell.theme import DARK_STYLESHEET, BG, TEXT_PRI, SURFACE, BORDER


def build_application(argv: Sequence[str] | None = None) -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(list(argv or []))

    app.setApplicationName("V.E.C.T.O.R.")
    app.setOrganizationName("V.E.C.T.O.R.")

    # Monospace font hierarchy — same across all platforms
    font = QFont()
    font.setFamilies(["SF Mono", "JetBrains Mono", "Menlo", "Consolas", "Courier New"])
    font.setPointSize(11)
    app.setFont(font)

    # Dark palette so Qt widgets default dark even without full stylesheet
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BG))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT_PRI))
    palette.setColor(QPalette.ColorRole.Base, QColor(SURFACE))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(SURFACE))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT_PRI))
    palette.setColor(QPalette.ColorRole.Button, QColor(SURFACE))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT_PRI))
    app.setPalette(palette)

    app.setStyleSheet(DARK_STYLESHEET)

    return app
