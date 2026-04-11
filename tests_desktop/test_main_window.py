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
