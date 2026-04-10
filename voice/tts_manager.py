"""Backend-neutral manager for local text-to-speech backends."""

from __future__ import annotations

from dataclasses import replace
import os
import re
import sys
from typing import Mapping

from voice.tts_models import BackendCapabilities, BackendRuntimeStatus, VoiceDescriptor, VoiceResolutionTrace
from voice.tts_provider import SpeechUtterance, TTSBackend, TTSResult
from voice.voice_profiles import default_voice_profile_for_locale, fallback_voice_profile_ids

_MACOS_NATIVE_BACKEND_ENV = "JARVIS_TTS_MACOS_NATIVE"
_RU_BACKEND_ENV = "JARVIS_TTS_RU_BACKEND"
_EN_BACKEND_ENV = "JARVIS_TTS_EN_BACKEND"
_RU_ALLOW_FALLBACK_ENV = "JARVIS_TTS_RU_ALLOW_FALLBACK"
_EN_ALLOW_FALLBACK_ENV = "JARVIS_TTS_EN_ALLOW_FALLBACK"
_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_YANDEX_BACKEND_NAME = "yandex_speechkit"


class TTSManager:
    """Resolve product profiles and route speech through the configured backends."""

    def __init__(
        self,
        backends: list[TTSBackend] | None = None,
        *,
        environ: Mapping[str, str] | None = None,
        configuration_notes: tuple[str, ...] | None = None,
    ) -> None:
        self._backends = tuple(backends if backends is not None else _default_backends_for_platform(sys.platform))
        self._environ = environ
        self._configuration_notes = tuple(
            note
            for note in (str(item or "").strip() for item in tuple(configuration_notes or ()))
            if note
        )

    def speak(self, utterance: SpeechUtterance | None) -> TTSResult:
        message = str(getattr(utterance, "text", "") or "").strip()
        if not message:
            return TTSResult(ok=True, attempted=False, backend_name=self.backend_name())

        prepared = self._prepare_utterance(utterance)
        first_failure: TTSResult | None = None
        for backend in self._candidate_backends(prepared):
            resolved_voice = (
                backend.resolve_voice(prepared.voice_profile, prepared.locale)
                if not prepared.voice_id
                else None
            )
            backend_utterance = prepared
            if resolved_voice is not None:
                backend_utterance = replace(
                    backend_utterance,
                    voice_id=backend_utterance.voice_id or resolved_voice.id,
                )
            result = backend.speak(backend_utterance)
            normalized = _normalize_result(
                result,
                backend_name=backend.capabilities().backend_name,
                voice_id=backend_utterance.voice_id,
            )
            if normalized.ok:
                return normalized
            if first_failure is None:
                first_failure = normalized

        return first_failure or TTSResult(
            ok=False,
            error_code="UNSUPPORTED_PLATFORM",
            error_message="Text-to-speech backend is unavailable on this platform.",
            backend_name=self.backend_name(),
        )

    def stop(self) -> bool:
        """Stop speech in every configured backend until one reports success."""
        stopped = False
        for backend in self._available_backends():
            try:
                stopped = backend.stop() or stopped
            except Exception:
                continue
        return stopped

    def list_voices(self, locale_hint: str | None = None) -> list[VoiceDescriptor]:
        """Return voices from the currently preferred available backend."""
        backend = self._primary_backend()
        if backend is None:
            return []
        return list(backend.list_voices(locale_hint=locale_hint))

    def resolve_voice(self, profile: str | None, locale: str | None = None) -> VoiceDescriptor | None:
        """Resolve one product-level profile to the first backend-native voice."""
        return self.resolve_voice_trace(profile, locale).resolved_voice

    def resolve_voice_trace(self, profile: str | None, locale: str | None = None) -> VoiceResolutionTrace:
        """Return one structured explanation of profile resolution and fallback."""
        requested_profile_id = str(profile or default_voice_profile_for_locale(locale) or "").strip()
        attempted_profile_ids = fallback_voice_profile_ids(requested_profile_id or None, locale)
        if not attempted_profile_ids and requested_profile_id:
            attempted_profile_ids = (requested_profile_id,)

        for backend in self._available_backends():
            backend_name = _backend_capabilities(backend).backend_name
            for attempted_profile_id in attempted_profile_ids:
                voice = backend.resolve_voice(attempted_profile_id, locale)
                if voice is None:
                    continue
                return VoiceResolutionTrace(
                    requested_profile_id=requested_profile_id,
                    locale=locale,
                    attempted_profile_ids=attempted_profile_ids,
                    resolved_profile_id=attempted_profile_id,
                    backend_name=backend_name,
                    resolved_voice=voice,
                    note=_resolution_note(
                        requested_profile_id=requested_profile_id,
                        resolved_profile_id=attempted_profile_id,
                        backend_name=backend_name,
                    ),
                )

        return VoiceResolutionTrace(
            requested_profile_id=requested_profile_id,
            locale=locale,
            attempted_profile_ids=attempted_profile_ids,
            resolved_profile_id=None,
            backend_name=self.backend_name(),
            resolved_voice=None,
            note=_unresolved_resolution_note(
                requested_profile_id=requested_profile_id,
                attempted_profile_ids=attempted_profile_ids,
                backend_name=self.backend_name(),
            ),
        )

    def is_available(self) -> bool:
        """Return whether at least one backend is ready."""
        return any(True for _ in self._available_backends())

    def capabilities(self) -> BackendCapabilities:
        """Expose the currently preferred backend capabilities."""
        backend = self._primary_backend()
        if backend is not None:
            return backend.capabilities()
        return BackendCapabilities(backend_name="unavailable", is_fallback=True)

    def backend_name(self) -> str:
        """Return the active backend name or an unavailable sentinel."""
        return self.capabilities().backend_name

    def backend_diagnostics(self) -> tuple[BackendRuntimeStatus, ...]:
        """Return ordered backend availability and fallback diagnostics."""
        primary_backend = self._primary_backend()
        return tuple(
            _backend_runtime_status(
                backend,
                selected=backend is primary_backend,
            )
            for backend in self._backends
        )

    def configuration_notes(self) -> tuple[str, ...]:
        """Return operator-facing notes about current CLI-side TTS configuration."""
        return self._configuration_notes

    def _prepare_utterance(self, utterance: SpeechUtterance | None) -> SpeechUtterance:
        current = utterance or SpeechUtterance(text="")
        if current.voice_profile:
            return current
        default_profile = default_voice_profile_for_locale(current.locale)
        if default_profile is None:
            return current
        return replace(current, voice_profile=default_profile)

    def _available_backends(self) -> tuple[TTSBackend, ...]:
        return tuple(backend for backend in self._backends if _backend_is_available(backend))

    def _candidate_backends(self, utterance: SpeechUtterance | None = None) -> tuple[TTSBackend, ...]:
        available = self._available_backends()
        if not available or utterance is None:
            return available
        preferred_language = _utterance_language(utterance)
        explicit_voice_backend = _voice_backend_name(utterance.voice_id)
        if explicit_voice_backend == _YANDEX_BACKEND_NAME:
            return _stable_partition_backends(
                available,
                predicate=lambda backend: _backend_capabilities(backend).backend_name == _YANDEX_BACKEND_NAME,
            )
        pinned_backend_name = self._pinned_backend_name(preferred_language)
        if pinned_backend_name:
            pinned_backends = tuple(
                backend
                for backend in available
                if _backend_capabilities(backend).backend_name == pinned_backend_name
            )
            if pinned_backends:
                if not self._language_fallback_allowed(preferred_language):
                    return pinned_backends
                return _stable_partition_backends(
                    available,
                    predicate=lambda backend: _backend_capabilities(backend).backend_name == pinned_backend_name,
                )
        if preferred_language == "ru":
            yandex_backends = tuple(
                backend
                for backend in available
                if _backend_capabilities(backend).backend_name == _YANDEX_BACKEND_NAME
            )
            if yandex_backends and not self._language_fallback_allowed(preferred_language):
                return yandex_backends
            return _stable_partition_backends(
                available,
                predicate=lambda backend: _backend_capabilities(backend).backend_name == _YANDEX_BACKEND_NAME,
            )
        if preferred_language == "en":
            return _stable_partition_backends(
                available,
                predicate=lambda backend: _backend_capabilities(backend).backend_name != _YANDEX_BACKEND_NAME,
            )
        return available

    def _pinned_backend_name(self, language: str) -> str | None:
        if language == "ru":
            return _normalized_backend_pin(self._env(_RU_BACKEND_ENV))
        if language == "en":
            return _normalized_backend_pin(self._env(_EN_BACKEND_ENV))
        return None

    def _language_fallback_allowed(self, language: str) -> bool:
        if language == "ru":
            return _env_enabled(self._env(_RU_ALLOW_FALLBACK_ENV))
        if language == "en":
            return _env_enabled(self._env(_EN_ALLOW_FALLBACK_ENV))
        return True

    def _env(self, name: str) -> str:
        current = os.environ if self._environ is None else self._environ
        return str(current.get(name, "") or "").strip()

    def _primary_backend(self) -> TTSBackend | None:
        return next(iter(self._available_backends()), None)


def build_default_tts_manager(
    *,
    platform: str | None = None,
    environ: Mapping[str, str] | None = None,
    configuration_notes: tuple[str, ...] | None = None,
) -> TTSManager:
    """Build the default local manager for the current platform."""
    return TTSManager(
        backends=_default_backends_for_platform(platform or sys.platform, environ=environ),
        environ=environ,
        configuration_notes=configuration_notes,
    )


def _default_backends_for_platform(platform: str, *, environ: Mapping[str, str] | None = None) -> list[TTSBackend]:
    backends: list[TTSBackend] = []
    if _yandex_speechkit_backend_visible(environ):
        from voice.backends.yandex_speechkit import YandexSpeechKitTTSBackend

        backends.append(YandexSpeechKitTTSBackend(environ=environ))
    if _local_piper_backend_requested(environ):
        from voice.backends.piper import PiperTTSBackend

        backends.append(PiperTTSBackend(environ=environ))
    if platform == "darwin":
        if _native_macos_backend_enabled(environ):
            from voice.backends.macos_native import MacOSNativeTTSBackend

            backends.append(MacOSNativeTTSBackend())
        from voice.tts_macos import MacOSTTSProvider

        backends.append(MacOSTTSProvider())
        return backends
    return backends


def _backend_is_available(backend: TTSBackend) -> bool:
    try:
        return bool(backend.is_available())
    except Exception:
        return False


def _backend_capabilities(backend: TTSBackend) -> BackendCapabilities:
    try:
        capabilities = backend.capabilities()
    except Exception:
        return BackendCapabilities(backend_name=type(backend).__name__, is_fallback=True)
    return capabilities if isinstance(capabilities, BackendCapabilities) else BackendCapabilities(
        backend_name=str(getattr(capabilities, "backend_name", "") or type(backend).__name__),
        supports_stop=bool(getattr(capabilities, "supports_stop", False)),
        supports_voice_listing=bool(getattr(capabilities, "supports_voice_listing", False)),
        supports_voice_resolution=bool(getattr(capabilities, "supports_voice_resolution", False)),
        supports_explicit_voice_id=bool(getattr(capabilities, "supports_explicit_voice_id", False)),
        supports_rate=bool(getattr(capabilities, "supports_rate", False)),
        supports_pitch=bool(getattr(capabilities, "supports_pitch", False)),
        supports_volume=bool(getattr(capabilities, "supports_volume", False)),
        is_fallback=bool(getattr(capabilities, "is_fallback", False)),
    )


def _backend_runtime_status(
    backend: TTSBackend,
    *,
    selected: bool,
) -> BackendRuntimeStatus:
    capabilities = _backend_capabilities(backend)
    available, error_code, error_message = _backend_availability_details(backend)
    return BackendRuntimeStatus(
        backend_name=capabilities.backend_name,
        available=available,
        selected=selected and available,
        error_code=error_code,
        error_message=error_message,
        detail_lines=_backend_availability_detail_lines(backend, available=available),
        capabilities=capabilities,
    )


def _backend_availability_details(backend: TTSBackend) -> tuple[bool, str | None, str | None]:
    try:
        available = bool(backend.is_available())
    except Exception as exc:
        return False, "BACKEND_CHECK_FAILED", str(exc)
    if available:
        return True, None, None

    diagnostic_method = getattr(backend, "availability_diagnostic", None)
    if callable(diagnostic_method):
        try:
            raw_diagnostic = diagnostic_method()
        except Exception as exc:
            return False, "BACKEND_CHECK_FAILED", str(exc)
        if isinstance(raw_diagnostic, tuple) and len(raw_diagnostic) == 2:
            error_code = str(raw_diagnostic[0] or "").strip() or None
            error_message = str(raw_diagnostic[1] or "").strip() or None
            return False, error_code, error_message
    return False, None, None


def _backend_availability_detail_lines(
    backend: TTSBackend,
    *,
    available: bool,
) -> tuple[str, ...]:
    if available:
        return ()
    details_method = getattr(backend, "availability_detail_lines", None)
    if not callable(details_method):
        return ()
    try:
        raw_lines = details_method()
    except Exception:
        return ()
    return tuple(
        line
        for line in (str(item or "").strip() for item in tuple(raw_lines or ()))
        if line
    )


def _normalize_result(result: TTSResult, *, backend_name: str, voice_id: str | None) -> TTSResult:
    if result.backend_name == backend_name and result.voice_id == voice_id:
        return result
    return replace(
        result,
        backend_name=result.backend_name or backend_name,
        voice_id=result.voice_id or voice_id,
    )


def _native_macos_backend_enabled(environ: Mapping[str, str] | None = None) -> bool:
    value = str((environ or os.environ).get(_MACOS_NATIVE_BACKEND_ENV, "") or "").strip().lower()
    if value in {"0", "false", "no", "off"}:
        return False
    if value in {"1", "true", "yes", "on"}:
        return True
    return True


def _local_piper_backend_requested(environ: Mapping[str, str] | None = None) -> bool:
    from voice.backends.piper import piper_backend_requested

    return piper_backend_requested(environ)


def _yandex_speechkit_backend_requested(environ: Mapping[str, str] | None = None) -> bool:
    from voice.backends.yandex_speechkit import yandex_speechkit_backend_requested

    return yandex_speechkit_backend_requested(environ)


def _yandex_speechkit_backend_visible(environ: Mapping[str, str] | None = None) -> bool:
    from voice.backends.yandex_speechkit import yandex_speechkit_backend_configured

    return yandex_speechkit_backend_configured(environ)


def _voice_backend_name(voice_id: str | None) -> str | None:
    current = str(voice_id or "").strip()
    if current.startswith("yandex:"):
        return _YANDEX_BACKEND_NAME
    return None


def _utterance_language(utterance: SpeechUtterance | None) -> str:
    current = utterance or SpeechUtterance(text="")
    locale = str(current.locale or "").strip().lower()
    if locale.startswith("ru"):
        return "ru"
    if locale.startswith("en"):
        return "en"
    text = str(current.text or "")
    if _CYRILLIC_RE.search(text):
        return "ru"
    if _LATIN_RE.search(text):
        return "en"
    return ""


def _stable_partition_backends(
    backends: tuple[TTSBackend, ...],
    *,
    predicate,
) -> tuple[TTSBackend, ...]:
    preferred = tuple(backend for backend in backends if predicate(backend))
    remaining = tuple(backend for backend in backends if not predicate(backend))
    return (*preferred, *remaining)


def _normalized_backend_pin(value: str | None) -> str | None:
    current = str(value or "").strip().lower().replace("-", "_")
    if not current:
        return None
    aliases = {
        "yandex": _YANDEX_BACKEND_NAME,
        "yandex_speechkit": _YANDEX_BACKEND_NAME,
        "speechkit": _YANDEX_BACKEND_NAME,
        "piper": "local_piper",
        "local_piper": "local_piper",
        "macos_native": "macos_native",
        "native": "macos_native",
        "say": "macos_say_legacy",
        "legacy": "macos_say_legacy",
        "macos_say_legacy": "macos_say_legacy",
    }
    return aliases.get(current, current)


def _env_enabled(value: str | None) -> bool:
    current = str(value or "").strip().lower()
    return current in {"1", "true", "yes", "on"}


def _resolution_note(
    *,
    requested_profile_id: str,
    resolved_profile_id: str,
    backend_name: str,
) -> str:
    if requested_profile_id and requested_profile_id == resolved_profile_id:
        return f"resolved requested profile on {backend_name}"
    if requested_profile_id:
        return f"resolved via fallback profile {resolved_profile_id} on {backend_name}"
    return f"resolved on {backend_name}"


def _unresolved_resolution_note(
    *,
    requested_profile_id: str,
    attempted_profile_ids: tuple[str, ...],
    backend_name: str,
) -> str:
    if attempted_profile_ids:
        attempted = ", ".join(attempted_profile_ids)
        return f"unresolved after trying profiles: {attempted} on {backend_name}"
    if requested_profile_id:
        return f"unresolved for requested profile {requested_profile_id} on {backend_name}"
    return f"unresolved on {backend_name}"
