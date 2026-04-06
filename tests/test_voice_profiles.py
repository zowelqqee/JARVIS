"""Unit tests for product-level TTS voice profiles."""

from __future__ import annotations

import unittest

from voice.voice_profiles import (
    VOICE_PROFILE_EN_ASSISTANT_ANY,
    VOICE_PROFILE_EN_ASSISTANT_FEMALE,
    VOICE_PROFILE_EN_ASSISTANT_MALE,
    VOICE_PROFILE_RU_ASSISTANT_ANY,
    VOICE_PROFILE_RU_ASSISTANT_MALE,
    default_voice_profile_for_locale,
    fallback_voice_profile_ids,
    get_voice_profile,
)


class VoiceProfileTests(unittest.TestCase):
    """Protect stable voice profile identifiers and fallback order."""

    def test_default_profile_prefers_russian_male_assistant_for_russian_locale(self) -> None:
        self.assertEqual(default_voice_profile_for_locale("ru-RU"), VOICE_PROFILE_RU_ASSISTANT_MALE)

    def test_default_profile_prefers_english_male_assistant_for_english_locale(self) -> None:
        self.assertEqual(default_voice_profile_for_locale("en-GB"), VOICE_PROFILE_EN_ASSISTANT_MALE)

    def test_fallback_profiles_keep_requested_gender_before_any_gender(self) -> None:
        self.assertEqual(
            fallback_voice_profile_ids(VOICE_PROFILE_EN_ASSISTANT_FEMALE, "en-US"),
            (
                VOICE_PROFILE_EN_ASSISTANT_FEMALE,
                VOICE_PROFILE_EN_ASSISTANT_ANY,
            ),
        )

    def test_unknown_profile_falls_back_to_language_default(self) -> None:
        self.assertEqual(
            fallback_voice_profile_ids("unknown_profile", "ru-RU"),
            (
                VOICE_PROFILE_RU_ASSISTANT_MALE,
                VOICE_PROFILE_RU_ASSISTANT_ANY,
            ),
        )

    def test_profile_lookup_is_case_insensitive(self) -> None:
        profile = get_voice_profile("EN_ASSISTANT_MALE")

        self.assertIsNotNone(profile)
        self.assertEqual(profile.id, VOICE_PROFILE_EN_ASSISTANT_MALE)


if __name__ == "__main__":
    unittest.main()
