import unittest
from unittest.mock import MagicMock, patch


class TestOpenAppWindowsTerminal(unittest.TestCase):

    def test_launch_windows_cmd_uses_new_console_without_shell(self):
        with patch("actions.open_app.subprocess.Popen") as mock_popen, \
             patch("actions.open_app.subprocess.CREATE_NEW_CONSOLE", 16, create=True), \
             patch("actions.open_app.time.sleep"), \
             patch("actions.open_app._maximize_later") as mock_maximize:
            from actions.open_app import _launch_windows

            result = _launch_windows("cmd.exe")

        self.assertTrue(result)
        mock_popen.assert_called_once_with(["cmd.exe"], creationflags=16)
        mock_maximize.assert_called_once_with("cmd.exe")

    def test_open_app_skips_existing_process_focus_for_windows_terminal(self):
        launcher = MagicMock(return_value=True)

        with patch("actions.open_app.platform.system", return_value="Windows"), \
             patch.dict("actions.open_app._OS_LAUNCHERS", {"Windows": launcher}, clear=False), \
             patch("actions.open_app._is_running") as mock_is_running, \
             patch("actions.open_app._focus_existing_window") as mock_focus:
            from actions.open_app import open_app

            result = open_app(parameters={"app_name": "cmd"})

        self.assertIn("Opened cmd successfully, sir.", result)
        launcher.assert_called_once_with("cmd.exe")
        mock_is_running.assert_not_called()
        mock_focus.assert_not_called()
