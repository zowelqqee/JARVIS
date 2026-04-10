"""Deterministic answer backend for v1 question-answer mode."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from qa.answer_backend import AnswerBackendKind
from qa.answer_language import question_request_language
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
            return self._capability_answer(question, grounding_bundle)
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

    def _capability_answer(self, question: QuestionRequest, grounding_bundle: GroundingBundle | None) -> AnswerResult:
        supported_intents = ", ".join(entry["intent"] for entry in SUPPORTED_COMMANDS)
        qa_scopes = ", ".join(SUPPORTED_QUESTION_FAMILIES)
        safe_actions = ", ".join(SAFE_ACTIONS)
        sensitive_actions = ", ".join(SENSITIVE_ACTIONS)
        limits = ", ".join(MAJOR_LIMITS)
        if _prefers_russian_answer(question):
            answer_text = (
                f"Я поддерживаю командные интенты {supported_intents}. "
                f"Безопасные семейства команд: {safe_actions}. "
                f"Чувствительные действия, которые остаются за подтверждением: {sensitive_actions}. "
                f"Режим вопросов сейчас покрывает {qa_scopes}. "
                "Короткие уточнения вроде explain more и вопросов об источниках остаются привязаны только к последнему ответу. "
                f"Основные ограничения: {limits}."
            )
        else:
            answer_text = (
                f"I support command intents for {supported_intents}. "
                f"Safe command families include {safe_actions}. "
                f"Sensitive actions that stay behind confirmation are {sensitive_actions}. "
                f"Question mode currently covers {qa_scopes}. "
                "Short answer follow-ups such as explain-more and source questions stay grounded only to the most recent answer. "
                f"Key limits: {limits}."
            )
        return self._result(
            answer_text=answer_text,
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
        prefers_russian = _prefers_russian_answer(question)

        if "folder" in lowered and session_context is not None:
            folder_context = session_context.get_recent_project_context()
            if folder_context:
                return self._result(
                    answer_text=(
                        f"Текущий недавний контекст рабочего пространства или папки: {folder_context}."
                        if prefers_russian
                        else f"The current recent workspace or folder context is {folder_context}."
                    ),
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
                    answer_text=(
                        f"Последний видимый контекст команды: {command_summary}, но сейчас ничего не выполняется."
                        if prefers_russian
                        else f"The last visible command context is {command_summary}, but nothing is actively executing right now."
                    ),
                    grounding_bundle=grounding_bundle,
                    fallback_sources=[self._source("docs/runtime_flow.md")],
                    confidence=0.88,
                )
            return self._result(
                answer_text=(
                    "Сейчас нет активной команды."
                    if prefers_russian
                    else "No active command is running right now."
                ),
                grounding_bundle=grounding_bundle,
                fallback_sources=[self._source("docs/runtime_flow.md")],
                confidence=0.97,
            )

        parts: list[str] = [
            f"Текущее состояние выполнения команды: {state}."
            if prefers_russian
            else f"Current command runtime state: {state}."
        ]
        if command_summary:
            parts.append(f"Команда: {command_summary}." if prefers_russian else f"Command: {command_summary}.")
        if current_step:
            parts.append(f"Текущий шаг: {current_step}." if prefers_russian else f"Current step: {current_step}.")
        if blocked_reason:
            parts.append(f"Ожидание: {blocked_reason}." if prefers_russian else f"Blocked on: {blocked_reason}.")
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
        prefers_russian = _prefers_russian_answer(question)

        if runtime_state not in {"awaiting_confirmation", "awaiting_clarification"}:
            raise self._answer_error(
                ErrorCode.INSUFFICIENT_CONTEXT,
                _localized_text(
                    prefers_russian,
                    en="No blocked command is active right now.",
                    ru="Сейчас нет активной заблокированной команды.",
                ),
                details={"reason": "no_active_command"},
            )

        lowered = str(getattr(question, "raw_input", "")).lower()
        if blocked_kind == "confirmation" or runtime_state == "awaiting_confirmation":
            request_text = confirmation_message or blocked_reason or (
                "явное подтверждение перед продолжением выполнения"
                if prefers_russian
                else "explicit confirmation before execution can continue"
            )
            if "confirm" in lowered:
                answer_text = (
                    f"Я жду явного подтверждения перед продолжением. Мне нужно, чтобы ты подтвердил: {request_text}."
                    if prefers_russian
                    else f"I'm waiting for explicit confirmation before continuing. I need you to confirm: {request_text}."
                )
            else:
                answer_text = (
                    f"Сейчас я жду подтверждения. {request_text}."
                    if prefers_russian
                    else f"I'm blocked on confirmation right now. {request_text}."
                )
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

        clarification_text = clarification_question or blocked_reason or (
            "одно короткое уточнение перед продолжением выполнения"
            if prefers_russian
            else "one narrow clarification reply before execution can continue"
        )
        return self._result(
            answer_text=(
                f"Сейчас я жду уточнения. Мне нужно: {clarification_text}."
                if prefers_russian
                else f"I'm blocked on clarification right now. I need: {clarification_text}."
            ),
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
        prefers_russian = _prefers_russian_answer(question)

        if any(phrase in lowered for phrase in ("what command did you run last", "what was the last command", "what did you just do", "what did you do last")):
            if command_summary:
                return self._result(
                    answer_text=(
                        f"Последняя видимая команда: {command_summary}."
                        if prefers_russian
                        else f"The last visible command was {command_summary}."
                    ),
                    grounding_bundle=grounding_bundle,
                    fallback_sources=[self._source("docs/session_context.md"), self._source("docs/runtime_flow.md")],
                    confidence=0.93,
                )
            if recent_primary_action and recent_primary_target is not None:
                return self._result(
                    answer_text=(
                        f"Последнее видимое действие: {recent_primary_action} для {_target_label(recent_primary_target)}."
                        if prefers_russian
                        else f"The most recent visible action was {recent_primary_action} on {_target_label(recent_primary_target)}."
                    ),
                    grounding_bundle=grounding_bundle,
                    fallback_sources=[self._source("docs/session_context.md"), self._source("context/session_context.py")],
                    confidence=0.9,
                )
            raise self._answer_error(
                ErrorCode.INSUFFICIENT_CONTEXT,
                _localized_text(
                    prefers_russian,
                    en="No recent command is available in session context.",
                    ru="В контексте сессии нет недавней команды.",
                ),
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
                answer_text=(
                    f"Последняя видимая цель: {_target_label(recent_primary_target)}."
                    if prefers_russian
                    else f"The most recent visible target was {_target_label(recent_primary_target)}."
                ),
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
                _localized_text(
                    prefers_russian,
                    en="No recent target is available in session context.",
                    ru="В контексте сессии нет недавней цели.",
                ),
                details={"reason": "no_recent_target"},
            )

        if recent_project_context and any(phrase in lowered for phrase in ("what folder", "what project", "what workspace")):
            return self._result(
                answer_text=(
                    f"Последний видимый контекст проекта или рабочего пространства: {recent_project_context}."
                    if prefers_russian
                    else f"The most recent visible project or workspace context was {recent_project_context}."
                ),
                grounding_bundle=grounding_bundle,
                fallback_sources=[self._source("docs/session_context.md"), self._source("context/session_context.py")],
                confidence=0.9,
            )

        raise self._answer_error(
            ErrorCode.INSUFFICIENT_CONTEXT,
            _localized_text(
                prefers_russian,
                en="No recent runtime context is available for that question.",
                ru="Для этого вопроса нет недавнего runtime-контекста.",
            ),
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
        prefers_russian = _prefers_russian_answer(question)
        if not isinstance(context_refs, dict):
            raise self._answer_error(
                ErrorCode.INSUFFICIENT_CONTEXT,
                _localized_text(
                    prefers_russian,
                    en="No recent answer context is available for that follow-up.",
                    ru="Для этого уточнения нет недавнего контекста ответа.",
                ),
                details={"reason": "no_recent_answer"},
            )

        follow_up_kind = str(context_refs.get("follow_up_kind", "") or "").strip()
        answer_topic = str(context_refs.get("answer_topic", "") or "").strip()
        answer_scope = str(context_refs.get("answer_scope", "") or "").strip()
        answer_text = str(context_refs.get("answer_text", "") or "").strip()
        answer_warning = str(context_refs.get("answer_warning", "") or "").strip() or None
        answer_kind = str(context_refs.get("answer_kind", "") or "").strip() or None
        answer_provenance = str(context_refs.get("answer_provenance", "") or "").strip() or None
        answer_confidence = context_refs.get("answer_confidence")
        fallback_sources = [
            str(source).strip()
            for source in list(context_refs.get("answer_sources", []) or [])
            if str(source).strip()
        ]
        if not answer_topic and not answer_scope:
            raise self._answer_error(
                ErrorCode.INSUFFICIENT_CONTEXT,
                _localized_text(
                    prefers_russian,
                    en="No recent answer context is available for that follow-up.",
                    ru="Для этого уточнения нет недавнего контекста ответа.",
                ),
                details={"reason": "no_recent_answer"},
            )

        if follow_up_kind == "repeat":
            if not answer_text:
                raise self._answer_error(
                    ErrorCode.INSUFFICIENT_CONTEXT,
                    _localized_text(
                        prefers_russian,
                        en="No recent answer text is available for that repeat request.",
                        ru="Для этой просьбы повторить нет текста недавнего ответа.",
                    ),
                    details={"reason": "no_recent_answer_text"},
                )
            return self._repeat_follow_up_result(
                answer_text=answer_text,
                answer_warning=answer_warning,
                answer_kind=answer_kind,
                answer_provenance=answer_provenance,
                answer_confidence=answer_confidence,
                grounding_bundle=grounding_bundle,
                fallback_sources=fallback_sources,
            )

        if follow_up_kind in {"which_source", "where_written"}:
            source_list = self._formatted_source_list(question, self._sources(grounding_bundle, fallback_sources))
            prefix = (
                "Это написано в"
                if prefers_russian and self._docs_only_sources(self._sources(grounding_bundle, fallback_sources))
                else (
                    "Предыдущий ответ опирался на"
                    if prefers_russian
                    else (
                        "That is written in"
                        if self._docs_only_sources(self._sources(grounding_bundle, fallback_sources))
                        else "The previous answer was grounded in"
                    )
                )
            )
            return self._result(
                answer_text=f"{prefix} {source_list}.",
                grounding_bundle=grounding_bundle,
                fallback_sources=fallback_sources,
                confidence=0.93,
            )

        if follow_up_kind == "why":
            return self._result(
                answer_text=self._why_follow_up_text(question, answer_topic, answer_scope, runtime_snapshot=runtime_snapshot),
                grounding_bundle=grounding_bundle,
                fallback_sources=fallback_sources,
                confidence=0.91,
            )

        if follow_up_kind == "explain_more":
            return self._result(
                answer_text=self._explain_more_follow_up_text(question, answer_topic, answer_scope, runtime_snapshot=runtime_snapshot),
                grounding_bundle=grounding_bundle,
                fallback_sources=fallback_sources,
                confidence=0.92,
            )

        raise self._answer_error(
            ErrorCode.UNSUPPORTED_QUESTION,
            _localized_text(
                prefers_russian,
                en="Answer follow-up is outside the deterministic v1.5 rule set.",
                ru="Это уточнение выходит за рамки детерминированного набора правил v1.5.",
            ),
            details={"reason": "topic_not_supported", "follow_up_kind": follow_up_kind},
        )

    def _repeat_follow_up_result(
        self,
        *,
        answer_text: str,
        answer_warning: str | None,
        answer_kind: str | None,
        answer_provenance: str | None,
        answer_confidence: Any,
        grounding_bundle: GroundingBundle | None,
        fallback_sources: list[str],
    ) -> AnswerResult:
        resolved_answer_kind = _answer_kind_value(answer_kind, fallback_sources=fallback_sources)
        resolved_provenance = _answer_provenance_value(
            answer_provenance,
            answer_kind=resolved_answer_kind,
            fallback_sources=fallback_sources,
        )
        confidence = float(answer_confidence) if answer_confidence is not None else 0.98
        return AnswerResult(
            answer_text=answer_text,
            sources=self._sources(grounding_bundle, fallback_sources),
            source_attributions=self._source_attributions(grounding_bundle, fallback_sources),
            confidence=confidence,
            warning=answer_warning,
            answer_kind=resolved_answer_kind,
            provenance=resolved_provenance,
        )

    def _docs_rule_answer(self, question: QuestionRequest, *, grounding_bundle: GroundingBundle | None) -> AnswerResult:
        lowered = str(getattr(question, "raw_input", "")).lower()
        topic = self._topic(question)
        prefers_russian = _prefers_russian_answer(question)
        if "clarification" in lowered:
            return self._result(
                answer_text=_localized_text(
                    prefers_russian,
                    en=(
                        "Clarification is a hard boundary. JARVIS asks one minimal question only when ambiguity, missing data, low confidence, "
                        "or routing ambiguity blocks safe progress."
                    ),
                    ru=(
                        "Уточнение — это жёсткая граница. JARVIS задаёт один минимальный вопрос только тогда, когда безопасному продолжению мешают "
                        "неоднозначность, нехватка данных, низкая уверенность или неоднозначный роутинг."
                    ),
                ),
                grounding_bundle=grounding_bundle,
                fallback_sources=[self._source("docs/clarification_rules.md"), self._source("docs/runtime_flow.md")],
                confidence=0.95,
            )
        if "confirmation" in lowered:
            return self._result(
                answer_text=_localized_text(
                    prefers_russian,
                    en=(
                        "Confirmation is required before sensitive command actions. JARVIS pauses at the command or step boundary and resumes only "
                        "after explicit approval."
                    ),
                    ru=(
                        "Подтверждение требуется перед чувствительными действиями команды. JARVIS останавливается на границе команды или шага "
                        "и продолжает только после явного одобрения."
                    ),
                ),
                grounding_bundle=grounding_bundle,
                fallback_sources=[self._source("docs/product_rules.md"), self._source("docs/runtime_flow.md")],
                confidence=0.94,
            )
        if "session context" in lowered:
            return self._result(
                answer_text=_localized_text(
                    prefers_russian,
                    en=(
                        "Session context is short-lived state for the active supervised session. It keeps recent targets, execution state, and other "
                        "narrow context needed for follow-ups and grounded status answers."
                    ),
                    ru=(
                        "Session context — это короткоживущее состояние активной наблюдаемой сессии. Оно хранит недавние цели, состояние выполнения "
                        "и другой узкий контекст, нужный для уточнений и grounded-ответов о состоянии."
                    ),
                ),
                grounding_bundle=grounding_bundle,
                fallback_sources=[self._source("docs/session_context.md")],
                confidence=0.95,
            )
        if "runtime" in lowered or "state" in lowered or topic == "runtime":
            return self._result(
                answer_text=_localized_text(
                    prefers_russian,
                    en=(
                        "Command runtime flows through parsing, validating, planning, executing, and blocked terminal states. Question mode stays outside "
                        "the command execution state machine and returns a read-only answer."
                    ),
                    ru=(
                        "Runtime команды проходит через парсинг, валидацию, планирование, выполнение и блокирующие терминальные состояния. "
                        "Режим вопросов остаётся вне state machine выполнения команды и возвращает только read-only ответ."
                    ),
                ),
                grounding_bundle=grounding_bundle,
                fallback_sources=[self._source("docs/runtime_flow.md"), self._source("docs/runtime_components.md")],
                confidence=0.92,
            )
        raise self._answer_error(
            ErrorCode.UNSUPPORTED_QUESTION,
            _localized_text(
                prefers_russian,
                en="Docs question is outside the deterministic v1 rule set.",
                ru="Этот вопрос по документации выходит за рамки детерминированного набора правил v1.",
            ),
            details={"reason": "topic_not_supported"},
        )

    def _repo_structure_answer(self, question: QuestionRequest, *, grounding_bundle: GroundingBundle | None) -> AnswerResult:
        lowered = str(getattr(question, "raw_input", "")).lower()
        prefers_russian = _prefers_russian_answer(question)
        mappings: tuple[tuple[tuple[str, ...], str, list[str]], ...] = (
            (
                ("planner", "execution plan"),
                (
                    "Планирование выполнения находится в planner/execution_planner.py."
                    if prefers_russian
                    else "Execution planning lives in planner/execution_planner.py."
                ),
                [self._source("planner/execution_planner.py"), self._source("docs/repo_structure.md")],
            ),
            (
                ("parser", "parse command"),
                (
                    "Парсинг команд находится в parser/command_parser.py."
                    if prefers_russian
                    else "Command parsing lives in parser/command_parser.py."
                ),
                [self._source("parser/command_parser.py"), self._source("docs/repo_structure.md")],
            ),
            (
                ("validator", "validate command"),
                (
                    "Валидация команд находится в validator/command_validator.py."
                    if prefers_russian
                    else "Command validation lives in validator/command_validator.py."
                ),
                [self._source("validator/command_validator.py"), self._source("docs/repo_structure.md")],
            ),
            (
                ("runtime", "state machine", "runtime state"),
                (
                    "Оркестрация command runtime находится в runtime/runtime_manager.py и runtime/state_machine.py."
                    if prefers_russian
                    else "Command runtime orchestration lives in runtime/runtime_manager.py and runtime/state_machine.py."
                ),
                [self._source("runtime/runtime_manager.py"), self._source("runtime/state_machine.py"), self._source("docs/repo_structure.md")],
            ),
            (
                ("visibility", "ui"),
                (
                    "Маппинг visibility находится в ui/visibility_mapper.py."
                    if prefers_russian
                    else "Visibility mapping lives in ui/visibility_mapper.py."
                ),
                [self._source("ui/visibility_mapper.py"), self._source("docs/repo_structure.md")],
            ),
            (
                ("interaction router", "route interaction", "interaction"),
                (
                    "Верхнеуровневый dual-mode routing находится в interaction/interaction_router.py и interaction/interaction_manager.py."
                    if prefers_russian
                    else "Top-level dual-mode routing lives in interaction/interaction_router.py and interaction/interaction_manager.py."
                ),
                [self._source("interaction/interaction_router.py"), self._source("interaction/interaction_manager.py"), self._source("docs/repo_structure.md")],
            ),
            (
                ("answer engine", "qa", "question-answer"),
                (
                    "Вопросно-ответный слой находится под qa/: answer_engine.py координирует backends, а source_selector.py выбирает grounded-источники."
                    if prefers_russian
                    else "Question answering lives under qa/, with answer_engine.py coordinating the backends and source_selector.py choosing grounded sources."
                ),
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
            _localized_text(
                prefers_russian,
                en="Repo-structure question is outside the deterministic v1 rule set.",
                ru="Этот вопрос о структуре репозитория выходит за рамки детерминированного набора правил v1.",
            ),
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
        prefers_russian = _prefers_russian_answer(question)
        if "confirmation" in lowered:
            suffix = (
                f" Текущая причина блокировки: {blocked_reason}."
                if prefers_russian and blocked_reason
                else (f" Current blocked reason: {blocked_reason}." if blocked_reason else "")
            )
            return self._result(
                answer_text=_localized_text(
                    prefers_russian,
                    en=(
                        "Confirmation exists to protect sensitive actions such as closing active work. JARVIS must pause and wait for explicit approval "
                        "before continuing."
                        f"{suffix}"
                    ),
                    ru=(
                        "Подтверждение существует, чтобы защищать чувствительные действия, например закрытие активной работы. "
                        "JARVIS должен остановиться и дождаться явного одобрения перед продолжением."
                        f"{suffix}"
                    ),
                ),
                grounding_bundle=grounding_bundle,
                fallback_sources=[self._source("docs/product_rules.md"), self._source("docs/runtime_flow.md")],
                confidence=0.94,
            )
        if "execute" in lowered or "blocked" in lowered or blocked_reason:
            reason_text = blocked_reason or (
                "текущее состояние требует уточнения, подтверждения или корректной цели перед продолжением выполнения"
                if prefers_russian
                else "the current state requires clarification, confirmation, or a valid target before execution can continue"
            )
            return self._result(
                answer_text=(
                    f"Выполнение не продолжилось, потому что {reason_text}. JARVIS останавливается на неоднозначности, нехватке данных и границах подтверждения."
                    if prefers_russian
                    else f"Execution did not continue because {reason_text}. JARVIS stops on ambiguity, missing data, and confirmation boundaries."
                ),
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
            _localized_text(
                prefers_russian,
                en="Safety question is outside the deterministic v1 rule set.",
                ru="Этот вопрос о safety выходит за рамки детерминированного набора правил v1.",
            ),
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
        question: QuestionRequest,
        answer_topic: str,
        answer_scope: str,
        *,
        runtime_snapshot: dict[str, Any] | None,
    ) -> str:
        blocked_reason = _text_or_none((runtime_snapshot or {}).get("blocked_reason"))
        prefers_russian = _prefers_russian_answer(question)
        if answer_scope == "blocked_state" or answer_topic == QuestionType.BLOCKED_STATE.value:
            suffix = (
                f" Текущая причина блокировки: {blocked_reason}."
                if prefers_russian and blocked_reason
                else (f" Current blocked reason: {blocked_reason}." if blocked_reason else "")
            )
            return _localized_text(
                prefers_russian,
                en=(
                    "Because blocked commands stay paused until the exact clarification or confirmation boundary is resolved. "
                    "Question mode can explain the boundary, but it cannot approve or resume execution."
                    f"{suffix}"
                ),
                ru=(
                    "Потому что заблокированные команды остаются на паузе, пока не будет снята точная граница уточнения или подтверждения. "
                    "Режим вопросов может объяснить эту границу, но не может сам подтвердить или возобновить выполнение."
                    f"{suffix}"
                ),
            )
        if answer_scope == "recent_runtime" or answer_topic == QuestionType.RECENT_RUNTIME.value or answer_scope == "runtime":
            return _localized_text(
                prefers_russian,
                en=(
                    "Because runtime answers are limited to visible runtime state and short-lived session context from the current supervised session. "
                    "JARVIS must not invent memory or hidden background activity."
                ),
                ru=(
                    "Потому что runtime-ответы ограничены видимым состоянием runtime и короткоживущим session context текущей наблюдаемой сессии. "
                    "JARVIS не должен выдумывать память или скрытую фоновую активность."
                ),
            )
        if answer_scope == "capabilities" or answer_topic == QuestionType.CAPABILITIES.value:
            return _localized_text(
                prefers_russian,
                en=(
                    "Because JARVIS is intentionally bounded to supervised local actions and grounded read-only answers. "
                    "Unsupported or unsafe behavior stays explicit instead of being guessed."
                ),
                ru=(
                    "Потому что JARVIS намеренно ограничен наблюдаемыми локальными действиями и grounded read-only ответами. "
                    "Неподдерживаемое или небезопасное поведение остаётся явным, а не угадывается."
                ),
            )
        if answer_scope == "repo_structure":
            return _localized_text(
                prefers_russian,
                en=(
                    "Because the codebase keeps routing, runtime, visibility, and QA responsibilities in separate modules with one clear home. "
                    "Repo answers point to those ownership boundaries instead of doing arbitrary codebase QA."
                ),
                ru=(
                    "Потому что кодовая база держит routing, runtime, visibility и QA-ответственности в отдельных модулях с понятной зоной владения. "
                    "Ответы по репозиторию указывают на эти границы, а не превращаются в произвольное codebase QA."
                ),
            )
        if answer_scope == "safety" or answer_topic == QuestionType.SAFETY_EXPLANATIONS.value:
            return _localized_text(
                prefers_russian,
                en=(
                    "Because confirmation, clarification, and explicit failures protect against hidden or destructive execution. "
                    "Question mode can explain those boundaries, but it cannot weaken them."
                ),
                ru=(
                    "Потому что подтверждение, уточнение и явные ошибки защищают от скрытого или разрушительного выполнения. "
                    "Режим вопросов может объяснить эти границы, но не может их ослабить."
                ),
            )
        if answer_topic == "clarification":
            return _localized_text(
                prefers_russian,
                en=(
                    "Because ambiguity, missing data, low confidence, and mixed command-question input must stop execution until one narrow point is resolved. "
                    "Clarification exists to keep supervised behavior deterministic."
                ),
                ru=(
                    "Потому что неоднозначность, нехватка данных, низкая уверенность и смешанный ввод команды с вопросом должны остановить выполнение, "
                    "пока не будет снята одна узкая неопределённость. Уточнение нужно, чтобы наблюдаемое поведение оставалось детерминированным."
                ),
            )
        if answer_topic == "confirmation":
            return _localized_text(
                prefers_russian,
                en=(
                    "Because sensitive actions require an explicit approval boundary before execution continues. "
                    "That keeps question answers read-only and prevents silent destructive actions."
                ),
                ru=(
                    "Потому что чувствительные действия требуют явной границы одобрения перед продолжением выполнения. "
                    "Это сохраняет ответы в read-only режиме и не допускает тихих разрушительных действий."
                ),
            )
        if answer_topic == "session_context":
            return _localized_text(
                prefers_russian,
                en=(
                    "Because session context is intentionally short-lived. It only supports immediate follow-ups and grounded status answers inside the current supervised session."
                ),
                ru=(
                    "Потому что session context намеренно короткоживущий. Он поддерживает только ближайшие уточнения и grounded-ответы о состоянии внутри текущей наблюдаемой сессии."
                ),
            )
        return _localized_text(
            prefers_russian,
            en=(
                "Because question mode answers only from grounded local docs, runtime visibility, and short-lived session facts. "
                "If that support is missing, the system must fail honestly instead of guessing."
            ),
            ru=(
                "Потому что режим вопросов отвечает только на основе grounded локальных документов, runtime visibility и короткоживущих фактов сессии. "
                "Если такой опоры не хватает, система должна честно отказать, а не угадывать."
            ),
        )

    def _explain_more_follow_up_text(
        self,
        question: QuestionRequest,
        answer_topic: str,
        answer_scope: str,
        *,
        runtime_snapshot: dict[str, Any] | None,
    ) -> str:
        blocked_reason = _text_or_none((runtime_snapshot or {}).get("blocked_reason"))
        prefers_russian = _prefers_russian_answer(question)
        if answer_scope == "blocked_state" or answer_topic == QuestionType.BLOCKED_STATE.value:
            suffix = (
                f" Видимая причина блокировки: {blocked_reason}."
                if prefers_russian and blocked_reason
                else (f" The visible blocked reason is {blocked_reason}." if blocked_reason else "")
            )
            return _localized_text(
                prefers_russian,
                en=(
                    "In more detail: blocked-state questions read the current clarification or confirmation boundary from visible runtime state. "
                    "They can tell you what reply is needed, but only an explicit command-path reply can unblock the command."
                    f"{suffix}"
                ),
                ru=(
                    "Подробнее: вопросы о blocked state читают текущую границу уточнения или подтверждения из видимого runtime state. "
                    "Они могут сказать, какой ответ нужен, но разблокировать команду может только явный ответ по command path."
                    f"{suffix}"
                ),
            )
        if answer_scope == "recent_runtime" or answer_topic == QuestionType.RECENT_RUNTIME.value:
            return _localized_text(
                prefers_russian,
                en=(
                    "In more detail: recent-runtime answers can read only short-lived session facts such as the last visible command summary, "
                    "recent target, workspace context, and recent search results. They do not introduce long-term memory or repo search."
                ),
                ru=(
                    "Подробнее: ответы про recent runtime могут читать только короткоживущие факты сессии, такие как последний видимый summary команды, "
                    "недавняя цель, контекст рабочего пространства и недавние результаты поиска. Они не добавляют долговременную память или поиск по репозиторию."
                ),
            )
        if answer_scope == "runtime" or answer_topic == QuestionType.RUNTIME_STATUS.value:
            return _localized_text(
                prefers_russian,
                en=(
                    "In more detail: runtime-status answers describe only visible supervised state such as current runtime state, current step, blocked reason, "
                    "and recent folder context when it is explicitly available."
                ),
                ru=(
                    "Подробнее: runtime-status ответы описывают только видимое наблюдаемое состояние, такое как текущее runtime state, текущий шаг, причина блокировки "
                    "и недавний контекст папки, когда он явно доступен."
                ),
            )
        if answer_scope == "capabilities" or answer_topic == QuestionType.CAPABILITIES.value:
            supported_intents = ", ".join(entry["intent"] for entry in SUPPORTED_COMMANDS)
            return _localized_text(
                prefers_russian,
                en=(
                    "In more detail: command mode supports "
                    f"{supported_intents}. "
                    "Question mode stays read-only and grounded to capabilities, runtime state, docs rules, repo structure, and safety boundaries."
                ),
                ru=(
                    "Подробнее: режим команд поддерживает "
                    f"{supported_intents}. "
                    "Режим вопросов остаётся read-only и grounded к возможностям, runtime state, правилам из docs, структуре репозитория и safety-границам."
                ),
            )
        if answer_scope == "repo_structure":
            return _localized_text(
                prefers_russian,
                en=(
                    "In more detail: repo-structure answers point to the primary file or module that owns a responsibility so the dual-mode architecture stays clear. "
                    "Interaction routing lives above command runtime, and QA stays behind the answer-engine seam."
                ),
                ru=(
                    "Подробнее: ответы о структуре репозитория указывают на основной файл или модуль, который владеет ответственностью, чтобы dual-mode архитектура оставалась ясной. "
                    "Interaction routing находится над command runtime, а QA остаётся за швом answer engine."
                ),
            )
        if answer_scope == "safety" or answer_topic == QuestionType.SAFETY_EXPLANATIONS.value:
            return _localized_text(
                prefers_russian,
                en=(
                    "In more detail: safety explanations are grounded in product rules, clarification rules, and visible runtime state. "
                    "They explain why execution paused or failed without changing the blocked boundary."
                ),
                ru=(
                    "Подробнее: safety-объяснения grounded в product rules, clarification rules и видимом runtime state. "
                    "Они объясняют, почему выполнение остановилось или завершилось ошибкой, не меняя саму границу блокировки."
                ),
            )
        if answer_topic == "clarification":
            return _localized_text(
                prefers_russian,
                en=(
                    "In more detail: clarification happens before planning or execution when the input is ambiguous, missing required data, below confidence, "
                    "or mixes command and question semantics. JARVIS asks one minimal question, waits, and then re-enters the normal supervised flow."
                ),
                ru=(
                    "Подробнее: уточнение происходит до планирования или выполнения, когда ввод неоднозначен, не хватает обязательных данных, уверенность слишком низкая "
                    "или смешаны семантики команды и вопроса. JARVIS задаёт один минимальный вопрос, ждёт и затем возвращается в обычный наблюдаемый поток."
                ),
            )
        if answer_topic == "confirmation":
            return _localized_text(
                prefers_russian,
                en=(
                    "In more detail: confirmation pauses on a sensitive command or step boundary. "
                    "A question can explain the boundary, but approval still requires an explicit yes/no style reply on the command path."
                ),
                ru=(
                    "Подробнее: подтверждение ставит паузу на чувствительной границе команды или шага. "
                    "Вопрос может объяснить эту границу, но для одобрения всё равно нужен явный ответ в стиле да/нет по command path."
                ),
            )
        if answer_topic == "session_context":
            return _localized_text(
                prefers_russian,
                en=(
                    "In more detail: session context keeps only active-session state such as recent targets, workspace context, search results, and recent answer context. "
                    "It exists for narrow follow-ups, not for cross-session memory."
                ),
                ru=(
                    "Подробнее: session context хранит только состояние активной сессии, такое как недавние цели, контекст рабочего пространства, результаты поиска и контекст недавнего ответа. "
                    "Он существует для узких уточнений, а не для памяти между сессиями."
                ),
            )
        return _localized_text(
            prefers_russian,
            en=(
                "In more detail: the previous answer stayed inside grounded local scope and used only the smallest source bundle needed to answer safely. "
                "Question mode remains read-only and fails honestly when the needed support is missing."
            ),
            ru=(
                "Подробнее: предыдущий ответ оставался внутри grounded local scope и использовал только минимальный набор источников, нужный для безопасного ответа. "
                "Режим вопросов остаётся read-only и честно отказывает, когда нужной опоры не хватает."
            ),
        )

    def _docs_only_sources(self, sources: list[str]) -> bool:
        return bool(sources) and all("/docs/" in source.replace("\\", "/") for source in sources)

    def _formatted_source_list(self, question: QuestionRequest, sources: list[str]) -> str:
        labels = [self._display_source(source) for source in sources]
        prefers_russian = _prefers_russian_answer(question)
        if not labels:
            return "предыдущие grounded-источники" if prefers_russian else "the previous grounded sources"
        if len(labels) == 1:
            return labels[0]
        if len(labels) == 2:
            conjunction = "и" if prefers_russian else "and"
            return f"{labels[0]} {conjunction} {labels[1]}"
        conjunction = "и" if prefers_russian else "and"
        return f"{', '.join(labels[:-1])}, {conjunction} {labels[-1]}"

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


def _prefers_russian_answer(question: QuestionRequest | None) -> bool:
    return question_request_language(question) == "ru"


def _localized_text(prefers_russian: bool, *, en: str, ru: str) -> str:
    return ru if prefers_russian else en


def _answer_kind_value(value: str | None, *, fallback_sources: list[str]) -> AnswerKind:
    normalized = str(value or "").strip()
    if normalized:
        try:
            return AnswerKind(normalized)
        except ValueError:
            pass
    return AnswerKind.GROUNDED_LOCAL if fallback_sources else AnswerKind.OPEN_DOMAIN_MODEL


def _answer_provenance_value(
    value: str | None,
    *,
    answer_kind: AnswerKind,
    fallback_sources: list[str],
) -> AnswerProvenance | None:
    normalized = str(value or "").strip()
    if normalized:
        try:
            return AnswerProvenance(normalized)
        except ValueError:
            pass
    if fallback_sources:
        return AnswerProvenance.LOCAL_SOURCES
    if answer_kind == AnswerKind.OPEN_DOMAIN_MODEL:
        return AnswerProvenance.MODEL_KNOWLEDGE
    return None
