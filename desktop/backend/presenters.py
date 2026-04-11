"""Adapters from JARVIS core results to desktop view models."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from desktop.backend.view_models import (
    AnswerSourceViewModel,
    CommandProgressViewModel,
    EntrySurfaceViewModel,
    PendingPromptViewModel,
    PromptActionViewModel,
    ResultListItemViewModel,
    ResultListViewModel,
    SourceAttributionViewModel,
    StatusViewModel,
    TranscriptEntry,
    TurnViewModel,
)

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
    result_lists = _build_result_lists(visibility=visibility)
    command_progress = _build_command_progress(interaction_mode=interaction_mode, visibility=visibility)
    status = _build_status(
        interaction_mode=interaction_mode,
        visibility=visibility,
        result_lists=result_lists,
    )
    pending_prompt = _build_pending_prompt(result=result, visibility=visibility)
    entries = _build_entries(
        interaction_mode=interaction_mode,
        visibility=visibility,
        pending_prompt=pending_prompt,
        command_progress=command_progress,
        result_lists=result_lists,
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


def _build_status(
    *,
    interaction_mode: str,
    visibility: dict[str, Any],
    result_lists: tuple[ResultListViewModel, ...],
) -> StatusViewModel:
    runtime_state = str(visibility.get("runtime_state", "idle") or "idle")
    if interaction_mode != "command":
        runtime_state = "idle"
    return StatusViewModel(
        interaction_mode=interaction_mode or None,
        runtime_state=runtime_state,
        command_summary=_text_or_none(visibility.get("command_summary")),
        current_step=_text_or_none(visibility.get("current_step")),
        completed_steps=tuple(_normalized_string_list(visibility.get("completed_steps"))),
        blocked_reason=_text_or_none(visibility.get("blocked_reason")),
        next_step_hint=_text_or_none(visibility.get("next_step_hint")),
        completion_result=_text_or_none(visibility.get("completion_result")),
        failure_message=_text_or_none(visibility.get("failure_message")),
        result_lists=result_lists,
        can_cancel=bool(visibility.get("can_cancel", False)),
        busy=runtime_state in _BUSY_RUNTIME_STATES,
    )


def _build_pending_prompt(*, result: object, visibility: dict[str, Any]) -> PendingPromptViewModel | None:
    confirmation_request = visibility.get("confirmation_request")
    if isinstance(confirmation_request, dict):
        message = _text_or_none(confirmation_request.get("message"))
        if message:
            actions = _prompt_actions_for_options(["confirm", "cancel"])
            return PendingPromptViewModel(
                kind="confirmation",
                message=message,
                options=["confirm", "cancel"],
                actions=actions,
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
            actions=_prompt_actions_for_options(options),
            metadata={"code": str(getattr(clarification_request, "code", "") or "").strip() or None},
        )

    return None


def _build_entries(
    *,
    interaction_mode: str,
    visibility: dict[str, Any],
    pending_prompt: PendingPromptViewModel | None,
    command_progress: CommandProgressViewModel | None,
    result_lists: tuple[ResultListViewModel, ...],
) -> list[TranscriptEntry]:
    entries: list[TranscriptEntry] = []

    if interaction_mode == "question":
        answer_text = _text_or_none(visibility.get("answer_text"))
        if answer_text:
            source_models = _build_answer_sources(visibility=visibility)
            source_attributions = _build_source_attributions(visibility=visibility)
            entries.append(
                TranscriptEntry(
                    role="assistant",
                    text=answer_text,
                    entry_kind="answer",
                    surface=EntrySurfaceViewModel(
                        surface_kind="question_answer",
                        answer_summary=_text_or_none(visibility.get("answer_summary")),
                        answer_kind=_text_or_none(visibility.get("answer_kind")),
                        answer_provenance=_text_or_none(visibility.get("answer_provenance")),
                        sources=source_models,
                        source_attributions=source_attributions,
                    ),
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
            entries.append(
                TranscriptEntry(
                    role="system",
                    text=warning,
                    entry_kind="warning",
                    surface=EntrySurfaceViewModel(surface_kind="system_warning"),
                )
            )
        failure = _text_or_none(visibility.get("failure_message"))
        if failure and not answer_text:
            entries.append(
                TranscriptEntry(
                    role="system",
                    text=failure,
                    entry_kind="error",
                    surface=EntrySurfaceViewModel(surface_kind="question_failure"),
                )
            )
        return entries

    if pending_prompt is not None:
        entries.append(
            TranscriptEntry(
                role="assistant",
                text=pending_prompt.message,
                entry_kind="prompt",
                surface=EntrySurfaceViewModel(
                    surface_kind=f"{pending_prompt.kind}_prompt",
                    command_progress=command_progress,
                    result_lists=result_lists,
                    actions=pending_prompt.actions,
                ),
                metadata={"prompt_kind": pending_prompt.kind, "options": list(pending_prompt.options)},
            )
        )
        return entries

    failure = _text_or_none(visibility.get("failure_message"))
    if failure:
        entries.append(
            TranscriptEntry(
                role="system",
                text=failure,
                entry_kind="error",
                surface=EntrySurfaceViewModel(
                    surface_kind="command_failure" if interaction_mode == "command" else "error",
                    command_progress=command_progress,
                    result_lists=result_lists,
                ),
            )
        )
        return entries

    completion_result = _text_or_none(visibility.get("completion_result"))
    if completion_result:
        entries.append(
            TranscriptEntry(
                role="assistant",
                text=completion_result,
                entry_kind="result",
                surface=EntrySurfaceViewModel(
                    surface_kind="command_completion" if interaction_mode == "command" else "result",
                    command_progress=command_progress,
                    result_lists=result_lists,
                ),
            )
        )
        return entries

    current_step = _text_or_none(visibility.get("current_step"))
    if current_step:
        entries.append(
            TranscriptEntry(
                role="system",
                text=current_step,
                entry_kind="status",
                surface=EntrySurfaceViewModel(
                    surface_kind="command_progress" if interaction_mode == "command" else "status",
                    command_progress=command_progress,
                    result_lists=result_lists,
                ),
            )
        )
        return entries

    blocked_reason = _text_or_none(visibility.get("blocked_reason"))
    if blocked_reason:
        entries.append(
            TranscriptEntry(
                role="assistant",
                text=blocked_reason,
                entry_kind="prompt",
                surface=EntrySurfaceViewModel(
                    surface_kind="command_blocked" if interaction_mode == "command" else "prompt",
                    command_progress=command_progress,
                    result_lists=result_lists,
                ),
            )
        )
        return entries

    command_summary = _text_or_none(visibility.get("command_summary"))
    if command_summary:
        entries.append(
            TranscriptEntry(
                role="system",
                text=command_summary,
                entry_kind="status",
                surface=EntrySurfaceViewModel(
                    surface_kind="command_progress" if interaction_mode == "command" else "status",
                    command_progress=command_progress,
                    result_lists=result_lists,
                ),
            )
        )

    return entries


def _build_command_progress(
    *,
    interaction_mode: str,
    visibility: dict[str, Any],
) -> CommandProgressViewModel | None:
    if interaction_mode != "command":
        return None
    return CommandProgressViewModel(
        runtime_state=_text_or_none(visibility.get("runtime_state")) or "idle",
        command_summary=_text_or_none(visibility.get("command_summary")),
        current_step=_text_or_none(visibility.get("current_step")),
        completed_steps=tuple(_normalized_string_list(visibility.get("completed_steps"))),
        blocked_reason=_text_or_none(visibility.get("blocked_reason")),
        next_step_hint=_text_or_none(visibility.get("next_step_hint")),
    )


def _build_result_lists(*, visibility: dict[str, Any]) -> tuple[ResultListViewModel, ...]:
    result_lists: list[ResultListViewModel] = []

    search_results = visibility.get("search_results")
    if isinstance(search_results, dict):
        search_list = _build_search_results_list(search_results)
        if search_list is not None:
            result_lists.append(search_list)

    window_results = visibility.get("window_results")
    if isinstance(window_results, dict):
        window_list = _build_window_results_list(window_results)
        if window_list is not None:
            result_lists.append(window_list)

    return tuple(result_lists)


def _build_search_results_list(payload: dict[str, Any]) -> ResultListViewModel | None:
    raw_matches = payload.get("matches")
    if not isinstance(raw_matches, list):
        return None

    items: list[ResultListItemViewModel] = []
    for index, match in enumerate(raw_matches, start=1):
        if not isinstance(match, dict):
            continue
        path = _text_or_none(match.get("path"))
        name = _text_or_none(match.get("name")) or (Path(path).name if path else None)
        match_type = _text_or_none(match.get("type"))
        title = name or path
        if not title:
            continue
        subtitle = path if path and path != title else None
        items.append(
            ResultListItemViewModel(
                item_id=f"search-{index}",
                title=title,
                subtitle=subtitle,
                detail=match_type,
            )
        )

    total_matches = payload.get("total_matches")
    total_summary = f"{total_matches} match" if total_matches == 1 else f"{total_matches} matches" if isinstance(total_matches, int) else None
    query = _text_or_none(payload.get("query"))
    scope_path = _text_or_none(payload.get("scope_path"))
    scope_name = Path(scope_path).name if scope_path else None
    summary_parts = [part for part in (total_summary, f'query "{query}"' if query else None, f"in {scope_name}" if scope_name else None) if part]
    return ResultListViewModel(
        kind="search_results",
        title="Search Results",
        summary=", ".join(summary_parts) or None,
        items=tuple(items),
    )


def _build_window_results_list(payload: dict[str, Any]) -> ResultListViewModel | None:
    raw_windows = payload.get("windows")
    if not isinstance(raw_windows, list):
        return None

    items: list[ResultListItemViewModel] = []
    for index, window in enumerate(raw_windows, start=1):
        if not isinstance(window, dict):
            continue
        app_name = _text_or_none(window.get("app_name"))
        window_title = _text_or_none(window.get("window_title"))
        window_id = window.get("window_id")
        title = window_title or app_name or (f"Window #{window_id}" if isinstance(window_id, int) else None)
        if not title:
            continue
        subtitle = app_name if app_name and app_name != title else None
        detail = f"Window #{window_id}" if isinstance(window_id, int) else None
        items.append(
            ResultListItemViewModel(
                item_id=f"window-{index}",
                title=title,
                subtitle=subtitle,
                detail=detail,
            )
        )

    total_windows = payload.get("total_windows")
    total_summary = (
        f"{total_windows} window" if total_windows == 1 else f"{total_windows} windows"
        if isinstance(total_windows, int)
        else None
    )
    filter_name = _text_or_none(payload.get("filter"))
    summary_parts = [part for part in (total_summary, f"filter {filter_name}" if filter_name else None) if part]
    return ResultListViewModel(
        kind="window_results",
        title="Visible Windows",
        summary=", ".join(summary_parts) or None,
        items=tuple(items),
    )


def _build_answer_sources(*, visibility: dict[str, Any]) -> tuple[AnswerSourceViewModel, ...]:
    sources = list(visibility.get("answer_sources", []) or [])
    labels = list(visibility.get("answer_source_labels", []) or [])
    models: list[AnswerSourceViewModel] = []
    for index, raw_path in enumerate(sources):
        path = _text_or_none(raw_path)
        if not path:
            continue
        label = _text_or_none(labels[index] if index < len(labels) else None) or Path(path).name or path
        models.append(AnswerSourceViewModel(path=path, label=label))
    return tuple(models)


def _build_source_attributions(*, visibility: dict[str, Any]) -> tuple[SourceAttributionViewModel, ...]:
    sources = _build_answer_sources(visibility=visibility)
    labels_by_path = {source.path: source.label for source in sources}
    attributions: list[SourceAttributionViewModel] = []
    for raw_attribution in list(visibility.get("answer_source_attributions", []) or []):
        if not isinstance(raw_attribution, dict):
            continue
        source_path = _text_or_none(raw_attribution.get("source"))
        support = _text_or_none(raw_attribution.get("support"))
        if not source_path or not support:
            continue
        attributions.append(
            SourceAttributionViewModel(
                source_path=source_path,
                source_label=labels_by_path.get(source_path),
                support=support,
            )
        )
    return tuple(attributions)


def _prompt_actions_for_options(options: list[str]) -> tuple[PromptActionViewModel, ...]:
    actions: list[PromptActionViewModel] = []
    for option in options:
        option_text = _text_or_none(option)
        if not option_text:
            continue
        actions.append(
            PromptActionViewModel(
                action_id=option_text,
                label=_prompt_option_label(option_text),
                submit_text=option_text,
            )
        )
    return tuple(actions)


def _prompt_option_label(option: str) -> str:
    normalized = str(option or "").strip()
    if not normalized:
        return ""
    return " ".join(part.capitalize() for part in normalized.replace("_", " ").split())


def _normalized_string_list(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [text for text in (_text_or_none(item) for item in value) if text]


def _text_or_none(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None
