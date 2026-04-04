"""macOS-backed text-to-speech provider for JARVIS voice output."""

from __future__ import annotations

import os
import subprocess
import sys
from threading import Lock

from voice.tts_provider import SpeechUtterance, TTSResult

_DEFAULT_VOICE_BY_LANGUAGE = {
    "en": "Samantha",
    "ru": "Milena",
}
_VOICE_ENV_BY_LANGUAGE = {
    "en": "JARVIS_TTS_EN_VOICE",
    "ru": "JARVIS_TTS_RU_VOICE",
}


class MacOSTTSProvider:
    """Speak prepared utterances through the macOS `say` command."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._current_process: subprocess.Popen[str] | None = None

    def speak(self, utterance: SpeechUtterance | None) -> TTSResult:
        message = str(getattr(utterance, "text", "") or "").strip()
        if not message:
            return TTSResult(ok=True, attempted=False)

        if sys.platform != "darwin":
            return TTSResult(
                ok=False,
                error_code="UNSUPPORTED_PLATFORM",
                error_message="Text-to-speech is available only on macOS.",
            )

        locale = str(getattr(utterance, "locale", "") or "").strip()
        preferred_voice = _preferred_voice_for_locale(locale)
        primary_result = _run_say(_say_command(message, preferred_voice), provider=self)
        if primary_result.ok:
            return primary_result

        if preferred_voice:
            fallback_result = _run_say(_say_command(message, None), provider=self)
            if fallback_result.ok:
                return fallback_result

        return primary_result

    def stop(self) -> bool:
        """Stop the currently running macOS `say` process when one is active."""
        with self._lock:
            process = self._current_process
        if process is None or process.poll() is not None:
            return False
        try:
            process.terminate()
            try:
                process.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=0.2)
        except OSError:
            return False
        finally:
            self._clear_current_process(process)
        return True

    def _set_current_process(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            self._current_process = process

    def _clear_current_process(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            if self._current_process is process:
                self._current_process = None


def _preferred_voice_for_locale(locale: str | None) -> str | None:
    locale_text = str(locale or "").strip()
    if not locale_text:
        return None

    language = locale_text.split("-", maxsplit=1)[0].lower()
    if not language:
        return None

    override = os.environ.get(_VOICE_ENV_BY_LANGUAGE.get(language, ""), "").strip()
    if override:
        return override
    return _DEFAULT_VOICE_BY_LANGUAGE.get(language)


def _say_command(message: str, voice: str | None) -> list[str]:
    if voice:
        return ["say", "-v", voice, message]
    return ["say", message]


def _run_say(command: list[str], *, provider: MacOSTTSProvider | None = None) -> TTSResult:
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as exc:
        return TTSResult(
            ok=False,
            error_code="TTS_UNAVAILABLE",
            error_message=str(exc),
        )
    if provider is not None:
        provider._set_current_process(process)
    try:
        stdout, stderr = process.communicate()
    finally:
        if provider is not None:
            provider._clear_current_process(process)

    if process.returncode == 0:
        return TTSResult(ok=True)

    detail = _first_meaningful_line(stderr or stdout)
    return TTSResult(
        ok=False,
        error_code="TTS_FAILED",
        error_message=detail or "Speech synthesis failed.",
    )


def _first_meaningful_line(text: str | None) -> str:
    for line in str(text or "").splitlines():
        candidate = line.strip()
        if candidate:
            return candidate
    return ""
