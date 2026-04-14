"""Small persisted state store for protocol-friendly recent workspace context."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


_STATE_PATH_ENV = "JARVIS_PROTOCOL_STATE_PATH"
_DEFAULT_STATE_PATH = Path.home() / ".jarvis" / "state" / "protocol_state.json"
_FALLBACK_STATE_PATH = Path.cwd() / "tmp" / "runtime" / "protocol_state.json"


@dataclass(slots=True)
class ProtocolStateStore:
    """Persist a tiny cross-session protocol state snapshot."""

    path: Path = field(default_factory=lambda: _configured_state_path())

    def load(self) -> dict[str, Any]:
        """Return the current stored state or an empty baseline."""
        for candidate in self._candidate_paths():
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8"))
            except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError, ValueError):
                continue
            if isinstance(payload, dict):
                if candidate != self.path:
                    self.path = candidate
                return payload
        return {}

    def save(self, payload: dict[str, Any]) -> None:
        """Write the updated state atomically enough for the local MVP."""
        serialized = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(serialized, encoding="utf-8")
            return
        except OSError:
            if self.path == _FALLBACK_STATE_PATH:
                raise
        self.path = _FALLBACK_STATE_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(serialized, encoding="utf-8")

    def remember_command(self, command: object | None) -> None:
        """Persist recent workspace and protocol-friendly command context."""
        if command is None:
            return

        state = self.load()
        updated = dict(state)
        updated["last_seen_at"] = _utc_now_iso()
        updated["last_command_summary"] = _command_summary(command)

        intent = _intent_value(getattr(command, "intent", ""))
        if intent == "run_protocol":
            protocol_id = str(getattr(command, "parameters", {}).get("protocol_id", "") or "").strip()
            protocol_title = str(getattr(command, "parameters", {}).get("protocol_display_name", "") or "").strip()
            if protocol_id:
                updated["last_protocol_id"] = protocol_id
                updated["last_protocol_run_at"] = updated["last_seen_at"]
            if protocol_title:
                updated["last_protocol_title"] = protocol_title

        workspace = _workspace_payload(command)
        if workspace is not None:
            updated.update(workspace)

        if updated != state:
            self.save(updated)

    def template_context(self) -> dict[str, str]:
        """Return a safe string-only template context for protocol completion text."""
        state = self.load()
        stored_workspace_label = str(state.get("last_workspace_label", "") or "").strip()
        last_workspace_label = stored_workspace_label or "последний проект"
        last_workspace_path = str(state.get("last_workspace_path", "") or "").strip()
        last_git_branch = str(state.get("last_git_branch", "") or "").strip()
        last_work_summary = str(state.get("last_work_summary", "") or "").strip()
        if stored_workspace_label:
            branch_suffix_ru = _branch_suffix_ru(last_git_branch)
            branch_suffix_en = _branch_suffix_en(last_git_branch)
            last_project_sentence_ru = _stable_variant(
                (
                    f"В прошлый раз вы остановились на проекте {stored_workspace_label}{branch_suffix_ru}.",
                    f"Последним у вас был проект {stored_workspace_label}{branch_suffix_ru}.",
                    f"Помню, вы работали над проектом {stored_workspace_label}{branch_suffix_ru}.",
                ),
                seed=f"{stored_workspace_label}|{last_git_branch}|ru",
            )
            last_project_sentence_en = _stable_variant(
                (
                    f"You last stopped on {stored_workspace_label}{branch_suffix_en}.",
                    f"Your latest project was {stored_workspace_label}{branch_suffix_en}.",
                    f"I remember your recent project: {stored_workspace_label}{branch_suffix_en}.",
                ),
                seed=f"{stored_workspace_label}|{last_git_branch}|en",
            )
        else:
            last_project_sentence_ru = _stable_variant(
                (
                    "Последний проект я пока не успел запомнить.",
                    "Я пока не сохранил, над каким проектом вы работали в прошлый раз.",
                    "Историю последнего проекта я пока не собрал.",
                ),
                seed="missing_project|ru",
            )
            last_project_sentence_en = _stable_variant(
                (
                    "I have not remembered your last project yet.",
                    "I have not saved your previous project context yet.",
                    "I do not have your last project history yet.",
                ),
                seed="missing_project|en",
            )
        return {
            "last_workspace_label": last_workspace_label,
            "last_workspace_path": last_workspace_path,
            "last_git_branch": last_git_branch,
            "last_work_summary": last_work_summary,
            "branch_suffix": _branch_suffix_ru(last_git_branch),
            "branch_suffix_en": _branch_suffix_en(last_git_branch),
            "last_project_sentence_ru": last_project_sentence_ru,
            "last_project_sentence_en": last_project_sentence_en,
            "resume_context_ru": _resume_context_ru(last_git_branch=last_git_branch, last_work_summary=last_work_summary),
            "resume_context_en": _resume_context_en(last_git_branch=last_git_branch, last_work_summary=last_work_summary),
            "home_greeting_ru": "Приветствую, сэр.",
            "home_greeting_en": "Welcome home.",
        }

    def _candidate_paths(self) -> tuple[Path, ...]:
        if self.path == _FALLBACK_STATE_PATH:
            return (self.path,)
        return (self.path, _FALLBACK_STATE_PATH)


def _configured_state_path() -> Path:
    override = str(os.environ.get(_STATE_PATH_ENV, "") or "").strip()
    if override:
        return Path(override).expanduser()
    return _DEFAULT_STATE_PATH


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def _command_summary(command: object) -> str:
    intent = _intent_value(getattr(command, "intent", ""))
    parameters = dict(getattr(command, "parameters", {}) or {})
    if intent == "run_protocol":
        protocol_display_name = str(parameters.get("protocol_display_name", "") or "").strip()
        if protocol_display_name:
            return f"run_protocol: {protocol_display_name}"
    targets = list(getattr(command, "targets", []) or [])
    target_names = [str(getattr(target, "name", "") or "").strip() for target in targets if str(getattr(target, "name", "") or "").strip()]
    if target_names:
        return f"{intent}: {', '.join(target_names)}"
    return intent


def _workspace_payload(command: object) -> dict[str, str] | None:
    intent = _intent_value(getattr(command, "intent", ""))
    parameters = dict(getattr(command, "parameters", {}) or {})
    workspace_path = str(parameters.get("workspace_path", "") or "").strip()
    workspace_label = str(parameters.get("workspace_label", "") or "").strip()

    if not workspace_path:
        for target in list(getattr(command, "targets", []) or []):
            target_type = _target_type_value(getattr(target, "type", ""))
            if target_type != "folder":
                continue
            workspace_path = str(getattr(target, "path", "") or "").strip()
            workspace_label = workspace_label or str(getattr(target, "name", "") or "").strip()
            if workspace_path:
                break

    if not workspace_path:
        for target in list(getattr(command, "targets", []) or []):
            target_type = _target_type_value(getattr(target, "type", ""))
            if target_type != "file":
                continue
            file_path = str(getattr(target, "path", "") or "").strip()
            if not file_path:
                continue
            parent = Path(file_path).expanduser().parent
            workspace_path = str(parent).strip()
            workspace_label = workspace_label or parent.name or workspace_path
            if workspace_path:
                break

    if not workspace_path and intent not in {"prepare_workspace", "open_folder", "open_file"}:
        return None
    if not workspace_path:
        return None

    workspace_label = workspace_label or Path(workspace_path).name or workspace_path
    payload = {
        "last_workspace_path": workspace_path,
        "last_workspace_label": workspace_label,
        "last_workspace_opened_at": _utc_now_iso(),
        "last_work_summary": _command_summary(command),
    }
    git_branch = _git_branch_for_workspace(workspace_path)
    if git_branch:
        payload["last_git_branch"] = git_branch
    return payload


def _git_branch_for_workspace(workspace_path: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", workspace_path, "branch", "--show-current"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    branch = str(completed.stdout or "").strip()
    return branch or None


def _branch_suffix_ru(branch: str) -> str:
    normalized = str(branch or "").strip()
    return f", ветка {normalized}" if normalized else ""


def _branch_suffix_en(branch: str) -> str:
    normalized = str(branch or "").strip()
    return f", branch {normalized}" if normalized else ""


def _resume_context_ru(*, last_git_branch: str, last_work_summary: str) -> str:
    parts: list[str] = []
    normalized_branch = str(last_git_branch or "").strip()
    if normalized_branch:
        parts.append(f"Ветка: {normalized_branch}.")
    last_work_note = _humanized_last_work_note_ru(last_work_summary)
    if last_work_note:
        parts.append(last_work_note)
    return f" {' '.join(parts)}" if parts else ""


def _resume_context_en(*, last_git_branch: str, last_work_summary: str) -> str:
    parts: list[str] = []
    normalized_branch = str(last_git_branch or "").strip()
    if normalized_branch:
        parts.append(f"Branch: {normalized_branch}.")
    last_work_note = _humanized_last_work_note_en(last_work_summary)
    if last_work_note:
        parts.append(last_work_note)
    return f" {' '.join(parts)}" if parts else ""


def _humanized_last_work_note_ru(last_work_summary: str) -> str | None:
    intent, targets = _parsed_command_summary(last_work_summary)
    if intent == "open_file" and targets:
        return f"Последний файл: {targets[0]}."
    if intent == "run_protocol" and targets:
        return f"Последний протокол: {targets[0]}."
    return None


def _humanized_last_work_note_en(last_work_summary: str) -> str | None:
    intent, targets = _parsed_command_summary(last_work_summary)
    if intent == "open_file" and targets:
        return f"Last file: {targets[0]}."
    if intent == "run_protocol" and targets:
        return f"Last protocol: {targets[0]}."
    return None


def _parsed_command_summary(summary: str) -> tuple[str, list[str]]:
    normalized = str(summary or "").strip()
    if not normalized:
        return "", []
    intent, separator, target_blob = normalized.partition(":")
    if not separator:
        return intent.strip(), []
    targets = [part.strip() for part in target_blob.split(",") if part.strip()]
    return intent.strip(), targets


def _stable_variant(options: tuple[str, ...], *, seed: str) -> str:
    if not options:
        return ""
    if len(options) == 1:
        return options[0]
    normalized_seed = str(seed or "").strip()
    if not normalized_seed:
        return options[0]
    checksum = sum(ord(char) for char in normalized_seed)
    return options[checksum % len(options)]


def _intent_value(intent: Any) -> str:
    return str(getattr(intent, "value", intent))


def _target_type_value(target_type: Any) -> str:
    return str(getattr(target_type, "value", target_type))
