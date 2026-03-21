"""Short-lived session context contract for JARVIS MVP."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from types.command import Command
    from types.confirmation_request import ConfirmationResult
    from types.runtime_state import RuntimeState
    from types.step import StepStatus
    from types.target import Target


@dataclass(slots=True)
class SessionContext:
    """In-memory context used only for the active supervised session."""

    active_command: Command | None = None
    current_step_index: int | None = None
    step_statuses: dict[str, StepStatus] = field(default_factory=dict)
    runtime_state: RuntimeState | None = None
    last_resolved_targets: list[Target] = field(default_factory=list)
    recent_folder_context: Target | None = None
    recent_project_context: str | None = None
    recent_clarification_answer: str | None = None
    recent_confirmation_state: ConfirmationResult | None = None
    recent_workspace_context: str | None = None
    recent_primary_target: Target | None = None
    recent_primary_action: str | None = None
    recent_target_version: int = 0
    recent_search_results: list[dict[str, str]] = field(default_factory=list)
    recent_search_query: str | None = None
    recent_search_scope_path: str | None = None

    def set_active_command(self, command: Command | None) -> None:
        """Store the active command for the current supervised interaction."""
        self.active_command = command

    def get_active_command(self) -> Command | None:
        """Return the active command, if one is currently tracked."""
        return self.active_command

    def set_recent_targets(self, targets: list[Target] | None) -> None:
        """Store the most recent explicitly resolved targets."""
        self.last_resolved_targets = list(targets or [])
        self.recent_folder_context = None
        for target in reversed(self.last_resolved_targets):
            if _target_type_value(getattr(target, "type", "")) != "folder":
                continue
            self.recent_folder_context = target
            folder_context_value = str(getattr(target, "path", "") or "").strip() or str(getattr(target, "name", "")).strip()
            if folder_context_value:
                self.recent_project_context = folder_context_value
            break
        if self.last_resolved_targets:
            self.set_recent_primary_target(self.last_resolved_targets[-1], action=None)

    def get_recent_targets(self) -> list[Target]:
        """Return the recent explicit targets available for follow-ups."""
        return list(self.last_resolved_targets)

    def set_recent_folder_context(self, target: Target | None) -> None:
        """Store the recent explicit folder context for follow-up commands."""
        self.recent_folder_context = target
        if target is None:
            return
        folder_context_value = str(getattr(target, "path", "") or "").strip() or str(getattr(target, "name", "")).strip()
        if folder_context_value:
            self.recent_project_context = folder_context_value

    def get_recent_folder_context(self) -> Target | None:
        """Return the recent folder context when one is explicitly available."""
        return self.recent_folder_context

    def set_recent_project_context(self, context: str | None) -> None:
        """Store the recent explicit project descriptor for short follow-ups."""
        normalized = str(context or "").strip()
        self.recent_project_context = normalized or None

    def get_recent_project_context(self) -> str | None:
        """Return the recent project descriptor, if one is currently tracked."""
        return self.recent_project_context

    def set_execution_state(
        self,
        runtime_state: RuntimeState | str | None,
        current_step_index: int | None,
        step_statuses: dict[str, StepStatus] | None,
    ) -> None:
        """Store the current runtime state and visible step progress."""
        self.runtime_state = runtime_state
        self.current_step_index = current_step_index
        self.step_statuses = dict(step_statuses or {})

    def get_execution_state(self) -> dict[str, Any]:
        """Return the current runtime execution state snapshot."""
        return {
            "runtime_state": self.runtime_state,
            "current_step_index": self.current_step_index,
            "step_statuses": dict(self.step_statuses),
        }

    def set_recent_clarification_answer(self, answer: str | None) -> None:
        """Store the latest clarification reply used to unblock a command."""
        normalized = str(answer or "").strip()
        self.recent_clarification_answer = normalized or None

    def set_recent_confirmation_state(self, state: ConfirmationResult | None) -> None:
        """Store the latest confirmation state for the current supervised flow."""
        self.recent_confirmation_state = state

    def set_recent_workspace_context(self, context: str | None) -> None:
        """Store the recent workspace or app context established in-session."""
        normalized = str(context or "").strip()
        self.recent_workspace_context = normalized or None
        if not normalized:
            return

        intent = _intent_value(getattr(self.active_command, "intent", None))
        if intent in {"prepare_workspace", "open_folder", "search_local"} or _looks_like_project_context(normalized):
            self.recent_project_context = normalized

    def set_recent_primary_target(self, target: Target | None, action: str | None = None) -> None:
        """Store the most recent successful explicit target for narrow follow-ups."""
        if target is None:
            self.recent_primary_target = None
            self.recent_primary_action = None
            return

        cloned_target = _clone_target(target)
        self.recent_primary_target = cloned_target
        normalized_action = str(action or "").strip()
        self.recent_primary_action = normalized_action or None
        self.recent_target_version += 1

        target_type = _target_type_value(getattr(cloned_target, "type", ""))
        if target_type == "folder":
            self.set_recent_folder_context(cloned_target)
            return
        if target_type != "file":
            return

        target_path = str(getattr(cloned_target, "path", "") or "").strip()
        if not target_path:
            return
        parent = Path(target_path).expanduser().parent
        parent_text = str(parent).strip()
        if not parent_text:
            return
        folder_enum = getattr(getattr(cloned_target, "type", None).__class__, "FOLDER", None)
        if folder_enum is None:
            return
        self.set_recent_folder_context(
            type(cloned_target)(
                type=folder_enum,
                name=parent.name or parent_text,
                path=parent_text,
                metadata=None,
            ),
        )

    def get_recent_primary_target(self) -> Target | None:
        """Return the most recent successful explicit target when available."""
        if self.recent_primary_target is None:
            return None
        return _clone_target(self.recent_primary_target)

    def get_recent_primary_action(self) -> str | None:
        """Return the action that produced the current recent primary target."""
        return self.recent_primary_action

    def set_recent_search_results(
        self,
        matches: list[dict[str, Any]] | None,
        query: str | None = None,
        scope_path: str | None = None,
    ) -> None:
        """Store one short-lived ordered search result set for follow-up selection."""
        normalized_matches: list[dict[str, str]] = []
        for entry in list(matches or []):
            if not isinstance(entry, dict):
                continue
            path = str(entry.get("path", "")).strip()
            name = str(entry.get("name", "")).strip()
            match_type = str(entry.get("type", "")).strip()
            if not path and not name:
                continue
            normalized_entry: dict[str, str] = {}
            if name:
                normalized_entry["name"] = name
            if path:
                normalized_entry["path"] = path
            if match_type:
                normalized_entry["type"] = match_type
            normalized_matches.append(normalized_entry)

        self.recent_search_results = normalized_matches
        normalized_query = str(query or "").strip()
        normalized_scope = str(scope_path or "").strip()
        self.recent_search_query = normalized_query or None
        self.recent_search_scope_path = normalized_scope or None

    def get_recent_search_results(self) -> dict[str, Any] | None:
        """Return the most recent search result set for deterministic follow-ups."""
        if (
            not self.recent_search_results
            and not self.recent_search_query
            and not self.recent_search_scope_path
        ):
            return None
        return {
            "matches": [dict(entry) for entry in self.recent_search_results],
            "query": self.recent_search_query,
            "scope_path": self.recent_search_scope_path,
        }

    def clear_recent_search_results(self) -> None:
        """Clear recent search-result context used for numbered follow-up opens."""
        self.recent_search_results = []
        self.recent_search_query = None
        self.recent_search_scope_path = None

    def clear_expired_or_resettable_context(self, preserve_recent_context: bool = True) -> None:
        """Clear active execution state while optionally preserving recent follow-up context."""
        self.active_command = None
        self.current_step_index = None
        self.step_statuses = {}
        self.runtime_state = None
        self.recent_clarification_answer = None
        self.recent_confirmation_state = None
        if not preserve_recent_context:
            self.last_resolved_targets = []
            self.recent_folder_context = None
            self.recent_project_context = None
            self.recent_workspace_context = None
            self.recent_primary_target = None
            self.recent_primary_action = None
            self.recent_target_version = 0
            self.clear_recent_search_results()


def _target_type_value(target_type: Any) -> str:
    return str(getattr(target_type, "value", target_type))


def _intent_value(intent: Any) -> str:
    return str(getattr(intent, "value", intent))


def _looks_like_project_context(value: str) -> bool:
    lowered = value.lower()
    return value.startswith(("/", "~/", "./", "../")) or any(
        token in lowered for token in ("project", "workspace", "folder", "directory")
    )


def _clone_target(target: Target) -> Target:
    return type(target)(
        type=getattr(target, "type"),
        name=str(getattr(target, "name", "")),
        path=getattr(target, "path", None),
        metadata=dict(getattr(target, "metadata", None) or {}) or None,
    )
