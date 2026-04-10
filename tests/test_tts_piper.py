"""Contract tests for the local Piper TTS backend."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import ANY, MagicMock, patch
import wave

from voice.backends.piper import PiperTTSBackend, _combine_wav_files, _postprocess_wav_file, piper_backend_requested
from voice.tts_provider import SpeechUtterance


def _write_probe_wav(path: Path, *, framerate: int = 1000, frame_count: int = 200, sample: int = 1000) -> None:
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(framerate)
        frames = int(sample).to_bytes(2, byteorder="little", signed=True) * frame_count
        writer.writeframes(frames)


class PiperTTSBackendTests(unittest.TestCase):
    """Protect the independent local-model TTS backend wiring."""

    def test_backend_is_unavailable_without_configured_models(self) -> None:
        with tempfile.TemporaryDirectory() as runtime_root:
            backend = PiperTTSBackend(
                environ={"JARVIS_TTS_PIPER_ROOT": runtime_root},
                binary="/bin/echo",
                player_command=("/usr/bin/afplay",),
            )

            self.assertFalse(backend.is_available())
            self.assertEqual(
                backend.availability_diagnostic(),
                (
                    "PIPER_MODEL_MISSING",
                    "No Piper models are configured; set `JARVIS_TTS_PIPER_MODEL_RU`/`EN` or profile-specific model paths.",
                ),
            )

    def test_backend_is_available_with_binary_player_and_ru_model(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".onnx") as model_file:
            backend = PiperTTSBackend(
                environ={"JARVIS_TTS_PIPER_MODEL_RU": model_file.name},
                binary="/bin/echo",
                player_command=("/usr/bin/afplay",),
            )

            self.assertTrue(backend.is_available())
            descriptor = backend.resolve_voice("ru_assistant_male", "ru-RU")

        self.assertIsNotNone(descriptor)
        self.assertEqual(descriptor.locale, "ru-RU")
        self.assertEqual(descriptor.source, "piper")

    def test_backend_discovers_repo_local_runtime_slots_without_model_envs(self) -> None:
        with tempfile.TemporaryDirectory() as runtime_root:
            runtime_path = Path(runtime_root)
            model_path = runtime_path / "models" / "ru_male.onnx"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_text("stub", encoding="utf-8")
            (runtime_path / "bin").mkdir(parents=True, exist_ok=True)
            (runtime_path / "bin" / "piper").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            sidecar_path = Path(f"{model_path}.json")
            sidecar_path.write_text(
                json.dumps(
                    {
                        "language": {"code": "ru_RU"},
                        "speaker_id_map": {"dmitri": 0},
                    }
                ),
                encoding="utf-8",
            )
            backend = PiperTTSBackend(
                environ={"JARVIS_TTS_PIPER_ROOT": runtime_root},
                player_command=("/usr/bin/afplay",),
            )

            self.assertTrue(backend.is_available())
            descriptor = backend.resolve_voice("ru_assistant_male", "ru-RU")
            voices = backend.list_voices(locale_hint="ru-RU")

        self.assertIsNotNone(descriptor)
        assert descriptor is not None
        self.assertEqual(descriptor.display_name, "Dmitri")
        self.assertEqual(descriptor.gender_hint, "male")
        self.assertEqual(descriptor.locale, "ru-RU")
        self.assertEqual(len(voices), 1)
        self.assertEqual(voices[0].display_name, "Dmitri")
        self.assertEqual(voices[0].id, str(model_path))

    def test_backend_honors_repo_local_manifest_slot_override(self) -> None:
        with tempfile.TemporaryDirectory() as runtime_root:
            runtime_path = Path(runtime_root)
            model_path = runtime_path / "models" / "ru_male_ruslan.onnx"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_text("stub", encoding="utf-8")
            (runtime_path / "bin").mkdir(parents=True, exist_ok=True)
            (runtime_path / "bin" / "piper").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            (runtime_path / "manifest.json").write_text(
                json.dumps(
                    {
                        "slots": {
                            "ru_male": {
                                "path": "models/ru_male_ruslan.onnx",
                                "display_name": "Russian Male (Ruslan)",
                                "gender_hint": "male",
                                "locale": "ru-RU",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            backend = PiperTTSBackend(
                environ={"JARVIS_TTS_PIPER_ROOT": runtime_root},
                player_command=("/usr/bin/afplay",),
            )

            descriptor = backend.resolve_voice("ru_assistant_male", "ru-RU")

        self.assertIsNotNone(descriptor)
        assert descriptor is not None
        self.assertEqual(descriptor.id, str(model_path))
        self.assertEqual(descriptor.display_name, "Russian Male (Ruslan)")

    def test_speak_generates_and_plays_audio_with_resolved_model(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".onnx") as model_file:
            backend = PiperTTSBackend(
                environ={"JARVIS_TTS_PIPER_MODEL_RU": model_file.name},
                binary="/bin/echo",
                player_command=("/usr/bin/afplay",),
            )
            generation = MagicMock()
            generation.returncode = 0
            generation.stdout = ""
            generation.stderr = ""
            playback = MagicMock()
            playback.returncode = 0
            playback.communicate.return_value = ("", "")

            with patch("voice.backends.piper.subprocess.run", return_value=generation) as run_mock, patch(
                "voice.backends.piper.subprocess.Popen",
                return_value=playback,
            ) as popen_mock:
                result = backend.speak(SpeechUtterance(text="Привет", locale="ru-RU"))

        self.assertTrue(result.ok)
        self.assertEqual(result.backend_name, "local_piper")
        self.assertEqual(result.voice_id, model_file.name)
        run_mock.assert_called_once()
        self.assertEqual(
            run_mock.call_args.args[0][:3],
            ["/bin/echo", "--model", model_file.name],
        )
        self.assertEqual(run_mock.call_args.kwargs["input"], "Привет.")
        popen_mock.assert_called_once_with(
            ["/usr/bin/afplay", ANY],
            stdout=ANY,
            stderr=ANY,
            text=True,
        )

    def test_speak_prefers_english_local_model_for_english_text_even_with_ru_locale(self) -> None:
        with tempfile.TemporaryDirectory() as runtime_root:
            runtime_path = Path(runtime_root)
            ru_model = runtime_path / "models" / "ru_male.onnx"
            en_model = runtime_path / "models" / "en_male.onnx"
            ru_model.parent.mkdir(parents=True, exist_ok=True)
            ru_model.write_text("stub", encoding="utf-8")
            en_model.write_text("stub", encoding="utf-8")
            backend = PiperTTSBackend(
                environ={"JARVIS_TTS_PIPER_ROOT": runtime_root},
                binary="/usr/bin/true",
                player_command=("/usr/bin/afplay",),
            )
            generation = MagicMock()
            generation.returncode = 0
            generation.stdout = ""
            generation.stderr = ""
            playback = MagicMock()
            playback.returncode = 0
            playback.communicate.return_value = ("", "")

            with patch("voice.backends.piper.subprocess.run", return_value=generation) as run_mock, patch(
                "voice.backends.piper.subprocess.Popen",
                return_value=playback,
            ):
                result = backend.speak(
                    SpeechUtterance(
                        text="I can open files and folders for you.",
                        locale="ru-RU",
                        voice_profile="ru_assistant_male",
                    )
                )

        self.assertTrue(result.ok)
        self.assertEqual(result.voice_id, str(en_model))
        self.assertEqual(
            run_mock.call_args.args[0][:3],
            ["/usr/bin/true", "--model", str(en_model)],
        )

    def test_speak_uses_manifest_piper_timing_args(self) -> None:
        with tempfile.TemporaryDirectory() as runtime_root:
            runtime_path = Path(runtime_root)
            model_path = runtime_path / "models" / "ru_male.onnx"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_text("stub", encoding="utf-8")
            (runtime_path / "manifest.json").write_text(
                json.dumps(
                    {
                        "slots": {
                            "ru_male": {
                                "path": "models/ru_male.onnx",
                                "display_name": "Russian Male (Dmitri)",
                                "locale": "ru-RU",
                                "gender_hint": "male",
                                "piper_args": {
                                    "length_scale": 1.08,
                                    "sentence_silence": 0.18,
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            backend = PiperTTSBackend(
                environ={"JARVIS_TTS_PIPER_ROOT": runtime_root},
                binary="/usr/bin/true",
                player_command=("/usr/bin/afplay",),
            )
            generation = MagicMock()
            generation.returncode = 0
            generation.stdout = ""
            generation.stderr = ""
            playback = MagicMock()
            playback.returncode = 0
            playback.communicate.return_value = ("", "")

            with patch("voice.backends.piper.subprocess.run", return_value=generation) as run_mock, patch(
                "voice.backends.piper.subprocess.Popen",
                return_value=playback,
            ):
                result = backend.speak(
                    SpeechUtterance(
                        text="Проверка голоса.",
                        locale="ru-RU",
                        voice_profile="ru_assistant_male",
                    )
                )

        self.assertTrue(result.ok)
        command = run_mock.call_args.args[0]
        self.assertIn("--length-scale", command)
        self.assertIn("1.08", command)
        self.assertIn("--sentence-silence", command)
        self.assertIn("0.18", command)

    def test_speak_pronounces_short_tech_tokens_for_russian_tts(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".onnx") as model_file:
            backend = PiperTTSBackend(
                environ={"JARVIS_TTS_PIPER_MODEL_RU": model_file.name},
                binary="/bin/echo",
                player_command=("/usr/bin/afplay",),
            )
            generation = MagicMock()
            generation.returncode = 0
            generation.stdout = ""
            generation.stderr = ""
            playback = MagicMock()
            playback.returncode = 0
            playback.communicate.return_value = ("", "")

            with patch("voice.backends.piper.subprocess.run", return_value=generation) as run_mock, patch(
                "voice.backends.piper.subprocess.Popen",
                return_value=playback,
            ):
                result = backend.speak(
                    SpeechUtterance(
                        text="JARVIS использует OpenAI API, JSON и CLI.",
                        locale="ru-RU",
                        voice_profile="ru_assistant_male",
                    )
                )

        self.assertTrue(result.ok)
        self.assertEqual(
            run_mock.call_args.args[0][:3],
            ["/bin/echo", "--model", model_file.name],
        )
        self.assertEqual(
            run_mock.call_args.kwargs["input"],
            "Джарвис использует Оупен эй ай эй пи ай, джейсон и си эль ай.",
        )

    def test_speak_softens_russian_pause_punctuation_for_piper(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".onnx") as model_file:
            backend = PiperTTSBackend(
                environ={"JARVIS_TTS_PIPER_MODEL_RU": model_file.name},
                binary="/bin/echo",
                player_command=("/usr/bin/afplay",),
            )
            generation = MagicMock()
            generation.returncode = 0
            generation.stdout = ""
            generation.stderr = ""
            playback = MagicMock()
            playback.returncode = 0
            playback.communicate.return_value = ("", "")

            with patch("voice.backends.piper.subprocess.run", return_value=generation) as run_mock, patch(
                "voice.backends.piper.subprocess.Popen",
                return_value=playback,
            ):
                result = backend.speak(
                    SpeechUtterance(
                        text="Не понял, что ты имел в виду — попробуй сказать что-то проще.",
                        locale="ru-RU",
                        voice_profile="ru_assistant_male",
                    )
                )

        self.assertTrue(result.ok)
        self.assertEqual(
            [call.kwargs["input"] for call in run_mock.call_args_list],
            [
                "Не понял",
                "что ты имел в виду попробуй сказать что-то проще.",
            ],
        )

    def test_speak_softens_common_russian_lead_in_commas_for_piper(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".onnx") as model_file:
            backend = PiperTTSBackend(
                environ={"JARVIS_TTS_PIPER_MODEL_RU": model_file.name},
                binary="/bin/echo",
                player_command=("/usr/bin/afplay",),
            )
            generation = MagicMock()
            generation.returncode = 0
            generation.stdout = ""
            generation.stderr = ""
            playback = MagicMock()
            playback.returncode = 0
            playback.communicate.return_value = ("", "")

            with patch("voice.backends.piper.subprocess.run", return_value=generation) as run_mock, patch(
                "voice.backends.piper.subprocess.Popen",
                return_value=playback,
            ):
                result = backend.speak(
                    SpeechUtterance(
                        text="Хорошо, например, открою файлы, и покажу папки.",
                        locale="ru-RU",
                        voice_profile="ru_assistant_male",
                    )
                )

        self.assertTrue(result.ok)
        self.assertEqual(
            [call.kwargs["input"] for call in run_mock.call_args_list],
            [
                "Хорошо",
                "например",
                "открою файлы",
                "и покажу папки.",
            ],
        )

    def test_speak_splits_long_english_island_inside_russian_text(self) -> None:
        with tempfile.TemporaryDirectory() as runtime_root:
            runtime_path = Path(runtime_root)
            ru_model = runtime_path / "models" / "ru_male.onnx"
            en_model = runtime_path / "models" / "en_male.onnx"
            ru_model.parent.mkdir(parents=True, exist_ok=True)
            ru_model.write_text("stub", encoding="utf-8")
            en_model.write_text("stub", encoding="utf-8")
            backend = PiperTTSBackend(
                environ={"JARVIS_TTS_PIPER_ROOT": runtime_root},
                binary="/usr/bin/true",
                player_command=("/usr/bin/afplay",),
            )
            generation = MagicMock()
            generation.returncode = 0
            generation.stdout = ""
            generation.stderr = ""
            playback = MagicMock()
            playback.returncode = 0
            playback.communicate.return_value = ("", "")

            def _generate_probe_wav(command: list[str], **_: object) -> MagicMock:
                output_path = Path(command[command.index("--output_file") + 1])
                _write_probe_wav(output_path, frame_count=50)
                return generation

            with patch("voice.backends.piper.subprocess.run", side_effect=_generate_probe_wav) as run_mock, patch(
                "voice.backends.piper.subprocess.Popen",
                return_value=playback,
            ) as popen_mock:
                result = backend.speak(
                    SpeechUtterance(
                        text="Сначала скажи use the English model for this part, потом продолжи.",
                        locale="ru-RU",
                        voice_profile="ru_assistant_male",
                    )
                )

        self.assertTrue(result.ok)
        self.assertEqual(result.voice_id, str(ru_model))
        self.assertEqual(run_mock.call_count, 3)
        commands = [call.args[0] for call in run_mock.call_args_list]
        self.assertEqual(
            [command[:3] for command in commands],
            [
                ["/usr/bin/true", "--model", str(ru_model)],
                ["/usr/bin/true", "--model", str(en_model)],
                ["/usr/bin/true", "--model", str(ru_model)],
            ],
        )
        self.assertEqual(
            [call.kwargs["input"] for call in run_mock.call_args_list],
            [
                "Сначала скажи.",
                "use the English model for this part,",
                "потом продолжи.",
            ],
        )
        popen_mock.assert_called_once_with(
            ["/usr/bin/afplay", ANY],
            stdout=ANY,
            stderr=ANY,
            text=True,
        )

    def test_audio_postprocess_can_add_bass_to_pcm16_wav(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            wav_path = Path(tempdir) / "probe.wav"
            _write_probe_wav(wav_path)

            _postprocess_wav_file(
                wav_path,
                slot_config={
                    "audio_postprocess": {
                        "bass_boost": 0.25,
                        "bass_cutoff_hz": 140.0,
                        "output_gain": 0.98,
                        "sample_rate_scale": 0.9,
                    }
                },
            )

            with wave.open(str(wav_path), "rb") as reader:
                processed_framerate = reader.getframerate()
                processed = reader.readframes(reader.getnframes())

        samples = [
            int.from_bytes(processed[index : index + 2], byteorder="little", signed=True)
            for index in range(0, len(processed), 2)
        ]
        self.assertEqual(len(samples), 200)
        self.assertEqual(processed_framerate, 900)
        self.assertGreater(samples[-1], 1000)
        self.assertLessEqual(samples[-1], 32767)

    def test_combine_wav_files_resamples_segments_for_single_playback_file(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            temp_path = Path(tempdir)
            first = temp_path / "first.wav"
            second = temp_path / "second.wav"
            combined = temp_path / "combined.wav"
            _write_probe_wav(first, framerate=1000, frame_count=100)
            _write_probe_wav(second, framerate=500, frame_count=50)

            ok = _combine_wav_files([first, second], combined, inter_segment_silence_ms=10)

            with wave.open(str(combined), "rb") as reader:
                combined_framerate = reader.getframerate()
                combined_frame_count = reader.getnframes()

        self.assertTrue(ok)
        self.assertEqual(combined_framerate, 1000)
        self.assertEqual(combined_frame_count, 210)

    def test_list_voices_exposes_configured_models(self) -> None:
        with tempfile.TemporaryDirectory() as runtime_root, tempfile.NamedTemporaryFile(suffix=".onnx") as ru_model, tempfile.NamedTemporaryFile(
            suffix=".onnx"
        ) as en_model:
            backend = PiperTTSBackend(
                environ={
                    "JARVIS_TTS_PIPER_ROOT": runtime_root,
                    "JARVIS_TTS_PIPER_MODEL_RU": ru_model.name,
                    "JARVIS_TTS_PIPER_MODEL_EN": en_model.name,
                },
                binary="/bin/echo",
                player_command=("/usr/bin/afplay",),
            )

            voices = backend.list_voices()

        self.assertEqual(len(voices), 2)
        self.assertEqual({voice.locale for voice in voices}, {"ru-RU", "en-US"})

    def test_backend_request_detection_uses_models_or_explicit_enable(self) -> None:
        self.assertTrue(piper_backend_requested({"JARVIS_TTS_PIPER_MODEL_RU": "/tmp/ru.onnx"}))
        self.assertTrue(piper_backend_requested({"JARVIS_TTS_PIPER_ENABLED": "1"}))
        with tempfile.TemporaryDirectory() as runtime_root:
            runtime_path = Path(runtime_root)
            model_path = runtime_path / "models" / "ru_male.onnx"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_text("stub", encoding="utf-8")
            self.assertTrue(piper_backend_requested({"JARVIS_TTS_PIPER_ROOT": runtime_root}))
        self.assertFalse(
            piper_backend_requested(
                {
                    "JARVIS_TTS_PIPER_ENABLED": "0",
                    "JARVIS_TTS_PIPER_MODEL_RU": "/tmp/ru.onnx",
                }
            )
        )


if __name__ == "__main__":
    unittest.main()
