"""Shared rollout-profile helpers for QA live smoke and gate workflows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from qa.answer_config import load_answer_backend_config

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_LIVE_SMOKE_ARTIFACT = _REPO_ROOT / "tmp" / "qa" / "openai_live_smoke.json"
_PROFILE_LIVE_SMOKE_ARTIFACTS = {
    "llm_env": _REPO_ROOT / "tmp" / "qa" / "openai_live_smoke_llm_env.json",
    "llm_env_strict": _REPO_ROOT / "tmp" / "qa" / "openai_live_smoke_llm_env_strict.json",
}
_PROFILE_STABILITY_ARTIFACTS = {
    "llm_env": _REPO_ROOT / "tmp" / "qa" / "rollout_stability_llm_env.json",
    "llm_env_strict": _REPO_ROOT / "tmp" / "qa" / "rollout_stability_llm_env_strict.json",
}
_BETA_READINESS_ARTIFACT = _REPO_ROOT / "tmp" / "qa" / "beta_readiness.json"
_MANUAL_BETA_CHECKLIST_ARTIFACT = _REPO_ROOT / "tmp" / "qa" / "manual_beta_checklist.json"
_BETA_RELEASE_REVIEW_ARTIFACT = _REPO_ROOT / "tmp" / "qa" / "beta_release_review.json"


@dataclass(slots=True, frozen=True)
class RolloutCandidateSettings:
    """Resolved rollout settings for one candidate profile."""

    candidate_profile: str
    artifact_path: Path
    model: str
    strict_mode: bool
    fallback_enabled: bool
    open_domain_enabled: bool
    api_key_env: str
    smoke_command: str
    compare_command: str


def live_smoke_artifact_path_for_candidate(candidate_profile: str | None = None) -> Path:
    """Return the default artifact path for one rollout candidate profile."""
    return _PROFILE_LIVE_SMOKE_ARTIFACTS.get(str(candidate_profile or "").strip(), _DEFAULT_LIVE_SMOKE_ARTIFACT)


def rollout_smoke_command(candidate_profile: str | None = None) -> str:
    """Return the recommended live-smoke command for one rollout candidate."""
    candidate = str(candidate_profile or "").strip()
    if not candidate:
        return "scripts/run_openai_live_smoke.sh"
    return f"scripts/run_openai_live_smoke.sh {candidate}"


def rollout_stability_artifact_path_for_candidate(candidate_profile: str) -> Path:
    """Return the default stability-artifact path for one rollout candidate."""
    candidate = str(candidate_profile or "").strip()
    if candidate not in _PROFILE_STABILITY_ARTIFACTS:
        raise ValueError(f"Unsupported rollout candidate profile: {candidate_profile!r}.")
    return _PROFILE_STABILITY_ARTIFACTS[candidate]


def beta_readiness_artifact_path() -> Path:
    """Return the default artifact path for the offline beta-readiness decision record."""
    return _BETA_READINESS_ARTIFACT


def manual_beta_checklist_artifact_path() -> Path:
    """Return the default artifact path for the manual beta-checklist record."""
    return _MANUAL_BETA_CHECKLIST_ARTIFACT


def beta_release_review_artifact_path() -> Path:
    """Return the default artifact path for the beta release-review record."""
    return _BETA_RELEASE_REVIEW_ARTIFACT


def rollout_compare_command(candidate_profile: str) -> str:
    """Return the recommended comparative-gate command for one rollout candidate."""
    candidate = str(candidate_profile or "").strip()
    if not candidate:
        raise ValueError("candidate_profile must be non-empty.")
    return f"scripts/run_qa_rollout_gate.sh {candidate}"


def rollout_stability_command(candidate_profile: str, runs: int = 3) -> str:
    """Return the recommended repeated-gate stability command for one rollout candidate."""
    candidate = str(candidate_profile or "").strip()
    if not candidate:
        raise ValueError("candidate_profile must be non-empty.")
    normalized_runs = int(runs)
    if normalized_runs <= 0:
        raise ValueError("runs must be positive.")
    return f"scripts/run_qa_rollout_stability.sh {candidate} {normalized_runs}"


def resolve_rollout_candidate_settings(
    candidate_profile: str,
    *,
    environ: Mapping[str, str] | None = None,
) -> RolloutCandidateSettings:
    """Resolve current-env rollout settings for one candidate profile."""
    candidate = str(candidate_profile or "").strip()
    if candidate not in _PROFILE_LIVE_SMOKE_ARTIFACTS:
        raise ValueError(f"Unsupported rollout candidate profile: {candidate_profile!r}.")
    config = load_answer_backend_config(environ=environ)
    fallback_enabled = candidate == "llm_env"
    return RolloutCandidateSettings(
        candidate_profile=candidate,
        artifact_path=live_smoke_artifact_path_for_candidate(candidate),
        model=str(config.llm.model or "").strip(),
        strict_mode=bool(config.llm.strict_mode),
        fallback_enabled=fallback_enabled,
        open_domain_enabled=bool(config.llm.open_domain_enabled),
        api_key_env=str(config.llm.api_key_env or "").strip() or "OPENAI_API_KEY",
        smoke_command=rollout_smoke_command(candidate),
        compare_command=rollout_compare_command(candidate),
    )
