"""Main desktop shell window for JARVIS."""

from __future__ import annotations

from desktop.backend import EngineFacade
from desktop.shell.controllers import ConversationController
from desktop.shell.layout import ShellWidgets, build_shell_layout
from PySide6.QtWidgets import QMainWindow


class MainWindow(QMainWindow):
    """Top-level application window for the desktop UI shell."""

    def __init__(self, *, engine_facade: EngineFacade | None = None) -> None:
        super().__init__()
        self.setObjectName("mainWindow")
        self.setWindowTitle("JARVIS")
        self.resize(1100, 760)
        self.setMinimumSize(900, 600)
        self._widgets: ShellWidgets | None = None
        self._controller: ConversationController | None = None
        self._build_shell()
        self._wire_backend(engine_facade=engine_facade)

    @property
    def conversation_view(self):
        return self._widgets.conversation_view

    @property
    def composer(self):
        return self._widgets.composer

    @property
    def status_panel(self):
        return self._widgets.status_panel

    @property
    def controller(self):
        return self._controller

    def _build_shell(self) -> None:
        container, widgets = build_shell_layout(self)
        self._widgets = widgets
        self.setCentralWidget(container)
        self.statusBar().setObjectName("appStatusBar")
        self.statusBar().showMessage("Starting JARVIS...")

    def _wire_backend(self, *, engine_facade: EngineFacade | None) -> None:
        self._controller = ConversationController(
            engine_facade=engine_facade,
            conversation_view=self.conversation_view,
            composer=self.composer,
            status_panel=self.status_panel,
            status_sink=self.statusBar(),
        )
        self._controller.bind()
