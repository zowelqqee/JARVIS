"""Fixed capability metadata for deterministic question answering."""

from __future__ import annotations

SUPPORTED_COMMANDS: tuple[dict[str, str], ...] = (
    {"intent": "open_app", "description": "open or focus desktop applications"},
    {"intent": "open_file", "description": "open a local file"},
    {"intent": "open_folder", "description": "open a local folder"},
    {"intent": "open_website", "description": "open a URL in a browser"},
    {"intent": "list_windows", "description": "list open windows"},
    {"intent": "search_local", "description": "search local files and folders"},
    {"intent": "prepare_workspace", "description": "open a short predefined workspace setup"},
    {"intent": "close_app", "description": "close an application with confirmation when required"},
    {"intent": "close_window", "description": "close a window with confirmation when required"},
)

SUPPORTED_QUESTION_FAMILIES: tuple[str, ...] = (
    "capabilities",
    "runtime_status",
    "docs_rules",
    "repo_structure",
    "safety_explanations",
)

SAFE_ACTIONS: tuple[str, ...] = (
    "open_app",
    "open_file",
    "open_folder",
    "open_website",
    "list_windows",
    "search_local",
    "prepare_workspace",
)

SENSITIVE_ACTIONS: tuple[str, ...] = (
    "close_app",
    "close_window",
)

MAJOR_LIMITS: tuple[str, ...] = (
    "no hidden execution",
    "no background agents",
    "no internet-backed QA in v1",
    "no answer-triggered execution",
)
