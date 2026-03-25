"""Deterministic answer backend for v1 question-answer mode."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from qa.answer_backend import AnswerBackendKind
from qa.capability_catalog import MAJOR_LIMITS, SAFE_ACTIONS, SENSITIVE_ACTIONS, SUPPORTED_COMMANDS, SUPPORTED_QUESTION_FAMILIES
from qa.grounding_verifier import generic_source_support

if TYPE_CHECKING:
    from context.session_context import SessionContext
    from qa.answer_config import AnswerBackendConfig
    from qa.grounding import GroundingBundle
    from types.answer_result import AnswerResult
    from types.question_request import QuestionRequest


_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from answer_result import AnswerKind, AnswerProvenance, AnswerResult, AnswerSourceAttribution  # type: ignore  # noqa: E402
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
        debug_trace: dict[str, Any] | None = None,
    ) -> AnswerResult:
        question_type = getattr(question, "question_type", None)
        if question_type == QuestionType.BLOCKED_STATE:
            return self._blocked_state_answer(question, runtime_snapshot=runtime_snapshot, grounding_bundle=grounding_bundle)
        if question_type == QuestionType.RECENT_RUNTIME:
            return self._recent_runtime_answer(
                question,
                session_context=session_context,
                runtime_snapshot=runtime_snapshot,
                grounding_bundle=grounding_bundle,
            )
        if question_type == QuestionType.ANSWER_FOLLOW_UP:
            return self._answer_follow_up(
                question,
                runtime_snapshot=runtime_snapshot,
                grounding_bundle=grounding_bundle,
            )
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
        return self._result(
            answer_text=(
                f"I support command intents for {supported_intents}. "
                f"Safe command families include {safe_actions}. "
                f"Sensitive actions that stay behind confirmation are {sensitive_actions}. "
                f"Question mode currently covers {qa_scopes}. "
                "Short answer follow-ups such as explain-more and source questions stay grounded only to the most recent answer. "
                f"Key limits: {limits}."
            ),
            grounding_bundle=grounding_bundle,
            fallback_sources=[
                self._source("qa/capability_catalog.py"),
                self._source("docs/product_rules.md"),
                self._source("docs/question_answer_mode.md"),
                self._source("docs/command_model.md"),
            ],
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
        state = _text_or_none(snapshot.get("runtime_state")) or ""
        command_summary = _text_or_none(snapshot.get("command_summary"))
        blocked_reason = _text_or_none(snapshot.get("blocked_reason"))
        current_step = _text_or_none(snapshot.get("current_step"))
        lowered = str(getattr(question, "raw_input", "")).lower()

        if "folder" in lowered and session_context is not None:
            folder_context = session_context.get_recent_project_context()
            if folder_context:
                return self._result(
                    answer_text=f"The current recent workspace or folder context is {folder_context}.",
                    grounding_bundle=grounding_bundle,
                    fallback_sources=[
                        self._source("docs/session_context.md"),
                        self._source("context/session_context.py"),
                    ],
                    confidence=0.9,
                )

        if not state or state == "idle":
            if command_summary:
                return self._result(
                    answer_text=f"The last visible command context is {command_summary}, but nothing is actively executing right now.",
                    grounding_bundle=grounding_bundle,
                    fallback_sources=[self._source("docs/runtime_flow.md")],
                    confidence=0.88,
                )
            return self._result(
                answer_text="No active command is running right now.",
                grounding_bundle=grounding_bundle,
                fallback_sources=[self._source("docs/runtime_flow.md")],
                confidence=0.97,
            )

        parts: list[str] = [f"Current command runtime state: {state}."]
        if command_summary:
            parts.append(f"Command: {command_summary}.")
        if current_step:
            parts.append(f"Current step: {current_step}.")
        if blocked_reason:
            parts.append(f"Blocked on: {blocked_reason}.")
        return self._result(
            answer_text=" ".join(parts),
            grounding_bundle=grounding_bundle,
            fallback_sources=[self._source("docs/runtime_flow.md"), self._source("docs/session_context.md")],
            confidence=0.93,
        )

    def _blocked_state_answer(
        self,
        question: QuestionRequest,
        *,
        runtime_snapshot: dict[str, Any] | None,
        grounding_bundle: GroundingBundle | None,
    ) -> AnswerResult:
        snapshot = dict(runtime_snapshot or {})
        runtime_state = _text_or_none(snapshot.get("runtime_state"))
        blocked_kind = _text_or_none(snapshot.get("blocked_kind"))
        blocked_reason = _text_or_none(snapshot.get("blocked_reason"))
        clarification_question = _text_or_none(snapshot.get("clarification_question"))
        confirmation_message = _text_or_none(snapshot.get("confirmation_message"))

        if runtime_state not in {"awaiting_confirmation", "awaiting_clarification"}:
            raise self._answer_error(
                ErrorCode.INSUFFICIENT_CONTEXT,
                "No blocked command is active right now.",
                details={"reason": "no_active_command"},
            )

        lowered = str(getattr(question, "raw_input", "")).lower()
        if blocked_kind == "confirmation" or runtime_state == "awaiting_confirmation":
            request_text = confirmation_message or blocked_reason or "explicit confirmation before execution can continue"
            if "confirm" in lowered:
                answer_text = f"I'm waiting for explicit confirmation before continuing. I need you to confirm: {request_text}."
            else:
                answer_text = f"I'm blocked on confirmation right now. {request_text}."
            return self._result(
                answer_text=answer_text,
                grounding_bundle=grounding_bundle,
                fallback_sources=[
                    self._source("docs/question_answer_mode.md"),
                    self._source("docs/product_rules.md"),
                    self._source("docs/runtime_flow.md"),
                ],
                confidence=0.95,
            )

        clarification_text = clarification_question or blocked_reason or "one narrow clarification reply before execution can continue"
        return self._result(
            answer_text=f"I'm blocked on clarification right now. I need: {clarification_text}.",
            grounding_bundle=grounding_bundle,
            fallback_sources=[
                self._source("docs/question_answer_mode.md"),
                self._source("docs/clarification_rules.md"),
                self._source("docs/runtime_flow.md"),
            ],
            confidence=0.94,
        )

    def _recent_runtime_answer(
        self,
        question: QuestionRequest,
        *,
        session_context: SessionContext | None,
        runtime_snapshot: dict[str, Any] | None,
        grounding_bundle: GroundingBundle | None,
    ) -> AnswerResult:
        snapshot = dict(runtime_snapshot or {})
        lowered = str(getattr(question, "raw_input", "")).lower()
        command_summary = _text_or_none(snapshot.get("command_summary"))
        recent_project_context = session_context.get_recent_project_context() if session_context is not None else None
        recent_primary_action = session_context.get_recent_primary_action() if session_context is not None else None
        recent_primary_target = session_context.get_recent_primary_target() if session_context is not None else None

        if any(phrase in lowered for phrase in ("what command did you run last", "what was the last command", "what did you just do", "what did you do last")):
            if command_summary:
                return self._result(
                    answer_text=f"The last visible command was {command_summary}.",
                    grounding_bundle=grounding_bundle,
                    fallback_sources=[self._source("docs/session_context.md"), self._source("docs/runtime_flow.md")],
                    confidence=0.93,
                )
            if recent_primary_action and recent_primary_target is not None:
                return self._result(
                    answer_text=f"The most recent visible action was {recent_primary_action} on {_target_label(recent_primary_target)}.",
                    grounding_bundle=grounding_bundle,
                    fallback_sources=[self._source("docs/session_context.md"), self._source("context/session_context.py")],
                    confidence=0.9,
                )
            raise self._answer_error(
                ErrorCode.INSUFFICIENT_CONTEXT,
                "No recent command is available in session context.",
                details={"reason": "no_active_command"},
            )

        if recent_primary_target is not None and any(
            phrase in lowered
            for phrase in (
                "which target were you working with",
                "what target were you working with",
                "what app did you open last",
                "what file did you just open",
                "which file did you just open",
                "what was the last target",
                "what app was last",
                "what file was last",
            )
        ):
            return self._result(
                answer_text=f"The most recent visible target was {_target_label(recent_primary_target)}.",
                grounding_bundle=grounding_bundle,
                fallback_sources=[self._source("docs/session_context.md"), self._source("context/session_context.py")],
                confidence=0.91,
            )

        if any(
            phrase in lowered
            for phrase in (
                "which target were you working with",
                "what target were you working with",
                "what app did you open last",
                "what file did you just open",
                "which file did you just open",
                "what was the last target",
                "what app was last",
                "what file was last",
            )
        ):
            raise self._answer_error(
                ErrorCode.INSUFFICIENT_CONTEXT,
                "No recent target is available in session context.",
                details={"reason": "no_recent_target"},
            )

        if recent_project_context and any(phrase in lowered for phrase in ("what folder", "what project", "what workspace")):
            return self._result(
                answer_text=f"The most recent visible project or workspace context was {recent_project_context}.",
                grounding_bundle=grounding_bundle,
                fallback_sources=[self._source("docs/session_context.md"), self._source("context/session_context.py")],
                confidence=0.9,
            )

        raise self._answer_error(
            ErrorCode.INSUFFICIENT_CONTEXT,
            "No recent runtime context is available for that question.",
            details={"reason": "no_active_command"},
        )

    def _answer_follow_up(
        self,
        question: QuestionRequest,
        *,
        runtime_snapshot: dict[str, Any] | None,
        grounding_bundle: GroundingBundle | None,
    ) -> AnswerResult:
        context_refs = getattr(question, "context_refs", {}) or {}
        if not isinstance(context_refs, dict):
            raise self._answer_error(
                ErrorCode.INSUFFICIENT_CONTEXT,
                "No recent answer context is available for that follow-up.",
                details={"reason": "no_recent_answer"},
            )

        follow_up_kind = str(context_refs.get("follow_up_kind", "") or "").strip()
        answer_topic = str(context_refs.get("answer_topic", "") or "").strip()
        answer_scope = str(context_refs.get("answer_scope", "") or "").strip()
        fallback_sources = [
            str(source).strip()
            for source in list(context_refs.get("answer_sources", []) or [])
            if str(source).strip()
        ]
        if not answer_topic and not answer_scope:
            raise self._answer_error(
                ErrorCode.INSUFFICIENT_CONTEXT,
                "No recent answer context is available for that follow-up.",
                details={"reason": "no_recent_answer"},
            )

        if follow_up_kind in {"which_source", "where_written"}:
            source_list = self._formatted_source_list(self._sources(grounding_bundle, fallback_sources))
            prefix = "That is written in" if self._docs_only_sources(self._sources(grounding_bundle, fallback_sources)) else "The previous answer was grounded in"
            return self._result(
                answer_text=f"{prefix} {source_list}.",
                grounding_bundle=grounding_bundle,
                fallback_sources=fallback_sources,
                confidence=0.93,
            )

        if follow_up_kind == "why":
            return self._result(
                answer_text=self._why_follow_up_text(answer_topic, answer_scope, runtime_snapshot=runtime_snapshot),
                grounding_bundle=grounding_bundle,
                fallback_sources=fallback_sources,
                confidence=0.91,
            )

        if follow_up_kind == "explain_more":
            return self._result(
                answer_text=self._explain_more_follow_up_text(answer_topic, answer_scope, runtime_snapshot=runtime_snapshot),
                grounding_bundle=grounding_bundle,
                fallback_sources=fallback_sources,
                confidence=0.92,
            )

        raise self._answer_error(
            ErrorCode.UNSUPPORTED_QUESTION,
            "Answer follow-up is outside the deterministic v1.5 rule set.",
            details={"reason": "topic_not_supported", "follow_up_kind": follow_up_kind},
        )

    def _docs_rule_answer(self, question: QuestionRequest, *, grounding_bundle: GroundingBundle | None) -> AnswerResult:
        lowered = str(getattr(question, "raw_input", "")).lower()
        topic = self._topic(question)
        if "clarification" in lowered:
            return self._result(
                answer_text=(
                    "Clarification is a hard boundary. JARVIS asks one minimal question only when ambiguity, missing data, low confidence, "
                    "or routing ambiguity blocks safe progress."
                ),
                grounding_bundle=grounding_bundle,
                fallback_sources=[self._source("docs/clarification_rules.md"), self._source("docs/runtime_flow.md")],
                confidence=0.95,
            )
        if "confirmation" in lowered:
            return self._result(
                answer_text=(
                    "Confirmation is required before sensitive command actions. JARVIS pauses at the command or step boundary and resumes only "
                    "after explicit approval."
                ),
                grounding_bundle=grounding_bundle,
                fallback_sources=[self._source("docs/product_rules.md"), self._source("docs/runtime_flow.md")],
                confidence=0.94,
            )
        if "session context" in lowered:
            return self._result(
                answer_text=(
                    "Session context is short-lived state for the active supervised session. It keeps recent targets, execution state, and other "
                    "narrow context needed for follow-ups and grounded status answers."
                ),
                grounding_bundle=grounding_bundle,
                fallback_sources=[self._source("docs/session_context.md")],
                confidence=0.95,
            )
        if "runtime" in lowered or "state" in lowered or topic == "runtime":
            return self._result(
                answer_text=(
                    "Command runtime flows through parsing, validating, planning, executing, and blocked terminal states. Question mode stays outside "
                    "the command execution state machine and returns a read-only answer."
                ),
                grounding_bundle=grounding_bundle,
                fallback_sources=[self._source("docs/runtime_flow.md"), self._source("docs/runtime_components.md")],
                confidence=0.92,
            )
        raise self._answer_error(
            ErrorCode.UNSUPPORTED_QUESTION,
            "Docs question is outside the deterministic v1 rule set.",
            details={"reason": "topic_not_supported"},
        )

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
                "Question answering lives under qa/, with answer_engine.py coordinating the backends and source_selector.py choosing grounded sources.",
                [
                    self._source("qa/answer_engine.py"),
                    self._source("qa/source_selector.py"),
                    self._source("qa/source_registry.py"),
                    self._source("docs/repo_structure.md"),
                ],
            ),
        )
        for keywords, answer_text, sources in mappings:
            if any(keyword in lowered for keyword in keywords):
                return self._result(
                    answer_text=answer_text,
                    grounding_bundle=grounding_bundle,
                    fallback_sources=sources,
                    confidence=0.92,
                )
        raise self._answer_error(
            ErrorCode.UNSUPPORTED_QUESTION,
            "Repo-structure question is outside the deterministic v1 rule set.",
            details={"reason": "topic_not_supported"},
        )

    def _safety_answer(
        self,
        question: QuestionRequest,
        *,
        runtime_snapshot: dict[str, Any] | None,
        grounding_bundle: GroundingBundle | None,
    ) -> AnswerResult:
        lowered = str(getattr(question, "raw_input", "")).lower()
        blocked_reason = _text_or_none((runtime_snapshot or {}).get("blocked_reason"))
        if "confirmation" in lowered:
            suffix = f" Current blocked reason: {blocked_reason}." if blocked_reason else ""
            return self._result(
                answer_text=(
                    "Confirmation exists to protect sensitive actions such as closing active work. JARVIS must pause and wait for explicit approval "
                    "before continuing."
                    f"{suffix}"
                ),
                grounding_bundle=grounding_bundle,
                fallback_sources=[self._source("docs/product_rules.md"), self._source("docs/runtime_flow.md")],
                confidence=0.94,
            )
        if "execute" in lowered or "blocked" in lowered or blocked_reason:
            reason_text = blocked_reason or "the current state requires clarification, confirmation, or a valid target before execution can continue"
            return self._result(
                answer_text=f"Execution did not continue because {reason_text}. JARVIS stops on ambiguity, missing data, and confirmation boundaries.",
                grounding_bundle=grounding_bundle,
                fallback_sources=[
                    self._source("docs/product_rules.md"),
                    self._source("docs/clarification_rules.md"),
                    self._source("docs/runtime_flow.md"),
                ],
                confidence=0.91,
            )
        raise self._answer_error(
            ErrorCode.UNSUPPORTED_QUESTION,
            "Safety question is outside the deterministic v1 rule set.",
            details={"reason": "topic_not_supported"},
        )

    def _answer_error(self, code: ErrorCode, message: str, details: dict[str, Any] | None = None) -> JarvisError:
        return JarvisError(
            category=ErrorCategory.ANSWER_ERROR,
            code=code,
            message=message,
            details=details,
            blocking=False,
            terminal=True,
        )

    def _source(self, relative_path: str) -> str:
        return str(Path(__file__).resolve().parents[1] / relative_path)

    def _sources(self, grounding_bundle: GroundingBundle | None, fallback_sources: list[str]) -> list[str]:
        if grounding_bundle is not None and grounding_bundle.source_paths:
            return list(grounding_bundle.source_paths)
        return fallback_sources

    def _source_attributions(
        self,
        grounding_bundle: GroundingBundle | None,
        fallback_sources: list[str],
    ) -> list[AnswerSourceAttribution]:
        if grounding_bundle is not None and grounding_bundle.source_paths:
            return grounding_bundle.build_source_attributions()
        return [
            AnswerSourceAttribution(source=source, support=generic_source_support(source))
            for source in fallback_sources
        ]

    def _result(
        self,
        *,
        answer_text: str,
        grounding_bundle: GroundingBundle | None,
        fallback_sources: list[str],
        confidence: float,
        warning: str | None = None,
    ) -> AnswerResult:
        return AnswerResult(
            answer_text=answer_text,
            sources=self._sources(grounding_bundle, fallback_sources),
            source_attributions=self._source_attributions(grounding_bundle, fallback_sources),
            confidence=confidence,
            warning=warning,
            answer_kind=AnswerKind.GROUNDED_LOCAL,
            provenance=AnswerProvenance.LOCAL_SOURCES,
        )

    def _topic(self, question: QuestionRequest) -> str | None:
        context_refs = getattr(question, "context_refs", {}) or {}
        if not isinstance(context_refs, dict):
            return None
        topic = str(context_refs.get("topic", "") or "").strip()
        return topic or None

    def _why_follow_up_text(
        self,
        answer_topic: str,
        answer_scope: str,
        *,
        runtime_snapshot: dict[str, Any] | None,
    ) -> str:
        blocked_reason = _text_or_none((runtime_snapshot or {}).get("blocked_reason"))
        if answer_scope == "blocked_state" or answer_topic == QuestionType.BLOCKED_STATE.value:
            suffix = f" Current blocked reason: {blocked_reason}." if blocked_reason else ""
            return (
                "Because blocked commands stay paused until the exact clarification or confirmation boundary is resolved. "
                "Question mode can explain the boundary, but it cannot approve or resume execution."
                f"{suffix}"
            )
        if answer_scope == "recent_runtime" or answer_topic == QuestionType.RECENT_RUNTIME.value or answer_scope == "runtime":
            return (
                "Because runtime answers are limited to visible runtime state and short-lived session context from the current supervised session. "
                "JARVIS must not invent memory or hidden background activity."
            )
        if answer_scope == "capabilities" or answer_topic == QuestionType.CAPABILITIES.value:
            return (
                "Because JARVIS is intentionally bounded to supervised local actions and grounded read-only answers. "
                "Unsupported or unsafe behavior stays explicit instead of being guessed."
            )
        if answer_scope == "repo_structure":
            return (
                "Because the codebase keeps routing, runtime, visibility, and QA responsibilities in separate modules with one clear home. "
                "Repo answers point to those ownership boundaries instead of doing arbitrary codebase QA."
            )
        if answer_scope == "safety" or answer_topic == QuestionType.SAFETY_EXPLANATIONS.value:
            return (
                "Because confirmation, clarification, and explicit failures protect against hidden or destructive execution. "
                "Question mode can explain those boundaries, but it cannot weaken them."
            )
        if answer_topic == "clarification":
            return (
                "Because ambiguity, missing data, low confidence, and mixed command-question input must stop execution until one narrow point is resolved. "
                "Clarification exists to keep supervised behavior deterministic."
            )
        if answer_topic == "confirmation":
            return (
                "Because sensitive actions require an explicit approval boundary before execution continues. "
                "That keeps question answers read-only and prevents silent destructive actions."
            )
        if answer_topic == "session_context":
            return (
                "Because session context is intentionally short-lived. It only supports immediate follow-ups and grounded status answers inside the current supervised session."
            )
        return (
            "Because question mode answers only from grounded local docs, runtime visibility, and short-lived session facts. "
            "If that support is missing, the system must fail honestly instead of guessing."
        )

    def _explain_more_follow_up_text(
        self,
        answer_topic: str,
        answer_scope: str,
        *,
        runtime_snapshot: dict[str, Any] | None,
    ) -> str:
        blocked_reason = _text_or_none((runtime_snapshot or {}).get("blocked_reason"))
        if answer_scope == "blocked_state" or answer_topic == QuestionType.BLOCKED_STATE.value:
            suffix = f" The visible blocked reason is {blocked_reason}." if blocked_reason else ""
            return (
                "In more detail: blocked-state questions read the current clarification or confirmation boundary from visible runtime state. "
                "They can tell you what reply is needed, but only an explicit command-path reply can unblock the command."
                f"{suffix}"
            )
        if answer_scope == "recent_runtime" or answer_topic == QuestionType.RECENT_RUNTIME.value:
            return (
                "In more detail: recent-runtime answers can read only short-lived session facts such as the last visible command summary, "
                "recent target, workspace context, and recent search results. They do not introduce long-term memory or repo search."
            )
        if answer_scope == "runtime" or answer_topic == QuestionType.RUNTIME_STATUS.value:
            return (
                "In more detail: runtime-status answers describe only visible supervised state such as current runtime state, current step, blocked reason, "
                "and recent folder context when it is explicitly available."
            )
        if answer_scope == "capabilities" or answer_topic == QuestionType.CAPABILITIES.value:
            supported_intents = ", ".join(entry["intent"] for entry in SUPPORTED_COMMANDS)
            return (
                "In more detail: command mode supports "
                f"{supported_intents}. "
                "Question mode stays read-only and grounded to capabilities, runtime state, docs rules, repo structure, and safety boundaries."
            )
        if answer_scope == "repo_structure":
            return (
                "In more detail: repo-structure answers point to the primary file or module that owns a responsibility so the dual-mode architecture stays clear. "
                "Interaction routing lives above command runtime, and QA stays behind the answer-engine seam."
            )
        if answer_scope == "safety" or answer_topic == QuestionType.SAFETY_EXPLANATIONS.value:
            return (
                "In more detail: safety explanations are grounded in product rules, clarification rules, and visible runtime state. "
                "They explain why execution paused or failed without changing the blocked boundary."
            )
        if answer_topic == "clarification":
            return (
                "In more detail: clarification happens before planning or execution when the input is ambiguous, missing required data, below confidence, "
                "or mixes command and question semantics. JARVIS asks one minimal question, waits, and then re-enters the normal supervised flow."
            )
        if answer_topic == "confirmation":
            return (
                "In more detail: confirmation pauses on a sensitive command or step boundary. "
                "A question can explain the boundary, but approval still requires an explicit yes/no style reply on the command path."
            )
        if answer_topic == "session_context":
            return (
                "In more detail: session context keeps only active-session state such as recent targets, workspace context, search results, and recent answer context. "
                "It exists for narrow follow-ups, not for cross-session memory."
            )
        return (
            "In more detail: the previous answer stayed inside grounded local scope and used only the smallest source bundle needed to answer safely. "
            "Question mode remains read-only and fails honestly when the needed support is missing."
        )

    def _docs_only_sources(self, sources: list[str]) -> bool:
        return bool(sources) and all("/docs/" in source.replace("\\", "/") for source in sources)

    def _formatted_source_list(self, sources: list[str]) -> str:
        labels = [self._display_source(source) for source in sources]
        if not labels:
            return "the previous grounded sources"
        if len(labels) == 1:
            return labels[0]
        if len(labels) == 2:
            return f"{labels[0]} and {labels[1]}"
        return f"{', '.join(labels[:-1])}, and {labels[-1]}"

    def _display_source(self, source: str) -> str:
        source_path = Path(source)
        repo_root = Path(__file__).resolve().parents[1]
        try:
            return str(source_path.relative_to(repo_root))
        except ValueError:
            return str(source_path)


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == "None":
        return None
    return text


def _target_label(target: Any) -> str:
    name = str(getattr(target, "name", "") or "").strip()
    path = str(getattr(target, "path", "") or "").strip()
    if name and path:
        return f"{name} ({path})"
    return name or path or "the recent target"
