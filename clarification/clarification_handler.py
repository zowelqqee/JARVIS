"""Deterministic clarification handling for JARVIS MVP."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from protocols.registry import resolve_protocol_reference
from user_language import prefers_russian_text

if TYPE_CHECKING:
    from types.clarification_request import ClarificationRequest
    from types.command import Command
    from types.jarvis_error import JarvisError


_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from clarification_request import ClarificationRequest  # type: ignore  # noqa: E402
from command import Command  # type: ignore  # noqa: E402
from jarvis_error import ErrorCode  # type: ignore  # noqa: E402
from target import Target, TargetType  # type: ignore  # noqa: E402


def build_clarification(validation_issue: JarvisError, command: Command) -> ClarificationRequest:
    """Create one short clarification request for a blocked command."""
    code = _error_code_value(getattr(validation_issue, "code", "CLARIFICATION_REQUIRED"))
    details = _error_details(validation_issue)
    options = _extract_options(details)
    prefer_russian = _prefers_russian_command(command)

    if code == ErrorCode.LOW_CONFIDENCE.value:
        message = (
            "Не уверен, что ты имел в виду. Переформулируй команду."
            if prefer_russian
            else "I am not sure what you meant; can you rephrase the command?"
        )
        options = None
    elif code == ErrorCode.MISSING_PARAMETER.value:
        message = _missing_parameter_message(command, prefer_russian=prefer_russian)
        options = None
    elif code == ErrorCode.TARGET_NOT_FOUND.value:
        message = _target_not_found_message(command, options, prefer_russian=prefer_russian)
    elif code == ErrorCode.MULTIPLE_MATCHES.value:
        message = _multiple_matches_message(options, prefer_russian=prefer_russian)
    elif code == ErrorCode.FOLLOWUP_REFERENCE_UNCLEAR.value:
        message = (
            "Какую предыдущую цель ты имеешь в виду?"
            if prefer_russian
            else "Which previous target are you referring to?"
        )
    else:
        message = "Уточни действие и цель." if prefer_russian else "Please clarify the action and target."
        if not options:
            options = None

    return ClarificationRequest(message=message, code=code, options=options)


def apply_clarification(command: Command, user_reply: str) -> Command:
    """Patch only blocked command fields from a user clarification reply."""
    reply = _normalize_reply(user_reply)
    patched_command = _clone_command(command)
    if not reply:
        return patched_command

    patched = False
    patched |= _apply_protocol_reference(patched_command, reply)
    patched |= _apply_ambiguous_choice(patched_command, reply)
    patched |= _apply_missing_parameter(patched_command, reply)
    patched |= _apply_missing_target(patched_command, reply)

    if not patched and float(getattr(patched_command, "confidence", 0.0)) < 0.6:
        patched_command.raw_input = reply

    return patched_command


def _normalize_reply(user_reply: str) -> str:
    if not isinstance(user_reply, str):
        return ""
    return re.sub(r"\s+", " ", user_reply).strip()


def _clone_command(command: Command) -> Command:
    return Command(
        raw_input=str(getattr(command, "raw_input", "")),
        intent=getattr(command, "intent"),
        targets=[_clone_target(target) for target in list(getattr(command, "targets", []) or [])],
        parameters=dict(getattr(command, "parameters", {}) or {}),
        confidence=float(getattr(command, "confidence", 0.0)),
        requires_confirmation=bool(getattr(command, "requires_confirmation", False)),
        execution_steps=list(getattr(command, "execution_steps", []) or []),
        status_message=str(getattr(command, "status_message", "")),
    )


def _clone_target(target: Any) -> Target:
    return Target(
        type=_coerce_target_type(_target_type_value(getattr(target, "type", "unknown"))),
        name=str(getattr(target, "name", "")),
        path=getattr(target, "path", None),
        metadata=dict(getattr(target, "metadata", {}) or {}) or None,
    )


def _apply_ambiguous_choice(command: Command, reply: str) -> bool:
    for target in command.targets:
        metadata = dict(target.metadata or {})
        if not metadata.get("ambiguous"):
            continue

        candidates = [str(item).strip() for item in metadata.get("candidates", []) if str(item).strip()]
        selected = _select_candidate(reply, candidates)
        if selected is None:
            return False

        target.name = selected
        if _target_type_value(target.type) == TargetType.UNKNOWN.value:
            target.type = _expected_target_type(_intent_value(command.intent))
        metadata.pop("ambiguous", None)
        metadata.pop("candidates", None)
        target.metadata = metadata or None
        return True
    return False


def _apply_protocol_reference(command: Command, reply: str) -> bool:
    if _intent_value(command.intent) != "run_protocol":
        return False
    matches = resolve_protocol_reference(reply)
    if len(matches) != 1:
        return False
    match = matches[0]
    command.parameters["protocol_id"] = str(getattr(match.definition, "id", "") or "").strip()
    command.parameters["protocol_display_name"] = str(getattr(match.definition, "title", "") or "").strip()
    command.parameters.pop("protocol_ambiguous", None)
    command.parameters.pop("protocol_candidates", None)
    command.parameters["requested_protocol_name"] = reply
    command.targets = []
    return True


def _select_candidate(reply: str, candidates: list[str]) -> str | None:
    if not candidates:
        return None

    if reply.isdigit():
        index = int(reply) - 1
        if 0 <= index < len(candidates):
            return candidates[index]

    lowered = reply.lower()
    exact = [candidate for candidate in candidates if candidate.lower() == lowered]
    if len(exact) == 1:
        return exact[0]

    prefix = [candidate for candidate in candidates if candidate.lower().startswith(lowered)]
    if len(prefix) == 1:
        return prefix[0]

    return None


def _apply_missing_parameter(command: Command, reply: str) -> bool:
    intent = _intent_value(command.intent)
    parameters = command.parameters

    if intent == "search_local" and not str(parameters.get("query", "")).strip():
        parameters["query"] = reply
        return True

    if intent == "open_website" and not str(parameters.get("url", "")).strip():
        url = _normalize_url(reply)
        if url:
            parameters["url"] = url
            return True

    if intent == "prepare_workspace" and not str(parameters.get("workspace", "")).strip():
        parameters["workspace"] = reply
        return True

    if intent == "run_protocol" and not str(parameters.get("protocol_id", "")).strip():
        parameters["requested_protocol_name"] = reply
        return True

    if intent == "confirm" and not str(parameters.get("response", "")).strip():
        response = _confirmation_response(reply)
        if response:
            parameters["response"] = response
            return True

    return False


def _apply_missing_target(command: Command, reply: str) -> bool:
    for target in command.targets:
        unresolved = _target_type_value(target.type) == TargetType.UNKNOWN.value or (
            not str(target.name).strip() and not str(target.path or "").strip()
        )
        if not unresolved:
            continue

        normalized_path = reply if _is_path_like(reply) else None
        target.name = Path(reply).name if normalized_path else reply
        target.path = normalized_path if normalized_path else target.path
        if _target_type_value(target.type) == TargetType.UNKNOWN.value:
            target.type = _expected_target_type(_intent_value(command.intent))
        if _target_type_value(target.type) == TargetType.BROWSER.value:
            url = _normalize_url(reply)
            if url:
                target.metadata = {"url": url}
        return True

    if command.targets:
        return False

    expected_type = _expected_target_type(_intent_value(command.intent))
    normalized_path = reply if _is_path_like(reply) else None
    command.targets.append(
        Target(
            type=expected_type,
            name=Path(reply).name if normalized_path else reply,
            path=normalized_path,
            metadata={"url": _normalize_url(reply)} if expected_type == TargetType.BROWSER and _normalize_url(reply) else None,
        )
    )
    return True


def _missing_parameter_message(command: Command, *, prefer_russian: bool) -> str:
    intent = _intent_value(command.intent)
    if intent == "search_local":
        return "Что мне искать?" if prefer_russian else "What should I search for?"
    if intent == "open_website":
        return "Какой адрес сайта открыть?" if prefer_russian else "Which website URL should I open?"
    if intent == "prepare_workspace":
        return "Какое рабочее пространство подготовить?" if prefer_russian else "What workspace should I prepare?"
    if intent == "run_protocol":
        return "Какой протокол запустить?" if prefer_russian else "Which protocol should I run?"
    if intent == "confirm":
        return "Скажи: подтвердить или отменить." if prefer_russian else "Please reply with confirm or cancel."
    return "Какое значение использовать, чтобы продолжить?" if prefer_russian else "Which value should I use to continue?"


def _target_not_found_message(command: Command, options: list[str] | None, *, prefer_russian: bool) -> str:
    if command.targets:
        missing_target = str(command.targets[0].name).strip() or ("эту цель" if prefer_russian else "that target")
        if options:
            if prefer_russian:
                return f"Не могу найти {missing_target}; ты имел в виду {', '.join(options)}?"
            return f"I could not find {missing_target}; did you mean {', '.join(options)}?"
        if prefer_russian:
            return f"Не могу найти {missing_target}; какую цель использовать?"
        return f"I could not find {missing_target}; which target should I use?"
    if options:
        if prefer_russian:
            return f"Не могу найти эту цель; ты имел в виду {', '.join(options)}?"
        return f"I could not find that target; did you mean {', '.join(options)}?"
    return "Не могу найти цель; какую использовать?" if prefer_russian else "I could not find the target; which one should I use?"


def _multiple_matches_message(options: list[str] | None, *, prefer_russian: bool) -> str:
    if options:
        return (
            f"Какой вариант ты имеешь в виду: {', '.join(options)}?"
            if prefer_russian
            else f"Which one do you mean: {', '.join(options)}?"
        )
    return "Нашёл несколько вариантов; какой использовать?" if prefer_russian else "I found multiple matches; which one should I use?"


def _prefers_russian_command(command: Command) -> bool:
    return prefers_russian_text(str(getattr(command, "raw_input", "") or ""))


def _error_details(issue: JarvisError) -> dict[str, Any]:
    details = getattr(issue, "details", None)
    if isinstance(details, dict):
        return details
    return {}


def _extract_options(details: dict[str, Any]) -> list[str] | None:
    for key in ("options", "candidates", "matches", "suggestions", "available_targets"):
        raw = details.get(key)
        if not isinstance(raw, list):
            continue
        parsed: list[str] = []
        for item in raw:
            if isinstance(item, str) and item.strip():
                parsed.append(item.strip())
            elif isinstance(item, dict):
                name = str(item.get("name", "") or item.get("label", "")).strip()
                if name:
                    parsed.append(name)
        if parsed:
            return _dedupe(parsed)
    return None


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        lowered = value.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(value)
    return deduped


def _error_code_value(code: Any) -> str:
    return str(getattr(code, "value", code))


def _intent_value(intent: Any) -> str:
    return str(getattr(intent, "value", intent))


def _target_type_value(target_type: Any) -> str:
    return str(getattr(target_type, "value", target_type))


def _coerce_target_type(target_type: str) -> TargetType:
    for item in TargetType:
        if item.value == target_type:
            return item
    return TargetType.UNKNOWN


def _expected_target_type(intent: str) -> TargetType:
    mapping = {
        "open_app": TargetType.APPLICATION,
        "close_app": TargetType.APPLICATION,
        "open_file": TargetType.FILE,
        "open_folder": TargetType.FOLDER,
        "open_website": TargetType.BROWSER,
        "focus_window": TargetType.WINDOW,
        "close_window": TargetType.WINDOW,
        "list_windows": TargetType.WINDOW,
        "search_local": TargetType.FOLDER,
    }
    return mapping.get(intent, TargetType.UNKNOWN)


def _normalize_url(value: str) -> str | None:
    text = value.strip()
    if re.fullmatch(r"https?://\S+", text, flags=re.IGNORECASE):
        return text
    if re.fullmatch(r"www\.\S+", text, flags=re.IGNORECASE):
        return f"https://{text}"
    return None


def _confirmation_response(value: str) -> str | None:
    lowered = value.strip().lower()
    if lowered in {"yes", "confirm", "ok", "okay", "approve", "approved"}:
        return "approved"
    if lowered in {"cancel", "no", "deny", "denied", "stop"}:
        return "denied"
    return None


def _is_path_like(value: str) -> bool:
    return value.startswith(("/", "~/", "./", "../")) or ("/" in value and " " not in value)
