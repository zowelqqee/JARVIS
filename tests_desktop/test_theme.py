"""Tests for the desktop theme layer."""

from __future__ import annotations

import unittest

from desktop.shell.theme import build_stylesheet


class ThemeTests(unittest.TestCase):
    """Pure tests for desktop theme output."""

    def test_stylesheet_targets_main_shell_surfaces(self) -> None:
        stylesheet = build_stylesheet()

        self.assertIn("QMainWindow#mainWindow", stylesheet)
        self.assertIn("QWidget#shellRoot", stylesheet)
        self.assertIn("QWidget#conversationCard", stylesheet)
        self.assertIn("QWidget#composerCard", stylesheet)
        self.assertIn("QWidget#statusCard", stylesheet)

    def test_stylesheet_includes_accent_controls(self) -> None:
        stylesheet = build_stylesheet()

        self.assertIn("QPushButton#composerSendButton", stylesheet)
        self.assertIn("QPlainTextEdit#composerInput:focus", stylesheet)
        self.assertIn("#0f766e", stylesheet)


if __name__ == "__main__":
    unittest.main()
