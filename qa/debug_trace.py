"""Safe structured debug-trace helpers for QA observability."""

from __future__ import annotations

import os
from typing import Any, Mapping

_ENV_QA_DEBUG = "JARVIS_QA_DEBUG"


def qa_debug_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Return whether structured QA debug tracing is enabled."""
    env = dict(os.environ if environ is None else environ)
    value = str(env.get(_ENV_QA_DEBUG, "") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def set_debug_payload(debug_trace: dict[str, Any] | None, key: str, payload: dict[str, Any] | None) -> None:
    """Store one pruned structured payload in the shared debug trace."""
    if debug_trace is None:
        return
    normalized_key = str(key or "").strip()
    if not normalized_key:
        return
    pruned = _prune_debug_value(payload)
    if pruned in (None, {}, [], ""):
        return
    debug_trace[normalized_key] = pruned


def update_debug_payload(debug_trace: dict[str, Any] | None, key: str, payload: dict[str, Any] | None) -> None:
    """Merge one structured payload into an existing debug-trace section."""
    if debug_trace is None:
        return
    normalized_key = str(key or "").strip()
    if not normalized_key:
        return
    current = debug_trace.get(normalized_key)
    if not isinstance(current, dict):
        current = {}
    next_payload = _prune_debug_value(payload)
    if not isinstance(next_payload, dict):
        if next_payload not in (None, {}, [], ""):
            debug_trace[normalized_key] = next_payload
        return
    current.update(next_payload)
    debug_trace[normalized_key] = current


def debug_flag_name() -> str:
    """Return the environment variable name for QA debug mode."""
    return _ENV_QA_DEBUG


def _prune_debug_value(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            pruned = _prune_debug_value(item)
            if pruned in (None, {}, [], ""):
                continue
            result[str(key)] = pruned
        return result
    if isinstance(value, (list, tuple)):
        result_list = []
        for item in value:
            pruned = _prune_debug_value(item)
            if pruned in (None, {}, [], ""):
                continue
            result_list.append(pruned)
        return result_list
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return value
