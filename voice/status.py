"""Session-aware status helpers for the current CLI voice path."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from voice.flags import build_voice_mode_status
from voice.telemetry import VoiceTelemetrySnapshot
from voice.tts_operator_hints import native_tts_doctor_guidance
from voice.tts_models import BackendCapabilities, BackendRuntimeStatus, VoiceDescriptor, VoiceResolutionTrace
from voice.voice_profiles import (
    VOICE_PROFILE_EN_ASSISTANT_ANY,
    VOICE_PROFILE_EN_ASSISTANT_FEMALE,
    VOICE_PROFILE_EN_ASSISTANT_MALE,
    VOICE_PROFILE_RU_ASSISTANT_ANY,
    VOICE_PROFILE_RU_ASSISTANT_FEMALE,
    VOICE_PROFILE_RU_ASSISTANT_MALE,
)


@dataclass(frozen=True, slots=True)
class VoiceSessionStatus:
    """Compact operator-facing view of the current CLI voice session."""

    speak_enabled: bool
    continuous_mode_enabled: bool
    advanced_follow_up_default_off: bool
    max_auto_follow_up_turns: int
    short_answer_follow_up_requires_speech: bool
    telemetry_capture_attempts: int
    telemetry_dispatch_count: int
    telemetry_tts_attempts: int
    telemetry_max_follow_up_chain_length: int
    telemetry_follow_up_limit_hit_count: int
    telemetry_follow_up_relisten_count: int
    telemetry_follow_up_dismiss_count: int
    telemetry_speech_interrupt_count: int
    telemetry_speech_interrupt_for_capture_count: int
    telemetry_speech_interrupt_for_response_count: int
    telemetry_speech_interrupt_conflict_count: int


@dataclass(frozen=True, slots=True)
class TTSBackendStatus:
    """Compact operator-facing summary of the current TTS backend."""

    backend_name: str
    available: bool
    supports_stop: bool
    supports_voice_listing: bool
    supports_voice_resolution: bool
    supports_explicit_voice_id: bool
    supports_rate: bool
    supports_pitch: bool
    supports_volume: bool
    is_fallback: bool
    selection_note: str | None = None
    configuration_notes: tuple[str, ...] = ()
    diagnostics: tuple[BackendRuntimeStatus, ...] = ()
    guidance: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TTSVoiceInventory:
    """Visible TTS voices for the current backend."""

    backend_name: str
    available: bool
    locale_hint: str | None
    voices: tuple[VoiceDescriptor, ...]


@dataclass(frozen=True, slots=True)
class TTSCurrentVoiceResolution:
    """Resolved backend-native voice for one product-level profile."""

    profile_id: str
    locale: str
    resolved_voice: VoiceDescriptor | None = None
    resolved_profile_id: str | None = None
    backend_name: str | None = None
    attempted_profile_ids: tuple[str, ...] = ()
    resolution_note: str | None = None


@dataclass(frozen=True, slots=True)
class TTSCurrentStatus:
    """Current product-level TTS profile resolution summary."""

    backend_name: str
    available: bool
    resolutions: tuple[TTSCurrentVoiceResolution, ...]
    selection_note: str | None = None


@dataclass(frozen=True, slots=True)
class TTSDoctorStatus:
    """Aggregated operator-facing doctor summary for TTS backend debugging."""

    backend_status: TTSBackendStatus
    current_status: TTSCurrentStatus
    voice_inventory: TTSVoiceInventory
    guidance: tuple[str, ...] = ()


_DEFAULT_TTS_PROFILE_REQUESTS = (
    (VOICE_PROFILE_RU_ASSISTANT_MALE, "ru-RU"),
    (VOICE_PROFILE_RU_ASSISTANT_FEMALE, "ru-RU"),
    (VOICE_PROFILE_RU_ASSISTANT_ANY, "ru-RU"),
    (VOICE_PROFILE_EN_ASSISTANT_MALE, "en-US"),
    (VOICE_PROFILE_EN_ASSISTANT_FEMALE, "en-US"),
    (VOICE_PROFILE_EN_ASSISTANT_ANY, "en-US"),
)
_DOCTOR_VOICE_PREVIEW_LIMIT = 8


def build_voice_session_status(
    *,
    speak_enabled: bool,
    telemetry_snapshot: VoiceTelemetrySnapshot | None,
    environ: Mapping[str, str] | None = None,
) -> VoiceSessionStatus:
    """Build one current-session voice status summary for CLI helpers."""
    mode_status = build_voice_mode_status(environ=environ)
    snapshot = telemetry_snapshot or _empty_telemetry_snapshot()
    return VoiceSessionStatus(
        speak_enabled=bool(speak_enabled),
        continuous_mode_enabled=mode_status.continuous_mode_enabled,
        advanced_follow_up_default_off=mode_status.advanced_follow_up_default_off,
        max_auto_follow_up_turns=mode_status.max_auto_follow_up_turns,
        short_answer_follow_up_requires_speech=mode_status.short_answer_follow_up_requires_speech,
        telemetry_capture_attempts=snapshot.capture_attempts,
        telemetry_dispatch_count=snapshot.dispatch_count,
        telemetry_tts_attempts=snapshot.tts_attempts,
        telemetry_max_follow_up_chain_length=snapshot.max_follow_up_chain_length,
        telemetry_follow_up_limit_hit_count=snapshot.follow_up_limit_hit_count,
        telemetry_follow_up_relisten_count=snapshot.follow_up_relisten_count,
        telemetry_follow_up_dismiss_count=snapshot.follow_up_dismiss_count,
        telemetry_speech_interrupt_count=snapshot.speech_interrupt_count,
        telemetry_speech_interrupt_for_capture_count=snapshot.speech_interrupt_for_capture_count,
        telemetry_speech_interrupt_for_response_count=snapshot.speech_interrupt_for_response_count,
        telemetry_speech_interrupt_conflict_count=snapshot.speech_interrupt_conflict_count,
    )


def format_voice_session_status(status: VoiceSessionStatus) -> str:
    """Render one current-session voice status summary for operators."""
    return "\n".join(
        [
            "JARVIS Voice Status",
            f"speech output enabled: {'yes' if status.speak_enabled else 'no'}",
            f"continuous mode enabled: {'yes' if status.continuous_mode_enabled else 'no'}",
            f"advanced follow-up default off: {'yes' if status.advanced_follow_up_default_off else 'no'}",
            f"max auto follow-up turns: {status.max_auto_follow_up_turns}",
            f"short-answer follow-up requires speech: {'yes' if status.short_answer_follow_up_requires_speech else 'no'}",
            f"telemetry capture attempts: {status.telemetry_capture_attempts}",
            f"telemetry dispatch count: {status.telemetry_dispatch_count}",
            f"telemetry tts attempts: {status.telemetry_tts_attempts}",
            f"telemetry max follow-up chain length: {status.telemetry_max_follow_up_chain_length}",
            f"telemetry follow-up limit hit count: {status.telemetry_follow_up_limit_hit_count}",
            f"telemetry follow-up relisten count: {status.telemetry_follow_up_relisten_count}",
            f"telemetry follow-up dismiss count: {status.telemetry_follow_up_dismiss_count}",
            f"telemetry speech interrupt count: {status.telemetry_speech_interrupt_count}",
            f"telemetry speech interrupt for capture count: {status.telemetry_speech_interrupt_for_capture_count}",
            f"telemetry speech interrupt for response count: {status.telemetry_speech_interrupt_for_response_count}",
            f"telemetry speech interrupt conflict count: {status.telemetry_speech_interrupt_conflict_count}",
        ]
    )


def build_tts_backend_status(tts_provider: object | None) -> TTSBackendStatus:
    """Build one operator-facing summary for the active TTS backend."""
    capabilities = _backend_capabilities(tts_provider)
    diagnostics = _backend_diagnostics(tts_provider)
    return TTSBackendStatus(
        backend_name=capabilities.backend_name,
        available=_backend_is_available(tts_provider),
        supports_stop=capabilities.supports_stop,
        supports_voice_listing=capabilities.supports_voice_listing,
        supports_voice_resolution=capabilities.supports_voice_resolution,
        supports_explicit_voice_id=capabilities.supports_explicit_voice_id,
        supports_rate=capabilities.supports_rate,
        supports_pitch=capabilities.supports_pitch,
        supports_volume=capabilities.supports_volume,
        is_fallback=capabilities.is_fallback,
        selection_note=_selection_note_from_diagnostics(diagnostics),
        configuration_notes=_backend_configuration_notes(tts_provider),
        diagnostics=diagnostics,
        guidance=_backend_guidance(diagnostics),
    )


def format_tts_backend_status(status: TTSBackendStatus) -> str:
    """Render one compact backend capability summary for operators."""
    lines = [
        "JARVIS TTS Backend",
        f"backend: {status.backend_name}",
        f"available: {'yes' if status.available else 'no'}",
        f"fallback backend: {'yes' if status.is_fallback else 'no'}",
        f"supports stop: {'yes' if status.supports_stop else 'no'}",
        f"supports voice listing: {'yes' if status.supports_voice_listing else 'no'}",
        f"supports voice resolution: {'yes' if status.supports_voice_resolution else 'no'}",
        f"supports explicit voice id: {'yes' if status.supports_explicit_voice_id else 'no'}",
        f"supports rate: {'yes' if status.supports_rate else 'no'}",
        f"supports pitch: {'yes' if status.supports_pitch else 'no'}",
        f"supports volume: {'yes' if status.supports_volume else 'no'}",
    ]
    if status.selection_note:
        lines.append(f"selection note: {status.selection_note}")
    if status.configuration_notes:
        lines.append("configuration:")
        lines.extend(f"- {note}" for note in status.configuration_notes)
    if status.diagnostics:
        lines.append("configured backends:")
        for diagnostic in status.diagnostics:
            lines.append(f"- {_format_backend_runtime_status(diagnostic)}")
            lines.extend(f"  detail: {detail}" for detail in diagnostic.detail_lines)
    if status.guidance:
        lines.append("guidance:")
        lines.extend(f"- {hint}" for hint in status.guidance)
    return "\n".join(lines)


def build_tts_voice_inventory(
    tts_provider: object | None,
    *,
    locale_hint: str | None = None,
) -> TTSVoiceInventory:
    """Build one visible-voice inventory for the active TTS backend."""
    capabilities = _backend_capabilities(tts_provider)
    return TTSVoiceInventory(
        backend_name=capabilities.backend_name,
        available=_backend_is_available(tts_provider),
        locale_hint=str(locale_hint or "").strip() or None,
        voices=tuple(_list_backend_voices(tts_provider, locale_hint=locale_hint)),
    )


def format_tts_voice_inventory(inventory: TTSVoiceInventory) -> str:
    """Render one operator-facing visible-voices summary."""
    lines = [
        "JARVIS TTS Voices",
        f"backend: {inventory.backend_name}",
        f"available: {'yes' if inventory.available else 'no'}",
        f"locale hint: {inventory.locale_hint or 'none'}",
        f"visible voice count: {len(inventory.voices)}",
    ]
    if not inventory.voices:
        lines.append("no voices visible to this backend.")
        return "\n".join(lines)
    lines.extend(f"- {_format_voice_descriptor(voice)}" for voice in inventory.voices)
    return "\n".join(lines)


def build_tts_current_status(tts_provider: object | None) -> TTSCurrentStatus:
    """Build one current product-level profile resolution summary."""
    capabilities = _backend_capabilities(tts_provider)
    diagnostics = _backend_diagnostics(tts_provider)
    resolutions = tuple(
        _build_tts_current_voice_resolution(
            tts_provider,
            profile_id=profile_id,
            locale=locale,
        )
        for profile_id, locale in _DEFAULT_TTS_PROFILE_REQUESTS
    )
    return TTSCurrentStatus(
        backend_name=capabilities.backend_name,
        available=_backend_is_available(tts_provider),
        selection_note=_selection_note_from_diagnostics(diagnostics),
        resolutions=resolutions,
    )


def format_tts_current_status(status: TTSCurrentStatus) -> str:
    """Render one operator-facing summary of current profile resolution."""
    lines = [
        "JARVIS TTS Current",
        f"backend: {status.backend_name}",
        f"available: {'yes' if status.available else 'no'}",
    ]
    if status.selection_note:
        lines.append(f"selection note: {status.selection_note}")
    for resolution in status.resolutions:
        lines.append(
            _format_current_voice_resolution_line(
                resolution,
                include_voice_metadata=True,
            )
        )
    return "\n".join(lines)


def build_tts_doctor_status(
    tts_provider: object | None,
    *,
    locale_hint: str | None = None,
) -> TTSDoctorStatus:
    """Build one aggregated TTS doctor summary for operator debugging."""
    backend_status = build_tts_backend_status(tts_provider)
    current_status = build_tts_current_status(tts_provider)
    voice_inventory = build_tts_voice_inventory(tts_provider, locale_hint=locale_hint)
    return TTSDoctorStatus(
        backend_status=backend_status,
        current_status=current_status,
        voice_inventory=voice_inventory,
        guidance=_doctor_guidance(
            backend_status=backend_status,
            current_status=current_status,
            voice_inventory=voice_inventory,
        ),
    )


def format_tts_doctor_status(status: TTSDoctorStatus) -> str:
    """Render one compact TTS doctor summary with next-step hints."""
    lines = [
        "JARVIS TTS Doctor",
        f"active backend: {status.backend_status.backend_name}",
        f"backend available: {'yes' if status.backend_status.available else 'no'}",
        f"visible voice count: {len(status.voice_inventory.voices)}",
    ]
    if status.backend_status.selection_note:
        lines.append(f"selection note: {status.backend_status.selection_note}")
    if status.backend_status.configuration_notes:
        lines.append("configuration:")
        lines.extend(f"- {note}" for note in status.backend_status.configuration_notes)
    lines.append("configured backends:")
    if status.backend_status.diagnostics:
        for diagnostic in status.backend_status.diagnostics:
            lines.append(f"- {_format_backend_runtime_status(diagnostic)}")
            lines.extend(f"  detail: {detail}" for detail in diagnostic.detail_lines)
    else:
        lines.append("- none")

    lines.append("profile resolution:")
    for resolution in status.current_status.resolutions:
        lines.append(
            f"- {_format_current_voice_resolution_line(resolution, include_voice_metadata=False)}"
        )

    lines.append("voice preview:")
    preview = status.voice_inventory.voices[:_DOCTOR_VOICE_PREVIEW_LIMIT]
    if preview:
        lines.extend(f"- {_format_voice_descriptor(voice)}" for voice in preview)
        remaining = len(status.voice_inventory.voices) - len(preview)
        if remaining > 0:
            lines.append(f"- + {remaining} more visible voice(s); run `voice tts voices` for the full list.")
    else:
        lines.append("- no voices visible to the active backend.")

    if status.guidance:
        lines.append("guidance:")
        lines.extend(f"- {hint}" for hint in status.guidance)
    return "\n".join(lines)


def _empty_telemetry_snapshot() -> VoiceTelemetrySnapshot:
    return VoiceTelemetrySnapshot(
        capture_attempts=0,
        dispatch_count=0,
        tts_attempts=0,
        recognition_latency_ms=None,
        empty_recognition_rate=0.0,
        clarification_rate=0.0,
        confirmation_completion_rate=0.0,
        retry_rate=0.0,
        tts_failure_rate=0.0,
        average_spoken_response_length=0.0,
        follow_up_relisten_count=0,
        follow_up_dismiss_count=0,
        max_follow_up_chain_length=0,
        follow_up_limit_hit_count=0,
        speech_interrupt_count=0,
        speech_interrupt_for_capture_count=0,
        speech_interrupt_for_response_count=0,
        speech_interrupt_conflict_count=0,
    )


def _backend_capabilities(tts_provider: object | None) -> BackendCapabilities:
    method = getattr(tts_provider, "capabilities", None)
    if not callable(method):
        return BackendCapabilities(backend_name="unavailable", is_fallback=True)
    try:
        return _coerce_backend_capabilities(method())
    except Exception:
        return BackendCapabilities(backend_name="unavailable", is_fallback=True)


def _backend_diagnostics(tts_provider: object | None) -> tuple[BackendRuntimeStatus, ...]:
    method = getattr(tts_provider, "backend_diagnostics", None)
    if callable(method):
        try:
            diagnostics = tuple(
                diagnostic
                for diagnostic in (_coerce_backend_runtime_status(item) for item in method() or ())
                if diagnostic is not None
            )
        except Exception:
            diagnostics = ()
        if diagnostics:
            return diagnostics

    capabilities = _backend_capabilities(tts_provider)
    if tts_provider is None and capabilities.backend_name == "unavailable":
        return ()
    available = _backend_is_available(tts_provider)
    return (
        BackendRuntimeStatus(
            backend_name=capabilities.backend_name,
            available=available,
            selected=available,
            capabilities=capabilities,
        ),
    )


def _backend_configuration_notes(tts_provider: object | None) -> tuple[str, ...]:
    method = getattr(tts_provider, "configuration_notes", None)
    if not callable(method):
        return ()
    try:
        return tuple(
            note
            for note in (str(item or "").strip() for item in tuple(method() or ()))
            if note
        )
    except Exception:
        return ()


def _backend_is_available(tts_provider: object | None) -> bool:
    method = getattr(tts_provider, "is_available", None)
    if not callable(method):
        return False
    try:
        return bool(method())
    except Exception:
        return False


def _list_backend_voices(
    tts_provider: object | None,
    *,
    locale_hint: str | None = None,
) -> list[VoiceDescriptor]:
    method = getattr(tts_provider, "list_voices", None)
    if not callable(method):
        return []
    try:
        raw_voices = method(locale_hint=locale_hint)
    except Exception:
        return []
    voices = [voice for voice in (_coerce_voice_descriptor(item) for item in raw_voices or ()) if voice is not None]
    return sorted(
        voices,
        key=lambda voice: (
            str(voice.locale or ""),
            str(voice.display_name or voice.id).lower(),
            voice.id.lower(),
        ),
    )


def _resolve_backend_voice(
    tts_provider: object | None,
    profile_id: str,
    locale: str,
) -> VoiceDescriptor | None:
    method = getattr(tts_provider, "resolve_voice", None)
    if not callable(method):
        return None
    try:
        return _coerce_voice_descriptor(method(profile_id, locale))
    except Exception:
        return None


def _resolve_backend_voice_trace(
    tts_provider: object | None,
    profile_id: str,
    locale: str,
) -> VoiceResolutionTrace | None:
    method = getattr(tts_provider, "resolve_voice_trace", None)
    if not callable(method):
        return None
    try:
        raw_trace = method(profile_id, locale)
    except Exception:
        return None
    return _coerce_voice_resolution_trace(raw_trace)


def _build_tts_current_voice_resolution(
    tts_provider: object | None,
    *,
    profile_id: str,
    locale: str,
) -> TTSCurrentVoiceResolution:
    trace = _resolve_backend_voice_trace(tts_provider, profile_id, locale)
    if trace is not None:
        return TTSCurrentVoiceResolution(
            profile_id=profile_id,
            locale=locale,
            resolved_voice=trace.resolved_voice,
            resolved_profile_id=trace.resolved_profile_id,
            backend_name=trace.backend_name,
            attempted_profile_ids=trace.attempted_profile_ids,
            resolution_note=trace.note,
        )
    return TTSCurrentVoiceResolution(
        profile_id=profile_id,
        locale=locale,
        resolved_voice=_resolve_backend_voice(tts_provider, profile_id, locale),
    )


def _coerce_backend_capabilities(raw_value: object | None) -> BackendCapabilities:
    if isinstance(raw_value, BackendCapabilities):
        return raw_value
    return BackendCapabilities(
        backend_name=str(getattr(raw_value, "backend_name", "") or "unavailable"),
        supports_stop=bool(getattr(raw_value, "supports_stop", False)),
        supports_voice_listing=bool(getattr(raw_value, "supports_voice_listing", False)),
        supports_voice_resolution=bool(getattr(raw_value, "supports_voice_resolution", False)),
        supports_explicit_voice_id=bool(getattr(raw_value, "supports_explicit_voice_id", False)),
        supports_rate=bool(getattr(raw_value, "supports_rate", False)),
        supports_pitch=bool(getattr(raw_value, "supports_pitch", False)),
        supports_volume=bool(getattr(raw_value, "supports_volume", False)),
        is_fallback=bool(getattr(raw_value, "is_fallback", False)),
    )


def _coerce_backend_runtime_status(raw_value: object | None) -> BackendRuntimeStatus | None:
    if isinstance(raw_value, BackendRuntimeStatus):
        return raw_value
    backend_name = str(getattr(raw_value, "backend_name", "") or "").strip()
    if not backend_name:
        return None
    raw_capabilities = getattr(raw_value, "capabilities", None)
    return BackendRuntimeStatus(
        backend_name=backend_name,
        available=bool(getattr(raw_value, "available", False)),
        selected=bool(getattr(raw_value, "selected", False)),
        error_code=str(getattr(raw_value, "error_code", "") or "").strip() or None,
        error_message=str(getattr(raw_value, "error_message", "") or "").strip() or None,
        detail_lines=tuple(
            line
            for line in (
                str(item or "").strip()
                for item in tuple(getattr(raw_value, "detail_lines", ()) or ())
            )
            if line
        ),
        capabilities=_coerce_backend_capabilities(raw_capabilities) if raw_capabilities is not None else None,
    )


def _coerce_voice_resolution_trace(raw_value: object | None) -> VoiceResolutionTrace | None:
    if isinstance(raw_value, VoiceResolutionTrace):
        return raw_value
    requested_profile_id = str(getattr(raw_value, "requested_profile_id", "") or "").strip()
    if not requested_profile_id:
        return None
    attempted_profiles = tuple(
        str(item or "").strip()
        for item in tuple(getattr(raw_value, "attempted_profile_ids", ()) or ())
        if str(item or "").strip()
    )
    return VoiceResolutionTrace(
        requested_profile_id=requested_profile_id,
        locale=str(getattr(raw_value, "locale", "") or "").strip() or None,
        attempted_profile_ids=attempted_profiles,
        resolved_profile_id=str(getattr(raw_value, "resolved_profile_id", "") or "").strip() or None,
        backend_name=str(getattr(raw_value, "backend_name", "") or "").strip() or None,
        resolved_voice=_coerce_voice_descriptor(getattr(raw_value, "resolved_voice", None)),
        note=str(getattr(raw_value, "note", "") or "").strip() or None,
    )


def _coerce_voice_descriptor(raw_value: object | None) -> VoiceDescriptor | None:
    if isinstance(raw_value, VoiceDescriptor):
        return raw_value
    voice_id = str(getattr(raw_value, "id", "") or "").strip()
    if not voice_id:
        return None
    display_name = str(getattr(raw_value, "display_name", "") or voice_id).strip() or voice_id
    return VoiceDescriptor(
        id=voice_id,
        display_name=display_name,
        locale=str(getattr(raw_value, "locale", "") or "").strip() or None,
        gender_hint=str(getattr(raw_value, "gender_hint", "") or "").strip() or None,
        quality_hint=str(getattr(raw_value, "quality_hint", "") or "").strip() or None,
        source=str(getattr(raw_value, "source", "") or "").strip() or None,
        is_default=bool(getattr(raw_value, "is_default", False)),
    )


def _format_voice_descriptor(voice: VoiceDescriptor) -> str:
    parts = [voice.display_name or voice.id]
    metadata: list[str] = []
    if voice.display_name != voice.id:
        metadata.append(f"id={voice.id}")
    if voice.locale:
        metadata.append(f"locale={voice.locale}")
    if voice.gender_hint:
        metadata.append(f"gender={voice.gender_hint}")
    if voice.quality_hint:
        metadata.append(f"quality={voice.quality_hint}")
    if voice.source:
        metadata.append(f"source={voice.source}")
    if voice.is_default:
        metadata.append("default=yes")
    if not metadata:
        return parts[0]
    return f"{parts[0]} ({', '.join(metadata)})"


def _format_backend_runtime_status(status: BackendRuntimeStatus) -> str:
    state = "selected" if status.selected else ("available" if status.available else "unavailable")
    detail = status.error_message
    if detail and status.error_code:
        return f"{status.backend_name}: {state} ({status.error_code}: {detail})"
    if detail:
        return f"{status.backend_name}: {state} ({detail})"
    return f"{status.backend_name}: {state}"


def _selection_note_from_diagnostics(diagnostics: tuple[BackendRuntimeStatus, ...]) -> str | None:
    if not diagnostics:
        return None
    selected_index = next((index for index, diagnostic in enumerate(diagnostics) if diagnostic.selected), None)
    if selected_index is None:
        return "no configured backend is currently available."
    prior_unavailable = [diagnostic for diagnostic in diagnostics[:selected_index] if not diagnostic.available]
    if not prior_unavailable:
        return None
    first_unavailable = prior_unavailable[0]
    detail = first_unavailable.error_message or "reported unavailable"
    return (
        f"fallback active: using {diagnostics[selected_index].backend_name} "
        f"because {first_unavailable.backend_name} is unavailable ({detail})."
    )


def _format_current_voice_resolution_line(
    resolution: TTSCurrentVoiceResolution,
    *,
    include_voice_metadata: bool,
) -> str:
    voice = resolution.resolved_voice
    if voice is None:
        line = f"{resolution.profile_id} ({resolution.locale}): unresolved"
    else:
        formatted_voice = _format_voice_descriptor(voice) if include_voice_metadata else (voice.display_name or voice.id)
        line = f"{resolution.profile_id} ({resolution.locale}): {formatted_voice}"
    trace_details = _resolution_trace_details(resolution)
    if not trace_details:
        return line
    return f"{line} [{'; '.join(trace_details)}]"


def _resolution_trace_details(resolution: TTSCurrentVoiceResolution) -> list[str]:
    details: list[str] = []
    if resolution.attempted_profile_ids:
        details.append(f"profiles: {' -> '.join(resolution.attempted_profile_ids)}")
    if resolution.resolved_profile_id:
        label = "resolved profile"
        if resolution.resolved_profile_id != resolution.profile_id:
            label = "fallback profile"
        details.append(f"{label}: {resolution.resolved_profile_id}")
    if resolution.backend_name:
        details.append(f"backend: {resolution.backend_name}")
    if resolution.resolution_note and (resolution.resolved_voice is None or not details):
        details.append(resolution.resolution_note)
    return details


def _doctor_guidance(
    *,
    backend_status: TTSBackendStatus,
    current_status: TTSCurrentStatus,
    voice_inventory: TTSVoiceInventory,
) -> tuple[str, ...]:
    hints = list(backend_status.guidance)

    if not backend_status.available:
        hints.append("no TTS backend is currently available in this runtime.")

    if backend_status.selection_note:
        hints.append("fallback is active; use `voice tts backend` to confirm why the preferred backend was skipped.")

    unresolved_count = sum(1 for resolution in current_status.resolutions if resolution.resolved_voice is None)
    if unresolved_count > 0:
        hints.append(
            "some product profiles are unresolved; compare `voice tts current` with `voice tts voices` before manual smoke."
        )

    if backend_status.available and not voice_inventory.voices:
        hints.append("the active backend reports available but returned no visible voices.")

    return tuple(_dedupe_preserving_order(hints))


def _backend_guidance(diagnostics: tuple[BackendRuntimeStatus, ...]) -> tuple[str, ...]:
    hints: list[str] = []
    for diagnostic in diagnostics:
        if diagnostic.backend_name != "macos_native" or diagnostic.available:
            continue
        hints.extend(native_tts_doctor_guidance(diagnostic.error_code, detail_lines=diagnostic.detail_lines))
    return tuple(_dedupe_preserving_order(hints))


def _dedupe_preserving_order(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        candidate = str(item or "").strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        result.append(candidate)
    return result
