"""Desktop backend facade over the existing JARVIS core modules."""

from __future__ import annotations

from dataclasses import replace

from context.session_context import SessionContext
from desktop.backend.presenters import present_interaction_result
from desktop.backend.session_service import BackendSessionService
from desktop.backend.speech_service import DesktopSpeechService, SpeechState
from desktop.backend.view_models import SessionSnapshotViewModel, StatusViewModel, TranscriptEntry, TurnViewModel
from input.voice_input import VoiceInputError
from interaction.interaction_manager import InteractionManager
from voice.dispatcher import dispatch_interaction_input
from voice.language import detect_spoken_locale
from voice.session import capture_cli_voice_turn
from voice.tts_provider import TTSResult

_VOICE_CAPTURE_TIMEOUT_SECONDS = 8.0


class EngineFacade:
    """Thin desktop boundary around the current JARVIS interaction engine."""

    def __init__(
        self,
        *,
        interaction_manager: InteractionManager | None = None,
        session_service: BackendSessionService | None = None,
        session_context: SessionContext | None = None,
        speech_service: DesktopSpeechService | None = None,
    ) -> None:
        self._session_service = session_service or BackendSessionService(session_context=session_context)
        self._interaction_manager = interaction_manager or InteractionManager()
        self._speech_service = speech_service or DesktopSpeechService()

    @property
    def session_context(self) -> SessionContext:
        """Return the shared core session context."""
        return self._session_service.session_context

    @property
    def speech_enabled(self) -> bool:
        """Return whether desktop speech output is enabled."""
        return self._speech_service.enabled

    def submit_text(self, raw_input: str) -> TurnViewModel:
        """Submit one text turn through the existing JARVIS core."""
        text = str(raw_input or "").strip()
        shell_turn = self._handle_shell_command(text)
        if shell_turn is not None:
            self._session_service.record_turn(shell_turn)
            return shell_turn

        dispatch_result = dispatch_interaction_input(
            text,
            interaction_manager=self._interaction_manager,
            session_context=self.session_context,
            speak_enabled=self._speech_service.enabled,
            speech_locale_hint=_preferred_speech_locale_hint(text) if self._speech_service.enabled else None,
        )
        turn = present_interaction_result(text, dispatch_result.interaction_result)
        if dispatch_result.speech_utterance is not None:
            turn.metadata["speech_text"] = dispatch_result.speech_utterance.text
            turn.metadata["speech_locale"] = dispatch_result.speech_utterance.locale
        speech_result = self._speech_service.speak(dispatch_result.speech_utterance)
        turn = self._apply_speech_result(turn, speech_result=speech_result)
        self._session_service.record_turn(turn)
        return turn

    def snapshot(self) -> SessionSnapshotViewModel:
        """Return the latest desktop-visible session state."""
        snapshot = self._session_service.snapshot()
        snapshot.status = _merge_speech_status(snapshot.status, self._speech_service.snapshot())
        return snapshot

    def set_speech_enabled(self, enabled: bool) -> SessionSnapshotViewModel:
        """Enable or disable desktop speech output without adding a transcript entry."""
        self._speech_service.set_enabled(bool(enabled))
        return self.snapshot()

    def reset_session(self) -> SessionSnapshotViewModel:
        """Reset desktop history and the underlying supervised runtime state."""
        runtime_manager = getattr(self._interaction_manager, "runtime_manager", None)
        clear_runtime = getattr(runtime_manager, "clear_runtime", None)
        if callable(clear_runtime):
            clear_runtime()
        self.session_context.clear_expired_or_resettable_context(preserve_recent_context=False)
        self._session_service.reset()
        return self.snapshot()

    def capture_voice_text(self) -> str:
        """Capture one spoken request for the desktop shell and return its transcript."""
        self._speech_service.stop()
        voice_turn = capture_cli_voice_turn(timeout_seconds=_VOICE_CAPTURE_TIMEOUT_SECONDS)
        transcript = str(getattr(voice_turn, "normalized_text", "") or "").strip()
        if transcript:
            return transcript
        raise VoiceInputError("EMPTY_RECOGNITION", "No speech was recognized. Try again.")

    def _handle_shell_command(self, raw_input: str) -> TurnViewModel | None:
        lowered = raw_input.casefold()
        if lowered in {"speak on", "/speak on"}:
            speech_state = self._speech_service.set_enabled(True)
            return _build_shell_turn(
                raw_input=raw_input,
                message=speech_state.message or "Speech output enabled.",
                speech_state=speech_state,
                failed=not speech_state.enabled,
            )
        if lowered in {"speak off", "/speak off"}:
            speech_state = self._speech_service.set_enabled(False)
            return _build_shell_turn(
                raw_input=raw_input,
                message=speech_state.message or "Speech output disabled.",
                speech_state=speech_state,
                failed=False,
            )
        return None

    def _apply_speech_result(self, turn: TurnViewModel, *, speech_result: TTSResult | None) -> TurnViewModel:
        if speech_result is not None:
            turn.metadata["speech_attempted"] = bool(speech_result.attempted)
            turn.metadata["speech_backend"] = speech_result.backend_name
            if speech_result.attempted and not speech_result.ok:
                detail = str(speech_result.error_message or "").strip() or "speech: unavailable."
                turn.entries.append(
                    TranscriptEntry(
                        role="system",
                        text=detail,
                        entry_kind="warning",
                        metadata={
                            "speech_backend": str(speech_result.backend_name or "").strip() or None,
                            "speech_error_code": speech_result.error_code,
                        },
                    )
                )
        turn.status = _merge_speech_status(turn.status, self._speech_service.snapshot())
        return turn


def build_default_engine_facade() -> EngineFacade:
    """Create the default desktop backend facade."""
    return EngineFacade()


def _preferred_speech_locale_hint(text: str) -> str | None:
    """Only pass a locale hint when the text is clearly Russian."""
    detected_locale = detect_spoken_locale(text)
    if detected_locale.startswith("ru"):
        return detected_locale
    return None


def _merge_speech_status(status: StatusViewModel, speech_state: SpeechState) -> StatusViewModel:
    return replace(
        status,
        speech_enabled=speech_state.enabled,
        speech_available=speech_state.available,
        speech_backend=speech_state.backend_name,
        speech_message=speech_state.message,
    )


def _build_shell_turn(
    *,
    raw_input: str,
    message: str,
    speech_state: SpeechState,
    failed: bool,
) -> TurnViewModel:
    entry_kind = "error" if failed else "result"
    role = "system" if failed else "assistant"
    status = _merge_speech_status(
        StatusViewModel(
            interaction_mode="desktop_shell",
            runtime_state="idle",
            completion_result=None if failed else message,
            failure_message=message if failed else None,
        ),
        speech_state,
    )
    return TurnViewModel(
        input_text=raw_input,
        interaction_mode="desktop_shell",
        entries=[
            TranscriptEntry(
                role=role,
                text=message,
                entry_kind=entry_kind,
                metadata={"speech_backend": speech_state.backend_name},
            )
        ],
        status=status,
        metadata={"desktop_command": raw_input.casefold()},
    )
