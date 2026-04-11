"""Desktop speech-output service built on top of the existing JARVIS TTS stack."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import os
from typing import MutableMapping

from voice.status import TTSBackendStatus, build_tts_backend_status
from voice.tts_provider import SpeechUtterance, TTSProvider, TTSResult, build_default_tts_provider, stop_speech_if_supported
from voice.tts_runtime_env import apply_cli_tts_env_defaults


@dataclass(slots=True)
class SpeechState:
    """Current desktop speech-output state."""

    enabled: bool = False
    available: bool | None = None
    backend_name: str | None = None
    message: str | None = None


class DesktopSpeechService:
    """Own desktop speech-output state and the underlying TTS provider lifecycle."""

    def __init__(
        self,
        *,
        tts_provider: TTSProvider | None = None,
        provider_factory: Callable[[], TTSProvider] | None = None,
        environ: MutableMapping[str, str] | None = None,
    ) -> None:
        self._environ = dict(os.environ) if environ is None else environ
        apply_cli_tts_env_defaults(self._environ)
        self._provider = tts_provider
        self._provider_factory = provider_factory or (lambda: build_default_tts_provider(environ=self._environ))
        self._enabled = False
        self._backend_name: str | None = None
        self._available: bool | None = None
        self._message: str | None = "Speech output is off."
        if self._provider is not None:
            self._refresh_backend_status()

    @property
    def enabled(self) -> bool:
        """Return whether desktop speech output is currently enabled."""
        return self._enabled

    def snapshot(self) -> SpeechState:
        """Return the current speech state for desktop UI rendering."""
        return SpeechState(
            enabled=self._enabled,
            available=self._available,
            backend_name=self._backend_name,
            message=self._message or "Speech output is off.",
        )

    def set_enabled(self, enabled: bool) -> SpeechState:
        """Enable or disable desktop speech output."""
        if not enabled:
            self._enabled = False
            stop_speech_if_supported(self._provider)
            self._message = "Speech output disabled."
            return self.snapshot()

        provider = self._ensure_provider()
        if provider is None:
            self._enabled = False
            if not self._message:
                self._message = "Speech output is unavailable."
            return self.snapshot()

        self._enabled = True
        self._refresh_backend_status()
        backend_name = self._backend_name or "the active backend"
        self._message = f"Speech output enabled via {backend_name}."
        return self.snapshot()

    def speak(self, utterance: SpeechUtterance | None) -> TTSResult | None:
        """Speak one prepared utterance when desktop speech output is enabled."""
        if utterance is None or not self._enabled:
            return None

        provider = self._ensure_provider()
        if provider is None:
            return TTSResult(
                ok=False,
                attempted=True,
                error_code="TTS_UNAVAILABLE",
                error_message=self._message or "Speech output is unavailable.",
                backend_name=self._backend_name or "unavailable",
            )

        try:
            result = provider.speak(utterance)
        except Exception as exc:
            result = TTSResult(
                ok=False,
                attempted=True,
                error_code="TTS_EXCEPTION",
                error_message=str(exc) or "Speech output failed.",
                backend_name=self._backend_name or "unavailable",
            )

        backend_name = str(result.backend_name or self._backend_name or "unavailable").strip() or "unavailable"
        self._backend_name = backend_name
        if result.ok:
            self._available = True
            self._message = f"Speech output enabled via {backend_name}."
        else:
            detail = str(result.error_message or "").strip() or f"Speech output failed via {backend_name}."
            if self._available is None:
                self._available = False
            self._message = detail
        return result

    def stop(self) -> bool:
        """Stop any active speech output before an explicit new voice capture."""
        return stop_speech_if_supported(self._provider)

    def _ensure_provider(self) -> TTSProvider | None:
        if self._provider is None:
            try:
                self._provider = self._provider_factory()
            except Exception as exc:
                self._backend_name = "unavailable"
                self._available = False
                self._message = str(exc) or "Speech backend failed to initialize."
                return None
        self._refresh_backend_status()
        if self._available is False:
            return None
        return self._provider

    def _refresh_backend_status(self) -> None:
        status = build_tts_backend_status(self._provider)
        self._backend_name = status.backend_name
        self._available = status.available
        if status.available:
            if self._enabled:
                self._message = f"Speech output enabled via {status.backend_name}."
            elif not self._message:
                self._message = f"Speech ready via {status.backend_name}."
            return
        self._message = _backend_unavailable_message(status)


def _backend_unavailable_message(status: TTSBackendStatus) -> str:
    detail = (
        str(status.selection_note or "").strip()
        or next((str(hint).strip() for hint in status.guidance if str(hint).strip()), "")
        or next(
            (
                str(diagnostic.error_message or "").strip()
                for diagnostic in status.diagnostics
                if str(diagnostic.error_message or "").strip()
            ),
            "",
        )
    )
    if detail:
        return f"Speech output is unavailable: {detail}"
    backend_name = str(status.backend_name or "unavailable").strip() or "unavailable"
    return f"Speech output is unavailable via {backend_name}."
