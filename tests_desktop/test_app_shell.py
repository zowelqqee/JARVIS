"""Smoke tests for the desktop application shell."""

from __future__ import annotations

import importlib.util
import unittest


_PYSIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None


@unittest.skipUnless(_PYSIDE6_AVAILABLE, "PySide6 is not installed in the active environment.")
class DesktopShellTests(unittest.TestCase):
    """Basic desktop-shell smoke coverage."""

    def test_main_window_defaults(self) -> None:
        from desktop.app.application import build_application
        from desktop.shell.main_window import MainWindow

        app = build_application([])
        self.addCleanup(app.quit)

        window = MainWindow()

        self.assertEqual(window.windowTitle(), "JARVIS")
        self.assertGreaterEqual(window.minimumWidth(), 900)
        self.assertGreaterEqual(window.minimumHeight(), 600)
        self.assertEqual(window.statusBar().currentMessage(), "JARVIS shell connected")
