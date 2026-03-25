"""Shared rollout-profile helpers for QA live smoke and gate workflows."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_LIVE_SMOKE_ARTIFACT = _REPO_ROOT / "tmp" / "qa" / "openai_live_smoke.json"
_PROFILE_LIVE_SMOKE_ARTIFACTS = {
    "llm_env": _REPO_ROOT / "tmp" / "qa" / "openai_live_smoke_llm_env.json",
    "llm_env_strict": _REPO_ROOT / "tmp" / "qa" / "openai_live_smoke_llm_env_strict.json",
}


def live_smoke_artifact_path_for_candidate(candidate_profile: str | None = None) -> Path:
    """Return the default artifact path for one rollout candidate profile."""
    return _PROFILE_LIVE_SMOKE_ARTIFACTS.get(str(candidate_profile or "").strip(), _DEFAULT_LIVE_SMOKE_ARTIFACT)


def rollout_smoke_command(candidate_profile: str | None = None) -> str:
    """Return the recommended live-smoke command for one rollout candidate."""
    candidate = str(candidate_profile or "").strip()
    if not candidate:
        return "scripts/run_openai_live_smoke.sh"
    return f"scripts/run_openai_live_smoke.sh {candidate}"


def rollout_compare_command(candidate_profile: str) -> str:
    """Return the recommended comparative-gate command for one rollout candidate."""
    candidate = str(candidate_profile or "").strip()
    if not candidate:
        raise ValueError("candidate_profile must be non-empty.")
    return f"scripts/run_qa_rollout_gate.sh {candidate}"
