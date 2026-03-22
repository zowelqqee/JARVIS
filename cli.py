"""Minimal interactive CLI for local JARVIS MVP testing."""

from __future__ import annotations

import re
import subprocess

from context.session_context import SessionContext
from input.voice_input import VoiceInputError, capture_voice_input
from runtime.runtime_manager import RuntimeManager, RuntimeResult

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
}
_VOICE_WAKE_PREFIX_RE = re.compile(
    r"^\s*(?:(?:hey|ok|okay)\s+)?jarvis(?:\s*[,:;.!-]\s*|\s+)",
    flags=re.IGNORECASE,
)


def main() -> int:
    """Run a small REPL over the current supervised runtime."""
    runtime_manager = RuntimeManager()
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
            runtime_manager.clear_runtime()
            session_context.clear_expired_or_resettable_context(preserve_recent_context=False)
            print("Runtime reset.")
            return False, speak_enabled

        if lowered in {"voice", "/voice"}:
            print("voice: listening... speak now.")
            recognized_text = capture_voice_input(timeout_seconds=_VOICE_CAPTURE_TIMEOUT_SECONDS)
            normalized_text = _normalize_voice_command(recognized_text)
            print(f'recognized: "{normalized_text}"')
            _handle_runtime_input(
                normalized_text,
                runtime_manager=runtime_manager,
                session_context=session_context,
                speak_enabled=speak_enabled,
            )
            return False, speak_enabled

        if lowered in {"speak on", "/speak on", "speak off", "/speak off"}:
            updated_speak_enabled = lowered.endswith("on")
            print(f"Speech output {'enabled' if updated_speak_enabled else 'disabled'}.")
            return False, updated_speak_enabled

        _handle_runtime_input(
            raw_input,
            runtime_manager=runtime_manager,
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
    print("  reset            Clear runtime and session context.")
    print("  quit             Exit the CLI.")
    print("  exit             Exit the CLI.")


def _handle_runtime_input(
    raw_input: str,
    runtime_manager: RuntimeManager,
    session_context: SessionContext,
    speak_enabled: bool,
) -> None:
    """Run one text input through the runtime and print the visible result."""
    result = runtime_manager.handle_input(raw_input, session_context=session_context)
    _print_result(result)
    if speak_enabled:
        _speak_runtime_result(result)


def _print_result(result: RuntimeResult) -> None:
    """Print a compact user-facing runtime summary."""
    visibility = result.visibility
    runtime_state = visibility.get("runtime_state") or result.runtime_state

    print(f"state: {runtime_state}")

    command_summary = visibility.get("command_summary")
    if command_summary:
        print(f"command: {command_summary}")

    current_step = visibility.get("current_step")
    if current_step:
        print(f"current: {current_step}")

    completed_steps = visibility.get("completed_steps") or []
    if completed_steps:
        print(f"done: {', '.join(completed_steps)}")

    blocked_reason = visibility.get("blocked_reason")
    clarification_question = visibility.get("clarification_question")
    confirmation_request = visibility.get("confirmation_request")

    if blocked_reason and blocked_reason != clarification_question and (
        not confirmation_request or blocked_reason != confirmation_request.get("message")
    ):
        print(f"blocked: {blocked_reason}")

    if clarification_question:
        print(f"clarify: {clarification_question}")

    if confirmation_request:
        print(f"confirm: {confirmation_request.get('message')}")

    failure_message = visibility.get("failure_message")
    if failure_message:
        print(f"error: {failure_message}")

    completion_result = visibility.get("completion_result")
    if completion_result:
        print(f"result: {completion_result}")


def _speak_runtime_result(result: RuntimeResult) -> None:
    """Speak one short user-facing runtime message when enabled."""
    message = _spoken_message(result)
    if not message:
        return

    try:
        speech_result = subprocess.run(["say", message], capture_output=True, text=True, check=False)
    except OSError:
        print("speech: unavailable.")
        return

    if speech_result.returncode != 0:
        print("speech: unavailable.")


def _spoken_message(result: RuntimeResult) -> str | None:
    """Select the single runtime message worth speaking for the current result."""
    visibility = result.visibility
    clarification_question = visibility.get("clarification_question")
    if clarification_question:
        return str(clarification_question)

    confirmation_request = visibility.get("confirmation_request")
    if isinstance(confirmation_request, dict):
        message = confirmation_request.get("message")
        if message:
            return str(message)

    failure_message = visibility.get("failure_message")
    if failure_message:
        return str(failure_message)

    completion_result = visibility.get("completion_result")
    if completion_result:
        return str(completion_result)

    return None


def _normalize_voice_command(recognized_text: str) -> str:
    """Keep one deterministic command from a noisy voice transcription."""
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
