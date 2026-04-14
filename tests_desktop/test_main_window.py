"""UI-shell tests for the desktop main window."""

from __future__ import annotations

import importlib.util
import sys
import unittest


_PYSIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None


@unittest.skipUnless(_PYSIDE6_AVAILABLE, "PySide6 is not installed in the active environment.")
class MainWindowUiTests(unittest.TestCase):
    """Smoke coverage for the unstyled UI layer."""

    def test_main_window_exposes_shell_widgets(self) -> None:
        from desktop.app.application import build_application
        from desktop.shell.main_window import MainWindow
        from PySide6.QtWidgets import QLabel

        app = build_application([])
        self.addCleanup(app.quit)

        window = MainWindow()

        self.assertIsNotNone(window.conversation_view)
        self.assertIsNotNone(window.composer)
        self.assertIsNotNone(window.status_panel)
        self.assertIsNotNone(window.controller)
        self.assertEqual(window.conversation_view.list_widget.count(), 1)
        expected_voice_label = "Start Listening" if sys.platform == "darwin" else "Voice Unavailable"
        self.assertEqual(window.composer.voice_button.text(), expected_voice_label)
        self.assertEqual(window.composer.send_button.text(), "Send Text")
        self.assertEqual(window.status_panel._speech_toggle_button.text(), "Enable Speech")
        self.assertEqual(window.status_panel._cancel_button.text(), "Cancel Flow")
        self.assertEqual(window.status_panel._retry_button.text(), "Retry Prompt")
        self.assertEqual(window.status_panel._reset_button.text(), "New Session")
        root_layout = window.centralWidget().layout()
        left_column = root_layout.itemAt(0).layout()
        self.assertIs(left_column.itemAt(0).widget(), window.composer)
        self.assertIs(left_column.itemAt(1).widget(), window.conversation_view)
        title = window.composer.findChild(QLabel, "composerTitle")
        subtitle = window.composer.findChild(QLabel, "composerSubtitle")
        voice_detail = window.composer.findChild(QLabel, "composerVoiceDetail")
        self.assertIsNotNone(title)
        self.assertIsNotNone(subtitle)
        self.assertIsNotNone(voice_detail)
        self.assertEqual(title.text(), "Start or Resume Work")
        self.assertIn("start work", subtitle.text().lower())
        self.assertIn("resume work", subtitle.text().lower())
        self.assertIn("start work", voice_detail.text().lower())
        self.assertIn("resume work", voice_detail.text().lower())
        self.assertIn("start work", window.composer.input_field.placeholderText().lower())
        self.assertIn("resume work", window.composer.input_field.placeholderText().lower())

    def test_submission_appends_backend_entries(self) -> None:
        from desktop.app.application import build_application
        from desktop.shell.main_window import MainWindow

        app = build_application([])
        self.addCleanup(app.quit)

        window = MainWindow()
        initial_count = window.conversation_view.list_widget.count()

        window.composer.input_field.setPlainText("What can you do?")
        window.composer.send_button.click()

        self.assertGreater(window.conversation_view.list_widget.count(), initial_count)


if __name__ == "__main__":
    unittest.main()
