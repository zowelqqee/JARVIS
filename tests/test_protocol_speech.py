"""Speech rendering tests for protocol command summaries."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from voice.speech_presenter import interaction_speech_message


class ProtocolSpeechTests(unittest.TestCase):
    """Keep spoken protocol summaries short and intentional."""

    def test_run_protocol_command_summary_uses_protocol_template(self) -> None:
        result = SimpleNamespace(
            interaction_mode="command",
            visibility={
                "interaction_mode": "command",
                "runtime_state": "completed",
                "command_summary": "run_protocol: Clean Slate",
                "completion_result": "Completed run_protocol with 4 step(s).",
            },
        )

        self.assertEqual(interaction_speech_message(result), "Ran protocol Clean Slate.")
