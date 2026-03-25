"""Minimal interactive CLI for local JARVIS MVP testing."""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from context.session_context import SessionContext
from input.voice_input import VoiceInputError, capture_voice_input
from interaction.interaction_manager import InteractionManager
from qa.answer_config import load_answer_backend_config
from qa.rollout_profiles import live_smoke_artifact_path_for_candidate, rollout_compare_command, rollout_smoke_command
from runtime.runtime_manager import RuntimeManager
from ui.interaction_presenter import interaction_output_lines, interaction_speech_message

_VOICE_CAPTURE_TIMEOUT_SECONDS = 7.0
_VOICE_COMMAND_STARTERS = {
    "open",
    "run",
    "launch",
    "start",
    "close",
    "list",
    "show",
    "find",
    "search",
    "prepare",
    "set",
    "use",
    "focus",
    "confirm",
    "cancel",
    "yes",
    "no",
    "what",
    "how",
    "why",
    "which",
    "where",
    "when",
    "who",
    "explain",
    "help",
}
_VOICE_WAKE_PREFIX_RE = re.compile(
    r"^\s*(?:(?:hey|ok|okay)\s+)?jarvis(?:\s*[,:;.!-]\s*|\s+)",
    flags=re.IGNORECASE,
)
_LIVE_SMOKE_ARTIFACT_ENV = "JARVIS_QA_OPENAI_LIVE_ARTIFACT"
_LIVE_SMOKE_ARTIFACT_MAX_AGE_HOURS = 24.0


def main() -> int:
    """Run a small REPL over the current supervised runtime."""
    runtime_manager = RuntimeManager()
    interaction_manager = InteractionManager(runtime_manager=runtime_manager)
    session_context = SessionContext()
    speak_enabled = False

    print("JARVIS MVP CLI")
    print("Shell commands: help, voice, speak on, speak off, reset, quit")

    while True:
        try:
            raw_input = input("jarvis> ")
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print()
            continue

        should_exit, speak_enabled = _handle_cli_command(
            raw_input,
            runtime_manager=runtime_manager,
            interaction_manager=interaction_manager,
            session_context=session_context,
            speak_enabled=speak_enabled,
        )
        if should_exit:
            return 0


def _handle_cli_command(
    raw_input: str,
    runtime_manager: RuntimeManager,
    session_context: SessionContext,
    speak_enabled: bool,
    interaction_manager: InteractionManager | None = None,
) -> tuple[bool, bool]:
    """Handle one CLI command and return exit intent plus updated speech mode."""
    try:
        command = raw_input.strip()
        lowered = command.lower()

        if not command:
            return False, speak_enabled

        if lowered in {"exit", "quit"}:
            return True, speak_enabled

        if lowered in {"help", "/help"}:
            _print_help()
            return False, speak_enabled

        if lowered in {"reset", "/reset"}:
            active_runtime_manager = interaction_manager.runtime_manager if interaction_manager is not None else runtime_manager
            active_runtime_manager.clear_runtime()
            session_context.clear_expired_or_resettable_context(preserve_recent_context=False)
            print("Runtime reset.")
            return False, speak_enabled

        if lowered in {"qa backend", "/qa backend"}:
            _print_qa_backend()
            return False, speak_enabled

        if lowered in {"qa model", "/qa model"}:
            _print_qa_model()
            return False, speak_enabled

        if lowered in {"qa smoke", "/qa smoke"}:
            _print_qa_smoke()
            return False, speak_enabled

        if lowered in {"qa gate", "/qa gate"}:
            _print_qa_gate()
            return False, speak_enabled

        if lowered in {"qa gate strict", "/qa gate strict"}:
            _print_qa_gate(strict_candidate=True)
            return False, speak_enabled

        if lowered in {"voice", "/voice"}:
            print("voice: listening... speak now.")
            recognized_text = capture_voice_input(timeout_seconds=_VOICE_CAPTURE_TIMEOUT_SECONDS)
            normalized_text = _normalize_voice_command(recognized_text)
            print(f'recognized: "{normalized_text}"')
            if interaction_manager is None:
                _handle_runtime_input(
                    normalized_text,
                    runtime_manager=runtime_manager,
                    session_context=session_context,
                    speak_enabled=speak_enabled,
                )
            else:
                _handle_runtime_input(
                    normalized_text,
                    runtime_manager=runtime_manager,
                    interaction_manager=interaction_manager,
                    session_context=session_context,
                    speak_enabled=speak_enabled,
                )
            return False, speak_enabled

        if lowered in {"speak on", "/speak on", "speak off", "/speak off"}:
            updated_speak_enabled = lowered.endswith("on")
            print(f"Speech output {'enabled' if updated_speak_enabled else 'disabled'}.")
            return False, updated_speak_enabled

        if interaction_manager is None:
            _handle_runtime_input(
                raw_input,
                runtime_manager=runtime_manager,
                session_context=session_context,
                speak_enabled=speak_enabled,
            )
        else:
            _handle_runtime_input(
                raw_input,
                runtime_manager=runtime_manager,
                interaction_manager=interaction_manager,
                session_context=session_context,
                speak_enabled=speak_enabled,
            )
        return False, speak_enabled
    except KeyboardInterrupt:
        print()
        return False, speak_enabled
    except VoiceInputError as exc:
        print(f"voice: {exc}")
        if exc.hint:
            print(f"hint: {exc.hint}")
        return False, speak_enabled
    except Exception as exc:
        print(f"Unexpected error: {exc}")
        runtime_manager.clear_runtime()
        session_context.clear_expired_or_resettable_context(preserve_recent_context=False)
        return False, speak_enabled


def _print_help() -> None:
    """Print the minimal supported shell commands."""
    print("Shell commands:")
    print("  help             Show shell commands.")
    print("  voice            Capture one spoken command on macOS.")
    print("  /voice           Capture one spoken command on macOS.")
    print("  speak on         Enable spoken output for key runtime messages.")
    print("  /speak on        Enable spoken output for key runtime messages.")
    print("  speak off        Disable spoken output.")
    print("  /speak off       Disable spoken output.")
    print("  qa backend       Show the current QA backend mode.")
    print("  /qa backend      Show the current QA backend mode.")
    print("  qa model         Show the configured QA model path.")
    print("  /qa model        Show the configured QA model path.")
    print("  qa smoke         Show live smoke readiness and command.")
    print("  /qa smoke        Show live smoke readiness and command.")
    print("  qa gate          Show offline rollout-gate precheck.")
    print("  /qa gate         Show offline rollout-gate precheck.")
    print("  qa gate strict   Show offline precheck for llm_env_strict.")
    print("  /qa gate strict  Show offline precheck for llm_env_strict.")
    print("  reset            Clear runtime and session context.")
    print("  quit             Exit the CLI.")
    print("  exit             Exit the CLI.")


def _handle_runtime_input(
    raw_input: str,
    runtime_manager: RuntimeManager,
    session_context: SessionContext,
    speak_enabled: bool,
    interaction_manager: InteractionManager | None = None,
) -> None:
    """Run one text input through the dual-mode interaction layer and print the visible result."""
    active_interaction_manager = interaction_manager or InteractionManager(runtime_manager=runtime_manager)
    result = active_interaction_manager.handle_input(raw_input, session_context=session_context)
    for line in interaction_output_lines(result):
        print(line)
    if speak_enabled:
        _speak_message(interaction_speech_message(result))


def _speak_message(message: str | None) -> None:
    """Speak one short user-facing message when enabled."""
    if not message:
        return
    try:
        speech_result = subprocess.run(["say", message], capture_output=True, text=True, check=False)
    except OSError:
        print("speech: unavailable.")
        return

    if speech_result.returncode != 0:
        print("speech: unavailable.")


def _print_qa_backend() -> None:
    """Print the current QA backend selection without mutating runtime state."""
    config = load_answer_backend_config()
    print(f"qa backend: {getattr(config.backend_kind, 'value', config.backend_kind)}")
    print(f"llm provider: {getattr(config.llm.provider, 'value', config.llm.provider)}")
    print(f"llm enabled: {'on' if config.llm.enabled else 'off'}")
    print(f"llm fallback: {'on' if config.llm.fallback_enabled else 'off'}")


def _print_qa_model() -> None:
    """Print the current QA model configuration in a concise operator-friendly form."""
    config = load_answer_backend_config()
    print(f"qa model: {config.llm.model}")
    print(f"reasoning effort: {config.llm.reasoning_effort}")
    print(f"strict mode: {'on' if config.llm.strict_mode else 'off'}")
    print(f"max output tokens: {config.llm.max_output_tokens}")


def _print_qa_smoke() -> None:
    """Print the current live-smoke readiness without triggering network calls."""
    config = load_answer_backend_config()
    api_key_present = bool(os.environ.get(config.llm.api_key_env, "").strip())
    live_flag_present = bool(os.environ.get("JARVIS_QA_OPENAI_LIVE_SMOKE", "").strip())
    debug_flag_present = bool(os.environ.get("JARVIS_QA_DEBUG", "").strip())
    artifact_path, artifact_payload, artifact_error = _load_live_smoke_artifact()
    artifact_status = _live_smoke_artifact_status(
        artifact_payload=artifact_payload,
        artifact_error=artifact_error,
    )
    open_domain_verified = bool((artifact_payload or {}).get("open_domain_verified"))
    print("qa smoke command: scripts/run_openai_live_smoke.sh")
    print(f"api key env: {config.llm.api_key_env} ({'present' if api_key_present else 'missing'})")
    print(f"live smoke flag: JARVIS_QA_OPENAI_LIVE_SMOKE ({'present' if live_flag_present else 'missing'})")
    print(f"debug flag: JARVIS_QA_DEBUG ({'present' if debug_flag_present else 'missing'})")
    print(f"live smoke artifact: {artifact_path} ({artifact_status})")
    print(f"open-domain live verification: {'yes' if open_domain_verified else 'no'}")
    if artifact_error is not None:
        print(f"artifact error: {artifact_error}")


def _print_qa_gate(*, strict_candidate: bool = False) -> None:
    """Print an offline rollout-gate precheck without running networked evals."""
    config = load_answer_backend_config()
    candidate_profile = "llm_env_strict" if strict_candidate else "llm_env"
    fallback_enabled = False if strict_candidate else True
    api_key_present = bool(os.environ.get(config.llm.api_key_env, "").strip())
    artifact_path, artifact_payload, artifact_error = _load_live_smoke_artifact(candidate_profile)
    artifact_status = _live_smoke_artifact_status(
        artifact_payload=artifact_payload,
        artifact_error=artifact_error,
    )
    artifact_age_hours, artifact_fresh, artifact_fresh_reason = _live_smoke_artifact_freshness(artifact_payload)
    artifact_match, artifact_match_reason = _live_smoke_artifact_profile_match(
        artifact_payload=artifact_payload,
        provider=str(getattr(config.llm.provider, "value", config.llm.provider) or "").strip(),
        model=str(getattr(config.llm, "model", "") or "").strip(),
        strict_mode=bool(getattr(config.llm, "strict_mode", False)),
        fallback_enabled=fallback_enabled,
        open_domain_enabled=bool(getattr(config.llm, "open_domain_enabled", False)),
    )
    open_domain_enabled = bool(getattr(config.llm, "open_domain_enabled", False))
    open_domain_verified = bool((artifact_payload or {}).get("open_domain_verified"))
    blockers: list[str] = []
    if not api_key_present:
        blockers.append(f"{config.llm.api_key_env} is missing")
    if not open_domain_enabled:
        blockers.append("open-domain question answering is disabled")
    if artifact_error is not None:
        blockers.append("live smoke artifact is invalid")
    elif artifact_payload is None:
        blockers.append("live smoke artifact is missing")
    elif not bool(artifact_payload.get("success")):
        blockers.append("live smoke artifact is not green")
    if artifact_payload is not None and artifact_error is None and artifact_fresh is not True:
        blockers.append("live smoke artifact is stale")
    if artifact_payload is not None and artifact_error is None and artifact_match is False:
        blockers.append("live smoke artifact does not match candidate provider/model/strict/fallback/open-domain config")
    if open_domain_enabled and not open_domain_verified:
        blockers.append("open-domain live verification is missing")

    smoke_command = rollout_smoke_command(candidate_profile)
    compare_command = rollout_compare_command(candidate_profile)
    print(f"qa gate candidate: {candidate_profile}")
    print(f"provider/model: {getattr(config.llm.provider, 'value', config.llm.provider)} / {config.llm.model}")
    print(f"api key env: {config.llm.api_key_env} ({'present' if api_key_present else 'missing'})")
    print(f"strict mode: {'on' if getattr(config.llm, 'strict_mode', False) else 'off'}")
    print(f"open-domain: {'on' if open_domain_enabled else 'off'}")
    print(f"fallback: {'on' if fallback_enabled else 'off'}")
    print(f"live smoke artifact: {artifact_path} ({artifact_status})")
    if artifact_fresh is None:
        print("live smoke artifact fresh: n/a")
    elif artifact_fresh:
        print(f"live smoke artifact fresh: yes ({artifact_age_hours}h)")
    else:
        print(f"live smoke artifact fresh: no ({artifact_fresh_reason or 'stale'})")
    if artifact_match is None:
        print("live smoke artifact matches profile: n/a")
    elif artifact_match:
        print("live smoke artifact matches profile: yes")
    else:
        print(f"live smoke artifact matches profile: no ({artifact_match_reason or 'mismatch'})")
    print(f"open-domain live verification: {'yes' if open_domain_verified else 'no'}")
    print(f"precheck: {'ready' if not blockers else 'blocked'}")
    for blocker in blockers:
        print(f"blocker: {blocker}")
    print(f"smoke command: {smoke_command}")
    print(f"compare command: {compare_command}")
    print("note: full comparative gate is still required for routing, fallback, latency, and usage signals.")


def _load_live_smoke_artifact(candidate_profile: str | None = None) -> tuple[Path, dict[str, object] | None, str | None]:
    """Return the current live-smoke artifact plus any parse error."""
    configured = str(os.environ.get(_LIVE_SMOKE_ARTIFACT_ENV, "") or "").strip()
    artifact_path = Path(configured) if configured else live_smoke_artifact_path_for_candidate(candidate_profile)
    if not artifact_path.exists():
        return artifact_path, None, None
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return artifact_path, None, f"{type(exc).__name__}: {exc}"
    if not isinstance(payload, dict):
        return artifact_path, None, "ValueError: live smoke artifact must be a JSON object."
    return artifact_path, payload, None


def _artifact_now() -> datetime:
    """Return the current UTC time for artifact freshness checks."""
    return datetime.now(timezone.utc)


def _live_smoke_artifact_freshness(
    artifact_payload: dict[str, object] | None,
) -> tuple[float | None, bool | None, str | None]:
    """Return artifact age plus a freshness decision."""
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
    return age_hours, age_hours <= _LIVE_SMOKE_ARTIFACT_MAX_AGE_HOURS, None


def _live_smoke_artifact_profile_match(
    *,
    artifact_payload: dict[str, object] | None,
    provider: str,
    model: str,
    strict_mode: bool,
    fallback_enabled: bool,
    open_domain_enabled: bool,
) -> tuple[bool | None, str | None]:
    """Return whether one artifact matches the current candidate profile."""
    if artifact_payload is None:
        return None, None
    diagnostics = dict(artifact_payload.get("diagnostics", {}) or {})
    actual_provider = str(diagnostics.get("provider", "") or "").strip()
    actual_model = str(diagnostics.get("model", "") or "").strip()
    actual_strict_mode = bool(diagnostics.get("strict_mode", False))
    actual_fallback_enabled = bool(diagnostics.get("fallback_enabled", False))
    actual_open_domain = bool(diagnostics.get("open_domain_enabled", False))
    mismatches: list[str] = []
    if actual_provider != provider:
        mismatches.append(f"artifact provider {actual_provider or '<missing>'} != {provider or '<missing>'}")
    if actual_model != model:
        mismatches.append(f"artifact model {actual_model or '<missing>'} != {model or '<missing>'}")
    if actual_strict_mode is not strict_mode:
        mismatches.append("artifact strict-mode flag does not match current config")
    if actual_fallback_enabled is not fallback_enabled:
        mismatches.append("artifact fallback flag does not match current config")
    if actual_open_domain is not open_domain_enabled:
        mismatches.append("artifact open-domain flag does not match current config")
    return (not mismatches), "; ".join(mismatches) or None


def _live_smoke_artifact_status(
    *,
    artifact_payload: dict[str, object] | None,
    artifact_error: str | None,
) -> str:
    """Return one short operator-friendly artifact status."""
    if artifact_error is not None:
        return "invalid"
    if artifact_payload is None:
        return "missing"
    if bool(artifact_payload.get("success")):
        return "green"
    return "failed"


def _normalize_voice_command(recognized_text: str) -> str:
    """Keep one deterministic interaction from a noisy voice transcription."""
    compact = " ".join(recognized_text.strip().split())
    compact = _strip_voice_wake_prefix(compact)
    if not compact:
        return compact

    tokens = compact.split(" ")
    lowered = [token.lower() for token in tokens]

    for index in range(1, len(tokens)):
        if lowered[index] not in _VOICE_COMMAND_STARTERS:
            continue

        head = " ".join(tokens[:index]).strip()
        tail = " ".join(tokens[index:]).strip()
        if not head or not tail:
            continue

        if head.lower() == tail.lower():
            return head

        if lowered[index] == lowered[0]:
            return head

    return compact


def _strip_voice_wake_prefix(text: str) -> str:
    """Strip a small fixed wake-word prefix used in spoken commands."""
    candidate = text.strip()
    stripped = _VOICE_WAKE_PREFIX_RE.sub("", candidate, count=1).strip()
    return stripped or candidate


if __name__ == "__main__":
    raise SystemExit(main())
