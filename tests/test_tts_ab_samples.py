"""Tests for Russian TTS A/B sample generation."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from voice.tts_ab_samples import discover_ru_piper_candidates, render_ru_ab_samples


class TTSABSamplesTests(unittest.TestCase):
    """Protect the offline Piper model comparison helper."""

    def test_discovers_russian_candidates_from_runtime_models(self) -> None:
        with tempfile.TemporaryDirectory() as runtime_root:
            runtime_path = Path(runtime_root)
            models = runtime_path / "models"
            models.mkdir(parents=True)
            for filename in ("ru_male.onnx", "ru_male_denis.onnx", "ru_male_ruslan.onnx", "en_male.onnx"):
                (models / filename).write_text("stub", encoding="utf-8")

            candidates = discover_ru_piper_candidates(runtime_path)

        self.assertEqual([candidate.key for candidate in candidates], ["denis", "dmitri", "ruslan"])
        self.assertEqual({candidate.display_name for candidate in candidates}, {"Russian Male (Denis)", "Russian Male (Dmitri)", "Russian Male (Ruslan)"})

    def test_render_samples_invokes_piper_and_writes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as runtime_root, tempfile.TemporaryDirectory() as output_dir:
            runtime_path = Path(runtime_root)
            models = runtime_path / "models"
            models.mkdir(parents=True)
            model_path = models / "ru_male_denis.onnx"
            model_path.write_text("stub", encoding="utf-8")
            config_path = Path(f"{model_path}.json")
            config_path.write_text("{}", encoding="utf-8")
            piper_path = runtime_path / "venv" / "bin" / "piper"
            piper_path.parent.mkdir(parents=True)
            piper_path.write_text("#!/bin/sh\n", encoding="utf-8")
            completed = MagicMock()
            completed.returncode = 0
            completed.stdout = ""
            completed.stderr = ""

            with patch("voice.tts_ab_samples.subprocess.run", return_value=completed) as run_mock:
                result = render_ru_ab_samples(
                    runtime_root=runtime_path,
                    output_dir=Path(output_dir),
                    phrases=("Проверка голоса.",),
                    candidate_keys=("denis",),
                )

            self.assertTrue(result.ok)
            run_mock.assert_called_once()
            command = run_mock.call_args.args[0]
            self.assertEqual(command[:3], [str(piper_path), "--model", str(model_path)])
            self.assertIn("--config", command)
            self.assertIn(str(config_path), command)
            self.assertEqual(run_mock.call_args.kwargs["input"], "Проверка голоса.")
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["candidates"][0]["key"], "denis")
        self.assertEqual(manifest["samples"][0]["candidate_key"], "denis")
        self.assertTrue(manifest["samples"][0]["ok"])

    def test_render_samples_rejects_unknown_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as runtime_root, tempfile.TemporaryDirectory() as output_dir:
            runtime_path = Path(runtime_root)
            models = runtime_path / "models"
            models.mkdir(parents=True)
            (models / "ru_male_denis.onnx").write_text("stub", encoding="utf-8")
            piper_path = runtime_path / "venv" / "bin" / "piper"
            piper_path.parent.mkdir(parents=True)
            piper_path.write_text("#!/bin/sh\n", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "Unknown candidate"):
                render_ru_ab_samples(
                    runtime_root=runtime_path,
                    output_dir=Path(output_dir),
                    phrases=("Проверка.",),
                    candidate_keys=("missing",),
                )


if __name__ == "__main__":
    unittest.main()
