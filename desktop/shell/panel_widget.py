"""
PanelWidget — the single vertical panel container.

Assembles the 6 sections in the fixed order specified in the layout contract:

  1. TitlebarWidget        — always visible
  2. StateRowWidget        — always visible
  3. CurrentActionWidget   — always visible
  [4. PromptZoneWidget]    — conditional, inserted/removed at index 3
  5. LastExchangeWidget    — always visible
  6. InputBarWidget        — always visible

A stretch spacer between CurrentAction and LastExchange fills the gap
when no PromptZone is present.

Signals propagated to PanelController:
  submitted(str)                — from InputBar
  prompt_confirmed()            — from PromptZone
  prompt_cancelled()            — from PromptZone
  clarification_submitted(str)  — from PromptZone
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from desktop.backend.view_models import PanelState, PendingPrompt
from desktop.shell.widgets.titlebar       import TitlebarWidget
from desktop.shell.widgets.state_row      import StateRowWidget
from desktop.shell.widgets.current_action import CurrentActionWidget
from desktop.shell.widgets.prompt_zone    import PromptZoneWidget
from desktop.shell.widgets.last_exchange  import LastExchangeWidget
from desktop.shell.widgets.input_bar      import InputBarWidget
from desktop.shell.theme import BG


class PanelWidget(QWidget):

    submitted               = Signal(str)
    prompt_confirmed        = Signal()
    prompt_cancelled        = Signal()
    clarification_submitted = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {BG};")
        self._prompt_zone: PromptZoneWidget | None = None
        self._build()

    # ------------------------------------------------------------------ #
    # Build                                                                #
    # ------------------------------------------------------------------ #

    def _build(self) -> None:
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        self._titlebar       = TitlebarWidget(self)
        self._state_row      = StateRowWidget(self)
        self._current_action = CurrentActionWidget(self)
        # index 3 = stretch (shifts when PromptZone is inserted)
        self._last_exchange  = LastExchangeWidget(self)
        self._input_bar      = InputBarWidget(self)

        self._layout.addWidget(self._titlebar)       # index 0
        self._layout.addWidget(self._state_row)      # index 1
        self._layout.addWidget(self._current_action) # index 2
        self._layout.addStretch(1)                   # index 3 — fills gap
        self._layout.addWidget(self._last_exchange)  # index 4
        self._layout.addWidget(self._input_bar)      # index 5

        # Wire InputBar signal up
        self._input_bar.submitted.connect(self.submitted)

    # ------------------------------------------------------------------ #
    # Public — called by PanelController on every state update            #
    # ------------------------------------------------------------------ #

    def update_state(self, state: PanelState) -> None:
        self._titlebar.update_state(state.runtime_state)
        self._state_row.update_state(state.mode, state.runtime_state)
        self._current_action.update_text(state.current_action_text, state.runtime_state)
        self._sync_prompt_zone(state.pending_prompt)
        self._last_exchange.update_exchange(state.last_user, state.last_vector)
        self._input_bar.update_state(state.runtime_state)

    # ------------------------------------------------------------------ #
    # Prompt Zone lifecycle — contract: insert/remove from widget tree    #
    # ------------------------------------------------------------------ #

    def _sync_prompt_zone(self, prompt: PendingPrompt | None) -> None:
        if prompt is not None and self._prompt_zone is None:
            # Create and insert at index 3 (before the stretch spacer)
            self._prompt_zone = PromptZoneWidget(self)
            self._prompt_zone.confirmed.connect(self.prompt_confirmed)
            self._prompt_zone.cancelled.connect(self.prompt_cancelled)
            self._prompt_zone.clarification_submitted.connect(
                self.clarification_submitted
            )
            self._layout.insertWidget(3, self._prompt_zone)
            self._prompt_zone.set_prompt(prompt)
            self._prompt_zone.show()

        elif prompt is not None and self._prompt_zone is not None:
            # Update existing zone (prompt content may have changed)
            self._prompt_zone.set_prompt(prompt)

        elif prompt is None and self._prompt_zone is not None:
            # Remove from layout entirely — no placeholder, no gap
            self._layout.removeWidget(self._prompt_zone)
            self._prompt_zone.deleteLater()
            self._prompt_zone = None
