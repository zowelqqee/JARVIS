"""Top-level interaction router for command mode vs question-answer mode."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from context.session_context import SessionContext

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from interaction_kind import InteractionKind  # type: ignore  # noqa: E402


RoutedInteraction = InteractionKind


@dataclass(slots=True)
class InteractionDecision:
    """Deterministic routing decision for one normalized input."""

    kind: InteractionKind
    normalized_input: str
    confidence: float
    reason: str | None = None
    clarification_message: str | None = None
    question_input: str | None = None
    command_input: str | None = None


_COMMAND_STARTERS = (
    "open ",
    "launch ",
    "start ",
    "reopen ",
    "run ",
    "close ",
    "list ",
    "show ",
    "find ",
    "search ",
    "prepare ",
    "set up ",
    "focus ",
    "switch ",
    "use ",
    "confirm",
    "cancel",
    "yes",
    "no",
)
_EXECUTION_COMMAND_STARTERS = (
    "open ",
    "launch ",
    "start ",
    "reopen ",
    "run ",
    "close ",
    "list ",
    "show ",
    "find ",
    "search ",
    "prepare ",
    "set up ",
    "focus ",
    "switch ",
    "use ",
)
_POLITE_COMMAND_PREFIXES = (
    "can you open ",
    "can you launch ",
    "can you start ",
    "can you close ",
    "can you find ",
    "can you search ",
    "could you open ",
    "could you launch ",
    "could you start ",
    "could you close ",
    "would you open ",
    "would you launch ",
    "would you start ",
    "would you close ",
    "please open ",
    "please launch ",
    "please start ",
    "please close ",
)
_QUESTION_STARTERS = (
    "what ",
    "how ",
    "why ",
    "which ",
    "where ",
    "when ",
    "who ",
    "explain ",
    "help ",
    "что ",
    "как ",
    "почему ",
    "зачем ",
    "где ",
    "когда ",
    "кто ",
    "сколько ",
    "какой ",
    "какая ",
    "какое ",
    "какие ",
    "объясни ",
    "помоги ",
)
_QUESTION_MARKERS = (
    "what can you do",
    "which commands do you support",
    "what do you support",
    "how does ",
    "what is ",
    "why do you ",
    "repeat that",
    "repeat the answer",
    "say that again",
    "что ты умеешь",
    "что такое ",
    "как работает ",
)
_GREETING_QUESTION_MARKERS = (
    "hello",
    "hello jarvis",
    "hi",
    "hi jarvis",
    "hey",
    "hey jarvis",
    "привет",
    "привет джарвис",
    "здравствуй",
    "здравствуй джарвис",
)
_MIXED_COMMAND_MARKERS = (
    " and open ",
    " and launch ",
    " and start ",
    " and close ",
    " and find ",
    " and search ",
    " and prepare ",
    " and focus ",
    " and switch ",
    " and use ",
    " then open ",
    " then close ",
    " then search ",
)
_BLOCKED_STATE_QUESTION_MARKERS = (
    "what are you waiting",
    "what are you waiting for",
    "why did you stop",
    "what do you need from me",
    "what exactly do you need me to confirm",
    "what do you need me to confirm",
    "что ты ждешь",
    "что тебе нужно",
    "что тебе нужно от меня",
    "что именно тебе нужно подтвердить",
    "что тебе нужно подтвердить",
)
_CHOICE_FILLER_PREFIXES = ("please ", "just ", "then ", "okay ", "ok ", "пожалуйста ", "тогда ", "ладно ")
_ANSWER_CHOICE_PATTERNS = (
    re.compile(r"^(?:the\s+)?answer(?:\s+first)?$"),
    re.compile(r"^question(?:\s+first)?$"),
    re.compile(r"^explain(?:\s+first)?$"),
    re.compile(r"^(?:сначала\s+)?(?:ответ|ответь|ответить)$"),
)
_EXECUTE_CHOICE_PATTERNS = (
    re.compile(r"^(?:the\s+)?command$"),
    re.compile(r"^(?:execute|run|do)(?:\s+(?:the\s+)?command)?(?:\s+first)?$"),
    re.compile(r"^(?:сначала\s+)?команд[ау]$"),
    re.compile(r"^(?:сначала\s+)?(?:выполни|выполнить)(?:\s+команд[ау])?$"),
)
_EMBEDDED_COMMAND_PATTERN = re.compile(
    r"\b(?:and|then)\s+(?P<command>(?:open|launch|start|reopen|run|close|list|show|find|search|prepare|focus|switch|use)\b.*)$",
    flags=re.IGNORECASE,
)


def route_interaction(
    raw_input: str,
    session_context: SessionContext | None = None,
    runtime_state: str | None = None,
) -> InteractionDecision:
    """Route one raw input into command mode, question mode, or routing clarification."""
    del session_context  # reserved for future routing refinements

    normalized = _normalize_for_routing(raw_input)
    state_text = str(getattr(runtime_state, "value", runtime_state or "")).strip()
    if state_text in {"awaiting_confirmation", "awaiting_clarification"}:
        if _looks_like_blocked_state_question(normalized):
            return InteractionDecision(
                kind=InteractionKind.QUESTION,
                normalized_input=normalized,
                confidence=0.93,
                reason="blocked_state_question",
            )
        return InteractionDecision(
            kind=InteractionKind.COMMAND,
            normalized_input=normalized,
            confidence=1.0,
            reason="blocked_state_priority",
        )

    if _looks_like_polite_command(normalized):
        return InteractionDecision(kind=InteractionKind.COMMAND, normalized_input=normalized, confidence=0.95)

    looks_like_command = _looks_like_command(normalized)
    looks_like_question = _looks_like_question(normalized)

    if looks_like_question and _contains_embedded_command_request(normalized):
        question_input, command_input = split_mixed_interaction_input(normalized)
        return InteractionDecision(
            kind=InteractionKind.CLARIFICATION,
            normalized_input=normalized,
            confidence=0.8,
            reason="mixed_interaction",
            clarification_message=_mixed_interaction_message(command_input),
            question_input=question_input,
            command_input=command_input,
        )

    if looks_like_command and looks_like_question:
        question_input, command_input = split_mixed_interaction_input(normalized)
        return InteractionDecision(
            kind=InteractionKind.CLARIFICATION,
            normalized_input=normalized,
            confidence=0.78,
            reason="mixed_interaction",
            clarification_message=_mixed_interaction_message(command_input),
            question_input=question_input,
            command_input=command_input,
        )

    if looks_like_command:
        return InteractionDecision(kind=InteractionKind.COMMAND, normalized_input=normalized, confidence=0.9)

    if looks_like_question:
        return InteractionDecision(kind=InteractionKind.QUESTION, normalized_input=normalized, confidence=0.85)

    return InteractionDecision(kind=InteractionKind.COMMAND, normalized_input=normalized, confidence=0.55, reason="fallback_command")


def _normalize_for_routing(raw_input: str) -> str:
    if not isinstance(raw_input, str):
        return ""
    return " ".join(raw_input.strip().split())


def split_mixed_interaction_input(raw_input: str) -> tuple[str | None, str | None]:
    """Split one mixed question+command input into explicit question and command parts."""
    normalized = _normalize_for_routing(raw_input)
    if not normalized:
        return None, None
    match = _EMBEDDED_COMMAND_PATTERN.search(normalized)
    if match is None:
        return None, None

    question_input = normalized[: match.start()].strip(" \t\r\n,.!?;:")
    command_input = str(match.group("command") or "").strip(" \t\r\n,.!?;:")
    if not question_input or not command_input:
        return None, None
    return question_input, command_input


def resolve_interaction_clarification_choice(raw_input: str) -> str | None:
    """Resolve a short answer/execute reply for a pending mixed interaction clarification."""
    normalized = _normalize_for_routing(raw_input)
    if not normalized:
        return None

    lowered = normalized.lower().strip(" \t\r\n,.!?;:")
    while True:
        updated = lowered
        for prefix in _CHOICE_FILLER_PREFIXES:
            if updated.startswith(prefix):
                updated = updated[len(prefix) :].strip()
                break
        if updated == lowered:
            break
        lowered = updated

    if any(pattern.fullmatch(lowered) for pattern in _ANSWER_CHOICE_PATTERNS):
        return "answer"
    if any(pattern.fullmatch(lowered) for pattern in _EXECUTE_CHOICE_PATTERNS):
        return "execute"
    return None


def looks_like_fresh_interaction_input(raw_input: str) -> bool:
    """Return whether the input is a fresh explicit command/question rather than a short routing reply."""
    normalized = _normalize_for_routing(raw_input)
    if not normalized:
        return False
    return (
        _looks_like_question(normalized)
        or _looks_like_polite_command(normalized)
        or _looks_like_execution_command(normalized)
        or (_looks_like_question(normalized) and _contains_embedded_command_request(normalized))
    )


def _mixed_interaction_message(command_input: str | None) -> str:
    normalized_command = _normalize_for_routing(command_input or "").strip(" \t\r\n,.!?;:")
    if not normalized_command:
        return "Do you want an answer first or should I execute the command?"
    return f"Do you want an answer first or should I {normalized_command}?"


def _looks_like_command(text: str) -> bool:
    lowered = text.lower()
    return lowered.startswith(_COMMAND_STARTERS)


def _looks_like_execution_command(text: str) -> bool:
    lowered = text.lower()
    return lowered.startswith(_EXECUTION_COMMAND_STARTERS)


def _looks_like_polite_command(text: str) -> bool:
    lowered = text.lower()
    return lowered.startswith(_POLITE_COMMAND_PREFIXES)


def _looks_like_question(text: str) -> bool:
    lowered = text.lower()
    return (
        lowered.endswith("?")
        or lowered.startswith(_QUESTION_STARTERS)
        or lowered in _GREETING_QUESTION_MARKERS
        or any(marker in lowered for marker in _QUESTION_MARKERS)
    )


def _contains_embedded_command_request(text: str) -> bool:
    lowered = f" {text.lower()} "
    return any(marker in lowered for marker in _MIXED_COMMAND_MARKERS)


def _looks_like_blocked_state_question(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _BLOCKED_STATE_QUESTION_MARKERS)
