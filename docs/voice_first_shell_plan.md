# Current Voice/Shell Integration Points

- `desktop/shell/widgets/composer.py` already contains the shell’s explicit voice-input control surface:
  - primary `voice_requested` signal
  - voice state pill and detail text
  - parallel text input and send button in the same widget
- `desktop/shell/controllers/conversation_controller.py` already binds `voice_requested` to `start_voice_capture()`, sets visible composer voice states (`listening`, `routing`, `error`), and submits recognized speech through the same supervised text path as typed input.
- `desktop/backend/engine_facade.py` already owns the desktop voice capture call by stopping active TTS and calling `voice.session.capture_cli_voice_turn()`, then returning recognized text to the controller.
- `desktop/shell/layout.py` already mounts the composer, conversation view, and status panel into one shell layout.
- `desktop/shell/main_window.py` already exposes the shell widgets and wires the controller on startup.
- `desktop/shell/widgets/status_panel.py` already exposes supporting speech controls/state for the shell, but it is not the voice capture surface.
- `voice/speech_presenter.py` already handles spoken completion/failure text downstream; this plan should keep that path unchanged.

# What Is Currently Missing In The Shell For Voice-First Use

- The shell is still page-level transcript-first: `desktop/shell/layout.py` puts `ConversationView` above `ComposerWidget`, so the voice composer is not the first interaction surface on launch.
- The current composer copy is generic (`Speak or Type`, `Voice Input`) and does not point directly at the shipped hero-flow phrases like `start work` and `resume work`.
- The controller resets the composer back to a generic ready state after bind/reset/capture; it does not re-seed a stronger voice-first prompt for the current hero flow.
- The status panel shows speech output state and controls, but it does not help reinforce that voice capture is the primary way to begin the current hero flow.

# Smallest Coherent Layout/Control Change

- Move `ComposerWidget` above `ConversationView` in the main shell column so voice capture is the first visible interaction surface at launch.
- Keep the existing single composer widget and same voice/text submission path; do not add a second voice control surface.
- Update the composer’s ready-state hierarchy and microcopy so the primary action is clearly:
  - click to listen
  - say `start work` or `resume work`
  - use text in the same composer as the secondary path
- Have the controller restore a hero-flow-oriented ready/detail state after bind, reset, and completed voice submission instead of falling back to only generic copy.
- Keep the status panel as a supporting runtime surface with speech toggle/state, not the primary place to start voice capture.

# Exact Files To Change

- `desktop/shell/layout.py` - move the composer to the top of the left column and adjust stretch so it stays clearly visible above the transcript.
- `desktop/shell/widgets/composer.py` - tighten the voice-first hierarchy and microcopy around the shipped hero phrases while keeping text in the same surface.
- `desktop/shell/controllers/conversation_controller.py` - seed and restore the composer’s ready/detail state with hero-flow-specific voice guidance on bind/reset/post-capture.
- `desktop/shell/main_window.py` - apply any minimal startup focus/default-control adjustment needed so the promoted composer feels primary on launch.
- `desktop/shell/widgets/status_panel.py` - reduce competing voice emphasis to supporting copy only if needed for the promoted composer to remain the obvious primary entry point.
- `tests_desktop/test_main_window.py` - lock the visible shell composition and promoted voice control labels.
- `tests_desktop/test_conversation_controller.py` - lock hero-flow-oriented ready-state resets while preserving the current voice capture submission path.

# Non-Goals

- No continuous listening, wake word, background microphone behavior, or automatic follow-up capture.
- No routing/runtime changes for command vs question handling.
- No new hero flow and no change to the existing `start work / resume work` execution behavior.
- No redesign of transcript/result surfaces beyond what is needed to promote the existing composer.
- No new voice controls outside the current composer/controller/facade path.

# Acceptance Criteria

- On launch, the desktop shell shows the composer before the transcript at the default window size.
- The composer makes `Start Listening` the clearest primary action and explicitly suggests `start work` / `resume work` as the current voice entry phrases.
- Text input remains available in the same composer as a secondary path.
- Voice capture still runs through the existing path:
  `ComposerWidget` -> `ConversationController.start_voice_capture()` -> `EngineFacade.capture_voice_text()` -> normal `submit_text()` flow.
- Existing blocked states, confirmations, and question-mode behavior remain unchanged.
- After bind, reset, and a completed voice submission, the composer returns to a clear hero-flow-oriented ready state instead of a generic idle prompt.
