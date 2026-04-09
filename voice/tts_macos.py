"""macOS-backed text-to-speech provider for JARVIS voice output."""

from __future__ import annotations

import os
import subprocess
import sys
from threading import Lock

from voice.tts_models import BackendCapabilities, VoiceDescriptor
from voice.tts_provider import SpeechUtterance, TTSResult
from voice.voice_profiles import fallback_voice_profile_ids

_BACKEND_NAME = "macos_say_legacy"
_DEFAULT_VOICE_CANDIDATES_BY_PROFILE = {
    "en_assistant_male": (
        "Daniel",
        "Samantha",
    ),
    "en_assistant_female": (
        "Samantha",
        "Daniel",
    ),
    "en_assistant_any": (
        "Daniel",
        "Samantha",
    ),
    "ru_assistant_male": (
        "Yuri",
        "Milena",
    ),
    "ru_assistant_female": (
        "Milena",
        "Yuri",
    ),
    "ru_assistant_any": (
        "Yuri",
        "Milena",
    ),
}
_DEFAULT_VOICE_CANDIDATES_BY_LOCALE_AND_PROFILE = {
    ("en-us", "en_assistant_male"): (
        "Reed (English (US))",
        "Eddy (English (US))",
        *_DEFAULT_VOICE_CANDIDATES_BY_PROFILE["en_assistant_male"],
    ),
    ("en-us", "en_assistant_any"): (
        "Reed (English (US))",
        "Eddy (English (US))",
        *_DEFAULT_VOICE_CANDIDATES_BY_PROFILE["en_assistant_any"],
    ),
    ("en-gb", "en_assistant_male"): (
        "Reed (English (UK))",
        "Eddy (English (UK))",
        *_DEFAULT_VOICE_CANDIDATES_BY_PROFILE["en_assistant_male"],
    ),
    ("en-gb", "en_assistant_any"): (
        "Reed (English (UK))",
        "Eddy (English (UK))",
        *_DEFAULT_VOICE_CANDIDATES_BY_PROFILE["en_assistant_any"],
    ),
}
_VOICE_METADATA_BY_ID = {
    "Daniel": {"gender_hint": "male", "quality_hint": "default", "source": "say"},
    "Eddy (English (UK))": {"gender_hint": "male", "quality_hint": "assistant", "source": "say"},
    "Eddy (English (US))": {"gender_hint": "male", "quality_hint": "assistant", "source": "say"},
    "Milena": {"gender_hint": "female", "quality_hint": "default", "source": "say"},
    "Reed (English (UK))": {"gender_hint": "male", "quality_hint": "assistant", "source": "say"},
    "Reed (English (US))": {"gender_hint": "male", "quality_hint": "assistant", "source": "say"},
    "Samantha": {"gender_hint": "female", "quality_hint": "default", "source": "say"},
    "Yuri": {"gender_hint": "male", "quality_hint": "default", "source": "say"},
}
_VOICE_ENV_BY_LANGUAGE = {
    "en": "JARVIS_TTS_EN_VOICE",
    "ru": "JARVIS_TTS_RU_VOICE",
}
_DEFAULT_RATE_BY_LANGUAGE = {
    "en": 190,
    "ru": 184,
}
_RATE_ENV_BY_LANGUAGE = {
    "en": "JARVIS_TTS_EN_RATE",
    "ru": "JARVIS_TTS_RU_RATE",
}
_GLOBAL_RATE_ENV = "JARVIS_TTS_RATE"
_AVAILABLE_VOICE_CACHE_UNSET = object()


class MacOSTTSProvider:
    """Speak prepared utterances through the macOS `say` command."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._current_process: subprocess.Popen[str] | None = None
        self._available_voices: tuple[VoiceDescriptor, ...] | None | object = _AVAILABLE_VOICE_CACHE_UNSET

    def speak(self, utterance: SpeechUtterance | None) -> TTSResult:
        message = str(getattr(utterance, "text", "") or "").strip()
        if not message:
            return TTSResult(ok=True, attempted=False, backend_name=_BACKEND_NAME)

        if sys.platform != "darwin":
            return TTSResult(
                ok=False,
                error_code="UNSUPPORTED_PLATFORM",
                error_message="Text-to-speech is available only on macOS.",
                backend_name=_BACKEND_NAME,
            )

        locale = str(getattr(utterance, "locale", "") or "").strip()
        available_voices = self._available_voice_names()
        rate = _preferred_rate_for_locale(locale)
        selected_voice_ids = _preferred_voice_ids_for_utterance(
            utterance,
            available_voices=available_voices,
        )

        first_failure: TTSResult | None = None
        for preferred_voice in selected_voice_ids:
            result = _run_say(_say_command(message, preferred_voice, rate), provider=self)
            if result.ok:
                return _with_backend_metadata(result, voice_id=preferred_voice)
            if first_failure is None:
                first_failure = _with_backend_metadata(result, voice_id=preferred_voice)

        fallback_result = _run_say(_say_command(message, None, rate), provider=self)
        if fallback_result.ok:
            return _with_backend_metadata(fallback_result, voice_id=None)
        return first_failure or fallback_result

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

    def _available_voice_names(self) -> set[str] | None:
        descriptors = self._available_voice_descriptors()
        if descriptors is None:
            return None
        return {descriptor.id for descriptor in descriptors}

    def list_voices(self, locale_hint: str | None = None) -> list[VoiceDescriptor]:
        """Return voice descriptors visible through `say -v ?`."""
        descriptors = list(self._available_voice_descriptors() or ())
        if not locale_hint:
            return descriptors
        return [descriptor for descriptor in descriptors if _locale_matches_hint(descriptor.locale, locale_hint)]

    def resolve_voice(self, profile: str | None, locale: str | None = None) -> VoiceDescriptor | None:
        """Resolve one product-level profile to an installed `say` voice."""
        descriptor_by_id = {descriptor.id: descriptor for descriptor in self.list_voices(locale_hint=locale)}
        override = _preferred_voice_override(locale)
        if override:
            descriptor = descriptor_by_id.get(override)
            if descriptor is not None:
                return descriptor
            return _override_voice_descriptor(override, locale)
        for candidate in _preferred_voice_ids(profile, locale, descriptor_by_id.keys()):
            descriptor = descriptor_by_id.get(candidate)
            if descriptor is not None:
                return descriptor
        return None

    def is_available(self) -> bool:
        """Return whether the legacy `say` backend can be used in this runtime."""
        return sys.platform == "darwin"

    def capabilities(self) -> BackendCapabilities:
        """Return structured capability metadata for the legacy `say` backend."""
        return BackendCapabilities(
            backend_name=_BACKEND_NAME,
            supports_stop=True,
            supports_voice_listing=True,
            supports_voice_resolution=True,
            supports_explicit_voice_id=True,
            supports_rate=True,
            is_fallback=True,
        )

    def availability_diagnostic(self) -> tuple[str | None, str | None]:
        """Return the current availability failure, if any."""
        if sys.platform == "darwin":
            return None, None
        return "UNSUPPORTED_PLATFORM", "Text-to-speech is available only on macOS."

    def _available_voice_descriptors(self) -> tuple[VoiceDescriptor, ...] | None:
        with self._lock:
            cached = self._available_voices
            if cached is _AVAILABLE_VOICE_CACHE_UNSET:
                cached = _list_available_voices()
                self._available_voices = cached
        return None if cached is _AVAILABLE_VOICE_CACHE_UNSET else cached


def _preferred_voice_ids_for_utterance(
    utterance: SpeechUtterance | None,
    *,
    available_voices: set[str] | None = None,
) -> list[str]:
    explicit_voice_id = str(getattr(utterance, "voice_id", "") or "").strip()
    profile = str(getattr(utterance, "voice_profile", "") or "").strip()
    locale = str(getattr(utterance, "locale", "") or "").strip()
    return _dedupe_preserving_order(
        [
            explicit_voice_id,
            *_preferred_voice_ids(profile or None, locale or None, available_voices),
        ]
    )


def _preferred_voice_ids(
    profile: str | None,
    locale: str | None,
    available_voices: set[str] | None = None,
) -> list[str]:
    locale_text = str(locale or "").strip()
    normalized_locale = locale_text.lower()
    language = normalized_locale.split("-", maxsplit=1)[0]
    if not language and not profile:
        return []

    override = _preferred_voice_override(locale)
    candidates: list[str | None] = [override]
    for profile_id in fallback_voice_profile_ids(profile, locale):
        candidates.extend(_DEFAULT_VOICE_CANDIDATES_BY_LOCALE_AND_PROFILE.get((normalized_locale, profile_id), ()))
        candidates.extend(_DEFAULT_VOICE_CANDIDATES_BY_PROFILE.get(profile_id, ()))
    raw_candidates = _dedupe_preserving_order(candidates)
    if available_voices is None:
        return raw_candidates

    filtered = [
        candidate
        for candidate in raw_candidates
        if candidate == override or candidate in available_voices
    ]
    return filtered or raw_candidates


def _preferred_voice_override(locale: str | None) -> str | None:
    locale_text = str(locale or "").strip()
    normalized_locale = locale_text.lower()
    language = normalized_locale.split("-", maxsplit=1)[0]
    env_name = _VOICE_ENV_BY_LANGUAGE.get(language, "")
    if not env_name:
        return None
    override = os.environ.get(env_name, "").strip()
    return override or None


def _preferred_rate_for_locale(locale: str | None) -> int | None:
    locale_text = str(locale or "").strip()
    normalized_locale = locale_text.lower()
    language = normalized_locale.split("-", maxsplit=1)[0]

    for env_name in (_RATE_ENV_BY_LANGUAGE.get(language, ""), _GLOBAL_RATE_ENV):
        rate = _parse_rate(os.environ.get(env_name, ""))
        if rate is not None:
            return rate
    return _DEFAULT_RATE_BY_LANGUAGE.get(language)


def _say_command(message: str, voice: str | None, rate: int | None) -> list[str]:
    command = ["say"]
    if voice:
        command.extend(["-v", voice])
    if rate is not None:
        command.extend(["-r", str(rate)])
    command.append(message)
    return command


def _list_available_voices() -> tuple[VoiceDescriptor, ...] | None:
    try:
        result = subprocess.run(
            ["say", "-v", "?"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None

    voices: list[VoiceDescriptor] = []
    for line in str(result.stdout or "").splitlines():
        descriptor = _voice_descriptor_from_listing(line)
        if descriptor is not None:
            voices.append(descriptor)
    return tuple(voices) or None


def _voice_descriptor_from_listing(line: str) -> VoiceDescriptor | None:
    head = str(line or "").split("#", maxsplit=1)[0].rstrip()
    if not head:
        return None
    parts = head.split()
    if len(parts) < 2:
        return None
    locale_token = parts[-1]
    if "_" not in locale_token and "-" not in locale_token:
        return None
    voice_id = head[: head.rfind(locale_token)].rstrip()
    if not voice_id:
        return None
    metadata = _VOICE_METADATA_BY_ID.get(voice_id, {})
    return VoiceDescriptor(
        id=voice_id,
        display_name=voice_id,
        locale=_normalize_locale(locale_token),
        gender_hint=str(metadata.get("gender_hint") or "").strip() or None,
        quality_hint=str(metadata.get("quality_hint") or "").strip() or None,
        source=str(metadata.get("source") or "say"),
        is_default=False,
    )


def _normalize_locale(locale_token: str | None) -> str | None:
    normalized = str(locale_token or "").strip().replace("_", "-")
    return normalized or None


def _override_voice_descriptor(voice_id: str | None, locale: str | None) -> VoiceDescriptor | None:
    normalized_voice_id = str(voice_id or "").strip()
    if not normalized_voice_id:
        return None
    metadata = _VOICE_METADATA_BY_ID.get(normalized_voice_id, {})
    return VoiceDescriptor(
        id=normalized_voice_id,
        display_name=normalized_voice_id,
        locale=_normalize_locale(locale),
        gender_hint=str(metadata.get("gender_hint") or "").strip() or None,
        quality_hint=str(metadata.get("quality_hint") or "").strip() or None,
        source=str(metadata.get("source") or "say"),
        is_default=False,
    )


def _locale_matches_hint(locale: str | None, locale_hint: str | None) -> bool:
    normalized_locale = str(locale or "").strip().lower()
    normalized_hint = str(locale_hint or "").strip().lower().replace("_", "-")
    if not normalized_hint:
        return True
    if normalized_locale == normalized_hint:
        return True
    return normalized_locale.split("-", maxsplit=1)[0] == normalized_hint.split("-", maxsplit=1)[0]


def _parse_rate(raw_value: str | None) -> int | None:
    value = str(raw_value or "").strip()
    if not value:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def _dedupe_preserving_order(items: list[str | None]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        candidate = str(item or "").strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        result.append(candidate)
    return result


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
            backend_name=_BACKEND_NAME,
        )
    if provider is not None:
        provider._set_current_process(process)
    try:
        stdout, stderr = process.communicate()
    finally:
        if provider is not None:
            provider._clear_current_process(process)

    if process.returncode == 0:
        return TTSResult(ok=True, backend_name=_BACKEND_NAME)

    detail = _first_meaningful_line(stderr or stdout)
    return TTSResult(
        ok=False,
        error_code="TTS_FAILED",
        error_message=detail or "Speech synthesis failed.",
        backend_name=_BACKEND_NAME,
    )


def _first_meaningful_line(text: str | None) -> str:
    for line in str(text or "").splitlines():
        candidate = line.strip()
        if candidate:
            return candidate
    return ""


def _with_backend_metadata(result: TTSResult, *, voice_id: str | None) -> TTSResult:
    if result.backend_name == _BACKEND_NAME and result.voice_id == voice_id:
        return result
    return TTSResult(
        ok=result.ok,
        attempted=result.attempted,
        error_code=result.error_code,
        error_message=result.error_message,
        backend_name=result.backend_name or _BACKEND_NAME,
        voice_id=result.voice_id or voice_id,
    )
