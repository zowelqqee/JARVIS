"""Deterministic command parser for JARVIS MVP."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from input.adapter import normalize_input

if TYPE_CHECKING:
    from context.session_context import SessionContext
    from types.command import Command


_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from command import Command, IntentType  # type: ignore  # noqa: E402
from target import Target, TargetType  # type: ignore  # noqa: E402

_CONFIRM_APPROVE = {
    "yes",
    "y",
    "yeah",
    "yep",
    "ok",
    "okay",
    "confirm",
    "approved",
    "approve",
    "continue",
    "go ahead",
    "да",
    "подтвердить",
    "подтверждаю",
}
_CONFIRM_DENY = {
    "cancel",
    "stop",
    "no",
    "nope",
    "deny",
    "denied",
    "нет",
    "отмена",
    "отменить",
    "отмени",
}
_CLARIFY_PHRASES = {"which one", "which one?", "what do you mean", "what?", "which?"}
_OPEN_VERBS = ("open", "launch", "start", "reopen", "run")
_FOLLOW_UP_PREFIX = re.compile(r"^(also|now)\s+", flags=re.IGNORECASE)
_LIST_WINDOWS_PATTERN = re.compile(r"^(list|show)( all)? windows$", flags=re.IGNORECASE)
_LIST_OPEN_WINDOWS_PATTERN = re.compile(r"^(list|show)\s+open\s+windows$", flags=re.IGNORECASE)
_LIST_WINDOWS_FOR_PATTERN = re.compile(r"^(?:list|show)(?:\s+open)?\s+windows\s+for\s+(.+)$", flags=re.IGNORECASE)
_LIST_FILTERED_WINDOWS_PATTERN = re.compile(r"^(?:list|show)(?:\s+open)?\s+(.+?)\s+windows$", flags=re.IGNORECASE)
_WHATS_OPEN_PATTERN = re.compile(r"^(?:what(?:'s| is)|whats)\s+open$", flags=re.IGNORECASE)
_FIND_NAMED_PATTERN = re.compile(r"^find\s+files?\s+named\s+(.+)$", flags=re.IGNORECASE)
_SEARCH_SCOPE_PATTERN = re.compile(
    r"^(?:search|find)\s+(?:the\s+|my\s+)?(.+?(?:folder|directory|project|workspace|repo|repository|here))\s+for\s+(.+)$",
    flags=re.IGNORECASE,
)
_WORKSPACE_OPEN_PATTERN = re.compile(
    r"^(?:open|launch|start)\s+(?:my\s+|the\s+)?(.+?)\s+workspace$",
    flags=re.IGNORECASE,
)
_WORKSPACE_TARGETS_PATTERN = re.compile(
    r"^(?:open|launch|start)\s+(.+?)\s+for\s+(.+)$",
    flags=re.IGNORECASE,
)
_BROWSER_SUFFIX_PATTERN = re.compile(r"^(.+?)\s+in\s+browser$", flags=re.IGNORECASE)
_CODE_SUFFIX_PATTERN = re.compile(
    r"^(.+?)\s+in\s+(?:code|vs code|vscode|visual studio code)$",
    flags=re.IGNORECASE,
)
_SCOPED_OPEN_SEARCH_PATTERN = re.compile(
    r"^(?:open|find)\s+(.+?)\s+in\s+(.+)$",
    flags=re.IGNORECASE,
)
_UNSUPPORTED_WINDOW_MANAGEMENT_PATTERNS = (
    re.compile(r"^(?:close|quit)\s+everything\s+except\s+.+$", flags=re.IGNORECASE),
    re.compile(r"^keep\s+.+\s+and\s+close\s+(?:the\s+)?rest\.?$", flags=re.IGNORECASE),
    re.compile(r"^keep\s+.+\s+open\s+and\s+close\s+(?:the\s+)?rest\.?$", flags=re.IGNORECASE),
)

_APP_ALIASES = {
    "browser": "Safari",
    "web browser": "Safari",
    "safari": "Safari",
    "notes": "Notes",
    "заметки": "Notes",
    "code": "Visual Studio Code",
    "vs code": "Visual Studio Code",
    "vscode": "Visual Studio Code",
    "visual studio code": "Visual Studio Code",
    "telegram": "Telegram",
    "chrome": "Google Chrome",
    "google chrome": "Google Chrome",
    "finder": "Finder",
}

_WEBSITE_ALIASES = {
    "chatgpt": "https://chat.openai.com",
    "chatgpt website": "https://chat.openai.com",
    "github": "https://github.com",
    "github website": "https://github.com",
    "openai": "https://openai.com",
    "openai website": "https://openai.com",
}

_HOME_FOLDER_PATHS = {
    "downloads": Path.home() / "Downloads",
    "desktop": Path.home() / "Desktop",
    "documents": Path.home() / "Documents",
    "home": Path.home(),
}

_CONTEXTUAL_FOLDER_REFERENCES = {
    "same folder",
    "the same folder",
    "that folder",
    "this folder",
    "project folder",
    "workspace folder",
    "same project folder",
    "same workspace folder",
}

_CONTEXTUAL_PROJECT_REFERENCES = {
    "this project",
    "the project",
    "same project",
    "that project",
    "this workspace",
    "the workspace",
    "same workspace",
    "that workspace",
    "this repo",
    "the repo",
    "this repository",
    "the repository",
}

_CONTEXTUAL_SCOPE_REFERENCES = _CONTEXTUAL_FOLDER_REFERENCES | _CONTEXTUAL_PROJECT_REFERENCES | {"here"}
_CONTEXTUAL_FILE_REFERENCES = {
    "this file",
    "that file",
    "same file",
    "the same file",
}

_GENERIC_CONTEXT_REFERENCES = {
    "it",
    "that",
    "that one",
    "same app",
    "that app",
    "this app",
}
_SEARCH_RESULT_SINGLE_REFERENCES = {"that file", "that result", "the file", "the result"}
_SEARCH_RESULT_ORDINALS = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
}
_SEARCH_RESULT_NUMERIC_PATTERN = re.compile(
    r"^(?:the\s+)?(?:result\s+)?(\d+)(?:st|nd|rd|th)?(?:\s+(?:one|result|file))?$",
    flags=re.IGNORECASE,
)
_SEARCH_RESULT_ORDINAL_PATTERN = re.compile(
    r"^(?:the\s+)?(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)(?:\s+(?:one|result|file))?$",
    flags=re.IGNORECASE,
)

_WEB_TLDS = {"ai", "app", "co", "com", "dev", "edu", "gov", "io", "net", "org"}


def parse_command(raw_input: str, session_context: SessionContext | None) -> Command:
    """Parse normalized raw input into a preliminary Command."""
    normalized = normalize_input(raw_input)
    lowered = normalized.lower()

    intent, targets, parameters = _infer_command(normalized, lowered, session_context)
    confidence = _compute_confidence(intent, targets, parameters)

    return Command(
        raw_input=normalized,
        intent=_coerce_intent(intent),
        targets=targets,
        parameters=parameters,
        confidence=confidence,
        requires_confirmation=intent in {"close_app", "close_window"},
        execution_steps=[],
        status_message=_status_message(intent),
    )


def _infer_command(
    original_text: str,
    lowered_text: str,
    session_context: SessionContext | None,
) -> tuple[str, list[Target], dict[str, Any]]:
    confirm_intent = _parse_confirm_intent(lowered_text)
    if confirm_intent is not None:
        return "confirm", [], {"response": confirm_intent}

    if lowered_text in _CLARIFY_PHRASES or lowered_text.endswith("?"):
        return "clarify", [], {}

    unsupported_command = _parse_explicitly_unsupported_command(original_text)
    if unsupported_command is not None:
        return unsupported_command

    list_windows_command = _parse_list_windows_command(original_text, lowered_text, session_context)
    if list_windows_command is not None:
        return list_windows_command

    search_command = _parse_search_command(original_text, lowered_text, session_context)
    if search_command is not None:
        return search_command

    workspace_command = _parse_workspace_command(original_text, lowered_text, session_context)
    if workspace_command is not None:
        return workspace_command

    if lowered_text.startswith("close "):
        return _parse_close_command(original_text, session_context)

    if lowered_text.startswith("focus window") or lowered_text.startswith("switch to window"):
        return _parse_focus_window(original_text)

    use_command = _parse_use_command(original_text, lowered_text, session_context)
    if use_command is not None:
        return use_command

    open_candidate = _FOLLOW_UP_PREFIX.sub("", original_text).strip()
    if _starts_with_open_verb(open_candidate):
        return _parse_open_command(open_candidate, session_context)

    return "clarify", [_unknown_target(original_text)], {}


def _parse_explicitly_unsupported_command(original_text: str) -> tuple[str, list[Target], dict[str, Any]] | None:
    for pattern in _UNSUPPORTED_WINDOW_MANAGEMENT_PATTERNS:
        if pattern.fullmatch(original_text.strip()):
            return (
                "switch_window",
                [
                    Target(
                        type=TargetType.UNKNOWN,
                        name=original_text.strip(),
                        metadata={"unsupported_reason": "window_management_batch"},
                    )
                ],
                {"unsupported_reason": "window_management_batch"},
            )
    return None


def _parse_list_windows_command(
    original_text: str,
    lowered_text: str,
    session_context: SessionContext | None,
) -> tuple[str, list[Target], dict[str, Any]] | None:
    if _LIST_WINDOWS_PATTERN.fullmatch(lowered_text):
        return "list_windows", [], {}
    if _LIST_OPEN_WINDOWS_PATTERN.fullmatch(lowered_text):
        return "list_windows", [], {}
    if _WHATS_OPEN_PATTERN.fullmatch(lowered_text):
        return "list_windows", [], {}

    for_match = _LIST_WINDOWS_FOR_PATTERN.match(original_text)
    if for_match is not None:
        filter_target = _build_list_windows_filter_target(for_match.group(1).strip(), session_context)
        return "list_windows", [filter_target], {}

    filtered_match = _LIST_FILTERED_WINDOWS_PATTERN.match(original_text)
    if filtered_match is not None:
        filter_phrase = filtered_match.group(1).strip()
        normalized_filter = _normalize_phrase(filter_phrase)
        if normalized_filter in {"open", "all"}:
            return "list_windows", [], {}
        filter_target = _build_list_windows_filter_target(filter_phrase, session_context)
        return "list_windows", [filter_target], {}

    return None


def _build_list_windows_filter_target(filter_text: str, session_context: SessionContext | None) -> Target:
    normalized_filter = re.sub(r"\s+", " ", filter_text).strip()
    if not normalized_filter:
        return Target(type=TargetType.UNKNOWN, name=filter_text)

    alias_name = _application_alias(normalized_filter)
    if alias_name is not None:
        return Target(type=TargetType.APPLICATION, name=alias_name)

    candidate = _build_target(normalized_filter, session_context)
    candidate_type = _target_type_value(getattr(candidate, "type", "unknown"))

    if candidate_type in {"application", "window", "unknown"}:
        return candidate

    if candidate_type == "browser":
        metadata = getattr(candidate, "metadata", None) or {}
        if not metadata.get("url"):
            browser_name = str(getattr(candidate, "name", "")).strip() or _APP_ALIASES["browser"]
            return Target(type=TargetType.APPLICATION, name=browser_name)
        return Target(type=TargetType.UNKNOWN, name=normalized_filter)

    return Target(type=TargetType.UNKNOWN, name=normalized_filter)


def _parse_confirm_intent(lowered_text: str) -> str | None:
    candidate = lowered_text.strip(" \t\r\n,.!?;:")
    if candidate in _CONFIRM_APPROVE:
        return "approved"
    if candidate in _CONFIRM_DENY:
        return "denied"
    return None


def _parse_search_command(
    original_text: str,
    lowered_text: str,
    session_context: SessionContext | None,
) -> tuple[str, list[Target], dict[str, Any]] | None:
    open_search_command = _parse_open_search_command(original_text, lowered_text, session_context)
    if open_search_command is not None:
        return open_search_command

    scoped_open_match = _SCOPED_OPEN_SEARCH_PATTERN.match(original_text)
    if scoped_open_match is not None and _looks_like_search_phrase(scoped_open_match.group(1).strip()):
        scoped_area = scoped_open_match.group(2).strip()
        if not _is_code_app_phrase(scoped_area):
            parameters = _search_parameters(scoped_open_match.group(1).strip(), open_requested=lowered_text.startswith("open "))
            return "search_local", [_build_target(scoped_area, session_context)], parameters

    if lowered_text.startswith("search local for "):
        query = original_text[len("search local for ") :].strip()
        parameters = _search_parameters(query)
        scope_target = _search_scope_from_context(session_context) or Target(type=TargetType.UNKNOWN, name="current folder")
        if _target_type_value(scope_target.type) != TargetType.UNKNOWN.value:
            parameters["scope_source"] = "session_context"
        return "search_local", [scope_target], parameters

    named_match = _FIND_NAMED_PATTERN.match(original_text)
    if named_match is not None:
        parameters = _search_parameters(named_match.group(1).strip())
        scope_target = _search_scope_from_context(session_context) or Target(type=TargetType.UNKNOWN, name="current folder")
        if _target_type_value(scope_target.type) != TargetType.UNKNOWN.value:
            parameters["scope_source"] = "session_context"
        return "search_local", [scope_target], parameters

    scoped_match = _SEARCH_SCOPE_PATTERN.match(original_text)
    if scoped_match is not None:
        scope_text = scoped_match.group(1).strip()
        parameters = _search_parameters(scoped_match.group(2).strip())
        return "search_local", [_build_target(scope_text, session_context)], parameters

    if lowered_text.startswith("search for "):
        query = original_text[len("search for ") :].strip()
        parameters = _search_parameters(query)
        scope_target = _search_scope_from_context(session_context) or Target(type=TargetType.UNKNOWN, name="current folder")
        if _target_type_value(scope_target.type) != TargetType.UNKNOWN.value:
            parameters["scope_source"] = "session_context"
        return "search_local", [scope_target], parameters

    if lowered_text.startswith("find "):
        query = original_text[len("find ") :].strip()
        parameters = _search_parameters(query)
        scope_target = _search_scope_from_context(session_context) or Target(type=TargetType.UNKNOWN, name="current folder")
        if _target_type_value(scope_target.type) != TargetType.UNKNOWN.value:
            parameters["scope_source"] = "session_context"
        return "search_local", [scope_target], parameters

    return None


def _parse_open_search_command(
    original_text: str,
    lowered_text: str,
    session_context: SessionContext | None,
) -> tuple[str, list[Target], dict[str, Any]] | None:
    if not lowered_text.startswith("open "):
        return None

    payload = _strip_open_verb(original_text)
    if _CODE_SUFFIX_PATTERN.match(payload) is not None:
        return None
    if _parse_search_result_selection(payload) is not None:
        return None
    if not _looks_like_search_phrase(payload):
        return None

    scoped_match = _SCOPED_OPEN_SEARCH_PATTERN.match(original_text)
    if scoped_match is not None and _looks_like_search_phrase(scoped_match.group(1).strip()):
        parameters = _search_parameters(scoped_match.group(1).strip(), open_requested=True)
        return "search_local", [_build_target(scoped_match.group(2).strip(), session_context)], parameters

    parameters = _search_parameters(payload, open_requested=True)
    scope_target = _search_scope_from_context(session_context) or Target(type=TargetType.UNKNOWN, name="current folder")
    if _target_type_value(scope_target.type) != TargetType.UNKNOWN.value:
        parameters["scope_source"] = "session_context"
    return "search_local", [scope_target], parameters


def _parse_workspace_command(
    original_text: str,
    lowered_text: str,
    session_context: SessionContext | None,
) -> tuple[str, list[Target], dict[str, Any]] | None:
    if lowered_text.startswith("prepare workspace"):
        workspace = _extract_after_keyword(original_text, "prepare workspace for")
        return _build_workspace_command(workspace, None, session_context)

    if lowered_text.startswith("set up workspace"):
        workspace = _extract_after_keyword(original_text, "set up workspace for")
        return _build_workspace_command(workspace, None, session_context)

    workspace_open_match = _WORKSPACE_OPEN_PATTERN.match(original_text)
    if workspace_open_match is not None:
        return _build_workspace_command(workspace_open_match.group(1).strip(), None, session_context)

    workspace_targets_match = _WORKSPACE_TARGETS_PATTERN.match(original_text)
    if workspace_targets_match is not None:
        target_phrase = workspace_targets_match.group(1).strip()
        workspace = workspace_targets_match.group(2).strip()
        if _looks_like_workspace_target_list(target_phrase) or _is_workspace_target_phrase(target_phrase):
            return _build_workspace_command(workspace, target_phrase, session_context)

    return None


def _parse_use_command(
    original_text: str,
    lowered_text: str,
    session_context: SessionContext | None,
) -> tuple[str, list[Target], dict[str, Any]] | None:
    if not lowered_text.startswith("use "):
        return None

    phrase = original_text[len("use ") :].strip()
    if phrase.lower() in _CONTEXTUAL_FOLDER_REFERENCES:
        target = _target_from_context(session_context, preferred_types={"folder"})
        if target is not None:
            return "open_folder", [target], {}
        return "open_folder", [Target(type=TargetType.UNKNOWN, name=phrase)], {}

    return None


def _parse_close_command(
    original_text: str,
    session_context: SessionContext | None,
) -> tuple[str, list[Target], dict[str, Any]]:
    payload = original_text[len("close ") :].strip()
    lowered_payload = payload.lower()

    if lowered_payload in {"window", "this window", "that window"}:
        return "close_window", [Target(type=TargetType.WINDOW, name="")], {}

    if lowered_payload.endswith(" window"):
        window_name = payload[: -len(" window")].strip()
        return "close_window", [Target(type=TargetType.WINDOW, name=window_name)], {}

    if lowered_payload.startswith("window "):
        window_name = payload[len("window ") :].strip()
        return "close_window", [Target(type=TargetType.WINDOW, name=window_name)], {}

    normalized_payload = _normalize_phrase(payload)
    if normalized_payload in _GENERIC_CONTEXT_REFERENCES:
        recent_target = _recent_primary_target_from_context(session_context)
        if recent_target is None:
            return (
                "close_app",
                [_followup_unknown_target(payload, reason="missing_recent_target")],
                {},
            )
        recent_type = _target_type_value(getattr(recent_target, "type", ""))
        if recent_type == "application":
            return "close_app", [recent_target], {}
        if recent_type == "browser":
            browser_name = str(getattr(recent_target, "name", "")).strip() or _APP_ALIASES["browser"]
            return "close_app", [Target(type=TargetType.APPLICATION, name=browser_name)], {}
        if recent_type == "window":
            return "close_window", [recent_target], {}
        return (
            "close_app",
            [
                _followup_unknown_target(
                    payload,
                    reason="unsupported_close_target",
                    source_type=recent_type,
                )
            ],
            {},
        )

    return "close_app", [Target(type=TargetType.APPLICATION, name=_application_alias(payload) or payload)], {}


def _parse_focus_window(original_text: str) -> tuple[str, list[Target], dict[str, Any]]:
    if original_text.lower().startswith("focus window"):
        payload = original_text[len("focus window") :].strip()
    else:
        payload = original_text[len("switch to window") :].strip()
    return "focus_window", [Target(type=TargetType.WINDOW, name=payload)], {}


def _parse_open_command(
    action_text: str,
    session_context: SessionContext | None,
) -> tuple[str, list[Target], dict[str, Any]]:
    payload = _strip_open_verb(action_text)
    payload = re.sub(r"\btoo\b$", "", payload, flags=re.IGNORECASE).strip()

    if not payload:
        context_target = _target_from_context(session_context)
        if context_target is not None:
            return _intent_from_target_type(_target_type_value(context_target.type)), [context_target], {}
        return "open_app", [Target(type=TargetType.UNKNOWN, name="")], {}

    search_followup = _parse_search_result_open_followup(payload, session_context)
    if search_followup is not None:
        return search_followup

    code_match = _CODE_SUFFIX_PATTERN.match(payload)
    if code_match is not None:
        workspace_reference = code_match.group(1).strip()
        code_target = _build_target(workspace_reference, session_context)
        code_target_type = _target_type_value(code_target.type)
        if code_target_type == "file":
            return "open_file", [code_target], {"app": _APP_ALIASES["code"]}
        if code_target_type == "folder":
            code_app_target = Target(type=TargetType.APPLICATION, name=_APP_ALIASES["code"])
            targets = [code_app_target, code_target]
            normalized_targets = _normalize_workspace_targets(targets)
            return "prepare_workspace", normalized_targets, _workspace_parameters_from_targets(normalized_targets)

        folder_target = _resolve_folder_for_code_reference(workspace_reference, session_context)
        if folder_target is not None:
            code_target = Target(type=TargetType.APPLICATION, name=_APP_ALIASES["code"])
            targets = [code_target, folder_target]
            normalized_targets = _normalize_workspace_targets(targets)
            return "prepare_workspace", normalized_targets, _workspace_parameters_from_targets(normalized_targets)
        if _looks_like_workspace_reference(workspace_reference):
            return _build_workspace_command(workspace_reference, "code", session_context)
        if code_target_type == "unknown" and _looks_like_file_reference(workspace_reference):
            return "open_file", [code_target], {"app": _APP_ALIASES["code"]}
        if _can_fallback_to_workspace_code_reference(workspace_reference):
            return _build_workspace_command(workspace_reference, "code", session_context)

    browser_match = _BROWSER_SUFFIX_PATTERN.match(payload)
    if browser_match is not None:
        website_target = _build_website_target(browser_match.group(1).strip())
        if website_target is not None and website_target.metadata and website_target.metadata.get("url"):
            return "open_website", [website_target], {"url": website_target.metadata["url"]}
        if _looks_like_workspace_reference(browser_match.group(1).strip()):
            return _build_workspace_command(browser_match.group(1).strip(), "browser", session_context)
        return "open_website", [Target(type=TargetType.UNKNOWN, name=browser_match.group(1).strip())], {}

    if " or " in payload.lower():
        candidates = [part.strip() for part in re.split(r"\s+or\s+", payload) if part.strip()]
        ambiguous_target = Target(
            type=TargetType.UNKNOWN,
            name=payload,
            metadata={"ambiguous": True, "candidates": candidates},
        )
        return "open_app", [ambiguous_target], {}

    segments = _split_multi_open_targets(payload)
    targets = [_build_target(segment, session_context) for segment in segments]

    if len(targets) == 1:
        target = targets[0]
        target_type = _target_type_value(target.type)
        if target_type == "browser" and target.metadata and "url" in target.metadata:
            return "open_website", targets, {"url": target.metadata["url"]}
        if target_type == "unknown":
            metadata = getattr(target, "metadata", None) or {}
            expected_type = str(metadata.get("expected_type", "")).strip()
            if expected_type:
                return _intent_from_target_type(expected_type), targets, {}
        return _intent_from_target_type(target_type), targets, {}

    kind_set = {_target_type_value(target.type) for target in targets}
    if kind_set == {"application"}:
        return "open_app", targets, {}
    if kind_set == {"folder"}:
        return "open_folder", targets, {}
    if kind_set == {"file"}:
        return "open_file", targets, {}
    if len(targets) > 1 and _is_workspace_target_group(targets):
        normalized_targets = _normalize_workspace_targets(_normalize_workspace_browser_targets(targets))
        parameters = _workspace_parameters_from_targets(normalized_targets)
        return "prepare_workspace", normalized_targets, parameters

    return "clarify", targets, {}


def _parse_search_result_open_followup(
    payload: str,
    session_context: SessionContext | None,
) -> tuple[str, list[Target], dict[str, Any]] | None:
    selection = _parse_search_result_selection(payload)
    if selection is None:
        return None

    index = selection.get("index")
    recent_search = _recent_search_context(session_context)
    if recent_search is None:
        return (
            "open_file",
            [
                _search_result_unknown_target(
                    payload,
                    reason="missing_context",
                    requested_index=index,
                )
            ],
            {},
        )

    matches = list(recent_search.get("matches", []) or [])
    if selection.get("mode") == "single_reference":
        if len(matches) == 1:
            return "open_file", [_search_match_to_file_target(matches[0], payload, selected_index=1)], {}
        if not matches:
            return "open_file", [_search_result_unknown_target(payload, reason="no_results")], {}
        return (
            "open_file",
            [_search_result_unknown_target(payload, reason="ambiguous_reference", available_count=len(matches))],
            {},
        )

    if not isinstance(index, int) or index <= 0:
        return (
            "open_file",
            [_search_result_unknown_target(payload, reason="missing_parameter")],
            {},
        )

    if index > len(matches):
        return (
            "open_file",
            [
                _search_result_unknown_target(
                    payload,
                    reason="index_out_of_range",
                    requested_index=index,
                    available_count=len(matches),
                )
            ],
            {},
        )

    return "open_file", [_search_match_to_file_target(matches[index - 1], payload, selected_index=index)], {}


def _parse_search_result_selection(payload: str) -> dict[str, Any] | None:
    normalized = _normalize_phrase(payload)
    if normalized in _SEARCH_RESULT_SINGLE_REFERENCES:
        return {"mode": "single_reference"}

    numeric_match = _SEARCH_RESULT_NUMERIC_PATTERN.fullmatch(payload.strip())
    if numeric_match is not None:
        return {"mode": "index", "index": int(numeric_match.group(1))}

    ordinal_match = _SEARCH_RESULT_ORDINAL_PATTERN.fullmatch(payload.strip())
    if ordinal_match is not None:
        ordinal_index = _SEARCH_RESULT_ORDINALS.get(ordinal_match.group(1).lower())
        if ordinal_index is not None:
            return {"mode": "index", "index": ordinal_index}

    return None


def _search_match_to_file_target(match: Any, reference: str, selected_index: int) -> Target:
    if not isinstance(match, dict):
        return _search_result_unknown_target(reference, reason="missing_context", requested_index=selected_index)

    match_type = str(match.get("type", "")).strip().lower()
    match_path = str(match.get("path", "")).strip()
    match_name = str(match.get("name", "")).strip() or (Path(match_path).name if match_path else "")
    if match_type and match_type != "file":
        return _search_result_unknown_target(
            reference,
            reason="non_file_result",
            requested_index=selected_index,
            result_type=match_type,
        )
    if not match_path and not match_name:
        return _search_result_unknown_target(reference, reason="missing_context", requested_index=selected_index)

    return Target(
        type=TargetType.FILE,
        name=match_name or match_path,
        path=match_path or None,
        metadata={"search_result_index": selected_index},
    )


def _search_result_unknown_target(
    reference: str,
    reason: str,
    requested_index: int | None = None,
    available_count: int | None = None,
    result_type: str | None = None,
) -> Target:
    metadata: dict[str, Any] = {
        "followup_reference": True,
        "search_result_reference": reason,
    }
    if requested_index is not None:
        metadata["requested_index"] = requested_index
    if available_count is not None:
        metadata["available_count"] = available_count
    if result_type:
        metadata["result_type"] = result_type
    return Target(type=TargetType.UNKNOWN, name=reference, metadata=metadata)


def _recent_search_context(session_context: SessionContext | None) -> dict[str, Any] | None:
    if session_context is None:
        return None
    getter = getattr(session_context, "get_recent_search_results", None)
    if not callable(getter):
        return None
    context = getter()
    if not isinstance(context, dict):
        return None
    return context


def _resolve_folder_for_code_reference(value: str, session_context: SessionContext | None) -> Target | None:
    normalized = _normalize_phrase(value)
    if normalized in _GENERIC_CONTEXT_REFERENCES or normalized in _CONTEXTUAL_SCOPE_REFERENCES:
        folder_target = _folder_target_from_recent_context(session_context)
        if folder_target is not None:
            return folder_target
        return _followup_unknown_target(value, expected_type="folder", reason="missing_folder_context")

    if _looks_like_workspace_reference(value):
        return _build_workspace_folder_descriptor(value, session_context)

    return None


def _folder_target_from_recent_context(session_context: SessionContext | None) -> Target | None:
    folder_target = _search_scope_from_context(session_context)
    if folder_target is not None:
        return folder_target
    return _folder_from_recent_primary_target(session_context)


def _build_workspace_command(
    workspace_text: str | None,
    target_phrase: str | None,
    session_context: SessionContext | None,
) -> tuple[str, list[Target], dict[str, Any]]:
    parameters: dict[str, Any] = {}
    workspace = _normalize_workspace_descriptor(workspace_text)
    if workspace:
        parameters["workspace"] = workspace

    targets: list[Target] = []
    workspace_folder_target = _workspace_folder_target(workspace, session_context)
    if target_phrase:
        targets = [
            _build_workspace_target(
                segment,
                session_context,
                workspace_folder_target=workspace_folder_target,
            )
            for segment in _split_multi_open_targets(target_phrase)
        ]
        targets = _inject_workspace_folder_target(targets, workspace_folder_target)
    else:
        targets = _default_workspace_targets(workspace, session_context)

    targets = _normalize_workspace_targets(targets)
    if "workspace" not in parameters:
        parameters.update(_workspace_parameters_from_targets(targets))
    return "prepare_workspace", targets, parameters


def _default_workspace_targets(workspace: str | None, session_context: SessionContext | None) -> list[Target]:
    targets = [
        Target(type=TargetType.APPLICATION, name=_APP_ALIASES["code"]),
        Target(type=TargetType.APPLICATION, name=_APP_ALIASES["chrome"]),
    ]

    folder_target = _workspace_folder_target(workspace, session_context)
    if folder_target is not None:
        targets.insert(1, folder_target)

    return targets


def _workspace_folder_target(workspace: str | None, session_context: SessionContext | None) -> Target | None:
    if not workspace:
        return _search_scope_from_context(session_context)

    target = _build_workspace_folder_descriptor(workspace, session_context)
    if _target_type_value(target.type) in {"folder", "unknown"}:
        return target
    return None


def _build_workspace_target(
    segment: str,
    session_context: SessionContext | None,
    workspace_folder_target: Target | None = None,
) -> Target:
    if _normalize_phrase(segment) in {"browser", "web browser"}:
        return Target(type=TargetType.APPLICATION, name=_APP_ALIASES["chrome"])
    if workspace_folder_target is not None and _is_generic_workspace_folder_segment(segment):
        return _clone_target(workspace_folder_target)

    target = _build_target(segment, session_context)
    if workspace_folder_target is not None and _is_workspace_placeholder_target(target):
        return _clone_target(workspace_folder_target)
    if _target_type_value(target.type) == "browser" and not (target.metadata and target.metadata.get("url")):
        return Target(type=TargetType.APPLICATION, name=_APP_ALIASES["chrome"])
    return target


def _build_target(segment: str, session_context: SessionContext | None) -> Target:
    value = re.sub(r"\s+", " ", segment).strip().strip(".")
    lowered = value.lower()

    context_target = _context_target_from_reference(value, session_context)
    if context_target is not None:
        return context_target

    website_target = _build_website_target(value)
    if website_target is not None:
        return website_target

    existing_path_target = _existing_local_path_target(value)
    if existing_path_target is not None:
        return existing_path_target

    if _is_path_like(value):
        path = value
        if _looks_like_folder_path(value):
            return Target(type=TargetType.FOLDER, name=Path(value).name or value, path=path)
        return Target(type=TargetType.FILE, name=Path(value).name or value, path=path)

    home_folder_target = _home_folder_target(value)
    if home_folder_target is not None:
        return home_folder_target

    if any(noun in lowered for noun in ("folder", "directory", "project", "workspace", "repo", "repository")):
        stripped_name = _strip_noun(value, ("folder", "directory", "project", "workspace", "repo", "repository"))
        if not stripped_name and lowered in _CONTEXTUAL_FOLDER_REFERENCES:
            return Target(type=TargetType.UNKNOWN, name=value)
        folder_name = stripped_name or value
        cwd_folder_target = _cwd_folder_target_for_name(folder_name)
        if cwd_folder_target is not None:
            return cwd_folder_target
        return Target(type=TargetType.FOLDER, name=folder_name)

    if "file" in lowered or "document" in lowered:
        stripped_name = _strip_noun(value, ("file", "document"))
        if not stripped_name:
            return Target(type=TargetType.UNKNOWN, name=value)
        return Target(type=TargetType.FILE, name=stripped_name)

    application_name = _application_alias(value)
    if application_name is not None:
        metadata = {"browser_alias": True} if _normalize_phrase(value) in {"browser", "web browser"} else None
        return Target(type=TargetType.APPLICATION, name=application_name, metadata=metadata)

    if _looks_like_file_reference(value):
        return Target(type=TargetType.FILE, name=Path(value).name or value)

    return Target(type=TargetType.APPLICATION, name=value)


def _build_website_target(value: str) -> Target | None:
    url = _detect_url(value)
    if url is None:
        alias_key = _normalize_phrase(value, strip_words=("website", "site"))
        url = _WEBSITE_ALIASES.get(alias_key)
    if url is None:
        return None
    return Target(type=TargetType.BROWSER, name=_APP_ALIASES["browser"], metadata={"url": url})


def _existing_local_path_target(value: str) -> Target | None:
    candidate = Path(value).expanduser()
    try:
        if candidate.is_dir():
            return Target(type=TargetType.FOLDER, name=candidate.name or value, path=str(candidate))
        if candidate.is_file():
            return Target(type=TargetType.FILE, name=candidate.name or value, path=str(candidate))
    except OSError:
        return None
    return None


def _application_alias(value: str) -> str | None:
    alias_key = _normalize_phrase(value, strip_words=("app", "application"))
    return _APP_ALIASES.get(alias_key)


def _home_folder_target(value: str) -> Target | None:
    alias_key = _normalize_phrase(value, strip_words=("folder", "directory"))
    path = _HOME_FOLDER_PATHS.get(alias_key)
    if path is None:
        return None
    return Target(type=TargetType.FOLDER, name=path.name or str(path), path=str(path))


def _context_target_from_reference(value: str, session_context: SessionContext | None) -> Target | None:
    lowered = _normalize_phrase(value)

    if lowered in _CONTEXTUAL_FILE_REFERENCES:
        primary_target = _recent_primary_target_from_context(session_context)
        if primary_target is not None and _target_type_value(getattr(primary_target, "type", "")) == "file":
            return primary_target
        return _followup_unknown_target(value, expected_type="file", reason="missing_recent_target")

    if lowered in _GENERIC_CONTEXT_REFERENCES:
        context_target = _target_from_context(session_context)
        if context_target is not None:
            return context_target
        return _followup_unknown_target(value, reason="missing_recent_target")

    if lowered in _CONTEXTUAL_FOLDER_REFERENCES:
        folder_target = _search_scope_from_context(session_context)
        if folder_target is not None:
            return folder_target
        return _followup_unknown_target(value, expected_type="folder", reason="missing_folder_context")

    if lowered in _CONTEXTUAL_PROJECT_REFERENCES:
        project_target = _search_scope_from_context(session_context)
        if project_target is not None:
            return project_target
        return _followup_unknown_target(value, expected_type="folder", reason="missing_folder_context")

    if lowered == "here":
        scope_target = _search_scope_from_context(session_context)
        if scope_target is not None:
            return scope_target
        return _followup_unknown_target(value, expected_type="folder", reason="missing_folder_context")

    return None


def _target_from_context(
    session_context: SessionContext | None,
    preferred_types: set[str] | None = None,
) -> Target | None:
    if session_context is None:
        return None

    primary_target = _recent_primary_target_from_context(session_context)
    if primary_target is not None:
        primary_type = _target_type_value(getattr(primary_target, "type", "unknown"))
        if preferred_types is None or primary_type in preferred_types:
            return primary_target

    recent_folder_target = getattr(session_context, "get_recent_folder_context", None)
    if callable(recent_folder_target):
        folder_target = recent_folder_target()
        if folder_target is not None:
            folder_type = _target_type_value(getattr(folder_target, "type", "unknown"))
            if preferred_types is None or folder_type in preferred_types:
                return Target(
                    type=_coerce_target_type(folder_type),
                    name=str(getattr(folder_target, "name", "")),
                    path=getattr(folder_target, "path", None),
                    metadata=getattr(folder_target, "metadata", None),
                )

    recent_targets = getattr(session_context, "last_resolved_targets", None) or []
    for source in reversed(recent_targets):
        target_type = _target_type_value(getattr(source, "type", "unknown"))
        if preferred_types is not None and target_type not in preferred_types:
            continue
        return Target(
            type=_coerce_target_type(target_type),
            name=str(getattr(source, "name", "")),
            path=getattr(source, "path", None),
            metadata=getattr(source, "metadata", None),
        )

    return None


def _recent_primary_target_from_context(session_context: SessionContext | None) -> Target | None:
    if session_context is None:
        return None
    getter = getattr(session_context, "get_recent_primary_target", None)
    if not callable(getter):
        return None
    target = getter()
    if target is None:
        return None
    return Target(
        type=_coerce_target_type(_target_type_value(getattr(target, "type", "unknown"))),
        name=str(getattr(target, "name", "")),
        path=getattr(target, "path", None),
        metadata=getattr(target, "metadata", None),
    )


def _folder_from_recent_primary_target(session_context: SessionContext | None) -> Target | None:
    primary_target = _recent_primary_target_from_context(session_context)
    if primary_target is None:
        return None
    primary_type = _target_type_value(getattr(primary_target, "type", "unknown"))
    if primary_type == "folder":
        return primary_target
    if primary_type != "file":
        return None

    file_path = str(getattr(primary_target, "path", "") or "").strip()
    if not file_path:
        return None
    parent = Path(file_path).expanduser().parent
    parent_path = str(parent).strip()
    if not parent_path:
        return None
    return Target(type=TargetType.FOLDER, name=parent.name or parent_path, path=parent_path)


def _search_scope_from_context(session_context: SessionContext | None) -> Target | None:
    folder_target = _target_from_context(session_context, preferred_types={"folder"})
    if folder_target is not None:
        return folder_target

    file_parent_folder_target = _folder_from_recent_primary_target(session_context)
    if file_parent_folder_target is not None:
        return file_parent_folder_target

    if session_context is None:
        return None

    project_context_getter = getattr(session_context, "get_recent_project_context", None)
    project_context = project_context_getter() if callable(project_context_getter) else getattr(
        session_context,
        "recent_project_context",
        None,
    )
    normalized_project_context = str(project_context or "").strip()
    if not normalized_project_context:
        return None

    return _build_workspace_folder_descriptor(normalized_project_context, session_context)


def _looks_like_file_reference(value: str) -> bool:
    normalized = _normalize_phrase(value)
    if normalized in _CONTEXTUAL_FILE_REFERENCES:
        return True

    lowered = value.lower()
    if "file" in lowered or "document" in lowered:
        return True

    if _is_path_like(value):
        return not _looks_like_folder_path(value)

    leaf = Path(value).name
    if "." in leaf and not leaf.startswith(".") and not _looks_like_web_host(leaf):
        return True

    return False


def _detect_url(value: str) -> str | None:
    candidate = value.strip()
    if re.fullmatch(r"https?://\S+", candidate, flags=re.IGNORECASE):
        return candidate
    if candidate.lower().startswith("www.") and _looks_like_web_host(candidate[4:]):
        return f"https://{candidate}"
    if " " not in candidate and _looks_like_web_host(candidate):
        return f"https://{candidate}"
    return None


def _looks_like_web_host(value: str) -> bool:
    host = value.split("/", 1)[0]
    if "." not in host:
        return False
    labels = [label for label in host.split(".") if label]
    if len(labels) < 2:
        return False
    if not all(re.fullmatch(r"[a-z0-9-]+", label, flags=re.IGNORECASE) for label in labels):
        return False
    return labels[-1].lower() in _WEB_TLDS


def _is_path_like(value: str) -> bool:
    if value.startswith(("/", "~/", "./", "../")):
        return True
    if "/" in value and "://" not in value and not value.lower().startswith("www."):
        return True
    return False


def _looks_like_folder_path(value: str) -> bool:
    if value.endswith("/"):
        return True
    leaf = Path(value).name
    return "." not in leaf


def _strip_noun(value: str, nouns: tuple[str, ...]) -> str:
    result = value.strip()
    result = re.sub(r"^(my|the|a|an)\s+", "", result, flags=re.IGNORECASE)
    for noun in nouns:
        result = re.sub(rf"\b{re.escape(noun)}\b", "", result, flags=re.IGNORECASE)
    result = re.sub(r"\s+", " ", result).strip()
    return result or value.strip()


def _search_parameters(query_text: str, open_requested: bool = False) -> dict[str, Any]:
    original = re.sub(r"\s+", " ", query_text).strip().strip(".")
    lowered = original.lower()
    parameters: dict[str, Any] = {}

    if any(marker in lowered for marker in ("latest", "newest", "most recent", "last")):
        parameters["sort_hint"] = "latest"

    if re.search(r"\b(markdown|md)\b", lowered):
        parameters["file_type"] = "markdown"

    if open_requested or "and open it" in lowered:
        parameters["open_requested"] = True

    named_match = re.search(r"(?:file|files|document|documents)\s+named\s+(.+)$", original, flags=re.IGNORECASE)
    if named_match is not None:
        query = named_match.group(1).strip()
        parameters["filename_hint"] = query
    else:
        query = re.sub(r"\band open it\b", "", original, flags=re.IGNORECASE)
        query = re.sub(r"\b(?:the\s+)?(?:latest|newest|most recent|last)\b", "", query, flags=re.IGNORECASE)
        query = re.sub(r"\b(?:file|files|document|documents)\b", "", query, flags=re.IGNORECASE)
        query = re.sub(r"\s+", " ", query).strip(" .")

    if not query:
        if parameters.get("file_type") == "markdown":
            query = "markdown"
        else:
            query = original

    parameters["query"] = query
    return parameters


def _looks_like_search_phrase(value: str) -> bool:
    lowered = value.lower()
    return any(
        token in lowered
        for token in ("find ", "search ", "file", "files", "document", "documents", "markdown", "md", "latest", "newest", "most recent", "last", "named ")
    )


def _is_code_app_phrase(value: str) -> bool:
    normalized = _normalize_phrase(value)
    return normalized in {"code", "vs code", "vscode", "visual studio code"}


def _normalize_phrase(value: str, strip_words: tuple[str, ...] = ()) -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r"^(my|the|a|an)\s+", "", normalized)
    for word in strip_words:
        normalized = re.sub(rf"\b{re.escape(word)}\b", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _followup_unknown_target(
    value: str,
    expected_type: str | None = None,
    reason: str | None = None,
    source_type: str | None = None,
) -> Target:
    metadata: dict[str, Any] = {"followup_reference": True}
    if expected_type:
        metadata["expected_type"] = expected_type
    if reason:
        metadata["recent_target_reference"] = reason
    if source_type:
        metadata["source_type"] = source_type
    return Target(type=TargetType.UNKNOWN, name=value, metadata=metadata)


def _normalize_workspace_descriptor(workspace_text: str | None) -> str | None:
    if workspace_text is None:
        return None
    normalized = re.sub(r"\s+", " ", workspace_text).strip()
    return normalized or None


def _extract_after_keyword(text: str, keyword: str) -> str | None:
    index = text.lower().find(keyword.lower())
    if index < 0:
        return None
    value = text[index + len(keyword) :].strip()
    return value or None


def _split_multi_open_targets(payload: str) -> list[str]:
    parts = re.split(r"\s+and\s+|\s+plus\s+|,\s*", payload)
    cleaned: list[str] = []
    for part in parts:
        if not part.strip():
            continue
        segment = re.sub(r"^(?:and|plus)\s+", "", part.strip(), flags=re.IGNORECASE)
        segment = re.sub(r"\btoo\b$", "", segment, flags=re.IGNORECASE).strip()
        if segment:
            cleaned.append(segment)
    return cleaned if cleaned else [payload]


def _looks_like_workspace_target_list(target_phrase: str) -> bool:
    lowered = target_phrase.lower()
    if not any(separator in lowered for separator in (" and ", " plus ", ",")):
        return False

    segments = _split_multi_open_targets(target_phrase)
    if len(segments) < 2:
        return False

    return all(_is_workspace_target_phrase(segment) for segment in segments)


def _is_workspace_target_phrase(segment: str) -> bool:
    if _application_alias(segment) is not None:
        return True
    if _build_website_target(segment) is not None:
        return True
    lowered = segment.lower()
    return _is_path_like(segment) or any(word in lowered for word in ("folder", "directory", "project", "workspace", "repo", "repository"))


def _looks_like_workspace_reference(value: str) -> bool:
    lowered = value.lower()
    if _is_path_like(value):
        return True
    if _home_folder_target(value) is not None:
        return True
    if any(word in lowered for word in ("folder", "directory", "project", "workspace", "repo", "repository")):
        return True
    return _normalize_phrase(value) in _CONTEXTUAL_SCOPE_REFERENCES


def _can_fallback_to_workspace_code_reference(value: str) -> bool:
    normalized = _normalize_phrase(value)
    if not normalized:
        return False
    if _application_alias(value) is not None:
        return False
    if _looks_like_file_reference(value):
        return False
    return True


def _build_workspace_folder_descriptor(workspace: str, session_context: SessionContext | None) -> Target:
    normalized = re.sub(r"\s+", " ", workspace).strip()
    lowered = _normalize_phrase(normalized)

    if lowered in _CONTEXTUAL_SCOPE_REFERENCES:
        context_target = _search_scope_from_context(session_context)
        if context_target is not None:
            return context_target
        return _followup_unknown_target(normalized, expected_type="folder", reason="missing_folder_context")

    if _is_path_like(normalized):
        leaf_name = Path(normalized).name or normalized
        return Target(type=TargetType.FOLDER, name=leaf_name, path=normalized)

    home_folder_target = _home_folder_target(normalized)
    if home_folder_target is not None:
        return home_folder_target

    stripped_name = _strip_noun(normalized, ("folder", "directory", "project", "workspace", "repo", "repository"))
    resolved_name = stripped_name or normalized
    cwd_folder_target = _cwd_folder_target_for_name(resolved_name)
    if cwd_folder_target is not None:
        return cwd_folder_target
    return Target(type=TargetType.FOLDER, name=resolved_name)


def _cwd_folder_target_for_name(value: str) -> Target | None:
    normalized = _normalize_phrase(value)
    if not normalized:
        return None
    cwd = Path.cwd()
    if normalized != _normalize_phrase(cwd.name):
        return None
    return Target(type=TargetType.FOLDER, name=cwd.name, path=str(cwd))


def _inject_workspace_folder_target(targets: list[Target], folder_target: Target | None) -> list[Target]:
    if folder_target is None:
        return targets
    if any(_target_type_value(target.type) == "folder" for target in targets):
        return targets
    if not targets:
        return [folder_target]

    if _target_type_value(targets[0].type) == "application":
        return [targets[0], folder_target, *targets[1:]]
    return [folder_target, *targets]


def _workspace_parameters_from_targets(targets: list[Target]) -> dict[str, Any]:
    for target in targets:
        if _target_type_value(target.type) != "folder":
            continue
        workspace = str(getattr(target, "path", "") or "").strip() or str(getattr(target, "name", "")).strip()
        if workspace:
            return {"workspace": workspace}
    return {}


def _normalize_workspace_targets(targets: list[Target]) -> list[Target]:
    normalized: list[Target] = []
    seen: set[tuple[str, str, str, str]] = set()
    for target in targets:
        key = _workspace_target_key(target)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(target)
    return normalized


def _normalize_workspace_browser_targets(targets: list[Target]) -> list[Target]:
    normalized: list[Target] = []
    for target in targets:
        metadata = getattr(target, "metadata", None) or {}
        if (
            _target_type_value(getattr(target, "type", "unknown")) == "application"
            and metadata.get("browser_alias")
        ):
            normalized.append(Target(type=TargetType.APPLICATION, name=_APP_ALIASES["chrome"]))
            continue
        normalized.append(target)
    return normalized


def _workspace_target_key(target: Target) -> tuple[str, str, str, str]:
    target_type = _target_type_value(getattr(target, "type", "unknown"))
    name = str(getattr(target, "name", "")).strip().lower()
    path = str(getattr(target, "path", "") or "").strip().lower()
    metadata = getattr(target, "metadata", None) or {}
    url = str(metadata.get("url", "")).strip().lower()
    return (target_type, name, path, url)


def _is_generic_workspace_folder_segment(segment: str) -> bool:
    normalized = _normalize_phrase(segment)
    if normalized in _CONTEXTUAL_SCOPE_REFERENCES:
        return True
    return normalized in {
        "folder",
        "directory",
        "project",
        "workspace",
        "repo",
        "repository",
        "project folder",
        "workspace folder",
        "repo folder",
        "repository folder",
    }


def _is_workspace_placeholder_target(target: Target) -> bool:
    if _target_type_value(getattr(target, "type", "unknown")) != TargetType.FOLDER.value:
        return False
    normalized_name = _normalize_phrase(str(getattr(target, "name", "")))
    return normalized_name in {
        "folder",
        "directory",
        "project",
        "workspace",
        "repo",
        "repository",
        "project folder",
        "workspace folder",
        "repo folder",
        "repository folder",
    }


def _is_workspace_target_group(targets: list[Target]) -> bool:
    workspace_types: set[str] = set()
    for target in targets:
        target_type = _target_type_value(target.type)
        metadata = getattr(target, "metadata", None) or {}
        if target_type == "unknown":
            if not metadata.get("followup_reference"):
                return False
            continue
        if target_type not in {"application", "folder", "browser"}:
            return False
        workspace_types.add(target_type)
    return bool(workspace_types)


def _starts_with_open_verb(text: str) -> bool:
    lowered = text.lower()
    return any(lowered.startswith(f"{verb} ") for verb in _OPEN_VERBS)


def _strip_open_verb(text: str) -> str:
    lowered = text.lower()
    for verb in _OPEN_VERBS:
        prefix = f"{verb} "
        if lowered.startswith(prefix):
            return text[len(prefix) :].strip()
    return text.strip()


def _unknown_target(raw_text: str) -> Target:
    return Target(type=TargetType.UNKNOWN, name=raw_text)


def _intent_from_target_type(target_type: str) -> str:
    if target_type == "file":
        return "open_file"
    if target_type == "folder":
        return "open_folder"
    if target_type == "browser":
        return "open_website"
    return "open_app"


def _target_type_value(target_type: Any) -> str:
    return str(getattr(target_type, "value", target_type))


def _coerce_target_type(target_type: str) -> TargetType:
    for enum_value in TargetType:
        if enum_value.value == target_type:
            return enum_value
    return TargetType.UNKNOWN


def _clone_target(target: Target) -> Target:
    metadata = getattr(target, "metadata", None)
    return Target(
        type=_coerce_target_type(_target_type_value(getattr(target, "type", "unknown"))),
        name=str(getattr(target, "name", "")),
        path=getattr(target, "path", None),
        metadata=dict(metadata) if isinstance(metadata, dict) and metadata else metadata,
    )


def _coerce_intent(intent: str) -> IntentType | str:
    try:
        return IntentType(intent)
    except ValueError:
        return intent


def _compute_confidence(intent: str, targets: list[Target], parameters: dict[str, Any]) -> float:
    base_by_intent = {
        "confirm": 0.95,
        "clarify": 0.7,
        "list_windows": 0.95,
        "open_website": 0.92,
        "open_app": 0.9,
        "open_file": 0.88,
        "open_folder": 0.88,
        "focus_window": 0.85,
        "close_window": 0.85,
        "close_app": 0.85,
        "search_local": 0.87,
        "prepare_workspace": 0.84,
    }
    confidence = base_by_intent.get(intent, 0.45)

    target_required = {
        "open_app",
        "open_file",
        "open_folder",
        "open_website",
        "focus_window",
        "close_window",
        "close_app",
    }
    if intent in target_required and not targets:
        confidence -= 0.35

    has_unknown_target = any(_target_type_value(target.type) == "unknown" for target in targets)
    if has_unknown_target:
        confidence -= 0.25

    if intent == "search_local" and not str(parameters.get("query", "")).strip():
        confidence -= 0.2

    if intent == "prepare_workspace":
        if targets:
            confidence += 0.04
        elif not parameters:
            confidence -= 0.2

    return round(max(0.0, min(1.0, confidence)), 2)


def _status_message(intent: str) -> str:
    messages = {
        "open_app": "Parsed application open request.",
        "open_file": "Parsed file open request.",
        "open_folder": "Parsed folder open request.",
        "open_website": "Parsed website open request.",
        "focus_window": "Parsed window focus request.",
        "close_window": "Parsed window close request.",
        "close_app": "Parsed app close request.",
        "list_windows": "Parsed window listing request.",
        "search_local": "Parsed local search request.",
        "prepare_workspace": "Parsed workspace preparation request.",
        "clarify": "Clarification is likely required.",
        "confirm": "Parsed confirmation response.",
        "switch_window": "Parsed unsupported window-management request.",
    }
    return messages.get(intent, "Parsed preliminary command.")
