import unittest
from unittest.mock import MagicMock, patch


class TestAgentTaskFeedback(unittest.TestCase):

    def test_agent_task_returns_structured_status_not_spoken_phrase(self):
        fake_queue = MagicMock()
        fake_queue.submit.return_value = "abc12345"
        fake_player = MagicMock()

        with patch("agent.task_queue.get_queue", return_value=fake_queue), \
             patch("agent.task_queue.clear_interrupt"):
            from actions.registry import _agent_task_handler

            result = _agent_task_handler(
                {"goal": "research asyncio docs", "priority": "high"},
                fake_player,
                speak=None,
            )

        self.assertEqual(result, {"status": "queued"})
        fake_queue.submit.assert_called_once()
        fake_player.write_log.assert_called_once_with("[agent_task] queued [abc12345]")
