"""Minimal interactive CLI for local JARVIS MVP testing."""

from __future__ import annotations

import json
import os
import hashlib
from collections.abc import MutableMapping
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Thread
from time import perf_counter

from context.session_context import SessionContext
from input.voice_input import VoiceInputError
from interaction.interaction_manager import InteractionManager
from interaction.interaction_router import route_interaction
from qa.beta_release_review import (
    beta_release_review_artifact_consistency,
    beta_release_review_pending_checks,
    beta_release_review_suggested_args,
    beta_release_review_status,
    build_beta_release_review_record,
    format_beta_release_review_record,
    load_beta_release_review_artifact,
)
from qa.beta_readiness import build_beta_readiness_record, format_beta_readiness_record
from qa.manual_beta_checklist import (
    build_manual_beta_checklist_record,
    manual_beta_checklist_detail_lines,
    format_manual_beta_checklist_record,
    manual_beta_checklist_guide_command,
    manual_beta_checklist_pending_item_details,
    load_manual_beta_checklist_artifact,
    manual_beta_checklist_pending_items,
    manual_beta_checklist_suggested_args,
    manual_beta_checklist_status,
)
from qa.answer_config import load_answer_backend_config, rollout_default_path_label
from qa.rollout_profiles import (
    beta_release_review_artifact_path,
    beta_readiness_artifact_path,
    live_smoke_artifact_path_for_candidate,
    manual_beta_checklist_artifact_path,
    rollout_compare_command,
    rollout_launch_command,
    rollout_smoke_command,
    rollout_stage_preview_command,
    rollout_stability_artifact_path_for_candidate,
)
from runtime.runtime_manager import RuntimeManager
from voice.audio_policy import HalfDuplexAudioPolicy, build_default_audio_policy
from voice.dispatcher import dispatch_interaction_input, dispatch_voice_turn, render_interaction_dispatch
from voice.earcons import EarconProvider, build_default_earcon_provider
from voice.flags import (
    build_voice_mode_status,
    continuous_voice_mode_enabled,
    format_voice_mode_status,
    max_auto_follow_up_turns,
    voice_earcons_enabled,
)
from voice.gate import build_voice_readiness_gate_report, format_voice_readiness_gate_report
from voice.language import detect_spoken_locale
from voice.readiness import build_voice_readiness_record, format_voice_readiness_record, write_voice_readiness_artifact
from voice.session import (
    VoiceTurn,
    build_follow_up_capture_request,
    capture_cli_voice_turn as capture_voice_turn,
    capture_follow_up_voice_turn,
    follow_up_control_action,
)
from voice.session_state import (
    VoiceSessionState,
    build_default_voice_session_state,
    format_voice_last_event,
)
from voice.speech_presenter import latency_filler_utterance
from voice.status import build_voice_session_status, format_voice_session_status
from voice.telemetry import (
    VoiceTelemetryCollector,
    build_default_voice_telemetry,
    format_voice_telemetry_artifact_summary,
    format_voice_telemetry_snapshot,
    load_voice_telemetry_snapshot,
    write_voice_telemetry_artifact,
)
from voice.tts_provider import TTSProvider, build_default_tts_provider

_VOICE_CAPTURE_TIMEOUT_SECONDS = 7.0
_VOICE_LATENCY_FILLER_DELAY_SECONDS = 0.6
_FOLLOW_UP_EMPTY_RETRYABLE_CODES = frozenset({"EMPTY_RECOGNITION", "RECOGNITION_FAILED"})
_VOICE_ANSWER_FOLLOW_UP_FILLER_SURFACES = frozenset(
    {
        "explain more",
        "which source",
        "which sources",
        "where is that written",
        "where is that documented",
        "why is that",
        "why so",
        "repeat that",
    }
)
_LIVE_SMOKE_ARTIFACT_ENV = "JARVIS_QA_OPENAI_LIVE_ARTIFACT"
_LIVE_SMOKE_ARTIFACT_MAX_AGE_HOURS = 24.0


def main() -> int:
    """Run a small REPL over the current supervised runtime."""
    runtime_manager = RuntimeManager()
    interaction_manager = _build_default_interaction_manager(runtime_manager)
    session_context = SessionContext()
    tts_provider = build_default_tts_provider()
    audio_policy = build_default_audio_policy()
    voice_telemetry = build_default_voice_telemetry()
    voice_session_state = build_default_voice_session_state()
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
            tts_provider=tts_provider,
            audio_policy=audio_policy,
            telemetry=voice_telemetry,
            voice_session_state=voice_session_state,
        )
        if should_exit:
            return 0


def _handle_cli_command(
    raw_input: str,
    runtime_manager: RuntimeManager,
    session_context: SessionContext,
    speak_enabled: bool,
    interaction_manager: InteractionManager | None = None,
    tts_provider: TTSProvider | None = None,
    audio_policy: HalfDuplexAudioPolicy | None = None,
    telemetry: VoiceTelemetryCollector | None = None,
    voice_session_state: VoiceSessionState | None = None,
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

        if lowered in {"qa beta", "/qa beta"}:
            _print_qa_beta()
            return False, speak_enabled

        if lowered in {"qa checklist", "/qa checklist"}:
            _print_qa_checklist()
            return False, speak_enabled

        if lowered in {"qa release review", "/qa release review"}:
            _print_qa_release_review()
            return False, speak_enabled

        if lowered in {"qa readiness", "/qa readiness"}:
            _print_qa_readiness()
            return False, speak_enabled

        if lowered in {"voice readiness", "/voice readiness"}:
            _print_voice_readiness()
            return False, speak_enabled

        if lowered in {"voice readiness write", "/voice readiness write"}:
            _write_voice_readiness()
            return False, speak_enabled

        if lowered in {"voice mode", "/voice mode"}:
            _print_voice_mode()
            return False, speak_enabled

        if lowered in {"voice last", "/voice last"}:
            _print_voice_last(voice_session_state)
            return False, speak_enabled

        if lowered in {"voice status", "/voice status"}:
            _print_voice_status(speak_enabled=speak_enabled, telemetry=telemetry)
            return False, speak_enabled

        if lowered in {"voice gate", "/voice gate"}:
            _print_voice_gate()
            return False, speak_enabled

        if lowered in {"voice telemetry", "/voice telemetry"}:
            _print_voice_telemetry(telemetry)
            return False, speak_enabled

        if lowered in {"voice telemetry artifact", "/voice telemetry artifact"}:
            _print_voice_telemetry_artifact()
            return False, speak_enabled

        if lowered in {"voice telemetry reset", "/voice telemetry reset"}:
            _reset_voice_telemetry(telemetry)
            return False, speak_enabled

        if lowered in {"voice telemetry write", "/voice telemetry write"}:
            _write_voice_telemetry(telemetry)
            return False, speak_enabled

        if lowered in {"voice", "/voice"}:
            active_interaction_manager = interaction_manager or _build_default_interaction_manager(runtime_manager)
            active_tts_provider = (tts_provider or build_default_tts_provider()) if speak_enabled else None
            active_earcon_provider = build_default_earcon_provider() if voice_earcons_enabled() else None
            _run_voice_command(
                interaction_manager=active_interaction_manager,
                session_context=session_context,
                speak_enabled=speak_enabled,
                tts_provider=active_tts_provider,
                earcon_provider=active_earcon_provider,
                audio_policy=audio_policy,
                telemetry=telemetry,
                voice_session_state=voice_session_state,
            )
            return False, speak_enabled

        if lowered in {"speak on", "/speak on", "speak off", "/speak off"}:
            updated_speak_enabled = lowered.endswith("on")
            print(f"Speech output {'enabled' if updated_speak_enabled else 'disabled'}.")
            return False, updated_speak_enabled

        _dispatch_runtime_input(
            raw_input,
            runtime_manager=runtime_manager,
            interaction_manager=interaction_manager,
            session_context=session_context,
            speak_enabled=speak_enabled,
            speech_locale_hint=_preferred_speech_locale_hint(raw_input) if speak_enabled else None,
            tts_provider=tts_provider,
            audio_policy=audio_policy,
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
    print("  qa beta          Show offline beta-decision readiness summary.")
    print("  /qa beta         Show offline beta-decision readiness summary.")
    print("  qa checklist     Show the manual beta checklist helper summary.")
    print("  /qa checklist    Show the manual beta checklist helper summary.")
    print("  qa release review Show the beta release-review helper summary.")
    print("  /qa release review Show the beta release-review helper summary.")
    print("  qa readiness     Show the beta readiness helper summary.")
    print("  /qa readiness    Show the beta readiness helper summary.")
    print("  voice readiness  Show the offline voice readiness helper summary.")
    print("  /voice readiness Show the offline voice readiness helper summary.")
    print("  voice readiness write Write the offline voice readiness artifact when unblocked.")
    print("  /voice readiness write Write the offline voice readiness artifact when unblocked.")
    print("  voice mode       Show the current bounded voice-conversation mode.")
    print("  /voice mode      Show the current bounded voice-conversation mode.")
    print("  voice last       Show the last voice event in this CLI session.")
    print("  /voice last      Show the last voice event in this CLI session.")
    print("  voice status     Show current CLI voice-session status and counters.")
    print("  /voice status    Show current CLI voice-session status and counters.")
    print("  voice gate       Show the offline voice rollout gate verdict.")
    print("  /voice gate      Show the offline voice rollout gate verdict.")
    print("  voice telemetry  Show in-memory voice metrics for this CLI session.")
    print("  /voice telemetry Show in-memory voice metrics for this CLI session.")
    print("  voice telemetry artifact Show the saved voice telemetry artifact summary.")
    print("  /voice telemetry artifact Show the saved voice telemetry artifact summary.")
    print("  voice telemetry reset Clear in-memory voice metrics for this CLI session.")
    print("  /voice telemetry reset Clear in-memory voice metrics for this CLI session.")
    print("  voice telemetry write Save current voice metrics to tmp/qa.")
    print("  /voice telemetry write Save current voice metrics to tmp/qa.")
    print("  reset            Clear runtime and session context.")
    print("  quit             Exit the CLI.")
    print("  exit             Exit the CLI.")


def _dispatch_and_render_voice_turn(
    voice_turn: VoiceTurn | object,
    *,
    interaction_manager: InteractionManager,
    session_context: SessionContext,
    speak_enabled: bool,
    tts_provider: TTSProvider | None = None,
    earcon_provider: EarconProvider | None = None,
    audio_policy: HalfDuplexAudioPolicy | None = None,
    telemetry: VoiceTelemetryCollector | None = None,
    voice_session_state: VoiceSessionState | None = None,
):
    """Resolve one prepared voice turn and render its visible/spoken result."""
    print(f'recognized: "{getattr(voice_turn, "normalized_text", "")}"')
    filler_worker = _start_voice_latency_filler(
        voice_turn,
        interaction_manager=interaction_manager,
        session_context=session_context,
        speak_enabled=speak_enabled,
        tts_provider=tts_provider,
        audio_policy=audio_policy,
    )
    try:
        voice_dispatch = dispatch_voice_turn(
            voice_turn,
            session_context=session_context,
            speak_enabled=speak_enabled,
            interaction_manager=interaction_manager,
        )
    finally:
        _stop_voice_latency_filler(filler_worker)
    if voice_session_state is not None:
        voice_session_state.record_dispatch(voice_dispatch.voice_turn)
    if telemetry is not None:
        telemetry.record_dispatch(voice_dispatch.voice_turn, voice_dispatch.interaction)
    render_interaction_dispatch(
        voice_dispatch.interaction,
        emit_line=print,
        tts_provider=tts_provider,
        earcon_provider=earcon_provider,
        audio_policy=audio_policy,
        on_speech_result=telemetry.record_tts_result if telemetry is not None else None,
    )
    return voice_dispatch


def _start_voice_latency_filler(
    voice_turn: VoiceTurn | object,
    *,
    interaction_manager: InteractionManager,
    session_context: SessionContext,
    speak_enabled: bool,
    tts_provider: TTSProvider | None = None,
    audio_policy: HalfDuplexAudioPolicy | None = None,
) -> tuple[Event, Thread] | None:
    """Start one best-effort timer for slow question-like voice turns."""
    if not _should_emit_voice_latency_filler(
        voice_turn,
        interaction_manager=interaction_manager,
        session_context=session_context,
        speak_enabled=speak_enabled,
        tts_provider=tts_provider,
    ):
        return None

    stop_event = Event()
    worker = Thread(
        target=_run_voice_latency_filler,
        kwargs={
            "stop_event": stop_event,
            "preferred_locale": str(
                getattr(voice_turn, "locale_hint", None)
                or getattr(voice_turn, "detected_locale", "")
                or ""
            ).strip()
            or None,
            "tts_provider": tts_provider,
            "audio_policy": audio_policy,
        },
        daemon=True,
    )
    worker.start()
    return stop_event, worker


def _stop_voice_latency_filler(worker_state: tuple[Event, Thread] | None) -> None:
    """Stop one pending latency filler worker and wait for it to settle."""
    if worker_state is None:
        return
    stop_event, worker = worker_state
    stop_event.set()
    worker.join()


def _run_voice_latency_filler(
    *,
    stop_event: Event,
    preferred_locale: str | None,
    tts_provider: TTSProvider | None = None,
    audio_policy: HalfDuplexAudioPolicy | None = None,
) -> None:
    """Emit one short voice filler when answer generation takes noticeably long."""
    if stop_event.wait(_VOICE_LATENCY_FILLER_DELAY_SECONDS):
        return

    print("voice: thinking...")
    if tts_provider is None or stop_event.is_set():
        return

    utterance = latency_filler_utterance(preferred_locale=preferred_locale)
    try:
        if audio_policy is None:
            tts_provider.speak(utterance)
        else:
            with audio_policy.speaking_phase():
                tts_provider.speak(utterance)
    except Exception:
        return


def _should_emit_voice_latency_filler(
    voice_turn: VoiceTurn | object,
    *,
    interaction_manager: InteractionManager,
    session_context: SessionContext,
    speak_enabled: bool,
    tts_provider: TTSProvider | None = None,
) -> bool:
    """Return whether one prepared voice turn is likely to hit answer-generation latency."""
    if not speak_enabled or tts_provider is None:
        return False

    interaction_input = str(
        getattr(voice_turn, "interaction_input", None)
        or getattr(voice_turn, "normalized_text", None)
        or getattr(voice_turn, "normalized_transcript", "")
        or ""
    ).strip()
    if not interaction_input:
        return False

    decision = route_interaction(
        interaction_input,
        session_context=session_context,
        runtime_state=getattr(interaction_manager.runtime_manager, "current_state", None),
    )
    decision_kind = str(getattr(getattr(decision, "kind", None), "value", getattr(decision, "kind", "")) or "").strip()
    if decision_kind == "question":
        return True
    if decision_kind != "command":
        return False

    recent_answer_context = session_context.get_recent_answer_context()
    if recent_answer_context is None:
        return False

    normalized_input = interaction_input.lower().strip(" \t\r\n,.!?;:")
    return normalized_input in _VOICE_ANSWER_FOLLOW_UP_FILLER_SURFACES


def _run_voice_command(
    *,
    interaction_manager: InteractionManager,
    session_context: SessionContext,
    speak_enabled: bool,
    tts_provider: TTSProvider | None = None,
    earcon_provider: EarconProvider | None = None,
    audio_policy: HalfDuplexAudioPolicy | None = None,
    telemetry: VoiceTelemetryCollector | None = None,
    voice_session_state: VoiceSessionState | None = None,
) -> None:
    """Run one bounded voice conversation starting from the explicit `voice` shell command."""
    follow_up_budget = max_auto_follow_up_turns()
    completed_follow_up_turns = 0
    limit_hit = False
    print("voice: listening... speak now.")
    _play_voice_earcon(earcon_provider, "listening_start")
    try:
        current_turn = _capture_voice_turn_with_telemetry(
            capture_fn=capture_voice_turn,
            phase="initial",
            timeout_seconds=_VOICE_CAPTURE_TIMEOUT_SECONDS,
            audio_policy=audio_policy,
            telemetry=telemetry,
            earcon_provider=earcon_provider,
        )
        current_dispatch = _dispatch_and_render_voice_turn(
            current_turn,
            interaction_manager=interaction_manager,
            session_context=session_context,
            speak_enabled=speak_enabled,
            tts_provider=tts_provider,
            earcon_provider=earcon_provider,
            audio_policy=audio_policy,
            telemetry=telemetry,
            voice_session_state=voice_session_state,
        )
    except VoiceInputError:
        _play_voice_earcon(earcon_provider, "error")
        raise
    for _ in range(follow_up_budget):
        follow_up_request = _auto_follow_up_request(current_dispatch)
        if follow_up_request is None:
            break
        follow_up_turn = _capture_auto_follow_up_turn(
            current_dispatch.voice_turn,
            telemetry=telemetry,
            earcon_provider=earcon_provider,
            audio_policy=audio_policy,
            voice_session_state=voice_session_state,
        )
        if follow_up_turn is None:
            break
        if telemetry is not None:
            telemetry.record_follow_up_completed(current_dispatch.voice_turn, follow_up_turn)
        completed_follow_up_turns += 1
        current_dispatch = _dispatch_and_render_voice_turn(
            follow_up_turn,
            interaction_manager=interaction_manager,
            session_context=session_context,
            speak_enabled=speak_enabled,
            tts_provider=tts_provider,
            earcon_provider=earcon_provider,
            audio_policy=audio_policy,
            telemetry=telemetry,
            voice_session_state=voice_session_state,
        )
    if follow_up_budget > 0:
        limit_hit = (
            completed_follow_up_turns >= follow_up_budget and _auto_follow_up_request(current_dispatch) is not None
        )
    if limit_hit:
        print("voice: follow-up limit reached.")
    if telemetry is not None and follow_up_budget > 0:
        telemetry.record_follow_up_loop(
            completed_turns=completed_follow_up_turns,
            limit_hit=limit_hit,
        )


def _auto_follow_up_request(voice_dispatch: object):
    """Return one blocking follow-up capture request for the explicit voice shell path."""
    if not continuous_voice_mode_enabled():
        return None
    voice_turn = getattr(voice_dispatch, "voice_turn", None)
    if not isinstance(voice_turn, VoiceTurn):
        return None
    request = build_follow_up_capture_request(voice_turn)
    if request is None:
        return None
    if request.reason not in {"clarification", "confirmation", "short_answer"}:
        return None
    if request.reason == "short_answer":
        interaction = getattr(voice_dispatch, "interaction", None)
        spoken_text = str(getattr(getattr(interaction, "speech_utterance", None), "text", "") or "").strip()
        if not spoken_text:
            return None
    return request


def _capture_voice_turn_with_telemetry(
    *,
    capture_fn,
    phase: str,
    telemetry: VoiceTelemetryCollector | None = None,
    earcon_provider: EarconProvider | None = None,
    **capture_kwargs,
):
    """Capture one voice turn and record timing plus error outcome when telemetry is enabled."""
    started_at = perf_counter()
    try:
        voice_turn = capture_fn(**capture_kwargs)
    except VoiceInputError as exc:
        if telemetry is not None:
            telemetry.record_capture(
                phase=phase,
                elapsed_seconds=perf_counter() - started_at,
                error=exc,
            )
        raise
    finally:
        if phase in {"initial", "follow_up"}:
            _play_voice_earcon(earcon_provider, "listening_stop")
    if telemetry is not None:
        telemetry.record_capture(
            phase=phase,
            elapsed_seconds=perf_counter() - started_at,
            voice_turn=voice_turn,
    )
    return voice_turn


def _capture_auto_follow_up_turn(
    prior_turn: VoiceTurn,
    *,
    telemetry: VoiceTelemetryCollector | None = None,
    earcon_provider: EarconProvider | None = None,
    audio_policy: HalfDuplexAudioPolicy | None = None,
    voice_session_state: VoiceSessionState | None = None,
):
    """Capture one blocking follow-up reply with bounded control and no-speech retries."""
    relisten_attempts = 0
    empty_retry_attempts = 0
    prompt_kind = "initial"
    while True:
        if telemetry is not None:
            telemetry.record_follow_up_opened(prior_turn)
        if prompt_kind == "initial":
            print("voice: follow-up... speak now.")
        elif prompt_kind == "listen_again":
            print("voice: listening again... speak now.")
        else:
            print("voice: didn't catch that. speak again.")
        _play_voice_earcon(earcon_provider, "listening_start")
        try:
            follow_up_turn = _capture_voice_turn_with_telemetry(
                capture_fn=capture_follow_up_voice_turn,
                phase="follow_up",
                telemetry=telemetry,
                earcon_provider=earcon_provider,
                voice_turn=prior_turn,
                audio_policy=audio_policy,
            )
        except VoiceInputError as exc:
            _play_voice_earcon(earcon_provider, "error")
            if _is_retryable_follow_up_capture_error(exc) and empty_retry_attempts < 1:
                empty_retry_attempts += 1
                prompt_kind = "empty_retry"
                continue
            if _is_retryable_follow_up_capture_error(exc):
                print("voice: no follow-up reply detected.")
                print("voice: follow-up closed.")
                return None
            raise
        control_action = follow_up_control_action(
            follow_up_turn,
            prior_reason=str(getattr(prior_turn, "follow_up_reason", "") or "").strip() or None,
        )
        if telemetry is not None and control_action is not None:
            telemetry.record_follow_up_control(
                prior_turn,
                follow_up_turn,
                action=control_action,
            )
        if voice_session_state is not None and control_action is not None:
            voice_session_state.record_control(
                prior_turn,
                follow_up_turn,
                action=control_action,
            )
        if control_action == "dismiss_follow_up":
            print("voice: follow-up closed.")
            return None
        if control_action != "listen_again":
            return follow_up_turn
        if relisten_attempts >= 1:
            print("voice: follow-up closed.")
            return None
        relisten_attempts += 1
        prompt_kind = "listen_again"


def _is_retryable_follow_up_capture_error(error: VoiceInputError) -> bool:
    """Return whether one follow-up capture error should stay inside the bounded voice loop."""
    return str(getattr(error, "code", "") or "").strip() in _FOLLOW_UP_EMPTY_RETRYABLE_CODES


def _play_voice_earcon(earcon_provider: EarconProvider | None, event: str) -> None:
    """Play one best-effort earcon event when the feature is enabled."""
    if earcon_provider is None:
        return
    try:
        earcon_provider.play(event)
    except Exception:
        return


def _handle_runtime_input(
    raw_input: str,
    runtime_manager: RuntimeManager,
    session_context: SessionContext,
    speak_enabled: bool,
    interaction_manager: InteractionManager | None = None,
    speech_locale_hint: str | None = None,
    tts_provider: TTSProvider | None = None,
    audio_policy: HalfDuplexAudioPolicy | None = None,
) -> None:
    """Run one text input through the dual-mode interaction layer and print the visible result."""
    active_interaction_manager = interaction_manager or _build_default_interaction_manager(runtime_manager)
    dispatch_result = dispatch_interaction_input(
        raw_input,
        interaction_manager=active_interaction_manager,
        session_context=session_context,
        speak_enabled=speak_enabled,
        speech_locale_hint=speech_locale_hint,
    )
    render_interaction_dispatch(
        dispatch_result,
        emit_line=print,
        tts_provider=(tts_provider or build_default_tts_provider()) if speak_enabled else None,
        audio_policy=audio_policy,
    )


def _dispatch_runtime_input(
    raw_input: str,
    *,
    runtime_manager: RuntimeManager,
    session_context: SessionContext,
    speak_enabled: bool,
    interaction_manager: InteractionManager | None = None,
    speech_locale_hint: str | None = None,
    tts_provider: TTSProvider | None = None,
    audio_policy: HalfDuplexAudioPolicy | None = None,
) -> None:
    """Preserve the legacy runtime-call shape unless a TTS provider is supplied."""
    call_kwargs = {
        "runtime_manager": runtime_manager,
        "session_context": session_context,
        "speak_enabled": speak_enabled,
    }
    if interaction_manager is not None:
        call_kwargs["interaction_manager"] = interaction_manager
    if speech_locale_hint is not None:
        call_kwargs["speech_locale_hint"] = speech_locale_hint
    if tts_provider is not None:
        call_kwargs["tts_provider"] = tts_provider
    if audio_policy is not None:
        call_kwargs["audio_policy"] = audio_policy
    _handle_runtime_input(raw_input, **call_kwargs)


def _preferred_speech_locale_hint(text: str) -> str | None:
    """Only pass a locale hint when it carries signal beyond the default English path."""
    detected_locale = detect_spoken_locale(text)
    if detected_locale.startswith("ru"):
        return detected_locale
    return None


def _apply_cli_question_defaults(environ: MutableMapping[str, str] | None = None) -> MutableMapping[str, str]:
    """Enable the plain CLI question-mode defaults unless the user already overrode them."""
    env = os.environ if environ is None else environ
    env.setdefault("JARVIS_QA_LLM_ENABLED", "true")
    env.setdefault("JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED", "true")
    env.setdefault("JARVIS_QA_LLM_PROVIDER", "openai_responses")
    env.setdefault("JARVIS_QA_LLM_STRICT_MODE", "true")
    return env


def _build_default_interaction_manager(runtime_manager: RuntimeManager) -> InteractionManager:
    """Build the default interactive CLI manager with question-mode defaults applied."""
    env = _apply_cli_question_defaults()
    return InteractionManager(
        runtime_manager=runtime_manager,
        answer_backend_config=load_answer_backend_config(environ=env),
    )


def _print_qa_backend() -> None:
    """Print the current QA backend selection without mutating runtime state."""
    config = load_answer_backend_config()
    rollout_stage = str(getattr(config, "rollout_stage", "alpha_opt_in") or "alpha_opt_in")
    print(f"qa backend: {getattr(config.backend_kind, 'value', config.backend_kind)}")
    print(f"rollout stage: {rollout_stage}")
    print(f"default question path: {rollout_default_path_label(rollout_stage)}")
    print(
        "backend selection source: "
        f"{getattr(config, 'backend_selection_source', 'builtin_default')}"
    )
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
    precheck = _candidate_gate_precheck(candidate_profile, config=config)
    print(f"qa gate candidate: {candidate_profile}")
    print(f"provider/model: {getattr(config.llm.provider, 'value', config.llm.provider)} / {config.llm.model}")
    print(f"api key env: {config.llm.api_key_env} ({'present' if precheck['api_key_present'] else 'missing'})")
    print(f"strict mode: {'on' if getattr(config.llm, 'strict_mode', False) else 'off'}")
    print(f"open-domain: {'on' if precheck['open_domain_enabled'] else 'off'}")
    print(f"fallback: {'on' if precheck['fallback_enabled'] else 'off'}")
    print(f"live smoke artifact: {precheck['artifact_path']} ({precheck['artifact_status']})")
    if precheck["artifact_fresh"] is None:
        print("live smoke artifact fresh: n/a")
    elif precheck["artifact_fresh"]:
        print(f"live smoke artifact fresh: yes ({precheck['artifact_age_hours']}h)")
    else:
        print(f"live smoke artifact fresh: no ({precheck['artifact_fresh_reason'] or 'stale'})")
    if precheck["artifact_match"] is None:
        print("live smoke artifact matches profile: n/a")
    elif precheck["artifact_match"]:
        print("live smoke artifact matches profile: yes")
    else:
        print(f"live smoke artifact matches profile: no ({precheck['artifact_match_reason'] or 'mismatch'})")
    print(f"open-domain live verification: {'yes' if precheck['open_domain_verified'] else 'no'}")
    print(f"precheck: {'ready' if not precheck['blockers'] else 'blocked'}")
    for blocker in precheck["blockers"]:
        print(f"blocker: {blocker}")
    print(f"smoke command: {precheck['smoke_command']}")
    print(f"compare command: {precheck['compare_command']}")
    print("note: full comparative gate is still required for routing, fallback, latency, and usage signals.")


def _print_qa_beta() -> None:
    """Print an offline beta-decision summary without triggering networked evals."""
    config = load_answer_backend_config()
    rollout_stage = str(getattr(config, "rollout_stage", "alpha_opt_in") or "alpha_opt_in")
    candidate_profiles = ("llm_env", "llm_env_strict")
    candidate_prechecks = [_candidate_gate_precheck(candidate, config=config) for candidate in candidate_profiles]
    ready_candidates = [str(precheck["candidate_profile"]) for precheck in candidate_prechecks if not precheck["blockers"]]
    stability_ready_candidates: list[str] = []
    technically_ready_candidates: list[str] = []
    latest_candidate_evidence: dict[str, dict[str, object]] = {}
    beta_artifact_path, beta_artifact_payload, beta_artifact_error = _load_beta_readiness_artifact()
    beta_artifact_status = _beta_readiness_artifact_status(
        artifact_payload=beta_artifact_payload,
        artifact_error=beta_artifact_error,
    )
    beta_artifact_candidate = _beta_readiness_artifact_candidate(beta_artifact_payload)
    beta_artifact_candidate_selection = _beta_readiness_artifact_candidate_selection_source(beta_artifact_payload)
    manual_checklist_artifact_path, manual_checklist_artifact_payload, manual_checklist_artifact_error = (
        load_manual_beta_checklist_artifact(manual_beta_checklist_artifact_path())
    )
    (
        manual_checklist_artifact_status,
        manual_checklist_items_passed,
        manual_checklist_items_total,
        manual_checklist_complete,
    ) = manual_beta_checklist_status(manual_checklist_artifact_payload, manual_checklist_artifact_error)
    (
        manual_checklist_artifact_age_hours,
        manual_checklist_artifact_fresh,
        manual_checklist_artifact_fresh_reason,
    ) = _beta_readiness_artifact_freshness(manual_checklist_artifact_payload)
    release_review_artifact_path, release_review_artifact_payload, release_review_artifact_error = (
        load_beta_release_review_artifact(beta_release_review_artifact_path())
    )
    (
        release_review_artifact_status,
        release_review_checks_completed,
        release_review_checks_total,
        release_review_complete,
        release_review_candidate,
    ) = beta_release_review_status(release_review_artifact_payload, release_review_artifact_error)
    release_review_candidate_selection = _beta_release_review_artifact_candidate_selection_source(
        release_review_artifact_payload
    )
    (
        release_review_artifact_age_hours,
        release_review_artifact_fresh,
        release_review_artifact_fresh_reason,
    ) = _beta_readiness_artifact_freshness(release_review_artifact_payload)
    manual_checklist_pending_item_ids = manual_beta_checklist_pending_items(
        manual_checklist_artifact_payload,
        manual_checklist_artifact_error,
    )
    manual_checklist_pending_item_detail_records = manual_beta_checklist_pending_item_details(
        manual_checklist_artifact_payload,
        manual_checklist_artifact_error,
    )
    manual_checklist_command_args = manual_beta_checklist_suggested_args(
        manual_checklist_pending_item_ids,
        force_full_rerun=manual_checklist_artifact_fresh is False,
    )
    release_review_pending_check_ids = beta_release_review_pending_checks(
        release_review_artifact_payload,
        release_review_artifact_error,
    )
    beta_artifact_age_hours, beta_artifact_fresh, beta_artifact_fresh_reason = _beta_readiness_artifact_freshness(
        beta_artifact_payload
    )
    recommended_candidate: str | None = None
    print(f"qa beta stage: {rollout_stage}")
    print(f"qa beta default path: {rollout_default_path_label(rollout_stage)}")
    if len(ready_candidates) == len(candidate_prechecks):
        print(f"qa beta technical precheck: ready ({', '.join(ready_candidates)})")
    else:
        print("qa beta technical precheck: blocked")
    for precheck in candidate_prechecks:
        live_artifact_path, live_artifact_payload, live_artifact_error = _load_live_smoke_artifact(
            str(precheck["candidate_profile"])
        )
        stability_path, stability_payload, stability_error = _load_rollout_stability_artifact(
            str(precheck["candidate_profile"])
        )
        stability_status, stability_passes, stability_runs_requested = _rollout_stability_artifact_status(
            artifact_payload=stability_payload,
            artifact_error=stability_error,
        )
        stability_age_hours, stability_fresh, stability_fresh_reason = _rollout_stability_artifact_freshness(
            stability_payload
        )
        blockers = list(precheck["blockers"])
        if stability_status == "green" and stability_fresh:
            stability_ready_candidates.append(str(precheck["candidate_profile"]))
        if not blockers and stability_status == "green" and stability_fresh:
            technically_ready_candidates.append(str(precheck["candidate_profile"]))
        status = "ready" if not blockers else "blocked"
        summary_parts = [
            f"artifact={precheck['artifact_status']}",
            f"fresh={'yes' if precheck['artifact_fresh'] else 'no' if precheck['artifact_fresh'] is False else 'n/a'}",
            f"match={'yes' if precheck['artifact_match'] else 'no' if precheck['artifact_match'] is False else 'n/a'}",
            f"open-domain={'yes' if precheck['open_domain_verified'] else 'no'}",
            f"stability={stability_status}{_format_stability_ratio(stability_passes, stability_runs_requested)}",
            f"fallback={'on' if precheck['fallback_enabled'] else 'off'}",
        ]
        if stability_status != "missing":
            summary_parts.append(
                f"stability-fresh={'yes' if stability_fresh else 'no' if stability_fresh is False else 'n/a'}"
            )
        stability_blockers = _rollout_stability_blocker_summary(stability_payload)
        if stability_blockers:
            summary_parts.append(f"stability-blockers={stability_blockers}")
        stability_fallback_cases = _rollout_stability_fallback_summary(stability_payload)
        if stability_fallback_cases:
            summary_parts.append(f"stability-fallback-cases={stability_fallback_cases}")
        if stability_path is not None:
            summary_parts.append(f"stability-artifact={stability_path}")
        if stability_error is not None:
            summary_parts.append(f"stability-error={stability_error}")
        elif stability_fresh is False and stability_fresh_reason:
            summary_parts.append(f"stability-reason={stability_fresh_reason}")
        if blockers:
            summary_parts.append(f"blockers={'; '.join(blockers)}")
        latest_candidate_evidence[str(precheck["candidate_profile"])] = {
            "technical_ready": not blockers and stability_status == "green" and stability_fresh,
            "smoke_artifact_created_at": _artifact_created_at(live_artifact_payload),
            "smoke_artifact_sha256": _artifact_sha256(live_artifact_path, artifact_error=live_artifact_error),
            "stability_artifact_created_at": _artifact_created_at(stability_payload),
            "stability_artifact_sha256": _artifact_sha256(stability_path, artifact_error=stability_error),
            "smoke_artifact_status": str(precheck["artifact_status"]),
            "stability_artifact_status": str(stability_status),
            "stability_gate_passes": stability_passes,
            "stability_runs_requested": stability_runs_requested,
        }
        if live_artifact_error is not None:
            latest_candidate_evidence[str(precheck["candidate_profile"])]["smoke_artifact_error"] = live_artifact_error
        if live_artifact_path is not None:
            latest_candidate_evidence[str(precheck["candidate_profile"])]["smoke_artifact_path"] = str(live_artifact_path)
        print(f"candidate {precheck['candidate_profile']}: {status} ({', '.join(summary_parts)})")
    if "llm_env_strict" in technically_ready_candidates:
        recommended_candidate = "llm_env_strict"
    elif "llm_env" in technically_ready_candidates:
        recommended_candidate = "llm_env"
    release_review_artifact_consistent, release_review_artifact_consistency_reason = (
        beta_release_review_artifact_consistency(
            artifact_payload=release_review_artifact_payload,
            manual_checklist_artifact_payload=manual_checklist_artifact_payload,
            manual_checklist_artifact_path=manual_checklist_artifact_path,
            manual_checklist_artifact_error=manual_checklist_artifact_error,
            expected_candidate=recommended_candidate,
        )
    )
    release_review_command_args = beta_release_review_suggested_args(
        release_review_pending_check_ids,
        force_full_rerun=release_review_artifact_fresh is False or release_review_artifact_consistent is False,
    )
    beta_artifact_consistent, beta_artifact_consistency_reason = _beta_readiness_artifact_consistency(
        artifact_payload=beta_artifact_payload,
        recommended_candidate=recommended_candidate,
        technically_ready_candidates=technically_ready_candidates,
        latest_candidate_evidence=latest_candidate_evidence,
        manual_checklist_artifact_payload=manual_checklist_artifact_payload,
        manual_checklist_artifact_path=manual_checklist_artifact_path,
        manual_checklist_artifact_error=manual_checklist_artifact_error,
        release_review_artifact_payload=release_review_artifact_payload,
        release_review_artifact_path=release_review_artifact_path,
        release_review_artifact_error=release_review_artifact_error,
    )
    beta_artifact_recommendation_drift = _beta_readiness_artifact_recommendation_drift(
        artifact_payload=beta_artifact_payload,
        recommended_candidate=recommended_candidate,
    )
    print(f"qa beta recommended candidate: {recommended_candidate or 'none'}")
    if recommended_candidate is not None:
        print(f"qa beta launch command: {rollout_launch_command(recommended_candidate)}")
    print(
        "qa beta manual checklist artifact: "
        f"{manual_checklist_artifact_path} "
        f"({manual_checklist_artifact_status}{_format_stability_ratio(manual_checklist_items_passed, manual_checklist_items_total)})"
    )
    print(
        "qa beta manual checklist artifact fresh: "
        f"{'yes' if manual_checklist_artifact_fresh else 'no' if manual_checklist_artifact_fresh is False else 'n/a'}"
        f"{_format_optional_age(manual_checklist_artifact_age_hours, manual_checklist_artifact_fresh)}"
    )
    if manual_checklist_pending_item_ids:
        print(f"qa beta manual checklist pending items: {', '.join(manual_checklist_pending_item_ids)}")
        print("qa beta manual checklist helper command: qa checklist")
    print(f"qa beta manual checklist guide command: {manual_beta_checklist_guide_command()}")
    print(
        "qa beta release review artifact: "
        f"{release_review_artifact_path} "
        f"({release_review_artifact_status}{_format_stability_ratio(release_review_checks_completed, release_review_checks_total)})"
    )
    print(
        "qa beta release review artifact fresh: "
        f"{'yes' if release_review_artifact_fresh else 'no' if release_review_artifact_fresh is False else 'n/a'}"
        f"{_format_optional_age(release_review_artifact_age_hours, release_review_artifact_fresh)}"
    )
    print(
        "qa beta release review artifact consistent with latest evidence: "
        f"{'yes' if release_review_artifact_consistent else 'no' if release_review_artifact_consistent is False else 'n/a'}"
    )
    if release_review_pending_check_ids:
        print(f"qa beta release review pending checks: {', '.join(release_review_pending_check_ids)}")
    print(f"qa beta release review candidate: {release_review_candidate or 'none'}")
    print(f"qa beta release review candidate selection: {release_review_candidate_selection or 'none'}")
    print(f"qa beta recorded candidate: {beta_artifact_candidate or 'none'}")
    print(f"qa beta recorded candidate selection: {beta_artifact_candidate_selection or 'none'}")
    print(f"qa beta decision artifact: {beta_artifact_path} ({beta_artifact_status})")
    print(
        "qa beta decision artifact fresh: "
        f"{'yes' if beta_artifact_fresh else 'no' if beta_artifact_fresh is False else 'n/a'}"
    )
    print(
        "qa beta decision artifact consistent with latest evidence: "
        f"{'yes' if beta_artifact_consistent else 'no' if beta_artifact_consistent is False else 'n/a'}"
    )
    beta_artifact_manual_summary = _beta_readiness_artifact_manual_summary(beta_artifact_payload)
    if beta_artifact_manual_summary:
        print(f"qa beta recorded checks: {beta_artifact_manual_summary}")
    if beta_artifact_error is not None:
        print(f"qa beta decision artifact error: {beta_artifact_error}")
    elif beta_artifact_fresh is False and beta_artifact_fresh_reason:
        print(f"qa beta decision artifact freshness reason: {beta_artifact_fresh_reason}")
    if manual_checklist_artifact_error is not None:
        print(f"qa beta manual checklist artifact error: {manual_checklist_artifact_error}")
    elif manual_checklist_artifact_fresh is False and manual_checklist_artifact_fresh_reason:
        print(f"qa beta manual checklist artifact freshness reason: {manual_checklist_artifact_fresh_reason}")
    if release_review_artifact_error is not None:
        print(f"qa beta release review artifact error: {release_review_artifact_error}")
    elif release_review_artifact_fresh is False and release_review_artifact_fresh_reason:
        print(f"qa beta release review artifact freshness reason: {release_review_artifact_fresh_reason}")
    if release_review_artifact_consistency_reason:
        print(f"qa beta release review artifact consistency reason: {release_review_artifact_consistency_reason}")
    if beta_artifact_consistency_reason:
        print(f"qa beta decision artifact consistency reason: {beta_artifact_consistency_reason}")
    if beta_artifact_recommendation_drift:
        print(f"qa beta decision artifact drift: {beta_artifact_recommendation_drift}")
    beta_artifact_ready_current = (
        beta_artifact_status == "ready" and beta_artifact_consistent is not False and beta_artifact_fresh is not False
    )
    if beta_artifact_ready_current:
        print("qa beta decision: recorded as ready for explicit beta_question_default review; default remains unchanged")
        print(f"qa beta stage preview command: {rollout_stage_preview_command('beta_question_default')}")
    elif beta_artifact_status == "ready":
        print("qa beta decision: recorded beta readiness is stale against latest evidence; review must be repeated")
    else:
        print("qa beta decision: blocked until beta_question_default is explicitly approved")
    if len(stability_ready_candidates) == len(candidate_prechecks):
        print(f"qa beta latest stability evidence: clean ({', '.join(stability_ready_candidates)})")
    else:
        print("qa beta latest stability evidence: incomplete")
    if beta_artifact_ready_current:
        print(
            "next beta step: offline beta evidence is already recorded; any rollout-stage or default-path change "
            "remains a separate explicit product decision."
        )
    elif not manual_checklist_complete or manual_checklist_artifact_fresh is False:
        print("next beta step: complete the manual beta checklist artifact before release sign-off.")
        print(f"manual checklist command: python3 -m qa.manual_beta_checklist {manual_checklist_command_args} --write-artifact")
        if manual_checklist_pending_item_detail_records:
            for line in manual_beta_checklist_detail_lines(
                manual_checklist_pending_item_detail_records,
                heading="qa beta manual checklist scenario guide:",
            ):
                print(line)
    elif recommended_candidate is None:
        print("next beta step: get one candidate back to fresh green smoke + stability before manual beta sign-off.")
    elif (
        not release_review_complete
        or release_review_candidate != recommended_candidate
        or release_review_artifact_fresh is False
        or release_review_artifact_consistent is False
    ):
        print(
            "next beta step: "
            f"record the beta release review artifact for {recommended_candidate} after latency/cost review and sign-off."
        )
        print(
            "release review command: "
            "python3 -m qa.beta_release_review "
            f"--candidate-profile {recommended_candidate} "
            f"{release_review_command_args} --write-artifact"
        )
    elif recommended_candidate is not None:
        print(
            "next beta step: "
            f"record beta readiness for {recommended_candidate} against the latest technical and manual evidence."
        )
        print(
            "beta readiness command: "
            "python3 -m qa.beta_readiness "
            f"--candidate-profile {recommended_candidate} --write-artifact"
        )
    print("manual checklist doc: docs/manual_verification_commands.md")
    print("decision gate doc: docs/llm_default_decision_gate.md")
    print("note: this helper is offline; it does not run smoke, gate, or stability and does not switch the default.")


def _print_qa_checklist() -> None:
    """Print the current manual beta checklist helper summary."""
    artifact_path, existing_payload, existing_error = load_manual_beta_checklist_artifact()
    if existing_error is not None:
        print(f"qa checklist artifact error: {existing_error}")
        print(f"artifact: {artifact_path}")
        return
    record = build_manual_beta_checklist_record(existing_payload=existing_payload)
    print(format_manual_beta_checklist_record(record))


def _print_qa_release_review() -> None:
    """Print the current beta release-review helper summary."""
    artifact_path, existing_payload, existing_error = load_beta_release_review_artifact()
    if existing_error is not None:
        print(f"qa release review artifact error: {existing_error}")
        print(f"artifact: {artifact_path}")
        return
    record = build_beta_release_review_record(existing_payload=existing_payload)
    print(format_beta_release_review_record(record))


def _print_qa_readiness() -> None:
    """Print the current beta readiness helper summary."""
    record = build_beta_readiness_record()
    print(format_beta_readiness_record(record))


def _print_voice_readiness() -> None:
    """Print the current offline voice-readiness helper summary."""
    record = build_voice_readiness_record()
    print(format_voice_readiness_record(record))


def _print_voice_mode() -> None:
    """Print the current bounded voice-conversation mode summary."""
    print(format_voice_mode_status(build_voice_mode_status()))


def _print_voice_last(voice_session_state: VoiceSessionState | None) -> None:
    """Print the last current-session voice event summary."""
    print(format_voice_last_event(voice_session_state))


def _print_voice_status(
    *,
    speak_enabled: bool,
    telemetry: VoiceTelemetryCollector | None,
) -> None:
    """Print the current CLI voice-session status and counters."""
    active_telemetry = telemetry or build_default_voice_telemetry()
    print(
        format_voice_session_status(
            build_voice_session_status(
                speak_enabled=speak_enabled,
                telemetry_snapshot=active_telemetry.snapshot(),
            )
        )
    )


def _write_voice_readiness() -> None:
    """Persist the current offline voice-readiness artifact when unblocked."""
    record = build_voice_readiness_record()
    if not record.voice_ready:
        print(format_voice_readiness_record(record))
        print("voice readiness is still blocked; refusing to write final artifact")
        return
    artifact_path = write_voice_readiness_artifact(record)
    print(f"wrote voice readiness artifact: {artifact_path}")


def _print_voice_gate() -> None:
    """Print the current offline voice rollout gate verdict."""
    report = build_voice_readiness_gate_report()
    print(format_voice_readiness_gate_report(report))


def _print_voice_telemetry(telemetry: VoiceTelemetryCollector | None) -> None:
    """Print the current in-memory voice telemetry summary."""
    active_telemetry = telemetry or build_default_voice_telemetry()
    print(format_voice_telemetry_snapshot(active_telemetry.snapshot()))


def _print_voice_telemetry_artifact() -> None:
    """Print the saved voice telemetry artifact summary."""
    artifact_path, artifact_status, artifact_created_at, snapshot, artifact_error = load_voice_telemetry_snapshot()
    print(
        format_voice_telemetry_artifact_summary(
            artifact_path=artifact_path,
            artifact_status=artifact_status,
            artifact_created_at=artifact_created_at,
            snapshot=snapshot,
            artifact_error=artifact_error,
        )
    )


def _reset_voice_telemetry(telemetry: VoiceTelemetryCollector | None) -> None:
    """Clear the current in-memory voice telemetry collector when present."""
    if telemetry is not None:
        telemetry.clear()
    print("Voice telemetry reset.")


def _write_voice_telemetry(telemetry: VoiceTelemetryCollector | None) -> None:
    """Persist the current in-memory voice telemetry snapshot to tmp/qa."""
    active_telemetry = telemetry or build_default_voice_telemetry()
    artifact_path = write_voice_telemetry_artifact(active_telemetry.snapshot())
    print(f"wrote voice telemetry artifact: {artifact_path}")


def _candidate_gate_precheck(candidate_profile: str, *, config: object) -> dict[str, object]:
    """Collect one candidate's offline gate precheck state."""
    fallback_enabled = candidate_profile != "llm_env_strict"
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
    return {
        "candidate_profile": candidate_profile,
        "fallback_enabled": fallback_enabled,
        "api_key_present": api_key_present,
        "artifact_path": artifact_path,
        "artifact_status": artifact_status,
        "artifact_age_hours": artifact_age_hours,
        "artifact_fresh": artifact_fresh,
        "artifact_fresh_reason": artifact_fresh_reason,
        "artifact_match": artifact_match,
        "artifact_match_reason": artifact_match_reason,
        "open_domain_enabled": open_domain_enabled,
        "open_domain_verified": open_domain_verified,
        "blockers": blockers,
        "smoke_command": rollout_smoke_command(candidate_profile),
        "compare_command": rollout_compare_command(candidate_profile),
    }


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


def _load_rollout_stability_artifact(candidate_profile: str) -> tuple[Path, dict[str, object] | None, str | None]:
    """Return the current rollout-stability artifact plus any parse error."""
    artifact_path = rollout_stability_artifact_path_for_candidate(candidate_profile)
    if not artifact_path.exists():
        return artifact_path, None, None
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return artifact_path, None, f"{type(exc).__name__}: {exc}"
    if not isinstance(payload, dict):
        return artifact_path, None, "ValueError: rollout stability artifact must be a JSON object."
    return artifact_path, payload, None


def _load_beta_readiness_artifact() -> tuple[Path, dict[str, object] | None, str | None]:
    """Return the current beta-readiness artifact plus any parse error."""
    artifact_path = beta_readiness_artifact_path()
    if not artifact_path.exists():
        return artifact_path, None, None
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return artifact_path, None, f"{type(exc).__name__}: {exc}"
    if not isinstance(payload, dict):
        return artifact_path, None, "ValueError: beta readiness artifact must be a JSON object."
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


def _rollout_stability_artifact_freshness(
    artifact_payload: dict[str, object] | None,
) -> tuple[float | None, bool | None, str | None]:
    """Return rollout-stability artifact age plus a freshness decision."""
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


def _rollout_stability_artifact_status(
    *,
    artifact_payload: dict[str, object] | None,
    artifact_error: str | None,
) -> tuple[str, int | None, int | None]:
    """Return one short operator-friendly rollout-stability artifact status."""
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


def _format_stability_ratio(gate_passes: int | None, runs_requested: int | None) -> str:
    if gate_passes is None or runs_requested is None:
        return ""
    return f"({gate_passes}/{runs_requested})"


def _format_optional_age(age_hours: float | None, fresh: bool | None) -> str:
    if age_hours is None or fresh is None:
        return ""
    return f" ({age_hours}h)"


def _rollout_stability_blocker_summary(artifact_payload: dict[str, object] | None) -> str:
    report = dict((artifact_payload or {}).get("report", {}) or {})
    blocker_counts = report.get("blocker_counts")
    if not isinstance(blocker_counts, dict):
        return ""
    summaries: list[str] = []
    for blocker, count in blocker_counts.items():
        if not isinstance(blocker, str) or not isinstance(count, int):
            continue
        summaries.append(f"{blocker} x{count}")
    return "; ".join(summaries)


def _rollout_stability_fallback_summary(artifact_payload: dict[str, object] | None) -> str:
    report = dict((artifact_payload or {}).get("report", {}) or {})
    fallback_case_counts = report.get("fallback_case_counts")
    if not isinstance(fallback_case_counts, dict):
        return ""
    summaries: list[str] = []
    for case_id, count in fallback_case_counts.items():
        if not isinstance(case_id, str) or not isinstance(count, int):
            continue
        summaries.append(f"{case_id} x{count}")
    return "; ".join(summaries)


def _beta_readiness_artifact_status(
    *,
    artifact_payload: dict[str, object] | None,
    artifact_error: str | None,
) -> str:
    if artifact_error is not None:
        return "invalid"
    if artifact_payload is None:
        return "missing"
    report = artifact_payload.get("report")
    if not isinstance(report, dict):
        return "invalid"
    if bool(report.get("beta_ready")):
        return "ready"
    return "blocked"


def _beta_readiness_artifact_freshness(
    artifact_payload: dict[str, object] | None,
) -> tuple[float | None, bool | None, str | None]:
    """Return beta-readiness artifact age plus a freshness decision."""
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


def _beta_readiness_artifact_consistency(
    *,
    artifact_payload: dict[str, object] | None,
    recommended_candidate: str | None,
    technically_ready_candidates: list[str],
    latest_candidate_evidence: dict[str, dict[str, object]],
    manual_checklist_artifact_payload: dict[str, object] | None,
    manual_checklist_artifact_path: Path | None,
    manual_checklist_artifact_error: str | None,
    release_review_artifact_payload: dict[str, object] | None,
    release_review_artifact_path: Path | None,
    release_review_artifact_error: str | None,
) -> tuple[bool | None, str | None]:
    if artifact_payload is None:
        return None, None
    report = dict(artifact_payload.get("report", {}) or {})
    recorded_manual_checklist_sha256 = str(report.get("manual_checklist_artifact_sha256", "") or "").strip()
    latest_manual_checklist_sha256 = _artifact_sha256(
        manual_checklist_artifact_path, artifact_error=manual_checklist_artifact_error
    )
    if not recorded_manual_checklist_sha256:
        return False, "recorded manual checklist snapshot is missing"
    if not latest_manual_checklist_sha256:
        return False, "latest manual checklist artifact is missing or unreadable"
    (
        _manual_checklist_age_hours,
        manual_checklist_fresh,
        manual_checklist_fresh_reason,
    ) = _beta_readiness_artifact_freshness(manual_checklist_artifact_payload)
    if manual_checklist_artifact_payload is not None and manual_checklist_artifact_error is None and manual_checklist_fresh is not True:
        if manual_checklist_fresh_reason:
            return False, f"latest manual checklist artifact is stale: {manual_checklist_fresh_reason}"
        return False, "latest manual checklist artifact is stale"
    if recorded_manual_checklist_sha256 != latest_manual_checklist_sha256:
        return False, "recorded manual checklist artifact fingerprint no longer matches the latest artifact"
    recorded_manual_checklist_created_at = str(report.get("manual_checklist_artifact_created_at", "") or "").strip()
    latest_manual_checklist_created_at = str(_artifact_created_at(manual_checklist_artifact_payload) or "").strip()
    if (
        recorded_manual_checklist_created_at
        and latest_manual_checklist_created_at
        and recorded_manual_checklist_created_at != latest_manual_checklist_created_at
    ):
        return False, "recorded manual checklist artifact snapshot no longer matches the latest artifact"
    recorded_release_review_sha256 = str(report.get("release_review_artifact_sha256", "") or "").strip()
    latest_release_review_sha256 = _artifact_sha256(
        release_review_artifact_path, artifact_error=release_review_artifact_error
    )
    if not recorded_release_review_sha256:
        return False, "recorded beta release review snapshot is missing"
    if not latest_release_review_sha256:
        return False, "latest beta release review artifact is missing or unreadable"
    (
        _release_review_age_hours,
        release_review_fresh,
        release_review_fresh_reason,
    ) = _beta_readiness_artifact_freshness(release_review_artifact_payload)
    if release_review_artifact_payload is not None and release_review_artifact_error is None and release_review_fresh is not True:
        if release_review_fresh_reason:
            return False, f"latest beta release review artifact is stale: {release_review_fresh_reason}"
        return False, "latest beta release review artifact is stale"
    if recorded_release_review_sha256 != latest_release_review_sha256:
        return False, "recorded beta release review artifact fingerprint no longer matches the latest artifact"
    recorded_release_review_created_at = str(report.get("release_review_artifact_created_at", "") or "").strip()
    latest_release_review_created_at = str(_artifact_created_at(release_review_artifact_payload) or "").strip()
    if (
        recorded_release_review_created_at
        and latest_release_review_created_at
        and recorded_release_review_created_at != latest_release_review_created_at
    ):
        return False, "recorded beta release review artifact snapshot no longer matches the latest artifact"
    recorded_release_review_candidate = str(report.get("release_review_artifact_candidate", "") or "").strip()
    latest_release_review_candidate = str(
        dict((release_review_artifact_payload or {}).get("report", {}) or {}).get("candidate_profile", "") or ""
    ).strip()
    if recorded_release_review_candidate and latest_release_review_candidate:
        if recorded_release_review_candidate != latest_release_review_candidate:
            return False, "recorded beta release review candidate no longer matches the latest artifact"
    chosen_candidate = str(report.get("chosen_candidate", "") or "").strip()
    if not chosen_candidate:
        return False, "recorded candidate is missing"
    candidate_selection_source = str(report.get("candidate_selection_source", "") or "").strip()
    if candidate_selection_source != "explicit":
        if candidate_selection_source:
            return (
                False,
                f"recorded candidate selection source is {candidate_selection_source}; final beta artifact requires explicit operator choice",
            )
        return False, "recorded candidate selection source is missing; final beta artifact requires explicit operator choice"
    if chosen_candidate not in technically_ready_candidates:
        return False, f"recorded candidate {chosen_candidate} is not technically ready on latest artifacts"
    recorded_candidate_states = dict(report.get("candidate_states", {}) or {})
    recorded_candidate_state = dict(recorded_candidate_states.get(chosen_candidate, {}) or {})
    latest_candidate_state = dict(latest_candidate_evidence.get(chosen_candidate, {}) or {})
    if not recorded_candidate_state:
        return False, f"recorded evidence snapshot for candidate {chosen_candidate} is missing"
    recorded_smoke_sha256 = str(recorded_candidate_state.get("smoke_artifact_sha256", "") or "").strip()
    latest_smoke_sha256 = str(latest_candidate_state.get("smoke_artifact_sha256", "") or "").strip()
    if recorded_smoke_sha256 and latest_smoke_sha256 and recorded_smoke_sha256 != latest_smoke_sha256:
        return False, f"recorded smoke artifact fingerprint for {chosen_candidate} no longer matches the latest artifact"
    recorded_smoke_created_at = str(recorded_candidate_state.get("smoke_artifact_created_at", "") or "").strip()
    latest_smoke_created_at = str(latest_candidate_state.get("smoke_artifact_created_at", "") or "").strip()
    if recorded_smoke_created_at and latest_smoke_created_at and recorded_smoke_created_at != latest_smoke_created_at:
        return False, f"recorded smoke artifact snapshot for {chosen_candidate} no longer matches the latest artifact"
    recorded_stability_sha256 = str(recorded_candidate_state.get("stability_artifact_sha256", "") or "").strip()
    latest_stability_sha256 = str(latest_candidate_state.get("stability_artifact_sha256", "") or "").strip()
    if recorded_stability_sha256 and latest_stability_sha256 and recorded_stability_sha256 != latest_stability_sha256:
        return False, f"recorded stability artifact fingerprint for {chosen_candidate} no longer matches the latest artifact"
    recorded_stability_created_at = str(recorded_candidate_state.get("stability_artifact_created_at", "") or "").strip()
    latest_stability_created_at = str(latest_candidate_state.get("stability_artifact_created_at", "") or "").strip()
    if (
        recorded_stability_created_at
        and latest_stability_created_at
        and recorded_stability_created_at != latest_stability_created_at
    ):
        return False, f"recorded stability artifact snapshot for {chosen_candidate} no longer matches the latest artifact"
    if bool(report.get("beta_ready")) and not technically_ready_candidates:
        return False, "latest technical evidence is not green for any candidate"
    if recommended_candidate is None:
        return True, None
    recorded_recommended_candidate = str(report.get("recommended_candidate", "") or "").strip()
    if recorded_recommended_candidate and recorded_recommended_candidate != recommended_candidate:
        return True, (
            f"latest recommended candidate is {recommended_candidate}, "
            f"but the recorded artifact was created when {recorded_recommended_candidate} was preferred"
        )
    return True, None


def _beta_readiness_artifact_recommendation_drift(
    artifact_payload: dict[str, object] | None,
    recommended_candidate: str | None,
) -> str | None:
    report = dict((artifact_payload or {}).get("report", {}) or {})
    if not report:
        return None
    chosen_candidate = str(report.get("chosen_candidate", "") or "").strip()
    if not chosen_candidate or not recommended_candidate or chosen_candidate == recommended_candidate:
        return None
    return f"recorded candidate {chosen_candidate} differs from the latest recommended candidate {recommended_candidate}"


def _beta_readiness_artifact_candidate(artifact_payload: dict[str, object] | None) -> str | None:
    report = dict((artifact_payload or {}).get("report", {}) or {})
    candidate = str(report.get("chosen_candidate", "") or "").strip()
    return candidate or None


def _beta_readiness_artifact_candidate_selection_source(artifact_payload: dict[str, object] | None) -> str | None:
    report = dict((artifact_payload or {}).get("report", {}) or {})
    candidate_selection_source = str(report.get("candidate_selection_source", "") or "").strip()
    return candidate_selection_source or None


def _beta_release_review_artifact_candidate_selection_source(artifact_payload: dict[str, object] | None) -> str | None:
    report = dict((artifact_payload or {}).get("report", {}) or {})
    candidate_selection_source = str(report.get("candidate_selection_source", "") or "").strip()
    return candidate_selection_source or None


def _beta_readiness_artifact_manual_summary(artifact_payload: dict[str, object] | None) -> str:
    report = dict((artifact_payload or {}).get("report", {}) or {})
    if not report:
        return ""
    checks = [
        ("manual", bool(report.get("manual_checklist_completed", False))),
        ("review", bool(report.get("release_review_artifact_completed", False))),
        ("latency", bool(report.get("latency_review_completed", False))),
        ("cost", bool(report.get("cost_review_completed", False))),
        ("signoff", bool(report.get("operator_signoff_completed", False))),
        ("approval", bool(report.get("product_approval_completed", False))),
    ]
    return ", ".join(f"{name}={'yes' if passed else 'no'}" for name, passed in checks)


def _artifact_created_at(artifact_payload: dict[str, object] | None) -> str | None:
    created_at = str((artifact_payload or {}).get("created_at", "") or "").strip()
    return created_at or None


def _artifact_sha256(artifact_path: Path | None, *, artifact_error: str | None) -> str | None:
    if artifact_path is None or artifact_error is not None or not artifact_path.exists():
        return None
    try:
        return hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    except OSError:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
