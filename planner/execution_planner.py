"""Deterministic execution planning for JARVIS MVP."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from executor.desktop_actions import DesktopAction
from protocols.planner import expand_protocol_command

if TYPE_CHECKING:
    from types.command import Command
    from types.planned_command import PlannedCommand


_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from command import Command  # type: ignore  # noqa: E402
from confirmation_request import (  # type: ignore  # noqa: E402
    ConfirmationBoundaryType,
    ConfirmationRequest,
)
from planned_command import PlannedCommand  # type: ignore  # noqa: E402
from step import Step, StepAction, StepStatus  # type: ignore  # noqa: E402
from target import Target, TargetType  # type: ignore  # noqa: E402

_SUPPORTED_INTENTS = {
    "open_app",
    "open_file",
    "open_folder",
    "open_website",
    "focus_window",
    "close_window",
    "close_app",
    "list_windows",
    "search_local",
    "prepare_workspace",
    "run_protocol",
    "clarify",
    "confirm",
}

_STEP_REQUIRED_INTENTS = {
    "open_app",
    "open_file",
    "open_folder",
    "open_website",
    "focus_window",
    "close_window",
    "close_app",
    "list_windows",
    "search_local",
    "prepare_workspace",
    "run_protocol",
}
_MARKDOWN_SUFFIXES = (".md", ".markdown", ".mdown")
_SEARCH_IGNORE_TERMS = {"file", "files", "document", "documents", "for", "the", "a", "an"}
_CODE_EDITOR_NAMES = {"visual studio code", "vs code", "vscode", "code"}
_BROWSER_APP_NAMES = {"safari", "google chrome", "chrome", "browser", "web browser"}


def build_execution_plan(command: Command) -> PlannedCommand:
    """Build an ordered execution plan from a validated command."""
    intent = _intent_value(getattr(command, "intent", ""))
    if intent not in _SUPPORTED_INTENTS:
        raise ValueError(f"Unsupported intent for planning: {intent!r}")

    planned_command = command
    status_message_override: str | None = None
    if intent == "run_protocol":
        expansion = expand_protocol_command(command)
        planned_command = expansion.command
        steps = list(expansion.steps)
        status_message_override = expansion.status_message
    else:
        steps = _steps_for_intent(command, intent)
    if intent in _STEP_REQUIRED_INTENTS and not steps:
        raise ValueError(f"No executable steps generated for required intent: {intent!r}")
    status_message = status_message_override or _plan_status_message(intent, steps)
    requires_confirmation = bool(getattr(planned_command, "requires_confirmation", False)) or any(
        step.requires_confirmation for step in steps
    )

    planned_command = _clone_command_with_plan(
        command=planned_command,
        execution_steps=steps,
        status_message=status_message,
        requires_confirmation=requires_confirmation,
    )
    boundaries = _build_confirmation_boundaries(planned_command, steps)

    return PlannedCommand(
        command=planned_command,
        execution_steps=steps,
        status_message=status_message,
        confirmation_boundaries=boundaries or None,
    )


def _steps_for_intent(command: Command, intent: str) -> list[Step]:
    targets = list(getattr(command, "targets", []) or [])
    parameters = dict(getattr(command, "parameters", {}) or {})

    if intent == "open_app":
        return [
            _make_step(index + 1, DesktopAction.OPEN_APP, target)
            for index, target in enumerate(targets)
            if _target_type_value(target.type) == TargetType.APPLICATION.value
        ]

    if intent == "open_file":
        target = _first_target(targets, TargetType.FILE)
        return [_make_step(1, DesktopAction.OPEN_FILE, target, parameters=_open_target_parameters(parameters, target))]

    if intent == "open_folder":
        target = _first_target(targets, TargetType.FOLDER)
        return [_make_step(1, DesktopAction.OPEN_FOLDER, target, parameters=_open_target_parameters(parameters, target))]

    if intent == "open_website":
        target = _first_target(targets, TargetType.BROWSER)
        step_parameters = _website_parameters(parameters, target)
        return [_make_step(1, DesktopAction.OPEN_WEBSITE, target, parameters=step_parameters)]

    if intent == "focus_window":
        return [_make_step(1, DesktopAction.FOCUS_WINDOW, _first_target(targets, TargetType.WINDOW))]

    if intent == "close_window":
        return [
            _make_step(
                1,
                DesktopAction.CLOSE_WINDOW,
                _first_target(targets, TargetType.WINDOW),
                requires_confirmation=True,
            )
        ]

    if intent == "close_app":
        return [
            _make_step(
                1,
                DesktopAction.CLOSE_APP,
                _first_target(targets, TargetType.APPLICATION),
                requires_confirmation=True,
            )
        ]

    if intent == "list_windows":
        target = targets[0] if targets else Target(type=TargetType.WINDOW, name="windows")
        return [_make_step(1, DesktopAction.LIST_WINDOWS, target)]

    if intent == "search_local":
        return _search_local_steps(targets, parameters)

    if intent == "prepare_workspace":
        return _prepare_workspace_steps(command)

    return []


def _prepare_workspace_steps(command: Command) -> list[Step]:
    targets = _normalized_workspace_targets(list(getattr(command, "targets", []) or []))
    parameters = dict(getattr(command, "parameters", {}) or {})
    app_hint = _preferred_workspace_app_hint(targets, parameters)

    if targets:
        steps: list[Step] = []
        step_index = 1
        for target in targets:
            target_type = _target_type_value(target.type)
            if target_type == TargetType.APPLICATION.value:
                steps.append(_make_step(step_index, DesktopAction.OPEN_APP, target))
                step_index += 1
                continue

            if target_type == TargetType.FOLDER.value:
                step_parameters = _open_target_parameters(parameters, target, app_hint=app_hint)
                steps.append(_make_step(step_index, DesktopAction.OPEN_FOLDER, target, parameters=step_parameters))
                step_index += 1
                continue

            if target_type == TargetType.BROWSER.value:
                url = _website_url(parameters, target)
                if url:
                    steps.append(
                        _make_step(
                            step_index,
                            DesktopAction.OPEN_WEBSITE,
                            target,
                            parameters={"url": url},
                        )
                    )
                else:
                    browser_target = Target(type=TargetType.APPLICATION, name=target.name or "browser")
                    steps.append(_make_step(step_index, DesktopAction.OPEN_APP, browser_target))
                step_index += 1
                continue

            raise ValueError("prepare_workspace received unsupported target type for planning.")
        return steps

    sequence = parameters.get("sequence")
    if sequence:
        return _prepare_workspace_sequence_steps(sequence)

    raise ValueError("prepare_workspace requires explicit targets or explicit sequence to build steps.")


def _search_local_steps(targets: list[Target], parameters: dict[str, Any]) -> list[Step]:
    scope_target = targets[0] if targets else Target(type=TargetType.FOLDER, name="local")
    step_parameters = {"query": parameters.get("query")}
    for key in ("scope_path", "scope_source", "sort_hint", "file_type", "open_requested", "filename_hint"):
        if parameters.get(key) is not None:
            step_parameters[key] = parameters[key]

    steps = [_make_step(1, DesktopAction.SEARCH_LOCAL, scope_target, parameters=step_parameters)]
    if not bool(parameters.get("open_requested")):
        return steps

    open_target = _resolved_search_open_target(scope_target, step_parameters)
    steps.append(_make_step(2, DesktopAction.OPEN_FILE, open_target))
    return steps


def _resolved_search_open_target(scope_target: Target, parameters: dict[str, Any]) -> Target:
    scope_path = _search_scope_path(scope_target, parameters)
    if scope_path is not None:
        resolved_file = _select_search_result(scope_path, parameters)
        if resolved_file is not None:
            return Target(type=TargetType.FILE, name=resolved_file.name, path=str(resolved_file))

    fallback_name = _search_result_label(parameters)
    fallback_path = f"/__jarvis_unresolved__/{_safe_file_slug(fallback_name or 'latest-file')}"
    return Target(type=TargetType.FILE, name=fallback_name, path=fallback_path)


def _search_scope_path(scope_target: Target, parameters: dict[str, Any]) -> Path | None:
    raw_scope_path = str(parameters.get("scope_path", "")).strip()
    if raw_scope_path:
        candidate = Path(raw_scope_path).expanduser()
        if candidate.is_dir():
            return candidate

    raw_target_path = str(getattr(scope_target, "path", "") or "").strip()
    if raw_target_path:
        candidate = Path(raw_target_path).expanduser()
        if candidate.is_dir():
            return candidate

    return None


def _select_search_result(scope_path: Path, parameters: dict[str, Any]) -> Path | None:
    candidates = [path for path in _iter_search_files(scope_path) if _is_search_candidate_file(path, parameters)]
    if not candidates:
        return None

    sort_hint = str(parameters.get("sort_hint", "")).strip()
    filename_hint = str(parameters.get("filename_hint", "")).strip().lower()
    query = str(parameters.get("query", "")).strip()

    def rank(path: Path) -> tuple[int, int, str]:
        match_rank = _candidate_match_rank(path, filename_hint, query, parameters)
        recency_rank = -int(path.stat().st_mtime)
        return (match_rank, recency_rank, str(path).lower())

    if sort_hint == "latest":
        candidates.sort(key=rank)
    else:
        candidates.sort(key=lambda path: (_candidate_match_rank(path, filename_hint, query, parameters), str(path).lower()))

    return candidates[0]


def _iter_search_files(scope_path: Path) -> list[Path]:
    candidates: list[Path] = []
    try:
        iterator = scope_path.rglob("*")
    except OSError:
        return candidates

    for path in iterator:
        candidates.append(path)
    return candidates


def _is_search_candidate_file(path: Path, parameters: dict[str, Any]) -> bool:
    try:
        is_file = path.is_file()
    except OSError:
        return False
    if not is_file:
        return False

    file_type = str(parameters.get("file_type", "")).strip()
    if file_type == "markdown" and path.suffix.lower() not in _MARKDOWN_SUFFIXES:
        return False

    filename_hint = str(parameters.get("filename_hint", "")).strip().lower()
    if filename_hint:
        normalized_name = path.name.lower()
        normalized_stem = path.stem.lower()
        if filename_hint == normalized_name or filename_hint == normalized_stem:
            return True
        return filename_hint in normalized_name

    query = str(parameters.get("query", "")).strip()
    if _is_generic_search_query(query, parameters):
        return True
    return _path_matches_search_query(path, query, parameters)


def _candidate_match_rank(path: Path, filename_hint: str, query: str, parameters: dict[str, Any]) -> int:
    normalized_name = path.name.lower()
    normalized_stem = path.stem.lower()

    if filename_hint:
        if filename_hint == normalized_name or filename_hint == normalized_stem:
            return 0
        if filename_hint in normalized_name:
            return 1
        return 3

    if _is_generic_search_query(query, parameters):
        return 0

    lowered_query = query.lower().strip()
    if lowered_query and (lowered_query == normalized_name or lowered_query == normalized_stem):
        return 0
    if lowered_query and lowered_query in normalized_name:
        return 1
    if _path_matches_search_query(path, query, parameters):
        return 2
    return 3


def _path_matches_search_query(path: Path, query: str, parameters: dict[str, Any]) -> bool:
    if not query:
        return True
    lowered_name = path.name.lower()
    tokens = [
        token
        for token in re.findall(r"[a-z0-9._-]+", query.lower())
        if token not in _SEARCH_IGNORE_TERMS
    ]
    if str(parameters.get("file_type", "")).strip() == "markdown":
        tokens = [token for token in tokens if token not in {"markdown", "md"}]
    if not tokens:
        return True
    return all(token in lowered_name for token in tokens)


def _is_generic_search_query(query: str, parameters: dict[str, Any]) -> bool:
    normalized = re.sub(r"\s+", " ", query.lower()).strip()
    if str(parameters.get("file_type", "")).strip() == "markdown" and normalized in {"", "markdown", "md"}:
        return True
    return normalized in {
        "",
        "latest file",
        "newest file",
        "most recent file",
        "last file",
        "the latest file",
        "the newest file",
        "the most recent file",
        "the last file",
    }


def _search_result_label(parameters: dict[str, Any]) -> str:
    filename_hint = str(parameters.get("filename_hint", "")).strip()
    if filename_hint:
        return filename_hint
    query = str(parameters.get("query", "")).strip()
    if query:
        return query
    if str(parameters.get("file_type", "")).strip() == "markdown":
        return "latest-markdown-file"
    return "latest-file"


def _safe_file_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip("-")
    return slug or "latest-file"


def _prepare_workspace_sequence_steps(sequence: Any) -> list[Step]:
    if not isinstance(sequence, list):
        raise ValueError("prepare_workspace sequence must be a list.")

    steps: list[Step] = []
    allowed_actions = {
        DesktopAction.OPEN_APP.value,
        DesktopAction.OPEN_FOLDER.value,
        DesktopAction.OPEN_WEBSITE.value,
    }

    for index, item in enumerate(sequence, start=1):
        if not isinstance(item, dict):
            raise ValueError("prepare_workspace sequence items must be objects.")

        action_name = str(item.get("action", "")).strip()
        if action_name not in allowed_actions:
            raise ValueError("prepare_workspace sequence contains unsupported action.")

        target_payload = item.get("target")
        if not isinstance(target_payload, dict):
            raise ValueError("prepare_workspace sequence items must include explicit target objects.")

        target = _target_from_mapping(target_payload)
        step_parameters = item.get("parameters") if isinstance(item.get("parameters"), dict) else None
        desktop_action = DesktopAction(action_name)
        steps.append(_make_step(index, desktop_action, target, parameters=step_parameters))

    return steps


def _open_target_parameters(
    command_parameters: dict[str, Any],
    target: Target,
    app_hint: str | None = None,
) -> dict[str, Any] | None:
    explicit_app = app_hint or _explicit_app_parameter(command_parameters, target)
    if not explicit_app:
        return None
    return {"app": explicit_app}


def _explicit_app_parameter(command_parameters: dict[str, Any], target: Target) -> str | None:
    command_app = str(command_parameters.get("app", "")).strip()
    if command_app:
        return command_app

    metadata = getattr(target, "metadata", None) or {}
    target_app = str(metadata.get("app", "")).strip()
    if target_app:
        return target_app
    return None


def _preferred_workspace_app_hint(targets: list[Target], parameters: dict[str, Any]) -> str | None:
    command_app = str(parameters.get("app", "")).strip()
    if command_app and _is_code_editor_app(command_app):
        return command_app

    for target in targets:
        if _target_type_value(target.type) != TargetType.APPLICATION.value:
            continue
        app_name = str(getattr(target, "name", "")).strip()
        if app_name and _is_code_editor_app(app_name):
            return app_name
    return None


def _normalized_workspace_targets(targets: list[Target]) -> list[Target]:
    unique_targets: list[tuple[int, Target]] = []
    seen: set[tuple[str, str, str, str]] = set()

    for index, target in enumerate(targets):
        key = _workspace_target_key(target)
        if key in seen:
            continue
        seen.add(key)
        unique_targets.append((index, target))

    unique_targets.sort(key=lambda item: (_workspace_target_rank(item[1]), item[0]))
    return [item[1] for item in unique_targets]


def _workspace_target_key(target: Target) -> tuple[str, str, str, str]:
    target_type = _target_type_value(getattr(target, "type", "unknown"))
    name = str(getattr(target, "name", "")).strip().lower()
    path = str(getattr(target, "path", "") or "").strip().lower()
    metadata = getattr(target, "metadata", None) or {}
    url = str(metadata.get("url", "")).strip().lower()
    return (target_type, name, path, url)


def _workspace_target_rank(target: Target) -> int:
    target_type = _target_type_value(getattr(target, "type", "unknown"))
    if target_type == TargetType.APPLICATION.value:
        app_name = str(getattr(target, "name", "")).strip()
        if _is_code_editor_app(app_name):
            return 0
        if _is_browser_app(app_name):
            return 3
        return 2
    if target_type == TargetType.FOLDER.value:
        return 1
    if target_type == TargetType.BROWSER.value:
        return 3
    return 4


def _is_code_editor_app(value: str) -> bool:
    return _normalize_workspace_name(value) in _CODE_EDITOR_NAMES


def _is_browser_app(value: str) -> bool:
    return _normalize_workspace_name(value) in _BROWSER_APP_NAMES


def _normalize_workspace_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def _target_from_mapping(raw_target: dict[str, Any]) -> Target:
    target_type = _coerce_target_type(str(raw_target.get("type", "unknown")))
    target_name = str(raw_target.get("name", "")).strip()
    if not target_name:
        raise ValueError("Sequence target is missing name.")
    return Target(
        type=target_type,
        name=target_name,
        path=raw_target.get("path"),
        metadata=raw_target.get("metadata") if isinstance(raw_target.get("metadata"), dict) else None,
    )


def _make_step(
    index: int,
    action: DesktopAction,
    target: Target,
    parameters: dict[str, Any] | None = None,
    requires_confirmation: bool = False,
) -> Step:
    step_parameters = dict(parameters or {}) or None
    return Step(
        id=f"step_{index}",
        action=StepAction(action.value),
        target=_clone_target(target),
        parameters=step_parameters,
        status=StepStatus.PENDING,
        requires_confirmation=requires_confirmation,
    )


def _first_target(targets: list[Target], required_type: TargetType) -> Target:
    for target in targets:
        if _target_type_value(target.type) == required_type.value:
            return target
    raise ValueError(f"Missing target required for planning: {required_type.value!r}.")


def _website_parameters(parameters: dict[str, Any], target: Target) -> dict[str, Any]:
    url = _website_url(parameters, target)
    if not url:
        raise ValueError("open_website planning requires URL in parameters or target metadata.")
    return {"url": url}


def _website_url(parameters: dict[str, Any], target: Target) -> str:
    if str(parameters.get("url", "")).strip():
        return str(parameters["url"]).strip()
    metadata = target.metadata or {}
    if str(metadata.get("url", "")).strip():
        return str(metadata["url"]).strip()
    return ""


def _build_confirmation_boundaries(command: Command, steps: list[Step]) -> list[ConfirmationRequest]:
    boundaries: list[ConfirmationRequest] = []
    if bool(getattr(command, "requires_confirmation", False)):
        boundaries.append(
            ConfirmationRequest(
                message=_command_confirmation_message(command, steps),
                affected_targets=[_clone_target(target) for target in list(getattr(command, "targets", []) or [])],
                boundary_type=ConfirmationBoundaryType.COMMAND,
            )
        )

    for step in steps:
        if not step.requires_confirmation:
            continue
        boundaries.append(
            ConfirmationRequest(
                message=_step_confirmation_message(step),
                affected_targets=[_clone_target(step.target)],
                boundary_type=ConfirmationBoundaryType.STEP,
            )
        )

    return boundaries


def _command_confirmation_message(command: Command, steps: list[Step]) -> str:
    intent = _intent_value(command.intent)
    if intent == "run_protocol":
        protocol_name = str(getattr(command, "parameters", {}).get("protocol_display_name", "") or "").strip()
        if protocol_name:
            return f"Approve protocol {protocol_name} before execution."
    target_names = _target_names(list(getattr(command, "targets", []) or []))
    if target_names:
        return f"Approve {intent} for {', '.join(target_names)} before execution."
    if steps:
        return f"Approve command before running {steps[0].action.value}."
    return "Approve command before execution."


def _step_confirmation_message(step: Step) -> str:
    target_name = str(getattr(step.target, "name", "")).strip() or "target"
    return f"Approve {step.action.value} for {target_name}."


def _target_names(targets: list[Target]) -> list[str]:
    names: list[str] = []
    for target in targets:
        name = str(getattr(target, "name", "")).strip()
        if name:
            names.append(name)
    return names


def _clone_command_with_plan(
    command: Command,
    execution_steps: list[Step],
    status_message: str,
    requires_confirmation: bool,
) -> Command:
    return Command(
        raw_input=str(getattr(command, "raw_input", "")),
        intent=getattr(command, "intent"),
        targets=[_clone_target(target) for target in list(getattr(command, "targets", []) or [])],
        parameters=dict(getattr(command, "parameters", {}) or {}),
        confidence=float(getattr(command, "confidence", 0.0)),
        requires_confirmation=requires_confirmation,
        execution_steps=execution_steps,
        status_message=status_message,
    )


def _clone_target(target: Target) -> Target:
    return Target(
        type=_coerce_target_type(_target_type_value(getattr(target, "type", "unknown"))),
        name=str(getattr(target, "name", "")),
        path=getattr(target, "path", None),
        metadata=dict(getattr(target, "metadata", {}) or {}) or None,
    )


def _coerce_target_type(value: str) -> TargetType:
    for target_type in TargetType:
        if target_type.value == value:
            return target_type
    return TargetType.UNKNOWN


def _target_type_value(target_type: Any) -> str:
    return str(getattr(target_type, "value", target_type))


def _intent_value(intent: Any) -> str:
    return str(getattr(intent, "value", intent))


def _plan_status_message(intent: str, steps: list[Step]) -> str:
    if intent in {"clarify", "confirm"}:
        return "No desktop steps generated for clarification or confirmation intent."
    if not steps:
        return "No executable steps generated."
    if intent == "run_protocol":
        return f"Planned {len(steps)} step(s) for run_protocol."
    return f"Planned {len(steps)} step(s) for {intent}."
