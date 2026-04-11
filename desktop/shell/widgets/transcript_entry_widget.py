"""Structured transcript entry renderer for the desktop shell."""

from __future__ import annotations

from pathlib import Path

from desktop.backend.view_models import (
    CommandProgressViewModel,
    EntrySurfaceViewModel,
    PromptActionViewModel,
    ResultListItemViewModel,
    ResultListViewModel,
    TranscriptEntry,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class TranscriptEntryWidget(QFrame):
    """Render one transcript entry as a structured desktop card."""

    action_requested = Signal(str)

    def __init__(self, entry: TranscriptEntry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._entry = entry
        self.setObjectName("transcriptEntryCard")
        self.setProperty("entryRole", _entry_role_value(entry.role))
        self.setProperty("surfaceKind", getattr(entry.surface, "surface_kind", ""))
        self.setProperty("entryKind", str(entry.entry_kind or "").strip().lower())
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 13, 15, 13)
        layout.setSpacing(10)

        layout.addLayout(self._header_row())

        surface = self._entry.surface
        summary_text = _summary_text(surface, self._entry.text)
        if summary_text:
            layout.addWidget(_build_label(summary_text, object_name="transcriptSummaryText"))

        primary_text = str(self._entry.text or "").strip()
        if primary_text:
            layout.addWidget(_build_label(primary_text, object_name="transcriptPrimaryText"))

        if surface is None:
            return

        command_progress = surface.command_progress
        if command_progress is not None:
            self._add_command_progress(layout, command_progress)

        if surface.sources:
            self._add_sources(layout, surface)

        if surface.source_attributions:
            self._add_source_attributions(layout, surface)

        if surface.result_lists:
            self._add_result_lists(layout, surface)

        if surface.actions:
            self._add_reply_actions(layout, surface.actions)

    def _header_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(_build_pill(_role_label(self._entry.role), "transcriptRolePill"), alignment=Qt.AlignmentFlag.AlignLeft)

        surface_label = _surface_label(self._entry.surface, self._entry.entry_kind)
        if surface_label:
            row.addWidget(_build_pill(surface_label, "transcriptSurfacePill"), alignment=Qt.AlignmentFlag.AlignLeft)
        runtime_label = _runtime_pill_label(self._entry.surface)
        if runtime_label:
            row.addWidget(_build_pill(runtime_label, "transcriptStatePill"), alignment=Qt.AlignmentFlag.AlignLeft)
        row.addStretch(1)
        return row

    def _add_command_progress(self, layout: QVBoxLayout, command_progress: CommandProgressViewModel) -> None:
        layout.addWidget(_build_section_heading("Runtime Feed"))
        layout.addWidget(
            _build_label(f"State: {_humanize_runtime_state(command_progress.runtime_state)}", object_name="transcriptSecondaryText")
        )
        if command_progress.command_summary:
            layout.addWidget(
                _build_label(f"Command: {command_progress.command_summary}", object_name="transcriptSecondaryText")
            )
        if command_progress.current_step:
            layout.addWidget(
                _build_label(f"Now: {command_progress.current_step}", object_name="transcriptSecondaryText")
            )
        if command_progress.completed_steps:
            layout.addWidget(_build_label("Completed:", object_name="transcriptSecondaryText"))
            for step in command_progress.completed_steps:
                layout.addWidget(_build_label(f"• {step}", object_name="transcriptListMeta"))
        if command_progress.blocked_reason:
            layout.addWidget(
                _build_label(f"Waiting on: {command_progress.blocked_reason}", object_name="transcriptSecondaryText")
            )
        if command_progress.next_step_hint:
            layout.addWidget(
                _build_label(f"Suggested reply: {command_progress.next_step_hint}", object_name="transcriptSecondaryText")
            )

    def _add_sources(self, layout: QVBoxLayout, surface: EntrySurfaceViewModel) -> None:
        layout.addWidget(_build_section_heading("Grounding"))
        for source in surface.sources:
            layout.addWidget(_build_label(f"• {source.label}", object_name="transcriptSecondaryText"))
            layout.addWidget(_build_label(source.path, object_name="transcriptListMeta"))

    def _add_source_attributions(self, layout: QVBoxLayout, surface: EntrySurfaceViewModel) -> None:
        layout.addWidget(_build_section_heading("Why These Sources"))
        for attribution in surface.source_attributions:
            prefix = attribution.source_label or Path(attribution.source_path).name or attribution.source_path
            layout.addWidget(_build_label(f"• {prefix}: {attribution.support}", object_name="transcriptSecondaryText"))

    def _add_result_lists(self, layout: QVBoxLayout, surface: EntrySurfaceViewModel) -> None:
        for result_list in surface.result_lists:
            self._add_result_list(layout, result_list)

    def _add_result_list(self, layout: QVBoxLayout, result_list: ResultListViewModel) -> None:
        layout.addWidget(_build_section_heading(result_list.title))
        if result_list.summary:
            layout.addWidget(_build_label(result_list.summary, object_name="transcriptSecondaryText"))
        for item in result_list.items:
            layout.addWidget(_build_result_item_widget(item))

    def _add_reply_actions(self, layout: QVBoxLayout, actions: tuple[PromptActionViewModel, ...]) -> None:
        layout.addWidget(_build_section_heading("Reply With"))
        chip_row = QHBoxLayout()
        chip_row.setContentsMargins(0, 0, 0, 0)
        chip_row.setSpacing(8)
        for action in actions:
            button = _build_action_button(action)
            if button is None:
                continue
            button.clicked.connect(lambda _checked=False, submit_text=action.submit_text: self.action_requested.emit(submit_text))
            chip_row.addWidget(button, alignment=Qt.AlignmentFlag.AlignLeft)
        chip_row.addStretch(1)
        layout.addLayout(chip_row)


def _build_pill(text: str, object_name: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName(object_name)
    return label


def _build_action_button(action: PromptActionViewModel) -> QPushButton | None:
    label = str(getattr(action, "label", "") or "").strip()
    submit_text = str(getattr(action, "submit_text", "") or "").strip()
    if not label or not submit_text:
        return None
    button = QPushButton(label)
    button.setObjectName("transcriptReplyChipButton")
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setToolTip(f'Submit "{submit_text}"')
    return button


def _build_section_heading(text: str) -> QLabel:
    return _build_label(text, object_name="transcriptSectionHeading")


def _build_label(text: str, *, object_name: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName(object_name)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def _build_result_item_widget(item: ResultListItemViewModel) -> QWidget:
    card = QFrame()
    card.setObjectName("transcriptResultItem")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(10, 8, 10, 8)
    layout.setSpacing(4)
    layout.addWidget(_build_label(item.title, object_name="transcriptResultItemTitle"))
    if item.subtitle:
        layout.addWidget(_build_label(item.subtitle, object_name="transcriptListMeta"))
    if item.detail:
        layout.addWidget(_build_label(item.detail, object_name="transcriptResultItemDetail"))
    return card


def _summary_text(surface: EntrySurfaceViewModel | None, primary_text: str) -> str | None:
    if surface is None:
        return None
    summary = str(surface.answer_summary or "").strip()
    if not summary:
        return None
    if summary == str(primary_text or "").strip():
        return None
    return summary


def _runtime_pill_label(surface: EntrySurfaceViewModel | None) -> str | None:
    command_progress = getattr(surface, "command_progress", None)
    if command_progress is None:
        return None
    return _humanize_runtime_state(command_progress.runtime_state)


def _humanize_runtime_state(value: str | None) -> str:
    normalized = str(value or "").strip().replace("_", " ")
    if not normalized:
        return ""
    words = normalized.split()
    return " ".join(word.capitalize() for word in words)


def _entry_role_value(role: str) -> str:
    normalized = str(role or "").strip().lower()
    if normalized in {"user", "assistant", "system"}:
        return normalized
    return "assistant"


def _role_label(role: str) -> str:
    normalized = _entry_role_value(role)
    if normalized == "user":
        return "You"
    if normalized == "system":
        return "System"
    return "JARVIS"


def _surface_label(surface: EntrySurfaceViewModel | None, entry_kind: str) -> str | None:
    if surface is not None:
        mapped = {
            "question_answer": "Question",
            "question_failure": "Question Failed",
            "clarification_prompt": "Clarification",
            "confirmation_prompt": "Confirmation",
            "command_progress": "Command",
            "command_completion": "Completed",
            "command_failure": "Failed",
            "command_blocked": "Blocked",
            "system_warning": "Warning",
        }.get(str(surface.surface_kind or "").strip())
        if mapped:
            return mapped
    normalized_kind = str(entry_kind or "").strip().lower()
    fallback = {
        "input": "Input",
        "answer": "Answer",
        "warning": "Warning",
        "error": "Error",
        "result": "Result",
        "status": "Status",
        "prompt": "Prompt",
    }.get(normalized_kind)
    return fallback or None
