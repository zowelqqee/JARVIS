"""In-memory supervised runtime loop for JARVIS MVP."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from clarification.clarification_handler import apply_clarification, build_clarification
from confirmation.confirmation_gate import request_confirmation
from executor.desktop_executor import execute_step
from input.adapter import InputNormalizationError, normalize_input
from parser.command_parser import parse_command
from planner.execution_planner import build_execution_plan
from runtime.state_machine import assert_valid_transition, normalize_state_value
from ui.visibility_mapper import VisibilityPayload, map_visibility
from validator.command_validator import validate_command

if TYPE_CHECKING:
    from context.session_context import SessionContext


_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from command import Command  # type: ignore  # noqa: E402
from clarification_request import ClarificationRequest  # type: ignore  # noqa: E402
from confirmation_request import (  # type: ignore  # noqa: E402
    ConfirmationBoundaryType,
    ConfirmationRequest,
    ConfirmationResult,
)
from jarvis_error import ErrorCategory, ErrorCode, JarvisError  # type: ignore  # noqa: E402
from step import Step, StepStatus  # type: ignore  # noqa: E402


_CONFIRM_APPROVAL_WORDS = {"yes", "confirm", "ok", "continue"}
_CONFIRM_DENIAL_WORDS = {"no", "cancel", "stop"}
_CLARIFICATION_CANCEL_WORDS = {"cancel", "stop"}
_FRESH_COMMAND_PREFIXES = (
    "open ",
    "launch ",
    "start ",
    "reopen ",
    "close ",
    "find ",
    "search ",
    "prepare ",
    "set up ",
    "show ",
    "list ",
    "focus ",
    "switch ",
    "use ",
    "run ",
)


@dataclass(slots=True)
class RuntimeResult:
    """Minimal runtime loop output for one supervised command pass."""

    runtime_state: str
    command_summary: str | None = None
    clarification_request: ClarificationRequest | None = None
    confirmation_request: ConfirmationRequest | None = None
    completed_steps: list[Step] = field(default_factory=list)
    current_step: Step | None = None
    blocked_reason: str | None = None
    last_error: JarvisError | None = None
    completion_summary: str | None = None
    visibility: VisibilityPayload = field(default_factory=dict)


@dataclass(slots=True)
class RuntimeManager:
    """Minimal runtime orchestrator for the MVP supervised flow."""

    current_state: str = "idle"
    active_command: Command | None = None
    current_step_index: int | None = None
    last_error: JarvisError | None = None
    blocked_reason: str | None = None
    clarification_request: ClarificationRequest | None = None
    confirmation_request: ConfirmationRequest | None = None
    completed_steps: list[Step] = field(default_factory=list)
    completed_step_results: dict[str, Any] = field(default_factory=dict)
    current_step: Step | None = None

    def set_active_command(self, command: Command | None) -> None:
        """Set or clear the active command bound to runtime state."""
        self.active_command = command
        self.current_step_index = None
        self.current_step = None
        self.completed_steps = []
        self.completed_step_results = {}
        self.blocked_reason = None
        self.clarification_request = None
        self.confirmation_request = None
        self.last_error = None

    def transition_to(self, next_state: str) -> str:
        """Transition to the next runtime state if the transition is legal."""
        assert_valid_transition(self.current_state, next_state)
        self.current_state = normalize_state_value(next_state)
        return self.current_state

    def clear_runtime(self) -> None:
        """Reset runtime holder to idle with no active command context."""
        self.current_state = "idle"
        self.active_command = None
        self.current_step_index = None
        self.last_error = None
        self.blocked_reason = None
        self.clarification_request = None
        self.confirmation_request = None
        self.completed_steps = []
        self.completed_step_results = {}
        self.current_step = None

    def handle_input(self, raw_input: str, session_context: SessionContext | None = None) -> RuntimeResult:
        """Run one supervised in-memory MVP command pass or resume an existing blocked flow."""
        start_state = normalize_state_value(self.current_state)

        if start_state == "awaiting_clarification":
            return self._handle_clarification_reply(raw_input, session_context)

        if start_state == "awaiting_confirmation":
            return self._handle_confirmation_reply(raw_input, session_context)

        if start_state in {"parsing", "validating", "planning", "executing"}:
            self._sync_session_context(session_context)
            return self._build_result()

        if start_state == "completed":
            if session_context is not None:
                session_context.clear_expired_or_resettable_context(preserve_recent_context=True)
            self.transition_to("idle")
        elif start_state in {"failed", "cancelled"}:
            if session_context is not None:
                session_context.clear_expired_or_resettable_context(preserve_recent_context=False)
            self.transition_to("idle")

        return self._handle_new_command(raw_input, session_context)

    def _handle_new_command(self, raw_input: str, session_context: SessionContext | None) -> RuntimeResult:
        if session_context is not None:
            session_context.clear_expired_or_resettable_context(preserve_recent_context=True)

        self.set_active_command(None)
        self.transition_to("parsing")

        try:
            normalized_input = normalize_input(raw_input)
            parsed_command = parse_command(normalized_input, session_context)
        except InputNormalizationError as exc:
            return self._fail_with_error(self._input_error(exc), session_context)
        except Exception as exc:
            return self._fail_with_error(
                self._runtime_error(
                    code=ErrorCode.UNREADABLE_INPUT,
                    message=f"Input parsing failed: {exc}",
                    category=ErrorCategory.INPUT_ERROR,
                ),
                session_context,
            )

        self.active_command = parsed_command
        self._sync_session_context(session_context)
        self.transition_to("validating")
        return self._validate_and_continue(parsed_command, session_context, reset_progress=True)

    def _handle_clarification_reply(self, raw_input: str, session_context: SessionContext | None) -> RuntimeResult:
        if self.active_command is None:
            return self._fail_with_error(
                self._blocked_state_error("Clarification reply received without an active command."),
                session_context,
            )

        reply = self._normalize_optional_input(raw_input)
        if reply is None:
            self.blocked_reason = self._clarification_prompt()
            self._sync_session_context(session_context)
            return self._build_result()

        if self._should_restart_as_fresh_command(reply):
            return self._restart_from_blocked_state(reply, session_context)

        if reply.lower() in _CLARIFICATION_CANCEL_WORDS:
            return self._cancel_with_error(self._cancellation_error("Command cancelled."), session_context)

        if session_context is not None:
            session_context.set_recent_clarification_answer(reply)

        patched_command = apply_clarification(self.active_command, reply)
        self.active_command = patched_command
        self.clarification_request = None
        self.blocked_reason = None
        self.last_error = None
        self.transition_to("validating")
        return self._validate_and_continue(patched_command, session_context, reset_progress=False)

    def _handle_confirmation_reply(self, raw_input: str, session_context: SessionContext | None) -> RuntimeResult:
        if self.active_command is None:
            return self._fail_with_error(
                self._blocked_state_error("Confirmation reply received without an active command."),
                session_context,
            )

        reply = self._normalize_optional_input(raw_input)
        decision = self._parse_confirmation_reply(reply)

        if decision == "unclear":
            self.blocked_reason = "Please confirm or cancel."
            self.last_error = self._confirmation_pending_error()
            if session_context is not None:
                session_context.set_recent_confirmation_state(ConfirmationResult.PENDING)
            self._sync_session_context(session_context)
            return self._build_result()

        if decision == "deny":
            if session_context is not None:
                session_context.set_recent_confirmation_state(ConfirmationResult.DENIED)
            return self._cancel_with_error(
                self._confirmation_denied_error(),
                session_context,
                completion_summary="Confirmation denied. Command cancelled.",
            )

        if session_context is not None:
            session_context.set_recent_confirmation_state(ConfirmationResult.APPROVED)

        self._clear_approved_confirmation_boundary()
        self.last_error = None
        self.blocked_reason = None
        self.clarification_request = None
        self.confirmation_request = None
        self.transition_to("executing")
        return self._execute_current_command(session_context, start_index=self._resume_step_index())

    def _validate_and_continue(
        self,
        command: Command,
        session_context: SessionContext | None,
        reset_progress: bool,
    ) -> RuntimeResult:
        validation_result = validate_command(command)
        if not bool(getattr(validation_result, "valid", False)):
            error = getattr(validation_result, "error", None) or self._runtime_error(
                code=ErrorCode.EXECUTION_FAILED,
                message="Validation failed without structured error.",
                category=ErrorCategory.VALIDATION_ERROR,
            )
            self.last_error = error
            self.blocked_reason = error.message

            if self._should_block_for_clarification(error):
                self.clarification_request = build_clarification(error, command)
                self.transition_to("awaiting_clarification")
                self._sync_session_context(session_context)
                return self._build_result()

            return self._fail_with_error(error, session_context)

        validated_command = getattr(validation_result, "validated_command", None) or command
        self.active_command = validated_command
        self.last_error = None
        self.blocked_reason = None
        self.clarification_request = None
        self.confirmation_request = None
        if reset_progress:
            self.completed_steps = []
            self.completed_step_results = {}
            self.current_step = None
            self.current_step_index = None
        self._sync_session_context(session_context)
        return self._plan_and_execute(validated_command, session_context)

    def _plan_and_execute(self, command: Command, session_context: SessionContext | None) -> RuntimeResult:
        self.transition_to("planning")
        try:
            planned = build_execution_plan(command)
        except Exception as exc:
            return self._fail_with_error(
                self._runtime_error(
                    code=ErrorCode.UNSUPPORTED_ACTION,
                    message=f"Planning failed: {exc}",
                    category=ErrorCategory.VALIDATION_ERROR,
                ),
                session_context,
            )

        steps = list(planned.execution_steps or [])
        if len(self.completed_steps) > len(steps):
            return self._fail_with_error(
                self._runtime_error(
                    code=ErrorCode.COMMAND_SCOPE_MISMATCH,
                    message="Planned command no longer matches completed step state.",
                    category=ErrorCategory.RUNTIME_ERROR,
                ),
                session_context,
            )

        for index in range(len(self.completed_steps)):
            steps[index].status = StepStatus.DONE

        self.active_command = planned.command
        self.active_command.execution_steps = steps
        self.active_command.status_message = planned.status_message
        self.current_step = steps[self.current_step_index] if self.current_step_index is not None and self.current_step_index < len(steps) else None

        self.transition_to("executing")
        if self._needs_command_level_confirmation(planned):
            self.current_step_index = self._resume_step_index() if steps else None
            self.current_step = steps[self.current_step_index] if self.current_step_index is not None and self.current_step_index < len(steps) else None
            return self._block_for_confirmation(
                self._command_confirmation_request(planned, self.active_command),
                session_context,
            )

        return self._execute_current_command(session_context, start_index=self._resume_step_index())

    def _execute_current_command(self, session_context: SessionContext | None, start_index: int) -> RuntimeResult:
        if self.active_command is None:
            return self._fail_with_error(
                self._blocked_state_error("Execution resume was requested without an active command."),
                session_context,
            )

        steps = list(getattr(self.active_command, "execution_steps", []) or [])
        if start_index > len(steps):
            return self._fail_with_error(
                self._runtime_error(
                    code=ErrorCode.BLOCKED_STATE_CORRUPTED,
                    message="Current step index is outside the planned step range.",
                    category=ErrorCategory.RUNTIME_ERROR,
                ),
                session_context,
            )

        for index in range(start_index, len(steps)):
            step = steps[index]
            self.current_step_index = index
            self.current_step = step

            if bool(getattr(step, "requires_confirmation", False)):
                return self._block_for_confirmation(request_confirmation(step), session_context)

            step.status = StepStatus.EXECUTING
            self._sync_session_context(session_context)

            action_result = execute_step(step)
            if not bool(getattr(action_result, "success", False)):
                step.status = StepStatus.FAILED
                return self._fail_with_error(self._execution_error(action_result, step), session_context)

            step.status = StepStatus.DONE
            self._record_completed_step(step, action_result)
            self._sync_session_context(session_context)

        self.current_step = None
        self.current_step_index = None
        self.confirmation_request = None
        self.clarification_request = None
        self.blocked_reason = None
        self.last_error = None
        self.transition_to("completed")
        if session_context is not None:
            session_context.set_recent_confirmation_state(None)
        self._sync_session_context(session_context)
        return self._build_result(
            completion_summary=f"Completed {_intent_value(self.active_command.intent)} with {len(self.completed_steps)} step(s)."
        )

    def _block_for_confirmation(
        self,
        confirmation_request: ConfirmationRequest,
        session_context: SessionContext | None,
    ) -> RuntimeResult:
        self.confirmation_request = confirmation_request
        self.last_error = self._confirmation_pending_error()
        self.blocked_reason = confirmation_request.message
        self.transition_to("awaiting_confirmation")
        if session_context is not None:
            session_context.set_recent_confirmation_state(ConfirmationResult.PENDING)
        self._sync_session_context(session_context)
        return self._build_result()

    def _fail_with_error(self, error: JarvisError, session_context: SessionContext | None) -> RuntimeResult:
        self.last_error = error
        self.blocked_reason = error.message
        self.clarification_request = None
        self.confirmation_request = None
        self.transition_to("failed")
        if session_context is not None:
            session_context.set_recent_confirmation_state(None)
        self._sync_session_context(session_context)
        return self._build_result()

    def _cancel_with_error(
        self,
        error: JarvisError,
        session_context: SessionContext | None,
        completion_summary: str | None = None,
    ) -> RuntimeResult:
        self.last_error = error
        self.blocked_reason = None
        self.clarification_request = None
        self.confirmation_request = None
        self.transition_to("cancelled")
        if session_context is not None:
            session_context.set_recent_confirmation_state(None)
        self._sync_session_context(session_context)
        return self._build_result(completion_summary=completion_summary or error.message)

    def _build_result(self, completion_summary: str | None = None) -> RuntimeResult:
        visibility = map_visibility(
            state=self.current_state,
            command=self.active_command,
            current_step=self.current_step,
            clarification=self.clarification_request,
            confirmation=self.confirmation_request,
            error=self.last_error,
            completed_steps=self.completed_steps,
            step_results=self.completed_step_results,
            blocked_reason=self.blocked_reason,
            completion_result=completion_summary,
        )
        return RuntimeResult(
            runtime_state=normalize_state_value(self.current_state),
            command_summary=visibility.get("command_summary"),
            clarification_request=self.clarification_request,
            confirmation_request=self.confirmation_request,
            completed_steps=list(self.completed_steps),
            current_step=self.current_step,
            blocked_reason=visibility.get("blocked_reason"),
            last_error=self.last_error,
            completion_summary=visibility.get("completion_result"),
            visibility=visibility,
        )

    def _sync_session_context(self, session_context: SessionContext | None) -> None:
        if session_context is None:
            return

        execution_steps = list(getattr(self.active_command, "execution_steps", []) or [])
        session_context.set_active_command(self.active_command)
        session_context.set_execution_state(
            runtime_state=self.current_state,
            current_step_index=self.current_step_index,
            step_statuses={step.id: step.status for step in execution_steps},
        )
        resolved_targets = self._resolved_completed_targets()
        if resolved_targets:
            session_context.set_recent_targets(resolved_targets)
        latest_target_context = self._latest_completed_target_context()
        if latest_target_context is not None:
            target, action = latest_target_context
            session_context.set_recent_primary_target(target, action=action)
        session_context.set_recent_workspace_context(self._workspace_context_value(self.active_command))
        self._sync_recent_search_results(session_context)

    def _sync_recent_search_results(self, session_context: SessionContext) -> None:
        latest_search_result = self._latest_completed_search_result()
        if latest_search_result is None:
            return
        matches, query, scope_path = latest_search_result
        session_context.set_recent_search_results(matches=matches, query=query, scope_path=scope_path)

    def _latest_completed_search_result(self) -> tuple[list[dict[str, Any]], str | None, str | None] | None:
        for step in reversed(self.completed_steps):
            if _action_value(getattr(step, "action", "")) != "search_local":
                continue
            action_result = self.completed_step_results.get(step.id)
            if action_result is None or not bool(getattr(action_result, "success", False)):
                continue
            details = getattr(action_result, "details", None)
            if not isinstance(details, dict):
                continue
            matches = details.get("matches")
            if not isinstance(matches, list):
                continue
            query = str(details.get("query", "")).strip() or None
            scope_path = str(details.get("scope_path", "")).strip() or None
            return (matches, query, scope_path)
        return None

    def _resolved_completed_targets(self) -> list[Any]:
        resolved_targets: list[Any] = []
        seen: set[tuple[str, str, str]] = set()
        for step in self.completed_steps:
            target = getattr(step, "target", None)
            if target is None or not self._is_resolved_target(target):
                continue
            target_type = str(getattr(getattr(target, "type", ""), "value", getattr(target, "type", "")))
            target_name = str(getattr(target, "name", "")).strip()
            target_path = str(getattr(target, "path", "") or "").strip()
            dedupe_key = (target_type, target_name, target_path)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            resolved_targets.append(target)
        return resolved_targets

    def _latest_completed_target_context(self) -> tuple[Any, str] | None:
        for step in reversed(self.completed_steps):
            target = getattr(step, "target", None)
            if target is None or not self._is_resolved_target(target):
                continue
            action = _action_value(getattr(step, "action", ""))
            return (target, action)
        return None

    def _record_completed_step(self, step: Step, action_result: Any) -> None:
        for index, existing_step in enumerate(self.completed_steps):
            if existing_step.id == step.id:
                self.completed_steps[index] = step
                self.completed_step_results[step.id] = action_result
                return
        self.completed_steps.append(step)
        self.completed_step_results[step.id] = action_result

    def _resume_step_index(self) -> int:
        if self.current_step_index is not None:
            return self.current_step_index
        return len(self.completed_steps)

    def _needs_command_level_confirmation(self, planned: Any) -> bool:
        if self._resume_step_index() > 0:
            return False
        if not bool(getattr(self.active_command, "requires_confirmation", False)):
            return False

        boundaries = list(getattr(planned, "confirmation_boundaries", []) or [])
        for boundary in boundaries:
            boundary_type = str(
                getattr(getattr(boundary, "boundary_type", ""), "value", getattr(boundary, "boundary_type", ""))
            )
            if boundary_type == ConfirmationBoundaryType.COMMAND.value:
                return True
        return False

    def _clear_approved_confirmation_boundary(self) -> None:
        if self.active_command is None:
            return

        self.active_command.requires_confirmation = False
        boundary_type = str(
            getattr(
                getattr(self.confirmation_request, "boundary_type", ConfirmationBoundaryType.STEP),
                "value",
                getattr(self.confirmation_request, "boundary_type", ConfirmationBoundaryType.STEP),
            )
        )

        steps = list(getattr(self.active_command, "execution_steps", []) or [])
        if not steps:
            return

        if boundary_type == ConfirmationBoundaryType.COMMAND.value:
            resume_index = self._resume_step_index()
            if 0 <= resume_index < len(steps):
                steps[resume_index].requires_confirmation = False
            return

        if self.current_step_index is not None and 0 <= self.current_step_index < len(steps):
            steps[self.current_step_index].requires_confirmation = False

    def _should_block_for_clarification(self, error: JarvisError) -> bool:
        clarifiable_codes = {
            ErrorCode.LOW_CONFIDENCE.value,
            ErrorCode.MISSING_PARAMETER.value,
            ErrorCode.TARGET_NOT_FOUND.value,
            ErrorCode.MULTIPLE_MATCHES.value,
            ErrorCode.FOLLOWUP_REFERENCE_UNCLEAR.value,
        }
        if bool(getattr(error, "terminal", False)):
            return False

        category_value = str(getattr(getattr(error, "category", ""), "value", getattr(error, "category", "")))
        if category_value == ErrorCategory.CLARIFICATION_BLOCK.value:
            return True

        code_value = _error_code_value(getattr(error, "code", ""))
        return code_value in clarifiable_codes

    def _command_confirmation_request(self, planned: Any, command: Command) -> ConfirmationRequest:
        boundaries = list(getattr(planned, "confirmation_boundaries", []) or [])
        for boundary in boundaries:
            boundary_type = str(
                getattr(getattr(boundary, "boundary_type", ""), "value", getattr(boundary, "boundary_type", ""))
            )
            if boundary_type == ConfirmationBoundaryType.COMMAND.value:
                return request_confirmation(boundary)
        return request_confirmation(command)

    def _normalize_optional_input(self, raw_input: str) -> str | None:
        try:
            return normalize_input(raw_input)
        except InputNormalizationError:
            return None

    def _parse_confirmation_reply(self, raw_input: str | None) -> str:
        if raw_input is None:
            return "unclear"

        lowered = raw_input.lower()
        if lowered in _CONFIRM_APPROVAL_WORDS:
            return "approve"
        if lowered in _CONFIRM_DENIAL_WORDS:
            return "deny"
        return "unclear"

    def _clarification_prompt(self) -> str:
        if self.clarification_request is not None:
            return self.clarification_request.message
        return "Please answer the clarification question."

    def _should_restart_as_fresh_command(self, reply: str) -> bool:
        lowered = reply.lower().strip()
        if not lowered:
            return False
        if lowered in _CLARIFICATION_CANCEL_WORDS:
            return False
        return any(lowered.startswith(prefix) for prefix in _FRESH_COMMAND_PREFIXES)

    def _restart_from_blocked_state(self, raw_input: str, session_context: SessionContext | None) -> RuntimeResult:
        current_state = normalize_state_value(self.current_state)
        if current_state not in {"awaiting_clarification", "awaiting_confirmation"}:
            return self._handle_new_command(raw_input, session_context)
        self.transition_to("cancelled")
        self.transition_to("idle")
        return self._handle_new_command(raw_input, session_context)

    def _workspace_context_value(self, command: Command | None) -> str | None:
        if command is None:
            return None

        parameters = dict(getattr(command, "parameters", {}) or {})
        workspace_value = str(parameters.get("workspace", "")).strip()
        if workspace_value:
            return workspace_value

        for target in list(getattr(command, "targets", []) or []):
            if not self._is_resolved_target(target):
                continue
            target_name = str(getattr(target, "name", "")).strip()
            if target_name:
                return target_name
            target_path = str(getattr(target, "path", "") or "").strip()
            if target_path:
                return target_path
        return None

    def _resolved_targets(self, command: Command | None) -> list[Any]:
        if command is None:
            return []
        return [target for target in list(getattr(command, "targets", []) or []) if self._is_resolved_target(target)]

    def _is_resolved_target(self, target: Any) -> bool:
        target_type = str(getattr(getattr(target, "type", ""), "value", getattr(target, "type", "")))
        if target_type == "unknown":
            return False
        if target_type in {"file", "folder"}:
            return bool(str(getattr(target, "name", "")).strip() or str(getattr(target, "path", "") or "").strip())
        return bool(str(getattr(target, "name", "")).strip())

    def _input_error(self, exc: InputNormalizationError) -> JarvisError:
        code = _coerce_error_code(getattr(exc, "code", ""), fallback=ErrorCode.UNREADABLE_INPUT)
        return JarvisError(
            category=ErrorCategory.INPUT_ERROR,
            code=code,
            message=str(exc),
            details=None,
            blocking=False,
            terminal=True,
        )

    def _runtime_error(self, code: ErrorCode, message: str, category: ErrorCategory) -> JarvisError:
        return JarvisError(
            category=category,
            code=code,
            message=message,
            details=None,
            blocking=False,
            terminal=True,
        )

    def _blocked_state_error(self, message: str) -> JarvisError:
        return JarvisError(
            category=ErrorCategory.RUNTIME_ERROR,
            code=ErrorCode.BLOCKED_STATE_CORRUPTED,
            message=message,
            details=None,
            blocking=False,
            terminal=True,
        )

    def _confirmation_pending_error(self) -> JarvisError:
        return JarvisError(
            category=ErrorCategory.CONFIRMATION_BLOCK,
            code=ErrorCode.CONFIRMATION_REQUIRED,
            message="Explicit confirmation is required before execution can continue.",
            details=None,
            blocking=True,
            terminal=False,
        )

    def _confirmation_denied_error(self) -> JarvisError:
        return JarvisError(
            category=ErrorCategory.CONFIRMATION_BLOCK,
            code=ErrorCode.CONFIRMATION_DENIED,
            message="Confirmation denied. Command cancelled.",
            details=None,
            blocking=False,
            terminal=True,
        )

    def _cancellation_error(self, message: str) -> JarvisError:
        return JarvisError(
            category=ErrorCategory.CANCELLATION,
            code=ErrorCode.USER_CANCELLED,
            message=message,
            details=None,
            blocking=False,
            terminal=True,
        )

    def _execution_error(self, action_result: Any, step: Step) -> JarvisError:
        raw_error = getattr(action_result, "error", None)
        raw_code = getattr(raw_error, "code", "") if raw_error is not None else ""
        code = _coerce_error_code(raw_code, fallback=ErrorCode.EXECUTION_FAILED)
        message = (
            str(getattr(raw_error, "message", "")).strip()
            if raw_error is not None
            else "Step execution failed."
        )
        return JarvisError(
            category=ErrorCategory.EXECUTION_ERROR,
            code=code,
            message=message or "Step execution failed.",
            details={"step_id": step.id, "action": _action_value(step.action)},
            blocking=False,
            terminal=True,
        )


def _coerce_error_code(value: Any, fallback: ErrorCode) -> ErrorCode:
    value_text = str(getattr(value, "value", value))
    for code in ErrorCode:
        if code.value == value_text:
            return code
    return fallback


def _intent_value(intent: Any) -> str:
    return str(getattr(intent, "value", intent))


def _action_value(action: Any) -> str:
    return str(getattr(action, "value", action))


def _error_code_value(code: Any) -> str:
    return str(getattr(code, "value", code))
