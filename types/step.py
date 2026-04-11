"""Shared execution step contract for JARVIS MVP."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from types.target import Target


class StepAction(str, Enum):
    """Supported MVP step actions."""

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
    PLAY_MUSIC = "play_music"


class StepStatus(str, Enum):
    """Allowed step lifecycle statuses."""

    PENDING = "pending"
    EXECUTING = "executing"
    DONE = "done"
    FAILED = "failed"


@dataclass(slots=True)
class Step:
    """One executable desktop step in ordered command flow."""

    id: str
    action: StepAction
    target: Target
    parameters: dict[str, Any] | None = None
    status: StepStatus = StepStatus.PENDING
    requires_confirmation: bool = False
