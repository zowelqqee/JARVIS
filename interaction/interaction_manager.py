"""Top-level dual-mode interaction manager."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from input.adapter import InputNormalizationError
from interaction.interaction_router import route_interaction
from qa.answer_backend import AnswerBackendKind
from qa.answer_config import AnswerBackendConfig, load_answer_backend_config
from qa.debug_trace import qa_debug_enabled, set_debug_payload
from qa.answer_engine import answer_question, classify_question
from runtime.runtime_manager import RuntimeManager
from ui.visibility_mapper import map_interaction_visibility, map_visibility

if TYPE_CHECKING:
    from context.session_context import SessionContext


_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from clarification_request import ClarificationRequest  # type: ignore  # noqa: E402
from interaction_kind import InteractionKind  # type: ignore  # noqa: E402
from interaction_result import InteractionResult  # type: ignore  # noqa: E402
from jarvis_error import ErrorCategory, ErrorCode, JarvisError  # type: ignore  # noqa: E402


@dataclass(slots=True)
class InteractionManager:
    """Route each input into command mode or question-answer mode."""

    runtime_manager: RuntimeManager = field(default_factory=RuntimeManager)
    answer_backend_config: AnswerBackendConfig = field(default_factory=load_answer_backend_config)
    answer_backend_kind: AnswerBackendKind | None = None

    def handle_input(self, raw_input: str, session_context: SessionContext | None = None) -> InteractionResult:
        """Handle one user input through the dual-mode routing layer."""
        debug_trace: dict[str, Any] | None = {} if qa_debug_enabled() else None
        decision = route_interaction(
            raw_input,
            session_context=session_context,
            runtime_state=self.runtime_manager.current_state,
        )
        set_debug_payload(
            debug_trace,
            "routing_decision",
            {
                "interaction_kind": getattr(decision.kind, "value", decision.kind),
                "confidence": round(float(getattr(decision, "confidence", 0.0) or 0.0), 3),
                "reason": decision.reason,
                "runtime_state": str(getattr(self.runtime_manager.current_state, "value", self.runtime_manager.current_state or "")).strip() or None,
            },
        )

        if decision.kind == InteractionKind.CLARIFICATION:
            clarification_request = ClarificationRequest(
                message=decision.clarification_message or "Do you want an answer or command execution?",
                code=ErrorCode.CLARIFICATION_REQUIRED.value,
                options=["answer", "execute"],
            )
            return InteractionResult(
                interaction_mode=InteractionKind.CLARIFICATION,
                normalized_input=decision.normalized_input,
                clarification_request=clarification_request,
                visibility=map_interaction_visibility(
                    interaction_mode=InteractionKind.CLARIFICATION,
                    clarification_request=clarification_request,
                ),
                metadata=_metadata_with_debug({"reason": decision.reason}, debug_trace),
            )

        if decision.kind == InteractionKind.COMMAND:
            runtime_result = self.runtime_manager.handle_input(decision.normalized_input or raw_input, session_context=session_context)
            return InteractionResult(
                interaction_mode=InteractionKind.COMMAND,
                normalized_input=decision.normalized_input,
                runtime_result=runtime_result,
                visibility=map_interaction_visibility(
                    interaction_mode=InteractionKind.COMMAND,
                    runtime_result=runtime_result,
                ),
                metadata=_metadata_with_debug({"reason": decision.reason}, debug_trace),
            )

        try:
            answer_backend_config = self._effective_answer_backend_config()
            answer_result = answer_question(
                decision.normalized_input,
                session_context=session_context,
                runtime_snapshot=self._runtime_snapshot(),
                backend_config=answer_backend_config,
                debug_trace=debug_trace,
            )
        except InputNormalizationError as exc:
            input_error = self._input_error(exc)
            return InteractionResult(
                interaction_mode=InteractionKind.QUESTION,
                normalized_input=decision.normalized_input,
                error=input_error,
                visibility=map_interaction_visibility(
                    interaction_mode=InteractionKind.QUESTION,
                    error=input_error,
                ),
                metadata=_metadata_with_debug(None, debug_trace),
            )
        except JarvisError as error:
            return InteractionResult(
                interaction_mode=InteractionKind.QUESTION,
                normalized_input=decision.normalized_input,
                error=error,
                visibility=map_interaction_visibility(
                    interaction_mode=InteractionKind.QUESTION,
                    error=error,
                ),
                metadata=_metadata_with_debug(None, debug_trace),
            )

        _remember_answer_context(
            session_context,
            raw_input=decision.normalized_input or raw_input,
            answer_result=answer_result,
        )

        return InteractionResult(
            interaction_mode=InteractionKind.QUESTION,
            normalized_input=decision.normalized_input,
            answer_result=answer_result,
            visibility=map_interaction_visibility(
                interaction_mode=InteractionKind.QUESTION,
                answer_result=answer_result,
            ),
            metadata=_metadata_with_debug({"answer_backend": answer_backend_config.backend_kind.value}, debug_trace),
        )

    def _runtime_snapshot(self) -> dict[str, Any]:
        visibility = map_visibility(
            state=self.runtime_manager.current_state,
            command=self.runtime_manager.active_command,
            current_step=self.runtime_manager.current_step,
            clarification=self.runtime_manager.clarification_request,
            confirmation=self.runtime_manager.confirmation_request,
            error=self.runtime_manager.last_error,
            completed_steps=self.runtime_manager.completed_steps,
            step_results=self.runtime_manager.completed_step_results,
            blocked_reason=self.runtime_manager.blocked_reason,
        )
        return {
            "runtime_state": visibility.get("runtime_state"),
            "command_summary": visibility.get("command_summary"),
            "current_step": visibility.get("current_step"),
            "completed_steps": visibility.get("completed_steps"),
            "blocked_reason": visibility.get("blocked_reason"),
            "blocked_kind": (
                "confirmation"
                if self.runtime_manager.confirmation_request is not None
                else "clarification"
                if self.runtime_manager.clarification_request is not None
                else None
            ),
            "clarification_question": getattr(self.runtime_manager.clarification_request, "message", None),
            "confirmation_message": getattr(self.runtime_manager.confirmation_request, "message", None),
        }

    def _input_error(self, exc: InputNormalizationError) -> JarvisError:
        code_text = str(getattr(exc, "code", ErrorCode.UNREADABLE_INPUT.value))
        error_code = ErrorCode.EMPTY_INPUT if code_text == ErrorCode.EMPTY_INPUT.value else ErrorCode.UNREADABLE_INPUT
        return JarvisError(
            category=ErrorCategory.INPUT_ERROR,
            code=error_code,
            message=str(exc),
            details={"code": code_text},
            blocking=False,
            terminal=True,
        )

    def _effective_answer_backend_config(self) -> AnswerBackendConfig:
        return self.answer_backend_config.with_backend_kind(self.answer_backend_kind)


def _remember_answer_context(
    session_context: SessionContext | None,
    *,
    raw_input: str,
    answer_result: Any,
) -> None:
    if session_context is None:
        return
    question = classify_question(raw_input, session_context=session_context)
    question_type_value = str(getattr(getattr(question, "question_type", None), "value", getattr(question, "question_type", "")) or "").strip()
    context_refs = getattr(question, "context_refs", {}) or {}
    if not isinstance(context_refs, dict):
        context_refs = {}
    if question_type_value == "answer_follow_up":
        topic = str(context_refs.get("answer_topic", "") or "").strip()
        scope = str(context_refs.get("answer_scope", "") or getattr(question, "scope", "") or "").strip()
        sources = context_refs.get("answer_sources", []) or getattr(answer_result, "sources", [])
    else:
        topic = str(context_refs.get("topic", "") or "").strip() or question_type_value
        scope = str(getattr(question, "scope", "") or "").strip()
        sources = getattr(answer_result, "sources", [])
    session_context.set_recent_answer_context(
        topic=topic or None,
        scope=scope or None,
        sources=[str(source).strip() for source in list(sources or []) if str(source).strip()],
    )


def _metadata_with_debug(base: dict[str, Any] | None, debug_trace: dict[str, Any] | None) -> dict[str, Any] | None:
    metadata = dict(base or {})
    if debug_trace:
        metadata["debug"] = dict(debug_trace)
    return metadata or None
