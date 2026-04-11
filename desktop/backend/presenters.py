"""Adapters from JARVIS core results to desktop view models."""

from __future__ import annotations

from typing import Any

from desktop.backend.view_models import PendingPromptViewModel, StatusViewModel, TranscriptEntry, TurnViewModel

_BUSY_RUNTIME_STATES = {
    "parsing",
    "validating",
    "planning",
    "executing",
    "awaiting_clarification",
    "awaiting_confirmation",
}


def present_interaction_result(raw_input: str, result: object) -> TurnViewModel:
    """Convert one core interaction result into desktop-friendly view models."""
    visibility = dict(getattr(result, "visibility", {}) or {})
    interaction_mode = str(getattr(getattr(result, "interaction_mode", ""), "value", getattr(result, "interaction_mode", "")))
    status = _build_status(interaction_mode=interaction_mode, visibility=visibility)
    pending_prompt = _build_pending_prompt(result=result, visibility=visibility)
    entries = _build_entries(
        interaction_mode=interaction_mode,
        visibility=visibility,
        pending_prompt=pending_prompt,
    )
    return TurnViewModel(
        input_text=str(raw_input),
        interaction_mode=interaction_mode,
        entries=entries,
        status=status,
        pending_prompt=pending_prompt,
        visibility=visibility,
        metadata=dict(getattr(result, "metadata", {}) or {}),
    )


def _build_status(*, interaction_mode: str, visibility: dict[str, Any]) -> StatusViewModel:
    runtime_state = str(visibility.get("runtime_state", "idle") or "idle")
    if interaction_mode != "command":
        runtime_state = "idle"
    return StatusViewModel(
        interaction_mode=interaction_mode or None,
        runtime_state=runtime_state,
        command_summary=_text_or_none(visibility.get("command_summary")),
        current_step=_text_or_none(visibility.get("current_step")),
        blocked_reason=_text_or_none(visibility.get("blocked_reason")),
        next_step_hint=_text_or_none(visibility.get("next_step_hint")),
        completion_result=_text_or_none(visibility.get("completion_result")),
        failure_message=_text_or_none(visibility.get("failure_message")),
        can_cancel=bool(visibility.get("can_cancel", False)),
        busy=runtime_state in _BUSY_RUNTIME_STATES,
    )


def _build_pending_prompt(*, result: object, visibility: dict[str, Any]) -> PendingPromptViewModel | None:
    confirmation_request = visibility.get("confirmation_request")
    if isinstance(confirmation_request, dict):
        message = _text_or_none(confirmation_request.get("message"))
        if message:
            return PendingPromptViewModel(
                kind="confirmation",
                message=message,
                options=["confirm", "cancel"],
                metadata=dict(confirmation_request),
            )

    clarification_message = _text_or_none(visibility.get("clarification_question"))
    if clarification_message:
        clarification_request = getattr(result, "clarification_request", None)
        options = [
            str(option).strip()
            for option in list(getattr(clarification_request, "options", []) or [])
            if str(option).strip()
        ]
        return PendingPromptViewModel(
            kind="clarification",
            message=clarification_message,
            options=options,
            metadata={"code": str(getattr(clarification_request, "code", "") or "").strip() or None},
        )

    return None


def _build_entries(
    *,
    interaction_mode: str,
    visibility: dict[str, Any],
    pending_prompt: PendingPromptViewModel | None,
) -> list[TranscriptEntry]:
    entries: list[TranscriptEntry] = []

    if interaction_mode == "question":
        answer_text = _text_or_none(visibility.get("answer_text"))
        if answer_text:
            entries.append(
                TranscriptEntry(
                    role="assistant",
                    text=answer_text,
                    entry_kind="answer",
                    metadata={
                        "summary": _text_or_none(visibility.get("answer_summary")),
                        "answer_kind": _text_or_none(visibility.get("answer_kind")),
                        "answer_provenance": _text_or_none(visibility.get("answer_provenance")),
                        "sources": list(visibility.get("answer_sources", []) or []),
                        "source_labels": list(visibility.get("answer_source_labels", []) or []),
                        "source_attributions": list(visibility.get("answer_source_attributions", []) or []),
                    },
                )
            )
        warning = _text_or_none(visibility.get("answer_warning"))
        if warning:
            entries.append(TranscriptEntry(role="system", text=warning, entry_kind="warning"))
        failure = _text_or_none(visibility.get("failure_message"))
        if failure and not answer_text:
            entries.append(TranscriptEntry(role="system", text=failure, entry_kind="error"))
        return entries

    if pending_prompt is not None:
        entries.append(
            TranscriptEntry(
                role="assistant",
                text=pending_prompt.message,
                entry_kind="prompt",
                metadata={"prompt_kind": pending_prompt.kind, "options": list(pending_prompt.options)},
            )
        )
        return entries

    failure = _text_or_none(visibility.get("failure_message"))
    if failure:
        entries.append(TranscriptEntry(role="system", text=failure, entry_kind="error"))
        return entries

    completion_result = _text_or_none(visibility.get("completion_result"))
    if completion_result:
        entries.append(TranscriptEntry(role="assistant", text=completion_result, entry_kind="result"))
        return entries

    current_step = _text_or_none(visibility.get("current_step"))
    if current_step:
        entries.append(TranscriptEntry(role="system", text=current_step, entry_kind="status"))
        return entries

    blocked_reason = _text_or_none(visibility.get("blocked_reason"))
    if blocked_reason:
        entries.append(TranscriptEntry(role="assistant", text=blocked_reason, entry_kind="prompt"))
        return entries

    command_summary = _text_or_none(visibility.get("command_summary"))
    if command_summary:
        entries.append(TranscriptEntry(role="system", text=command_summary, entry_kind="status"))

    return entries


def _text_or_none(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None
