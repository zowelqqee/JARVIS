"""Deterministic structural validator for JARVIS MVP commands."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from types.command import Command
    from types.validation_result import ValidationResult


_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from jarvis_error import ErrorCategory, ErrorCode, JarvisError  # type: ignore  # noqa: E402
from target import TargetType  # type: ignore  # noqa: E402
from validation_result import ValidationResult  # type: ignore  # noqa: E402

_CONFIDENCE_THRESHOLD = 0.6
_SUPPORTED_INTENTS = {
    "open_app",
    "open_file",
    "open_folder",
    "open_website",
    "focus_window",
    "close_window",
    "close_app",
    "list_windows",
    "search_local",
    "prepare_workspace",
    "clarify",
    "confirm",
}


def validate_command(command: Command) -> ValidationResult:
    """Validate a preliminary command against MVP runtime rules."""
    intent = _intent_value(getattr(command, "intent", ""))

    if intent not in _SUPPORTED_INTENTS:
        if intent == "switch_window":
            return _invalid(
                ErrorCode.UNSUPPORTED_ACTION,
                "Intent 'switch_window' is not supported in the current parser/validator contract.",
            )
        return _invalid(ErrorCode.UNKNOWN_INTENT, f"Unsupported intent: {intent!r}.")

    confidence = float(getattr(command, "confidence", 0.0))
    if confidence < _CONFIDENCE_THRESHOLD:
        return _invalid(ErrorCode.LOW_CONFIDENCE, "Command confidence is below threshold.")

    targets = list(getattr(command, "targets", []) or [])
    parameters = dict(getattr(command, "parameters", {}) or {})

    ambiguous_error = _check_ambiguous_targets(targets)
    if ambiguous_error is not None:
        return ambiguous_error

    if intent == "open_app":
        return _validate_open_app(command, targets)
    if intent == "open_file":
        return _validate_open_file(command, targets)
    if intent == "open_folder":
        return _validate_open_folder(command, targets)
    if intent == "open_website":
        return _validate_open_website(command, targets, parameters)
    if intent == "focus_window":
        return _validate_window_intent(command, targets, intent_name="focus_window")
    if intent == "close_window":
        return _validate_window_intent(command, targets, intent_name="close_window")
    if intent == "close_app":
        return _validate_close_app(command, targets)
    if intent == "list_windows":
        return _validate_list_windows(command, targets)
    if intent == "search_local":
        return _validate_search_local(command, targets, parameters)
    if intent == "prepare_workspace":
        return _validate_prepare_workspace(command, targets, parameters)
    if intent == "clarify":
        return _validate_clarify(command)
    if intent == "confirm":
        return _validate_confirm(command, parameters)

    return _invalid(ErrorCode.UNKNOWN_INTENT, f"Unsupported intent: {intent!r}.")


def _validate_open_app(command: Command, targets: list[Any]) -> ValidationResult:
    if not targets:
        return _invalid(ErrorCode.TARGET_NOT_FOUND, "open_app requires at least one application target.")
    recent_target_error = _recent_target_followup_error(targets)
    if recent_target_error is not None:
        return recent_target_error
    if _contains_followup_reference_unknown(targets):
        return _invalid(ErrorCode.FOLLOWUP_REFERENCE_UNCLEAR, "open_app follow-up target is unclear.")
    if _contains_unknown_targets(targets):
        return _invalid(ErrorCode.TARGET_NOT_FOUND, "open_app target is missing required name.")
    if not _all_targets_of_type(targets, {"application"}):
        return _invalid(ErrorCode.UNSUPPORTED_TARGET, "open_app accepts only application targets.")
    if not _all_targets_resolved(targets):
        return _invalid(ErrorCode.TARGET_NOT_FOUND, "open_app target is missing required name.")
    return _valid(command)


def _validate_open_file(command: Command, targets: list[Any]) -> ValidationResult:
    if not targets:
        return _invalid(ErrorCode.TARGET_NOT_FOUND, "open_file requires a file target.")
    recent_target_error = _recent_target_followup_error(targets)
    if recent_target_error is not None:
        return recent_target_error
    search_followup_error = _search_result_followup_error(targets)
    if search_followup_error is not None:
        return search_followup_error
    if _contains_followup_reference_unknown(targets):
        return _invalid(ErrorCode.FOLLOWUP_REFERENCE_UNCLEAR, "open_file follow-up target is unclear.")
    if _contains_unknown_targets(targets):
        return _invalid(ErrorCode.TARGET_NOT_FOUND, "open_file target requires a name or path.")
    if not _all_targets_of_type(targets, {"file"}):
        return _invalid(ErrorCode.UNSUPPORTED_TARGET, "open_file accepts only file targets.")
    if not _all_targets_resolved(targets):
        return _invalid(ErrorCode.TARGET_NOT_FOUND, "open_file target requires a name or path.")
    return _valid(command)


def _validate_open_folder(command: Command, targets: list[Any]) -> ValidationResult:
    if not targets:
        return _invalid(ErrorCode.TARGET_NOT_FOUND, "open_folder requires a folder target.")
    recent_target_error = _recent_target_followup_error(targets)
    if recent_target_error is not None:
        return recent_target_error
    if _contains_followup_reference_unknown(targets):
        return _invalid(ErrorCode.FOLLOWUP_REFERENCE_UNCLEAR, "open_folder follow-up target is unclear.")
    if _contains_unknown_targets(targets):
        return _invalid(ErrorCode.TARGET_NOT_FOUND, "open_folder target requires a name or path.")
    if not _all_targets_of_type(targets, {"folder"}):
        return _invalid(ErrorCode.UNSUPPORTED_TARGET, "open_folder accepts only folder targets.")
    if not _all_targets_resolved(targets):
        return _invalid(ErrorCode.TARGET_NOT_FOUND, "open_folder target requires a name or path.")
    return _valid(command)


def _validate_open_website(
    command: Command,
    targets: list[Any],
    parameters: dict[str, Any],
) -> ValidationResult:
    if not targets:
        return _invalid(ErrorCode.TARGET_NOT_FOUND, "open_website requires a browser target.")
    if _contains_followup_reference_unknown(targets):
        return _invalid(ErrorCode.FOLLOWUP_REFERENCE_UNCLEAR, "open_website follow-up target is unclear.")
    if _contains_unknown_targets(targets):
        return _invalid(ErrorCode.TARGET_NOT_FOUND, "open_website target is not resolved.")
    if not _all_targets_of_type(targets, {"browser"}):
        return _invalid(ErrorCode.UNSUPPORTED_TARGET, "open_website accepts only browser targets.")

    url = str(parameters.get("url", "")).strip()
    if not url:
        for target in targets:
            metadata = getattr(target, "metadata", None) or {}
            url = str(metadata.get("url", "")).strip()
            if url:
                break

    if not url:
        return _invalid(ErrorCode.MISSING_PARAMETER, "open_website requires a URL.")
    if not re.fullmatch(r"https?://\S+", url, flags=re.IGNORECASE):
        return _invalid(ErrorCode.MISSING_PARAMETER, "open_website URL must start with http:// or https://.")

    return _valid(command)


def _validate_window_intent(command: Command, targets: list[Any], intent_name: str) -> ValidationResult:
    if not targets:
        return _invalid(ErrorCode.TARGET_NOT_FOUND, f"{intent_name} requires a window target.")
    recent_target_error = _recent_target_followup_error(targets)
    if recent_target_error is not None:
        return recent_target_error
    if _contains_followup_reference_unknown(targets):
        return _invalid(ErrorCode.FOLLOWUP_REFERENCE_UNCLEAR, f"{intent_name} follow-up target is unclear.")
    if _contains_unknown_targets(targets):
        return _invalid(ErrorCode.TARGET_NOT_FOUND, f"{intent_name} target is not resolved.")
    if not _all_targets_of_type(targets, {"window"}):
        return _invalid(ErrorCode.UNSUPPORTED_TARGET, f"{intent_name} accepts only window targets.")
    if not _all_targets_resolved(targets):
        return _invalid(ErrorCode.TARGET_NOT_FOUND, f"{intent_name} target is not resolved.")
    return _valid(command)


def _validate_close_app(command: Command, targets: list[Any]) -> ValidationResult:
    if not targets:
        return _invalid(ErrorCode.TARGET_NOT_FOUND, "close_app requires an application target.")
    recent_target_error = _recent_target_followup_error(targets)
    if recent_target_error is not None:
        return recent_target_error
    if _contains_followup_reference_unknown(targets):
        return _invalid(ErrorCode.FOLLOWUP_REFERENCE_UNCLEAR, "close_app follow-up target is unclear.")
    if _contains_unknown_targets(targets):
        return _invalid(ErrorCode.TARGET_NOT_FOUND, "close_app target is not resolved.")
    if not _all_targets_of_type(targets, {"application"}):
        return _invalid(ErrorCode.UNSUPPORTED_TARGET, "close_app accepts only application targets.")
    if not _all_targets_resolved(targets):
        return _invalid(ErrorCode.TARGET_NOT_FOUND, "close_app target is not resolved.")
    return _valid(command)


def _validate_list_windows(command: Command, targets: list[Any]) -> ValidationResult:
    if len(targets) > 1:
        return _invalid(
            ErrorCode.MULTIPLE_MATCHES,
            "list_windows accepts at most one filter target.",
        )
    if _contains_followup_reference_unknown(targets):
        return _invalid(
            ErrorCode.FOLLOWUP_REFERENCE_UNCLEAR,
            "list_windows follow-up filter is unclear.",
        )
    if _contains_unknown_targets(targets):
        return _invalid(
            ErrorCode.TARGET_NOT_FOUND,
            "list_windows filter target is not resolved.",
        )
    if targets and not _all_targets_of_type(targets, {"window", "application"}):
        return _invalid(
            ErrorCode.UNSUPPORTED_TARGET,
            "list_windows accepts only window targets or an application filter.",
        )
    if targets and not _all_targets_resolved(targets):
        return _invalid(
            ErrorCode.TARGET_NOT_FOUND,
            "list_windows filter target is not resolved.",
        )
    return _valid(command)


def _validate_search_local(
    command: Command,
    targets: list[Any],
    parameters: dict[str, Any],
) -> ValidationResult:
    query = str(parameters.get("query", "")).strip()
    if not query:
        return _invalid(ErrorCode.MISSING_PARAMETER, "search_local requires a non-empty query.")
    if str(parameters.get("sort_hint", "")).strip() not in {"", "latest"}:
        return _invalid(ErrorCode.MISSING_PARAMETER, "search_local supports only the latest recency hint in MVP.")
    if str(parameters.get("file_type", "")).strip() not in {"", "markdown"}:
        return _invalid(ErrorCode.MISSING_PARAMETER, "search_local supports only the markdown file-type hint in MVP.")
    if parameters.get("filename_hint") is not None and not str(parameters.get("filename_hint", "")).strip():
        return _invalid(ErrorCode.MISSING_PARAMETER, "search_local filename hint must be non-empty when provided.")
    if _contains_followup_reference_unknown(targets):
        return _invalid(ErrorCode.FOLLOWUP_REFERENCE_UNCLEAR, "search_local follow-up scope is unclear.")
    if _contains_unknown_targets(targets):
        return _invalid(ErrorCode.TARGET_NOT_FOUND, "search_local scope target is not resolved.")
    if not targets and not str(parameters.get("scope_path", "")).strip():
        return _invalid(ErrorCode.TARGET_NOT_FOUND, "search_local requires an explicit folder scope.")
    if targets and not _all_targets_of_type(targets, {"folder"}):
        return _invalid(ErrorCode.UNSUPPORTED_TARGET, "search_local accepts only folder scope targets.")
    return _valid(command)


def _validate_prepare_workspace(
    command: Command,
    targets: list[Any],
    parameters: dict[str, Any],
) -> ValidationResult:
    workspace = str(parameters.get("workspace", "")).strip()
    sequence = parameters.get("sequence")
    if not targets and not sequence:
        return _invalid(
            ErrorCode.MISSING_PARAMETER,
            "prepare_workspace requires executable targets or a sequence.",
        )

    if _contains_followup_reference_unknown(targets):
        return _invalid(
            ErrorCode.FOLLOWUP_REFERENCE_UNCLEAR,
            "prepare_workspace follow-up scope is unclear.",
        )
    if _contains_unknown_targets(targets):
        return _invalid(
            ErrorCode.TARGET_NOT_FOUND,
            "prepare_workspace target is not resolved.",
        )
    if targets and not _all_targets_of_type(targets, {"application", "folder", "browser"}):
        return _invalid(
            ErrorCode.UNSUPPORTED_TARGET,
            "prepare_workspace accepts only application, folder, or browser targets.",
        )
    has_folder_target = _has_target_type(targets, TargetType.FOLDER.value)
    if not sequence and not has_folder_target:
        if workspace:
            return _invalid(
                ErrorCode.TARGET_NOT_FOUND,
                "prepare_workspace requires a resolved folder or project target.",
            )
        return _invalid(
            ErrorCode.MISSING_PARAMETER,
            "prepare_workspace requires a folder or project target.",
        )
    if not targets and workspace and not sequence:
        return _invalid(
            ErrorCode.MISSING_PARAMETER,
            "prepare_workspace needs explicit targets or sequence for the workspace.",
        )
    return _valid(command)


def _validate_clarify(command: Command) -> ValidationResult:
    raw_text = str(getattr(command, "raw_input", "")).strip().lower()
    if raw_text.endswith("?") or raw_text.startswith(("which", "what", "where", "how", "who")):
        return _valid(command)
    return _invalid(ErrorCode.MISSING_PARAMETER, "clarify intent requires a clear clarification phrase.")


def _validate_confirm(command: Command, parameters: dict[str, Any]) -> ValidationResult:
    response = str(parameters.get("response", "")).strip().lower()
    if response in {"approved", "denied", "pending"}:
        return _valid(command)

    raw_text = str(getattr(command, "raw_input", "")).strip().lower()
    if raw_text in {"yes", "yeah", "yep", "ok", "okay", "confirm", "continue", "cancel", "no", "nope", "stop"}:
        return _valid(command)

    return _invalid(ErrorCode.MISSING_PARAMETER, "confirm intent requires approved/denied-style input.")


def _all_targets_of_type(targets: list[Any], allowed_values: set[str]) -> bool:
    return all(_target_type_value(getattr(target, "type", "unknown")) in allowed_values for target in targets)


def _has_target_type(targets: list[Any], target_type: str) -> bool:
    return any(_target_type_value(getattr(target, "type", "unknown")) == target_type for target in targets)


def _all_targets_resolved(targets: list[Any]) -> bool:
    for target in targets:
        target_type = _target_type_value(getattr(target, "type", "unknown"))
        name = str(getattr(target, "name", "")).strip()
        path = str(getattr(target, "path", "") or "").strip()
        if target_type == TargetType.UNKNOWN.value:
            return False
        if target_type in {TargetType.FILE.value, TargetType.FOLDER.value}:
            if not (name or path):
                return False
        elif not name:
            return False
    return True


def _check_ambiguous_targets(targets: list[Any]) -> ValidationResult | None:
    for target in targets:
        metadata = getattr(target, "metadata", None) or {}
        if bool(metadata.get("ambiguous")):
            return _invalid(ErrorCode.MULTIPLE_MATCHES, "Multiple matching targets require clarification.")
    return None


def _contains_unknown_targets(targets: list[Any]) -> bool:
    return any(_target_type_value(getattr(target, "type", "unknown")) == TargetType.UNKNOWN.value for target in targets)


def _contains_followup_reference_unknown(targets: list[Any]) -> bool:
    for target in targets:
        target_type = _target_type_value(getattr(target, "type", "unknown"))
        metadata = getattr(target, "metadata", None) or {}
        if target_type == TargetType.UNKNOWN.value and bool(metadata.get("followup_reference")):
            return True
    return False


def _recent_target_followup_error(targets: list[Any]) -> ValidationResult | None:
    for target in targets:
        metadata = getattr(target, "metadata", None) or {}
        reason = str(metadata.get("recent_target_reference", "")).strip()
        if not reason:
            continue
        source_type = str(metadata.get("source_type", "")).strip()

        if reason == "missing_recent_target":
            return _invalid(
                ErrorCode.TARGET_NOT_FOUND,
                "No recent target is available for this follow-up.",
            )
        if reason == "missing_folder_context":
            return _invalid(
                ErrorCode.TARGET_NOT_FOUND,
                "No recent folder context is available for this follow-up.",
            )
        if reason == "unsupported_close_target":
            if source_type:
                return _invalid(
                    ErrorCode.UNSUPPORTED_TARGET,
                    f"Recent target type {source_type!r} is not closable in the current MVP action surface.",
                )
            return _invalid(
                ErrorCode.UNSUPPORTED_TARGET,
                "Recent target is not closable in the current MVP action surface.",
            )
        if reason == "ambiguous_recent_target":
            return _invalid(
                ErrorCode.MULTIPLE_MATCHES,
                "Recent target reference is ambiguous. Use a more explicit command.",
            )
    return None


def _search_result_followup_error(targets: list[Any]) -> ValidationResult | None:
    for target in targets:
        metadata = getattr(target, "metadata", None) or {}
        reason = str(metadata.get("search_result_reference", "")).strip()
        if not reason:
            continue

        requested_index = metadata.get("requested_index")
        available_count = metadata.get("available_count")
        result_type = str(metadata.get("result_type", "")).strip()

        if reason == "missing_context":
            return _invalid(
                ErrorCode.TARGET_NOT_FOUND,
                "No recent search results are available. Run a search first.",
            )
        if reason == "no_results":
            return _invalid(
                ErrorCode.TARGET_NOT_FOUND,
                "Recent search returned no results to open.",
            )
        if reason == "index_out_of_range":
            if isinstance(requested_index, int) and isinstance(available_count, int):
                return _invalid(
                    ErrorCode.TARGET_NOT_FOUND,
                    f"Search result {requested_index} is out of range (available: {available_count}).",
                )
            return _invalid(
                ErrorCode.TARGET_NOT_FOUND,
                "Selected search result index is out of range.",
            )
        if reason == "ambiguous_reference":
            if isinstance(available_count, int):
                return _invalid(
                    ErrorCode.MULTIPLE_MATCHES,
                    f"Multiple recent search results are available ({available_count}). Choose a specific result number.",
                )
            return _invalid(
                ErrorCode.MULTIPLE_MATCHES,
                "Recent search result reference is ambiguous. Choose a specific result number.",
            )
        if reason == "non_file_result":
            if result_type:
                return _invalid(
                    ErrorCode.UNSUPPORTED_TARGET,
                    f"Selected search result is a {result_type}, not a file.",
                )
            return _invalid(
                ErrorCode.UNSUPPORTED_TARGET,
                "Selected search result is not a file.",
            )
        if reason == "missing_parameter":
            return _invalid(
                ErrorCode.MISSING_PARAMETER,
                "open_file follow-up is missing a selectable search result reference.",
            )
    return None


def _intent_value(intent: Any) -> str:
    return str(getattr(intent, "value", intent))


def _target_type_value(target_type: Any) -> str:
    return str(getattr(target_type, "value", target_type))


def _valid(command: Command) -> ValidationResult:
    return ValidationResult(valid=True, validated_command=command, error=None)


def _invalid(code: ErrorCode, message: str) -> ValidationResult:
    return ValidationResult(
        valid=False,
        validated_command=None,
        error=JarvisError(
            category=ErrorCategory.VALIDATION_ERROR,
            code=code,
            message=message,
            details=None,
            blocking=True,
            terminal=False,
        ),
    )
