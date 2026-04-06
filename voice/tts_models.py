"""Backend-neutral TTS metadata models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VoiceDescriptor:
    """One native voice exposed by a backend."""

    id: str
    display_name: str
    locale: str | None = None
    gender_hint: str | None = None
    quality_hint: str | None = None
    source: str | None = None
    is_default: bool = False


@dataclass(frozen=True, slots=True)
class BackendCapabilities:
    """Structured backend capability flags for debug and selection."""

    backend_name: str
    supports_stop: bool = False
    supports_voice_listing: bool = False
    supports_voice_resolution: bool = False
    supports_explicit_voice_id: bool = False
    supports_rate: bool = False
    supports_pitch: bool = False
    supports_volume: bool = False
    is_fallback: bool = False


@dataclass(frozen=True, slots=True)
class BackendRuntimeStatus:
    """Runtime availability and selection state for one backend candidate."""

    backend_name: str
    available: bool
    selected: bool = False
    error_code: str | None = None
    error_message: str | None = None
    detail_lines: tuple[str, ...] = ()
    capabilities: BackendCapabilities | None = None


@dataclass(frozen=True, slots=True)
class VoiceResolutionTrace:
    """Structured explanation of how one product voice profile was resolved."""

    requested_profile_id: str
    locale: str | None = None
    attempted_profile_ids: tuple[str, ...] = ()
    resolved_profile_id: str | None = None
    backend_name: str | None = None
    resolved_voice: VoiceDescriptor | None = None
    note: str | None = None
