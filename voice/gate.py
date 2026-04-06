"""Offline gate helper for staged voice-rollout readiness."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from voice.readiness import build_voice_readiness_record


@dataclass(slots=True, frozen=True)
class VoiceReadinessGateReport:
    """Gate-style readiness verdict for the current voice rollout prerequisites."""

    gate_status: str
    gate_ready: bool
    artifact_path: str
    artifact_status: str
    telemetry_artifact_path: str
    telemetry_artifact_status: str
    telemetry_artifact_command: str
    telemetry_follow_up_relisten_count: int | None
    telemetry_follow_up_dismiss_count: int | None
    telemetry_max_follow_up_chain_length: int | None
    telemetry_follow_up_limit_hit_count: int | None
    telemetry_speech_interrupt_conflict_count: int | None
    telemetry_note: str
    next_step_kind: str
    next_step_reason: str
    next_step_command: str | None
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_status": self.gate_status,
            "gate_ready": self.gate_ready,
            "artifact_path": self.artifact_path,
            "artifact_status": self.artifact_status,
            "telemetry_artifact_path": self.telemetry_artifact_path,
            "telemetry_artifact_status": self.telemetry_artifact_status,
            "telemetry_artifact_command": self.telemetry_artifact_command,
            "telemetry_follow_up_relisten_count": self.telemetry_follow_up_relisten_count,
            "telemetry_follow_up_dismiss_count": self.telemetry_follow_up_dismiss_count,
            "telemetry_max_follow_up_chain_length": self.telemetry_max_follow_up_chain_length,
            "telemetry_follow_up_limit_hit_count": self.telemetry_follow_up_limit_hit_count,
            "telemetry_speech_interrupt_conflict_count": self.telemetry_speech_interrupt_conflict_count,
            "telemetry_note": self.telemetry_note,
            "next_step_kind": self.next_step_kind,
            "next_step_reason": self.next_step_reason,
            "next_step_command": self.next_step_command or "",
            "blockers": list(self.blockers),
        }


def build_voice_readiness_gate_report(
    *,
    environ: Mapping[str, str] | None = None,
    artifact_path: Path | None = None,
    telemetry_artifact_path: Path | None = None,
) -> VoiceReadinessGateReport:
    """Build one explicit ready/blocked voice rollout gate verdict."""
    readiness = build_voice_readiness_record(
        environ=environ,
        artifact_path=artifact_path,
        telemetry_artifact_path=telemetry_artifact_path,
    )
    gate_ready = bool(
        readiness.voice_ready
        and readiness.artifact_status == "ready"
        and readiness.next_step_kind == "voice_readiness_artifact_already_recorded"
    )
    blockers = list(readiness.blockers)
    if readiness.artifact_status != "ready":
        blockers.append(f"voice readiness artifact status is {readiness.artifact_status}")
    elif readiness.next_step_kind != "voice_readiness_artifact_already_recorded":
        blockers.append("voice readiness artifact must be re-recorded against the current rollout prerequisites")
    telemetry_note = (
        "latest session telemetry artifact is recorded"
        f" (follow-up relisten={readiness.telemetry_follow_up_relisten_count or 0},"
        f" dismiss={readiness.telemetry_follow_up_dismiss_count or 0},"
        f" max_chain={readiness.telemetry_max_follow_up_chain_length or 0},"
        f" limit_hits={readiness.telemetry_follow_up_limit_hit_count or 0},"
        f" interrupt_conflicts={readiness.telemetry_speech_interrupt_conflict_count or 0})"
        if readiness.telemetry_artifact_status == "ready"
        else f"advisory only; record a session snapshot before live sign-off with {readiness.telemetry_artifact_command}"
    )
    return VoiceReadinessGateReport(
        gate_status="ready" if gate_ready else "blocked",
        gate_ready=gate_ready,
        artifact_path=readiness.artifact_path,
        artifact_status=readiness.artifact_status,
        telemetry_artifact_path=readiness.telemetry_artifact_path,
        telemetry_artifact_status=readiness.telemetry_artifact_status,
        telemetry_artifact_command=readiness.telemetry_artifact_command,
        telemetry_follow_up_relisten_count=readiness.telemetry_follow_up_relisten_count,
        telemetry_follow_up_dismiss_count=readiness.telemetry_follow_up_dismiss_count,
        telemetry_max_follow_up_chain_length=readiness.telemetry_max_follow_up_chain_length,
        telemetry_follow_up_limit_hit_count=readiness.telemetry_follow_up_limit_hit_count,
        telemetry_speech_interrupt_conflict_count=readiness.telemetry_speech_interrupt_conflict_count,
        telemetry_note=telemetry_note,
        next_step_kind=readiness.next_step_kind,
        next_step_reason=readiness.next_step_reason,
        next_step_command=readiness.next_step_command,
        blockers=blockers,
    )


def format_voice_readiness_gate_report(report: VoiceReadinessGateReport) -> str:
    """Render one operator-friendly voice rollout gate verdict."""
    return "\n".join(
        [
            "JARVIS Voice Readiness Gate",
            f"gate: {report.gate_status}",
            f"artifact path: {report.artifact_path}",
            f"artifact status: {report.artifact_status}",
            f"telemetry artifact path: {report.telemetry_artifact_path}",
            f"telemetry artifact status: {report.telemetry_artifact_status}",
            f"telemetry artifact command: {report.telemetry_artifact_command}",
            f"telemetry follow-up relisten count: {_telemetry_metric_text(report.telemetry_follow_up_relisten_count)}",
            f"telemetry follow-up dismiss count: {_telemetry_metric_text(report.telemetry_follow_up_dismiss_count)}",
            f"telemetry max follow-up chain length: {_telemetry_metric_text(report.telemetry_max_follow_up_chain_length)}",
            f"telemetry follow-up limit hit count: {_telemetry_metric_text(report.telemetry_follow_up_limit_hit_count)}",
            f"telemetry speech interrupt conflict count: {_telemetry_metric_text(report.telemetry_speech_interrupt_conflict_count)}",
            f"telemetry note: {report.telemetry_note}",
            f"next step: {report.next_step_kind}",
            f"next step reason: {report.next_step_reason}",
            f"next step command: {report.next_step_command or 'n/a'}",
            f"blockers: {', '.join(report.blockers) if report.blockers else 'none'}",
        ]
    )


def main() -> int:
    """Build and print one offline voice rollout gate verdict."""
    parser = argparse.ArgumentParser(description="Build an offline voice rollout gate verdict.")
    parser.add_argument(
        "--artifact-path",
        help="Optional path to a specific voice-readiness artifact JSON file.",
    )
    parser.add_argument(
        "--telemetry-artifact-path",
        help="Optional path to a specific voice-telemetry artifact JSON file.",
    )
    parser.add_argument("--json", action="store_true", help="Print the gate report as JSON.")
    args = parser.parse_args()

    report = build_voice_readiness_gate_report(
        artifact_path=Path(args.artifact_path).expanduser() if args.artifact_path else None,
        telemetry_artifact_path=Path(args.telemetry_artifact_path).expanduser() if args.telemetry_artifact_path else None,
    )
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(format_voice_readiness_gate_report(report))
    return 0 if report.gate_ready else 1


def _telemetry_metric_text(value: int | None) -> str:
    if value is None:
        return "n/a"
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
