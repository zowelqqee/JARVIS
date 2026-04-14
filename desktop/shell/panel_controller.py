"""
PanelController — wires PanelBridge signals to PanelWidget slots.

Signal flow:
  bridge.state_updated  ──→  panel.update_state
  panel.submitted       ──→  bridge.submit_text
  panel.prompt_confirmed      ──→  bridge.clear_pending_prompt
  panel.prompt_cancelled      ──→  bridge.clear_pending_prompt
  panel.clarification_submitted ──→  bridge.submit_text + clear_pending_prompt
"""
from __future__ import annotations

from desktop.backend.panel_bridge import PanelBridge
from desktop.shell.panel_widget   import PanelWidget


class PanelController:

    def __init__(self, bridge: PanelBridge, panel: PanelWidget) -> None:
        self._bridge = bridge
        self._panel  = panel
        self._bind()

    def _bind(self) -> None:
        # State flows down
        self._bridge.state_updated.connect(self._panel.update_state)

        # Events flow up
        self._panel.submitted.connect(self._bridge.submit_text)
        self._panel.prompt_confirmed.connect(self._on_confirmed)
        self._panel.prompt_cancelled.connect(self._on_cancelled)
        self._panel.clarification_submitted.connect(self._on_clarification)

        # Render initial state immediately
        self._panel.update_state(self._bridge.get_state())

    # ------------------------------------------------------------------ #
    # Handlers                                                             #
    # ------------------------------------------------------------------ #

    def _on_confirmed(self) -> None:
        self._bridge.clear_pending_prompt()

    def _on_cancelled(self) -> None:
        self._bridge.clear_pending_prompt()

    def _on_clarification(self, text: str) -> None:
        self._bridge.submit_text(text)
        self._bridge.clear_pending_prompt()
