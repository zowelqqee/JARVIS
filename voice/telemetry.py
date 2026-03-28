"""In-memory telemetry helpers for the current CLI voice path."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from input.voice_input import VoiceInputError
from voice.tts_provider import SpeechUtterance, TTSResult

_REPO_ROOT = Path(__file__).resolve().parents[1]
_VOICE_TELEMETRY_ARTIFACT = _REPO_ROOT / "tmp" / "qa" / "voice_telemetry.json"


@dataclass(frozen=True, slots=True)
class VoiceTelemetryEvent:
    """One normalized telemetry event emitted by the voice layer."""

    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class VoiceTelemetrySnapshot:
    """Derived metrics over the currently recorded voice events."""

    capture_attempts: int
    dispatch_count: int
    tts_attempts: int
    recognition_latency_ms: float | None
    empty_recognition_rate: float
    clarification_rate: float
    confirmation_completion_rate: float
    retry_rate: float
    tts_failure_rate: float
    average_spoken_response_length: float

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable snapshot representation."""
        return {
            "capture_attempts": self.capture_attempts,
            "dispatch_count": self.dispatch_count,
            "tts_attempts": self.tts_attempts,
            "recognition_latency_ms": self.recognition_latency_ms,
            "empty_recognition_rate": self.empty_recognition_rate,
            "clarification_rate": self.clarification_rate,
            "confirmation_completion_rate": self.confirmation_completion_rate,
            "retry_rate": self.retry_rate,
            "tts_failure_rate": self.tts_failure_rate,
            "average_spoken_response_length": self.average_spoken_response_length,
        }


class VoiceTelemetryCollector:
    """Collect minimal voice-path events and derive rollout-friendly metrics."""

    def __init__(self) -> None:
        self._events: list[VoiceTelemetryEvent] = []

    @property
    def events(self) -> tuple[VoiceTelemetryEvent, ...]:
        """Expose recorded events as an immutable sequence for tests/debugging."""
        return tuple(self._events)

    def clear(self) -> None:
        """Drop the currently accumulated in-memory telemetry events."""
        self._events.clear()

    def record_capture(
        self,
        *,
        phase: str,
        elapsed_seconds: float,
        voice_turn: object | None = None,
        error: VoiceInputError | None = None,
    ) -> None:
        """Record one capture attempt outcome."""
        normalized_text = _normalized_text(voice_turn)
        error_code = str(getattr(error, "code", "") or "").strip() or None
        self._events.append(
            VoiceTelemetryEvent(
                event_type="capture",
                payload={
                    "phase": str(phase or "initial"),
                    "latency_ms": max(0.0, float(elapsed_seconds)) * 1000.0,
                    "success": error is None,
                    "empty_recognition": not normalized_text if error is None else error_code == "EMPTY_RECOGNITION",
                    "retryable": bool(getattr(voice_turn, "retryable", True)) if error is None else _retryable_error(error),
                    "error_code": error_code,
                    "locale": _voice_locale(voice_turn),
                    "recognized_chars": len(normalized_text),
                },
            )
        )

    def record_dispatch(self, voice_turn: object, dispatch_result: object) -> None:
        """Record one downstream routing result for a prepared voice turn."""
        interaction = getattr(dispatch_result, "interaction", dispatch_result)
        self._events.append(
            VoiceTelemetryEvent(
                event_type="dispatch",
                payload={
                    "interaction_mode": _interaction_mode(interaction),
                    "follow_up_reason": str(getattr(interaction, "follow_up_reason", "") or "").strip() or None,
                    "locale": _voice_locale(getattr(dispatch_result, "voice_turn", voice_turn)),
                    "lifecycle_state": str(getattr(getattr(dispatch_result, "voice_turn", voice_turn), "lifecycle_state", "") or "").strip() or None,
                },
            )
        )

    def record_follow_up_opened(self, voice_turn: object) -> None:
        """Record that the CLI opened one immediate follow-up capture window."""
        self._events.append(
            VoiceTelemetryEvent(
                event_type="follow_up_opened",
                payload={
                    "reason": str(getattr(voice_turn, "follow_up_reason", "") or "").strip() or None,
                    "locale": _voice_locale(voice_turn),
                },
            )
        )

    def record_follow_up_completed(self, prior_turn: object, follow_up_turn: object) -> None:
        """Record that one blocking follow-up reply was captured successfully."""
        self._events.append(
            VoiceTelemetryEvent(
                event_type="follow_up_completed",
                payload={
                    "reason": str(getattr(prior_turn, "follow_up_reason", "") or "").strip() or None,
                    "locale": _voice_locale(follow_up_turn),
                    "recognized_chars": len(_normalized_text(follow_up_turn)),
                },
            )
        )

    def record_tts_result(self, utterance: SpeechUtterance, result: TTSResult) -> None:
        """Record one spoken-output attempt outcome."""
        spoken_text = str(getattr(utterance, "text", "") or "").strip()
        self._events.append(
            VoiceTelemetryEvent(
                event_type="tts",
                payload={
                    "attempted": bool(getattr(result, "attempted", True)),
                    "ok": bool(getattr(result, "ok", False)),
                    "locale": str(getattr(utterance, "locale", "") or "").strip() or None,
                    "utterance_chars": len(spoken_text),
                    "error_code": str(getattr(result, "error_code", "") or "").strip() or None,
                },
            )
        )

    def snapshot(self) -> VoiceTelemetrySnapshot:
        """Return the current derived voice metrics."""
        capture_events = [event.payload for event in self._events if event.event_type == "capture"]
        dispatch_events = [event.payload for event in self._events if event.event_type == "dispatch"]
        follow_up_completed = [event.payload for event in self._events if event.event_type == "follow_up_completed"]
        tts_events = [event.payload for event in self._events if event.event_type == "tts"]
        attempted_tts_events = [payload for payload in tts_events if bool(payload.get("attempted", False))]
        confirmation_requests = [
            payload for payload in dispatch_events if payload.get("follow_up_reason") == "confirmation"
        ]
        clarification_dispatches = [
            payload
            for payload in dispatch_events
            if payload.get("interaction_mode") == "clarification" or payload.get("follow_up_reason") == "clarification"
        ]
        retryable_failures = [
            payload for payload in capture_events if not bool(payload.get("success", False)) and bool(payload.get("retryable", False))
        ]
        tts_failures = [
            payload for payload in attempted_tts_events if not bool(payload.get("ok", False))
        ]
        spoken_lengths = [
            int(payload.get("utterance_chars", 0) or 0) for payload in attempted_tts_events
        ]
        latency_values = [
            float(payload.get("latency_ms", 0.0) or 0.0) for payload in capture_events
        ]
        confirmation_completions = [
            payload for payload in follow_up_completed if payload.get("reason") == "confirmation"
        ]
        empty_captures = [
            payload for payload in capture_events if bool(payload.get("empty_recognition", False))
        ]

        return VoiceTelemetrySnapshot(
            capture_attempts=len(capture_events),
            dispatch_count=len(dispatch_events),
            tts_attempts=len(attempted_tts_events),
            recognition_latency_ms=_average(latency_values),
            empty_recognition_rate=_rate(len(empty_captures), len(capture_events)),
            clarification_rate=_rate(len(clarification_dispatches), len(dispatch_events)),
            confirmation_completion_rate=_rate(len(confirmation_completions), len(confirmation_requests)),
            retry_rate=_rate(len(retryable_failures), len(capture_events)),
            tts_failure_rate=_rate(len(tts_failures), len(attempted_tts_events)),
            average_spoken_response_length=_average(spoken_lengths) or 0.0,
        )


def build_default_voice_telemetry() -> VoiceTelemetryCollector:
    """Build the default in-memory telemetry collector for local CLI use."""
    return VoiceTelemetryCollector()


def voice_telemetry_artifact_path() -> Path:
    """Return the default artifact path for voice telemetry snapshots."""
    return _VOICE_TELEMETRY_ARTIFACT


def voice_telemetry_snapshot_payload(snapshot: VoiceTelemetrySnapshot) -> dict[str, Any]:
    """Return the machine-readable voice telemetry artifact payload."""
    return {
        "schema_version": 1,
        "runner": "voice.telemetry",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "snapshot": snapshot.to_dict(),
    }


def write_voice_telemetry_artifact(
    snapshot: VoiceTelemetrySnapshot,
    *,
    artifact_path: Path | None = None,
) -> Path:
    """Persist one voice telemetry snapshot to tmp/qa."""
    resolved_artifact_path = artifact_path or voice_telemetry_artifact_path()
    resolved_artifact_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_artifact_path.write_text(
        json.dumps(voice_telemetry_snapshot_payload(snapshot), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return resolved_artifact_path


def load_voice_telemetry_artifact(
    artifact_path: Path | None = None,
) -> tuple[Path, dict[str, Any] | None, str | None]:
    """Load the current voice telemetry artifact plus any parse error."""
    resolved_artifact_path = artifact_path or voice_telemetry_artifact_path()
    if not resolved_artifact_path.exists():
        return resolved_artifact_path, None, None
    try:
        payload = json.loads(resolved_artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return resolved_artifact_path, None, f"{type(exc).__name__}: {exc}"
    if not isinstance(payload, dict):
        return resolved_artifact_path, None, "ValueError: voice telemetry artifact must be a JSON object."
    return resolved_artifact_path, payload, None


def format_voice_telemetry_snapshot(snapshot: VoiceTelemetrySnapshot) -> str:
    """Render one compact operator-facing voice telemetry summary."""
    return "\n".join(
        [
            "JARVIS Voice Telemetry",
            f"capture attempts: {snapshot.capture_attempts}",
            f"dispatch count: {snapshot.dispatch_count}",
            f"tts attempts: {snapshot.tts_attempts}",
            f"recognition latency ms: {_metric_value(snapshot.recognition_latency_ms)}",
            f"empty recognition rate: {_percent(snapshot.empty_recognition_rate)}",
            f"clarification rate: {_percent(snapshot.clarification_rate)}",
            f"confirmation completion rate: {_percent(snapshot.confirmation_completion_rate)}",
            f"retry rate: {_percent(snapshot.retry_rate)}",
            f"tts failure rate: {_percent(snapshot.tts_failure_rate)}",
            f"average spoken response length: {_metric_value(snapshot.average_spoken_response_length)}",
        ]
    )


def _interaction_mode(interaction: object) -> str | None:
    interaction_result = getattr(interaction, "interaction_result", interaction)
    mode = getattr(interaction_result, "interaction_mode", None)
    if mode is None:
        mode = getattr(interaction_result, "visibility", {}).get("interaction_mode")
    mode_text = str(getattr(mode, "value", mode) or "").strip()
    return mode_text or None


def _normalized_text(voice_turn: object | None) -> str:
    if voice_turn is None:
        return ""
    return str(
        getattr(voice_turn, "normalized_text", None)
        or getattr(voice_turn, "normalized_transcript", None)
        or getattr(voice_turn, "interaction_input", "")
        or ""
    ).strip()


def _voice_locale(voice_turn: object | None) -> str | None:
    if voice_turn is None:
        return None
    locale = str(
        getattr(voice_turn, "locale_hint", None)
        or getattr(voice_turn, "detected_locale", None)
        or ""
    ).strip()
    return locale or None


def _retryable_error(error: VoiceInputError) -> bool:
    code = str(getattr(error, "code", "") or "").strip()
    return code not in {"PERMISSION_DENIED", "MICROPHONE_UNAVAILABLE", "UNSUPPORTED_PLATFORM", "VOICE_SETUP_FAILED"}


def _average(values: list[float] | list[int]) -> float | None:
    if not values:
        return None
    return float(sum(values)) / float(len(values))


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)


def _percent(value: float) -> str:
    return f"{float(value) * 100.0:.1f}%"


def _metric_value(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.1f}"
