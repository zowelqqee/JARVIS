"""Deterministic answer backend for v1 question-answer mode."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from qa.answer_backend import AnswerBackendKind
from qa.capability_catalog import MAJOR_LIMITS, SAFE_ACTIONS, SENSITIVE_ACTIONS, SUPPORTED_COMMANDS, SUPPORTED_QUESTION_FAMILIES

if TYPE_CHECKING:
    from context.session_context import SessionContext
    from qa.answer_config import AnswerBackendConfig
    from qa.grounding import GroundingBundle
    from types.answer_result import AnswerResult
    from types.question_request import QuestionRequest


_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from answer_result import AnswerResult  # type: ignore  # noqa: E402
from jarvis_error import ErrorCategory, ErrorCode, JarvisError  # type: ignore  # noqa: E402
from question_request import QuestionType  # type: ignore  # noqa: E402


class DeterministicAnswerBackend:
    """Rules/templates backend for grounded v1 answers."""

    backend_kind = AnswerBackendKind.DETERMINISTIC

    def answer(
        self,
        question: QuestionRequest,
        *,
        session_context: SessionContext | None = None,
        runtime_snapshot: dict[str, Any] | None = None,
        grounding_bundle: GroundingBundle | None = None,
        config: AnswerBackendConfig | None = None,
    ) -> AnswerResult:
        question_type = getattr(question, "question_type", None)
        if question_type == QuestionType.CAPABILITIES:
            return self._capability_answer(grounding_bundle)
        if question_type == QuestionType.RUNTIME_STATUS:
            return self._runtime_status_answer(
                question,
                session_context=session_context,
                runtime_snapshot=runtime_snapshot,
                grounding_bundle=grounding_bundle,
            )
        if question_type == QuestionType.DOCS_RULES:
            return self._docs_rule_answer(question, grounding_bundle=grounding_bundle)
        if question_type == QuestionType.REPO_STRUCTURE:
            return self._repo_structure_answer(question, grounding_bundle=grounding_bundle)
        if question_type == QuestionType.SAFETY_EXPLANATIONS:
            return self._safety_answer(question, runtime_snapshot=runtime_snapshot, grounding_bundle=grounding_bundle)
        raise self._answer_error(ErrorCode.UNSUPPORTED_QUESTION, "Question type is not supported by the deterministic backend.")

    def _capability_answer(self, grounding_bundle: GroundingBundle | None) -> AnswerResult:
        supported_intents = ", ".join(entry["intent"] for entry in SUPPORTED_COMMANDS)
        qa_scopes = ", ".join(SUPPORTED_QUESTION_FAMILIES)
        safe_actions = ", ".join(SAFE_ACTIONS)
        sensitive_actions = ", ".join(SENSITIVE_ACTIONS)
        limits = ", ".join(MAJOR_LIMITS)
        return AnswerResult(
            answer_text=(
                f"I support command intents for {supported_intents}. "
                f"Safe command families include {safe_actions}. "
                f"Sensitive actions that stay behind confirmation are {sensitive_actions}. "
                f"Question mode currently covers {qa_scopes}. "
                f"Key limits: {limits}."
            ),
            sources=self._sources(
                grounding_bundle,
                [
                    self._source("qa/capability_catalog.py"),
                    self._source("docs/product_rules.md"),
                    self._source("docs/question_answer_mode.md"),
                    self._source("docs/command_model.md"),
                ],
            ),
            confidence=0.96,
        )

    def _runtime_status_answer(
        self,
        question: QuestionRequest,
        *,
        session_context: SessionContext | None,
        runtime_snapshot: dict[str, Any] | None,
        grounding_bundle: GroundingBundle | None,
    ) -> AnswerResult:
        snapshot = dict(runtime_snapshot or {})
        state = str(snapshot.get("runtime_state", "")).strip()
        command_summary = str(snapshot.get("command_summary", "")).strip() or None
        blocked_reason = str(snapshot.get("blocked_reason", "")).strip() or None
        current_step = str(snapshot.get("current_step", "")).strip() or None
        lowered = str(getattr(question, "raw_input", "")).lower()

        if "folder" in lowered and session_context is not None:
            folder_context = session_context.get_recent_project_context()
            if folder_context:
                return AnswerResult(
                    answer_text=f"The current recent workspace or folder context is {folder_context}.",
                    sources=self._sources(
                        grounding_bundle,
                        [
                            self._source("docs/session_context.md"),
                            self._source("context/session_context.py"),
                        ],
                    ),
                    confidence=0.9,
                )

        if not state or state == "idle":
            if command_summary:
                return AnswerResult(
                    answer_text=f"The last visible command context is {command_summary}, but nothing is actively executing right now.",
                    sources=self._sources(grounding_bundle, [self._source("docs/runtime_flow.md")]),
                    confidence=0.88,
                )
            return AnswerResult(
                answer_text="No active command is running right now.",
                sources=self._sources(grounding_bundle, [self._source("docs/runtime_flow.md")]),
                confidence=0.97,
            )

        parts: list[str] = [f"Current command runtime state: {state}."]
        if command_summary:
            parts.append(f"Command: {command_summary}.")
        if current_step:
            parts.append(f"Current step: {current_step}.")
        if blocked_reason:
            parts.append(f"Blocked on: {blocked_reason}.")
        return AnswerResult(
            answer_text=" ".join(parts),
            sources=self._sources(
                grounding_bundle,
                [self._source("docs/runtime_flow.md"), self._source("docs/session_context.md")],
            ),
            confidence=0.93,
        )

    def _docs_rule_answer(self, question: QuestionRequest, *, grounding_bundle: GroundingBundle | None) -> AnswerResult:
        lowered = str(getattr(question, "raw_input", "")).lower()
        if "clarification" in lowered:
            return AnswerResult(
                answer_text=(
                    "Clarification is a hard boundary. JARVIS asks one minimal question only when ambiguity, missing data, low confidence, "
                    "or routing ambiguity blocks safe progress."
                ),
                sources=self._sources(
                    grounding_bundle,
                    [self._source("docs/clarification_rules.md"), self._source("docs/runtime_flow.md")],
                ),
                confidence=0.95,
            )
        if "confirmation" in lowered:
            return AnswerResult(
                answer_text=(
                    "Confirmation is required before sensitive command actions. JARVIS pauses at the command or step boundary and resumes only "
                    "after explicit approval."
                ),
                sources=self._sources(
                    grounding_bundle,
                    [self._source("docs/product_rules.md"), self._source("docs/runtime_flow.md")],
                ),
                confidence=0.94,
            )
        if "session context" in lowered:
            return AnswerResult(
                answer_text=(
                    "Session context is short-lived state for the active supervised session. It keeps recent targets, execution state, and other "
                    "narrow context needed for follow-ups and grounded status answers."
                ),
                sources=self._sources(grounding_bundle, [self._source("docs/session_context.md")]),
                confidence=0.95,
            )
        if "runtime" in lowered or "state" in lowered:
            return AnswerResult(
                answer_text=(
                    "Command runtime flows through parsing, validating, planning, executing, and blocked terminal states. Question mode stays outside "
                    "the command execution state machine and returns a read-only answer."
                ),
                sources=self._sources(
                    grounding_bundle,
                    [self._source("docs/runtime_flow.md"), self._source("docs/runtime_components.md")],
                ),
                confidence=0.92,
            )
        raise self._answer_error(ErrorCode.UNSUPPORTED_QUESTION, "Docs question is outside the deterministic v1 rule set.")

    def _repo_structure_answer(self, question: QuestionRequest, *, grounding_bundle: GroundingBundle | None) -> AnswerResult:
        lowered = str(getattr(question, "raw_input", "")).lower()
        mappings: tuple[tuple[tuple[str, ...], str, list[str]], ...] = (
            (
                ("planner", "execution plan"),
                "Execution planning lives in planner/execution_planner.py.",
                [self._source("planner/execution_planner.py"), self._source("docs/repo_structure.md")],
            ),
            (
                ("parser", "parse command"),
                "Command parsing lives in parser/command_parser.py.",
                [self._source("parser/command_parser.py"), self._source("docs/repo_structure.md")],
            ),
            (
                ("validator", "validate command"),
                "Command validation lives in validator/command_validator.py.",
                [self._source("validator/command_validator.py"), self._source("docs/repo_structure.md")],
            ),
            (
                ("runtime", "state machine", "runtime state"),
                "Command runtime orchestration lives in runtime/runtime_manager.py and runtime/state_machine.py.",
                [self._source("runtime/runtime_manager.py"), self._source("runtime/state_machine.py"), self._source("docs/repo_structure.md")],
            ),
            (
                ("visibility", "ui"),
                "Visibility mapping lives in ui/visibility_mapper.py.",
                [self._source("ui/visibility_mapper.py"), self._source("docs/repo_structure.md")],
            ),
            (
                ("interaction router", "route interaction", "interaction"),
                "Top-level dual-mode routing lives in interaction/interaction_router.py and interaction/interaction_manager.py.",
                [self._source("interaction/interaction_router.py"), self._source("interaction/interaction_manager.py"), self._source("docs/repo_structure.md")],
            ),
            (
                ("answer engine", "qa", "question-answer"),
                "Question answering lives under qa/, with answer_engine.py coordinating the backends.",
                [self._source("qa/answer_engine.py"), self._source("qa/deterministic_backend.py"), self._source("docs/repo_structure.md")],
            ),
        )
        for keywords, answer_text, sources in mappings:
            if any(keyword in lowered for keyword in keywords):
                return AnswerResult(answer_text=answer_text, sources=self._sources(grounding_bundle, sources), confidence=0.92)
        raise self._answer_error(ErrorCode.UNSUPPORTED_QUESTION, "Repo-structure question is outside the deterministic v1 rule set.")

    def _safety_answer(
        self,
        question: QuestionRequest,
        *,
        runtime_snapshot: dict[str, Any] | None,
        grounding_bundle: GroundingBundle | None,
    ) -> AnswerResult:
        lowered = str(getattr(question, "raw_input", "")).lower()
        blocked_reason = str((runtime_snapshot or {}).get("blocked_reason", "")).strip() or None
        if "confirmation" in lowered:
            suffix = f" Current blocked reason: {blocked_reason}." if blocked_reason else ""
            return AnswerResult(
                answer_text=(
                    "Confirmation exists to protect sensitive actions such as closing active work. JARVIS must pause and wait for explicit approval "
                    "before continuing."
                    f"{suffix}"
                ),
                sources=self._sources(
                    grounding_bundle,
                    [self._source("docs/product_rules.md"), self._source("docs/runtime_flow.md")],
                ),
                confidence=0.94,
            )
        if "execute" in lowered or "blocked" in lowered or blocked_reason:
            reason_text = blocked_reason or "the current state requires clarification, confirmation, or a valid target before execution can continue"
            return AnswerResult(
                answer_text=f"Execution did not continue because {reason_text}. JARVIS stops on ambiguity, missing data, and confirmation boundaries.",
                sources=self._sources(
                    grounding_bundle,
                    [self._source("docs/product_rules.md"), self._source("docs/clarification_rules.md"), self._source("docs/runtime_flow.md")],
                ),
                confidence=0.91,
            )
        raise self._answer_error(ErrorCode.UNSUPPORTED_QUESTION, "Safety question is outside the deterministic v1 rule set.")

    def _answer_error(self, code: ErrorCode, message: str) -> JarvisError:
        return JarvisError(
            category=ErrorCategory.ANSWER_ERROR,
            code=code,
            message=message,
            details=None,
            blocking=False,
            terminal=True,
        )

    def _source(self, relative_path: str) -> str:
        return str(Path(__file__).resolve().parents[1] / relative_path)

    def _sources(self, grounding_bundle: GroundingBundle | None, fallback_sources: list[str]) -> list[str]:
        if grounding_bundle is not None and grounding_bundle.source_paths:
            return list(grounding_bundle.source_paths)
        return fallback_sources
