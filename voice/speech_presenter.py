"""Speech-first rendering helpers for voice output."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from voice.language import detect_spoken_locale, prefers_russian_locale
from voice.tts_provider import SpeechUtterance

_INTERNAL_COMPLETION_RE = re.compile(r"^Completed [a-z_]+ with \d+ step\(s\)\.$")
_APPROVE_CONFIRMATION_RE = re.compile(
    r"^Approve\s+(?P<intent>[a-z_]+)(?:\s+for\s+(?P<targets>.+?))?\s+before execution\.$",
    flags=re.IGNORECASE,
)
_MIXED_INTERACTION_CLARIFICATION_RE = re.compile(
    r"^Do you want an answer first or should I open (?P<target>.+)\?$",
    flags=re.IGNORECASE,
)
_TARGET_NOT_FOUND_WITH_OPTIONS_RE = re.compile(
    r"^I could not find (?P<target>.+?); did you mean (?P<options>.+)\?$",
    flags=re.IGNORECASE,
)
_TARGET_NOT_FOUND_WITH_TARGET_RE = re.compile(
    r"^I could not find (?P<target>.+?); which target should I use\?$",
    flags=re.IGNORECASE,
)
_TARGET_NOT_FOUND_GENERIC_OPTIONS_RE = re.compile(
    r"^I could not find that target; did you mean (?P<options>.+)\?$",
    flags=re.IGNORECASE,
)
_OPEN_AFTER_SEARCH_WITH_TARGET_DETAIL_RE = re.compile(
    r"^Found a matching file, but could not open it: (?P<target>.+?)\. (?P<detail>.+)$",
    flags=re.IGNORECASE,
)
_OPEN_AFTER_SEARCH_WITH_TARGET_RE = re.compile(
    r"^Found a matching file, but could not open it: (?P<target>.+?)\.$",
    flags=re.IGNORECASE,
)
_OPEN_AFTER_SEARCH_WITH_DETAIL_RE = re.compile(
    r"^Found a matching file, but could not open it\. (?P<detail>.+)$",
    flags=re.IGNORECASE,
)
_LIST_WINDOWS_FAILURE_RE = re.compile(
    r"^Could not list windows(?:: (?P<detail>.+))?$",
    flags=re.IGNORECASE,
)
_SEARCH_OPEN_EMPTY_RE = re.compile(
    r"^Search found no matches to open(?:(?:\.|:)\s*(?P<detail>.+))?$",
    flags=re.IGNORECASE,
)
_SEARCH_FOUND_RE = re.compile(
    r"^Found (?P<count>\d+) (?P<label>match|matches)(?P<scope> in .+)?\.$",
    flags=re.IGNORECASE,
)
_SEARCH_FOUND_AND_OPEN_RE = re.compile(
    r"^Found (?P<count>\d+) (?P<label>match|matches)(?P<scope> in .+)? and opened a file\.$",
    flags=re.IGNORECASE,
)
_SEARCH_COMPLETED_RE = re.compile(
    r"^Search completed(?P<scope> in .+)?\.$",
    flags=re.IGNORECASE,
)
_SEARCH_COMPLETED_AND_OPEN_RE = re.compile(
    r"^Search completed and opened a file\.$",
    flags=re.IGNORECASE,
)
_VISIBLE_WINDOWS_RE = re.compile(
    r"^Found (?P<count>\d+) visible (?P<label>window|windows)\.$",
    flags=re.IGNORECASE,
)
_FILTERED_WINDOWS_RE = re.compile(
    r"^Found (?P<count>\d+) (?P<filter>.+) (?P<label>window|windows)\.$",
    flags=re.IGNORECASE,
)
_NO_VISIBLE_FILTERED_WINDOWS_RE = re.compile(
    r"^No visible (?P<filter>.+) windows found\.$",
    flags=re.IGNORECASE,
)
_URL_RE = re.compile(r"(?P<url>https?://[^\s)]+)")
_ABSOLUTE_PATH_RE = re.compile(r"(?P<path>/[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)+)")
_RELATIVE_PATH_RE = re.compile(r"(?P<path>(?:[A-Za-z0-9._-]+/)+[A-Za-z0-9._-]+)")
_SPOKEN_MARKDOWN_RE = re.compile(r"(```|`|\*\*|__)")
_QUESTION_REFUSAL_RE = re.compile(r"\bI can['’]t help with\b", flags=re.IGNORECASE)
_QUESTION_SELF_HARM_REFUSAL_RE = re.compile(
    r"\b(can['’]t help with self-harm|can['’]t help with instructions for hurting yourself)\b",
    flags=re.IGNORECASE,
)
_INTERNAL_DEBUG_MARKERS = (
    "Traceback (most recent call last):",
    "Debug:",
    "debug:",
    "request_id=",
    "correlation_id=",
    "latency_ms=",
    "error_code=",
    "structured_output=",
    "output_text=",
)

_SPOKEN_INTENT_TEMPLATES = {
    "en": {
        "close_app": "Closed {targets}.",
        "open_app": "Opened {targets}.",
        "open_file": "Opened file {targets}.",
        "open_folder": "Opened folder {targets}.",
        "prepare_workspace": "Prepared workspace: {targets}.",
    },
    "ru": {
        "close_app": "Закрыл {targets}.",
        "open_app": "Открыл {targets}.",
        "open_file": "Открыл файл {targets}.",
        "open_folder": "Открыл папку {targets}.",
        "prepare_workspace": "Подготовил рабочее пространство: {targets}.",
    },
}

_SPOKEN_CONFIRMATION_TEMPLATES = {
    "en": {
        "close_app": "Do you want me to close {targets}? Say yes or no.",
        "close_window": "Do you want me to close the {targets} window? Say yes or no.",
        "open_app": "Do you want me to open {targets}?",
        "open_file": "Do you want me to open file {targets}?",
    },
    "ru": {
        "close_app": "Закрыть {targets}? Скажи да или нет.",
        "close_window": "Закрыть окно {targets}? Скажи да или нет.",
        "open_app": "Открыть {targets}?",
        "open_file": "Открыть файл {targets}?",
    },
}

_RUSSIAN_CLARIFICATION_EXACT_MAP = {
    "I am not sure what you meant; can you rephrase the command?": "Не уверен, что ты имел в виду. Переформулируй команду.",
    "What should I search for?": "Что мне искать?",
    "Which website URL should I open?": "Какой адрес сайта открыть?",
    "What workspace should I prepare?": "Какое рабочее пространство подготовить?",
    "Please reply with confirm or cancel.": "Скажи: подтвердить или отменить.",
    "Please reply with answer or execute.": "Скажи: ответить или выполнить.",
    "Which previous target are you referring to?": "Какую предыдущую цель ты имеешь в виду?",
    "Please clarify the action and target.": "Уточни действие и цель.",
    "Which app do you want?": "Какое приложение ты имеешь в виду?",
}

_ENGLISH_CLARIFICATION_EXACT_MAP = {
    "Please reply with confirm or cancel.": "Say confirm or cancel.",
    "Please reply with answer or execute.": "Say answer or execute.",
    "Which previous target are you referring to?": "Which target do you mean?",
    "Which website URL should I open?": "Which website should I open?",
    "Please clarify the action and target.": "Tell me the action and target.",
}

_RUSSIAN_FAILURE_EXACT_MAP = {
    "Command cancelled.": "Команда отменена.",
    "Confirmation denied. Command cancelled.": "Подтверждение отклонено. Команда отменена.",
}

_RUSSIAN_HINT_EXACT_MAP = {
    "Reply yes to continue or no to cancel.": "Скажи да, чтобы продолжить, или нет, чтобы отменить.",
    "Reply with one app name.": "Назови одно приложение.",
    "Reply with one window name.": "Назови одно окно.",
    "Reply with an exact name or full path.": "Назови точное имя или полный путь.",
    "Reply with one full website URL.": "Назови один полный адрес сайта.",
    "Reply with a folder or search query.": "Назови папку или поисковый запрос.",
    "Reply with one project folder.": "Назови одну папку проекта.",
    "Reply with one specific target.": "Назови одну конкретную цель.",
    "Try a more specific app or file name.": "Назови приложение или файл точнее.",
    "Try a more specific target name.": "Назови цель точнее.",
    "Try opening a folder first, then retry.": "Сначала открой папку, потом попробуй снова.",
    "Try opening a folder first, then search inside it.": "Сначала открой папку, потом ищи внутри неё.",
    "Try again in an active macOS desktop session.": "Попробуй ещё раз в активной сессии macOS.",
    "Try using the app name instead of a window reference.": "Попробуй использовать имя приложения вместо ссылки на окно.",
}

_ENGLISH_HINT_EXACT_MAP = {
    "Reply yes to continue or no to cancel.": "Say yes to continue or no to cancel.",
    "Reply with one app name.": "Say one app name.",
    "Reply with one window name.": "Say one window name.",
    "Reply with an exact name or full path.": "Say an exact name or full path.",
    "Reply with one full website URL.": "Say one full website address.",
    "Reply with a folder or search query.": "Say a folder or search query.",
    "Reply with one project folder.": "Say one project folder.",
    "Reply with one specific target.": "Say one specific target.",
    "Try a more specific app or file name.": "Try a more specific app or file name.",
    "Try a more specific target name.": "Try a more specific target name.",
    "Try opening a folder first, then retry.": "Try opening a folder first, then retry.",
    "Try opening a folder first, then search inside it.": "Try opening a folder first, then search inside it.",
    "Try again in an active macOS desktop session.": "Try again in an active macOS desktop session.",
    "Try using the app name instead of a window reference.": "Try using the app name instead of a window reference.",
    "Try a more specific command.": "Try a more specific command.",
}

_RUSSIAN_QUESTION_TEXT_EXACT_MAP = {
    "I can't help with that request.": "Я не могу помочь с этой просьбой.",
    "I can’t help with that request.": "Я не могу помочь с этой просьбой.",
}

_RUSSIAN_QUESTION_WARNING_EXACT_MAP = {
    "Answer is limited to grounded local sources.": "Ответ ограничен локальными источниками.",
    "This answer is based on model knowledge, not local sources.": "Этот ответ основан на знаниях модели, а не на локальных источниках.",
    "This answer may be out of date for changing public facts.": "Этот ответ может быть неактуален для меняющихся публичных фактов.",
    "This is general information, not medical advice.": "Это общая информация, а не медицинский совет.",
    "This is general information, not legal advice.": "Это общая информация, а не юридическая консультация.",
    "This is general information, not financial advice.": "Это общая информация, а не финансовая рекомендация.",
}

_RUSSIAN_QUESTION_FAILURE_EXACT_MAP = {
    "UNSUPPORTED_QUESTION: Question is outside the supported v1 grounded QA scope.": (
        "Я не могу ответить на этот вопрос в текущем режиме."
    ),
    "INSUFFICIENT_CONTEXT: No recent answer context is available for that follow-up.": (
        "Мне не хватает недавнего контекста, чтобы ответить на это уточнение."
    ),
}


def interaction_speech_utterance(result: object, preferred_locale: str | None = None) -> SpeechUtterance | None:
    """Return one prepared spoken utterance for an interaction result."""
    message = interaction_speech_message(result, preferred_locale=preferred_locale)
    if not message:
        return None
    return SpeechUtterance(text=message, locale=_spoken_utterance_locale(message, preferred_locale=preferred_locale))


def latency_filler_utterance(preferred_locale: str | None = None) -> SpeechUtterance:
    """Return one short spoken filler for slow voice answer generation."""
    if prefers_russian_locale(preferred_locale):
        return SpeechUtterance(text="Одну секунду.", locale="ru-RU")
    return SpeechUtterance(text="One moment.", locale="en-US")


def interaction_speech_message(result: object, preferred_locale: str | None = None) -> str | None:
    """Return the speech-friendly top-level interaction message."""
    mode = _interaction_mode_value(result)
    visibility = _interaction_visibility(result)

    if mode == "question":
        return _question_speech_message(result=result, visibility=visibility, preferred_locale=preferred_locale)

    if mode == "clarification":
        clarification_question = str(visibility.get("clarification_question", "") or "").strip()
        if not clarification_question:
            clarification_request = getattr(result, "clarification_request", None)
            clarification_question = str(getattr(clarification_request, "message", "") or "").strip()
        if clarification_question:
            return _spoken_clarification_text(clarification_question, preferred_locale=preferred_locale)
        failure_message = str(visibility.get("failure_message", "") or "").strip()
        if not failure_message:
            error = getattr(result, "error", None)
            failure_message = _interaction_error_message(error) if error is not None else ""
        if failure_message:
            return _spoken_failure_text(failure_message, preferred_locale=preferred_locale)
        return None

    return _command_speech_message(visibility, preferred_locale=preferred_locale)


def _question_speech_message(
    *,
    result: object,
    visibility: dict[str, Any],
    preferred_locale: str | None = None,
) -> str | None:
    summary = _question_summary(result=result, visibility=visibility)
    if summary:
        spoken_summary = _spoken_question_text(summary, preferred_locale=preferred_locale)
        warning = str(visibility.get("answer_warning", "") or "").strip()
        if not warning:
            answer_result = getattr(result, "answer_result", None)
            warning = str(getattr(answer_result, "warning", "") or "").strip()
        if warning:
            spoken_warning = _spoken_question_warning(warning, preferred_locale=preferred_locale)
            return f"{spoken_summary} {_warning_prefix(preferred_locale, spoken_summary, spoken_warning)}: {spoken_warning}"
        return spoken_summary

    answer_text = str(visibility.get("answer_text", "") or "").strip()
    if not answer_text:
        answer_result = getattr(result, "answer_result", None)
        answer_text = str(getattr(answer_result, "answer_text", "") or "").strip()
    if answer_text:
        spoken_answer = _spoken_question_answer_text(answer_text, preferred_locale=preferred_locale)
        if spoken_answer:
            return spoken_answer

    failure_message = str(visibility.get("failure_message", "") or "").strip()
    if not failure_message:
        error = getattr(result, "error", None)
        failure_message = _interaction_error_message(error) if error is not None else ""
    if failure_message:
        return _spoken_question_failure(failure_message, preferred_locale=preferred_locale)
    return None


def _command_speech_message(visibility: dict[str, Any], *, preferred_locale: str | None = None) -> str | None:
    clarification_question = str(visibility.get("clarification_question", "") or "").strip()
    if clarification_question:
        return _spoken_clarification_text(clarification_question, preferred_locale=preferred_locale)

    confirmation_request = visibility.get("confirmation_request")
    if isinstance(confirmation_request, dict):
        confirmation_message = _spoken_confirmation_message(
            confirmation_request,
            visibility=visibility,
            preferred_locale=preferred_locale,
        )
        if confirmation_message:
            return confirmation_message

    failure_message = str(visibility.get("failure_message", "") or "").strip()
    if failure_message:
        return _spoken_failure_text(
            failure_message,
            preferred_locale=preferred_locale,
            next_step_hint=str(visibility.get("next_step_hint", "") or "").strip(),
        )

    completion_result = str(visibility.get("completion_result", "") or "").strip()
    if completion_result and not _looks_like_internal_completion(completion_result):
        return _sanitize_spoken_completion(completion_result, preferred_locale=preferred_locale)

    command_summary = str(visibility.get("command_summary", "") or "").strip()
    spoken_command = _spoken_command_summary(command_summary, preferred_locale=preferred_locale)
    if spoken_command:
        return spoken_command

    if completion_result:
        return _sanitize_spoken_completion(completion_result, preferred_locale=preferred_locale)

    return None


def _spoken_confirmation_message(
    confirmation_request: dict[str, Any],
    *,
    visibility: dict[str, Any],
    preferred_locale: str | None = None,
) -> str | None:
    message = str(confirmation_request.get("message", "") or "").strip()
    affected_targets = [str(target).strip() for target in list(confirmation_request.get("affected_targets", []) or [])]
    affected_targets = [target for target in affected_targets if target]
    command_summary = str(visibility.get("command_summary", "") or "").strip()
    intent, summary_targets = _parse_command_summary(command_summary)
    targets = affected_targets or summary_targets
    template = _spoken_confirmation_template(intent, *targets, message, preferred_locale=preferred_locale)
    if template and targets:
        return template.format(targets=", ".join(_spoken_target(target) for target in targets))
    regex_rendered = _spoken_confirmation_message_from_text(message, preferred_locale=preferred_locale)
    if regex_rendered:
        return regex_rendered
    return message or None


def _spoken_command_summary(command_summary: str, *, preferred_locale: str | None = None) -> str | None:
    intent, targets = _parse_command_summary(command_summary)
    template = _spoken_intent_template(intent, *targets, preferred_locale=preferred_locale)
    if not template or not targets:
        return None
    return template.format(targets=", ".join(_spoken_target(target) for target in targets))


def _sanitize_spoken_completion(completion_result: str, *, preferred_locale: str | None = None) -> str:
    normalized = _sanitize_spoken_surface(completion_result)
    if not normalized:
        return ""

    if prefers_russian_locale(preferred_locale, normalized):
        localized = _localized_russian_completion_text(normalized)
        if localized:
            return _sanitize_spoken_surface(localized)

    if normalized.lower().startswith("opened file:"):
        opened_path = normalized.split(":", maxsplit=1)[1].strip()
        label = _spoken_target(opened_path)
        if label:
            if prefers_russian_locale(preferred_locale, normalized):
                return f"Открыл файл {label}."
            return f"Opened file {label}."

    return _sanitize_spoken_surface(normalized)


def _looks_like_internal_completion(text: str) -> bool:
    return bool(_INTERNAL_COMPLETION_RE.match(" ".join(str(text or "").split()).strip()))


def _parse_command_summary(command_summary: str) -> tuple[str, list[str]]:
    if not command_summary:
        return "", []

    intent, separator, target_blob = command_summary.partition(":")
    targets = [part.strip() for part in target_blob.split(",")] if separator else []
    return intent.strip(), [target for target in targets if target]


def _spoken_target(target: str) -> str:
    candidate = str(target or "").strip()
    if not candidate:
        return ""
    if "/" in candidate:
        return Path(candidate).name or candidate
    return candidate


def _warning_prefix(preferred_locale: str | None, *parts: str) -> str:
    if prefers_russian_locale(preferred_locale, *parts):
        return "Предупреждение"
    return "Warning"


def _spoken_confirmation_message_from_text(message: str, *, preferred_locale: str | None = None) -> str | None:
    match = _APPROVE_CONFIRMATION_RE.match(str(message or "").strip())
    if match is None:
        return None

    intent = str(match.group("intent") or "").strip().lower()
    raw_targets = str(match.group("targets") or "").strip()
    targets = [part.strip() for part in raw_targets.split(",") if part.strip()]
    template = _spoken_confirmation_template(intent, *targets, message, preferred_locale=preferred_locale)
    if not template or not targets:
        return None
    return template.format(targets=", ".join(_spoken_target(target) for target in targets))


def _spoken_clarification_text(message: str, *, preferred_locale: str | None = None) -> str:
    normalized = _sanitize_spoken_surface(message)
    if not normalized:
        return normalized

    if not prefers_russian_locale(preferred_locale, normalized):
        return _sanitize_spoken_surface(_localized_english_clarification_text(normalized))

    return _sanitize_spoken_surface(_localized_russian_clarification_text(normalized))


def _localized_russian_clarification_text(normalized: str) -> str:
    exact = _RUSSIAN_CLARIFICATION_EXACT_MAP.get(normalized)
    if exact:
        return exact

    mixed_match = _MIXED_INTERACTION_CLARIFICATION_RE.match(normalized)
    if mixed_match is not None:
        target = str(mixed_match.group("target") or "").strip()
        if target:
            return f"Сначала ответить или открыть {target}?"

    target_with_options = _TARGET_NOT_FOUND_WITH_OPTIONS_RE.match(normalized)
    if target_with_options is not None:
        target = str(target_with_options.group("target") or "").strip()
        options = str(target_with_options.group("options") or "").strip()
        return f"Не нашёл {_spoken_target(target)}. Ты имел в виду {_spoken_option_list(options)}?"

    target_with_followup = _TARGET_NOT_FOUND_WITH_TARGET_RE.match(normalized)
    if target_with_followup is not None:
        target = str(target_with_followup.group("target") or "").strip()
        return f"Не нашёл {_spoken_target(target)}. Какую цель использовать?"

    generic_options = _TARGET_NOT_FOUND_GENERIC_OPTIONS_RE.match(normalized)
    if generic_options is not None:
        options = str(generic_options.group("options") or "").strip()
        return f"Не нашёл эту цель. Ты имел в виду {_spoken_option_list(options)}?"

    if normalized == "I could not find the target; which one should I use?":
        return "Не нашёл цель. Какую использовать?"

    return normalized


def _localized_english_clarification_text(normalized: str) -> str:
    exact = _ENGLISH_CLARIFICATION_EXACT_MAP.get(normalized)
    if exact:
        return exact

    target_with_options = _TARGET_NOT_FOUND_WITH_OPTIONS_RE.match(normalized)
    if target_with_options is not None:
        target = str(target_with_options.group("target") or "").strip()
        options = str(target_with_options.group("options") or "").strip()
        return f"I couldn't find {_spoken_target(target)}. Did you mean {_spoken_option_list(options, conjunction='or')}?"

    target_with_followup = _TARGET_NOT_FOUND_WITH_TARGET_RE.match(normalized)
    if target_with_followup is not None:
        target = str(target_with_followup.group("target") or "").strip()
        return f"I couldn't find {_spoken_target(target)}. Which target should I use?"

    generic_options = _TARGET_NOT_FOUND_GENERIC_OPTIONS_RE.match(normalized)
    if generic_options is not None:
        options = str(generic_options.group("options") or "").strip()
        return f"I couldn't find that target. Did you mean {_spoken_option_list(options, conjunction='or')}?"

    if normalized == "I could not find the target; which one should I use?":
        return "I couldn't find the target. Which one should I use?"

    return normalized


def _spoken_failure_text(
    message: str,
    *,
    preferred_locale: str | None = None,
    next_step_hint: str | None = None,
) -> str:
    normalized = _sanitize_spoken_surface(message)
    if not normalized:
        return ""

    localized = normalized
    if prefers_russian_locale(preferred_locale, normalized):
        localized = _sanitize_spoken_surface(_localized_russian_failure_text(normalized))

    spoken_hint = _spoken_hint_text(next_step_hint, preferred_locale=preferred_locale)
    if spoken_hint and not _messages_overlap(localized, spoken_hint):
        return _sanitize_spoken_surface(_join_sentences(localized, spoken_hint))
    return _sanitize_spoken_surface(localized)


def _spoken_question_text(text: str, *, preferred_locale: str | None = None) -> str:
    normalized = " ".join(str(text or "").split()).strip()
    if not normalized:
        return normalized
    refusal_override = _spoken_question_refusal_text(normalized, preferred_locale=preferred_locale)
    if refusal_override:
        return _sanitize_spoken_question_surface(refusal_override)
    if not prefers_russian_locale(preferred_locale, normalized):
        return _sanitize_spoken_question_surface(normalized)
    return _sanitize_spoken_question_surface(_RUSSIAN_QUESTION_TEXT_EXACT_MAP.get(normalized, normalized))


def _spoken_question_warning(warning: str, *, preferred_locale: str | None = None) -> str:
    normalized = " ".join(str(warning or "").split()).strip()
    if not normalized or not prefers_russian_locale(preferred_locale, normalized):
        return _sanitize_spoken_question_surface(normalized)
    return _sanitize_spoken_question_surface(_RUSSIAN_QUESTION_WARNING_EXACT_MAP.get(normalized, normalized))


def _spoken_question_failure(message: str, *, preferred_locale: str | None = None) -> str:
    normalized = " ".join(str(message or "").split()).strip()
    if not normalized:
        return normalized

    failure_code = _question_failure_code(normalized)
    if failure_code:
        if prefers_russian_locale(preferred_locale, normalized):
            return _sanitize_spoken_question_surface({
                "UNSUPPORTED_QUESTION": "Я не могу ответить на этот вопрос в текущем режиме.",
                "INSUFFICIENT_CONTEXT": "Мне не хватает недавнего контекста, чтобы ответить на это уточнение.",
            }.get(failure_code, normalized))
        return _sanitize_spoken_question_surface({
            "UNSUPPORTED_QUESTION": "I can't answer that in the current mode.",
            "INSUFFICIENT_CONTEXT": "I need more recent context for that follow-up.",
        }.get(failure_code, normalized))

    if not prefers_russian_locale(preferred_locale, normalized):
        return _sanitize_spoken_question_surface(normalized)
    return _sanitize_spoken_question_surface(_RUSSIAN_QUESTION_FAILURE_EXACT_MAP.get(normalized, normalized))


def _spoken_question_answer_text(answer_text: str, *, preferred_locale: str | None = None) -> str:
    normalized = " ".join(str(answer_text or "").split()).strip()
    if not normalized:
        return ""

    refusal_override = _spoken_question_refusal_text(normalized, preferred_locale=preferred_locale)
    if refusal_override:
        return refusal_override
    return _spoken_question_text(_answer_summary(normalized), preferred_locale=preferred_locale)


def _spoken_question_refusal_text(text: str, *, preferred_locale: str | None = None) -> str | None:
    normalized = " ".join(str(text or "").split()).strip()
    if not normalized:
        return None

    if _looks_like_self_harm_refusal(normalized):
        if prefers_russian_locale(preferred_locale, normalized):
            return "Я не могу помочь с этим. Если тебе угрожает немедленная опасность, позвони или напиши на 988 прямо сейчас."
        return "I can't help with that. If you're in immediate danger, call or text 988 now."

    if _QUESTION_REFUSAL_RE.search(normalized) is not None:
        if prefers_russian_locale(preferred_locale, normalized):
            return "Я не могу помочь с этой просьбой."
        return "I can't help with that request."

    return None


def _looks_like_self_harm_refusal(text: str) -> bool:
    normalized = " ".join(str(text or "").split()).strip()
    if not normalized:
        return False
    if _QUESTION_SELF_HARM_REFUSAL_RE.search(normalized) is not None:
        return True
    return "988" in normalized and "self-harm" in normalized.lower()


def _question_failure_code(message: str) -> str:
    code, separator, _detail = str(message or "").partition(":")
    normalized_code = code.strip()
    if not separator:
        return ""
    if normalized_code in {"UNSUPPORTED_QUESTION", "INSUFFICIENT_CONTEXT"}:
        return normalized_code
    return ""


def _sanitize_spoken_surface(text: str) -> str:
    normalized = " ".join(str(text or "").split()).strip()
    if not normalized:
        return normalized
    without_debug = _trim_internal_debug_suffix(normalized)
    without_markup = _SPOKEN_MARKDOWN_RE.sub("", without_debug)
    with_short_urls = _URL_RE.sub(
        lambda match: _spoken_url_target(str(match.group("url") or "").strip()),
        without_markup,
    )
    with_short_absolute_paths = _ABSOLUTE_PATH_RE.sub(
        lambda match: _spoken_target(str(match.group("path") or "").strip()),
        with_short_urls,
    )
    return _RELATIVE_PATH_RE.sub(
        lambda match: _spoken_relative_path_target(match, with_short_absolute_paths),
        with_short_absolute_paths,
    )


def _sanitize_spoken_question_surface(text: str) -> str:
    return _sanitize_spoken_surface(text)


def _spoken_relative_path_target(match: re.Match[str], source_text: str) -> str:
    path = str(match.group("path") or "").strip()
    if not path:
        return path

    start = match.start()
    prefix = source_text[max(0, start - 8) : start].lower()
    if prefix.endswith("http://") or prefix.endswith("https://"):
        return path
    return _spoken_target(path)


def _spoken_url_target(url: str) -> str:
    candidate = str(url or "").strip()
    if not candidate:
        return candidate

    trailing = ""
    while candidate and candidate[-1] in ".,;:!?":
        trailing = candidate[-1] + trailing
        candidate = candidate[:-1]

    parsed = urlsplit(candidate)
    host = parsed.netloc or candidate
    return f"{host}{trailing}"


def _trim_internal_debug_suffix(text: str) -> str:
    normalized = " ".join(str(text or "").split()).strip()
    if not normalized:
        return normalized

    cutoff = len(normalized)
    for marker in _INTERNAL_DEBUG_MARKERS:
        position = normalized.find(marker)
        if position == 0:
            return ""
        if position > 0:
            cutoff = min(cutoff, position)

    if cutoff == len(normalized):
        return normalized
    return normalized[:cutoff].rstrip(" ,;:-")


def _localized_russian_failure_text(message: str) -> str:
    exact = _RUSSIAN_FAILURE_EXACT_MAP.get(message)
    if exact:
        return exact

    list_windows_match = _LIST_WINDOWS_FAILURE_RE.match(message.rstrip("."))
    if list_windows_match is not None:
        detail = str(list_windows_match.group("detail") or "").strip()
        if detail:
            return f"Не удалось показать окна: {detail}"
        return "Не удалось показать окна."

    open_with_target_detail = _OPEN_AFTER_SEARCH_WITH_TARGET_DETAIL_RE.match(message)
    if open_with_target_detail is not None:
        target = str(open_with_target_detail.group("target") or "").strip()
        detail = str(open_with_target_detail.group("detail") or "").strip()
        if target and detail:
            return f"Нашёл подходящий файл, но не смог открыть {_spoken_target(target)}. {detail}"

    open_with_target = _OPEN_AFTER_SEARCH_WITH_TARGET_RE.match(message)
    if open_with_target is not None:
        target = str(open_with_target.group("target") or "").strip()
        if target:
            return f"Нашёл подходящий файл, но не смог открыть {_spoken_target(target)}."

    open_with_detail = _OPEN_AFTER_SEARCH_WITH_DETAIL_RE.match(message)
    if open_with_detail is not None:
        detail = str(open_with_detail.group("detail") or "").strip()
        if detail:
            return f"Нашёл подходящий файл, но не смог его открыть. {detail}"
        return "Нашёл подходящий файл, но не смог его открыть."

    search_empty_match = _SEARCH_OPEN_EMPTY_RE.match(message)
    if search_empty_match is not None:
        detail = str(search_empty_match.group("detail") or "").strip()
        if detail:
            return f"Поиск не нашёл файл для открытия. {detail}"
        return "Поиск не нашёл файл для открытия."

    return message


def _localized_russian_completion_text(message: str) -> str:
    exact = _RUSSIAN_FAILURE_EXACT_MAP.get(message)
    if exact:
        return exact
    if message == "Command completed.":
        return "Команда выполнена."

    if message.lower().startswith("opened file:"):
        opened_path = message.split(":", maxsplit=1)[1].strip()
        label = _spoken_target(opened_path)
        if label:
            return f"Открыл файл {label}."

    search_found = _SEARCH_FOUND_RE.match(message)
    if search_found is not None:
        count = int(search_found.group("count"))
        scope = _normalized_scope_suffix(search_found.group("scope"))
        return f"Нашёл {count} {_russian_count_form(count, 'совпадение', 'совпадения', 'совпадений')}{scope}."

    search_found_and_open = _SEARCH_FOUND_AND_OPEN_RE.match(message)
    if search_found_and_open is not None:
        count = int(search_found_and_open.group("count"))
        scope = _normalized_scope_suffix(search_found_and_open.group("scope"))
        return (
            f"Нашёл {count} {_russian_count_form(count, 'совпадение', 'совпадения', 'совпадений')}"
            f"{scope} и открыл файл."
        )

    search_completed = _SEARCH_COMPLETED_RE.match(message)
    if search_completed is not None:
        scope = _normalized_scope_suffix(search_completed.group("scope"))
        return f"Поиск завершён{scope}."

    if _SEARCH_COMPLETED_AND_OPEN_RE.match(message) is not None:
        return "Поиск завершён, файл открыт."

    visible_windows = _VISIBLE_WINDOWS_RE.match(message)
    if visible_windows is not None:
        count = int(visible_windows.group("count"))
        return f"Сейчас видно {count} {_russian_count_form(count, 'окно', 'окна', 'окон')}."

    filtered_windows = _FILTERED_WINDOWS_RE.match(message)
    if filtered_windows is not None:
        count = int(filtered_windows.group("count"))
        filter_name = str(filtered_windows.group("filter") or "").strip()
        if filter_name:
            return f"Сейчас видно {count} {_russian_count_form(count, 'окно', 'окна', 'окон')} {filter_name}."

    filtered_windows_none = _NO_VISIBLE_FILTERED_WINDOWS_RE.match(message)
    if filtered_windows_none is not None:
        filter_name = str(filtered_windows_none.group("filter") or "").strip()
        if filter_name:
            return f"Окон {filter_name} не найдено."

    if message == "No visible windows found.":
        return "Видимых окон не найдено."

    return message


def _spoken_hint_text(hint: str | None, *, preferred_locale: str | None = None) -> str:
    normalized = _sanitize_spoken_surface(hint)
    if not normalized:
        return ""
    if prefers_russian_locale(preferred_locale, normalized):
        return _RUSSIAN_HINT_EXACT_MAP.get(normalized, "")
    return _ENGLISH_HINT_EXACT_MAP.get(normalized, "")


def _messages_overlap(primary: str, secondary: str) -> bool:
    primary_text = " ".join(str(primary or "").lower().split()).strip()
    secondary_text = " ".join(str(secondary or "").lower().split()).strip()
    return bool(primary_text and secondary_text and (secondary_text in primary_text or primary_text in secondary_text))


def _join_sentences(primary: str, secondary: str) -> str:
    first = str(primary or "").strip()
    second = str(secondary or "").strip()
    if not first:
        return second
    if not second:
        return first
    if first[-1] not in ".!?":
        first = f"{first}."
    return f"{first} {second}"


def _russian_count_form(count: int, one: str, few: str, many: str) -> str:
    normalized_count = abs(int(count))
    mod10 = normalized_count % 10
    mod100 = normalized_count % 100
    if mod10 == 1 and mod100 != 11:
        return one
    if 2 <= mod10 <= 4 and not 12 <= mod100 <= 14:
        return few
    return many


def _normalized_scope_suffix(scope: str | None) -> str:
    scope_text = str(scope or "").strip()
    if not scope_text:
        return ""
    if scope_text.lower().startswith("in "):
        return f" в {scope_text[3:].strip()}"
    return scope_text


def _spoken_option_list(options: str, *, conjunction: str | None = None) -> str:
    parts = [part.strip() for part in str(options or "").split(",") if part.strip()]
    if not parts:
        return str(options or "").strip()
    spoken_parts = [_spoken_target(part) for part in parts]
    if conjunction and len(spoken_parts) >= 2:
        if len(spoken_parts) == 2:
            return f"{spoken_parts[0]} {conjunction} {spoken_parts[1]}"
        return f"{', '.join(spoken_parts[:-1])}, {conjunction} {spoken_parts[-1]}"
    return ", ".join(spoken_parts)

def _spoken_intent_template(intent: str, *parts: str, preferred_locale: str | None = None) -> str | None:
    language = "ru" if prefers_russian_locale(preferred_locale, *parts) else "en"
    return _SPOKEN_INTENT_TEMPLATES.get(language, {}).get(intent or "")


def _spoken_confirmation_template(intent: str, *parts: str, preferred_locale: str | None = None) -> str | None:
    language = "ru" if prefers_russian_locale(preferred_locale, *parts) else "en"
    return _SPOKEN_CONFIRMATION_TEMPLATES.get(language, {}).get(intent or "")


def _question_summary(*, result: object, visibility: dict[str, Any]) -> str:
    summary = str(visibility.get("answer_summary", "") or "").strip()
    if summary:
        return summary
    answer_text = str(visibility.get("answer_text", "") or "").strip()
    if not answer_text:
        answer_result = getattr(result, "answer_result", None)
        answer_text = str(getattr(answer_result, "answer_text", "") or "").strip()
    return _answer_summary(answer_text)


def _spoken_utterance_locale(message: str, *, preferred_locale: str | None = None) -> str:
    locale_text = str(preferred_locale or "").strip().lower()
    if locale_text.startswith("ru"):
        return "ru-RU"
    return detect_spoken_locale(message)


def _answer_summary(answer_text: str) -> str:
    normalized = " ".join(str(answer_text or "").split()).strip()
    if not normalized:
        return ""
    for punctuation in (". ", "! ", "? "):
        split_index = normalized.find(punctuation)
        if 0 < split_index <= 110:
            return normalized[: split_index + 1].strip()
    if len(normalized) <= 110:
        return normalized
    clipped = normalized[:107].rsplit(" ", 1)[0].strip() or normalized[:107].strip()
    return f"{clipped}..."


def _interaction_visibility(result: object) -> dict[str, Any]:
    result_visibility = dict(getattr(result, "visibility", {}) or {})
    if result_visibility:
        return result_visibility

    runtime_result = getattr(result, "runtime_result", None)
    runtime_visibility = dict(getattr(runtime_result, "visibility", {}) or {})
    if runtime_visibility:
        return runtime_visibility

    return {}


def _interaction_mode_value(result: object) -> str:
    return str(getattr(getattr(result, "interaction_mode", ""), "value", getattr(result, "interaction_mode", ""))).strip()


def _interaction_error_message(error: object) -> str:
    code = str(getattr(getattr(error, "code", ""), "value", getattr(error, "code", ""))).strip()
    message = str(getattr(error, "message", "")).strip()
    if code and message:
        return f"{code}: {message}"
    return message or code
