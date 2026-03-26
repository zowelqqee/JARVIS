"""Machine-readable beta release-review artifact for QA rollout decisioning."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from qa.manual_beta_checklist import load_manual_beta_checklist_artifact, manual_beta_checklist_status
from qa.rollout_profiles import beta_release_review_artifact_path
from qa.rollout_profiles import manual_beta_checklist_artifact_path

_CANDIDATE_PROFILES = ("llm_env", "llm_env_strict")
_REVIEW_CHECKS = (
    ("latency_review", "Latency review"),
    ("cost_review", "Cost review"),
    ("operator_signoff", "Operator sign-off"),
    ("product_approval", "Product approval"),
)


@dataclass(slots=True, frozen=True)
class BetaReleaseReviewRecord:
    """Current release-review status for beta_question_default."""

    review_id: str
    candidate_profile: str | None
    checks: dict[str, dict[str, Any]]
    manual_checklist_artifact_status: str
    manual_checklist_artifact_completed: bool
    manual_checklist_items_passed: int | None
    manual_checklist_items_total: int | None
    manual_checklist_artifact_age_hours: float | None
    manual_checklist_artifact_fresh: bool | None
    manual_checklist_artifact_reason: str | None
    manual_checklist_artifact_created_at: str | None
    manual_checklist_artifact_sha256: str | None
    notes: str | None = None

    @property
    def completed_checks(self) -> int:
        return sum(1 for check in self.checks.values() if bool(check.get("completed")))

    @property
    def total_checks(self) -> int:
        return len(_REVIEW_CHECKS)

    @property
    def all_completed(self) -> bool:
        return (
            bool(self.candidate_profile)
            and self.manual_checklist_artifact_completed
            and self.manual_checklist_artifact_fresh is True
            and self.completed_checks == self.total_checks
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "candidate_profile": self.candidate_profile or "",
            "completed_checks": self.completed_checks,
            "total_checks": self.total_checks,
            "all_completed": self.all_completed,
            "manual_checklist_artifact_status": self.manual_checklist_artifact_status,
            "manual_checklist_artifact_completed": self.manual_checklist_artifact_completed,
            "manual_checklist_items_passed": self.manual_checklist_items_passed,
            "manual_checklist_items_total": self.manual_checklist_items_total,
            "manual_checklist_artifact_age_hours": self.manual_checklist_artifact_age_hours,
            "manual_checklist_artifact_fresh": self.manual_checklist_artifact_fresh,
            "manual_checklist_artifact_reason": self.manual_checklist_artifact_reason or "",
            "manual_checklist_artifact_created_at": self.manual_checklist_artifact_created_at,
            "manual_checklist_artifact_sha256": self.manual_checklist_artifact_sha256,
            "checks": dict(self.checks),
            "notes": self.notes or "",
        }


def build_beta_release_review_record(
    *,
    candidate_profile: str | None = None,
    latency_review_completed: bool = False,
    cost_review_completed: bool = False,
    operator_signoff_completed: bool = False,
    product_approval_completed: bool = False,
    all_completed: bool = False,
    notes: str | None = None,
    existing_payload: dict[str, Any] | None = None,
    reset: bool = False,
) -> BetaReleaseReviewRecord:
    """Build one beta release-review record, optionally updating an existing artifact."""
    existing_report = {} if reset else dict((existing_payload or {}).get("report", {}) or {})
    resolved_candidate = str(candidate_profile or existing_report.get("candidate_profile", "") or "").strip() or None
    if resolved_candidate is not None and resolved_candidate not in _CANDIDATE_PROFILES:
        raise ValueError(f"Unsupported beta release-review candidate profile: {candidate_profile!r}.")
    (
        manual_artifact_path,
        manual_artifact_payload,
        manual_artifact_error,
    ) = load_manual_beta_checklist_artifact(manual_beta_checklist_artifact_path())
    (
        manual_checklist_artifact_status,
        manual_checklist_items_passed,
        manual_checklist_items_total,
        manual_checklist_artifact_completed,
    ) = manual_beta_checklist_status(manual_artifact_payload, manual_artifact_error)
    (
        manual_checklist_artifact_age_hours,
        manual_checklist_artifact_fresh,
        manual_checklist_artifact_reason,
    ) = _artifact_freshness(manual_artifact_payload)

    existing_checks = _existing_check_states(existing_payload if not reset else None)
    checks: dict[str, dict[str, Any]] = {}
    for check_id, label in _REVIEW_CHECKS:
        existing_state = dict(existing_checks.get(check_id, {}) or {})
        checks[check_id] = {
            "label": label,
            "completed": bool(existing_state.get("completed", False)),
        }

    if all_completed:
        for check_state in checks.values():
            check_state["completed"] = True
    if latency_review_completed:
        checks["latency_review"]["completed"] = True
    if cost_review_completed:
        checks["cost_review"]["completed"] = True
    if operator_signoff_completed:
        checks["operator_signoff"]["completed"] = True
    if product_approval_completed:
        checks["product_approval"]["completed"] = True

    return BetaReleaseReviewRecord(
        review_id="beta_question_default",
        candidate_profile=resolved_candidate,
        checks=checks,
        manual_checklist_artifact_status=manual_checklist_artifact_status,
        manual_checklist_artifact_completed=manual_checklist_artifact_completed,
        manual_checklist_items_passed=manual_checklist_items_passed,
        manual_checklist_items_total=manual_checklist_items_total,
        manual_checklist_artifact_age_hours=manual_checklist_artifact_age_hours,
        manual_checklist_artifact_fresh=manual_checklist_artifact_fresh,
        manual_checklist_artifact_reason=manual_checklist_artifact_reason,
        manual_checklist_artifact_created_at=_artifact_created_at(manual_artifact_payload),
        manual_checklist_artifact_sha256=_artifact_sha256(manual_artifact_path, artifact_error=manual_artifact_error),
        notes=str(notes or "").strip() or None,
    )


def format_beta_release_review_record(record: BetaReleaseReviewRecord) -> str:
    """Render one operator-friendly beta release-review summary."""
    lines = [
        "JARVIS QA Beta Release Review",
        f"review: {record.review_id}",
        f"candidate: {record.candidate_profile or 'none'}",
        f"progress: {record.completed_checks}/{record.total_checks}",
        "manual checklist artifact: "
        f"{record.manual_checklist_artifact_status}"
        f"{_format_ratio(record.manual_checklist_items_passed, record.manual_checklist_items_total)}"
        f"{_format_freshness(record.manual_checklist_artifact_fresh, record.manual_checklist_artifact_age_hours)}",
        f"all completed: {'yes' if record.all_completed else 'no'}",
        "checks:",
    ]
    for check_id, label in _REVIEW_CHECKS:
        check_state = dict(record.checks.get(check_id, {}) or {})
        lines.append(
            f"  - {check_id}: {'completed' if bool(check_state.get('completed')) else 'pending'} ({label})"
        )
    if record.notes:
        lines.append(f"notes: {record.notes}")
    return "\n".join(lines)


def beta_release_review_artifact_payload(record: BetaReleaseReviewRecord) -> dict[str, Any]:
    """Return the machine-readable beta release-review artifact payload."""
    return {
        "schema_version": 1,
        "runner": "qa.beta_release_review",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "report": record.to_dict(),
    }


def write_beta_release_review_artifact(
    record: BetaReleaseReviewRecord,
    *,
    artifact_path: Path | None = None,
) -> Path:
    """Persist one beta release-review artifact."""
    resolved_artifact_path = artifact_path or beta_release_review_artifact_path()
    resolved_artifact_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_artifact_path.write_text(
        json.dumps(beta_release_review_artifact_payload(record), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return resolved_artifact_path


def load_beta_release_review_artifact(
    artifact_path: Path | None = None,
) -> tuple[Path, dict[str, Any] | None, str | None]:
    """Load the current beta release-review artifact plus any parse error."""
    resolved_artifact_path = artifact_path or beta_release_review_artifact_path()
    if not resolved_artifact_path.exists():
        return resolved_artifact_path, None, None
    try:
        payload = json.loads(resolved_artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return resolved_artifact_path, None, f"{type(exc).__name__}: {exc}"
    if not isinstance(payload, dict):
        return resolved_artifact_path, None, "ValueError: beta release review artifact must be a JSON object."
    return resolved_artifact_path, payload, None


def beta_release_review_status(
    artifact_payload: dict[str, Any] | None,
    artifact_error: str | None,
) -> tuple[str, int | None, int | None, bool, str | None]:
    """Return one short artifact status, progress counts, completion, and candidate."""
    if artifact_error is not None:
        return "invalid", None, None, False, None
    if artifact_payload is None:
        return "missing", None, None, False, None
    report = artifact_payload.get("report")
    if not isinstance(report, dict):
        return "invalid", None, None, False, None
    completed_checks = report.get("completed_checks")
    total_checks = report.get("total_checks")
    all_completed = bool(report.get("all_completed", False))
    manual_checklist_artifact_completed = bool(report.get("manual_checklist_artifact_completed", False))
    candidate_profile = str(report.get("candidate_profile", "") or "").strip() or None
    if not isinstance(completed_checks, int) or not isinstance(total_checks, int):
        return "invalid", None, None, False, candidate_profile
    if total_checks <= 0:
        return "invalid", completed_checks, total_checks, False, candidate_profile
    if (
        all_completed
        and manual_checklist_artifact_completed
        and bool(report.get("manual_checklist_artifact_fresh")) is True
        and completed_checks == total_checks
        and candidate_profile in _CANDIDATE_PROFILES
    ):
        return "complete", completed_checks, total_checks, True, candidate_profile
    return "incomplete", completed_checks, total_checks, False, candidate_profile


def beta_release_review_artifact_consistency(
    *,
    artifact_payload: dict[str, Any] | None,
    manual_checklist_artifact_payload: dict[str, Any] | None,
    manual_checklist_artifact_path: Path | None,
    manual_checklist_artifact_error: str | None,
    expected_candidate: str | None = None,
) -> tuple[bool | None, str | None]:
    """Return whether one release-review artifact still matches the latest manual evidence."""
    if artifact_payload is None:
        return None, None
    report = dict(artifact_payload.get("report", {}) or {})
    recorded_manual_sha256 = str(report.get("manual_checklist_artifact_sha256", "") or "").strip()
    latest_manual_sha256 = _artifact_sha256(
        manual_checklist_artifact_path,
        artifact_error=manual_checklist_artifact_error,
    )
    if not recorded_manual_sha256:
        return False, "recorded manual checklist snapshot is missing"
    if not latest_manual_sha256:
        return False, "latest manual checklist artifact is missing or unreadable"
    if recorded_manual_sha256 != latest_manual_sha256:
        return False, "recorded manual checklist artifact fingerprint no longer matches the latest artifact"
    recorded_manual_created_at = str(report.get("manual_checklist_artifact_created_at", "") or "").strip()
    latest_manual_created_at = str(_artifact_created_at(manual_checklist_artifact_payload) or "").strip()
    if recorded_manual_created_at and latest_manual_created_at and recorded_manual_created_at != latest_manual_created_at:
        return False, "recorded manual checklist artifact snapshot no longer matches the latest artifact"
    recorded_candidate = str(report.get("candidate_profile", "") or "").strip()
    if expected_candidate and recorded_candidate and recorded_candidate != expected_candidate:
        return False, f"recorded beta release review candidate {recorded_candidate} differs from expected candidate {expected_candidate}"
    return True, None


def main(argv: list[str] | None = None) -> int:
    """Inspect or update the beta release-review artifact."""
    parser = argparse.ArgumentParser(description="Inspect or update the QA beta release-review artifact.")
    parser.add_argument("--candidate-profile", choices=list(_CANDIDATE_PROFILES))
    parser.add_argument("--latency-reviewed", action="store_true", help="Mark latency review as completed.")
    parser.add_argument("--cost-reviewed", action="store_true", help="Mark cost review as completed.")
    parser.add_argument("--operator-signoff", action="store_true", help="Mark operator sign-off as completed.")
    parser.add_argument("--product-approval", action="store_true", help="Mark product approval as completed.")
    parser.add_argument("--all-complete", action="store_true", help="Mark every release-review check as completed.")
    parser.add_argument("--reset", action="store_true", help="Ignore any existing artifact state before applying updates.")
    parser.add_argument("--notes", default="", help="Optional short note stored in the artifact.")
    parser.add_argument("--write-artifact", action="store_true", help="Write the review artifact to tmp/qa.")
    parser.add_argument("--json", action="store_true", help="Print the full artifact JSON.")
    args = parser.parse_args(argv)

    artifact_path, existing_payload, existing_error = load_beta_release_review_artifact()
    if existing_error is not None:
        raise SystemExit(existing_error)
    record = build_beta_release_review_record(
        candidate_profile=args.candidate_profile,
        latency_review_completed=bool(args.latency_reviewed),
        cost_review_completed=bool(args.cost_reviewed),
        operator_signoff_completed=bool(args.operator_signoff),
        product_approval_completed=bool(args.product_approval),
        all_completed=bool(args.all_complete),
        notes=str(args.notes or "").strip() or None,
        existing_payload=existing_payload,
        reset=bool(args.reset),
    )
    resolved_artifact_path: Path | None = None
    if args.write_artifact:
        resolved_artifact_path = write_beta_release_review_artifact(record, artifact_path=artifact_path)

    if args.json:
        print(json.dumps(beta_release_review_artifact_payload(record), indent=2, sort_keys=True))
    else:
        print(format_beta_release_review_record(record))
        if resolved_artifact_path is not None:
            print(f"artifact: {resolved_artifact_path}")
    return 0 if record.all_completed else 1


def _existing_check_states(existing_payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    report = dict((existing_payload or {}).get("report", {}) or {})
    checks = report.get("checks")
    if not isinstance(checks, dict):
        return {}
    existing_states: dict[str, dict[str, Any]] = {}
    for check_id, check_state in checks.items():
        if not isinstance(check_id, str) or not isinstance(check_state, dict):
            continue
        existing_states[check_id] = dict(check_state)
    return existing_states


def _artifact_created_at(artifact_payload: dict[str, Any] | None) -> str | None:
    created_at = str((artifact_payload or {}).get("created_at", "") or "").strip()
    return created_at or None


def _artifact_freshness(artifact_payload: dict[str, Any] | None) -> tuple[float | None, bool | None, str | None]:
    if artifact_payload is None:
        return None, None, None
    created_at = str(artifact_payload.get("created_at", "") or "").strip()
    if not created_at:
        return None, False, "artifact is missing created_at"
    try:
        parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as exc:
        return None, False, f"artifact created_at is invalid: {exc}"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    age_hours = round((_artifact_now() - parsed.astimezone(timezone.utc)).total_seconds() / 3600.0, 3)
    return age_hours, age_hours <= 24.0, None


def _artifact_sha256(artifact_path: Path | None, *, artifact_error: str | None) -> str | None:
    if artifact_path is None or artifact_error is not None or not artifact_path.exists():
        return None
    try:
        return hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    except OSError:
        return None


def _format_ratio(completed_checks: int | None, total_checks: int | None) -> str:
    if completed_checks is None or total_checks is None:
        return ""
    return f"({completed_checks}/{total_checks})"


def _format_freshness(fresh: bool | None, age_hours: float | None) -> str:
    if fresh is None:
        return ""
    if age_hours is None:
        return f"; fresh={'yes' if fresh else 'no'}"
    return f"; fresh={'yes' if fresh else 'no'} ({age_hours}h)"


def _artifact_now() -> datetime:
    return datetime.now(timezone.utc)


if __name__ == "__main__":
    raise SystemExit(main())
