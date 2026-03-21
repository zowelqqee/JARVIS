"""Shared target contract for JARVIS MVP."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class TargetType(str, Enum):
    """Allowed target types for MVP commands and steps."""

    APPLICATION = "application"
    FILE = "file"
    FOLDER = "folder"
    WINDOW = "window"
    BROWSER = "browser"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class Target:
    """Resolved entity that an action can operate on."""

    type: TargetType
    name: str
    path: str | None = None
    metadata: dict[str, Any] | None = None

