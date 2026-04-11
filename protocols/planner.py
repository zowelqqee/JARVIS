"""Expand declarative protocols into executable runtime steps."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from executor.desktop_actions import DesktopAction
from protocols.registry import get_protocol_by_id
from protocols.state_store import ProtocolStateStore
from user_language import prefers_russian_text

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from command import Command  # type: ignore  # noqa: E402
from step import Step, StepAction, StepStatus  # type: ignore  # noqa: E402
from target import Target, TargetType  # type: ignore  # noqa: E402


_DIRECT_PROTOCOL_ACTIONS = frozenset(
    {
        "open_app",
        "open_file",
        "open_folder",
        "open_website",
        "close_app",
        "search_local",
        "list_windows",
    }
)
_SUPPORTED_PROTOCOL_ACTIONS = _DIRECT_PROTOCOL_ACTIONS | {"play_music", "open_last_workspace"}


@dataclass(frozen=True, slots=True)
class ProtocolExpansion:
    """Expanded protocol command details ready for normal runtime planning."""

    command: Command
    steps: tuple[Step, ...]
    status_message: str


def supported_protocol_action_types() -> frozenset[str]:
    """Return the currently supported declarative protocol action types."""
    return _SUPPORTED_PROTOCOL_ACTIONS


def expand_protocol_command(command: Command) -> ProtocolExpansion:
    """Expand one `run_protocol` command into a normal executable step list."""
    parameters = dict(getattr(command, "parameters", {}) or {})
    protocol_id = str(parameters.get("protocol_id", "") or "").strip()
    definition = get_protocol_by_id(protocol_id)
    if definition is None:
        raise ValueError(f"Unknown protocol id: {protocol_id!r}.")

    state_store = ProtocolStateStore()
    template_context = state_store.template_context()
    prefers_russian = prefers_russian_text(str(getattr(command, "raw_input", "") or ""))

    steps: list[Step] = []
    for action_definition in definition.steps:
        expanded = _expand_protocol_action(
            action_definition=action_definition,
            step_start_index=len(steps) + 1,
            template_context=template_context,
        )
        steps.extend(expanded)

    if not steps:
        raise ValueError(f"Protocol {definition.id!r} produced no executable steps.")

    completion_text = _render_completion_text(
        definition=definition,
        template_context=template_context,
        prefers_russian=prefers_russian,
    )
    updated_parameters = dict(parameters)
    updated_parameters["protocol_display_name"] = definition.title
    updated_parameters["protocol_source"] = definition.source
    if completion_text:
        updated_parameters["protocol_completion_text"] = completion_text

    updated_command = Command(
        raw_input=str(getattr(command, "raw_input", "")),
        intent=getattr(command, "intent"),
        targets=list(getattr(command, "targets", []) or []),
        parameters=updated_parameters,
        confidence=float(getattr(command, "confidence", 0.0)),
        requires_confirmation=_protocol_requires_confirmation(command, definition),
        execution_steps=list(steps),
        status_message=f"Parsed protocol request for {definition.title}.",
    )
    return ProtocolExpansion(
        command=updated_command,
        steps=tuple(steps),
        status_message=f"Planned {len(steps)} step(s) for protocol {definition.id}.",
    )


def _expand_protocol_action(
    *,
    action_definition: object,
    step_start_index: int,
    template_context: dict[str, str],
) -> list[Step]:
    action_type = str(getattr(action_definition, "action_type", "") or "").strip()
    inputs = dict(getattr(action_definition, "inputs", {}) or {})
    requires_confirmation = getattr(action_definition, "requires_confirmation", None)
    on_failure = str(getattr(action_definition, "on_failure", "") or "stop").strip() or "stop"

    if action_type in _DIRECT_PROTOCOL_ACTIONS:
        step = _direct_step_from_protocol_action(
            action_type=action_type,
            inputs=inputs,
            step_index=step_start_index,
            requires_confirmation=bool(requires_confirmation),
        )
        return [step]

    if action_type == "play_music":
        app_name = str(inputs.get("app_name", "") or "Music").strip() or "Music"
        return [
            _make_step(
                step_start_index,
                DesktopAction.PLAY_MUSIC,
                Target(type=TargetType.APPLICATION, name=app_name),
                requires_confirmation=bool(requires_confirmation),
            )
        ]

    if action_type == "open_last_workspace":
        workspace_path = str(template_context.get("last_workspace_path", "") or "").strip()
        if not workspace_path:
            if on_failure == "continue_if_safe":
                return []
            raise ValueError("Protocol requires a remembered workspace, but no last workspace is stored.")

        app_name = str(inputs.get("app_name", "") or "").strip()
        workspace_label = Path(workspace_path).name or workspace_path
        steps: list[Step] = []
        next_index = step_start_index
        if app_name:
            steps.append(
                _make_step(
                    next_index,
                    DesktopAction.OPEN_APP,
                    Target(type=TargetType.APPLICATION, name=app_name),
                )
            )
            next_index += 1
        folder_parameters = {"app": app_name} if app_name else None
        steps.append(
            _make_step(
                next_index,
                DesktopAction.OPEN_FOLDER,
                Target(type=TargetType.FOLDER, name=workspace_label, path=workspace_path),
                parameters=folder_parameters,
                requires_confirmation=bool(requires_confirmation),
            )
        )
        return steps

    raise ValueError(f"Unsupported protocol action type: {action_type!r}.")


def _direct_step_from_protocol_action(
    *,
    action_type: str,
    inputs: dict[str, Any],
    step_index: int,
    requires_confirmation: bool,
) -> Step:
    if action_type == "open_app":
        app_name = str(inputs.get("app_name", "") or inputs.get("name", "")).strip()
        if not app_name:
            raise ValueError("Protocol open_app action requires app_name.")
        return _make_step(step_index, DesktopAction.OPEN_APP, Target(type=TargetType.APPLICATION, name=app_name), requires_confirmation=requires_confirmation)

    if action_type == "close_app":
        app_name = str(inputs.get("app_name", "") or inputs.get("name", "")).strip()
        if not app_name:
            raise ValueError("Protocol close_app action requires app_name.")
        return _make_step(step_index, DesktopAction.CLOSE_APP, Target(type=TargetType.APPLICATION, name=app_name), requires_confirmation=requires_confirmation)

    if action_type == "open_folder":
        folder_path = str(inputs.get("path", "") or "").strip()
        folder_name = str(inputs.get("name", "") or Path(folder_path).name or folder_path).strip()
        if not folder_path:
            raise ValueError("Protocol open_folder action requires path.")
        app_name = str(inputs.get("app_name", "") or inputs.get("app", "")).strip()
        parameters = {"app": app_name} if app_name else None
        return _make_step(
            step_index,
            DesktopAction.OPEN_FOLDER,
            Target(type=TargetType.FOLDER, name=folder_name, path=folder_path),
            parameters=parameters,
            requires_confirmation=requires_confirmation,
        )

    if action_type == "open_file":
        file_path = str(inputs.get("path", "") or "").strip()
        file_name = str(inputs.get("name", "") or Path(file_path).name or file_path).strip()
        if not file_path:
            raise ValueError("Protocol open_file action requires path.")
        app_name = str(inputs.get("app_name", "") or inputs.get("app", "")).strip()
        parameters = {"app": app_name} if app_name else None
        return _make_step(
            step_index,
            DesktopAction.OPEN_FILE,
            Target(type=TargetType.FILE, name=file_name, path=file_path),
            parameters=parameters,
            requires_confirmation=requires_confirmation,
        )

    if action_type == "open_website":
        url = str(inputs.get("url", "") or "").strip()
        browser_name = str(inputs.get("browser_name", "") or inputs.get("browser", "") or "Safari").strip() or "Safari"
        if not url:
            raise ValueError("Protocol open_website action requires url.")
        return _make_step(
            step_index,
            DesktopAction.OPEN_WEBSITE,
            Target(type=TargetType.BROWSER, name=browser_name, metadata={"url": url}),
            parameters={"url": url},
            requires_confirmation=requires_confirmation,
        )

    if action_type == "search_local":
        scope_path = str(inputs.get("scope_path", "") or "").strip()
        query = str(inputs.get("query", "") or "").strip()
        if not scope_path or not query:
            raise ValueError("Protocol search_local action requires scope_path and query.")
        return _make_step(
            step_index,
            DesktopAction.SEARCH_LOCAL,
            Target(type=TargetType.FOLDER, name=Path(scope_path).name or scope_path, path=scope_path),
            parameters={"query": query, "scope_path": scope_path},
            requires_confirmation=requires_confirmation,
        )

    if action_type == "list_windows":
        app_name = str(inputs.get("app_name", "") or inputs.get("name", "")).strip()
        target = Target(type=TargetType.WINDOW, name="windows") if not app_name else Target(type=TargetType.APPLICATION, name=app_name)
        return _make_step(step_index, DesktopAction.LIST_WINDOWS, target, requires_confirmation=requires_confirmation)

    raise ValueError(f"Unsupported direct protocol action type: {action_type!r}.")


def _make_step(
    index: int,
    action: DesktopAction,
    target: Target,
    parameters: dict[str, Any] | None = None,
    requires_confirmation: bool = False,
) -> Step:
    return Step(
        id=f"step_{index}",
        action=StepAction(action.value),
        target=target,
        parameters=dict(parameters or {}) or None,
        status=StepStatus.PENDING,
        requires_confirmation=requires_confirmation,
    )


def _protocol_requires_confirmation(command: Command, definition: object) -> bool:
    if bool(getattr(command, "requires_confirmation", False)):
        return True
    mode = str(getattr(getattr(definition, "confirmation_policy", None), "mode", "") or "").strip()
    if mode == "always":
        return True
    if mode == "if_sensitive_steps_present":
        return any(str(getattr(step, "action_type", "") or "").strip() == "close_app" for step in getattr(definition, "steps", ()))
    return False


def _render_completion_text(*, definition: object, template_context: dict[str, str], prefers_russian: bool) -> str | None:
    raw_template = (
        str(getattr(definition, "completion_message_ru", "") or "").strip()
        if prefers_russian
        else str(getattr(definition, "completion_message", "") or "").strip()
    )
    if not raw_template:
        raw_template = str(getattr(definition, "completion_message", "") or "").strip()
    if not raw_template:
        return None
    try:
        return raw_template.format(**template_context)
    except (KeyError, ValueError):
        return raw_template
