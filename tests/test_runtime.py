"""
Focused tests for live-session robustness patches:
  1. Unsupported action returns structured tool-error response (not a raise)
  2. Scroll action dispatches correctly via computer_settings
  3. tool_call_in_progress pauses outgoing audio in _send_realtime
  4. 1011 error does NOT propagate out of the TaskGroup unhandled
"""

import asyncio
import types as builtin_types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# 1 & 2 — computer_settings scroll / unknown action
# ---------------------------------------------------------------------------

class TestComputerSettingsScroll(unittest.TestCase):

    def _call(self, params):
        with patch("pyautogui.scroll") as mock_scroll, \
             patch("actions.computer_settings._PYAUTOGUI", True):
            from actions.computer_settings import computer_settings
            result = computer_settings(params)
        return result, mock_scroll

    def test_scroll_down_default(self):
        with patch("pyautogui.scroll") as mock_scroll, \
             patch("actions.computer_settings._PYAUTOGUI", True):
            from actions.computer_settings import computer_settings
            result = computer_settings({"action": "scroll"})
        self.assertIn("down", result.lower())
        mock_scroll.assert_called_once()
        # negative amount = scroll down
        self.assertLess(mock_scroll.call_args[0][0], 0)

    def test_scroll_up_via_value(self):
        with patch("pyautogui.scroll") as mock_scroll, \
             patch("actions.computer_settings._PYAUTOGUI", True):
            from actions.computer_settings import computer_settings
            result = computer_settings({"action": "scroll", "value": "up"})
        self.assertIn("up", result.lower())
        mock_scroll.assert_called_once()
        self.assertGreater(mock_scroll.call_args[0][0], 0)

    def test_unknown_action_returns_string_not_raises(self):
        with patch("actions.computer_settings._PYAUTOGUI", True):
            from actions.computer_settings import computer_settings
            result = computer_settings({"action": "nonexistent_action_xyz"})
        self.assertIsInstance(result, str)
        self.assertIn("Unknown action", result)


# ---------------------------------------------------------------------------
# 3 — tool_call_in_progress pauses _send_realtime
# ---------------------------------------------------------------------------

class TestSendRealtimePause(unittest.IsolatedAsyncioTestCase):

    async def test_audio_discarded_when_tool_call_in_progress(self):
        from unittest.mock import AsyncMock, MagicMock

        ui_mock      = MagicMock()
        session_mock = AsyncMock()

        # Import after patching so registry import doesn't fail
        with patch.dict("sys.modules", {
            "pyaudio": MagicMock(),
            "ui": MagicMock(),
        }):
            import importlib, sys
            # We test _send_realtime in isolation by constructing a minimal object
            from main import JarvisLive

        jarvis         = JarvisLive.__new__(JarvisLive)
        jarvis.session = session_mock
        jarvis.out_queue = asyncio.Queue(maxsize=10)
        jarvis.tool_call_in_progress = True

        # Enqueue one chunk
        await jarvis.out_queue.put({"data": b"\x00\x01", "mime_type": "audio/pcm"})

        # Run _send_realtime for just long enough to process that chunk
        async def run_once():
            # Patch the loop to stop after draining one item
            original = jarvis.out_queue.get
            call_count = [0]
            async def patched_get():
                call_count[0] += 1
                if call_count[0] > 1:
                    raise asyncio.CancelledError
                return await original()
            jarvis.out_queue.get = patched_get
            try:
                await jarvis._send_realtime()
            except asyncio.CancelledError:
                pass

        await run_once()
        session_mock.send_realtime_input.assert_not_called()

    async def test_audio_sent_when_flag_clear(self):
        from main import JarvisLive

        session_mock = AsyncMock()
        jarvis       = JarvisLive.__new__(JarvisLive)
        jarvis.session = session_mock
        jarvis.out_queue = asyncio.Queue(maxsize=10)
        jarvis.tool_call_in_progress = False

        chunk = {"data": b"\x00\x01", "mime_type": "audio/pcm"}
        await jarvis.out_queue.put(chunk)

        original = jarvis.out_queue.get
        call_count = [0]
        async def patched_get():
            call_count[0] += 1
            if call_count[0] > 1:
                raise asyncio.CancelledError
            return await original()
        jarvis.out_queue.get = patched_get

        try:
            await jarvis._send_realtime()
        except asyncio.CancelledError:
            pass

        session_mock.send_realtime_input.assert_called_once_with(media=chunk)


# ---------------------------------------------------------------------------
# 4 — 1011 does not crash TaskGroup unhandled
# ---------------------------------------------------------------------------

class TestReconnectOn1011(unittest.IsolatedAsyncioTestCase):

    async def test_1011_caught_by_outer_loop(self):
        """run() must NOT propagate 1011 out; it should sleep and loop."""
        from main import JarvisLive

        ui_mock = MagicMock()
        ui_mock.write_log = MagicMock()
        for attr in ("set_connecting", "set_failed", "set_idle"):
            setattr(ui_mock, attr, MagicMock())

        jarvis = JarvisLive.__new__(JarvisLive)
        jarvis.ui = ui_mock
        jarvis.session = None
        jarvis.jarvis_loop = None
        jarvis._loop = None
        jarvis.audio_in_queue = None
        jarvis.out_queue = None
        jarvis.tool_call_in_progress = False
        jarvis.on_text_response = None
        jarvis.on_status_change = None

        iteration = [0]

        class FakeSession:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): pass

        class FakeTaskGroup:
            async def __aenter__(self): return self
            async def __aexit__(self, *a):
                iteration[0] += 1
                if iteration[0] == 1:
                    err = Exception("WebSocket connection closed: 1011")
                    raise err
                # Second iteration exits cleanly → raise CancelledError to stop run()
                raise asyncio.CancelledError

            def create_task(self, coro):
                # Cancel the coroutine immediately to avoid resource leak
                task = asyncio.ensure_future(coro)
                task.cancel()
                return task

        connect_cm = MagicMock()
        connect_cm.__aenter__ = AsyncMock(return_value=FakeSession())
        connect_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("main._get_api_key", return_value="fake"), \
             patch("main.JarvisLive._build_config", return_value=MagicMock()), \
             patch("genai.Client") as mock_client, \
             patch("asyncio.TaskGroup", FakeTaskGroup), \
             patch("asyncio.sleep", new_callable=AsyncMock):

            mock_client.return_value.aio.live.connect.return_value = connect_cm

            with self.assertRaises(asyncio.CancelledError):
                await jarvis.run()

        # If we get here without an unhandled Exception the test passes;
        # the CancelledError from iteration 2 is the expected exit signal.
        self.assertGreaterEqual(iteration[0], 1)


if __name__ == "__main__":
    unittest.main()
