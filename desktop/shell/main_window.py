"""
MainWindow — frameless panel window.

Width contract:
  min  360px
  pref 400px
  max  440px  (hard cap)

Height:
  default 520px
  min     420px

Always-on-top flag is NOT set by default — user positions the panel
alongside their workspace.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QWidget

from desktop.backend.panel_bridge    import PanelBridge
from desktop.shell.panel_widget      import PanelWidget
from desktop.shell.panel_controller  import PanelController
from desktop.shell.theme             import BG


class MainWindow(QMainWindow):

    def __init__(self, bridge: PanelBridge) -> None:
        super().__init__()

        # ── Window geometry & flags ─────────────────────────────────── #
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
        )
        self.setMinimumWidth(360)
        self.setMaximumWidth(440)
        self.setMinimumHeight(420)
        self.resize(400, 520)
        self.setWindowTitle("V.E.C.T.O.R.")

        # Prevent horizontal scroll / overflow at all costs
        self.setSizePolicy(
            self.sizePolicy().horizontalPolicy(),
            self.sizePolicy().verticalPolicy(),
        )

        # ── Dark background ─────────────────────────────────────────── #
        self.setStyleSheet(f"QMainWindow {{ background-color: {BG}; }}")

        # ── Panel ───────────────────────────────────────────────────── #
        self._panel = PanelWidget(self)
        self.setCentralWidget(self._panel)

        # ── Controller wires bridge ↔ panel ─────────────────────────── #
        self._controller = PanelController(bridge, self._panel)

        # No Qt status bar
        self.statusBar().setVisible(False)

    # ------------------------------------------------------------------ #
    # Expose panel for tests                                               #
    # ------------------------------------------------------------------ #

    @property
    def panel(self) -> PanelWidget:
        return self._panel
