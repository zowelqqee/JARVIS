"""Minimal smoke coverage for JARVIS CLI shell behavior."""

from __future__ import annotations

import io
import hashlib
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import cli
from input.voice_input import VoiceInputError


class CliSmokeTests(unittest.TestCase):
    """Protect the current CLI shell command behavior with small smoke tests."""

    def setUp(self) -> None:
        self.runtime_manager = MagicMock()
        self.session_context = MagicMock()

    def test_voice_aliases_capture_speech_before_runtime_dispatch(self) -> None:
        for command in ("voice", "/voice"):
            with self.subTest(command=command):
                with patch("cli.capture_voice_input", return_value="open browser") as capture_mock, patch(
                    "cli._handle_runtime_input"
                ) as runtime_mock:
                    should_exit, speak_enabled, output = self._run_command(command, speak_enabled=False)

                self.assertFalse(should_exit)
                self.assertFalse(speak_enabled)
                self.assertIn("voice: listening... speak now.", output)
                self.assertIn('recognized: "open browser"', output)
                capture_mock.assert_called_once_with(timeout_seconds=cli._VOICE_CAPTURE_TIMEOUT_SECONDS)
                runtime_mock.assert_called_once_with(
                    "open browser",
                    runtime_manager=self.runtime_manager,
                    session_context=self.session_context,
                    speak_enabled=False,
                )

    def test_voice_command_normalizes_repeated_open_phrase(self) -> None:
        with patch("cli.capture_voice_input", return_value="Open Safari open Safari") as capture_mock, patch(
            "cli._handle_runtime_input"
        ) as runtime_mock:
            should_exit, speak_enabled, output = self._run_command("voice", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn('recognized: "Open Safari"', output)
        capture_mock.assert_called_once_with(timeout_seconds=cli._VOICE_CAPTURE_TIMEOUT_SECONDS)
        runtime_mock.assert_called_once_with(
            "Open Safari",
            runtime_manager=self.runtime_manager,
            session_context=self.session_context,
            speak_enabled=False,
        )

    def test_voice_command_strips_jarvis_wake_prefix(self) -> None:
        with patch("cli.capture_voice_input", return_value="Jarvis close telegram") as capture_mock, patch(
            "cli._handle_runtime_input"
        ) as runtime_mock:
            should_exit, speak_enabled, output = self._run_command("voice", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn('recognized: "close telegram"', output)
        capture_mock.assert_called_once_with(timeout_seconds=cli._VOICE_CAPTURE_TIMEOUT_SECONDS)
        runtime_mock.assert_called_once_with(
            "close telegram",
            runtime_manager=self.runtime_manager,
            session_context=self.session_context,
            speak_enabled=False,
        )

    def test_voice_command_strips_jarvis_wake_prefix_with_punctuation(self) -> None:
        with patch("cli.capture_voice_input", return_value="Jarvis, open telegram") as capture_mock, patch(
            "cli._handle_runtime_input"
        ) as runtime_mock:
            should_exit, speak_enabled, output = self._run_command("voice", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn('recognized: "open telegram"', output)
        capture_mock.assert_called_once_with(timeout_seconds=cli._VOICE_CAPTURE_TIMEOUT_SECONDS)
        runtime_mock.assert_called_once_with(
            "open telegram",
            runtime_manager=self.runtime_manager,
            session_context=self.session_context,
            speak_enabled=False,
        )

    def test_voice_command_strips_hey_jarvis_prefix(self) -> None:
        with patch("cli.capture_voice_input", return_value="Hey Jarvis open safari") as capture_mock, patch(
            "cli._handle_runtime_input"
        ) as runtime_mock:
            should_exit, speak_enabled, output = self._run_command("voice", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn('recognized: "open safari"', output)
        capture_mock.assert_called_once_with(timeout_seconds=cli._VOICE_CAPTURE_TIMEOUT_SECONDS)
        runtime_mock.assert_called_once_with(
            "open safari",
            runtime_manager=self.runtime_manager,
            session_context=self.session_context,
            speak_enabled=False,
        )

    def test_voice_question_normalizes_repeated_question_phrase(self) -> None:
        with patch("cli.capture_voice_input", return_value="What can you do what can you do") as capture_mock, patch(
            "cli._handle_runtime_input"
        ) as runtime_mock:
            should_exit, speak_enabled, output = self._run_command("voice", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn('recognized: "What can you do"', output)
        capture_mock.assert_called_once_with(timeout_seconds=cli._VOICE_CAPTURE_TIMEOUT_SECONDS)
        runtime_mock.assert_called_once_with(
            "What can you do",
            runtime_manager=self.runtime_manager,
            session_context=self.session_context,
            speak_enabled=False,
        )

    def test_speak_aliases_toggle_without_runtime_dispatch(self) -> None:
        cases = [
            ("speak on", False, True, "Speech output enabled."),
            ("/speak on", False, True, "Speech output enabled."),
            ("speak off", True, False, "Speech output disabled."),
            ("/speak off", True, False, "Speech output disabled."),
        ]

        for command, initial_speak, expected_speak, expected_line in cases:
            with self.subTest(command=command):
                with patch("cli._handle_runtime_input") as runtime_mock:
                    should_exit, speak_enabled, output = self._run_command(command, speak_enabled=initial_speak)

                self.assertFalse(should_exit)
                self.assertEqual(speak_enabled, expected_speak)
                self.assertIn(expected_line, output)
                runtime_mock.assert_not_called()

    def test_voice_failure_shows_message_and_hint(self) -> None:
        error = VoiceInputError(
            "PERMISSION_DENIED",
            "Speech recognition permission was denied.",
            hint="Check macOS Settings -> Privacy & Security -> Microphone / Speech Recognition.",
        )

        with patch("cli.capture_voice_input", side_effect=error), patch("cli._handle_runtime_input") as runtime_mock:
            should_exit, speak_enabled, output = self._run_command("/voice", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("voice: Speech recognition permission was denied.", output)
        self.assertIn(
            "hint: Check macOS Settings -> Privacy & Security -> Microphone / Speech Recognition.",
            output,
        )
        runtime_mock.assert_not_called()

    def test_normal_command_reaches_runtime_path(self) -> None:
        with patch("cli.capture_voice_input") as capture_mock, patch("cli._handle_runtime_input") as runtime_mock:
            should_exit, speak_enabled, output = self._run_command("open browser", speak_enabled=True)

        self.assertFalse(should_exit)
        self.assertTrue(speak_enabled)
        self.assertEqual(output, "")
        capture_mock.assert_not_called()
        runtime_mock.assert_called_once_with(
            "open browser",
            runtime_manager=self.runtime_manager,
            session_context=self.session_context,
            speak_enabled=True,
        )

    def test_help_reset_quit_are_intercepted_before_runtime(self) -> None:
        with patch("cli._handle_runtime_input") as runtime_mock:
            should_exit, speak_enabled, help_output = self._run_command("help", speak_enabled=False)
            self.assertFalse(should_exit)
            self.assertFalse(speak_enabled)
            self.assertIn("Shell commands:", help_output)

            should_exit, speak_enabled, reset_output = self._run_command("reset", speak_enabled=False)
            self.assertFalse(should_exit)
            self.assertFalse(speak_enabled)
            self.assertIn("Runtime reset.", reset_output)
            self.runtime_manager.clear_runtime.assert_called()
            self.session_context.clear_expired_or_resettable_context.assert_called_with(
                preserve_recent_context=False
            )

            should_exit, speak_enabled, quit_output = self._run_command("quit", speak_enabled=False)
            self.assertTrue(should_exit)
            self.assertFalse(speak_enabled)
            self.assertEqual(quit_output, "")

        runtime_mock.assert_not_called()

    def test_qa_helper_commands_are_intercepted_before_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_artifact = str(Path(tmpdir) / "missing_live_smoke_artifact.json")
            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="deterministic",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=False,
                        fallback_enabled=True,
                        open_domain_enabled=False,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                    "JARVIS_QA_OPENAI_LIVE_ARTIFACT": missing_artifact,
                },
                clear=False,
            ):
                should_exit, speak_enabled, backend_output = self._run_command("qa backend", speak_enabled=False)
                self.assertFalse(should_exit)
                self.assertFalse(speak_enabled)
                self.assertIn("qa backend: deterministic", backend_output)
                self.assertIn("llm provider: openai_responses", backend_output)

                should_exit, speak_enabled, model_output = self._run_command("qa model", speak_enabled=False)
                self.assertFalse(should_exit)
                self.assertFalse(speak_enabled)
                self.assertIn("qa model: gpt-5-nano", model_output)
                self.assertIn("reasoning effort: minimal", model_output)

                should_exit, speak_enabled, smoke_output = self._run_command("qa smoke", speak_enabled=False)
                self.assertFalse(should_exit)
                self.assertFalse(speak_enabled)
                self.assertIn("qa smoke command: scripts/run_openai_live_smoke.sh", smoke_output)
                self.assertIn("api key env: OPENAI_API_KEY (present)", smoke_output)
                self.assertIn("debug flag: JARVIS_QA_DEBUG (missing)", smoke_output)
                self.assertIn("live smoke artifact:", smoke_output)
                self.assertIn("(missing)", smoke_output)
                self.assertIn("open-domain live verification: no", smoke_output)

                should_exit, speak_enabled, gate_output = self._run_command("qa gate", speak_enabled=False)
                self.assertFalse(should_exit)
                self.assertFalse(speak_enabled)
                self.assertIn("qa gate candidate: llm_env", gate_output)
                self.assertIn("fallback: on", gate_output)
                self.assertIn("precheck: blocked", gate_output)
                self.assertIn("blocker: open-domain question answering is disabled", gate_output)
                self.assertIn("blocker: live smoke artifact is missing", gate_output)
                self.assertIn("smoke command: scripts/run_openai_live_smoke.sh llm_env", gate_output)
                self.assertIn(
                    "compare command: scripts/run_qa_rollout_gate.sh llm_env",
                    gate_output,
                )

                should_exit, speak_enabled, strict_gate_output = self._run_command("qa gate strict", speak_enabled=False)
                self.assertFalse(should_exit)
                self.assertFalse(speak_enabled)
                self.assertIn("qa gate candidate: llm_env_strict", strict_gate_output)
                self.assertIn("fallback: off", strict_gate_output)
                self.assertIn("precheck: blocked", strict_gate_output)
                self.assertIn("blocker: open-domain question answering is disabled", strict_gate_output)
                self.assertIn("smoke command: scripts/run_openai_live_smoke.sh llm_env_strict", strict_gate_output)
                self.assertIn(
                    "compare command: scripts/run_qa_rollout_gate.sh llm_env_strict",
                    strict_gate_output,
                )

                should_exit, speak_enabled, beta_output = self._run_command("qa beta", speak_enabled=False)
                self.assertFalse(should_exit)
                self.assertFalse(speak_enabled)
                self.assertIn("qa beta stage: alpha_opt_in", beta_output)
                self.assertIn("qa beta default path: deterministic", beta_output)
                self.assertIn("qa beta recommended candidate: none", beta_output)
                self.assertIn("qa beta manual checklist artifact:", beta_output)
                self.assertIn("qa beta manual checklist pending items:", beta_output)
                self.assertIn("qa beta manual checklist helper command: qa checklist", beta_output)
                self.assertIn("qa beta manual checklist guide command: python3 -m qa.manual_beta_checklist", beta_output)
                self.assertIn("arbitrary_factual_question", beta_output)
                self.assertIn("provider_unavailable_path", beta_output)
                self.assertIn(
                    "qa beta release review pending checks: latency_review, cost_review, operator_signoff, product_approval",
                    beta_output,
                )
                self.assertIn("qa beta recorded candidate: none", beta_output)
                self.assertIn("qa beta decision artifact:", beta_output)
                self.assertIn("(missing)", beta_output)
                self.assertIn("qa beta decision artifact fresh: n/a", beta_output)
                self.assertIn("qa beta decision artifact consistent with latest evidence: n/a", beta_output)
                self.assertIn("qa beta decision: blocked until beta_question_default is explicitly approved", beta_output)
                self.assertIn("qa beta technical precheck: blocked", beta_output)
                self.assertIn("candidate llm_env: blocked", beta_output)
                self.assertIn("candidate llm_env_strict: blocked", beta_output)
                self.assertIn("manual checklist doc: docs/manual_verification_commands.md", beta_output)
                self.assertIn("decision gate doc: docs/llm_default_decision_gate.md", beta_output)

        runtime_mock.assert_not_called()

    def test_qa_smoke_reports_green_artifact_and_open_domain_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "openai_live_smoke.json"
            artifact_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-25T00:00:00+00:00",
                        "question": "Who is the president of France?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=False,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                    "JARVIS_QA_OPENAI_LIVE_ARTIFACT": str(artifact_path),
                },
                clear=False,
            ):
                should_exit, speak_enabled, smoke_output = self._run_command("qa smoke", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn(f"live smoke artifact: {artifact_path} (green)", smoke_output)
        self.assertIn("open-domain live verification: yes", smoke_output)
        runtime_mock.assert_not_called()

    def test_qa_gate_reports_green_matching_precheck(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "openai_live_smoke.json"
            artifact_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-25T00:00:00+00:00",
                        "question": "Who is the president of France?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 25, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=False,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                    "JARVIS_QA_OPENAI_LIVE_ARTIFACT": str(artifact_path),
                },
                clear=False,
            ):
                should_exit, speak_enabled, gate_output = self._run_command("qa gate", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("qa gate candidate: llm_env", gate_output)
        self.assertIn(f"live smoke artifact: {artifact_path} (green)", gate_output)
        self.assertIn("live smoke artifact fresh: yes (0.0h)", gate_output)
        self.assertIn("live smoke artifact matches profile: yes", gate_output)
        self.assertIn("open-domain live verification: yes", gate_output)
        self.assertIn("precheck: ready", gate_output)
        self.assertIn("smoke command: scripts/run_openai_live_smoke.sh llm_env", gate_output)
        self.assertIn(
            "compare command: scripts/run_qa_rollout_gate.sh llm_env",
            gate_output,
        )
        self.assertNotIn("blocker:", gate_output)
        runtime_mock.assert_not_called()

    def test_qa_gate_uses_candidate_default_artifact_path_without_env_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "openai_live_smoke_llm_env.json"
            artifact_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-25T00:00:00+00:00",
                        "question": "Who is the president of France?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 25, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.live_smoke_artifact_path_for_candidate",
                return_value=artifact_path,
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=False,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                },
                clear=False,
            ):
                should_exit, speak_enabled, gate_output = self._run_command("qa gate", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn(f"live smoke artifact: {artifact_path} (green)", gate_output)
        self.assertIn("precheck: ready", gate_output)
        runtime_mock.assert_not_called()

    def test_qa_beta_reports_ready_candidates_when_artifacts_are_fresh_and_matching(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_llm_env = Path(tmpdir) / "openai_live_smoke_llm_env.json"
            artifact_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            artifact_llm_env_strict = Path(tmpdir) / "openai_live_smoke_llm_env_strict.json"
            artifact_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": False,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env = Path(tmpdir) / "rollout_stability_llm_env.json"
            stability_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env_strict = Path(tmpdir) / "rollout_stability_llm_env_strict.json"
            stability_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env_strict",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )

            def _artifact_for_candidate(candidate_profile: str | None) -> Path:
                if candidate_profile == "llm_env_strict":
                    return artifact_llm_env_strict
                return artifact_llm_env

            def _stability_for_candidate(candidate_profile: str) -> Path:
                if candidate_profile == "llm_env_strict":
                    return stability_llm_env_strict
                return stability_llm_env

            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 26, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.live_smoke_artifact_path_for_candidate",
                side_effect=_artifact_for_candidate,
            ), patch(
                "cli.rollout_stability_artifact_path_for_candidate",
                side_effect=_stability_for_candidate,
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=True,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                },
                clear=False,
            ):
                should_exit, speak_enabled, beta_output = self._run_command("qa beta", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("qa beta stage: alpha_opt_in", beta_output)
        self.assertIn("qa beta technical precheck: ready (llm_env, llm_env_strict)", beta_output)
        self.assertIn("qa beta latest stability evidence: clean (llm_env, llm_env_strict)", beta_output)
        self.assertIn("qa beta recommended candidate: llm_env_strict", beta_output)
        self.assertIn("qa beta manual checklist artifact:", beta_output)
        self.assertIn("qa beta manual checklist pending items:", beta_output)
        self.assertIn("qa beta manual checklist helper command: qa checklist", beta_output)
        self.assertIn("qa beta manual checklist guide command: python3 -m qa.manual_beta_checklist", beta_output)
        self.assertIn("(missing)", beta_output)
        self.assertIn("qa beta manual checklist artifact fresh: n/a", beta_output)
        self.assertIn("qa beta release review artifact fresh: n/a", beta_output)
        self.assertIn(
            "qa beta release review pending checks: latency_review, cost_review, operator_signoff, product_approval",
            beta_output,
        )
        self.assertIn("qa beta recorded candidate: none", beta_output)
        self.assertIn("qa beta decision artifact:", beta_output)
        self.assertIn("(missing)", beta_output)
        self.assertIn("qa beta decision artifact fresh: n/a", beta_output)
        self.assertIn("qa beta decision artifact consistent with latest evidence: n/a", beta_output)
        self.assertIn("candidate llm_env: ready", beta_output)
        self.assertIn("candidate llm_env_strict: ready", beta_output)
        self.assertIn("stability=green(2/2)", beta_output)
        self.assertIn("stability-fresh=yes", beta_output)
        self.assertIn("fallback=on", beta_output)
        self.assertIn("fallback=off", beta_output)
        self.assertIn("next beta step: complete the manual beta checklist artifact before release sign-off.", beta_output)
        self.assertIn("manual checklist command: python3 -m qa.manual_beta_checklist --all-passed --write-artifact", beta_output)
        self.assertIn("qa beta manual checklist scenario guide:", beta_output)
        self.assertIn("  - arbitrary_factual_question: Arbitrary factual question", beta_output)
        self.assertIn("    input: who is the president of France?", beta_output)
        self.assertIn(
            "    env: JARVIS_QA_BACKEND=llm JARVIS_QA_LLM_ENABLED=true JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED=true",
            beta_output,
        )
        self.assertIn(
            "    expected: mode=question; answer-kind=open_domain_model; provenance=model_knowledge; no fake local sources",
            beta_output,
        )
        self.assertIn("note: this helper is offline; it does not run smoke, gate, or stability", beta_output)
        runtime_mock.assert_not_called()

    def test_cli_shell_exposes_release_decision_helper_commands(self) -> None:
        with patch("cli._handle_runtime_input") as runtime_mock, patch(
            "cli.load_manual_beta_checklist_artifact",
            return_value=(Path("/tmp/manual_beta_checklist.json"), None, None),
        ), patch(
            "cli.build_manual_beta_checklist_record",
            return_value=object(),
        ) as checklist_build_mock, patch(
            "cli.format_manual_beta_checklist_record",
            return_value="CHECKLIST SUMMARY",
        ), patch(
            "cli.load_beta_release_review_artifact",
            return_value=(Path("/tmp/beta_release_review.json"), None, None),
        ), patch(
            "cli.build_beta_release_review_record",
            return_value=object(),
        ) as review_build_mock, patch(
            "cli.format_beta_release_review_record",
            return_value="RELEASE REVIEW SUMMARY",
        ), patch(
            "cli.build_beta_readiness_record",
            return_value=object(),
        ) as readiness_build_mock, patch(
            "cli.format_beta_readiness_record",
            return_value="READINESS SUMMARY",
        ):
            should_exit, speak_enabled, checklist_output = self._run_command("qa checklist", speak_enabled=False)
            self.assertFalse(should_exit)
            self.assertFalse(speak_enabled)
            self.assertIn("CHECKLIST SUMMARY", checklist_output)
            checklist_build_mock.assert_called_once_with(existing_payload=None)

            should_exit, speak_enabled, review_output = self._run_command("qa release review", speak_enabled=False)
            self.assertFalse(should_exit)
            self.assertFalse(speak_enabled)
            self.assertIn("RELEASE REVIEW SUMMARY", review_output)
            review_build_mock.assert_called_once_with(existing_payload=None)

            should_exit, speak_enabled, readiness_output = self._run_command("qa readiness", speak_enabled=False)
            self.assertFalse(should_exit)
            self.assertFalse(speak_enabled)
            self.assertIn("READINESS SUMMARY", readiness_output)
            readiness_build_mock.assert_called_once_with()

        runtime_mock.assert_not_called()

    def test_qa_beta_reports_stale_manual_checklist_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_llm_env = Path(tmpdir) / "openai_live_smoke_llm_env.json"
            artifact_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            artifact_llm_env_strict = Path(tmpdir) / "openai_live_smoke_llm_env_strict.json"
            artifact_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": False,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env = Path(tmpdir) / "rollout_stability_llm_env.json"
            stability_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env_strict = Path(tmpdir) / "rollout_stability_llm_env_strict.json"
            stability_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env_strict",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            manual_artifact, _manual_created_at, _manual_sha256 = self._write_complete_manual_beta_checklist(tmpdir)
            manual_payload = json.loads(manual_artifact.read_text(encoding="utf-8"))
            manual_payload["created_at"] = "2026-03-24T00:00:00+00:00"
            manual_artifact.write_text(json.dumps(manual_payload, indent=2, sort_keys=True), encoding="utf-8")
            stale_manual_sha256 = hashlib.sha256(manual_artifact.read_bytes()).hexdigest()
            release_review_artifact, _release_review_created_at, _release_review_sha256 = (
                self._write_complete_beta_release_review(
                    tmpdir,
                    candidate_profile="llm_env_strict",
                    manual_created_at="2026-03-24T00:00:00+00:00",
                    manual_sha256=stale_manual_sha256,
                )
            )

            def _artifact_for_candidate(candidate_profile: str | None) -> Path:
                if candidate_profile == "llm_env_strict":
                    return artifact_llm_env_strict
                return artifact_llm_env

            def _stability_for_candidate(candidate_profile: str) -> Path:
                if candidate_profile == "llm_env_strict":
                    return stability_llm_env_strict
                return stability_llm_env

            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 26, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.live_smoke_artifact_path_for_candidate",
                side_effect=_artifact_for_candidate,
            ), patch(
                "cli.rollout_stability_artifact_path_for_candidate",
                side_effect=_stability_for_candidate,
            ), patch(
                "cli.manual_beta_checklist_artifact_path",
                return_value=manual_artifact,
            ), patch(
                "cli.beta_release_review_artifact_path",
                return_value=release_review_artifact,
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=True,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                },
                clear=False,
            ):
                should_exit, speak_enabled, beta_output = self._run_command("qa beta", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("qa beta manual checklist artifact fresh: no (48.0h)", beta_output)
        self.assertIn("qa beta release review artifact consistent with latest evidence: no", beta_output)
        self.assertIn(
            "qa beta release review artifact consistency reason: latest manual checklist artifact is stale",
            beta_output,
        )
        self.assertIn("next beta step: complete the manual beta checklist artifact before release sign-off.", beta_output)
        runtime_mock.assert_not_called()

    def test_qa_beta_reports_failed_stability_blockers_from_latest_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_llm_env = Path(tmpdir) / "openai_live_smoke_llm_env.json"
            artifact_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            artifact_llm_env_strict = Path(tmpdir) / "openai_live_smoke_llm_env_strict.json"
            artifact_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": False,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env = Path(tmpdir) / "rollout_stability_llm_env.json"
            stability_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env",
                            "runs_requested": 2,
                            "gate_passes": 0,
                            "runs": [],
                            "blocker_counts": {
                                "open-domain answer pass rate is below threshold": 1,
                                "fallback frequency is above threshold": 1,
                            },
                            "failed_case_counts": {},
                            "fallback_case_counts": {
                                "route_mixed_interaction_answer_reply": 1,
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env_strict = Path(tmpdir) / "rollout_stability_llm_env_strict.json"
            stability_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env_strict",
                            "runs_requested": 2,
                            "gate_passes": 0,
                            "runs": [],
                            "blocker_counts": {
                                "open-domain answer pass rate is below threshold": 2,
                            },
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )

            def _artifact_for_candidate(candidate_profile: str | None) -> Path:
                if candidate_profile == "llm_env_strict":
                    return artifact_llm_env_strict
                return artifact_llm_env

            def _stability_for_candidate(candidate_profile: str) -> Path:
                if candidate_profile == "llm_env_strict":
                    return stability_llm_env_strict
                return stability_llm_env

            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 26, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.live_smoke_artifact_path_for_candidate",
                side_effect=_artifact_for_candidate,
            ), patch(
                "cli.rollout_stability_artifact_path_for_candidate",
                side_effect=_stability_for_candidate,
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=True,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                },
                clear=False,
            ):
                should_exit, speak_enabled, beta_output = self._run_command("qa beta", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("qa beta recommended candidate: none", beta_output)
        self.assertIn("qa beta manual checklist artifact:", beta_output)
        self.assertIn("qa beta decision artifact fresh: n/a", beta_output)
        self.assertIn("qa beta decision artifact consistent with latest evidence: n/a", beta_output)
        self.assertIn("qa beta latest stability evidence: incomplete", beta_output)
        self.assertIn("candidate llm_env: ready", beta_output)
        self.assertIn("stability=failed(0/2)", beta_output)
        self.assertIn(
            "stability-blockers=open-domain answer pass rate is below threshold x1; fallback frequency is above threshold x1",
            beta_output,
        )
        self.assertIn(
            "stability-fallback-cases=route_mixed_interaction_answer_reply x1",
            beta_output,
        )
        runtime_mock.assert_not_called()

    def test_qa_beta_reports_release_review_artifact_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_llm_env = Path(tmpdir) / "openai_live_smoke_llm_env.json"
            artifact_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            artifact_llm_env_strict = Path(tmpdir) / "openai_live_smoke_llm_env_strict.json"
            artifact_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": False,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env = Path(tmpdir) / "rollout_stability_llm_env.json"
            stability_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env_strict = Path(tmpdir) / "rollout_stability_llm_env_strict.json"
            stability_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env_strict",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            manual_artifact, manual_created_at, manual_sha256 = self._write_complete_manual_beta_checklist(tmpdir)
            release_review_artifact, _release_review_created_at, _release_review_sha256 = (
                self._write_complete_beta_release_review(
                    tmpdir,
                    candidate_profile="llm_env_strict",
                    manual_created_at=manual_created_at,
                    manual_sha256=manual_sha256,
                )
            )
            manual_artifact.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.manual_beta_checklist",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "checklist_id": "beta_question_default",
                            "passed_items": 7,
                            "total_items": 7,
                            "all_passed": True,
                            "items": {},
                            "notes": "rerun after release review",
                        },
                    }
                ),
                encoding="utf-8",
            )

            def _artifact_for_candidate(candidate_profile: str | None) -> Path:
                if candidate_profile == "llm_env_strict":
                    return artifact_llm_env_strict
                return artifact_llm_env

            def _stability_for_candidate(candidate_profile: str) -> Path:
                if candidate_profile == "llm_env_strict":
                    return stability_llm_env_strict
                return stability_llm_env

            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 26, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.live_smoke_artifact_path_for_candidate",
                side_effect=_artifact_for_candidate,
            ), patch(
                "cli.rollout_stability_artifact_path_for_candidate",
                side_effect=_stability_for_candidate,
            ), patch(
                "cli.manual_beta_checklist_artifact_path",
                return_value=manual_artifact,
            ), patch(
                "cli.beta_release_review_artifact_path",
                return_value=release_review_artifact,
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=True,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                },
                clear=False,
            ):
                should_exit, speak_enabled, beta_output = self._run_command("qa beta", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("qa beta release review artifact consistent with latest evidence: no", beta_output)
        self.assertIn(
            "qa beta release review artifact consistency reason: recorded manual checklist artifact fingerprint no longer matches the latest artifact",
            beta_output,
        )
        self.assertIn(
            "release review command: python3 -m qa.beta_release_review --candidate-profile llm_env_strict --latency-reviewed --cost-reviewed --operator-signoff --product-approval --write-artifact",
            beta_output,
        )
        runtime_mock.assert_not_called()

    def test_qa_beta_uses_incremental_commands_for_partial_manual_and_release_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_llm_env = Path(tmpdir) / "openai_live_smoke_llm_env.json"
            artifact_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            artifact_llm_env_strict = Path(tmpdir) / "openai_live_smoke_llm_env_strict.json"
            artifact_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": False,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env = Path(tmpdir) / "rollout_stability_llm_env.json"
            stability_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env_strict = Path(tmpdir) / "rollout_stability_llm_env_strict.json"
            stability_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env_strict",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            manual_artifact = Path(tmpdir) / "manual_beta_checklist.json"
            manual_artifact.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.manual_beta_checklist",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "checklist_id": "beta_question_default",
                            "passed_items": 5,
                            "total_items": 7,
                            "all_passed": False,
                            "items": {
                                "arbitrary_factual_question": {"label": "Arbitrary factual question", "passed": True},
                                "arbitrary_explanation_question": {"label": "Arbitrary explanation question", "passed": True},
                                "casual_chat_question": {"label": "Casual chat question", "passed": True},
                                "blocked_state_question": {"label": "Blocked-state question", "passed": False},
                                "grounded_docs_question": {"label": "Grounded docs question", "passed": True},
                                "mixed_question_command": {"label": "Mixed question + command", "passed": True},
                                "provider_unavailable_path": {"label": "Provider unavailable path", "passed": False},
                            },
                            "notes": "",
                        },
                    }
                ),
                encoding="utf-8",
            )
            release_review_artifact = Path(tmpdir) / "beta_release_review.json"
            release_review_artifact.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.beta_release_review",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "review_id": "beta_question_default",
                            "candidate_profile": "llm_env_strict",
                            "candidate_selection_source": "explicit",
                            "completed_checks": 2,
                            "total_checks": 4,
                            "all_completed": False,
                            "manual_checklist_artifact_status": "complete",
                            "manual_checklist_artifact_completed": True,
                            "manual_checklist_items_passed": 7,
                            "manual_checklist_items_total": 7,
                            "manual_checklist_artifact_fresh": True,
                            "manual_checklist_artifact_created_at": "2026-03-26T00:00:00+00:00",
                            "manual_checklist_artifact_sha256": hashlib.sha256(manual_artifact.read_bytes()).hexdigest(),
                            "checks": {
                                "latency_review": {"label": "Latency review", "completed": True},
                                "cost_review": {"label": "Cost review", "completed": False},
                                "operator_signoff": {"label": "Operator sign-off", "completed": False},
                                "product_approval": {"label": "Product approval", "completed": True},
                            },
                            "notes": "",
                        },
                    }
                ),
                encoding="utf-8",
            )

            def _artifact_for_candidate(candidate_profile: str | None) -> Path:
                if candidate_profile == "llm_env_strict":
                    return artifact_llm_env_strict
                return artifact_llm_env

            def _stability_for_candidate(candidate_profile: str) -> Path:
                if candidate_profile == "llm_env_strict":
                    return stability_llm_env_strict
                return stability_llm_env

            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 26, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.live_smoke_artifact_path_for_candidate",
                side_effect=_artifact_for_candidate,
            ), patch(
                "cli.rollout_stability_artifact_path_for_candidate",
                side_effect=_stability_for_candidate,
            ), patch(
                "cli.manual_beta_checklist_artifact_path",
                return_value=manual_artifact,
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=True,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                },
                clear=False,
            ):
                should_exit, speak_enabled, beta_output = self._run_command("qa beta", speak_enabled=False)

            self.assertFalse(should_exit)
            self.assertFalse(speak_enabled)
            self.assertIn(
                "manual checklist command: python3 -m qa.manual_beta_checklist --pass blocked_state_question --pass provider_unavailable_path --write-artifact",
                beta_output,
            )
            self.assertIn("qa beta manual checklist helper command: qa checklist", beta_output)
            self.assertIn("qa beta manual checklist guide command: python3 -m qa.manual_beta_checklist", beta_output)
            self.assertIn("qa beta manual checklist scenario guide:", beta_output)
            self.assertIn("  - blocked_state_question: Blocked-state question", beta_output)
            self.assertIn("    input: close Telegram -> what exactly do you need me to confirm?", beta_output)
            self.assertIn(
                "    expected: awaiting_confirmation first; then grounded read-only explanation of the current confirmation boundary",
                beta_output,
            )
            runtime_mock.assert_not_called()

            manual_payload = json.loads(manual_artifact.read_text(encoding="utf-8"))
            manual_payload["report"]["all_passed"] = True
            manual_payload["report"]["passed_items"] = 7
            for item_state in manual_payload["report"]["items"].values():
                item_state["passed"] = True
            manual_artifact.write_text(json.dumps(manual_payload, indent=2, sort_keys=True), encoding="utf-8")
            release_review_payload = json.loads(release_review_artifact.read_text(encoding="utf-8"))
            release_review_payload["report"]["manual_checklist_artifact_created_at"] = str(manual_payload["created_at"])
            release_review_payload["report"]["manual_checklist_artifact_sha256"] = hashlib.sha256(
                manual_artifact.read_bytes()
            ).hexdigest()
            release_review_artifact.write_text(
                json.dumps(release_review_payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )

            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 26, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.live_smoke_artifact_path_for_candidate",
                side_effect=_artifact_for_candidate,
            ), patch(
                "cli.rollout_stability_artifact_path_for_candidate",
                side_effect=_stability_for_candidate,
            ), patch(
                "cli.manual_beta_checklist_artifact_path",
                return_value=manual_artifact,
            ), patch(
                "cli.beta_release_review_artifact_path",
                return_value=release_review_artifact,
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=True,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                },
                clear=False,
            ):
                should_exit, speak_enabled, beta_output = self._run_command("qa beta", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn(
            "release review command: python3 -m qa.beta_release_review --candidate-profile llm_env_strict --cost-reviewed --operator-signoff --write-artifact",
            beta_output,
        )
        runtime_mock.assert_not_called()

    def test_qa_beta_uses_full_rerun_commands_for_stale_partial_supporting_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_llm_env = Path(tmpdir) / "openai_live_smoke_llm_env.json"
            artifact_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            artifact_llm_env_strict = Path(tmpdir) / "openai_live_smoke_llm_env_strict.json"
            artifact_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": False,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env = Path(tmpdir) / "rollout_stability_llm_env.json"
            stability_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env_strict = Path(tmpdir) / "rollout_stability_llm_env_strict.json"
            stability_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env_strict",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            manual_artifact = Path(tmpdir) / "manual_beta_checklist.json"
            manual_artifact.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.manual_beta_checklist",
                        "created_at": "2026-03-24T00:00:00+00:00",
                        "report": {
                            "checklist_id": "beta_question_default",
                            "passed_items": 5,
                            "total_items": 7,
                            "all_passed": False,
                            "items": {
                                "arbitrary_factual_question": {"label": "Arbitrary factual question", "passed": True},
                                "arbitrary_explanation_question": {"label": "Arbitrary explanation question", "passed": True},
                                "casual_chat_question": {"label": "Casual chat question", "passed": True},
                                "blocked_state_question": {"label": "Blocked-state question", "passed": False},
                                "grounded_docs_question": {"label": "Grounded docs question", "passed": True},
                                "mixed_question_command": {"label": "Mixed question + command", "passed": True},
                                "provider_unavailable_path": {"label": "Provider unavailable path", "passed": False},
                            },
                            "notes": "",
                        },
                    }
                ),
                encoding="utf-8",
            )

            def _artifact_for_candidate(candidate_profile: str | None) -> Path:
                if candidate_profile == "llm_env_strict":
                    return artifact_llm_env_strict
                return artifact_llm_env

            def _stability_for_candidate(candidate_profile: str) -> Path:
                if candidate_profile == "llm_env_strict":
                    return stability_llm_env_strict
                return stability_llm_env

            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 26, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.live_smoke_artifact_path_for_candidate",
                side_effect=_artifact_for_candidate,
            ), patch(
                "cli.rollout_stability_artifact_path_for_candidate",
                side_effect=_stability_for_candidate,
            ), patch(
                "cli.manual_beta_checklist_artifact_path",
                return_value=manual_artifact,
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=True,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                },
                clear=False,
            ):
                should_exit, speak_enabled, beta_output = self._run_command("qa beta", speak_enabled=False)

            self.assertFalse(should_exit)
            self.assertFalse(speak_enabled)
            self.assertIn("qa beta manual checklist artifact fresh: no (48.0h)", beta_output)
            self.assertIn(
                "manual checklist command: python3 -m qa.manual_beta_checklist --all-passed --write-artifact",
                beta_output,
            )
            self.assertIn("qa beta manual checklist helper command: qa checklist", beta_output)
            self.assertIn("qa beta manual checklist guide command: python3 -m qa.manual_beta_checklist", beta_output)
            self.assertIn("qa beta manual checklist scenario guide:", beta_output)
            runtime_mock.assert_not_called()

            manual_artifact.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.manual_beta_checklist",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "checklist_id": "beta_question_default",
                            "passed_items": 7,
                            "total_items": 7,
                            "all_passed": True,
                            "items": {
                                "arbitrary_factual_question": {"label": "Arbitrary factual question", "passed": True},
                                "arbitrary_explanation_question": {"label": "Arbitrary explanation question", "passed": True},
                                "casual_chat_question": {"label": "Casual chat question", "passed": True},
                                "blocked_state_question": {"label": "Blocked-state question", "passed": True},
                                "grounded_docs_question": {"label": "Grounded docs question", "passed": True},
                                "mixed_question_command": {"label": "Mixed question + command", "passed": True},
                                "provider_unavailable_path": {"label": "Provider unavailable path", "passed": True},
                            },
                            "notes": "",
                        },
                    }
                ),
                encoding="utf-8",
            )
            release_review_artifact = Path(tmpdir) / "beta_release_review.json"
            release_review_artifact.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.beta_release_review",
                        "created_at": "2026-03-24T00:00:00+00:00",
                        "report": {
                            "review_id": "beta_question_default",
                            "candidate_profile": "llm_env_strict",
                            "candidate_selection_source": "explicit",
                            "completed_checks": 2,
                            "total_checks": 4,
                            "all_completed": False,
                            "manual_checklist_artifact_status": "complete",
                            "manual_checklist_artifact_completed": True,
                            "manual_checklist_items_passed": 7,
                            "manual_checklist_items_total": 7,
                            "manual_checklist_artifact_fresh": True,
                            "manual_checklist_artifact_created_at": "2026-03-26T00:00:00+00:00",
                            "manual_checklist_artifact_sha256": hashlib.sha256(manual_artifact.read_bytes()).hexdigest(),
                            "checks": {
                                "latency_review": {"label": "Latency review", "completed": True},
                                "cost_review": {"label": "Cost review", "completed": False},
                                "operator_signoff": {"label": "Operator sign-off", "completed": False},
                                "product_approval": {"label": "Product approval", "completed": True},
                            },
                            "notes": "",
                        },
                    }
                ),
                encoding="utf-8",
            )

            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 26, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.live_smoke_artifact_path_for_candidate",
                side_effect=_artifact_for_candidate,
            ), patch(
                "cli.rollout_stability_artifact_path_for_candidate",
                side_effect=_stability_for_candidate,
            ), patch(
                "cli.manual_beta_checklist_artifact_path",
                return_value=manual_artifact,
            ), patch(
                "cli.beta_release_review_artifact_path",
                return_value=release_review_artifact,
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=True,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                },
                clear=False,
            ):
                should_exit, speak_enabled, beta_output = self._run_command("qa beta", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("qa beta release review artifact fresh: no (48.0h)", beta_output)
        self.assertIn(
            "release review command: python3 -m qa.beta_release_review --candidate-profile llm_env_strict --latency-reviewed --cost-reviewed --operator-signoff --product-approval --write-artifact",
            beta_output,
        )
        runtime_mock.assert_not_called()

    def test_qa_beta_reports_recorded_beta_readiness_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_llm_env = Path(tmpdir) / "openai_live_smoke_llm_env.json"
            artifact_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            artifact_llm_env_strict = Path(tmpdir) / "openai_live_smoke_llm_env_strict.json"
            artifact_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": False,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env = Path(tmpdir) / "rollout_stability_llm_env.json"
            stability_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env_strict = Path(tmpdir) / "rollout_stability_llm_env_strict.json"
            stability_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env_strict",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            manual_artifact, manual_created_at, manual_sha256 = self._write_complete_manual_beta_checklist(tmpdir)
            release_review_artifact, release_review_created_at, release_review_sha256 = self._write_complete_beta_release_review(
                tmpdir,
                candidate_profile="llm_env_strict",
                manual_created_at=manual_created_at,
                manual_sha256=manual_sha256,
            )
            beta_artifact = self._write_ready_beta_readiness_artifact(
                tmpdir,
                artifact_llm_env=artifact_llm_env,
                artifact_llm_env_strict=artifact_llm_env_strict,
                stability_llm_env=stability_llm_env,
                stability_llm_env_strict=stability_llm_env_strict,
                manual_created_at=manual_created_at,
                manual_sha256=manual_sha256,
                release_review_created_at=release_review_created_at,
                release_review_sha256=release_review_sha256,
            )

            def _artifact_for_candidate(candidate_profile: str | None) -> Path:
                if candidate_profile == "llm_env_strict":
                    return artifact_llm_env_strict
                return artifact_llm_env

            def _stability_for_candidate(candidate_profile: str) -> Path:
                if candidate_profile == "llm_env_strict":
                    return stability_llm_env_strict
                return stability_llm_env

            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 26, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.live_smoke_artifact_path_for_candidate",
                side_effect=_artifact_for_candidate,
            ), patch(
                "cli.rollout_stability_artifact_path_for_candidate",
                side_effect=_stability_for_candidate,
            ), patch(
                "cli.beta_readiness_artifact_path",
                return_value=beta_artifact,
            ), patch(
                "cli.manual_beta_checklist_artifact_path",
                return_value=manual_artifact,
            ), patch(
                "cli.beta_release_review_artifact_path",
                return_value=release_review_artifact,
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=True,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                },
                clear=False,
            ):
                should_exit, speak_enabled, beta_output = self._run_command("qa beta", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("qa beta recorded candidate: llm_env_strict", beta_output)
        self.assertIn("qa beta recorded candidate selection: explicit", beta_output)
        self.assertIn("qa beta manual checklist artifact:", beta_output)
        self.assertIn("(complete(7/7))", beta_output)
        self.assertIn("qa beta release review artifact:", beta_output)
        self.assertIn("qa beta release review candidate: llm_env_strict", beta_output)
        self.assertIn("qa beta decision artifact:", beta_output)
        self.assertIn("(ready)", beta_output)
        self.assertIn("qa beta decision artifact fresh: yes", beta_output)
        self.assertIn("qa beta decision artifact consistent with latest evidence: yes", beta_output)
        self.assertIn(
            "qa beta recorded checks: manual=yes, review=yes, latency=yes, cost=yes, signoff=yes, approval=yes",
            beta_output,
        )
        self.assertIn(
            "qa beta decision: recorded as ready for explicit beta_question_default review; default remains unchanged",
            beta_output,
        )
        self.assertIn(
            "next beta step: offline beta evidence is already recorded; any rollout-stage or default-path change remains a separate explicit product decision.",
            beta_output,
        )
        self.assertNotIn("beta readiness command:", beta_output)
        runtime_mock.assert_not_called()

    def test_qa_beta_rejects_release_review_artifact_without_explicit_candidate_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_llm_env = Path(tmpdir) / "openai_live_smoke_llm_env.json"
            artifact_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            artifact_llm_env_strict = Path(tmpdir) / "openai_live_smoke_llm_env_strict.json"
            artifact_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": False,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env = Path(tmpdir) / "rollout_stability_llm_env.json"
            stability_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env_strict = Path(tmpdir) / "rollout_stability_llm_env_strict.json"
            stability_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env_strict",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            manual_artifact, manual_created_at, manual_sha256 = self._write_complete_manual_beta_checklist(tmpdir)
            release_review_artifact, _release_review_created_at, _release_review_sha256 = self._write_complete_beta_release_review(
                tmpdir,
                candidate_profile="llm_env_strict",
                manual_created_at=manual_created_at,
                manual_sha256=manual_sha256,
            )
            release_review_payload = json.loads(release_review_artifact.read_text(encoding="utf-8"))
            del release_review_payload["report"]["candidate_selection_source"]
            release_review_artifact.write_text(json.dumps(release_review_payload), encoding="utf-8")

            def _artifact_for_candidate(candidate_profile: str | None) -> Path:
                if candidate_profile == "llm_env_strict":
                    return artifact_llm_env_strict
                return artifact_llm_env

            def _stability_for_candidate(candidate_profile: str) -> Path:
                if candidate_profile == "llm_env_strict":
                    return stability_llm_env_strict
                return stability_llm_env

            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 26, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.live_smoke_artifact_path_for_candidate",
                side_effect=_artifact_for_candidate,
            ), patch(
                "cli.rollout_stability_artifact_path_for_candidate",
                side_effect=_stability_for_candidate,
            ), patch(
                "cli.beta_readiness_artifact_path",
                return_value=Path(tmpdir) / "beta_readiness.json",
            ), patch(
                "cli.manual_beta_checklist_artifact_path",
                return_value=manual_artifact,
            ), patch(
                "cli.beta_release_review_artifact_path",
                return_value=release_review_artifact,
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=True,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                },
                clear=False,
            ):
                should_exit, speak_enabled, beta_output = self._run_command("qa beta", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("qa beta release review candidate: llm_env_strict", beta_output)
        self.assertIn("qa beta release review candidate selection: none", beta_output)
        self.assertIn("qa beta release review artifact consistent with latest evidence: no", beta_output)
        self.assertIn(
            "qa beta release review artifact consistency reason: recorded beta release review candidate selection source is missing",
            beta_output,
        )
        runtime_mock.assert_not_called()

    def test_qa_beta_rejects_recorded_beta_readiness_artifact_without_explicit_candidate_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_llm_env = Path(tmpdir) / "openai_live_smoke_llm_env.json"
            artifact_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            artifact_llm_env_strict = Path(tmpdir) / "openai_live_smoke_llm_env_strict.json"
            artifact_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": False,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env = Path(tmpdir) / "rollout_stability_llm_env.json"
            stability_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env_strict = Path(tmpdir) / "rollout_stability_llm_env_strict.json"
            stability_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env_strict",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            manual_artifact, manual_created_at, manual_sha256 = self._write_complete_manual_beta_checklist(tmpdir)
            release_review_artifact, release_review_created_at, release_review_sha256 = self._write_complete_beta_release_review(
                tmpdir,
                candidate_profile="llm_env_strict",
                manual_created_at=manual_created_at,
                manual_sha256=manual_sha256,
            )
            beta_artifact = self._write_ready_beta_readiness_artifact(
                tmpdir,
                artifact_llm_env=artifact_llm_env,
                artifact_llm_env_strict=artifact_llm_env_strict,
                stability_llm_env=stability_llm_env,
                stability_llm_env_strict=stability_llm_env_strict,
                manual_created_at=manual_created_at,
                manual_sha256=manual_sha256,
                release_review_created_at=release_review_created_at,
                release_review_sha256=release_review_sha256,
                include_candidate_selection_source=False,
            )

            def _artifact_for_candidate(candidate_profile: str | None) -> Path:
                if candidate_profile == "llm_env_strict":
                    return artifact_llm_env_strict
                return artifact_llm_env

            def _stability_for_candidate(candidate_profile: str) -> Path:
                if candidate_profile == "llm_env_strict":
                    return stability_llm_env_strict
                return stability_llm_env

            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 26, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.live_smoke_artifact_path_for_candidate",
                side_effect=_artifact_for_candidate,
            ), patch(
                "cli.rollout_stability_artifact_path_for_candidate",
                side_effect=_stability_for_candidate,
            ), patch(
                "cli.beta_readiness_artifact_path",
                return_value=beta_artifact,
            ), patch(
                "cli.manual_beta_checklist_artifact_path",
                return_value=manual_artifact,
            ), patch(
                "cli.beta_release_review_artifact_path",
                return_value=release_review_artifact,
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=True,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                },
                clear=False,
            ):
                should_exit, speak_enabled, beta_output = self._run_command("qa beta", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("qa beta recorded candidate: llm_env_strict", beta_output)
        self.assertIn("qa beta recorded candidate selection: none", beta_output)
        self.assertIn("qa beta decision artifact fresh: yes", beta_output)
        self.assertIn("qa beta decision artifact consistent with latest evidence: no", beta_output)
        self.assertIn(
            "qa beta decision artifact consistency reason: recorded candidate selection source is missing; final beta artifact requires explicit operator choice",
            beta_output,
        )
        self.assertIn(
            "qa beta decision: recorded beta readiness is stale against latest evidence; review must be repeated",
            beta_output,
        )
        runtime_mock.assert_not_called()

    def test_qa_beta_reports_snapshot_mismatch_even_when_recorded_candidate_is_still_green(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_llm_env = Path(tmpdir) / "openai_live_smoke_llm_env.json"
            artifact_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            artifact_llm_env_strict = Path(tmpdir) / "openai_live_smoke_llm_env_strict.json"
            artifact_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": False,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env = Path(tmpdir) / "rollout_stability_llm_env.json"
            stability_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env_strict = Path(tmpdir) / "rollout_stability_llm_env_strict.json"
            stability_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env_strict",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            manual_artifact, manual_created_at, manual_sha256 = self._write_complete_manual_beta_checklist(tmpdir)
            release_review_artifact, release_review_created_at, release_review_sha256 = self._write_complete_beta_release_review(
                tmpdir,
                candidate_profile="llm_env_strict",
                manual_created_at=manual_created_at,
                manual_sha256=manual_sha256,
            )
            beta_artifact = Path(tmpdir) / "beta_readiness.json"
            beta_artifact.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.beta_readiness",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "stage": "alpha_opt_in",
                            "default_path": "deterministic",
                            "recommended_candidate": "llm_env_strict",
                            "chosen_candidate": "llm_env_strict",
                            "candidate_selection_source": "explicit",
                            "technical_ready_candidates": ["llm_env", "llm_env_strict"],
                            "manual_checklist_completed": True,
                            "manual_checklist_artifact_status": "complete",
                            "manual_checklist_artifact_completed": True,
                            "manual_checklist_items_passed": 7,
                            "manual_checklist_items_total": 7,
                            "manual_checklist_artifact_created_at": manual_created_at,
                            "manual_checklist_artifact_sha256": manual_sha256,
                            "release_review_artifact_status": "complete",
                            "release_review_artifact_completed": True,
                            "release_review_artifact_candidate": "llm_env_strict",
                            "release_review_checks_completed": 4,
                            "release_review_checks_total": 4,
                            "release_review_artifact_created_at": release_review_created_at,
                            "release_review_artifact_sha256": release_review_sha256,
                            "latency_review_completed": True,
                            "cost_review_completed": True,
                            "operator_signoff_completed": True,
                            "product_approval_completed": True,
                            "beta_ready": True,
                            "blockers": [],
                            "candidate_states": {
                                "llm_env_strict": {
                                    "candidate_profile": "llm_env_strict",
                                    "api_key_present": True,
                                    "fallback_enabled": False,
                                    "open_domain_enabled": True,
                                    "open_domain_verified": True,
                                    "technical_ready": True,
                                    "smoke_artifact_path": str(artifact_llm_env_strict),
                                    "smoke_artifact_status": "green",
                                    "smoke_artifact_created_at": "2026-03-26T00:00:00+00:00",
                                    "smoke_artifact_sha256": "outdated-smoke-fingerprint",
                                    "smoke_artifact_fresh": True,
                                    "smoke_artifact_match": True,
                                    "smoke_artifact_age_hours": 1.0,
                                    "smoke_artifact_reason": None,
                                    "stability_artifact_path": str(stability_llm_env_strict),
                                    "stability_artifact_status": "green",
                                    "stability_artifact_created_at": "2026-03-26T00:00:00+00:00",
                                    "stability_artifact_sha256": "outdated-stability-fingerprint",
                                    "stability_artifact_fresh": True,
                                    "stability_artifact_age_hours": 1.0,
                                    "stability_artifact_reason": None,
                                    "stability_gate_passes": 2,
                                    "stability_runs_requested": 2,
                                    "blockers": [],
                                }
                            },
                            "notes": "",
                        },
                    }
                ),
                encoding="utf-8",
            )

            def _artifact_for_candidate(candidate_profile: str | None) -> Path:
                if candidate_profile == "llm_env_strict":
                    return artifact_llm_env_strict
                return artifact_llm_env

            def _stability_for_candidate(candidate_profile: str) -> Path:
                if candidate_profile == "llm_env_strict":
                    return stability_llm_env_strict
                return stability_llm_env

            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 26, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.live_smoke_artifact_path_for_candidate",
                side_effect=_artifact_for_candidate,
            ), patch(
                "cli.rollout_stability_artifact_path_for_candidate",
                side_effect=_stability_for_candidate,
            ), patch(
                "cli.beta_readiness_artifact_path",
                return_value=beta_artifact,
            ), patch(
                "cli.manual_beta_checklist_artifact_path",
                return_value=manual_artifact,
            ), patch(
                "cli.beta_release_review_artifact_path",
                return_value=release_review_artifact,
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=True,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                },
                clear=False,
            ):
                should_exit, speak_enabled, beta_output = self._run_command("qa beta", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("qa beta recommended candidate: llm_env_strict", beta_output)
        self.assertIn("qa beta recorded candidate: llm_env_strict", beta_output)
        self.assertIn("qa beta manual checklist artifact:", beta_output)
        self.assertIn("(complete(7/7))", beta_output)
        self.assertIn("qa beta decision artifact fresh: yes", beta_output)
        self.assertIn("qa beta decision artifact consistent with latest evidence: no", beta_output)
        self.assertIn(
            "qa beta decision artifact consistency reason: recorded smoke artifact fingerprint for llm_env_strict no longer matches the latest artifact",
            beta_output,
        )
        self.assertIn(
            "qa beta decision: recorded beta readiness is stale against latest evidence; review must be repeated",
            beta_output,
        )
        runtime_mock.assert_not_called()

    def test_qa_beta_reports_manual_checklist_artifact_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_llm_env = Path(tmpdir) / "openai_live_smoke_llm_env.json"
            artifact_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            artifact_llm_env_strict = Path(tmpdir) / "openai_live_smoke_llm_env_strict.json"
            artifact_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": False,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env = Path(tmpdir) / "rollout_stability_llm_env.json"
            stability_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env_strict = Path(tmpdir) / "rollout_stability_llm_env_strict.json"
            stability_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env_strict",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            manual_artifact, manual_created_at, _manual_sha256 = self._write_complete_manual_beta_checklist(tmpdir)
            release_review_artifact, release_review_created_at, release_review_sha256 = self._write_complete_beta_release_review(
                tmpdir,
                candidate_profile="llm_env_strict",
                manual_created_at=manual_created_at,
                manual_sha256=_manual_sha256,
            )
            beta_artifact = Path(tmpdir) / "beta_readiness.json"
            beta_artifact.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.beta_readiness",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "stage": "alpha_opt_in",
                            "default_path": "deterministic",
                            "recommended_candidate": "llm_env_strict",
                            "chosen_candidate": "llm_env_strict",
                            "candidate_selection_source": "explicit",
                            "technical_ready_candidates": ["llm_env", "llm_env_strict"],
                            "manual_checklist_completed": True,
                            "manual_checklist_artifact_status": "complete",
                            "manual_checklist_artifact_completed": True,
                            "manual_checklist_items_passed": 7,
                            "manual_checklist_items_total": 7,
                            "manual_checklist_artifact_created_at": manual_created_at,
                            "manual_checklist_artifact_sha256": "outdated-manual-checklist-fingerprint",
                            "release_review_artifact_status": "complete",
                            "release_review_artifact_completed": True,
                            "release_review_artifact_candidate": "llm_env_strict",
                            "release_review_checks_completed": 4,
                            "release_review_checks_total": 4,
                            "release_review_artifact_created_at": release_review_created_at,
                            "release_review_artifact_sha256": release_review_sha256,
                            "latency_review_completed": True,
                            "cost_review_completed": True,
                            "operator_signoff_completed": True,
                            "product_approval_completed": True,
                            "beta_ready": True,
                            "blockers": [],
                            "candidate_states": {
                                "llm_env_strict": {
                                    "candidate_profile": "llm_env_strict",
                                    "api_key_present": True,
                                    "fallback_enabled": False,
                                    "open_domain_enabled": True,
                                    "open_domain_verified": True,
                                    "technical_ready": True,
                                    "smoke_artifact_path": str(artifact_llm_env_strict),
                                    "smoke_artifact_status": "green",
                                    "smoke_artifact_created_at": "2026-03-26T00:00:00+00:00",
                                    "smoke_artifact_sha256": hashlib.sha256(artifact_llm_env_strict.read_bytes()).hexdigest(),
                                    "smoke_artifact_fresh": True,
                                    "smoke_artifact_match": True,
                                    "smoke_artifact_age_hours": 0.0,
                                    "smoke_artifact_reason": None,
                                    "stability_artifact_path": str(stability_llm_env_strict),
                                    "stability_artifact_status": "green",
                                    "stability_artifact_created_at": "2026-03-26T00:00:00+00:00",
                                    "stability_artifact_sha256": hashlib.sha256(stability_llm_env_strict.read_bytes()).hexdigest(),
                                    "stability_artifact_fresh": True,
                                    "stability_artifact_age_hours": 0.0,
                                    "stability_artifact_reason": None,
                                    "stability_gate_passes": 2,
                                    "stability_runs_requested": 2,
                                    "blockers": [],
                                }
                            },
                            "notes": "",
                        },
                    }
                ),
                encoding="utf-8",
            )

            def _artifact_for_candidate(candidate_profile: str | None) -> Path:
                if candidate_profile == "llm_env_strict":
                    return artifact_llm_env_strict
                return artifact_llm_env

            def _stability_for_candidate(candidate_profile: str) -> Path:
                if candidate_profile == "llm_env_strict":
                    return stability_llm_env_strict
                return stability_llm_env

            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 26, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.live_smoke_artifact_path_for_candidate",
                side_effect=_artifact_for_candidate,
            ), patch(
                "cli.rollout_stability_artifact_path_for_candidate",
                side_effect=_stability_for_candidate,
            ), patch(
                "cli.beta_readiness_artifact_path",
                return_value=beta_artifact,
            ), patch(
                "cli.manual_beta_checklist_artifact_path",
                return_value=manual_artifact,
            ), patch(
                "cli.beta_release_review_artifact_path",
                return_value=release_review_artifact,
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=True,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                },
                clear=False,
            ):
                should_exit, speak_enabled, beta_output = self._run_command("qa beta", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("qa beta decision artifact consistent with latest evidence: no", beta_output)
        self.assertIn(
            "qa beta decision artifact consistency reason: recorded manual checklist artifact fingerprint no longer matches the latest artifact",
            beta_output,
        )
        self.assertIn(
            "qa beta decision: recorded beta readiness is stale against latest evidence; review must be repeated",
            beta_output,
        )
        runtime_mock.assert_not_called()

    def test_qa_beta_reports_ready_artifact_as_stale_when_latest_evidence_drifts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_llm_env = Path(tmpdir) / "openai_live_smoke_llm_env.json"
            artifact_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            artifact_llm_env_strict = Path(tmpdir) / "openai_live_smoke_llm_env_strict.json"
            artifact_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": False,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env = Path(tmpdir) / "rollout_stability_llm_env.json"
            stability_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env_strict = Path(tmpdir) / "rollout_stability_llm_env_strict.json"
            stability_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env_strict",
                            "runs_requested": 2,
                            "gate_passes": 0,
                            "runs": [],
                            "blocker_counts": {
                                "open-domain answer pass rate is below threshold": 1,
                            },
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            manual_artifact, manual_created_at, manual_sha256 = self._write_complete_manual_beta_checklist(tmpdir)
            release_review_artifact, release_review_created_at, release_review_sha256 = self._write_complete_beta_release_review(
                tmpdir,
                candidate_profile="llm_env_strict",
                manual_created_at=manual_created_at,
                manual_sha256=manual_sha256,
            )
            beta_artifact = Path(tmpdir) / "beta_readiness.json"
            beta_artifact.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.beta_readiness",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "stage": "alpha_opt_in",
                            "default_path": "deterministic",
                            "recommended_candidate": "llm_env_strict",
                            "chosen_candidate": "llm_env_strict",
                            "candidate_selection_source": "explicit",
                            "technical_ready_candidates": ["llm_env", "llm_env_strict"],
                            "manual_checklist_completed": True,
                            "manual_checklist_artifact_status": "complete",
                            "manual_checklist_artifact_completed": True,
                            "manual_checklist_items_passed": 7,
                            "manual_checklist_items_total": 7,
                            "manual_checklist_artifact_created_at": manual_created_at,
                            "manual_checklist_artifact_sha256": manual_sha256,
                            "release_review_artifact_status": "complete",
                            "release_review_artifact_completed": True,
                            "release_review_artifact_candidate": "llm_env_strict",
                            "release_review_checks_completed": 4,
                            "release_review_checks_total": 4,
                            "release_review_artifact_created_at": release_review_created_at,
                            "release_review_artifact_sha256": release_review_sha256,
                            "latency_review_completed": True,
                            "cost_review_completed": True,
                            "operator_signoff_completed": True,
                            "product_approval_completed": True,
                            "beta_ready": True,
                            "blockers": [],
                            "candidate_states": {
                                "llm_env_strict": {
                                    "candidate_profile": "llm_env_strict",
                                    "api_key_present": True,
                                    "fallback_enabled": False,
                                    "open_domain_enabled": True,
                                    "open_domain_verified": True,
                                    "technical_ready": True,
                                    "smoke_artifact_path": str(artifact_llm_env_strict),
                                    "smoke_artifact_status": "green",
                                    "smoke_artifact_created_at": "2026-03-26T00:00:00+00:00",
                                    "smoke_artifact_fresh": True,
                                    "smoke_artifact_match": True,
                                    "smoke_artifact_age_hours": 0.0,
                                    "smoke_artifact_reason": None,
                                    "stability_artifact_path": str(stability_llm_env_strict),
                                    "stability_artifact_status": "green",
                                    "stability_artifact_created_at": "2026-03-26T00:00:00+00:00",
                                    "stability_artifact_fresh": True,
                                    "stability_artifact_age_hours": 0.0,
                                    "stability_artifact_reason": None,
                                    "stability_gate_passes": 2,
                                    "stability_runs_requested": 2,
                                    "blockers": [],
                                }
                            },
                            "notes": "",
                        },
                    }
                ),
                encoding="utf-8",
            )

            def _artifact_for_candidate(candidate_profile: str | None) -> Path:
                if candidate_profile == "llm_env_strict":
                    return artifact_llm_env_strict
                return artifact_llm_env

            def _stability_for_candidate(candidate_profile: str) -> Path:
                if candidate_profile == "llm_env_strict":
                    return stability_llm_env_strict
                return stability_llm_env

            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 26, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.live_smoke_artifact_path_for_candidate",
                side_effect=_artifact_for_candidate,
            ), patch(
                "cli.rollout_stability_artifact_path_for_candidate",
                side_effect=_stability_for_candidate,
            ), patch(
                "cli.beta_readiness_artifact_path",
                return_value=beta_artifact,
            ), patch(
                "cli.manual_beta_checklist_artifact_path",
                return_value=manual_artifact,
            ), patch(
                "cli.beta_release_review_artifact_path",
                return_value=release_review_artifact,
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=True,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                },
                clear=False,
            ):
                should_exit, speak_enabled, beta_output = self._run_command("qa beta", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("qa beta recommended candidate: llm_env", beta_output)
        self.assertIn("qa beta recorded candidate: llm_env_strict", beta_output)
        self.assertIn("qa beta manual checklist artifact:", beta_output)
        self.assertIn("(complete(7/7))", beta_output)
        self.assertIn("qa beta decision artifact fresh: yes", beta_output)
        self.assertIn("qa beta decision artifact consistent with latest evidence: no", beta_output)
        self.assertIn(
            "qa beta decision artifact consistency reason: recorded candidate llm_env_strict is not technically ready on latest artifacts",
            beta_output,
        )
        self.assertIn(
            "qa beta decision artifact drift: recorded candidate llm_env_strict differs from the latest recommended candidate llm_env",
            beta_output,
        )
        self.assertIn(
            "qa beta decision: recorded beta readiness is stale against latest evidence; review must be repeated",
            beta_output,
        )
        runtime_mock.assert_not_called()

    def test_qa_beta_reports_ready_artifact_as_stale_when_manual_checklist_ages_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_llm_env = Path(tmpdir) / "openai_live_smoke_llm_env.json"
            artifact_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            artifact_llm_env_strict = Path(tmpdir) / "openai_live_smoke_llm_env_strict.json"
            artifact_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": False,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env = Path(tmpdir) / "rollout_stability_llm_env.json"
            stability_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env_strict = Path(tmpdir) / "rollout_stability_llm_env_strict.json"
            stability_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env_strict",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            manual_artifact, manual_created_at, manual_sha256 = self._write_complete_manual_beta_checklist(tmpdir)
            manual_payload = json.loads(manual_artifact.read_text(encoding="utf-8"))
            manual_payload["created_at"] = "2026-03-24T00:00:00+00:00"
            manual_artifact.write_text(json.dumps(manual_payload, indent=2, sort_keys=True), encoding="utf-8")
            stale_manual_created_at = "2026-03-24T00:00:00+00:00"
            stale_manual_sha256 = hashlib.sha256(manual_artifact.read_bytes()).hexdigest()
            release_review_artifact, release_review_created_at, release_review_sha256 = self._write_complete_beta_release_review(
                tmpdir,
                candidate_profile="llm_env_strict",
                manual_created_at=stale_manual_created_at,
                manual_sha256=stale_manual_sha256,
            )
            beta_artifact = Path(tmpdir) / "beta_readiness.json"
            beta_artifact.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.beta_readiness",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "stage": "alpha_opt_in",
                            "default_path": "deterministic",
                            "recommended_candidate": "llm_env_strict",
                            "chosen_candidate": "llm_env_strict",
                            "candidate_selection_source": "explicit",
                            "technical_ready_candidates": ["llm_env", "llm_env_strict"],
                            "manual_checklist_completed": True,
                            "manual_checklist_artifact_status": "complete",
                            "manual_checklist_artifact_completed": True,
                            "manual_checklist_items_passed": 7,
                            "manual_checklist_items_total": 7,
                            "manual_checklist_artifact_created_at": stale_manual_created_at,
                            "manual_checklist_artifact_sha256": stale_manual_sha256,
                            "release_review_artifact_status": "complete",
                            "release_review_artifact_completed": True,
                            "release_review_artifact_candidate": "llm_env_strict",
                            "release_review_checks_completed": 4,
                            "release_review_checks_total": 4,
                            "release_review_artifact_created_at": release_review_created_at,
                            "release_review_artifact_sha256": release_review_sha256,
                            "latency_review_completed": True,
                            "cost_review_completed": True,
                            "operator_signoff_completed": True,
                            "product_approval_completed": True,
                            "beta_ready": True,
                            "blockers": [],
                            "candidate_states": {
                                "llm_env_strict": {
                                    "candidate_profile": "llm_env_strict",
                                    "api_key_present": True,
                                    "fallback_enabled": False,
                                    "open_domain_enabled": True,
                                    "open_domain_verified": True,
                                    "technical_ready": True,
                                    "smoke_artifact_path": str(artifact_llm_env_strict),
                                    "smoke_artifact_status": "green",
                                    "smoke_artifact_created_at": "2026-03-26T00:00:00+00:00",
                                    "smoke_artifact_sha256": hashlib.sha256(artifact_llm_env_strict.read_bytes()).hexdigest(),
                                    "smoke_artifact_fresh": True,
                                    "smoke_artifact_match": True,
                                    "smoke_artifact_age_hours": 0.0,
                                    "smoke_artifact_reason": None,
                                    "stability_artifact_path": str(stability_llm_env_strict),
                                    "stability_artifact_status": "green",
                                    "stability_artifact_created_at": "2026-03-26T00:00:00+00:00",
                                    "stability_artifact_sha256": hashlib.sha256(stability_llm_env_strict.read_bytes()).hexdigest(),
                                    "stability_artifact_fresh": True,
                                    "stability_artifact_age_hours": 0.0,
                                    "stability_artifact_reason": None,
                                    "stability_gate_passes": 2,
                                    "stability_runs_requested": 2,
                                    "blockers": [],
                                }
                            },
                            "notes": "",
                        },
                    }
                ),
                encoding="utf-8",
            )

            def _artifact_for_candidate(candidate_profile: str | None) -> Path:
                if candidate_profile == "llm_env_strict":
                    return artifact_llm_env_strict
                return artifact_llm_env

            def _stability_for_candidate(candidate_profile: str) -> Path:
                if candidate_profile == "llm_env_strict":
                    return stability_llm_env_strict
                return stability_llm_env

            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 26, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.live_smoke_artifact_path_for_candidate",
                side_effect=_artifact_for_candidate,
            ), patch(
                "cli.rollout_stability_artifact_path_for_candidate",
                side_effect=_stability_for_candidate,
            ), patch(
                "cli.beta_readiness_artifact_path",
                return_value=beta_artifact,
            ), patch(
                "cli.manual_beta_checklist_artifact_path",
                return_value=manual_artifact,
            ), patch(
                "cli.beta_release_review_artifact_path",
                return_value=release_review_artifact,
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=True,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                },
                clear=False,
            ):
                should_exit, speak_enabled, beta_output = self._run_command("qa beta", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("qa beta manual checklist artifact fresh: no (48.0h)", beta_output)
        self.assertIn("qa beta decision artifact consistent with latest evidence: no", beta_output)
        self.assertIn(
            "qa beta decision artifact consistency reason: latest manual checklist artifact is stale",
            beta_output,
        )
        self.assertIn(
            "qa beta decision: recorded beta readiness is stale against latest evidence; review must be repeated",
            beta_output,
        )
        runtime_mock.assert_not_called()

    def test_qa_beta_reports_ready_artifact_as_stale_when_release_review_ages_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_llm_env = Path(tmpdir) / "openai_live_smoke_llm_env.json"
            artifact_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": True,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            artifact_llm_env_strict = Path(tmpdir) / "openai_live_smoke_llm_env_strict.json"
            artifact_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "tests.smoke_openai_responses_provider_live",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "question": "Why is the sky blue?",
                        "success": True,
                        "issues": [],
                        "error": None,
                        "open_domain_verified": True,
                        "diagnostics": {
                            "provider": "openai_responses",
                            "model": "gpt-5-nano",
                            "strict_mode": True,
                            "fallback_enabled": False,
                            "open_domain_enabled": True,
                            "answer_kind": "open_domain_model",
                            "provenance": "model_knowledge",
                            "source_count": 0,
                            "deterministic_fallback": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env = Path(tmpdir) / "rollout_stability_llm_env.json"
            stability_llm_env.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            stability_llm_env_strict = Path(tmpdir) / "rollout_stability_llm_env_strict.json"
            stability_llm_env_strict.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.rollout_stability",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "baseline_profile": "deterministic",
                            "candidate_profile": "llm_env_strict",
                            "runs_requested": 2,
                            "gate_passes": 2,
                            "runs": [],
                            "blocker_counts": {},
                            "failed_case_counts": {},
                            "fallback_case_counts": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            manual_artifact, manual_created_at, manual_sha256 = self._write_complete_manual_beta_checklist(tmpdir)
            release_review_artifact, _release_review_created_at, _release_review_sha256 = self._write_complete_beta_release_review(
                tmpdir,
                candidate_profile="llm_env_strict",
                manual_created_at=manual_created_at,
                manual_sha256=manual_sha256,
            )
            release_review_payload = json.loads(release_review_artifact.read_text(encoding="utf-8"))
            release_review_payload["created_at"] = "2026-03-24T00:00:00+00:00"
            release_review_artifact.write_text(
                json.dumps(release_review_payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            stale_release_review_created_at = "2026-03-24T00:00:00+00:00"
            stale_release_review_sha256 = hashlib.sha256(release_review_artifact.read_bytes()).hexdigest()
            beta_artifact = Path(tmpdir) / "beta_readiness.json"
            beta_artifact.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.beta_readiness",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "stage": "alpha_opt_in",
                            "default_path": "deterministic",
                            "recommended_candidate": "llm_env_strict",
                            "chosen_candidate": "llm_env_strict",
                            "candidate_selection_source": "explicit",
                            "technical_ready_candidates": ["llm_env", "llm_env_strict"],
                            "manual_checklist_completed": True,
                            "manual_checklist_artifact_status": "complete",
                            "manual_checklist_artifact_completed": True,
                            "manual_checklist_items_passed": 7,
                            "manual_checklist_items_total": 7,
                            "manual_checklist_artifact_created_at": manual_created_at,
                            "manual_checklist_artifact_sha256": manual_sha256,
                            "release_review_artifact_status": "complete",
                            "release_review_artifact_completed": True,
                            "release_review_artifact_candidate": "llm_env_strict",
                            "release_review_checks_completed": 4,
                            "release_review_checks_total": 4,
                            "release_review_artifact_created_at": stale_release_review_created_at,
                            "release_review_artifact_sha256": stale_release_review_sha256,
                            "latency_review_completed": True,
                            "cost_review_completed": True,
                            "operator_signoff_completed": True,
                            "product_approval_completed": True,
                            "beta_ready": True,
                            "blockers": [],
                            "candidate_states": {
                                "llm_env_strict": {
                                    "candidate_profile": "llm_env_strict",
                                    "api_key_present": True,
                                    "fallback_enabled": False,
                                    "open_domain_enabled": True,
                                    "open_domain_verified": True,
                                    "technical_ready": True,
                                    "smoke_artifact_path": str(artifact_llm_env_strict),
                                    "smoke_artifact_status": "green",
                                    "smoke_artifact_created_at": "2026-03-26T00:00:00+00:00",
                                    "smoke_artifact_sha256": hashlib.sha256(artifact_llm_env_strict.read_bytes()).hexdigest(),
                                    "smoke_artifact_fresh": True,
                                    "smoke_artifact_match": True,
                                    "smoke_artifact_age_hours": 0.0,
                                    "smoke_artifact_reason": None,
                                    "stability_artifact_path": str(stability_llm_env_strict),
                                    "stability_artifact_status": "green",
                                    "stability_artifact_created_at": "2026-03-26T00:00:00+00:00",
                                    "stability_artifact_sha256": hashlib.sha256(stability_llm_env_strict.read_bytes()).hexdigest(),
                                    "stability_artifact_fresh": True,
                                    "stability_artifact_age_hours": 0.0,
                                    "stability_artifact_reason": None,
                                    "stability_gate_passes": 2,
                                    "stability_runs_requested": 2,
                                    "blockers": [],
                                }
                            },
                            "notes": "",
                        },
                    }
                ),
                encoding="utf-8",
            )

            def _artifact_for_candidate(candidate_profile: str | None) -> Path:
                if candidate_profile == "llm_env_strict":
                    return artifact_llm_env_strict
                return artifact_llm_env

            def _stability_for_candidate(candidate_profile: str) -> Path:
                if candidate_profile == "llm_env_strict":
                    return stability_llm_env_strict
                return stability_llm_env

            with patch("cli._handle_runtime_input") as runtime_mock, patch(
                "cli._artifact_now",
                return_value=cli.datetime(2026, 3, 26, tzinfo=cli.timezone.utc),
            ), patch(
                "cli.live_smoke_artifact_path_for_candidate",
                side_effect=_artifact_for_candidate,
            ), patch(
                "cli.rollout_stability_artifact_path_for_candidate",
                side_effect=_stability_for_candidate,
            ), patch(
                "cli.beta_readiness_artifact_path",
                return_value=beta_artifact,
            ), patch(
                "cli.manual_beta_checklist_artifact_path",
                return_value=manual_artifact,
            ), patch(
                "cli.beta_release_review_artifact_path",
                return_value=release_review_artifact,
            ), patch(
                "cli.load_answer_backend_config",
                return_value=SimpleNamespace(
                    backend_kind="llm",
                    llm=SimpleNamespace(
                        provider="openai_responses",
                        enabled=True,
                        fallback_enabled=True,
                        open_domain_enabled=True,
                        model="gpt-5-nano",
                        reasoning_effort="minimal",
                        strict_mode=True,
                        max_output_tokens=800,
                        api_key_env="OPENAI_API_KEY",
                    ),
                ),
            ), patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                },
                clear=False,
            ):
                should_exit, speak_enabled, beta_output = self._run_command("qa beta", speak_enabled=False)

        self.assertFalse(should_exit)
        self.assertFalse(speak_enabled)
        self.assertIn("qa beta release review artifact fresh: no (48.0h)", beta_output)
        self.assertIn("qa beta decision artifact consistent with latest evidence: no", beta_output)
        self.assertIn(
            "qa beta decision artifact consistency reason: latest beta release review artifact is stale",
            beta_output,
        )
        self.assertIn(
            "qa beta decision: recorded beta readiness is stale against latest evidence; review must be repeated",
            beta_output,
        )
        runtime_mock.assert_not_called()

    def test_question_answer_output_includes_mode_answer_sources_and_warning(self) -> None:
        interaction_manager = MagicMock()
        interaction_manager.handle_input.return_value = SimpleNamespace(
            interaction_mode="question",
            answer_result=SimpleNamespace(
                answer_text="I can open apps and answer grounded questions.",
                sources=["/tmp/docs/product_rules.md", "/tmp/docs/question_answer_mode.md"],
                warning="Answer is limited to grounded local sources.",
            ),
            clarification_request=None,
            runtime_result=None,
            error=None,
        )

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            cli._handle_runtime_input(
                "What can you do?",
                runtime_manager=self.runtime_manager,
                session_context=self.session_context,
                speak_enabled=False,
                interaction_manager=interaction_manager,
            )

        output = buffer.getvalue()
        self.assertIn("mode: question", output)
        self.assertIn("summary: I can open apps and answer grounded questions.", output)
        self.assertIn("sources: Product Rules, Question Answer Mode", output)
        self.assertIn("paths: /tmp/docs/product_rules.md, /tmp/docs/question_answer_mode.md", output)
        self.assertIn("warning: Answer is limited to grounded local sources.", output)
        interaction_manager.handle_input.assert_called_once_with(
            "What can you do?",
            session_context=self.session_context,
        )

    def test_mixed_interaction_prints_routing_clarification(self) -> None:
        interaction_manager = MagicMock()
        interaction_manager.handle_input.return_value = SimpleNamespace(
            interaction_mode="clarification",
            answer_result=None,
            clarification_request=SimpleNamespace(
                message="Do you want an answer first or should I open Safari?"
            ),
            runtime_result=None,
            error=None,
        )

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            cli._handle_runtime_input(
                "What can you do and open Safari",
                runtime_manager=self.runtime_manager,
                session_context=self.session_context,
                speak_enabled=False,
                interaction_manager=interaction_manager,
            )

        output = buffer.getvalue()
        self.assertIn("mode: clarification", output)
        self.assertIn("clarify: Do you want an answer first or should I open Safari?", output)

    def test_question_answer_is_spoken_when_enabled(self) -> None:
        interaction_manager = MagicMock()
        interaction_manager.handle_input.return_value = SimpleNamespace(
            interaction_mode="question",
            answer_result=SimpleNamespace(
                answer_text="I can open apps and answer grounded questions. I stay read-only.",
                sources=[],
                warning="Answer is limited to grounded local sources.",
            ),
            clarification_request=None,
            runtime_result=None,
            error=None,
        )

        buffer = io.StringIO()
        with redirect_stdout(buffer), patch("cli.subprocess.run", return_value=SimpleNamespace(returncode=0)) as speech_mock:
            cli._handle_runtime_input(
                "What can you do?",
                runtime_manager=self.runtime_manager,
                session_context=self.session_context,
                speak_enabled=True,
                interaction_manager=interaction_manager,
            )

        speech_mock.assert_called_once_with(
            ["say", "I can open apps and answer grounded questions. Warning: Answer is limited to grounded local sources."],
            capture_output=True,
            text=True,
            check=False,
        )

    def _write_complete_manual_beta_checklist(self, tmpdir: str) -> tuple[Path, str, str]:
        manual_artifact = Path(tmpdir) / "manual_beta_checklist.json"
        created_at = "2026-03-26T00:00:00+00:00"
        manual_artifact.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "runner": "qa.manual_beta_checklist",
                    "created_at": created_at,
                    "report": {
                        "checklist_id": "beta_question_default",
                        "passed_items": 7,
                        "total_items": 7,
                        "all_passed": True,
                        "items": {},
                        "notes": "",
                    },
                }
            ),
            encoding="utf-8",
        )
        return manual_artifact, created_at, hashlib.sha256(manual_artifact.read_bytes()).hexdigest()

    def _write_complete_beta_release_review(
        self,
        tmpdir: str,
        *,
        candidate_profile: str,
        manual_created_at: str,
        manual_sha256: str,
    ) -> tuple[Path, str, str]:
        review_artifact = Path(tmpdir) / "beta_release_review.json"
        created_at = "2026-03-26T00:00:00+00:00"
        review_artifact.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "runner": "qa.beta_release_review",
                    "created_at": created_at,
                    "report": {
                        "review_id": "beta_question_default",
                        "candidate_profile": candidate_profile,
                        "candidate_selection_source": "explicit",
                        "completed_checks": 4,
                        "total_checks": 4,
                        "all_completed": True,
                        "manual_checklist_artifact_status": "complete",
                        "manual_checklist_artifact_completed": True,
                        "manual_checklist_items_passed": 7,
                        "manual_checklist_items_total": 7,
                        "manual_checklist_artifact_created_at": manual_created_at,
                        "manual_checklist_artifact_sha256": manual_sha256,
                        "checks": {
                            "latency_review": {"label": "Latency review", "completed": True},
                            "cost_review": {"label": "Cost review", "completed": True},
                            "operator_signoff": {"label": "Operator sign-off", "completed": True},
                            "product_approval": {"label": "Product approval", "completed": True},
                        },
                        "notes": "",
                    },
                }
            ),
            encoding="utf-8",
        )
        return review_artifact, created_at, hashlib.sha256(review_artifact.read_bytes()).hexdigest()

    def _write_ready_beta_readiness_artifact(
        self,
        tmpdir: str,
        *,
        artifact_llm_env: Path,
        artifact_llm_env_strict: Path,
        stability_llm_env: Path,
        stability_llm_env_strict: Path,
        manual_created_at: str,
        manual_sha256: str,
        release_review_created_at: str,
        release_review_sha256: str,
        include_candidate_selection_source: bool = True,
    ) -> Path:
        beta_artifact = Path(tmpdir) / "beta_readiness.json"
        report = {
            "stage": "alpha_opt_in",
            "default_path": "deterministic",
            "recommended_candidate": "llm_env_strict",
            "chosen_candidate": "llm_env_strict",
            "technical_ready_candidates": ["llm_env", "llm_env_strict"],
            "manual_checklist_completed": True,
            "manual_checklist_artifact_status": "complete",
            "manual_checklist_artifact_completed": True,
            "manual_checklist_items_passed": 7,
            "manual_checklist_items_total": 7,
            "manual_checklist_artifact_created_at": manual_created_at,
            "manual_checklist_artifact_sha256": manual_sha256,
            "release_review_artifact_status": "complete",
            "release_review_artifact_completed": True,
            "release_review_artifact_candidate": "llm_env_strict",
            "release_review_checks_completed": 4,
            "release_review_checks_total": 4,
            "release_review_artifact_created_at": release_review_created_at,
            "release_review_artifact_sha256": release_review_sha256,
            "latency_review_completed": True,
            "cost_review_completed": True,
            "operator_signoff_completed": True,
            "product_approval_completed": True,
            "beta_ready": True,
            "blockers": [],
            "candidate_states": {
                "llm_env": {
                    "candidate_profile": "llm_env",
                    "api_key_present": True,
                    "fallback_enabled": True,
                    "open_domain_enabled": True,
                    "open_domain_verified": True,
                    "technical_ready": True,
                    "smoke_artifact_path": str(artifact_llm_env),
                    "smoke_artifact_status": "green",
                    "smoke_artifact_created_at": "2026-03-26T00:00:00+00:00",
                    "smoke_artifact_sha256": hashlib.sha256(artifact_llm_env.read_bytes()).hexdigest(),
                    "smoke_artifact_fresh": True,
                    "smoke_artifact_match": True,
                    "smoke_artifact_age_hours": 0.0,
                    "smoke_artifact_reason": None,
                    "stability_artifact_path": str(stability_llm_env),
                    "stability_artifact_status": "green",
                    "stability_artifact_created_at": "2026-03-26T00:00:00+00:00",
                    "stability_artifact_sha256": hashlib.sha256(stability_llm_env.read_bytes()).hexdigest(),
                    "stability_artifact_fresh": True,
                    "stability_artifact_age_hours": 0.0,
                    "stability_artifact_reason": None,
                    "stability_gate_passes": 2,
                    "stability_runs_requested": 2,
                    "blockers": [],
                },
                "llm_env_strict": {
                    "candidate_profile": "llm_env_strict",
                    "api_key_present": True,
                    "fallback_enabled": False,
                    "open_domain_enabled": True,
                    "open_domain_verified": True,
                    "technical_ready": True,
                    "smoke_artifact_path": str(artifact_llm_env_strict),
                    "smoke_artifact_status": "green",
                    "smoke_artifact_created_at": "2026-03-26T00:00:00+00:00",
                    "smoke_artifact_sha256": hashlib.sha256(artifact_llm_env_strict.read_bytes()).hexdigest(),
                    "smoke_artifact_fresh": True,
                    "smoke_artifact_match": True,
                    "smoke_artifact_age_hours": 0.0,
                    "smoke_artifact_reason": None,
                    "stability_artifact_path": str(stability_llm_env_strict),
                    "stability_artifact_status": "green",
                    "stability_artifact_created_at": "2026-03-26T00:00:00+00:00",
                    "stability_artifact_sha256": hashlib.sha256(stability_llm_env_strict.read_bytes()).hexdigest(),
                    "stability_artifact_fresh": True,
                    "stability_artifact_age_hours": 0.0,
                    "stability_artifact_reason": None,
                    "stability_gate_passes": 2,
                    "stability_runs_requested": 2,
                    "blockers": [],
                },
            },
            "notes": "",
        }
        if include_candidate_selection_source:
            report["candidate_selection_source"] = "explicit"
        beta_artifact.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "runner": "qa.beta_readiness",
                    "created_at": "2026-03-26T00:00:00+00:00",
                    "report": report,
                }
            ),
            encoding="utf-8",
        )
        return beta_artifact

    def _run_command(self, command: str, speak_enabled: bool) -> tuple[bool, bool, str]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            should_exit, updated_speak_enabled = cli._handle_cli_command(
                command,
                runtime_manager=self.runtime_manager,
                session_context=self.session_context,
                speak_enabled=speak_enabled,
            )
        return should_exit, updated_speak_enabled, buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
