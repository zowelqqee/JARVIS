"""Fixed desktop action names for JARVIS MVP."""

from __future__ import annotations

from enum import Enum


class DesktopAction(str, Enum):
    """Supported MVP desktop actions."""

    OPEN_APP = "open_app"
    FOCUS_APP = "focus_app"
    OPEN_FILE = "open_file"
    OPEN_FOLDER = "open_folder"
    OPEN_WEBSITE = "open_website"
    LIST_WINDOWS = "list_windows"
    FOCUS_WINDOW = "focus_window"
    CLOSE_WINDOW = "close_window"
    CLOSE_APP = "close_app"
    SEARCH_LOCAL = "search_local"
    PREPARE_WORKSPACE = "prepare_workspace"


DESKTOP_ACTIONS: tuple[str, ...] = tuple(action.value for action in DesktopAction)

