"""Offline rollout-readiness helper for the current voice path."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
from typing import Any, Mapping

from voice.flags import continuous_voice_mode_enabled
from voice.session import build_follow_up_capture_request, capture_follow_up_voice_turn
from voice.status import build_tts_backend_status
from voice.telemetry import (
    VoiceTelemetrySnapshot,
    build_default_voice_telemetry,
    load_voice_telemetry_snapshot,
    voice_telemetry_artifact_path,
)
from voice.tts_operator_hints import (
    NATIVE_TTS_DOCTOR_COMMAND,
    NATIVE_TTS_TYPECHECK_COMMAND,
    native_tts_follow_up_command,
    native_tts_next_step_details,
)
from voice.tts_provider import build_default_tts_provider

_REPO_ROOT = Path(__file__).resolve().parents[1]
_VOICE_READINESS_ARTIFACT = _REPO_ROOT / "tmp" / "qa" / "voice_readiness.json"
_MANUAL_VERIFICATION_DOC = "docs/manual_voice_verification.md"
_MANUAL_VERIFICATION_DOC_PATH = _REPO_ROOT / _MANUAL_VERIFICATION_DOC
_VOICE_READINESS_GUIDE_COMMAND = "python3 -m voice.readiness"
_VOICE_TELEMETRY_GUIDE_COMMAND = "voice telemetry write"
_NATIVE_TTS_ENV = "JARVIS_TTS_MACOS_NATIVE"


@dataclass(slots=True, frozen=True)
class NativeTTSSmokeSummary:
    """Operator-facing native macOS TTS smoke status for the current env."""

    requested: bool
    status: str
    active_backend: str | None = None
    error_code: str | None = None
    reason: str | None = None
    command: str | None = None
    detail_lines: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class VoiceReadinessRecord:
    """Machine-readable readiness summary for staged voice rollout."""

    advanced_follow_up_flag: str
    advanced_follow_up_default_off: bool
    advanced_follow_up_enabled_in_current_env: bool
    telemetry_available: bool
    telemetry_artifact_path: str
    telemetry_artifact_status: str
    telemetry_artifact_created_at: str | None
    telemetry_artifact_command: str
    telemetry_follow_up_relisten_count: int | None
    telemetry_follow_up_dismiss_count: int | None
    telemetry_max_follow_up_chain_length: int | None
    telemetry_follow_up_limit_hit_count: int | None
    telemetry_speech_interrupt_conflict_count: int | None
    follow_up_session_available: bool
    native_tts_requested: bool
    native_tts_status: str
    native_tts_active_backend: str | None
    native_tts_reason: str | None
    native_tts_command: str | None
    native_tts_detail_lines: list[str]
    manual_verification_doc: str
    manual_verification_doc_present: bool
    manual_verification_recorded: bool
    artifact_path: str
    artifact_status: str
    artifact_created_at: str | None
    next_step_kind: str
    next_step_reason: str
    next_step_command: str | None
    next_step_detail_lines: list[str]
    blockers: list[str] = field(default_factory=list)
    notes: str | None = None

    @property
    def voice_ready(self) -> bool:
        return not self.blockers

    def to_dict(self) -> dict[str, Any]:
        return {
            "advanced_follow_up_flag": self.advanced_follow_up_flag,
            "advanced_follow_up_default_off": self.advanced_follow_up_default_off,
            "advanced_follow_up_enabled_in_current_env": self.advanced_follow_up_enabled_in_current_env,
            "telemetry_available": self.telemetry_available,
            "telemetry_artifact_path": self.telemetry_artifact_path,
            "telemetry_artifact_status": self.telemetry_artifact_status,
            "telemetry_artifact_created_at": self.telemetry_artifact_created_at,
            "telemetry_artifact_command": self.telemetry_artifact_command,
            "telemetry_follow_up_relisten_count": self.telemetry_follow_up_relisten_count,
            "telemetry_follow_up_dismiss_count": self.telemetry_follow_up_dismiss_count,
            "telemetry_max_follow_up_chain_length": self.telemetry_max_follow_up_chain_length,
            "telemetry_follow_up_limit_hit_count": self.telemetry_follow_up_limit_hit_count,
            "telemetry_speech_interrupt_conflict_count": self.telemetry_speech_interrupt_conflict_count,
            "follow_up_session_available": self.follow_up_session_available,
            "native_tts_requested": self.native_tts_requested,
            "native_tts_status": self.native_tts_status,
            "native_tts_active_backend": self.native_tts_active_backend or "",
            "native_tts_reason": self.native_tts_reason or "",
            "native_tts_command": self.native_tts_command or "",
            "native_tts_detail_lines": list(self.native_tts_detail_lines),
            "manual_verification_doc": self.manual_verification_doc,
            "manual_verification_doc_present": self.manual_verification_doc_present,
            "manual_verification_recorded": self.manual_verification_recorded,
            "artifact_path": self.artifact_path,
            "artifact_status": self.artifact_status,
            "artifact_created_at": self.artifact_created_at,
            "next_step_kind": self.next_step_kind,
            "next_step_reason": self.next_step_reason,
            "next_step_command": self.next_step_command or "",
            "next_step_detail_lines": list(self.next_step_detail_lines),
            "voice_ready": self.voice_ready,
            "blockers": list(self.blockers),
            "notes": self.notes or "",
        }


def build_voice_readiness_record(
    *,
    manual_verified: bool = False,
    notes: str | None = None,
    environ: Mapping[str, str] | None = None,
    artifact_path: Path | None = None,
    telemetry_artifact_path: Path | None = None,
) -> VoiceReadinessRecord:
    """Build the current offline voice-readiness summary."""
    resolved_artifact_path = artifact_path or voice_readiness_artifact_path()
    artifact_path_value, artifact_payload, artifact_error = load_voice_readiness_artifact(resolved_artifact_path)
    artifact_status = _voice_readiness_artifact_status(artifact_payload=artifact_payload, artifact_error=artifact_error)
    artifact_created_at = _artifact_created_at(artifact_payload)
    resolved_telemetry_artifact_path = telemetry_artifact_path or voice_telemetry_artifact_path()
    (
        telemetry_artifact_path_value,
        telemetry_artifact_status,
        telemetry_artifact_created_at,
        telemetry_snapshot,
        telemetry_error,
    ) = load_voice_telemetry_snapshot(resolved_telemetry_artifact_path)
    artifact_manual_verified = _artifact_manual_verified(artifact_payload)
    effective_manual_verified = bool(manual_verified or artifact_manual_verified)
    manual_doc_present = _MANUAL_VERIFICATION_DOC_PATH.exists()
    telemetry_available = callable(build_default_voice_telemetry)
    follow_up_session_available = callable(build_follow_up_capture_request) and callable(capture_follow_up_voice_turn)
    default_env_continuous_mode = continuous_voice_mode_enabled(environ={})
    current_env_continuous_mode = continuous_voice_mode_enabled(environ=environ)
    native_tts_smoke = _native_tts_smoke_summary(environ=environ)

    blockers: list[str] = []
    if not manual_doc_present:
        blockers.append("manual voice verification doc is missing")
    if not telemetry_available:
        blockers.append("voice telemetry collector is unavailable")
    if not follow_up_session_available:
        blockers.append("voice follow-up session helpers are unavailable")
    if default_env_continuous_mode:
        blockers.append("advanced voice follow-up is enabled by default")
    if not effective_manual_verified:
        blockers.append("manual voice verification is not recorded")
    if native_tts_smoke.requested and native_tts_smoke.status == "blocked":
        blockers.append(f"native macOS TTS smoke is blocked ({native_tts_smoke.reason or 'unknown reason'})")

    next_step_kind, next_step_reason, next_step_command, next_step_detail_lines = _voice_readiness_next_step(
        blockers=blockers,
        manual_verified=effective_manual_verified,
        artifact_status=artifact_status,
        artifact_payload=artifact_payload,
        native_tts_smoke=native_tts_smoke,
    )

    return VoiceReadinessRecord(
        advanced_follow_up_flag="JARVIS_VOICE_CONTINUOUS_MODE",
        advanced_follow_up_default_off=not default_env_continuous_mode,
        advanced_follow_up_enabled_in_current_env=current_env_continuous_mode,
        telemetry_available=telemetry_available,
        telemetry_artifact_path=str(telemetry_artifact_path_value),
        telemetry_artifact_status=telemetry_artifact_status,
        telemetry_artifact_created_at=telemetry_artifact_created_at,
        telemetry_artifact_command=_VOICE_TELEMETRY_GUIDE_COMMAND,
        telemetry_follow_up_relisten_count=_telemetry_count(telemetry_snapshot, "follow_up_relisten_count"),
        telemetry_follow_up_dismiss_count=_telemetry_count(telemetry_snapshot, "follow_up_dismiss_count"),
        telemetry_max_follow_up_chain_length=_telemetry_count(telemetry_snapshot, "max_follow_up_chain_length"),
        telemetry_follow_up_limit_hit_count=_telemetry_count(telemetry_snapshot, "follow_up_limit_hit_count"),
        telemetry_speech_interrupt_conflict_count=_telemetry_count(
            telemetry_snapshot,
            "speech_interrupt_conflict_count",
        ),
        follow_up_session_available=follow_up_session_available,
        native_tts_requested=native_tts_smoke.requested,
        native_tts_status=native_tts_smoke.status,
        native_tts_active_backend=native_tts_smoke.active_backend,
        native_tts_reason=native_tts_smoke.reason,
        native_tts_command=native_tts_smoke.command,
        native_tts_detail_lines=list(native_tts_smoke.detail_lines),
        manual_verification_doc=_MANUAL_VERIFICATION_DOC,
        manual_verification_doc_present=manual_doc_present,
        manual_verification_recorded=effective_manual_verified,
        artifact_path=str(artifact_path_value),
        artifact_status=artifact_status,
        artifact_created_at=artifact_created_at,
        next_step_kind=next_step_kind,
        next_step_reason=next_step_reason,
        next_step_command=next_step_command,
        next_step_detail_lines=list(next_step_detail_lines),
        blockers=blockers,
        notes=str(notes or "").strip() or None,
    )


def format_voice_readiness_record(record: VoiceReadinessRecord) -> str:
    """Render one operator-friendly voice-readiness summary."""
    lines = [
        "JARVIS Voice Readiness",
        f"artifact path: {record.artifact_path}",
        f"artifact status: {record.artifact_status}",
        f"artifact created at: {record.artifact_created_at or 'n/a'}",
        f"telemetry artifact path: {record.telemetry_artifact_path}",
        f"telemetry artifact status: {record.telemetry_artifact_status}",
        f"telemetry artifact created at: {record.telemetry_artifact_created_at or 'n/a'}",
        f"telemetry artifact command: {record.telemetry_artifact_command}",
        f"telemetry follow-up relisten count: {_telemetry_metric_text(record.telemetry_follow_up_relisten_count)}",
        f"telemetry follow-up dismiss count: {_telemetry_metric_text(record.telemetry_follow_up_dismiss_count)}",
        f"telemetry max follow-up chain length: {_telemetry_metric_text(record.telemetry_max_follow_up_chain_length)}",
        f"telemetry follow-up limit hit count: {_telemetry_metric_text(record.telemetry_follow_up_limit_hit_count)}",
        f"telemetry speech interrupt conflict count: {_telemetry_metric_text(record.telemetry_speech_interrupt_conflict_count)}",
        f"native tts requested in current env: {'yes' if record.native_tts_requested else 'no'}",
        f"native tts smoke status: {record.native_tts_status}",
        f"native tts active backend: {record.native_tts_active_backend or 'n/a'}",
        f"native tts reason: {record.native_tts_reason or 'n/a'}",
        f"native tts command: {record.native_tts_command or 'n/a'}",
        f"manual verification doc: {record.manual_verification_doc}",
        f"manual verification doc present: {'yes' if record.manual_verification_doc_present else 'no'}",
        f"manual verification recorded: {'yes' if record.manual_verification_recorded else 'no'}",
        f"advanced follow-up flag: {record.advanced_follow_up_flag}",
        f"advanced follow-up default off: {'yes' if record.advanced_follow_up_default_off else 'no'}",
        f"advanced follow-up enabled in current env: {'yes' if record.advanced_follow_up_enabled_in_current_env else 'no'}",
        f"telemetry available: {'yes' if record.telemetry_available else 'no'}",
        f"follow-up session available: {'yes' if record.follow_up_session_available else 'no'}",
        f"voice ready: {'yes' if record.voice_ready else 'no'}",
        f"next step: {record.next_step_kind}",
        f"next step reason: {record.next_step_reason}",
        f"next step command: {record.next_step_command or 'n/a'}",
        f"blockers: {', '.join(record.blockers) if record.blockers else 'none'}",
    ]
    lines.extend(f"native tts detail: {detail}" for detail in record.native_tts_detail_lines)
    lines.extend(f"next step detail: {detail}" for detail in record.next_step_detail_lines)
    if record.telemetry_artifact_status == "ready":
        lines.append(
            "telemetry note: latest session telemetry artifact is recorded"
            f" (follow-up relisten={record.telemetry_follow_up_relisten_count or 0},"
            f" dismiss={record.telemetry_follow_up_dismiss_count or 0},"
            f" max_chain={record.telemetry_max_follow_up_chain_length or 0},"
            f" limit_hits={record.telemetry_follow_up_limit_hit_count or 0},"
            f" interrupt_conflicts={record.telemetry_speech_interrupt_conflict_count or 0})"
        )
    else:
        lines.append(
            f"telemetry note: advisory only; record a session snapshot before live sign-off with {record.telemetry_artifact_command}"
        )
    if record.notes:
        lines.append(f"notes: {record.notes}")
    return "\n".join(lines)


def voice_readiness_artifact_payload(record: VoiceReadinessRecord) -> dict[str, Any]:
    """Return the machine-readable voice-readiness artifact payload."""
    return {
        "schema_version": 1,
        "runner": "voice.readiness",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "report": record.to_dict(),
    }


def write_voice_readiness_artifact(
    record: VoiceReadinessRecord,
    *,
    artifact_path: Path | None = None,
) -> Path:
    """Persist one voice-readiness artifact when all blockers are cleared."""
    if not record.voice_ready:
        raise ValueError("voice readiness record is blocked; refusing to write final artifact")
    resolved_artifact_path = artifact_path or voice_readiness_artifact_path()
    resolved_artifact_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_artifact_path.write_text(
        json.dumps(voice_readiness_artifact_payload(record), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return resolved_artifact_path


def load_voice_readiness_artifact(
    artifact_path: Path | None = None,
) -> tuple[Path, dict[str, Any] | None, str | None]:
    """Load the current voice-readiness artifact plus any parse error."""
    resolved_artifact_path = artifact_path or voice_readiness_artifact_path()
    if not resolved_artifact_path.exists():
        return resolved_artifact_path, None, None
    try:
        payload = json.loads(resolved_artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return resolved_artifact_path, None, f"{type(exc).__name__}: {exc}"
    if not isinstance(payload, dict):
        return resolved_artifact_path, None, "ValueError: voice readiness artifact must be a JSON object."
    return resolved_artifact_path, payload, None


def voice_readiness_artifact_path() -> Path:
    """Return the default artifact path for voice-readiness records."""
    return _VOICE_READINESS_ARTIFACT


def main() -> int:
    """Build and optionally persist one offline voice-readiness record."""
    parser = argparse.ArgumentParser(description="Build an offline voice-readiness record.")
    parser.add_argument(
        "--artifact-path",
        help="Optional path to a specific voice-readiness artifact JSON file.",
    )
    parser.add_argument(
        "--telemetry-artifact-path",
        help="Optional path to a specific voice-telemetry artifact JSON file.",
    )
    parser.add_argument("--manual-verified", action="store_true", help="Record that live manual voice verification was completed.")
    parser.add_argument("--notes", help="Optional operator notes.")
    parser.add_argument("--write-artifact", action="store_true", help="Write the voice-readiness artifact to tmp/qa.")
    parser.add_argument("--json", action="store_true", help="Print the record as JSON.")
    args = parser.parse_args()
    artifact_path = Path(args.artifact_path).expanduser() if args.artifact_path else None
    telemetry_artifact_path = Path(args.telemetry_artifact_path).expanduser() if args.telemetry_artifact_path else None

    record = build_voice_readiness_record(
        manual_verified=bool(args.manual_verified),
        notes=args.notes,
        artifact_path=artifact_path,
        telemetry_artifact_path=telemetry_artifact_path,
    )
    if args.write_artifact:
        if not record.voice_ready:
            print(format_voice_readiness_record(record))
            raise SystemExit("voice readiness is still blocked; refusing to write final artifact")
        written_path = write_voice_readiness_artifact(record, artifact_path=artifact_path)
        print(f"wrote voice readiness artifact: {written_path}")
        return 0
    if args.json:
        print(json.dumps(voice_readiness_artifact_payload(record), indent=2, sort_keys=True))
    else:
        print(format_voice_readiness_record(record))
    return 0


def _voice_readiness_artifact_status(
    *,
    artifact_payload: dict[str, Any] | None,
    artifact_error: str | None,
) -> str:
    report_status = _supporting_artifact_status(payload=artifact_payload, artifact_error=artifact_error, required_key="report")
    if report_status != "ready":
        return report_status
    report = artifact_payload.get("report")
    if bool(report.get("manual_verification_recorded")):
        return "ready"
    return "partial"


def _artifact_created_at(artifact_payload: dict[str, Any] | None) -> str | None:
    created_at = str((artifact_payload or {}).get("created_at", "") or "").strip()
    return created_at or None


def _artifact_manual_verified(artifact_payload: dict[str, Any] | None) -> bool:
    report = (artifact_payload or {}).get("report")
    if not isinstance(report, dict):
        return False
    return bool(report.get("manual_verification_recorded"))


def _artifact_matches_current_readiness(artifact_payload: dict[str, Any] | None) -> bool:
    report = (artifact_payload or {}).get("report")
    if not isinstance(report, dict):
        return False
    expected_pairs = {
        "advanced_follow_up_flag": "JARVIS_VOICE_CONTINUOUS_MODE",
        "advanced_follow_up_default_off": True,
        "telemetry_available": True,
        "follow_up_session_available": True,
        "manual_verification_doc": _MANUAL_VERIFICATION_DOC,
        "manual_verification_doc_present": True,
        "manual_verification_recorded": True,
        "voice_ready": True,
    }
    for key, expected_value in expected_pairs.items():
        if report.get(key) != expected_value:
            return False
    return True


def _supporting_artifact_status(
    *,
    payload: dict[str, Any] | None,
    artifact_error: str | None,
    required_key: str,
) -> str:
    if artifact_error:
        return "invalid"
    if payload is None:
        return "missing"
    if not isinstance(payload.get(required_key), dict):
        return "invalid"
    return "ready"


def _telemetry_count(snapshot: VoiceTelemetrySnapshot | None, field_name: str) -> int | None:
    if snapshot is None:
        return None
    return int(getattr(snapshot, field_name, 0) or 0)


def _telemetry_metric_text(value: int | None) -> str:
    if value is None:
        return "n/a"
    return str(value)


def _native_tts_smoke_summary(*, environ: Mapping[str, str] | None = None) -> NativeTTSSmokeSummary:
    current_environ = dict(os.environ if environ is None else environ)
    requested = _env_flag_enabled(current_environ.get(_NATIVE_TTS_ENV))
    if not requested:
        return NativeTTSSmokeSummary(
            requested=False,
            status="not_requested",
            reason="native macOS TTS opt-in is disabled in the current env",
            command=NATIVE_TTS_DOCTOR_COMMAND,
        )
    if sys.platform != "darwin":
        return NativeTTSSmokeSummary(
            requested=True,
            status="blocked",
            reason="UNSUPPORTED_PLATFORM: native macOS backend is darwin-only",
        )

    provider = build_default_tts_provider(environ=current_environ)
    backend_status = build_tts_backend_status(provider)
    native_diagnostic = next(
        (diagnostic for diagnostic in backend_status.diagnostics if diagnostic.backend_name == "macos_native"),
        None,
    )
    if native_diagnostic is None:
        return NativeTTSSmokeSummary(
            requested=True,
            status="unknown",
            active_backend=backend_status.backend_name,
            reason="native macOS backend diagnostics are unavailable",
            command=NATIVE_TTS_DOCTOR_COMMAND,
        )
    if native_diagnostic.available:
        return NativeTTSSmokeSummary(
            requested=True,
            status="ready",
            active_backend=backend_status.backend_name,
            error_code=native_diagnostic.error_code,
            reason="native macOS backend is available for manual smoke",
            command="env JARVIS_TTS_MACOS_NATIVE=1 python3 cli.py",
            detail_lines=native_diagnostic.detail_lines,
        )
    reason = _native_tts_reason(native_diagnostic.error_code, native_diagnostic.error_message)
    return NativeTTSSmokeSummary(
        requested=True,
        status="blocked",
        active_backend=backend_status.backend_name,
        error_code=native_diagnostic.error_code,
        reason=reason,
        command=native_tts_follow_up_command(native_diagnostic.error_code),
        detail_lines=native_diagnostic.detail_lines,
    )


def _voice_readiness_next_step(
    *,
    blockers: list[str],
    manual_verified: bool,
    artifact_status: str,
    artifact_payload: dict[str, Any] | None,
    native_tts_smoke: NativeTTSSmokeSummary,
) -> tuple[str, str, str | None, tuple[str, ...]]:
    if blockers:
        if not manual_verified:
            return (
                "complete_manual_voice_verification",
                "run the live voice verification checklist and then record readiness explicitly",
                f"{_VOICE_READINESS_GUIDE_COMMAND} --manual-verified --write-artifact",
                (),
            )
        native_tts_next_step = _native_tts_next_step(
            blockers=blockers,
            native_tts_smoke=native_tts_smoke,
        )
        if native_tts_next_step is not None:
            return native_tts_next_step
        return (
            "resolve_voice_rollout_blockers",
            "voice rollout prerequisites are still incomplete",
            None,
            (),
        )
    if artifact_status == "ready" and _artifact_matches_current_readiness(artifact_payload):
        return (
            "voice_readiness_artifact_already_recorded",
            "current voice readiness artifact is already recorded and matches the current rollout prerequisites",
            None,
            (),
        )
    return (
        "write_voice_readiness_artifact",
        "voice rollout prerequisites are satisfied; record the offline readiness artifact",
        f"{_VOICE_READINESS_GUIDE_COMMAND} --manual-verified --write-artifact",
        (),
    )


def _env_flag_enabled(raw_value: object | None) -> bool:
    value = str(raw_value or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _native_tts_reason(error_code: str | None, error_message: str | None) -> str:
    code = str(error_code or "").strip()
    message = str(error_message or "").strip()
    if code and message:
        return f"{code}: {message}"
    return message or code or "native macOS backend is unavailable"


def _native_tts_next_step(
    *,
    blockers: list[str],
    native_tts_smoke: NativeTTSSmokeSummary,
) -> tuple[str, str, str | None, tuple[str, ...]] | None:
    if not native_tts_smoke.requested or native_tts_smoke.status != "blocked":
        return None
    non_native_blockers = [
        blocker
        for blocker in blockers
        if not blocker.startswith("native macOS TTS smoke is blocked")
    ]
    if non_native_blockers:
        return None

    reason = str(native_tts_smoke.reason or "").strip()
    error_code = str(native_tts_smoke.error_code or "").strip()
    command = native_tts_smoke.command
    if error_code == "HOST_SDK_MISMATCH":
        return (
            "resolve_native_tts_sdk_mismatch",
            "align local Xcode and Command Line Tools so the active Swift compiler matches the installed SDK before native smoke",
            command or NATIVE_TTS_TYPECHECK_COMMAND,
            native_tts_next_step_details(error_code),
        )
    if error_code == "HOST_TOOLCHAIN_MISSING":
        return (
            "restore_native_tts_toolchain",
            "install or select a working Swift toolchain before retrying native macOS TTS smoke",
            command or NATIVE_TTS_DOCTOR_COMMAND,
            (),
        )
    if error_code == "HOST_SWIFT_BRIDGING_CONFLICT":
        return (
            "resolve_native_tts_swift_bridging_conflict",
            "clear the local SwiftBridging module conflict before retrying native macOS TTS smoke",
            command or NATIVE_TTS_TYPECHECK_COMMAND,
            (),
        )
    if error_code == "HOST_COMPILE_FAILED":
        return (
            "resolve_native_tts_compile_failure",
            "fix the native macOS host compile failure before retrying native TTS smoke",
            command or NATIVE_TTS_TYPECHECK_COMMAND,
            (),
        )
    return (
        "resolve_native_tts_opt_in_blocker",
        f"resolve the native macOS TTS opt-in blocker before retrying smoke ({reason or 'unknown reason'})",
        command or NATIVE_TTS_DOCTOR_COMMAND,
        (),
    )


if __name__ == "__main__":
    raise SystemExit(main())
