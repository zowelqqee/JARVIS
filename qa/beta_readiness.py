"""Offline beta-readiness decision helpers for QA rollout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from qa.answer_config import load_answer_backend_config
from qa.beta_release_review import (
    beta_release_review_artifact_consistency,
    beta_release_review_pending_checks,
    beta_release_review_suggested_args,
    beta_release_review_status,
    load_beta_release_review_artifact,
)
from qa.manual_beta_checklist import (
    manual_beta_checklist_detail_lines,
    manual_beta_checklist_guide_command,
    load_manual_beta_checklist_artifact,
    manual_beta_checklist_pending_item_details,
    manual_beta_checklist_pending_items,
    manual_beta_checklist_suggested_args,
    manual_beta_checklist_status,
    manual_beta_checklist_verification_doc,
)
from qa.rollout_profiles import (
    beta_release_review_artifact_path,
    beta_readiness_artifact_path,
    live_smoke_artifact_path_for_candidate,
    manual_beta_checklist_artifact_path,
    resolve_rollout_candidate_settings,
    rollout_stability_artifact_path_for_candidate,
)

_ARTIFACT_MAX_AGE_HOURS = 24.0
_CANDIDATE_PROFILES = ("llm_env", "llm_env_strict")
_STAGE = "alpha_opt_in"
_DEFAULT_PATH = "deterministic"


@dataclass(slots=True, frozen=True)
class BetaCandidateState:
    """Offline readiness state for one beta-candidate profile."""

    candidate_profile: str
    api_key_present: bool
    fallback_enabled: bool
    open_domain_enabled: bool
    open_domain_verified: bool
    smoke_artifact_path: str
    smoke_artifact_status: str
    smoke_artifact_created_at: str | None
    smoke_artifact_sha256: str | None
    smoke_artifact_fresh: bool | None
    smoke_artifact_match: bool | None
    smoke_artifact_age_hours: float | None
    smoke_artifact_reason: str | None
    stability_artifact_path: str
    stability_artifact_status: str
    stability_artifact_created_at: str | None
    stability_artifact_sha256: str | None
    stability_artifact_fresh: bool | None
    stability_artifact_age_hours: float | None
    stability_artifact_reason: str | None
    stability_gate_passes: int | None
    stability_runs_requested: int | None
    blockers: list[str] = field(default_factory=list)

    @property
    def technical_ready(self) -> bool:
        return not self.blockers

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_profile": self.candidate_profile,
            "api_key_present": self.api_key_present,
            "fallback_enabled": self.fallback_enabled,
            "open_domain_enabled": self.open_domain_enabled,
            "open_domain_verified": self.open_domain_verified,
            "technical_ready": self.technical_ready,
            "smoke_artifact_path": self.smoke_artifact_path,
            "smoke_artifact_status": self.smoke_artifact_status,
            "smoke_artifact_created_at": self.smoke_artifact_created_at,
            "smoke_artifact_sha256": self.smoke_artifact_sha256,
            "smoke_artifact_fresh": self.smoke_artifact_fresh,
            "smoke_artifact_match": self.smoke_artifact_match,
            "smoke_artifact_age_hours": self.smoke_artifact_age_hours,
            "smoke_artifact_reason": self.smoke_artifact_reason,
            "stability_artifact_path": self.stability_artifact_path,
            "stability_artifact_status": self.stability_artifact_status,
            "stability_artifact_created_at": self.stability_artifact_created_at,
            "stability_artifact_sha256": self.stability_artifact_sha256,
            "stability_artifact_fresh": self.stability_artifact_fresh,
            "stability_artifact_age_hours": self.stability_artifact_age_hours,
            "stability_artifact_reason": self.stability_artifact_reason,
            "stability_gate_passes": self.stability_gate_passes,
            "stability_runs_requested": self.stability_runs_requested,
            "blockers": list(self.blockers),
        }


@dataclass(slots=True, frozen=True)
class BetaReadinessRecord:
    """Machine-readable beta-readiness decision record."""

    stage: str
    default_path: str
    recommended_candidate: str | None
    chosen_candidate: str | None
    candidate_selection_source: str
    technical_ready_candidates: list[str]
    manual_checklist_completed: bool
    manual_checklist_artifact_status: str
    manual_checklist_artifact_completed: bool
    manual_checklist_items_passed: int | None
    manual_checklist_items_total: int | None
    manual_checklist_artifact_age_hours: float | None
    manual_checklist_artifact_fresh: bool | None
    manual_checklist_artifact_reason: str | None
    manual_checklist_pending_items: list[str]
    manual_checklist_pending_item_details: list[dict[str, str]]
    manual_checklist_command: str
    manual_checklist_guide_command: str
    manual_checklist_verification_doc: str
    manual_checklist_artifact_created_at: str | None
    manual_checklist_artifact_sha256: str | None
    release_review_artifact_status: str
    release_review_artifact_completed: bool
    release_review_artifact_candidate: str | None
    release_review_checks_completed: int | None
    release_review_checks_total: int | None
    release_review_artifact_age_hours: float | None
    release_review_artifact_fresh: bool | None
    release_review_artifact_reason: str | None
    release_review_artifact_consistent: bool | None
    release_review_artifact_consistency_reason: str | None
    release_review_pending_checks: list[str]
    release_review_command: str | None
    release_review_artifact_created_at: str | None
    release_review_artifact_sha256: str | None
    latency_review_completed: bool
    cost_review_completed: bool
    operator_signoff_completed: bool
    product_approval_completed: bool
    next_step_kind: str
    next_step_reason: str
    next_step_command: str | None
    blockers: list[str] = field(default_factory=list)
    candidate_states: list[BetaCandidateState] = field(default_factory=list)
    notes: str | None = None

    @property
    def beta_ready(self) -> bool:
        return not self.blockers

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "default_path": self.default_path,
            "recommended_candidate": self.recommended_candidate,
            "chosen_candidate": self.chosen_candidate,
            "candidate_selection_source": self.candidate_selection_source,
            "technical_ready_candidates": list(self.technical_ready_candidates),
            "manual_checklist_completed": self.manual_checklist_completed,
            "manual_checklist_artifact_status": self.manual_checklist_artifact_status,
            "manual_checklist_artifact_completed": self.manual_checklist_artifact_completed,
            "manual_checklist_items_passed": self.manual_checklist_items_passed,
            "manual_checklist_items_total": self.manual_checklist_items_total,
            "manual_checklist_artifact_age_hours": self.manual_checklist_artifact_age_hours,
            "manual_checklist_artifact_fresh": self.manual_checklist_artifact_fresh,
            "manual_checklist_artifact_reason": self.manual_checklist_artifact_reason or "",
            "manual_checklist_pending_items": list(self.manual_checklist_pending_items),
            "manual_checklist_pending_item_details": list(self.manual_checklist_pending_item_details),
            "manual_checklist_command": self.manual_checklist_command,
            "manual_checklist_guide_command": self.manual_checklist_guide_command,
            "manual_checklist_verification_doc": self.manual_checklist_verification_doc,
            "manual_checklist_artifact_created_at": self.manual_checklist_artifact_created_at,
            "manual_checklist_artifact_sha256": self.manual_checklist_artifact_sha256,
            "release_review_artifact_status": self.release_review_artifact_status,
            "release_review_artifact_completed": self.release_review_artifact_completed,
            "release_review_artifact_candidate": self.release_review_artifact_candidate or "",
            "release_review_checks_completed": self.release_review_checks_completed,
            "release_review_checks_total": self.release_review_checks_total,
            "release_review_artifact_age_hours": self.release_review_artifact_age_hours,
            "release_review_artifact_fresh": self.release_review_artifact_fresh,
            "release_review_artifact_reason": self.release_review_artifact_reason or "",
            "release_review_artifact_consistent": self.release_review_artifact_consistent,
            "release_review_artifact_consistency_reason": self.release_review_artifact_consistency_reason or "",
            "release_review_pending_checks": list(self.release_review_pending_checks),
            "release_review_command": self.release_review_command,
            "release_review_artifact_created_at": self.release_review_artifact_created_at,
            "release_review_artifact_sha256": self.release_review_artifact_sha256,
            "latency_review_completed": self.latency_review_completed,
            "cost_review_completed": self.cost_review_completed,
            "operator_signoff_completed": self.operator_signoff_completed,
            "product_approval_completed": self.product_approval_completed,
            "next_step_kind": self.next_step_kind,
            "next_step_reason": self.next_step_reason,
            "next_step_command": self.next_step_command or "",
            "beta_ready": self.beta_ready,
            "blockers": list(self.blockers),
            "candidate_states": {
                candidate_state.candidate_profile: candidate_state.to_dict()
                for candidate_state in self.candidate_states
            },
            "notes": self.notes or "",
        }


def build_beta_readiness_record(
    *,
    candidate_profile: str | None = None,
    notes: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> BetaReadinessRecord:
    """Build an offline beta-readiness record from the latest rollout artifacts."""
    chosen_candidate = str(candidate_profile or "").strip() or None
    if chosen_candidate is not None and chosen_candidate not in _CANDIDATE_PROFILES:
        raise ValueError(f"Unsupported beta candidate profile: {candidate_profile!r}.")
    env = dict(os.environ if environ is None else environ)
    candidate_states = [build_beta_candidate_state(candidate, environ=env) for candidate in _CANDIDATE_PROFILES]
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
    manual_checklist_pending_item_ids = manual_beta_checklist_pending_items(
        manual_artifact_payload,
        manual_artifact_error,
    )
    manual_checklist_pending_item_detail_records = manual_beta_checklist_pending_item_details(
        manual_artifact_payload,
        manual_artifact_error,
    )
    (
        release_review_artifact_path_value,
        release_review_artifact_payload,
        release_review_artifact_error,
    ) = load_beta_release_review_artifact(beta_release_review_artifact_path())
    (
        release_review_artifact_status,
        release_review_checks_completed,
        release_review_checks_total,
        release_review_artifact_completed,
        release_review_artifact_candidate,
    ) = beta_release_review_status(release_review_artifact_payload, release_review_artifact_error)
    (
        release_review_artifact_age_hours,
        release_review_artifact_fresh,
        release_review_artifact_reason,
    ) = _artifact_freshness(release_review_artifact_payload)
    release_review_pending_check_ids = beta_release_review_pending_checks(
        release_review_artifact_payload,
        release_review_artifact_error,
    )
    effective_latency_review_completed = _beta_release_review_check_completed(
        release_review_artifact_payload, "latency_review"
    )
    effective_cost_review_completed = _beta_release_review_check_completed(release_review_artifact_payload, "cost_review")
    effective_operator_signoff_completed = _beta_release_review_check_completed(
        release_review_artifact_payload, "operator_signoff"
    )
    effective_product_approval_completed = _beta_release_review_check_completed(
        release_review_artifact_payload, "product_approval"
    )
    effective_manual_checklist_completed = bool(
        manual_checklist_artifact_completed and manual_checklist_artifact_fresh is True
    )
    technical_ready_candidates = [
        candidate_state.candidate_profile for candidate_state in candidate_states if candidate_state.technical_ready
    ]
    recommended_candidate = _recommended_candidate(candidate_states)
    effective_candidate = chosen_candidate or release_review_artifact_candidate or recommended_candidate
    candidate_selection_source = _candidate_selection_source(
        explicit_candidate=chosen_candidate,
        release_review_candidate=release_review_artifact_candidate,
        recommended_candidate=recommended_candidate,
    )
    manual_checklist_command = _manual_beta_checklist_command(
        manual_checklist_pending_item_ids,
        force_full_rerun=manual_checklist_artifact_fresh is False,
    )
    release_review_artifact_consistent, release_review_artifact_consistency_reason = (
        beta_release_review_artifact_consistency(
            artifact_payload=release_review_artifact_payload,
            manual_checklist_artifact_payload=manual_artifact_payload,
            manual_checklist_artifact_path=manual_artifact_path,
            manual_checklist_artifact_error=manual_artifact_error,
            expected_candidate=chosen_candidate or None,
        )
    )
    release_review_command = _beta_release_review_command(
        candidate_profile=effective_candidate or recommended_candidate,
        pending_check_ids=release_review_pending_check_ids,
        force_full_rerun=release_review_artifact_fresh is False or release_review_artifact_consistent is False,
    )
    blockers: list[str] = []
    if not technical_ready_candidates:
        blockers.append("no candidate profile has fresh green smoke + stability evidence")
    if effective_candidate is None:
        blockers.append("beta candidate profile is not selected")
    else:
        selected_state = next(
            (candidate_state for candidate_state in candidate_states if candidate_state.candidate_profile == effective_candidate),
            None,
        )
        if selected_state is None or not selected_state.technical_ready:
            blockers.append(f"selected candidate {effective_candidate} is not technically ready")
    if not effective_manual_checklist_completed:
        blockers.append("manual verification checklist is not completed")
    if not manual_checklist_artifact_completed:
        blockers.append("manual beta checklist artifact is missing or incomplete")
    if manual_artifact_payload is not None and manual_artifact_error is None and manual_checklist_artifact_fresh is not True:
        blockers.append("manual beta checklist artifact is stale")
    if not release_review_artifact_completed:
        blockers.append("beta release review artifact is missing or incomplete")
    if (
        release_review_artifact_payload is not None
        and release_review_artifact_error is None
        and release_review_artifact_fresh is not True
    ):
        blockers.append("beta release review artifact is stale")
    if release_review_artifact_consistent is False:
        blockers.append(
            "beta release review artifact is stale against the latest manual checklist evidence"
        )
    if (
        effective_candidate is not None
        and release_review_artifact_candidate is not None
        and effective_candidate != release_review_artifact_candidate
    ):
        blockers.append(
            f"selected candidate {effective_candidate} does not match beta release review artifact candidate "
            f"{release_review_artifact_candidate}"
        )
    if not effective_latency_review_completed:
        blockers.append("latency review is not completed")
    if not effective_cost_review_completed:
        blockers.append("cost review is not completed")
    if not effective_operator_signoff_completed:
        blockers.append("operator sign-off is not completed")
    if not effective_product_approval_completed:
        blockers.append("product approval for beta_question_default is missing")
    selected_candidate_technical_ready = bool(
        effective_candidate
        and any(
            candidate_state.candidate_profile == effective_candidate and candidate_state.technical_ready
            for candidate_state in candidate_states
        )
    )
    next_step_kind, next_step_reason, next_step_command = _beta_readiness_next_step(
        technical_ready_candidates=technical_ready_candidates,
        effective_candidate=effective_candidate,
        selected_candidate_technical_ready=selected_candidate_technical_ready,
        effective_manual_checklist_completed=effective_manual_checklist_completed,
        release_review_artifact_completed=release_review_artifact_completed,
        release_review_artifact_candidate=release_review_artifact_candidate,
        release_review_artifact_fresh=release_review_artifact_fresh,
        release_review_artifact_consistent=release_review_artifact_consistent,
        manual_checklist_command=manual_checklist_command,
        release_review_command=release_review_command,
    )
    return BetaReadinessRecord(
        stage=_STAGE,
        default_path=_DEFAULT_PATH,
        recommended_candidate=recommended_candidate,
        chosen_candidate=effective_candidate,
        candidate_selection_source=candidate_selection_source,
        technical_ready_candidates=technical_ready_candidates,
        manual_checklist_completed=effective_manual_checklist_completed,
        manual_checklist_artifact_status=manual_checklist_artifact_status,
        manual_checklist_artifact_completed=manual_checklist_artifact_completed,
        manual_checklist_items_passed=manual_checklist_items_passed,
        manual_checklist_items_total=manual_checklist_items_total,
        manual_checklist_artifact_age_hours=manual_checklist_artifact_age_hours,
        manual_checklist_artifact_fresh=manual_checklist_artifact_fresh,
        manual_checklist_artifact_reason=manual_checklist_artifact_reason,
        manual_checklist_pending_items=manual_checklist_pending_item_ids,
        manual_checklist_pending_item_details=manual_checklist_pending_item_detail_records,
        manual_checklist_command=manual_checklist_command,
        manual_checklist_guide_command=manual_beta_checklist_guide_command(),
        manual_checklist_verification_doc=manual_beta_checklist_verification_doc(),
        manual_checklist_artifact_created_at=_artifact_created_at(manual_artifact_payload),
        manual_checklist_artifact_sha256=_artifact_sha256(manual_artifact_path, artifact_error=manual_artifact_error),
        release_review_artifact_status=release_review_artifact_status,
        release_review_artifact_completed=release_review_artifact_completed,
        release_review_artifact_candidate=release_review_artifact_candidate,
        release_review_checks_completed=release_review_checks_completed,
        release_review_checks_total=release_review_checks_total,
        release_review_artifact_age_hours=release_review_artifact_age_hours,
        release_review_artifact_fresh=release_review_artifact_fresh,
        release_review_artifact_reason=release_review_artifact_reason,
        release_review_artifact_consistent=release_review_artifact_consistent,
        release_review_artifact_consistency_reason=release_review_artifact_consistency_reason,
        release_review_pending_checks=release_review_pending_check_ids,
        release_review_command=release_review_command,
        release_review_artifact_created_at=_artifact_created_at(release_review_artifact_payload),
        release_review_artifact_sha256=_artifact_sha256(
            release_review_artifact_path_value,
            artifact_error=release_review_artifact_error,
        ),
        latency_review_completed=effective_latency_review_completed,
        cost_review_completed=effective_cost_review_completed,
        operator_signoff_completed=effective_operator_signoff_completed,
        product_approval_completed=effective_product_approval_completed,
        next_step_kind=next_step_kind,
        next_step_reason=next_step_reason,
        next_step_command=next_step_command,
        blockers=blockers,
        candidate_states=candidate_states,
        notes=str(notes or "").strip() or None,
    )


def build_beta_candidate_state(candidate_profile: str, *, environ: Mapping[str, str] | None = None) -> BetaCandidateState:
    """Build one candidate's current offline beta-readiness state."""
    env = dict(os.environ if environ is None else environ)
    config = load_answer_backend_config(environ=env)
    settings = resolve_rollout_candidate_settings(candidate_profile, environ=env)
    provider = str(getattr(config.llm.provider, "value", config.llm.provider) or "").strip()
    api_key_present = bool(env.get(settings.api_key_env, "").strip())

    smoke_artifact_path = live_smoke_artifact_path_for_candidate(candidate_profile)
    smoke_artifact_payload, smoke_artifact_error = _load_json_artifact(smoke_artifact_path)
    smoke_artifact_status = _live_smoke_artifact_status(
        artifact_payload=smoke_artifact_payload,
        artifact_error=smoke_artifact_error,
    )
    smoke_artifact_age_hours, smoke_artifact_fresh, smoke_artifact_reason = _artifact_freshness(smoke_artifact_payload)
    smoke_artifact_match, smoke_artifact_match_reason = _live_smoke_artifact_profile_match(
        artifact_payload=smoke_artifact_payload,
        provider=provider,
        model=settings.model,
        strict_mode=settings.strict_mode,
        fallback_enabled=settings.fallback_enabled,
        open_domain_enabled=settings.open_domain_enabled,
    )

    stability_artifact_path = rollout_stability_artifact_path_for_candidate(candidate_profile)
    stability_artifact_payload, stability_artifact_error = _load_json_artifact(stability_artifact_path)
    (
        stability_artifact_status,
        stability_gate_passes,
        stability_runs_requested,
    ) = _rollout_stability_artifact_status(
        artifact_payload=stability_artifact_payload,
        artifact_error=stability_artifact_error,
    )
    (
        stability_artifact_age_hours,
        stability_artifact_fresh,
        stability_artifact_reason,
    ) = _artifact_freshness(stability_artifact_payload)

    open_domain_verified = bool((smoke_artifact_payload or {}).get("open_domain_verified"))
    blockers: list[str] = []
    if not api_key_present:
        blockers.append(f"{settings.api_key_env} is missing")
    if not settings.open_domain_enabled:
        blockers.append("open-domain question answering is disabled")
    if smoke_artifact_error is not None:
        blockers.append("live smoke artifact is invalid")
    elif smoke_artifact_payload is None:
        blockers.append("live smoke artifact is missing")
    elif not bool(smoke_artifact_payload.get("success")):
        blockers.append("live smoke artifact is not green")
    if smoke_artifact_payload is not None and smoke_artifact_error is None and smoke_artifact_fresh is not True:
        blockers.append("live smoke artifact is stale")
    if smoke_artifact_payload is not None and smoke_artifact_error is None and smoke_artifact_match is False:
        blockers.append("live smoke artifact does not match candidate provider/model/strict/fallback/open-domain config")
    if settings.open_domain_enabled and not open_domain_verified:
        blockers.append("open-domain live verification is missing")
    if stability_artifact_error is not None:
        blockers.append("rollout stability artifact is invalid")
    elif stability_artifact_payload is None:
        blockers.append("rollout stability artifact is missing")
    elif stability_artifact_status != "green":
        blockers.append("rollout stability artifact is not green")
    if stability_artifact_payload is not None and stability_artifact_error is None and stability_artifact_fresh is not True:
        blockers.append("rollout stability artifact is stale")

    return BetaCandidateState(
        candidate_profile=candidate_profile,
        api_key_present=api_key_present,
        fallback_enabled=settings.fallback_enabled,
        open_domain_enabled=settings.open_domain_enabled,
        open_domain_verified=open_domain_verified,
        smoke_artifact_path=str(smoke_artifact_path),
        smoke_artifact_status=smoke_artifact_status,
        smoke_artifact_created_at=_artifact_created_at(smoke_artifact_payload),
        smoke_artifact_sha256=_artifact_sha256(smoke_artifact_path, artifact_error=smoke_artifact_error),
        smoke_artifact_fresh=smoke_artifact_fresh,
        smoke_artifact_match=smoke_artifact_match,
        smoke_artifact_age_hours=smoke_artifact_age_hours,
        smoke_artifact_reason=smoke_artifact_reason or smoke_artifact_match_reason,
        stability_artifact_path=str(stability_artifact_path),
        stability_artifact_status=stability_artifact_status,
        stability_artifact_created_at=_artifact_created_at(stability_artifact_payload),
        stability_artifact_sha256=_artifact_sha256(stability_artifact_path, artifact_error=stability_artifact_error),
        stability_artifact_fresh=stability_artifact_fresh,
        stability_artifact_age_hours=stability_artifact_age_hours,
        stability_artifact_reason=stability_artifact_reason or stability_artifact_error,
        stability_gate_passes=stability_gate_passes,
        stability_runs_requested=stability_runs_requested,
        blockers=blockers,
    )


def format_beta_readiness_record(record: BetaReadinessRecord) -> str:
    """Render one operator-friendly beta-readiness summary."""
    lines = [
        "JARVIS QA Beta Readiness",
        f"stage: {record.stage}",
        f"default path: {record.default_path}",
        f"recommended candidate: {record.recommended_candidate or 'none'}",
        f"chosen candidate: {record.chosen_candidate or 'none'}",
        f"candidate selection: {record.candidate_selection_source}",
        f"technical ready candidates: {', '.join(record.technical_ready_candidates) if record.technical_ready_candidates else 'none'}",
        f"manual checklist: {'yes' if record.manual_checklist_completed else 'no'}",
        "manual checklist artifact: "
        f"{record.manual_checklist_artifact_status}"
        f"{_format_ratio(record.manual_checklist_items_passed, record.manual_checklist_items_total)}"
        f"{_format_freshness(record.manual_checklist_artifact_fresh, record.manual_checklist_artifact_age_hours)}",
        f"manual checklist pending items: {', '.join(record.manual_checklist_pending_items) if record.manual_checklist_pending_items else 'none'}",
        f"manual checklist command: {record.manual_checklist_command}",
        f"manual checklist guide command: {record.manual_checklist_guide_command}",
        f"manual checklist verification doc: {record.manual_checklist_verification_doc}",
        "release review artifact: "
        f"{record.release_review_artifact_status}"
        f"{_format_ratio(record.release_review_checks_completed, record.release_review_checks_total)}"
        f"{_format_candidate(record.release_review_artifact_candidate)}"
        f"{_format_freshness(record.release_review_artifact_fresh, record.release_review_artifact_age_hours)}"
        f"{_format_consistency(record.release_review_artifact_consistent)}",
        f"release review pending checks: {', '.join(record.release_review_pending_checks) if record.release_review_pending_checks else 'none'}",
        f"release review command: {record.release_review_command or 'n/a'}",
        f"latency review: {'yes' if record.latency_review_completed else 'no'}",
        f"cost review: {'yes' if record.cost_review_completed else 'no'}",
        f"operator sign-off: {'yes' if record.operator_signoff_completed else 'no'}",
        f"product approval: {'yes' if record.product_approval_completed else 'no'}",
        f"next step: {record.next_step_kind}",
        f"next step reason: {record.next_step_reason}",
        f"next step command: {record.next_step_command or 'n/a'}",
        f"beta_question_default ready: {'yes' if record.beta_ready else 'no'}",
    ]
    if record.manual_checklist_pending_item_details:
        lines.extend(
            manual_beta_checklist_detail_lines(
                record.manual_checklist_pending_item_details,
                heading="manual checklist scenario guide:",
            )
        )
    else:
        lines.append("manual checklist scenario guide: none")
    if record.blockers:
        lines.append("blockers:")
        for blocker in record.blockers:
            lines.append(f"  - {blocker}")
    else:
        lines.append("blockers: none")
    lines.append("candidate states:")
    for candidate_state in record.candidate_states:
        lines.append(
            "  - "
            f"{candidate_state.candidate_profile}: "
            f"technical-ready={'yes' if candidate_state.technical_ready else 'no'}; "
            f"smoke={candidate_state.smoke_artifact_status}; "
            f"stability={candidate_state.stability_artifact_status}"
            f"{_format_ratio(candidate_state.stability_gate_passes, candidate_state.stability_runs_requested)}; "
            f"fallback={'on' if candidate_state.fallback_enabled else 'off'}"
        )
    if record.release_review_artifact_consistency_reason:
        lines.append(f"release review consistency reason: {record.release_review_artifact_consistency_reason}")
    return "\n".join(lines)


def beta_readiness_artifact_payload(record: BetaReadinessRecord) -> dict[str, Any]:
    """Return the machine-readable beta-readiness artifact payload."""
    return {
        "schema_version": 1,
        "runner": "qa.beta_readiness",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "report": record.to_dict(),
    }


def write_beta_readiness_artifact(
    record: BetaReadinessRecord,
    *,
    artifact_path: Path | None = None,
) -> Path:
    """Persist one beta-readiness artifact for operator review."""
    if not record.beta_ready:
        raise ValueError("beta readiness record is blocked; refusing to write final artifact")
    if record.candidate_selection_source != "explicit":
        raise ValueError("beta readiness record requires explicit candidate selection before final artifact write")
    resolved_artifact_path = artifact_path or beta_readiness_artifact_path()
    resolved_artifact_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_artifact_path.write_text(
        json.dumps(beta_readiness_artifact_payload(record), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return resolved_artifact_path


def main(argv: list[str] | None = None) -> int:
    """Build and optionally persist an offline beta-readiness record."""
    parser = argparse.ArgumentParser(description="Build an offline QA beta-readiness decision record.")
    parser.add_argument("--candidate-profile", choices=list(_CANDIDATE_PROFILES))
    parser.add_argument("--notes", default="", help="Optional short operator note stored in the artifact.")
    parser.add_argument("--write-artifact", action="store_true", help="Write the beta-readiness artifact to tmp/qa.")
    parser.add_argument("--json", action="store_true", help="Print the full record as JSON.")
    args = parser.parse_args(argv)
    if args.write_artifact and not args.candidate_profile:
        parser.error("--write-artifact requires explicit --candidate-profile")

    record = build_beta_readiness_record(
        candidate_profile=args.candidate_profile,
        notes=str(args.notes or "").strip() or None,
    )
    if args.write_artifact:
        if not record.beta_ready:
            print(format_beta_readiness_record(record))
            raise SystemExit("beta readiness is still blocked; refusing to write final artifact")
        artifact_path = write_beta_readiness_artifact(record)
    else:
        artifact_path = None

    if args.json:
        print(json.dumps(beta_readiness_artifact_payload(record), indent=2, sort_keys=True))
    else:
        print(format_beta_readiness_record(record))
        if artifact_path is not None:
            print(f"artifact: {artifact_path}")
    return 0 if record.beta_ready else 1


def _recommended_candidate(candidate_states: list[BetaCandidateState]) -> str | None:
    for preferred_candidate in ("llm_env_strict", "llm_env"):
        for candidate_state in candidate_states:
            if candidate_state.candidate_profile == preferred_candidate and candidate_state.technical_ready:
                return preferred_candidate
    return None


def _candidate_selection_source(
    *,
    explicit_candidate: str | None,
    release_review_candidate: str | None,
    recommended_candidate: str | None,
) -> str:
    if explicit_candidate:
        return "explicit"
    if release_review_candidate:
        return "release_review_artifact"
    if recommended_candidate:
        return "recommended_candidate"
    return "none"


def _manual_beta_checklist_command(
    pending_item_ids: list[str],
    *,
    force_full_rerun: bool,
) -> str:
    args = manual_beta_checklist_suggested_args(
        pending_item_ids,
        force_full_rerun=force_full_rerun,
    )
    return f"python3 -m qa.manual_beta_checklist {args} --write-artifact"


def _beta_release_review_command(
    *,
    candidate_profile: str | None,
    pending_check_ids: list[str],
    force_full_rerun: bool,
) -> str | None:
    if not candidate_profile:
        return None
    args = beta_release_review_suggested_args(
        pending_check_ids,
        force_full_rerun=force_full_rerun,
    )
    return f"python3 -m qa.beta_release_review --candidate-profile {candidate_profile} {args} --write-artifact"


def _beta_readiness_write_command(candidate_profile: str | None) -> str | None:
    if not candidate_profile:
        return None
    return f"python3 -m qa.beta_readiness --candidate-profile {candidate_profile} --write-artifact"


def _beta_readiness_next_step(
    *,
    technical_ready_candidates: list[str],
    effective_candidate: str | None,
    selected_candidate_technical_ready: bool,
    effective_manual_checklist_completed: bool,
    release_review_artifact_completed: bool,
    release_review_artifact_candidate: str | None,
    release_review_artifact_fresh: bool | None,
    release_review_artifact_consistent: bool | None,
    manual_checklist_command: str,
    release_review_command: str | None,
) -> tuple[str, str, str | None]:
    if not technical_ready_candidates:
        return (
            "refresh_technical_rollout_evidence",
            "no candidate has fresh green smoke plus stability evidence",
            None,
        )
    if effective_candidate is None:
        return (
            "select_beta_candidate",
            "choose the beta candidate profile before recording final readiness",
            None,
        )
    if not selected_candidate_technical_ready:
        return (
            "candidate_not_ready",
            f"selected candidate {effective_candidate} is not technically ready on the latest evidence",
            None,
        )
    if not effective_manual_checklist_completed:
        return (
            "complete_manual_beta_checklist",
            "manual beta checklist evidence is missing, incomplete, or stale",
            manual_checklist_command,
        )
    if (
        not release_review_artifact_completed
        or release_review_artifact_fresh is not True
        or release_review_artifact_consistent is False
        or release_review_artifact_candidate != effective_candidate
    ):
        return (
            "record_beta_release_review",
            "beta release review evidence is missing, incomplete, stale, or tied to a different candidate/manual snapshot",
            release_review_command,
        )
    return (
        "write_beta_readiness_artifact",
        "supporting evidence is complete; record the consolidated beta readiness artifact",
        _beta_readiness_write_command(effective_candidate),
    )


def _beta_release_review_check_completed(
    artifact_payload: dict[str, object] | None,
    check_id: str,
) -> bool:
    report = dict((artifact_payload or {}).get("report", {}) or {})
    checks = dict(report.get("checks", {}) or {})
    check_state = dict(checks.get(check_id, {}) or {})
    return bool(check_state.get("completed", False))


def _load_json_artifact(artifact_path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not artifact_path.exists():
        return None, None
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if not isinstance(payload, dict):
        return None, "ValueError: artifact must be a JSON object."
    return payload, None


def _artifact_freshness(artifact_payload: dict[str, object] | None) -> tuple[float | None, bool | None, str | None]:
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
    return age_hours, age_hours <= _ARTIFACT_MAX_AGE_HOURS, None


def _artifact_created_at(artifact_payload: dict[str, object] | None) -> str | None:
    if artifact_payload is None:
        return None
    created_at = str(artifact_payload.get("created_at", "") or "").strip()
    return created_at or None


def _artifact_sha256(artifact_path: Path, *, artifact_error: str | None) -> str | None:
    if artifact_error is not None or not artifact_path.exists():
        return None
    try:
        return hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    except OSError:
        return None


def _live_smoke_artifact_profile_match(
    *,
    artifact_payload: dict[str, object] | None,
    provider: str,
    model: str,
    strict_mode: bool,
    fallback_enabled: bool,
    open_domain_enabled: bool,
) -> tuple[bool | None, str | None]:
    if artifact_payload is None:
        return None, None
    diagnostics = dict(artifact_payload.get("diagnostics", {}) or {})
    actual_provider = str(diagnostics.get("provider", "") or "").strip()
    actual_model = str(diagnostics.get("model", "") or "").strip()
    actual_strict_mode = bool(diagnostics.get("strict_mode", False))
    actual_fallback_enabled = bool(diagnostics.get("fallback_enabled", False))
    actual_open_domain_enabled = bool(diagnostics.get("open_domain_enabled", False))
    mismatches: list[str] = []
    if actual_provider != provider:
        mismatches.append(f"artifact provider {actual_provider or '<missing>'} != {provider or '<missing>'}")
    if actual_model != model:
        mismatches.append(f"artifact model {actual_model or '<missing>'} != {model or '<missing>'}")
    if actual_strict_mode is not strict_mode:
        mismatches.append("artifact strict-mode flag does not match current config")
    if actual_fallback_enabled is not fallback_enabled:
        mismatches.append("artifact fallback flag does not match current config")
    if actual_open_domain_enabled is not open_domain_enabled:
        mismatches.append("artifact open-domain flag does not match current config")
    return (not mismatches), "; ".join(mismatches) or None


def _live_smoke_artifact_status(
    *,
    artifact_payload: dict[str, object] | None,
    artifact_error: str | None,
) -> str:
    if artifact_error is not None:
        return "invalid"
    if artifact_payload is None:
        return "missing"
    if bool(artifact_payload.get("success")):
        return "green"
    return "failed"


def _rollout_stability_artifact_status(
    *,
    artifact_payload: dict[str, object] | None,
    artifact_error: str | None,
) -> tuple[str, int | None, int | None]:
    if artifact_error is not None:
        return "invalid", None, None
    if artifact_payload is None:
        return "missing", None, None
    report = artifact_payload.get("report")
    if not isinstance(report, dict):
        return "invalid", None, None
    gate_passes = report.get("gate_passes")
    runs_requested = report.get("runs_requested")
    if not isinstance(gate_passes, int) or not isinstance(runs_requested, int):
        return "invalid", None, None
    if runs_requested <= 0:
        return "invalid", gate_passes, runs_requested
    if gate_passes == runs_requested:
        return "green", gate_passes, runs_requested
    return "failed", gate_passes, runs_requested


def _format_ratio(gate_passes: int | None, runs_requested: int | None) -> str:
    if gate_passes is None or runs_requested is None:
        return ""
    return f"({gate_passes}/{runs_requested})"


def _format_candidate(candidate_profile: str | None) -> str:
    if not candidate_profile:
        return ""
    return f" for {candidate_profile}"


def _format_consistency(consistent: bool | None) -> str:
    if consistent is None:
        return ""
    return f"; consistent={'yes' if consistent else 'no'}"


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
