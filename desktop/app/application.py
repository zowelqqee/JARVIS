"""Application bootstrap for the JARVIS desktop shell."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtWidgets import QApplication

from desktop.shell.theme import apply_app_theme
from desktop.shell.main_window import MainWindow


def build_application(argv: Sequence[str] | None = None) -> QApplication:
    """Create and configure the QApplication instance."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(list(argv or []))
    app.setApplicationName("JARVIS")
    app.setOrganizationName("JARVIS")
    app.setOrganizationDomain("jarvis.local")
    apply_app_theme(app)
    return app


def run_desktop_application(argv: Sequence[str] | None = None) -> int:
    """Start the desktop shell and return the Qt exit code."""
    app = build_application(argv)
    window = MainWindow()
    window.show()
    return app.exec()
