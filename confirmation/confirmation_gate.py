"""Confirmation request builder for JARVIS MVP."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from types.confirmation_request import ConfirmationRequest


_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from command import Command  # type: ignore  # noqa: E402
from confirmation_request import ConfirmationBoundaryType, ConfirmationRequest  # type: ignore  # noqa: E402
from step import Step  # type: ignore  # noqa: E402
from target import Target, TargetType  # type: ignore  # noqa: E402


def request_confirmation(boundary: Any) -> ConfirmationRequest:
    """Build a confirmation request from command-level or step-level boundary input."""
    if isinstance(boundary, ConfirmationRequest):
        return boundary

    if isinstance(boundary, Command):
        return ConfirmationRequest(
            message=_command_message(boundary),
            affected_targets=[_clone_target(target) for target in list(boundary.targets or [])],
            boundary_type=ConfirmationBoundaryType.COMMAND,
        )

    if isinstance(boundary, Step):
        return ConfirmationRequest(
            message=_step_message(boundary),
            affected_targets=[_clone_target(boundary.target)],
            boundary_type=ConfirmationBoundaryType.STEP,
        )

    raise TypeError("Unsupported confirmation boundary type.")


def _command_message(command: Command) -> str:
    intent = _intent_value(command.intent)
    target_names = [str(target.name).strip() for target in list(command.targets or []) if str(target.name).strip()]
    if target_names:
        return f"Approve {intent} for {', '.join(target_names)}?"
    return f"Approve command for {intent}?"


def _step_message(step: Step) -> str:
    target_name = str(getattr(step.target, "name", "")).strip() or "target"
    return f"Approve step {step.action.value} for {target_name}?"


def _clone_target(target: Target) -> Target:
    return Target(
        type=_coerce_target_type(_target_type_value(getattr(target, "type", "unknown"))),
        name=str(getattr(target, "name", "")),
        path=getattr(target, "path", None),
        metadata=dict(getattr(target, "metadata", {}) or {}) or None,
    )


def _intent_value(intent: Any) -> str:
    return str(getattr(intent, "value", intent))


def _target_type_value(target_type: Any) -> str:
    return str(getattr(target_type, "value", target_type))


def _coerce_target_type(value: str) -> TargetType:
    for target_type in TargetType:
        if target_type.value == value:
            return target_type
    return TargetType.UNKNOWN

