"""Offline rollout-readiness helper for the current voice path."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from voice.flags import continuous_voice_mode_enabled
from voice.session import build_follow_up_capture_request, capture_follow_up_voice_turn
from voice.telemetry import build_default_voice_telemetry

_REPO_ROOT = Path(__file__).resolve().parents[1]
_VOICE_READINESS_ARTIFACT = _REPO_ROOT / "tmp" / "qa" / "voice_readiness.json"
_MANUAL_VERIFICATION_DOC = "docs/manual_voice_verification.md"
_MANUAL_VERIFICATION_DOC_PATH = _REPO_ROOT / _MANUAL_VERIFICATION_DOC
_VOICE_READINESS_GUIDE_COMMAND = "python3 -m voice.readiness"


@dataclass(slots=True, frozen=True)
class VoiceReadinessRecord:
    """Machine-readable readiness summary for staged voice rollout."""

    advanced_follow_up_flag: str
    advanced_follow_up_default_off: bool
    advanced_follow_up_enabled_in_current_env: bool
    telemetry_available: bool
    follow_up_session_available: bool
    manual_verification_doc: str
    manual_verification_doc_present: bool
    manual_verification_recorded: bool
    artifact_path: str
    artifact_status: str
    artifact_created_at: str | None
    next_step_kind: str
    next_step_reason: str
    next_step_command: str | None
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
            "follow_up_session_available": self.follow_up_session_available,
            "manual_verification_doc": self.manual_verification_doc,
            "manual_verification_doc_present": self.manual_verification_doc_present,
            "manual_verification_recorded": self.manual_verification_recorded,
            "artifact_path": self.artifact_path,
            "artifact_status": self.artifact_status,
            "artifact_created_at": self.artifact_created_at,
            "next_step_kind": self.next_step_kind,
            "next_step_reason": self.next_step_reason,
            "next_step_command": self.next_step_command or "",
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
) -> VoiceReadinessRecord:
    """Build the current offline voice-readiness summary."""
    resolved_artifact_path = artifact_path or voice_readiness_artifact_path()
    artifact_path_value, artifact_payload, artifact_error = load_voice_readiness_artifact(resolved_artifact_path)
    artifact_status = _voice_readiness_artifact_status(artifact_payload=artifact_payload, artifact_error=artifact_error)
    artifact_created_at = _artifact_created_at(artifact_payload)
    artifact_manual_verified = _artifact_manual_verified(artifact_payload)
    effective_manual_verified = bool(manual_verified or artifact_manual_verified)
    manual_doc_present = _MANUAL_VERIFICATION_DOC_PATH.exists()
    telemetry_available = callable(build_default_voice_telemetry)
    follow_up_session_available = callable(build_follow_up_capture_request) and callable(capture_follow_up_voice_turn)
    default_env_continuous_mode = continuous_voice_mode_enabled(environ={})
    current_env_continuous_mode = continuous_voice_mode_enabled(environ=environ)

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

    next_step_kind, next_step_reason, next_step_command = _voice_readiness_next_step(
        blockers=blockers,
        manual_verified=effective_manual_verified,
        artifact_status=artifact_status,
        artifact_payload=artifact_payload,
    )

    return VoiceReadinessRecord(
        advanced_follow_up_flag="JARVIS_VOICE_CONTINUOUS_MODE",
        advanced_follow_up_default_off=not default_env_continuous_mode,
        advanced_follow_up_enabled_in_current_env=current_env_continuous_mode,
        telemetry_available=telemetry_available,
        follow_up_session_available=follow_up_session_available,
        manual_verification_doc=_MANUAL_VERIFICATION_DOC,
        manual_verification_doc_present=manual_doc_present,
        manual_verification_recorded=effective_manual_verified,
        artifact_path=str(artifact_path_value),
        artifact_status=artifact_status,
        artifact_created_at=artifact_created_at,
        next_step_kind=next_step_kind,
        next_step_reason=next_step_reason,
        next_step_command=next_step_command,
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
    parser.add_argument("--manual-verified", action="store_true", help="Record that live manual voice verification was completed.")
    parser.add_argument("--notes", help="Optional operator notes.")
    parser.add_argument("--write-artifact", action="store_true", help="Write the voice-readiness artifact to tmp/qa.")
    parser.add_argument("--json", action="store_true", help="Print the record as JSON.")
    args = parser.parse_args()
    artifact_path = Path(args.artifact_path).expanduser() if args.artifact_path else None

    record = build_voice_readiness_record(
        manual_verified=bool(args.manual_verified),
        notes=args.notes,
        artifact_path=artifact_path,
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
    if artifact_error:
        return "invalid"
    if artifact_payload is None:
        return "missing"
    report = artifact_payload.get("report")
    if not isinstance(report, dict):
        return "invalid"
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


def _voice_readiness_next_step(
    *,
    blockers: list[str],
    manual_verified: bool,
    artifact_status: str,
    artifact_payload: dict[str, Any] | None,
) -> tuple[str, str, str | None]:
    if blockers:
        if not manual_verified:
            return (
                "complete_manual_voice_verification",
                "run the live voice verification checklist and then record readiness explicitly",
                f"{_VOICE_READINESS_GUIDE_COMMAND} --manual-verified --write-artifact",
            )
        return (
            "resolve_voice_rollout_blockers",
            "voice rollout prerequisites are still incomplete",
            None,
        )
    if artifact_status == "ready" and _artifact_matches_current_readiness(artifact_payload):
        return (
            "voice_readiness_artifact_already_recorded",
            "current voice readiness artifact is already recorded and matches the current rollout prerequisites",
            None,
        )
    return (
        "write_voice_readiness_artifact",
        "voice rollout prerequisites are satisfied; record the offline readiness artifact",
        f"{_VOICE_READINESS_GUIDE_COMMAND} --manual-verified --write-artifact",
    )


if __name__ == "__main__":
    raise SystemExit(main())
