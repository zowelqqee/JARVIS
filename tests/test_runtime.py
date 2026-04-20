"""
Focused tests for live-session robustness patches:
  1. Unsupported action returns structured tool-error response (not a raise)
  2. Scroll action dispatches correctly via computer_settings
  3. tool_call_in_progress pauses outgoing audio in _send_realtime
  4. _receive_audio does NOT re-raise APIError 1011; marks session_failed and
     cancels siblings instead
  5. run() reconnects when TaskGroup propagates CancelledError after our
     controlled shutdown (session_failed=True path)
  6. run() reconnects when a 1011 exception escapes the TaskGroup directly
     (legacy/fallback path; string-based detection)
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# 1 & 2 — computer_settings scroll / unknown action
# ---------------------------------------------------------------------------

class TestComputerSettingsScroll(unittest.TestCase):

    def test_scroll_down_default(self):
        with patch("pyautogui.scroll") as mock_scroll, \
             patch("actions.computer_settings._PYAUTOGUI", True):
            from actions.computer_settings import computer_settings
            result = computer_settings({"action": "scroll"})
        self.assertIn("down", result.lower())
        mock_scroll.assert_called_once()
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
        session_mock = AsyncMock()
        from main import VectorLive
        vector = VectorLive.__new__(VectorLive)
        vector.session = session_mock
        vector.out_queue = asyncio.Queue(maxsize=10)
        vector.tool_call_in_progress = True

        await vector.out_queue.put({"data": b"\x00\x01", "mime_type": "audio/pcm"})

        original = vector.out_queue.get
        call_count = [0]
        async def patched_get():
            call_count[0] += 1
            if call_count[0] > 1:
                raise asyncio.CancelledError
            return await original()
        vector.out_queue.get = patched_get

        try:
            await vector._send_realtime()
        except asyncio.CancelledError:
            pass

        session_mock.send_realtime_input.assert_not_called()

    async def test_audio_sent_when_flag_clear(self):
        from main import VectorLive
        session_mock = AsyncMock()
        vector = VectorLive.__new__(VectorLive)
        vector.session = session_mock
        vector.out_queue = asyncio.Queue(maxsize=10)
        vector.tool_call_in_progress = False

        chunk = {"data": b"\x00\x01", "mime_type": "audio/pcm"}
        await vector.out_queue.put(chunk)

        original = vector.out_queue.get
        call_count = [0]
        async def patched_get():
            call_count[0] += 1
            if call_count[0] > 1:
                raise asyncio.CancelledError
            return await original()
        vector.out_queue.get = patched_get

        try:
            await vector._send_realtime()
        except asyncio.CancelledError:
            pass

        session_mock.send_realtime_input.assert_called_once_with(media=chunk)


# ---------------------------------------------------------------------------
# 4 — _receive_audio does NOT re-raise 1011; marks flag and cancels siblings
# ---------------------------------------------------------------------------

class TestReceiveAudioDisconnect(unittest.IsolatedAsyncioTestCase):

    def _make_vector(self):
        from main import VectorLive
        vector = VectorLive.__new__(VectorLive)
        vector.ui = MagicMock()
        vector.session = MagicMock()
        vector.audio_in_queue = asyncio.Queue()
        vector.out_queue = asyncio.Queue(maxsize=10)
        vector.tool_call_in_progress = False
        vector._session_failed = False
        vector._session_tasks = []
        vector.on_text_response = None
        vector.on_status_change = None
        return vector

    async def test_1011_does_not_reraise(self):
        """_receive_audio must return (not raise) on a 1011 APIError."""
        vector = self._make_vector()

        class _FakeIter:
            def __aiter__(self): return self
            async def __anext__(self): raise Exception("WebSocket closed: 1011 going away")

        vector.session.receive = MagicMock(return_value=_FakeIter())

        # Should complete without raising
        await vector._receive_audio()

        self.assertTrue(vector._session_failed)

    async def test_1011_cancels_siblings(self):
        """_receive_audio must cancel any non-done task in _session_tasks."""
        vector = self._make_vector()

        class _FakeIter:
            def __aiter__(self): return self
            async def __anext__(self): raise Exception("connection closed: 1011")

        vector.session.receive = MagicMock(return_value=_FakeIter())

        sibling = asyncio.ensure_future(asyncio.sleep(9999))
        vector._session_tasks = [sibling]

        await vector._receive_audio()

        self.assertTrue(sibling.cancelled() or sibling.cancelling() > 0)
        sibling.cancel()  # cleanup

    async def test_cancelled_error_still_propagates(self):
        """asyncio.CancelledError must not be swallowed by _receive_audio."""
        vector = self._make_vector()

        class _FakeIter:
            def __aiter__(self): return self
            async def __anext__(self): raise asyncio.CancelledError

        vector.session.receive = MagicMock(return_value=_FakeIter())

        with self.assertRaises(asyncio.CancelledError):
            await vector._receive_audio()

    async def test_non_conn_error_still_reraises(self):
        """Unrelated exceptions must still propagate so callers see them."""
        vector = self._make_vector()

        class _FakeIter:
            def __aiter__(self): return self
            async def __anext__(self): raise ValueError("unexpected codec error")

        vector.session.receive = MagicMock(return_value=_FakeIter())

        with self.assertRaises(ValueError):
            await vector._receive_audio()

        self.assertFalse(vector._session_failed)


# ---------------------------------------------------------------------------
# 5 — run() reconnects on CancelledError when session_failed=True
# ---------------------------------------------------------------------------

class TestReconnectOnSessionFailed(unittest.IsolatedAsyncioTestCase):

    async def test_cancelled_error_with_session_failed_triggers_reconnect(self):
        """
        When _receive_audio sets session_failed and cancels siblings, the
        TaskGroup eventually cancels the parent (run()) with CancelledError.
        run() must absorb that and reconnect rather than dying.
        """
        from main import VectorLive

        ui_mock = MagicMock()
        for attr in ("write_log", "set_connecting", "set_failed", "set_idle"):
            setattr(ui_mock, attr, MagicMock())

        vector = VectorLive.__new__(VectorLive)
        vector.ui = ui_mock
        vector.session = None
        vector.vector_loop = None
        vector._loop = None
        vector.audio_in_queue = None
        vector.out_queue = None
        vector.tool_call_in_progress = False
        vector.on_text_response = None
        vector.on_status_change = None
        vector._session_failed = False
        vector._session_tasks = []

        iteration = [0]

        class FakeSession:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): pass

        class FakeTaskGroup:
            async def __aenter__(self): return self
            async def __aexit__(self, *a):
                iteration[0] += 1
                if iteration[0] == 1:
                    # Simulate: _receive_audio set session_failed then returned;
                    # TaskGroup cancelled parent → CancelledError arrives here.
                    vector._session_failed = True
                    raise asyncio.CancelledError
                # Second attempt: exit cleanly then stop the loop
                raise asyncio.CancelledError  # stop test with real cancel

            def create_task(self, coro):
                task = asyncio.ensure_future(coro)
                task.cancel()
                return task

        connect_cm = MagicMock()
        connect_cm.__aenter__ = AsyncMock(return_value=FakeSession())
        connect_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("main._get_api_key", return_value="fake"), \
             patch("main.VectorLive._build_config", return_value=MagicMock()), \
             patch("main.genai.Client") as mock_client, \
             patch("asyncio.TaskGroup", FakeTaskGroup), \
             patch("asyncio.sleep", new_callable=AsyncMock):

            mock_client.return_value.aio.live.connect.return_value = connect_cm

            with self.assertRaises(asyncio.CancelledError):
                await vector.run()

        # First iteration was a controlled disconnect → reconnected (iteration 2 ran)
        self.assertGreaterEqual(iteration[0], 2)


# ---------------------------------------------------------------------------
# 6 — run() reconnects when 1011 exception escapes TaskGroup directly (legacy)
# ---------------------------------------------------------------------------

class TestReconnectOn1011Legacy(unittest.IsolatedAsyncioTestCase):

    async def test_1011_string_caught_by_outer_loop(self):
        """run() must NOT propagate 1011 out; it should sleep and loop."""
        from main import VectorLive

        ui_mock = MagicMock()
        ui_mock.write_log = MagicMock()
        for attr in ("set_connecting", "set_failed", "set_idle"):
            setattr(ui_mock, attr, MagicMock())

        vector = VectorLive.__new__(VectorLive)
        vector.ui = ui_mock
        vector.session = None
        vector.vector_loop = None
        vector._loop = None
        vector.audio_in_queue = None
        vector.out_queue = None
        vector.tool_call_in_progress = False
        vector.on_text_response = None
        vector.on_status_change = None
        vector._session_failed = False
        vector._session_tasks = []

        iteration = [0]

        class FakeSession:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): pass

        class FakeTaskGroup:
            async def __aenter__(self): return self
            async def __aexit__(self, *a):
                iteration[0] += 1
                if iteration[0] == 1:
                    raise Exception("WebSocket connection closed: 1011")
                raise asyncio.CancelledError

            def create_task(self, coro):
                task = asyncio.ensure_future(coro)
                task.cancel()
                return task

        connect_cm = MagicMock()
        connect_cm.__aenter__ = AsyncMock(return_value=FakeSession())
        connect_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("main._get_api_key", return_value="fake"), \
             patch("main.VectorLive._build_config", return_value=MagicMock()), \
             patch("main.genai.Client") as mock_client, \
             patch("asyncio.TaskGroup", FakeTaskGroup), \
             patch("asyncio.sleep", new_callable=AsyncMock):

            mock_client.return_value.aio.live.connect.return_value = connect_cm

            with self.assertRaises(asyncio.CancelledError):
                await vector.run()

        self.assertGreaterEqual(iteration[0], 1)


if __name__ == "__main__":
    unittest.main()
