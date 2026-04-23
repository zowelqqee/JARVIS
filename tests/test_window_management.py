import unittest
from unittest.mock import patch


class TestWindowManagement(unittest.TestCase):

    def test_maximize_action_accepts_named_app(self):
        with patch("actions.computer_settings._PYAUTOGUI", True), \
             patch("actions.computer_settings.maximize_window") as mock_maximize:
            from actions.computer_settings import computer_settings

            result = computer_settings({
                "action": "maximize",
                "value": "Visual Studio Code",
            })

        mock_maximize.assert_called_once_with("Visual Studio Code")
        self.assertEqual(result, "Maximized Visual Studio Code.")

    def test_open_app_maximize_retries_until_window_found(self):
        with patch("actions.open_app._focus_existing_window", side_effect=[False, False, True]) as mock_focus, \
             patch("actions.open_app.time.sleep") as mock_sleep:
            from actions.open_app import _maximize_window_with_retries, SW_SHOWMAXIMIZED

            result = _maximize_window_with_retries("chrome", attempts=3, interval=0.5)

        self.assertTrue(result)
        self.assertEqual(mock_focus.call_count, 3)
        mock_focus.assert_called_with("chrome", SW_SHOWMAXIMIZED)
        self.assertEqual(mock_sleep.call_count, 2)
