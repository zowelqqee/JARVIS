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
from qa.answer_engine import answer_question
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
        decision = route_interaction(
            raw_input,
            session_context=session_context,
            runtime_state=self.runtime_manager.current_state,
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
                metadata={"reason": decision.reason},
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
                metadata={"reason": decision.reason},
            )

        try:
            answer_backend_config = self._effective_answer_backend_config()
            answer_result = answer_question(
                decision.normalized_input,
                session_context=session_context,
                runtime_snapshot=self._runtime_snapshot(),
                backend_config=answer_backend_config,
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
            )

        return InteractionResult(
            interaction_mode=InteractionKind.QUESTION,
            normalized_input=decision.normalized_input,
            answer_result=answer_result,
            visibility=map_interaction_visibility(
                interaction_mode=InteractionKind.QUESTION,
                answer_result=answer_result,
            ),
            metadata={"answer_backend": answer_backend_config.backend_kind.value},
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
