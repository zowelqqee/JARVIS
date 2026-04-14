"""Runtime-to-visibility mapping for JARVIS MVP."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict

from qa.answer_summary import build_answer_summary
from user_language import prefers_russian_text

if TYPE_CHECKING:
    from types.clarification_request import ClarificationRequest
    from types.command import Command
    from types.confirmation_request import ConfirmationRequest
    from types.jarvis_error import JarvisError
    from types.runtime_state import RuntimeState
    from types.step import Step

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from interaction_kind import InteractionKind, interaction_kind_value  # type: ignore  # noqa: E402
from answer_result import (  # type: ignore  # noqa: E402
    AnswerKind,
    AnswerProvenance,
    answer_kind_value,
    answer_provenance_value,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]


class VisibilityPayload(TypedDict, total=False):
    """Minimal user-visible runtime payload shape."""

    runtime_state: str
    command_summary: str | None
    current_step: str | None
    completed_steps: list[str]
    blocked_reason: str | None
    clarification_question: str | None
    confirmation_request: dict[str, Any] | None
    failure_message: str | None
    completion_result: str | None
    next_step_hint: str | None
    search_results: dict[str, Any] | None
    window_results: dict[str, Any] | None
    can_cancel: bool


class InteractionVisibilityPayload(TypedDict, total=False):
    """Minimal user-visible payload shape for top-level dual-mode interactions."""

    interaction_mode: str
    runtime_state: str
    command_summary: str | None
    current_step: str | None
    completed_steps: list[str]
    blocked_reason: str | None
    clarification_question: str | None
    confirmation_request: dict[str, Any] | None
    failure_message: str | None
    completion_result: str | None
    next_step_hint: str | None
    search_results: dict[str, Any] | None
    window_results: dict[str, Any] | None
    can_cancel: bool
    answer_text: str | None
    answer_summary: str | None
    answer_kind: str | None
    answer_provenance: str | None
    answer_sources: list[str]
    answer_source_labels: list[str]
    answer_source_attributions: list[dict[str, str]]
    answer_warning: str | None


_CANCEL_ENABLED_STATES: set[str] = {
    "parsing",
    "validating",
    "planning",
    "executing",
    "awaiting_clarification",
    "awaiting_confirmation",
}
_SEARCH_RESULT_CAP = 5
_WINDOW_RESULT_CAP = 5
_MIXED_INTERACTION_CLARIFICATION_RE = re.compile(
    r"^Do you want an answer first or should I open (?P<target>.+)\?$",
    flags=re.IGNORECASE,
)
_TARGET_NOT_FOUND_WITH_OPTIONS_RE = re.compile(
    r"^I could not find (?P<target>.+?); did you mean (?P<options>.+)\?$",
    flags=re.IGNORECASE,
)
_TARGET_NOT_FOUND_WITH_TARGET_RE = re.compile(
    r"^I could not find (?P<target>.+?); which target should I use\?$",
    flags=re.IGNORECASE,
)
_TARGET_NOT_FOUND_GENERIC_OPTIONS_RE = re.compile(
    r"^I could not find that target; did you mean (?P<options>.+)\?$",
    flags=re.IGNORECASE,
)
_APPROVE_STEP_CONFIRMATION_RE = re.compile(
    r"^Approve step (?P<action>[a-z_]+) for (?P<target>.+)\?$",
    flags=re.IGNORECASE,
)
_APPROVE_CONFIRMATION_WITH_TARGETS_RE = re.compile(
    r"^Approve (?P<intent>[a-z_]+) for (?P<targets>.+)\?$",
    flags=re.IGNORECASE,
)
_APPROVE_CONFIRMATION_COMMAND_RE = re.compile(
    r"^Approve command for (?P<intent>[a-z_]+)\?$",
    flags=re.IGNORECASE,
)
_LIST_WINDOWS_FAILURE_RE = re.compile(
    r"^Could not list windows(?:: (?P<detail>.+))?$",
    flags=re.IGNORECASE,
)
_OPEN_AFTER_SEARCH_WITH_TARGET_DETAIL_RE = re.compile(
    r"^Found a matching file, but could not open it: (?P<target>.+?)\. (?P<detail>.+)$",
    flags=re.IGNORECASE,
)
_OPEN_AFTER_SEARCH_WITH_TARGET_RE = re.compile(
    r"^Found a matching file, but could not open it: (?P<target>.+?)\.$",
    flags=re.IGNORECASE,
)
_OPEN_AFTER_SEARCH_WITH_DETAIL_RE = re.compile(
    r"^Found a matching file, but could not open it\. (?P<detail>.+)$",
    flags=re.IGNORECASE,
)
_SEARCH_OPEN_EMPTY_RE = re.compile(
    r"^Search found no matches to open(?:(?:\.|:)\s*(?P<detail>.+))?$",
    flags=re.IGNORECASE,
)
_SEARCH_FOUND_RE = re.compile(
    r"^Found (?P<count>\d+) (?P<label>match|matches)(?P<scope> in .+)?\.$",
    flags=re.IGNORECASE,
)
_SEARCH_FOUND_AND_OPEN_RE = re.compile(
    r"^Found (?P<count>\d+) (?P<label>match|matches)(?P<scope> in .+)? and opened a file\.$",
    flags=re.IGNORECASE,
)
_SEARCH_COMPLETED_RE = re.compile(
    r"^Search completed(?P<scope> in .+)?\.$",
    flags=re.IGNORECASE,
)
_SEARCH_COMPLETED_AND_OPEN_RE = re.compile(
    r"^Search completed and opened a file\.$",
    flags=re.IGNORECASE,
)
_VISIBLE_WINDOWS_RE = re.compile(
    r"^Found (?P<count>\d+) visible (?P<label>window|windows)\.$",
    flags=re.IGNORECASE,
)
_FILTERED_WINDOWS_RE = re.compile(
    r"^Found (?P<count>\d+) (?P<filter>.+) (?P<label>window|windows)\.$",
    flags=re.IGNORECASE,
)
_NO_VISIBLE_FILTERED_WINDOWS_RE = re.compile(
    r"^No visible (?P<filter>.+) windows found\.$",
    flags=re.IGNORECASE,
)
_INTERNAL_COMPLETION_RE = re.compile(r"^Completed (?P<intent>[a-z_]+) with (?P<count>\d+) step\(s\)\.$")
_RUSSIAN_VISIBLE_EXACT_MAP = {
    "I am not sure what you meant; can you rephrase the command?": "Не уверен, что ты имел в виду. Переформулируй команду.",
    "What should I search for?": "Что мне искать?",
    "Which website URL should I open?": "Какой адрес сайта открыть?",
    "What workspace should I prepare?": "Какое рабочее пространство подготовить?",
    "Please reply with confirm or cancel.": "Скажи: подтвердить или отменить.",
    "Please reply with answer or execute.": "Скажи: ответить или выполнить.",
    "Which previous target are you referring to?": "Какую предыдущую цель ты имеешь в виду?",
    "Please clarify the action and target.": "Уточни действие и цель.",
    "Which app do you want?": "Какое приложение ты имеешь в виду?",
    "Reply yes to continue or no to cancel.": "Скажи да, чтобы продолжить, или нет, чтобы отменить.",
    "Reply with one app name.": "Назови одно приложение.",
    "Reply with one window name.": "Назови одно окно.",
    "Reply with an exact name or full path.": "Назови точное имя или полный путь.",
    "Reply with one full website URL.": "Назови один полный адрес сайта.",
    "Reply with a folder or search query.": "Назови папку или поисковый запрос.",
    "Reply with one project folder.": "Назови одну папку проекта.",
    "Reply with one specific target.": "Назови одну конкретную цель.",
    "Try a more specific app or file name.": "Назови приложение или файл точнее.",
    "Try a more specific target name.": "Назови цель точнее.",
    "Try opening a folder first, then retry.": "Сначала открой папку, потом попробуй снова.",
    "Try opening a folder first, then search inside it.": "Сначала открой папку, потом ищи внутри неё.",
    "Try again in an active macOS desktop session.": "Попробуй ещё раз в активной сессии macOS.",
    "Try using the app name instead of a window reference.": "Попробуй использовать имя приложения вместо ссылки на окно.",
    "Try a more specific command.": "Сформулируй команду точнее.",
    "No remembered workspace is available yet. Start work on a workspace first.": (
        "Пока нет сохраненного рабочего пространства. Сначала подготовь рабочее пространство."
    ),
    "Start work on a workspace first.": "Сначала подготовь рабочее пространство.",
    "Try adding the missing target or parameter.": "Добавь недостающую цель или параметр.",
    "Try a different installed app name.": "Попробуй другое установленное приложение.",
    "Try a specific installed app name, or omit the app to use the default.": (
        "Попробуй указать конкретное установленное приложение или не указывать приложение, "
        "чтобы использовать вариант по умолчанию."
    ),
    "Try a supported command like open app or search local.": "Попробуй поддерживаемую команду вроде open app или search local.",
    "Command cancelled.": "Команда отменена.",
    "Confirmation denied. Command cancelled.": "Подтверждение отклонено. Команда отменена.",
    "Command completed.": "Команда выполнена.",
    "Please confirm or cancel.": "Скажи: подтвердить или отменить.",
    "Please answer the clarification question.": "Ответь на уточняющий вопрос.",
}


def can_show_cancel(state: RuntimeState | str) -> bool:
    """Return whether cancel control should be visible for the runtime state."""
    return _state_value(state) in _CANCEL_ENABLED_STATES


def map_visibility(
    state: RuntimeState | str,
    command: Command | None = None,
    current_step: Step | None = None,
    clarification: ClarificationRequest | None = None,
    confirmation: ConfirmationRequest | None = None,
    error: JarvisError | None = None,
    completed_steps: list[Step] | None = None,
    step_results: dict[str, Any] | None = None,
    blocked_reason: str | None = None,
    completion_result: str | None = None,
) -> VisibilityPayload:
    """Map runtime truth into a deterministic user-visible payload."""
    state_text = _state_value(state)
    completed_step_list = completed_steps or []
    step_result_map = step_results or {}
    search_payload = _search_results_payload(
        completed_steps=completed_step_list,
        step_results=step_result_map,
        current_step=current_step,
    )
    window_payload = _window_results_payload(
        completed_steps=completed_step_list,
        step_results=step_result_map,
        current_step=current_step,
    )

    if blocked_reason is None:
        if clarification is not None:
            blocked_reason = clarification.message
        elif confirmation is not None:
            blocked_reason = confirmation.message
        elif error is not None and getattr(error, "blocking", False):
            blocked_reason = str(getattr(error, "message", "")) or None

    payload: VisibilityPayload = {
        "runtime_state": state_text,
        "command_summary": _command_summary(command),
        "current_step": _step_summary(current_step, _step_result(step_result_map, current_step)),
        "completed_steps": _completed_step_summaries(completed_step_list, step_result_map),
        "blocked_reason": blocked_reason,
        "clarification_question": getattr(clarification, "message", None),
        "confirmation_request": _confirmation_payload(confirmation),
        "failure_message": _failure_message(
            state_text=state_text,
            command=command,
            error=error,
            completed_steps=completed_step_list,
            current_step=current_step,
            search_payload=search_payload,
        ),
        "completion_result": _completion_text(
            state_text=state_text,
            completion_result=completion_result,
            command=command,
            completed_steps=completed_step_list,
            current_step=current_step,
            step_results=step_result_map,
            search_payload=search_payload,
            window_payload=window_payload,
        ),
        "search_results": search_payload,
        "window_results": window_payload,
        "can_cancel": can_show_cancel(state_text),
    }
    next_step_hint = _next_step_hint(
        state_text=state_text,
        command=command,
        current_step=current_step,
        clarification=clarification,
        confirmation=confirmation,
        error=error,
    )
    if next_step_hint:
        payload["next_step_hint"] = next_step_hint
    if _prefers_russian_visibility(
        command,
        blocked_reason,
        getattr(clarification, "message", None),
        getattr(confirmation, "message", None),
        completion_result,
        getattr(error, "message", None) if error is not None else None,
    ):
        payload = _localized_russian_payload(payload)
    return _prune_optional_none_fields(payload)


def map_interaction_visibility(
    *,
    interaction_mode: InteractionKind | str,
    runtime_result: Any | None = None,
    answer_result: Any | None = None,
    clarification_request: Any | None = None,
    error: Any | None = None,
) -> InteractionVisibilityPayload:
    """Map a top-level command/question/clarification result into a unified visible payload."""
    mode_text = interaction_kind_value(interaction_mode).strip()
    if mode_text == InteractionKind.COMMAND.value:
        runtime_visibility = dict(getattr(runtime_result, "visibility", {}) or {})
        payload: InteractionVisibilityPayload = {
            "interaction_mode": InteractionKind.COMMAND.value,
            "runtime_state": str(runtime_visibility.get("runtime_state", getattr(runtime_result, "runtime_state", "idle"))),
            "command_summary": runtime_visibility.get("command_summary"),
            "current_step": runtime_visibility.get("current_step"),
            "completed_steps": list(runtime_visibility.get("completed_steps", []) or []),
            "blocked_reason": runtime_visibility.get("blocked_reason"),
            "clarification_question": runtime_visibility.get("clarification_question"),
            "confirmation_request": runtime_visibility.get("confirmation_request"),
            "failure_message": runtime_visibility.get("failure_message"),
            "completion_result": runtime_visibility.get("completion_result"),
            "next_step_hint": runtime_visibility.get("next_step_hint"),
            "search_results": runtime_visibility.get("search_results"),
            "window_results": runtime_visibility.get("window_results"),
            "can_cancel": bool(runtime_visibility.get("can_cancel", False)),
        }
        return _prune_interaction_optional_none_fields(payload)

    if mode_text == InteractionKind.QUESTION.value:
        answer_sources = list(getattr(answer_result, "sources", []) or [])
        source_attributions = _answer_source_attributions(answer_result)
        warning = str(getattr(answer_result, "warning", "") or "").strip() or None
        answer_text = str(getattr(answer_result, "answer_text", "") or "").strip() or None
        answer_kind = (
            answer_kind_value(getattr(answer_result, "answer_kind", AnswerKind.GROUNDED_LOCAL))
            if answer_result is not None
            else None
        )
        answer_provenance = (
            answer_provenance_value(getattr(answer_result, "provenance", AnswerProvenance.LOCAL_SOURCES))
            if answer_result is not None
            else None
        )
        payload = {
            "interaction_mode": InteractionKind.QUESTION.value,
            "can_cancel": False,
            "answer_text": answer_text,
            "answer_summary": _answer_summary(answer_text),
            "answer_kind": answer_kind,
            "answer_provenance": answer_provenance,
            "answer_sources": answer_sources,
            "answer_source_labels": _answer_source_labels(answer_sources),
            "answer_source_attributions": source_attributions,
            "answer_warning": warning,
            "failure_message": _interaction_failure_message(error) if error is not None else None,
        }
        return _prune_interaction_optional_none_fields(payload)

    clarification_message = str(getattr(clarification_request, "message", "") or "").strip() or None
    payload = {
        "interaction_mode": InteractionKind.CLARIFICATION.value,
        "can_cancel": False,
        "blocked_reason": clarification_message,
        "clarification_question": clarification_message,
        "failure_message": _interaction_failure_message(error) if error is not None else None,
    }
    return _prune_interaction_optional_none_fields(payload)


def _state_value(state: RuntimeState | str) -> str:
    return str(getattr(state, "value", state))


def _answer_source_attributions(answer_result: Any | None) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for attribution in list(getattr(answer_result, "source_attributions", []) or []):
        if isinstance(attribution, dict):
            source = str(attribution.get("source", "") or "").strip()
            support = str(attribution.get("support", "") or "").strip()
        else:
            source = str(getattr(attribution, "source", "") or "").strip()
            support = str(getattr(attribution, "support", "") or "").strip()
        if source and support:
            result.append({"source": source, "support": support})
    return result


def _answer_summary(answer_text: str | None) -> str | None:
    return build_answer_summary(answer_text)


def _answer_source_labels(sources: list[str]) -> list[str]:
    return [_source_label(source) for source in sources if str(source).strip()]


def _source_label(source: str) -> str:
    raw_source = str(source or "").strip()
    if not raw_source:
        return ""
    source_path = Path(raw_source)
    try:
        relative_source = source_path.resolve().relative_to(_REPO_ROOT)
    except (ValueError, OSError):
        relative_source = Path(source_path.name or raw_source)
    label_seed = relative_source.stem or relative_source.name or raw_source
    words = str(label_seed).replace("_", " ").replace("-", " ").split()
    if not words:
        return raw_source
    return " ".join(word.capitalize() for word in words)


def _intent_value(intent: Any) -> str:
    return str(getattr(intent, "value", intent))


def _target_type_value(target_type: Any) -> str:
    return str(getattr(target_type, "value", target_type))


def _target_name(target: Any) -> str:
    name = str(getattr(target, "name", "")).strip()
    return name


def _command_summary(command: Command | None) -> str | None:
    if command is None:
        return None
    if _is_resume_work_protocol(command):
        return "resume_work: last workspace"
    if _is_start_work_command(command):
        workspace_label = _workspace_target_label(command)
        if workspace_label:
            return f"start_work: {workspace_label} in Visual Studio Code"
        return "start_work: Visual Studio Code"
    intent = _intent_value(getattr(command, "intent", ""))
    if intent == "run_protocol":
        parameters = dict(getattr(command, "parameters", {}) or {})
        protocol_name = (
            str(parameters.get("protocol_display_name", "") or "").strip()
            or str(parameters.get("requested_protocol_name", "") or "").strip()
        )
        return f"run_protocol: {protocol_name}" if protocol_name else intent
    targets = list(getattr(command, "targets", []) or [])
    names = [name for name in (_target_name(target) for target in targets) if name]
    if names:
        return f"{intent}: {', '.join(names)}"
    return intent or None


def _is_start_work_command(command: Command | None) -> bool:
    if command is None:
        return False
    if _intent_value(getattr(command, "intent", "")) != "prepare_workspace":
        return False
    raw_input = str(getattr(command, "raw_input", "") or "").strip().lower()
    return raw_input.startswith("start work")


def _is_resume_work_protocol(command: Command | None) -> bool:
    if command is None:
        return False
    if _intent_value(getattr(command, "intent", "")) != "run_protocol":
        return False
    parameters = dict(getattr(command, "parameters", {}) or {})
    return str(parameters.get("protocol_id", "") or "").strip() == "resume_work"


def _workspace_target_label(command: Command | None) -> str | None:
    if command is None:
        return None
    for target in list(getattr(command, "targets", []) or []):
        if _target_type_value(getattr(target, "type", "")) != "folder":
            continue
        label = _workspace_label_from_values(
            name=str(getattr(target, "name", "") or "").strip(),
            raw_path=str(getattr(target, "path", "") or "").strip(),
        )
        if label:
            return label

    parameters = dict(getattr(command, "parameters", {}) or {})
    return _workspace_label_from_values(
        name=str(parameters.get("workspace_label", "") or "").strip(),
        raw_path=str(parameters.get("workspace_path", "") or parameters.get("workspace", "") or "").strip(),
    )


def _workspace_label_from_values(*, name: str, raw_path: str) -> str | None:
    if name:
        return name
    if not raw_path:
        return None
    normalized_path = Path(raw_path).expanduser()
    return normalized_path.name or raw_path


def _step_summary(step: Step | None, step_result: Any | None = None) -> str | None:
    if step is None:
        return None
    action = _step_action_value(step)
    target = _target_name(getattr(step, "target", None))
    summary = f"{getattr(step, 'id', '')} {action}".strip()
    if target:
        summary = f"{summary} {target}".strip()

    details = getattr(step_result, "details", None)
    if action == "search_local":
        preview = _search_preview_text(details)
        if preview:
            return f"{summary} {preview}".strip()

    if action == "open_file":
        opened_path = _opened_file_path_from_details(details)
        if opened_path:
            return f"{summary} -> {opened_path}".strip()

    if action == "list_windows":
        preview = _window_preview_text(details)
        if preview:
            return f"{summary} {preview}".strip()

    return summary


def _step_action_value(step: Step) -> str:
    return str(getattr(getattr(step, "action", ""), "value", getattr(step, "action", "")))


def _step_result(step_results: dict[str, Any], step: Step | None) -> Any | None:
    if step is None:
        return None
    step_id = str(getattr(step, "id", ""))
    if not step_id:
        return None
    return step_results.get(step_id)


def _completed_step_summaries(completed_steps: list[Step], step_results: dict[str, Any]) -> list[str]:
    summaries: list[str] = []
    for step in completed_steps:
        summary = _step_summary(step, _step_result(step_results, step))
        if summary:
            summaries.append(summary)
    return summaries


def _confirmation_payload(confirmation: ConfirmationRequest | None) -> dict[str, Any] | None:
    if confirmation is None:
        return None
    return {
        "message": str(getattr(confirmation, "message", "")),
        "boundary_type": str(
            getattr(getattr(confirmation, "boundary_type", ""), "value", getattr(confirmation, "boundary_type", ""))
        ),
        "affected_targets": [
            _target_name(target)
            for target in list(getattr(confirmation, "affected_targets", []) or [])
            if _target_name(target)
        ],
    }


def _prefers_russian_visibility(command: Command | None, *parts: object) -> bool:
    raw_input = str(getattr(command, "raw_input", "") or "").strip()
    if raw_input:
        return prefers_russian_text(raw_input)
    return prefers_russian_text(*(str(part or "") for part in parts))


def _localized_russian_payload(payload: VisibilityPayload) -> VisibilityPayload:
    localized = dict(payload)
    for field in ("blocked_reason", "clarification_question", "failure_message", "completion_result", "next_step_hint"):
        current = localized.get(field)
        if current is None:
            continue
        localized[field] = _localized_russian_visible_text(str(current))
    confirmation_request = localized.get("confirmation_request")
    if isinstance(confirmation_request, dict):
        localized_confirmation = dict(confirmation_request)
        localized_confirmation["message"] = _localized_russian_visible_text(str(confirmation_request.get("message", "") or ""))
        localized["confirmation_request"] = localized_confirmation
    return localized


def _localized_russian_visible_text(text: str) -> str:
    normalized = " ".join(str(text or "").split()).strip()
    if not normalized:
        return normalized
    exact = _RUSSIAN_VISIBLE_EXACT_MAP.get(normalized)
    if exact:
        return exact

    mixed_interaction = _MIXED_INTERACTION_CLARIFICATION_RE.match(normalized)
    if mixed_interaction is not None:
        target = str(mixed_interaction.group("target") or "").strip()
        if target:
            return f"Сначала ответить или открыть {target}?"

    target_with_options = _TARGET_NOT_FOUND_WITH_OPTIONS_RE.match(normalized)
    if target_with_options is not None:
        target = str(target_with_options.group("target") or "").strip()
        options = str(target_with_options.group("options") or "").strip()
        return f"Не могу найти {target}; ты имел в виду {_spoken_option_list(options)}?"

    target_with_followup = _TARGET_NOT_FOUND_WITH_TARGET_RE.match(normalized)
    if target_with_followup is not None:
        target = str(target_with_followup.group("target") or "").strip()
        return f"Не могу найти {target}; какую цель использовать?"

    generic_options = _TARGET_NOT_FOUND_GENERIC_OPTIONS_RE.match(normalized)
    if generic_options is not None:
        options = str(generic_options.group("options") or "").strip()
        return f"Не могу найти эту цель; ты имел в виду {_spoken_option_list(options)}?"

    approve_step = _APPROVE_STEP_CONFIRMATION_RE.match(normalized)
    if approve_step is not None:
        action = str(approve_step.group("action") or "").strip()
        target = str(approve_step.group("target") or "").strip()
        if action and target:
            return f"Подтвердить шаг {action} для {target}?"

    approve_with_targets = _APPROVE_CONFIRMATION_WITH_TARGETS_RE.match(normalized)
    if approve_with_targets is not None:
        intent = str(approve_with_targets.group("intent") or "").strip()
        targets = str(approve_with_targets.group("targets") or "").strip()
        if intent and targets:
            return f"Подтвердить {intent} для {targets}?"

    approve_command = _APPROVE_CONFIRMATION_COMMAND_RE.match(normalized)
    if approve_command is not None:
        intent = str(approve_command.group("intent") or "").strip()
        if intent:
            return f"Подтвердить команду {intent}?"

    list_windows_match = _LIST_WINDOWS_FAILURE_RE.match(normalized.rstrip("."))
    if list_windows_match is not None:
        detail = str(list_windows_match.group("detail") or "").strip()
        if detail:
            return f"Не удалось показать окна: {detail}"
        return "Не удалось показать окна."

    open_with_target_detail = _OPEN_AFTER_SEARCH_WITH_TARGET_DETAIL_RE.match(normalized)
    if open_with_target_detail is not None:
        target = str(open_with_target_detail.group("target") or "").strip()
        detail = str(open_with_target_detail.group("detail") or "").strip()
        if target and detail:
            return f"Нашёл подходящий файл, но не смог открыть {target}. {detail}"

    open_with_target = _OPEN_AFTER_SEARCH_WITH_TARGET_RE.match(normalized)
    if open_with_target is not None:
        target = str(open_with_target.group("target") or "").strip()
        if target:
            return f"Нашёл подходящий файл, но не смог открыть {target}."

    open_with_detail = _OPEN_AFTER_SEARCH_WITH_DETAIL_RE.match(normalized)
    if open_with_detail is not None:
        detail = str(open_with_detail.group("detail") or "").strip()
        if detail:
            return f"Нашёл подходящий файл, но не смог его открыть. {detail}"
        return "Нашёл подходящий файл, но не смог его открыть."

    search_empty_match = _SEARCH_OPEN_EMPTY_RE.match(normalized)
    if search_empty_match is not None:
        detail = str(search_empty_match.group("detail") or "").strip()
        if detail:
            return f"Поиск не нашёл файл для открытия. {detail}"
        return "Поиск не нашёл файл для открытия."

    internal_completion = _INTERNAL_COMPLETION_RE.match(normalized)
    if internal_completion is not None:
        intent = str(internal_completion.group("intent") or "").strip()
        count = int(internal_completion.group("count"))
        return f"Завершил {intent}: {count} {_russian_count_form(count, 'шаг', 'шага', 'шагов')}."

    search_found = _SEARCH_FOUND_RE.match(normalized)
    if search_found is not None:
        count = int(search_found.group("count"))
        scope = _normalized_scope_suffix(search_found.group("scope"))
        return f"Найдено {count} {_russian_count_form(count, 'совпадение', 'совпадения', 'совпадений')}{scope}."

    search_found_and_open = _SEARCH_FOUND_AND_OPEN_RE.match(normalized)
    if search_found_and_open is not None:
        count = int(search_found_and_open.group("count"))
        scope = _normalized_scope_suffix(search_found_and_open.group("scope"))
        return (
            f"Найдено {count} {_russian_count_form(count, 'совпадение', 'совпадения', 'совпадений')}"
            f"{scope}, файл открыт."
        )

    search_completed = _SEARCH_COMPLETED_RE.match(normalized)
    if search_completed is not None:
        scope = _normalized_scope_suffix(search_completed.group("scope"))
        return f"Поиск завершён{scope}."

    if _SEARCH_COMPLETED_AND_OPEN_RE.match(normalized) is not None:
        return "Поиск завершён, файл открыт."

    visible_windows = _VISIBLE_WINDOWS_RE.match(normalized)
    if visible_windows is not None:
        count = int(visible_windows.group("count"))
        return f"Сейчас видно {count} {_russian_count_form(count, 'окно', 'окна', 'окон')}."

    filtered_windows = _FILTERED_WINDOWS_RE.match(normalized)
    if filtered_windows is not None:
        count = int(filtered_windows.group("count"))
        filter_name = str(filtered_windows.group("filter") or "").strip()
        if filter_name:
            return f"Сейчас видно {count} {_russian_count_form(count, 'окно', 'окна', 'окон')} {filter_name}."

    filtered_windows_none = _NO_VISIBLE_FILTERED_WINDOWS_RE.match(normalized)
    if filtered_windows_none is not None:
        filter_name = str(filtered_windows_none.group("filter") or "").strip()
        if filter_name:
            return f"Окон {filter_name} не найдено."

    return normalized


def _spoken_option_list(options: str) -> str:
    parts = [part.strip() for part in str(options or "").split(",") if part.strip()]
    return ", ".join(parts)


def _russian_count_form(count: int, one: str, few: str, many: str) -> str:
    normalized_count = abs(int(count))
    mod10 = normalized_count % 10
    mod100 = normalized_count % 100
    if mod10 == 1 and mod100 != 11:
        return one
    if 2 <= mod10 <= 4 and not 12 <= mod100 <= 14:
        return few
    return many


def _normalized_scope_suffix(scope: str | None) -> str:
    scope_text = str(scope or "").strip()
    if not scope_text:
        return ""
    if scope_text.lower().startswith("in "):
        return f" в {scope_text[3:].strip()}"
    return scope_text


def _failure_message(
    state_text: str,
    command: Command | None,
    error: JarvisError | None,
    completed_steps: list[Step],
    current_step: Step | None,
    search_payload: dict[str, Any] | None,
) -> str | None:
    if state_text != "failed" or error is None:
        return None
    reason = str(getattr(error, "message", "")).strip()
    error_code = str(getattr(getattr(error, "code", ""), "value", getattr(error, "code", ""))).strip()

    if _is_resume_work_protocol(command) and error_code == "INSUFFICIENT_CONTEXT":
        stale_path = str((getattr(error, "details", None) or {}).get("stale_workspace_path", "") or "").strip()
        if stale_path:
            workspace_label = Path(stale_path).name or stale_path
            return (
                f'The remembered workspace "{workspace_label}" no longer exists at the stored path. '
                f'Run "start work on <workspace>" to set a new one.'
            )
        return "No remembered workspace is available yet. Start work on a workspace first."

    if _is_resume_work_protocol(command) and error_code == "TARGET_NOT_FOUND":
        return 'The remembered workspace folder was not found. Run "start work on <workspace>" to set a new one.'

    if _is_search_then_open_failure(completed_steps, current_step, search_payload):
        total_matches = search_payload.get("total_matches") if search_payload else None
        if isinstance(total_matches, int) and total_matches <= 0:
            if reason:
                return f"Search found no matches to open. {reason}"
            return "Search found no matches to open."

    if _is_open_after_search_failure(completed_steps, current_step, search_payload):
        selected_target = _open_target_label(current_step)
        if selected_target and reason:
            return f"Found a matching file, but could not open it: {selected_target}. {reason}"
        if selected_target:
            return f"Found a matching file, but could not open it: {selected_target}."
        if reason:
            return f"Found a matching file, but could not open it. {reason}"
        return "Found a matching file, but could not open it."

    if _is_list_windows_failure(current_step):
        message = str(getattr(error, "message", "")).strip()
        if message:
            return f"Could not list windows: {message}"
        code = str(getattr(getattr(error, "code", ""), "value", getattr(error, "code", ""))).strip()
        if code:
            return f"Could not list windows: {code}"
        return "Could not list windows."

    code = str(getattr(getattr(error, "code", ""), "value", getattr(error, "code", "")))
    message = str(getattr(error, "message", "")).strip()
    if code and message:
        return f"{code}: {message}"
    if message:
        return message
    return code or "Command failed."


def _completion_text(
    state_text: str,
    completion_result: str | None,
    command: Command | None,
    completed_steps: list[Step],
    current_step: Step | None,
    step_results: dict[str, Any],
    search_payload: dict[str, Any] | None,
    window_payload: dict[str, Any] | None,
) -> str | None:
    if state_text == "cancelled":
        if completion_result:
            return completion_result
        return "Command cancelled."

    if state_text != "completed":
        return None

    search_completion = _search_completion_text(
        completed_steps=completed_steps,
        current_step=current_step,
        step_results=step_results,
        search_payload=search_payload,
    )
    if search_completion:
        return search_completion

    window_completion = _window_completion_text(window_payload)
    if window_completion:
        return window_completion

    if completion_result:
        return completion_result
    if command is None:
        return "Command completed."
    if _is_start_work_command(command):
        workspace_label = _workspace_target_label(command)
        if workspace_label:
            return f"Workspace ready: {workspace_label} in Visual Studio Code."
        return "Workspace ready in Visual Studio Code."
    intent = _intent_value(getattr(command, "intent", ""))
    return f"Completed {intent} with {len(completed_steps)} step(s)."


def _next_step_hint(
    state_text: str,
    command: Command | None,
    current_step: Step | None,
    clarification: ClarificationRequest | None,
    confirmation: ConfirmationRequest | None,
    error: JarvisError | None,
) -> str | None:
    # Explicit precedence:
    # 1) specific structured failure reason
    # 2) specific blocked state
    # 3) generic failure hint
    # 4) no hint
    if state_text == "failed" and error is not None:
        specific_failure_hint = _specific_failure_next_step_hint(command, current_step, error)
        if specific_failure_hint:
            return specific_failure_hint

    if state_text == "awaiting_confirmation":
        return "Reply yes to continue or no to cancel."

    if state_text == "awaiting_clarification":
        return _clarification_next_step_hint(command, error, clarification)

    if state_text == "failed" and error is not None:
        return _generic_failure_next_step_hint(error)

    return None


def _clarification_next_step_hint(
    command: Command | None,
    error: JarvisError | None,
    clarification: ClarificationRequest | None,
) -> str | None:
    intent = _intent_value(getattr(command, "intent", ""))
    error_code = _error_code_value(error)

    if error_code == "MULTIPLE_MATCHES":
        return "Try a more specific app or file name."
    if error_code == "FOLLOWUP_REFERENCE_UNCLEAR":
        if intent in {"search_local", "prepare_workspace", "open_folder", "open_file"}:
            return "Try opening a folder first, then retry."
        return "Try a more specific target name."
    if error_code == "TARGET_NOT_FOUND" and intent == "search_local":
        return "Try opening a folder first, then search inside it."

    if intent in {"open_app", "close_app", "list_windows"}:
        return "Reply with one app name."
    if intent in {"close_window", "focus_window"}:
        return "Reply with one window name."
    if intent in {"open_file", "open_folder"}:
        return "Reply with an exact name or full path."
    if intent == "open_website":
        return "Reply with one full website URL."
    if intent == "search_local":
        return "Reply with a folder or search query."
    if intent == "prepare_workspace":
        return "Reply with one project folder."
    if intent == "run_protocol":
        return "Reply with one protocol name."
    return "Reply with one specific target."


def _specific_failure_next_step_hint(command: Command | None, current_step: Step | None, error: JarvisError) -> str | None:
    intent = _intent_value(getattr(command, "intent", ""))
    error_code = _error_code_value(error)
    action = _step_action_value(current_step) if current_step is not None else ""

    if error_code == "TARGET_NOT_FOUND":
        if intent == "run_protocol":
            if _is_resume_work_protocol(command):
                return 'Run "start work on <workspace>" to set a new workspace.'
            return "Try a known protocol name."
        if intent == "search_local":
            return "Try opening a folder first, then search inside it."
        if intent == "open_file":
            return "Try: open /full/path/to/file"
        if intent in {"open_folder", "prepare_workspace"}:
            return "Try: open /full/path/to/folder"
        if intent == "list_windows":
            return "Try: show windows"
        return "Try a more specific app or file name."

    if error_code == "MULTIPLE_MATCHES":
        if intent == "run_protocol":
            return "Reply with one protocol name."
        return "Try a more specific app or file name."

    if error_code == "FOLLOWUP_REFERENCE_UNCLEAR":
        if intent in {"search_local", "prepare_workspace", "open_folder", "open_file"}:
            return "Try opening a folder first, then retry."
        return "Try a more specific target name."

    if error_code == "MISSING_PARAMETER":
        if intent == "open_website":
            return "Try: open https://example.com"
        if intent == "search_local":
            return "Try: search local for roadmap in /full/folder/path"
        if intent == "confirm":
            return "Reply yes to continue or no to cancel."
        return "Try adding the missing target or parameter."

    if error_code == "INSUFFICIENT_CONTEXT":
        if _is_resume_work_protocol(command):
            return "Start work on a workspace first."
        return "Try a more specific command."

    if error_code == "UNSUPPORTED_ACTION":
        if action == "focus_window" or intent == "focus_window":
            return "Try: list windows"
        if action == "close_window" or intent == "close_window":
            return "Try using the app name instead of a window reference."
        if action == "list_windows" or intent == "list_windows":
            return "Try again in an active macOS desktop session."
        return "Try a supported command like open app or search local."

    if error_code == "APP_UNAVAILABLE":
        if intent in {"open_file", "open_folder"}:
            return "Try a specific installed app name, or omit the app to use the default."
        return "Try a different installed app name."

    if error_code == "EXECUTION_FAILED":
        if action == "list_windows" or intent == "list_windows":
            return "Try again in an active macOS desktop session."
        if action == "close_window" or intent == "close_window":
            return "Try using the app name instead of a window reference."
        return None

    return None


def _generic_failure_next_step_hint(error: JarvisError | None) -> str | None:
    if error is None:
        return None
    return "Try a more specific command."


def _error_code_value(error: JarvisError | None) -> str:
    if error is None:
        return ""
    return str(getattr(getattr(error, "code", ""), "value", getattr(error, "code", "")))


def _search_results_payload(
    completed_steps: list[Step],
    step_results: dict[str, Any],
    current_step: Step | None,
) -> dict[str, Any] | None:
    latest_search_step: Step | None = None
    for step in reversed(completed_steps):
        if _step_action_value(step) == "search_local":
            latest_search_step = step
            break

    if latest_search_step is None:
        return None

    search_result = _step_result(step_results, latest_search_step)
    details = getattr(search_result, "details", None)
    if not isinstance(details, dict):
        return None

    raw_matches = details.get("matches")
    if not isinstance(raw_matches, list):
        return None

    normalized_matches = [match for match in (_normalize_search_match(entry) for entry in raw_matches) if match]
    total_matches = len(normalized_matches)
    capped_matches = normalized_matches[:_SEARCH_RESULT_CAP]
    flow = "search_only"
    all_actions = [_step_action_value(step) for step in completed_steps]
    if "open_file" in all_actions:
        flow = "search_then_open"
    elif current_step is not None and _step_action_value(current_step) == "open_file":
        flow = "search_then_open"

    payload: dict[str, Any] = {
        "flow": flow,
        "total_matches": total_matches,
        "matches": capped_matches,
    }
    query = str(details.get("query", "")).strip()
    scope_path = str(details.get("scope_path", "")).strip()
    if query:
        payload["query"] = query
    if scope_path:
        payload["scope_path"] = scope_path
    return payload


def _window_results_payload(
    completed_steps: list[Step],
    step_results: dict[str, Any],
    current_step: Step | None,
) -> dict[str, Any] | None:
    latest_window_step: Step | None = None
    for step in reversed(completed_steps):
        if _step_action_value(step) == "list_windows":
            latest_window_step = step
            break

    if latest_window_step is None:
        if current_step is None or _step_action_value(current_step) != "list_windows":
            return None
        latest_window_step = current_step

    window_result = _step_result(step_results, latest_window_step)
    details = getattr(window_result, "details", None)
    if not isinstance(details, dict):
        return None

    raw_windows = details.get("windows")
    if not isinstance(raw_windows, list):
        return None

    normalized_windows = [entry for entry in (_normalize_window_entry(item) for item in raw_windows) if entry]
    total_windows = details.get("count")
    if not isinstance(total_windows, int):
        total_windows = len(normalized_windows)

    payload: dict[str, Any] = {
        "total_windows": total_windows,
        "windows": normalized_windows[:_WINDOW_RESULT_CAP],
    }

    filter_name = str(details.get("filter", "")).strip()
    if filter_name:
        payload["filter"] = filter_name
    return payload


def _normalize_window_entry(entry: Any) -> dict[str, Any] | None:
    if not isinstance(entry, dict):
        return None

    app_name = str(entry.get("app_name", "") or entry.get("app", "")).strip()
    window_title = str(entry.get("window_title", "") or entry.get("title", "")).strip()
    raw_window_id = entry.get("window_id", entry.get("id"))
    window_id: int | None = None
    if isinstance(raw_window_id, int):
        window_id = raw_window_id
    elif isinstance(raw_window_id, str) and raw_window_id.isdigit():
        window_id = int(raw_window_id)

    if not app_name and not window_title and window_id is None:
        return None

    normalized: dict[str, Any] = {}
    if app_name:
        normalized["app_name"] = app_name
    if window_title:
        normalized["window_title"] = window_title
    if window_id is not None:
        normalized["window_id"] = window_id
    return normalized


def _window_preview_text(details: Any) -> str | None:
    if not isinstance(details, dict):
        return None
    raw_windows = details.get("windows")
    if not isinstance(raw_windows, list):
        return None

    normalized_windows = [entry for entry in (_normalize_window_entry(item) for item in raw_windows) if entry]
    total_windows = details.get("count")
    if not isinstance(total_windows, int):
        total_windows = len(normalized_windows)
    if total_windows <= 0:
        return "(0 windows)"

    labels = [_window_entry_label(entry) for entry in normalized_windows[:_WINDOW_RESULT_CAP]]
    labels = [label for label in labels if label]
    if not labels:
        return f"({total_windows} windows)"
    return f"({total_windows} windows: {'; '.join(labels)})"


def _window_entry_label(entry: dict[str, Any]) -> str:
    app_name = str(entry.get("app_name", "")).strip()
    window_title = str(entry.get("window_title", "")).strip()
    window_id = entry.get("window_id")

    if app_name and window_title:
        return f"{app_name} - {window_title}"
    if app_name:
        return app_name
    if window_title:
        return window_title
    if isinstance(window_id, int):
        return f"window #{window_id}"
    return ""


def _search_preview_text(details: Any) -> str | None:
    if not isinstance(details, dict):
        return None
    raw_matches = details.get("matches")
    if not isinstance(raw_matches, list):
        return None

    normalized_matches = [match for match in (_normalize_search_match(entry) for entry in raw_matches) if match]
    if not normalized_matches:
        return "(0 matches)"

    total = len(normalized_matches)
    preview_names = [_search_match_label(match) for match in normalized_matches[:_SEARCH_RESULT_CAP]]
    preview_text = "; ".join([name for name in preview_names if name])
    if not preview_text:
        return f"({total} matches)"
    return f"({total} matches: {preview_text})"


def _normalize_search_match(entry: Any) -> dict[str, Any] | None:
    if not isinstance(entry, dict):
        return None

    path = str(entry.get("path", "")).strip()
    name = str(entry.get("name", "")).strip()
    match_type = str(entry.get("type", "")).strip()
    if not name and path:
        name = Path(path).name
    if not name and not path:
        return None

    normalized: dict[str, Any] = {}
    if name:
        normalized["name"] = name
    if path:
        normalized["path"] = path
    if match_type:
        normalized["type"] = match_type
    return normalized


def _search_match_label(match: dict[str, Any]) -> str:
    path = str(match.get("path", "")).strip()
    if path:
        return path
    name = str(match.get("name", "")).strip()
    return name


def _search_completion_text(
    completed_steps: list[Step],
    current_step: Step | None,
    step_results: dict[str, Any],
    search_payload: dict[str, Any] | None,
) -> str | None:
    if not search_payload:
        return None

    flow = str(search_payload.get("flow", "")).strip()
    total_matches = search_payload.get("total_matches")
    scope_suffix = _scope_suffix(search_payload)

    if flow == "search_only":
        if isinstance(total_matches, int):
            label = "match" if total_matches == 1 else "matches"
            return f"Found {total_matches} {label}{scope_suffix}."
        return f"Search completed{scope_suffix}."

    if flow == "search_then_open":
        open_step = _latest_open_file_step(completed_steps, current_step)
        opened_path = _opened_path_for_step(open_step, step_results)
        if opened_path:
            return f"Opened file: {opened_path}"
        if isinstance(total_matches, int):
            label = "match" if total_matches == 1 else "matches"
            return f"Found {total_matches} {label}{scope_suffix} and opened a file."
        return "Search completed and opened a file."

    return None


def _window_completion_text(window_payload: dict[str, Any] | None) -> str | None:
    if not window_payload:
        return None

    total_windows = window_payload.get("total_windows")
    if not isinstance(total_windows, int):
        return None

    filter_name = str(window_payload.get("filter", "")).strip()
    if total_windows <= 0:
        if filter_name:
            return f"No visible {filter_name} windows found."
        return "No visible windows found."

    label = "window" if total_windows == 1 else "windows"
    if filter_name:
        return f"Found {total_windows} {filter_name} {label}."
    return f"Found {total_windows} visible {label}."


def _scope_suffix(search_payload: dict[str, Any]) -> str:
    scope_path = str(search_payload.get("scope_path", "")).strip()
    if not scope_path:
        return ""
    folder_name = Path(scope_path).name or scope_path
    return f" in {folder_name}"


def _latest_open_file_step(completed_steps: list[Step], current_step: Step | None) -> Step | None:
    for step in reversed(completed_steps):
        if _step_action_value(step) == "open_file":
            return step
    if current_step is not None and _step_action_value(current_step) == "open_file":
        return current_step
    return None


def _opened_path_for_step(step: Step | None, step_results: dict[str, Any]) -> str | None:
    if step is None:
        return None
    step_result = _step_result(step_results, step)
    path = _opened_file_path_from_details(getattr(step_result, "details", None))
    if path:
        return path
    return _open_target_label(step)


def _opened_file_path_from_details(details: Any) -> str | None:
    if not isinstance(details, dict):
        return None
    path = str(details.get("path", "")).strip()
    if path:
        return path
    return None


def _open_target_label(step: Step | None) -> str | None:
    if step is None:
        return None
    target = getattr(step, "target", None)
    path = str(getattr(target, "path", "") or "").strip()
    if path:
        return path
    name = _target_name(target)
    return name or None


def _is_open_after_search_failure(
    completed_steps: list[Step],
    current_step: Step | None,
    search_payload: dict[str, Any] | None,
) -> bool:
    if not _is_search_then_open_failure(completed_steps, current_step, search_payload):
        return False
    total_matches = search_payload.get("total_matches") if search_payload else None
    return isinstance(total_matches, int) and total_matches > 0


def _is_search_then_open_failure(
    completed_steps: list[Step],
    current_step: Step | None,
    search_payload: dict[str, Any] | None,
) -> bool:
    if not search_payload:
        return False
    if str(search_payload.get("flow", "")).strip() != "search_then_open":
        return False
    if current_step is None:
        return False
    return _step_action_value(current_step) == "open_file"


def _is_list_windows_failure(current_step: Step | None) -> bool:
    if current_step is None:
        return False
    return _step_action_value(current_step) == "list_windows"


def _prune_optional_none_fields(payload: VisibilityPayload) -> VisibilityPayload:
    optional_fields = (
        "command_summary",
        "current_step",
        "blocked_reason",
        "clarification_question",
        "confirmation_request",
        "failure_message",
        "completion_result",
        "search_results",
        "window_results",
        "next_step_hint",
    )
    for key in optional_fields:
        if payload.get(key) is None:
            payload.pop(key, None)
    return payload


def _prune_interaction_optional_none_fields(payload: InteractionVisibilityPayload) -> InteractionVisibilityPayload:
    optional_fields = (
        "command_summary",
        "current_step",
        "blocked_reason",
        "clarification_question",
        "confirmation_request",
        "failure_message",
        "completion_result",
        "search_results",
        "window_results",
        "next_step_hint",
        "answer_text",
        "answer_summary",
        "answer_warning",
    )
    for key in optional_fields:
        if payload.get(key) is None:
            payload.pop(key, None)
    if not payload.get("answer_sources"):
        payload.pop("answer_sources", None)
    if not payload.get("answer_source_labels"):
        payload.pop("answer_source_labels", None)
    if not payload.get("answer_source_attributions"):
        payload.pop("answer_source_attributions", None)
    return payload


def _interaction_failure_message(error: Any | None) -> str | None:
    if error is None:
        return None
    code = str(getattr(getattr(error, "code", ""), "value", getattr(error, "code", ""))).strip()
    message = str(getattr(error, "message", "")).strip()
    if code and message:
        return f"{code}: {message}"
    return message or code or None
