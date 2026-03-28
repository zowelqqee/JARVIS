"""Contract checks for staged voice feature flags."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from voice.flags import continuous_voice_mode_enabled


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


if __name__ == "__main__":
    unittest.main()
