"""Conversation history widget for the desktop shell."""

from __future__ import annotations

from typing import Any

from desktop.backend.view_models import TranscriptEntry
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget


class ConversationView(QWidget):
    """Read-only transcript surface for user and assistant messages."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build()

    @property
    def list_widget(self) -> QListWidget:
        """Expose the underlying list widget for tests and future controllers."""
        return self._list_widget

    def add_entry(
        self,
        *,
        role: str,
        text: str,
        entry_kind: str = "message",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Append one visible transcript entry."""
        normalized_text = str(text or "").strip()
        if not normalized_text:
            return
        item = QListWidgetItem(_entry_label(role=role, text=normalized_text))
        item.setData(
            Qt.ItemDataRole.UserRole,
            {
                "role": role,
                "entry_kind": entry_kind,
                "text": normalized_text,
                "metadata": dict(metadata or {}),
            },
        )
        self._list_widget.addItem(item)
        self._list_widget.scrollToBottom()
        self._sync_empty_state()

    def set_entries(self, entries: list[TranscriptEntry]) -> None:
        """Replace the visible transcript with one ordered entry list."""
        self.clear_entries()
        for entry in list(entries):
            self.add_entry(
                role=entry.role,
                text=entry.text,
                entry_kind=entry.entry_kind,
                metadata=entry.metadata,
            )

    def clear_entries(self) -> None:
        """Clear the transcript surface."""
        self._list_widget.clear()
        self._sync_empty_state()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        title = QLabel("Conversation", self)
        title.setObjectName("conversationTitle")

        subtitle = QLabel("Messages will appear here as you interact with JARVIS.", self)
        subtitle.setObjectName("conversationSubtitle")
        subtitle.setWordWrap(True)

        self._empty_state = QLabel("No messages yet.", self)
        self._empty_state.setObjectName("conversationEmptyState")
        self._empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._list_widget = QListWidget(self)
        self._list_widget.setObjectName("conversationList")
        self._list_widget.setAlternatingRowColors(False)
        self._list_widget.setSpacing(2)
        self._list_widget.setWordWrap(True)
        self._list_widget.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self._list_widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self._empty_state)
        layout.addWidget(self._list_widget, stretch=1)

        self._sync_empty_state()

    def _sync_empty_state(self) -> None:
        is_empty = self._list_widget.count() == 0
        self._empty_state.setVisible(is_empty)
        self._list_widget.setVisible(not is_empty)


def _entry_label(*, role: str, text: str) -> str:
    role_label = {
        "user": "You",
        "assistant": "JARVIS",
        "system": "System",
    }.get(str(role).strip().lower(), "JARVIS")
    return f"{role_label}: {text}"
