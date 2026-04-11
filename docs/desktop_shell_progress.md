# Completed

- Implemented Phase 1 of `docs/desktop_shell_plan.md`.
- Added explicit desktop backend surface contracts for:
  - prompt actions
  - grounded answer sources and source attributions
  - structured result lists
  - command progress snapshots
  - transcript entry surfaces
- Updated the desktop presenter to map existing core visibility payloads into those explicit surface models.
- Kept the current desktop UI behavior backward-compatible by preserving the existing plain transcript text and metadata fields.
- Added a narrow presenter regression test covering question answers, confirmation prompts, and search-result command completion.
- Implemented Phase 2 of `docs/desktop_shell_plan.md`.
- Added structured transcript-card rendering for desktop conversation history via `TranscriptEntry.surface`.
- Desktop transcript cards now visibly render:
  - answer summaries
  - grounded sources
  - source attributions
  - command runtime progress
  - completed steps
  - structured search/window result lists
  - visible prompt reply options as non-interactive transcript content
- Updated the desktop theme so structured transcript cards fit the existing shell styling.
- Added focused widget/theme coverage for the new conversation rendering.
- Polished the desktop shell presentation for testing:
  - clearer transcript hierarchy
  - stronger runtime-state visibility
  - cleaner result-list presentation
  - tighter status-panel wording
  - more coherent shell/status-bar microcopy
  - better visual separation between user input, prompts, completions, failures, and warnings
- Implemented the actionable prompt/control layer.
- Prompt reply chips on transcript prompt cards are now clickable and submit through the same controller/input path as typed shell input.
- Added minimal shell controls in the status panel for:
  - cancel current flow
  - new session / reset
  - retry last prompt reply when the same prompt is still active and a stable explicit prior reply exists
- Status panel now surfaces:
  - current interaction mode
  - current runtime state
  - current request summary
  - next required user action
  - currently available controls
- Refactored the desktop composer into a unified voice-first shell surface.
- Voice input is now a default-visible primary action in the composer, with text input kept alongside it in the same surface.
- Added explicit composer voice states for:
  - ready
  - listening
  - submitting
  - issue / unavailable
- Desktop voice capture now reuses the existing one-shot voice input path and routes the recognized transcript back through the same supervised text submission flow as typed input.
- Voice capture stops active desktop speech output before listening starts so the shell does not talk over its own microphone turn.

# Changed Files

- `docs/desktop_shell_plan.md`
- `docs/desktop_shell_progress.md`
- `desktop/backend/view_models.py`
- `desktop/shell/widgets/conversation_view.py`
- `desktop/shell/widgets/transcript_entry_widget.py`
- `desktop/shell/widgets/status_panel.py`
- `desktop/shell/controllers/conversation_controller.py`
- `desktop/shell/theme.py`
- `desktop/backend/engine_facade.py`
- `desktop/backend/speech_service.py`
- `desktop/shell/widgets/composer.py`
- `tests_desktop/test_desktop_presenters.py`
- `tests_desktop/test_conversation_view.py`
- `tests_desktop/test_conversation_controller.py`
- `tests_desktop/test_app_shell.py`
- `tests_desktop/test_main_window.py`
- `tests_desktop/test_backend_facade.py`
- `tests_desktop/test_theme.py`

# Decisions Made

- Phase 1 stays backend-only: no widget, controller, layout, or shell-control work was started.
- Structured desktop surfaces are attached to `TranscriptEntry.surface` so later UI phases can render richer cards without changing routing/runtime behavior.
- `PendingPromptViewModel` now carries explicit `actions` in addition to the existing option strings to preserve current behavior and prepare for Phase 3.
- Structured search/window payloads are normalized into typed result-list view models in the presenter, not reinterpreted in the UI.
- Existing transcript `text`, `entry_kind`, and metadata were preserved so current tests and the current shell keep working during the transition.
- Phase 2 keeps the conversation flow entry-based; it does not introduce turn regrouping or a second transcript state model.
- Prompt actions are visible in the transcript as reply labels only; no interactive prompt controls were added in Phase 2.
- `ConversationView` now renders every entry through a custom item widget, but still preserves the existing list item count and stored item data.
- Search/window rendering consumes the typed presenter output from Phase 1 rather than rebuilding payload logic inside the widget layer.
- Shell polish work stays presentation-only: no routing, runtime, confirmation, or backend behavior changed.
- Prompt reply options remain visible-only chips during this polish pass; interactive controls are still Phase 3 work.
- Status and status-bar copy now prefer operator-facing language such as `Shell`, `State`, `Waiting on`, and `Suggested reply` instead of flatter generic labels.
- Prompt chips and cancel/retry controls all reuse the same `ConversationController.submit_text(...)` path as normal typed input.
- Reset/new session uses the existing `EngineFacade.reset_session()` hook rather than introducing a reset command into normal routing.
- Retry prompt is intentionally narrow: it is enabled only when the exact same pending prompt is still active and the shell has a prior explicit reply text for that prompt.
- No new prompt/control widget layer was added; Phase 3 builds directly on the existing transcript-card prompt surface and status panel.
- The composer now owns primary voice interaction hierarchy; the status panel still reports speech output state, but voice capture starts from the main composer surface.
- Desktop voice input stays explicit and bounded: one click starts one capture, the recognized transcript is submitted through the normal shell path, and no automatic follow-up capture was added.
- This slice reuses the existing macOS voice helper path rather than introducing a second desktop-specific capture stack.

# Remaining Work

- Phase 4: add controller/widget integration coverage and refresh desktop package docs.
- Refresh any remaining desktop docs that still describe the shell as text-first or speech-output-only.

# Do Not Change Next

- Do not change routing, runtime, confirmation, or question-answer policy for desktop-specific rendering work.
- Do not rework transcript rendering again when starting Phase 3; build prompt actions and shell controls on top of the current card-based conversation surface.
- Do not invent a second visibility contract in the UI layer; consume the typed presenter/view-model output added in Phase 1.
- Do not turn visible prompt replies into direct runtime mutations; Phase 3 must submit through the existing supervised input path.
- Do not broaden retry into hidden prompt replay or background recovery; it must stay an explicit re-submit of the same prior prompt reply through the normal shell path.
- Do not expand the new voice-first composer into continuous listening, automatic follow-up capture, or background microphone behavior.
- Do not bypass the normal shell submission path when refining voice UX; recognized voice text must keep flowing through the same supervised routing as typed text.
