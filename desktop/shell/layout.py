"""Layout composition helpers for the desktop shell."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from desktop.shell.widgets.composer import ComposerWidget
from desktop.shell.widgets.conversation_view import ConversationView
from desktop.shell.widgets.status_panel import StatusPanel


@dataclass(slots=True)
class ShellWidgets:
    """Named access to the main shell widgets."""

    conversation_view: ConversationView
    composer: ComposerWidget
    status_panel: StatusPanel


def build_shell_layout(parent: QWidget | None = None) -> tuple[QWidget, ShellWidgets]:
    """Build the top-level shell layout for the desktop window."""
    container = QWidget(parent)
    container.setObjectName("shellRoot")

    root_layout = QHBoxLayout(container)
    root_layout.setContentsMargins(20, 20, 20, 20)
    root_layout.setSpacing(18)

    left_column = QVBoxLayout()
    left_column.setSpacing(14)

    conversation_view = ConversationView(container)
    composer = ComposerWidget(container)
    status_panel = StatusPanel(container)
    conversation_view.setObjectName("conversationCard")
    composer.setObjectName("composerCard")
    status_panel.setObjectName("statusCard")

    left_column.addWidget(composer, stretch=0)
    left_column.addWidget(conversation_view, stretch=1)

    root_layout.addLayout(left_column, stretch=5)
    root_layout.addWidget(status_panel, stretch=2)

    widgets = ShellWidgets(
        conversation_view=conversation_view,
        composer=composer,
        status_panel=status_panel,
    )
    return container, widgets
