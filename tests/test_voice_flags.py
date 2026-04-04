"""Contract checks for staged voice feature flags."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from voice.flags import (
    build_voice_mode_status,
    continuous_voice_mode_enabled,
    format_voice_mode_status,
    max_auto_follow_up_turns,
    voice_earcons_enabled,
)


class VoiceFlagsTests(unittest.TestCase):
    """Keep rollout defaults and truthy/falsy parsing stable."""

    def test_continuous_voice_mode_is_disabled_by_default(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(continuous_voice_mode_enabled())

    def test_continuous_voice_mode_accepts_truthy_values(self) -> None:
        for raw_value in ("1", "true", "yes", "on"):
            with self.subTest(raw_value=raw_value), patch.dict(
                "os.environ",
                {"JARVIS_VOICE_CONTINUOUS_MODE": raw_value},
                clear=True,
            ):
                self.assertTrue(continuous_voice_mode_enabled())

    def test_continuous_voice_mode_accepts_falsy_values(self) -> None:
        for raw_value in ("0", "false", "no", "off"):
            with self.subTest(raw_value=raw_value), patch.dict(
                "os.environ",
                {"JARVIS_VOICE_CONTINUOUS_MODE": raw_value},
                clear=True,
            ):
                self.assertFalse(continuous_voice_mode_enabled())

    def test_voice_earcons_are_disabled_by_default(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(voice_earcons_enabled())

    def test_voice_earcons_accept_truthy_values(self) -> None:
        for raw_value in ("1", "true", "yes", "on"):
            with self.subTest(raw_value=raw_value), patch.dict(
                "os.environ",
                {"JARVIS_VOICE_EARCONS": raw_value},
                clear=True,
            ):
                self.assertTrue(voice_earcons_enabled())

    def test_voice_mode_status_reports_zero_follow_up_budget_when_flag_is_disabled(self) -> None:
        status = build_voice_mode_status(environ={})

        self.assertFalse(status.continuous_mode_enabled)
        self.assertFalse(status.earcons_enabled)
        self.assertTrue(status.advanced_follow_up_default_off)
        self.assertEqual(status.max_auto_follow_up_turns, 0)
        self.assertTrue(status.short_answer_follow_up_requires_speech)

    def test_voice_mode_status_reports_follow_up_budget_when_flag_is_enabled(self) -> None:
        status = build_voice_mode_status(environ={"JARVIS_VOICE_CONTINUOUS_MODE": "1", "JARVIS_VOICE_EARCONS": "1"})

        self.assertTrue(status.continuous_mode_enabled)
        self.assertTrue(status.earcons_enabled)
        self.assertEqual(status.max_auto_follow_up_turns, max_auto_follow_up_turns({"JARVIS_VOICE_CONTINUOUS_MODE": "1"}))

    def test_format_voice_mode_status_mentions_flag_and_budget(self) -> None:
        rendered = format_voice_mode_status(
            build_voice_mode_status(environ={"JARVIS_VOICE_CONTINUOUS_MODE": "1", "JARVIS_VOICE_EARCONS": "1"})
        )

        self.assertIn("JARVIS Voice Mode", rendered)
        self.assertIn("advanced follow-up flag: JARVIS_VOICE_CONTINUOUS_MODE", rendered)
        self.assertIn("continuous mode enabled: yes", rendered)
        self.assertIn("earcons flag: JARVIS_VOICE_EARCONS", rendered)
        self.assertIn("earcons enabled: yes", rendered)
        self.assertIn("max auto follow-up turns: 2", rendered)


if __name__ == "__main__":
    unittest.main()
