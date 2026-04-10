"""Tests for explicit local CLI TTS defaults."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from voice.status import build_tts_backend_status, format_tts_backend_status
from voice.tts_provider import build_default_tts_provider
from voice.tts_runtime_env import apply_cli_tts_env_defaults, tts_runtime_configuration_notes


class TTSRuntimeEnvTests(unittest.TestCase):
    """Keep local CLI TTS defaults explicit and deterministic."""

    def test_apply_cli_tts_env_defaults_fills_missing_keys_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            defaults_path = Path(tmpdir) / "jarvis_tts.env"
            defaults_path.write_text(
                "\n".join(
                    [
                        "JARVIS_TTS_YANDEX_ENABLED=1",
                        "JARVIS_TTS_RU_BACKEND=yandex_speechkit",
                        "JARVIS_TTS_EN_BACKEND=local_piper",
                        "JARVIS_TTS_YANDEX_VOICE=different",
                        "HOME=/tmp/should_be_ignored",
                    ]
                ),
                encoding="utf-8",
            )
            env = {
                "JARVIS_TTS_ENV_FILE": str(defaults_path),
                "JARVIS_TTS_YANDEX_API_KEY": "secret",
                "JARVIS_TTS_YANDEX_VOICE": "ermil",
            }

            state = apply_cli_tts_env_defaults(env)

            self.assertTrue(state.loaded)
            self.assertEqual(state.path, str(defaults_path))
            self.assertEqual(
                state.configured_keys,
                (
                    "JARVIS_TTS_YANDEX_ENABLED",
                    "JARVIS_TTS_RU_BACKEND",
                    "JARVIS_TTS_EN_BACKEND",
                    "JARVIS_TTS_YANDEX_VOICE",
                ),
            )
            self.assertEqual(
                state.applied_keys,
                (
                    "JARVIS_TTS_YANDEX_ENABLED",
                    "JARVIS_TTS_RU_BACKEND",
                    "JARVIS_TTS_EN_BACKEND",
                ),
            )
            self.assertEqual(env["JARVIS_TTS_YANDEX_ENABLED"], "1")
            self.assertEqual(env["JARVIS_TTS_RU_BACKEND"], "yandex_speechkit")
            self.assertEqual(env["JARVIS_TTS_EN_BACKEND"], "local_piper")
            self.assertEqual(env["JARVIS_TTS_YANDEX_VOICE"], "ermil")
            self.assertNotIn("HOME", env)

    def test_build_default_tts_provider_reports_loaded_cli_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            defaults_path = Path(tmpdir) / "jarvis_tts.env"
            defaults_path.write_text(
                "\n".join(
                    [
                        "JARVIS_TTS_YANDEX_ENABLED=1",
                        "JARVIS_TTS_RU_BACKEND=yandex_speechkit",
                        "JARVIS_TTS_EN_BACKEND=local_piper",
                    ]
                ),
                encoding="utf-8",
            )
            env = {
                "JARVIS_TTS_ENV_FILE": str(defaults_path),
                "JARVIS_TTS_YANDEX_API_KEY": "secret",
                "JARVIS_TTS_YANDEX_VOICE": "ermil",
                "JARVIS_TTS_YANDEX_ROLE": "good",
                "JARVIS_TTS_YANDEX_PLAYER": "/bin/true",
            }
            apply_cli_tts_env_defaults(env)

            provider = build_default_tts_provider(environ=env)
            notes = tts_runtime_configuration_notes(env)
            rendered = format_tts_backend_status(build_tts_backend_status(provider))

            self.assertEqual(provider.backend_name(), "yandex_speechkit")
            self.assertIn(f"loaded local TTS defaults from {defaults_path}", notes)
            self.assertIn(
                "applied missing keys: JARVIS_TTS_YANDEX_ENABLED, JARVIS_TTS_RU_BACKEND, JARVIS_TTS_EN_BACKEND",
                notes,
            )
            self.assertIn("configuration:", rendered)
            self.assertIn(f"loaded local TTS defaults from {defaults_path}", rendered)
            self.assertIn(
                "applied missing keys: JARVIS_TTS_YANDEX_ENABLED, JARVIS_TTS_RU_BACKEND, JARVIS_TTS_EN_BACKEND",
                rendered,
            )

