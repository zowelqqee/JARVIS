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
            "next_step_kind": self.next_step_kind,
            "next_step_reason": self.next_step_reason,
            "next_step_command": self.next_step_command or "",
            "blockers": list(self.blockers),
        }


def build_voice_readiness_gate_report(
    *,
    environ: Mapping[str, str] | None = None,
    artifact_path: Path | None = None,
) -> VoiceReadinessGateReport:
    """Build one explicit ready/blocked voice rollout gate verdict."""
    readiness = build_voice_readiness_record(environ=environ, artifact_path=artifact_path)
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
    return VoiceReadinessGateReport(
        gate_status="ready" if gate_ready else "blocked",
        gate_ready=gate_ready,
        artifact_path=readiness.artifact_path,
        artifact_status=readiness.artifact_status,
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
    parser.add_argument("--json", action="store_true", help="Print the gate report as JSON.")
    args = parser.parse_args()

    report = build_voice_readiness_gate_report(
        artifact_path=Path(args.artifact_path).expanduser() if args.artifact_path else None,
    )
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(format_voice_readiness_gate_report(report))
    return 0 if report.gate_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
