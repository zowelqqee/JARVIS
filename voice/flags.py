"""Feature flags for staged voice-rollout behavior."""

from __future__ import annotations

import os
from typing import Mapping

_ENV_CONTINUOUS_MODE = "JARVIS_VOICE_CONTINUOUS_MODE"


def continuous_voice_mode_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Return whether advanced multi-turn voice follow-up is enabled."""
    env = os.environ if environ is None else environ
    return _parse_bool(env.get(_ENV_CONTINUOUS_MODE), default=False)


def _parse_bool(raw_value: str | None, *, default: bool) -> bool:
    if raw_value is None:
        return default
    normalized = str(raw_value or "").strip().lower()
    if not normalized:
        return default
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default
