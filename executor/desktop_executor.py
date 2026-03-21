"""macOS-first MVP executor with a narrow real action surface and explicit unsupported failures."""

from __future__ import annotations

import ctypes
import re
import subprocess
import sys
from pathlib import Path
from ctypes.util import find_library
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from executor.desktop_actions import DESKTOP_ACTIONS, DesktopAction

if TYPE_CHECKING:
    from types.action_result import ActionResult
    from types.step import Step


_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from action_result import ActionError, ActionResult  # type: ignore  # noqa: E402
from step import Step  # type: ignore  # noqa: E402
from target import Target  # type: ignore  # noqa: E402

_SEARCH_IGNORE_TERMS = {"file", "files", "folder", "folders", "local", "for", "the", "a", "an"}
_MARKDOWN_SUFFIXES = (".md", ".markdown", ".mdown")
_UTF8_ENCODING = 0x08000100
_CG_WINDOW_LIST_ON_SCREEN_ONLY = 1 << 0
_CG_WINDOW_LIST_EXCLUDE_DESKTOP = 1 << 4
_CF_NUMBER_DOUBLE_TYPE = 13
_WINDOW_TITLE_KEYS = {
    "owner": "kCGWindowOwnerName",
    "title": "kCGWindowName",
    "window_id": "kCGWindowNumber",
    "layer": "kCGWindowLayer",
}


def execute_step(step: Step) -> ActionResult:
    """Execute one validated step on macOS or fail explicitly when unsupported."""
    action = _action_value(getattr(step, "action", ""))
    target = getattr(step, "target")

    if bool(getattr(step, "requires_confirmation", False)):
        return _failure(
            action,
            target,
            code="CONFIRMATION_REQUIRED",
            message="Step requires explicit confirmation before execution.",
        )

    if sys.platform != "darwin":
        return _failure(
            action,
            target,
            code="UNSUPPORTED_ACTION",
            message="The real desktop executor is macOS-only.",
        )

    if action not in DESKTOP_ACTIONS:
        return _failure(
            action,
            target,
            code="UNSUPPORTED_ACTION",
            message=f"Unsupported desktop action: {action!r}.",
        )

    parameters = dict(getattr(step, "parameters", {}) or {})

    if action == DesktopAction.OPEN_APP.value:
        return _execute_open_app(target)
    if action == DesktopAction.FOCUS_APP.value:
        return _execute_focus_app(target)
    if action == DesktopAction.OPEN_FILE.value:
        return _execute_open_file(target, parameters)
    if action == DesktopAction.OPEN_FOLDER.value:
        return _execute_open_folder(target, parameters)
    if action == DesktopAction.OPEN_WEBSITE.value:
        return _execute_open_website(target, parameters)
    if action == DesktopAction.LIST_WINDOWS.value:
        return _execute_list_windows(target, parameters)
    if action == DesktopAction.FOCUS_WINDOW.value:
        return _unsupported_window_action(
            action,
            target,
            "Per-window focus is intentionally unsupported until a reliable exact-window raise path is in place.",
        )
    if action == DesktopAction.CLOSE_WINDOW.value:
        return _unsupported_window_action(action, target, "Window closing is not supported reliably yet on macOS MVP.")
    if action == DesktopAction.CLOSE_APP.value:
        return _execute_close_app(target)
    if action == DesktopAction.SEARCH_LOCAL.value:
        return _execute_search_local(target, parameters)
    if action == DesktopAction.PREPARE_WORKSPACE.value:
        return _failure(
            action,
            target,
            code="UNSUPPORTED_ACTION",
            message="prepare_workspace must execute through planned sub-steps, not as a direct executor action.",
        )

    return _failure(action, target, code="UNSUPPORTED_ACTION", message=f"Unsupported desktop action: {action!r}.")


def _execute_open_app(target: Target) -> ActionResult:
    action = DesktopAction.OPEN_APP.value
    if _target_type_value(getattr(target, "type", "")) != "application":
        return _failure(action, target, code="UNSUPPORTED_TARGET", message="open_app requires an application target.")
    app_name = _target_name(target)
    if not app_name:
        return _failure(action, target, code="TARGET_NOT_FOUND", message="Application target name is missing.")

    result = _run_command(["open", "-a", app_name])
    if result.returncode != 0:
        code = "APP_UNAVAILABLE" if _looks_like_app_unavailable(result) else _command_failure_code(result)
        message = _stderr_text(result) or f'Unable to open application "{app_name}".'
        return _failure(action, target, code=code, message=message)

    return _success(action, target, details={"focused": True})


def _execute_focus_app(target: Target) -> ActionResult:
    action = DesktopAction.FOCUS_APP.value
    if _target_type_value(getattr(target, "type", "")) != "application":
        return _failure(action, target, code="UNSUPPORTED_TARGET", message="focus_app requires an application target.")
    app_name = _target_name(target)
    if not app_name:
        return _failure(action, target, code="TARGET_NOT_FOUND", message="Application target name is missing.")

    if not _is_app_running(app_name):
        return _failure(action, target, code="APP_NOT_RUNNING", message=f'Application "{app_name}" is not running.')

    result = _run_apple_script([f'tell application "{_escape_applescript_string(app_name)}" to activate'])
    if result.returncode == 0:
        return _success(action, target, details={"focused": True})
    return _failure(
        action,
        target,
        code=_command_failure_code(result),
        message=_stderr_text(result) or f'Unable to focus application "{app_name}".',
    )


def _execute_open_file(target: Target, parameters: dict[str, Any]) -> ActionResult:
    action = DesktopAction.OPEN_FILE.value
    if _target_type_value(getattr(target, "type", "")) != "file":
        return _failure(action, target, code="UNSUPPORTED_TARGET", message="open_file requires a file target.")
    file_path = _resolve_existing_path(target, expect_directory=False)
    if file_path is None:
        return _failure(action, target, code="TARGET_NOT_FOUND", message="File target does not exist.")

    app_name = _open_app_hint(target, parameters)
    command = ["open", str(file_path)] if not app_name else ["open", "-a", app_name, str(file_path)]
    result = _run_command(command)
    if result.returncode != 0:
        if app_name and _looks_like_app_unavailable(result):
            return _failure(
                action,
                target,
                code="APP_UNAVAILABLE",
                message=_stderr_text(result) or f'Unable to find application "{app_name}" for file open.',
            )
        return _failure(
            action,
            target,
            code=_command_failure_code(result),
            message=_stderr_text(result) or f'Unable to open file "{file_path}".',
        )

    details: dict[str, Any] = {"path": str(file_path)}
    if app_name:
        details["app"] = app_name
    return _success(action, target, details=details)


def _execute_open_folder(target: Target, parameters: dict[str, Any]) -> ActionResult:
    action = DesktopAction.OPEN_FOLDER.value
    if _target_type_value(getattr(target, "type", "")) != "folder":
        return _failure(action, target, code="UNSUPPORTED_TARGET", message="open_folder requires a folder target.")
    folder_path = _resolve_existing_path(target, expect_directory=True)
    if folder_path is None:
        return _failure(action, target, code="TARGET_NOT_FOUND", message="Folder target does not exist.")

    app_name = _open_app_hint(target, parameters)
    command = ["open", str(folder_path)] if not app_name else ["open", "-a", app_name, str(folder_path)]
    result = _run_command(command)
    if result.returncode != 0:
        if not app_name:
            finder_result = _run_command(["open", "-a", "Finder", str(folder_path)])
            if finder_result.returncode == 0:
                return _success(
                    action,
                    target,
                    details={"path": str(folder_path), "app": "Finder", "fallback_used": True},
                )

        if app_name and _looks_like_app_unavailable(result):
            return _failure(
                action,
                target,
                code="APP_UNAVAILABLE",
                message=_stderr_text(result) or f'Unable to find application "{app_name}" for folder open.',
            )
        return _failure(
            action,
            target,
            code=_command_failure_code(result),
            message=_stderr_text(result) or f'Unable to open folder "{folder_path}".',
        )

    details: dict[str, Any] = {"path": str(folder_path)}
    if app_name:
        details["app"] = app_name
    return _success(action, target, details=details)


def _execute_open_website(target: Target, parameters: dict[str, Any]) -> ActionResult:
    action = DesktopAction.OPEN_WEBSITE.value
    if _target_type_value(getattr(target, "type", "")) != "browser":
        return _failure(action, target, code="UNSUPPORTED_TARGET", message="open_website requires a browser target.")
    url = _url_from_inputs(target, parameters)
    if not _is_valid_http_url(url):
        return _failure(action, target, code="INVALID_URL", message="URL must start with http:// or https://.")

    result = _run_command(["open", url])
    if result.returncode != 0:
        return _failure(
            action,
            target,
            code=_command_failure_code(result),
            message=_stderr_text(result) or f'Unable to open URL "{url}".',
        )

    return _success(action, target, details={"url": url})


def _execute_list_windows(target: Target, _parameters: dict[str, Any]) -> ActionResult:
    action = DesktopAction.LIST_WINDOWS.value
    target_type = _target_type_value(getattr(target, "type", ""))
    if target_type not in {"window", "application"}:
        return _failure(action, target, code="UNSUPPORTED_TARGET", message="list_windows requires a window or application target.")
    windows, error = _list_visible_windows()
    if error is not None:
        return _failure(action, target, code=_normalize_window_error_code(error.code), message=error.message)

    filtered_windows = _filter_windows_for_target(windows, target)
    filter_name = _window_filter_name(target)
    details: dict[str, Any] = {
        "count": len(filtered_windows),
        "windows": filtered_windows,
    }
    if filter_name:
        details["filter"] = filter_name
    return _success(action, target, details=details)


def _execute_close_app(target: Target) -> ActionResult:
    action = DesktopAction.CLOSE_APP.value
    if _target_type_value(getattr(target, "type", "")) != "application":
        return _failure(action, target, code="UNSUPPORTED_TARGET", message="close_app requires an application target.")
    app_name = _target_name(target)
    if not app_name:
        return _failure(action, target, code="TARGET_NOT_FOUND", message="Application target name is missing.")

    if not _is_app_running(app_name):
        return _failure(action, target, code="APP_NOT_RUNNING", message=f'Application "{app_name}" is not running.')

    result = _run_apple_script([f'tell application "{_escape_applescript_string(app_name)}" to quit'])
    if result.returncode == 0:
        return _success(action, target, details={"quit_requested": True})
    return _failure(
        action,
        target,
        code=_command_failure_code(result),
        message=_stderr_text(result) or f'Unable to request quit for "{app_name}".',
    )


def _execute_search_local(target: Target, parameters: dict[str, Any]) -> ActionResult:
    action = DesktopAction.SEARCH_LOCAL.value
    if _target_type_value(getattr(target, "type", "")) != "folder":
        return _failure(action, target, code="UNSUPPORTED_TARGET", message="search_local requires a folder scope target.")
    query = str(parameters.get("query", "")).strip()
    if not query:
        return _failure(action, target, code="MISSING_PARAMETER", message="search_local requires a query.")

    scope_path = _search_scope_path(target, parameters)
    if scope_path is None:
        return _failure(
            action,
            target,
            code="MISSING_PARAMETER",
            message="search_local requires an explicit local scope path.",
        )

    matches = _search_paths(scope_path, query)
    return _success(
        action,
        target,
        details={"query": query, "scope_path": str(scope_path), "matches": matches},
    )


def _unsupported_window_action(action: str, target: Target, message: str) -> ActionResult:
    return _failure(action, target, code="UNSUPPORTED_ACTION", message=message)


def _list_visible_windows() -> tuple[list[dict[str, Any]], ActionError | None]:
    core_graphics, core_foundation = _load_window_frameworks()
    if core_graphics is None or core_foundation is None:
        return [], ActionError(
            code="UNSUPPORTED_ACTION",
            message="CoreGraphics window inspection is unavailable on this macOS environment.",
        )

    _configure_window_frameworks(core_graphics, core_foundation)
    array_ref = core_graphics.CGWindowListCopyWindowInfo(
        _CG_WINDOW_LIST_ON_SCREEN_ONLY | _CG_WINDOW_LIST_EXCLUDE_DESKTOP,
        0,
    )
    if not array_ref:
        return [], ActionError(
            code="EXECUTION_FAILED",
            message="Visible window inspection is unavailable in the current macOS session.",
        )

    key_refs = {name: _cf_string_create(core_foundation, key) for name, key in _WINDOW_TITLE_KEYS.items()}
    try:
        windows: list[dict[str, Any]] = []
        seen_ids: set[int] = set()
        count = int(core_foundation.CFArrayGetCount(array_ref))
        for index in range(count):
            item_ref = core_foundation.CFArrayGetValueAtIndex(array_ref, index)
            if not item_ref:
                continue

            app_name = _cf_dictionary_string_value(core_foundation, item_ref, key_refs["owner"])
            if not app_name:
                continue

            layer = _cf_dictionary_number_value(core_foundation, item_ref, key_refs["layer"])
            if layer is None or int(layer) != 0:
                continue

            window_id = _cf_dictionary_number_value(core_foundation, item_ref, key_refs["window_id"])
            if window_id is None:
                continue

            normalized_window_id = int(window_id)
            if normalized_window_id in seen_ids:
                continue
            seen_ids.add(normalized_window_id)

            windows.append(
                {
                    "app_name": app_name,
                    "window_title": _cf_dictionary_string_value(core_foundation, item_ref, key_refs["title"]) or "",
                    "window_id": normalized_window_id,
                }
            )
        return windows, None
    finally:
        for key_ref in key_refs.values():
            if key_ref:
                core_foundation.CFRelease(key_ref)
        core_foundation.CFRelease(array_ref)


def _filter_windows_for_target(windows: list[dict[str, Any]], target: Target) -> list[dict[str, Any]]:
    target_name = _window_filter_name(target)
    if not target_name:
        return windows

    lowered_target = target_name.lower()
    target_type = _target_type_value(getattr(target, "type", ""))

    if target_type == "application":
        exact_application_matches = [window for window in windows if str(window.get("app_name", "")).lower() == lowered_target]
        if exact_application_matches:
            return exact_application_matches
        return [window for window in windows if lowered_target in str(window.get("app_name", "")).lower()]

    exact_title_matches = [window for window in windows if str(window.get("window_title", "")).lower() == lowered_target]
    if exact_title_matches:
        return exact_title_matches

    exact_app_matches = [window for window in windows if str(window.get("app_name", "")).lower() == lowered_target]
    if exact_app_matches:
        return exact_app_matches

    partial_title_matches = [window for window in windows if lowered_target in str(window.get("window_title", "")).lower()]
    if partial_title_matches:
        return partial_title_matches

    return [window for window in windows if lowered_target in str(window.get("app_name", "")).lower()]


def _window_filter_name(target: Target) -> str:
    name = _target_name(target)
    if not name:
        return ""
    if _target_type_value(getattr(target, "type", "")) == "window" and name.lower() == "windows":
        return ""
    return name


def _normalize_window_error_code(code: str) -> str:
    normalized = str(code or "").strip().upper()
    if normalized in {"PERMISSION_DENIED", "UNSUPPORTED_ACTION", "EXECUTION_FAILED", "WINDOW_UNAVAILABLE"}:
        return normalized
    return "EXECUTION_FAILED"


def _resolve_existing_path(target: Target, expect_directory: bool) -> Path | None:
    candidates: list[Path] = []
    raw_path = str(getattr(target, "path", "") or "").strip()
    raw_name = _target_name(target)

    if raw_path:
        candidates.append(Path(raw_path).expanduser())
    if raw_name:
        candidates.append(Path(raw_name).expanduser())

    seen: set[str] = set()
    for candidate in candidates:
        normalized = str(candidate)
        if normalized in seen:
            continue
        seen.add(normalized)
        if expect_directory and candidate.is_dir():
            return candidate
        if not expect_directory and candidate.is_file():
            return candidate
    return None


def _search_scope_path(target: Target, parameters: dict[str, Any]) -> Path | None:
    raw_scope = str(parameters.get("scope_path", "")).strip()
    if raw_scope:
        candidate = Path(raw_scope).expanduser()
        if candidate.is_dir():
            return candidate
        return None

    raw_target_path = str(getattr(target, "path", "") or "").strip()
    if raw_target_path:
        candidate = Path(raw_target_path).expanduser()
        if candidate.is_dir():
            return candidate

    return None


def _search_paths(scope_path: Path, query: str) -> list[dict[str, str]]:
    matches: list[dict[str, str]] = []
    for path in scope_path.rglob("*"):
        if _name_matches_query(path.name, query):
            matches.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "type": "folder" if path.is_dir() else "file",
                }
            )
    return matches


def _name_matches_query(name: str, query: str) -> bool:
    lowered_name = name.lower()
    tokens = [token for token in re.findall(r"[a-z0-9._-]+", query.lower()) if token not in _SEARCH_IGNORE_TERMS]
    if not tokens:
        return query.lower().strip() in lowered_name

    for token in tokens:
        if token == "markdown":
            if not lowered_name.endswith(_MARKDOWN_SUFFIXES):
                return False
            continue
        if token not in lowered_name:
            return False
    return True


def _url_from_inputs(target: Target, parameters: dict[str, Any]) -> str:
    raw_url = str(parameters.get("url", "")).strip()
    if raw_url:
        return raw_url

    metadata = getattr(target, "metadata", None) or {}
    metadata_url = str(metadata.get("url", "")).strip()
    if metadata_url:
        return metadata_url
    return ""


def _open_app_hint(target: Target, parameters: dict[str, Any]) -> str | None:
    app_name = str(parameters.get("app", "")).strip()
    if app_name:
        return app_name
    metadata = getattr(target, "metadata", None) or {}
    metadata_app = str(metadata.get("app", "")).strip()
    if metadata_app:
        return metadata_app
    return None


def _run_command(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(arguments, capture_output=True, text=True, check=False)


def _run_apple_script(lines: list[str]) -> subprocess.CompletedProcess[str]:
    arguments = ["osascript"]
    for line in lines:
        arguments.extend(["-e", line])
    return subprocess.run(arguments, capture_output=True, text=True, check=False)


def _load_window_frameworks() -> tuple[Any | None, Any | None]:
    core_graphics_path = find_library("CoreGraphics")
    core_foundation_path = find_library("CoreFoundation")
    if not core_graphics_path or not core_foundation_path:
        return None, None
    try:
        return ctypes.cdll.LoadLibrary(core_graphics_path), ctypes.cdll.LoadLibrary(core_foundation_path)
    except OSError:
        return None, None


def _configure_window_frameworks(core_graphics: Any, core_foundation: Any) -> None:
    core_graphics.CGWindowListCopyWindowInfo.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    core_graphics.CGWindowListCopyWindowInfo.restype = ctypes.c_void_p

    core_foundation.CFArrayGetCount.argtypes = [ctypes.c_void_p]
    core_foundation.CFArrayGetCount.restype = ctypes.c_long
    core_foundation.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]
    core_foundation.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
    core_foundation.CFDictionaryGetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    core_foundation.CFDictionaryGetValue.restype = ctypes.c_void_p
    core_foundation.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
    core_foundation.CFStringCreateWithCString.restype = ctypes.c_void_p
    core_foundation.CFStringGetCStringPtr.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    core_foundation.CFStringGetCStringPtr.restype = ctypes.c_char_p
    core_foundation.CFStringGetCString.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_char),
        ctypes.c_long,
        ctypes.c_uint32,
    ]
    core_foundation.CFStringGetCString.restype = ctypes.c_bool
    core_foundation.CFStringGetTypeID.restype = ctypes.c_ulong
    core_foundation.CFGetTypeID.argtypes = [ctypes.c_void_p]
    core_foundation.CFGetTypeID.restype = ctypes.c_ulong
    core_foundation.CFNumberGetTypeID.restype = ctypes.c_ulong
    core_foundation.CFNumberGetValue.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    core_foundation.CFNumberGetValue.restype = ctypes.c_bool
    core_foundation.CFRelease.argtypes = [ctypes.c_void_p]
    core_foundation.CFRelease.restype = None


def _cf_string_create(core_foundation: Any, value: str) -> ctypes.c_void_p:
    return core_foundation.CFStringCreateWithCString(None, value.encode("utf-8"), _UTF8_ENCODING)


def _cf_dictionary_string_value(core_foundation: Any, dictionary_ref: ctypes.c_void_p, key_ref: ctypes.c_void_p) -> str | None:
    value_ref = core_foundation.CFDictionaryGetValue(dictionary_ref, key_ref)
    return _cf_string_to_python(core_foundation, value_ref)


def _cf_dictionary_number_value(core_foundation: Any, dictionary_ref: ctypes.c_void_p, key_ref: ctypes.c_void_p) -> float | None:
    value_ref = core_foundation.CFDictionaryGetValue(dictionary_ref, key_ref)
    return _cf_number_to_python(core_foundation, value_ref)


def _cf_string_to_python(core_foundation: Any, value_ref: ctypes.c_void_p) -> str | None:
    if not value_ref or core_foundation.CFGetTypeID(value_ref) != core_foundation.CFStringGetTypeID():
        return None

    direct_value = core_foundation.CFStringGetCStringPtr(value_ref, _UTF8_ENCODING)
    if direct_value:
        return direct_value.decode("utf-8")

    buffer = ctypes.create_string_buffer(4096)
    if core_foundation.CFStringGetCString(value_ref, buffer, len(buffer), _UTF8_ENCODING):
        return buffer.value.decode("utf-8")
    return None


def _cf_number_to_python(core_foundation: Any, value_ref: ctypes.c_void_p) -> float | None:
    if not value_ref or core_foundation.CFGetTypeID(value_ref) != core_foundation.CFNumberGetTypeID():
        return None

    number_value = ctypes.c_double()
    if core_foundation.CFNumberGetValue(value_ref, _CF_NUMBER_DOUBLE_TYPE, ctypes.byref(number_value)):
        return float(number_value.value)
    return None


def _is_valid_http_url(url: str) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _looks_like_app_unavailable(result: subprocess.CompletedProcess[str]) -> bool:
    text = _stderr_text(result).lower()
    return "unable to find application" in text or "application named" in text


def _command_failure_code(result: subprocess.CompletedProcess[str]) -> str:
    text = _stderr_text(result)
    if _is_permission_error(text):
        return "PERMISSION_DENIED"
    return "EXECUTION_FAILED"


def _is_permission_error(text: str) -> bool:
    lowered = text.lower()
    return (
        "not authorized" in lowered
        or "not permitted" in lowered
        or "permission" in lowered
        or "not allowed assistive access" in lowered
        or "operation not permitted" in lowered
    )


def _stderr_text(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stderr or result.stdout or "").strip()


def _is_app_running(app_name: str) -> bool:
    result = _run_apple_script(
        [
            f'if application "{_escape_applescript_string(app_name)}" is running then',
            'return "yes"',
            "else",
            'return "no"',
            "end if",
        ]
    )
    return result.returncode == 0 and (result.stdout or "").strip().lower() == "yes"


def _escape_applescript_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _success(action: str, target: Target, details: dict[str, Any] | None = None) -> ActionResult:
    return ActionResult(action=action, success=True, target=target, details=details, error=None)


def _failure(action: str, target: Target, code: str, message: str) -> ActionResult:
    return ActionResult(
        action=action,
        success=False,
        target=target,
        details=None,
        error=ActionError(code=code, message=message),
    )


def _action_value(action: Any) -> str:
    return str(getattr(action, "value", action))


def _target_name(target: Any) -> str:
    return str(getattr(target, "name", "")).strip()


def _target_type_value(target_type: Any) -> str:
    return str(getattr(target_type, "value", target_type))
