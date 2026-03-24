"""Minimal interactive CLI for local JARVIS MVP testing."""

from __future__ import annotations

import os
import re
import subprocess

from context.session_context import SessionContext
from input.voice_input import VoiceInputError, capture_voice_input
from interaction.interaction_manager import InteractionManager
from qa.answer_config import load_answer_backend_config
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
    print("qa smoke command: scripts/run_openai_live_smoke.sh")
    print(f"api key env: {config.llm.api_key_env} ({'present' if api_key_present else 'missing'})")
    print(f"live smoke flag: JARVIS_QA_OPENAI_LIVE_SMOKE ({'present' if live_flag_present else 'missing'})")
    print(f"debug flag: JARVIS_QA_DEBUG ({'present' if debug_flag_present else 'missing'})")


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
