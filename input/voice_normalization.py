"""Normalization helpers for spoken CLI input."""

from __future__ import annotations

import re

_VOICE_STARTERS = {
    "answer",
    "execute",
    "open",
    "run",
    "launch",
    "start",
    "close",
    "list",
    "show",
    "find",
    "search",
    "prepare",
    "set",
    "use",
    "focus",
    "confirm",
    "continue",
    "cancel",
    "stop",
    "yes",
    "no",
    "what",
    "how",
    "why",
    "which",
    "where",
    "when",
    "who",
    "explain",
    "help",
    "открой",
    "запусти",
    "закрой",
    "покажи",
    "найди",
    "подготовь",
    "используй",
    "да",
    "нет",
    "подтверждаю",
    "подтвердить",
    "отмена",
    "отменить",
    "отмени",
    "стоп",
    "что",
    "как",
    "почему",
    "зачем",
    "где",
    "когда",
    "кто",
    "сколько",
    "какие",
    "какой",
    "какая",
    "какое",
    "объясни",
    "помоги",
}
_VOICE_WAKE_PREFIX_RE = re.compile(
    r"^\s*(?:(?:hello|hi|hey|ok|okay|привет|эй|окей)(?:\s*[,:;.!?-]\s*|\s+))?(?:jarvis|джарвис)(?:\s*[,:;.!?-]\s*|\s+)",
    flags=re.IGNORECASE,
)
_VOICE_WAKE_TOKENS = frozenset({"jarvis", "джарвис"})
_LEADING_VOICE_FILLER_TOKENS = frozenset(
    {
        "hello",
        "hi",
        "hey",
        "ok",
        "okay",
        "привет",
        "эй",
        "окей",
        "слушай",
        "слушай-ка",
        "ну",
        "а",
    }
)
_RUSSIAN_COMMAND_TRANSLATIONS = {
    "открой": "open",
    "запусти": "open",
    "закрой": "close",
    "покажи": "show",
    "найди": "find",
    "подготовь": "prepare",
    "используй": "use",
}
_RUSSIAN_COMMAND_TARGET_ALIASES = {
    "телеграм": "telegram",
    "сафари": "safari",
    "заметки": "notes",
}
_RUSSIAN_APPROVAL_FOLLOWUP_TOKENS = frozenset({"да", "подтверждаю", "подтвердить"})
_RUSSIAN_DENIAL_FOLLOWUP_TOKENS = frozenset({"нет", "отмена", "отменить", "отмени", "стоп"})
_RUSSIAN_EXACT_CANONICAL_MAP = {
    "что ты умеешь": "what can you do",
    "что именно тебе нужно подтвердить": "what exactly do you need me to confirm",
    "что тебе нужно подтвердить": "what do you need me to confirm",
}
_RUSSIAN_ANSWER_FOLLOW_UP_MAP = {
    "скажи подробнее": "Explain more",
    "объясни подробнее": "Explain more",
    "расскажи подробнее": "Explain more",
    "подробнее": "Explain more",
    "какой источник": "Which source?",
    "какие источники": "Which sources?",
    "где это написано": "Where is that written",
    "где это задокументировано": "Where is that documented",
    "почему": "Why is that",
    "почему это так": "Why is that",
    "почему так": "Why so",
    "повтори": "Repeat that",
    "повтори это": "Repeat that",
    "повтори ответ": "Repeat that",
    "скажи еще раз": "Repeat that",
    "скажи ещё раз": "Repeat that",
}
_RUSSIAN_CONTROL_COMMAND_MAP = {
    "слушай снова": "listen again",
    "слушай еще раз": "listen again",
    "слушай ещё раз": "listen again",
    "замолчи": "stop speaking",
}
_VOICE_EXACT_CANONICAL_MAP = {
    "repeat": "Repeat that",
}
_RUSSIAN_MIXED_COMMAND_RE = re.compile(
    r"^(?P<head>.+?)\s+(?P<join>и|а потом)\s+(?P<tail>(?:открой|запусти|закрой|покажи|найди|подготовь|используй)\b.+)$",
    flags=re.IGNORECASE,
)
_TERMINAL_PUNCTUATION = " \t\r\n,.;:!?"


def normalize_voice_command(recognized_text: str) -> str:
    """Keep one deterministic interaction from a noisy voice transcription."""
    compact = " ".join(str(recognized_text or "").strip().split())
    compact = _strip_voice_prefix_noise(compact)
    if not compact:
        return compact

    compact = _collapse_repeated_voice_phrase(compact)
    compact = _canonicalize_russian_followup(compact)
    compact = _normalize_russian_mixed_interaction(compact)
    compact = _canonicalize_russian_answer_follow_up(compact)
    compact = _canonicalize_russian_control_command(compact)
    compact = _canonicalize_exact_voice_phrase(compact)
    compact = _canonicalize_exact_russian_phrase(compact)
    compact = _canonicalize_russian_command(compact)
    return compact


def strip_voice_wake_prefix(text: str) -> str:
    """Strip a small fixed wake-word prefix used in spoken commands."""
    candidate = str(text or "").strip()
    stripped = _VOICE_WAKE_PREFIX_RE.sub("", candidate, count=1).strip()
    return stripped or candidate


def _strip_voice_prefix_noise(text: str) -> str:
    candidate = str(text or "").strip()
    if not candidate:
        return candidate

    for _ in range(4):
        updated = _strip_leading_voice_fillers(candidate)
        updated = strip_voice_wake_prefix(updated)
        updated = _strip_leading_voice_fillers(updated)
        updated = " ".join(updated.split()).strip()
        if not updated or updated == candidate:
            return updated or candidate
        candidate = updated
    return candidate


def _strip_leading_voice_fillers(text: str) -> str:
    candidate = str(text or "").strip()
    tokens = candidate.split()
    if not tokens:
        return candidate

    index = 0
    while index < len(tokens) and _normalized_voice_token(tokens[index]) in _LEADING_VOICE_FILLER_TOKENS:
        index += 1

    if index == 0 or index >= len(tokens):
        return candidate

    first_payload_token = _normalized_voice_token(tokens[index])
    if first_payload_token in _VOICE_STARTERS or first_payload_token in _VOICE_WAKE_TOKENS:
        return " ".join(tokens[index:])
    return candidate


def _normalized_voice_token(token: str) -> str:
    return str(token or "").lower().strip(_TERMINAL_PUNCTUATION).strip("-")


def _starts_with_voice_starter(text: str) -> bool:
    tokens = str(text or "").split(" ", maxsplit=1)
    if not tokens:
        return False
    starter = _normalized_voice_token(tokens[0])
    return starter in _VOICE_STARTERS


def _collapse_repeated_voice_phrase(text: str) -> str:
    tokens = text.split(" ")
    lowered = [token.lower() for token in tokens]

    for index in range(1, len(tokens)):
        if lowered[index] not in _VOICE_STARTERS:
            continue

        head = " ".join(tokens[:index]).strip()
        tail = " ".join(tokens[index:]).strip()
        if not head or not tail:
            continue

        if head.lower() == tail.lower():
            return head

        if lowered[index] == lowered[0]:
            return head

    return text


def _canonicalize_exact_russian_phrase(text: str) -> str:
    lookup = text.lower().strip(_TERMINAL_PUNCTUATION)
    mapped = _RUSSIAN_EXACT_CANONICAL_MAP.get(lookup)
    return mapped or text


def _canonicalize_exact_voice_phrase(text: str) -> str:
    lookup = text.lower().strip(_TERMINAL_PUNCTUATION)
    mapped = _VOICE_EXACT_CANONICAL_MAP.get(lookup)
    return mapped or text


def _canonicalize_russian_followup(text: str) -> str:
    tokens = [token.lower().strip(_TERMINAL_PUNCTUATION) for token in text.split()]
    compact_tokens = [token for token in tokens if token]
    if not compact_tokens:
        return text

    if all(token in _RUSSIAN_APPROVAL_FOLLOWUP_TOKENS for token in compact_tokens):
        if any(token.startswith("подт") for token in compact_tokens):
            return "confirm"
        return "yes"

    if all(token in _RUSSIAN_DENIAL_FOLLOWUP_TOKENS for token in compact_tokens):
        if all(token == "нет" for token in compact_tokens):
            return "no"
        return "cancel"

    return text


def _canonicalize_russian_answer_follow_up(text: str) -> str:
    lookup = text.lower().strip(_TERMINAL_PUNCTUATION)
    mapped = _RUSSIAN_ANSWER_FOLLOW_UP_MAP.get(lookup)
    return mapped or text


def _canonicalize_russian_control_command(text: str) -> str:
    lookup = text.lower().strip(_TERMINAL_PUNCTUATION)
    mapped = _RUSSIAN_CONTROL_COMMAND_MAP.get(lookup)
    return mapped or text


def _normalize_russian_mixed_interaction(text: str) -> str:
    match = _RUSSIAN_MIXED_COMMAND_RE.match(text.strip())
    if match is None:
        return text

    head = (match.group("head") or "").strip()
    join_token = (match.group("join") or "").strip().lower()
    tail = _canonicalize_russian_command((match.group("tail") or "").strip())
    if not head or not tail:
        return text

    joiner = "then" if join_token == "а потом" else "and"
    return f"{head} {joiner} {tail}"


def _canonicalize_russian_command(text: str) -> str:
    tokens = text.split(" ", maxsplit=1)
    if not tokens:
        return text

    english_starter = _RUSSIAN_COMMAND_TRANSLATIONS.get(tokens[0].lower())
    if english_starter is None:
        return text

    payload = tokens[1].strip() if len(tokens) > 1 else ""
    if not payload:
        return english_starter

    payload_lookup = payload.lower().strip(_TERMINAL_PUNCTUATION)
    normalized_payload = _RUSSIAN_COMMAND_TARGET_ALIASES.get(payload_lookup, payload)
    return f"{english_starter} {normalized_payload}".strip()
