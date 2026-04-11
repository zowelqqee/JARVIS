"""Shared command contract for JARVIS MVP."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from types.step import Step
    from types.target import Target


class IntentType(str, Enum):
    """Fixed MVP intent labels."""

    OPEN_APP = "open_app"
    OPEN_FILE = "open_file"
    OPEN_FOLDER = "open_folder"
    OPEN_WEBSITE = "open_website"
    SWITCH_WINDOW = "switch_window"
    CLOSE_WINDOW = "close_window"
    CLOSE_APP = "close_app"
    LIST_WINDOWS = "list_windows"
    SEARCH_LOCAL = "search_local"
    PREPARE_WORKSPACE = "prepare_workspace"
    RUN_PROTOCOL = "run_protocol"
    CLARIFY = "clarify"
    CONFIRM = "confirm"


@dataclass(slots=True)
class Command:
    """Parsed command object used across parser, validator, planner, and runtime."""

    raw_input: str
    intent: IntentType
    targets: list[Target] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    requires_confirmation: bool = False
    execution_steps: list[Step] = field(default_factory=list)
    status_message: str = ""
