"""Explicit local TTS defaults for the interactive CLI."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
from typing import Mapping, MutableMapping

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TTS_ENV_FILE_ENV = "JARVIS_TTS_ENV_FILE"
_DEFAULT_TTS_ENV_FILE = _REPO_ROOT / "tmp" / "runtime" / "jarvis_tts.env"
_RUNTIME_DEFAULTS_LOADED_ENV = "JARVIS_TTS_RUNTIME_DEFAULTS_LOADED"
_RUNTIME_DEFAULTS_PATH_ENV = "JARVIS_TTS_RUNTIME_DEFAULTS_PATH"
_RUNTIME_DEFAULTS_KEYS_ENV = "JARVIS_TTS_RUNTIME_DEFAULTS_KEYS"
_RUNTIME_DEFAULTS_APPLIED_KEYS_ENV = "JARVIS_TTS_RUNTIME_DEFAULTS_APPLIED_KEYS"
_VALID_ENV_KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_EXTRA_ALLOWED_KEYS = frozenset({"REQUESTS_CA_BUNDLE", "SSL_CERT_FILE"})


@dataclass(frozen=True, slots=True)
class TTSRuntimeDefaultsState:
    """Visible metadata for one local TTS defaults file."""

    path: str | None = None
    loaded: bool = False
    configured_keys: tuple[str, ...] = ()
    applied_keys: tuple[str, ...] = ()


def apply_cli_tts_env_defaults(environ: MutableMapping[str, str] | None = None) -> TTSRuntimeDefaultsState:
    """Fill missing TTS env keys from one explicit repo-local defaults file."""
    target = os.environ if environ is None else environ
    env_file = _resolve_tts_env_file(target)
    if env_file is None or not env_file.exists():
        return TTSRuntimeDefaultsState(path=str(env_file) if env_file is not None else None)

    configured = _read_tts_env_file(env_file)
    if not configured:
        return TTSRuntimeDefaultsState(path=str(env_file), loaded=True)

    applied_keys: list[str] = []
    for key, value in configured.items():
        current = str(target.get(key, "") or "").strip()
        if current:
            continue
        target[key] = value
        applied_keys.append(key)

    configured_keys = tuple(configured.keys())
    applied = tuple(applied_keys)
    target[_RUNTIME_DEFAULTS_LOADED_ENV] = "1"
    target[_RUNTIME_DEFAULTS_PATH_ENV] = str(env_file)
    target[_RUNTIME_DEFAULTS_KEYS_ENV] = ",".join(configured_keys)
    target[_RUNTIME_DEFAULTS_APPLIED_KEYS_ENV] = ",".join(applied)
    return TTSRuntimeDefaultsState(
        path=str(env_file),
        loaded=True,
        configured_keys=configured_keys,
        applied_keys=applied,
    )


def tts_runtime_configuration_notes(environ: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Return operator-facing notes about loaded CLI TTS defaults."""
    current = os.environ if environ is None else environ
    if str(current.get(_RUNTIME_DEFAULTS_LOADED_ENV, "") or "").strip().lower() not in {"1", "true", "yes", "on"}:
        return ()

    path = str(current.get(_RUNTIME_DEFAULTS_PATH_ENV, "") or "").strip()
    configured = _split_csv_env(current.get(_RUNTIME_DEFAULTS_KEYS_ENV))
    applied = _split_csv_env(current.get(_RUNTIME_DEFAULTS_APPLIED_KEYS_ENV))
    notes = []
    if path:
        notes.append(f"loaded local TTS defaults from {path}")
    if configured:
        notes.append(f"configured keys: {', '.join(configured)}")
    if applied:
        notes.append(f"applied missing keys: {', '.join(applied)}")
    elif configured:
        notes.append("applied missing keys: none (process env already set)")
    return tuple(notes)


def _resolve_tts_env_file(environ: Mapping[str, str]) -> Path | None:
    explicit = str(environ.get(_TTS_ENV_FILE_ENV, "") or "").strip()
    if explicit:
        return Path(explicit).expanduser()
    return _DEFAULT_TTS_ENV_FILE


def _read_tts_env_file(path: Path) -> dict[str, str]:
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError:
        return {}

    parsed: dict[str, str] = {}
    for line in raw_text.splitlines():
        entry = _parse_tts_env_line(line)
        if entry is None:
            continue
        key, value = entry
        parsed[key] = value
    return parsed


def _parse_tts_env_line(line: str) -> tuple[str, str] | None:
    current = str(line or "").strip()
    if not current or current.startswith("#"):
        return None
    if current.startswith("export "):
        current = current[len("export ") :].strip()
    if "=" not in current:
        return None
    key, value = current.split("=", 1)
    key = key.strip()
    if not _VALID_ENV_KEY_RE.fullmatch(key):
        return None
    if not _tts_env_key_allowed(key):
        return None
    return key, _normalize_env_value(value)


def _tts_env_key_allowed(key: str) -> bool:
    return key.startswith("JARVIS_TTS_") or key in _EXTRA_ALLOWED_KEYS


def _normalize_env_value(value: str) -> str:
    current = str(value or "").strip()
    if len(current) >= 2 and current[0] == current[-1] and current[0] in {"'", '"'}:
        return current[1:-1]
    return current


def _split_csv_env(value: str | None) -> tuple[str, ...]:
    return tuple(
        item
        for item in (part.strip() for part in str(value or "").split(","))
        if item
    )
