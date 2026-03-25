"""Minimal smoke coverage for JARVIS CLI shell behavior."""

from __future__ import annotations

import io
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
