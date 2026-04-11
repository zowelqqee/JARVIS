"""Tests for the desktop backend facade."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
import unittest

from desktop.backend.engine_facade import EngineFacade, build_default_engine_facade
from desktop.backend.speech_service import SpeechState
from voice.tts_provider import TTSResult


class _FakeRuntimeManager:
    def __init__(self) -> None:
        self.current_state = "idle"
        self.clear_runtime_calls = 0

    def clear_runtime(self) -> None:
        self.clear_runtime_calls += 1
        self.current_state = "idle"


class _FakeInteractionManager:
    def __init__(self, *results: object) -> None:
        self._results = list(results)
        self.calls: list[tuple[str, object]] = []
        self.runtime_manager = _FakeRuntimeManager()

    def handle_input(self, raw_input: str, session_context: object | None = None) -> object:
        self.calls.append((raw_input, session_context))
        return self._results.pop(0)


@dataclass
class _FakeSpeechService:
    enabled: bool = False
    available: bool | None = True
    backend_name: str | None = "fake_tts"
    message: str | None = "Speech output is off."
    spoken_texts: list[str] | None = None
    next_result: TTSResult | None = None

    def __post_init__(self) -> None:
        if self.spoken_texts is None:
            self.spoken_texts = []

    def snapshot(self) -> SpeechState:
        return SpeechState(
            enabled=self.enabled,
            available=self.available,
            backend_name=self.backend_name,
            message=self.message,
        )

    def set_enabled(self, enabled: bool) -> SpeechState:
        self.enabled = bool(enabled) and self.available is not False
        if self.enabled:
            self.message = f"Speech output enabled via {self.backend_name}."
        elif enabled:
            self.message = "Speech output is unavailable."
        else:
            self.message = "Speech output disabled."
        return self.snapshot()

    def speak(self, utterance: object | None) -> TTSResult | None:
        if utterance is None or not self.enabled:
            return None
        self.spoken_texts.append(str(getattr(utterance, "text", "")))
        result = self.next_result or TTSResult(ok=True, attempted=True, backend_name=self.backend_name)
        if result.ok:
            self.message = f"Speech output enabled via {self.backend_name}."
        else:
            self.message = str(result.error_message or "").strip() or "Speech output failed."
        return result


class EngineFacadeTests(unittest.TestCase):
    def test_submit_text_records_question_turn_in_history(self) -> None:
        manager = _FakeInteractionManager(
            SimpleNamespace(
                interaction_mode="question",
                visibility={
                    "interaction_mode": "question",
                    "answer_text": "I can answer grounded product questions.",
                    "answer_summary": "Grounded product help.",
                    "answer_kind": "grounded_local",
                    "answer_provenance": "local_sources",
                    "answer_sources": ["docs/use_cases.md"],
                    "answer_source_labels": ["Use Cases"],
                    "answer_source_attributions": [{"source": "docs/use_cases.md", "support": "Supported flows."}],
                    "can_cancel": False,
                },
                metadata={"reason": "question"},
            )
        )
        facade = EngineFacade(interaction_manager=manager, speech_service=_FakeSpeechService())

        turn = facade.submit_text("What can you do?")
        snapshot = facade.snapshot()

        self.assertEqual(turn.interaction_mode, "question")
        self.assertEqual(turn.status.interaction_mode, "question")
        self.assertEqual(len(turn.entries), 1)
        self.assertEqual(turn.entries[0].role, "assistant")
        self.assertEqual(len(snapshot.history), 2)
        self.assertEqual(snapshot.history[0].role, "user")
        self.assertEqual(snapshot.history[1].role, "assistant")
        self.assertEqual(snapshot.history[0].text, "What can you do?")
        self.assertEqual(snapshot.history[1].metadata["sources"], ["docs/use_cases.md"])

    def test_submit_text_exposes_confirmation_prompt(self) -> None:
        manager = _FakeInteractionManager(
            SimpleNamespace(
                interaction_mode="command",
                visibility={
                    "interaction_mode": "command",
                    "runtime_state": "awaiting_confirmation",
                    "blocked_reason": "Approve command for open_app?",
                    "confirmation_request": {
                        "message": "Approve command for open_app?",
                        "boundary_type": "command",
                        "affected_targets": ["Safari"],
                    },
                    "can_cancel": True,
                },
                metadata={"reason": "command"},
            )
        )
        facade = EngineFacade(interaction_manager=manager, speech_service=_FakeSpeechService())

        turn = facade.submit_text("Open Safari")

        self.assertEqual(turn.interaction_mode, "command")
        self.assertEqual(turn.status.runtime_state, "awaiting_confirmation")
        self.assertTrue(turn.status.can_cancel)
        self.assertIsNotNone(turn.pending_prompt)
        self.assertEqual(turn.pending_prompt.kind, "confirmation")
        self.assertEqual(turn.pending_prompt.options, ["confirm", "cancel"])
        self.assertEqual(turn.entries[0].entry_kind, "prompt")

    def test_reset_session_clears_history_and_runtime(self) -> None:
        manager = _FakeInteractionManager(
            SimpleNamespace(
                interaction_mode="question",
                visibility={"interaction_mode": "question", "answer_text": "Ready."},
                metadata={},
            )
        )
        facade = EngineFacade(interaction_manager=manager, speech_service=_FakeSpeechService())
        facade.submit_text("Hello")

        snapshot = facade.reset_session()

        self.assertEqual(manager.runtime_manager.clear_runtime_calls, 1)
        self.assertEqual(snapshot.history, [])
        self.assertEqual(snapshot.status.runtime_state, "idle")
        self.assertIsNone(snapshot.pending_prompt)

    def test_speak_on_shell_command_enables_desktop_speech(self) -> None:
        speech_service = _FakeSpeechService()
        facade = EngineFacade(
            interaction_manager=_FakeInteractionManager(),
            speech_service=speech_service,
        )

        turn = facade.submit_text("speak on")
        snapshot = facade.snapshot()

        self.assertTrue(speech_service.enabled)
        self.assertEqual(turn.interaction_mode, "desktop_shell")
        self.assertTrue(snapshot.status.speech_enabled)
        self.assertEqual(snapshot.history[-1].text, "Speech output enabled via fake_tts.")

    def test_enabled_speech_speaks_answer_text(self) -> None:
        manager = _FakeInteractionManager(
            SimpleNamespace(
                interaction_mode="question",
                visibility={
                    "interaction_mode": "question",
                    "answer_text": "I can answer grounded product questions.",
                    "answer_summary": "Grounded product help.",
                    "answer_kind": "grounded_local",
                    "answer_provenance": "local_sources",
                },
                metadata={},
            )
        )
        speech_service = _FakeSpeechService(enabled=True, message="Speech output enabled via fake_tts.")
        facade = EngineFacade(interaction_manager=manager, speech_service=speech_service)

        turn = facade.submit_text("What can you do?")

        self.assertEqual(speech_service.spoken_texts, ["Grounded product help."])
        self.assertTrue(turn.status.speech_enabled)
        self.assertEqual(turn.status.speech_backend, "fake_tts")

    def test_speech_failure_adds_visible_warning(self) -> None:
        manager = _FakeInteractionManager(
            SimpleNamespace(
                interaction_mode="question",
                visibility={
                    "interaction_mode": "question",
                    "answer_text": "Ready.",
                    "answer_summary": "Ready.",
                },
                metadata={},
            )
        )
        speech_service = _FakeSpeechService(
            enabled=True,
            next_result=TTSResult(
                ok=False,
                attempted=True,
                backend_name="fake_tts",
                error_message="Audio device missing.",
            ),
        )
        facade = EngineFacade(interaction_manager=manager, speech_service=speech_service)

        turn = facade.submit_text("Hello")

        self.assertEqual(turn.entries[-1].entry_kind, "warning")
        self.assertEqual(turn.entries[-1].text, "Audio device missing.")
        self.assertEqual(turn.status.speech_message, "Audio device missing.")

    def test_default_facade_uses_real_core_for_simple_question(self) -> None:
        facade = build_default_engine_facade()

        turn = facade.submit_text("What can you do?")

        self.assertEqual(turn.interaction_mode, "question")
        self.assertTrue(turn.entries)
        self.assertEqual(facade.snapshot().history[0].text, "What can you do?")


if __name__ == "__main__":
    unittest.main()
