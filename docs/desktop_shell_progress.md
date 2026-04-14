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
- Implemented the first real `start work / resume work` hero flow.
- `start work on <workspace>` now routes into the existing supervised `prepare_workspace` path with `Visual Studio Code` as the only default app target for this hero phrase.
- Bare `start work` now blocks explicitly on `What workspace should I prepare?` and continues the same supervised command after the user replies.
- Added a built-in `Resume Work` protocol for bare `resume work` using the existing remembered-workspace state and `open_last_workspace`.
- `resume work` now fails visibly and honestly when no remembered workspace exists yet, with a direct next-step hint to run `start work on <workspace>` first.
- Runtime completion and shell visibility now use hero-flow-specific summaries such as `start_work: ...`, `resume_work: last workspace`, and `Workspace ready: ... in Visual Studio Code.`
- Successful workspace-open steps now backfill the resolved folder path into the active command before protocol-state persistence, so named workspace opens can seed later `resume work`.
- Added focused coverage for routing, parse/validate behavior, runtime clarification continuation, resume-work success/failure, and spoken protocol output.
- Enhanced `resume work` to surface one more layer of remembered work context from the existing protocol state.
- `resume work` completion now adds remembered git branch when available.
- `resume work` completion now adds a short remembered last-work note when the existing stored `last_work_summary` can be rendered cleanly, such as a previously opened file or protocol.
- Workspace-only resume still falls back to the existing clean completion text when no extra remembered context is available.
- Added focused protocol-state coverage for the new resume-context template fields and fallback behavior.
- Restored the desktop shell’s voice-first interaction hierarchy for the current hero flow.
- The unified composer now appears above the transcript as the primary default-visible shell surface.
- Composer ready-state copy now explicitly guides the user toward `start work` and `resume work` while keeping typed input in the same surface.
- Controller voice-state resets now return to hero-flow guidance after bind, new-session reset, and completed voice capture instead of falling back to generic idle copy.
- Added focused desktop coverage for composer-first layout and hero-flow voice-ready resets.
- Fixed stale remembered workspace failure path for `resume work`.
- `resume work` now fails early at the validator stage when the remembered workspace path is in state but no longer exists on disk.
- The shell shows a clear, workspace-specific failure message ("The remembered workspace X no longer exists at the stored path. Run 'start work on <workspace>' to set a new one.") instead of leaking a raw executor TARGET_NOT_FOUND error.
- Added a defense-in-depth TARGET_NOT_FOUND fallback message in the visibility mapper for the resume_work protocol in case a stale path reaches execution.
- Both `_specific_failure_next_step_hint` cases for resume_work TARGET_NOT_FOUND now return a correct "start work on <workspace>" hint instead of the wrong "Try a known protocol name." guidance.
- Added a focused runtime test that seeds a stale workspace path and asserts the new honest failure message and hint.

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
- `clarification/clarification_handler.py`
- `interaction/interaction_router.py`
- `parser/command_parser.py`
- `protocols/builtin_protocols.py`
- `protocols/state_store.py`
- `runtime/runtime_manager.py`
- `ui/visibility_mapper.py`
- `voice/speech_presenter.py`
- `tests/test_interaction_router.py`
- `tests/test_parser_validator_contract.py`
- `tests/test_protocol_registry.py`
- `tests/test_protocol_runtime.py`
- `tests/test_protocol_state_store.py`
- `tests/test_protocol_speech.py`
- `tests_desktop/test_desktop_presenters.py`
- `tests_desktop/test_conversation_view.py`
- `tests_desktop/test_conversation_controller.py`
- `tests_desktop/test_app_shell.py`
- `tests_desktop/test_main_window.py`
- `tests_desktop/test_backend_facade.py`
- `tests_desktop/test_theme.py`
- `desktop/shell/layout.py`
- `validator/command_validator.py`
- `ui/visibility_mapper.py`
- `tests/test_protocol_runtime.py`
- `tests_desktop/test_desktop_presenters.py`
- `desktop/README.md`

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
- The hero flow stays intentionally narrow: `start work` is a thin phrase alias over `prepare_workspace`, and `resume work` is a small built-in protocol instead of a new workflow system.
- Clarification replies for bare `start work` keep going through the existing supervised command flow; there is no direct mutation or hidden workspace selection outside the normal runtime path.
- Remembered workspace state now comes from the actual resolved `open_folder` execution result, not just the initial parsed target text.
- `resume work` depends only on the existing protocol state store and does not introduce any broader memory or background recovery behavior.
- The resume enhancement stays text-only: it enriches the existing completion/result surface from stored state instead of adding a new restore action or shell control.
- `resume work` only surfaces remembered last-work context when the existing stored summary can be rendered clearly; it does not invent synthetic context when the stored summary is too generic.
- Voice-first shell promotion stays layout-and-copy only: the composer becomes the first surface, but voice capture still uses the existing bounded one-shot path and the same supervised submission flow.

- Completed Phase 4 of `docs/desktop_shell_plan.md`.
- Added presenter tests for the two previously untested surfaces: clarification prompt and command failure.
- Added a presenter test for window results (list_windows command completion).
- All Phase 4 acceptance criteria are now covered: question rendering, confirmation/clarification prompting, command failure/completion visibility, cancel/reset control behavior.
- Rewrote `desktop/README.md` from the stale "Step 1 scaffold" stub to an accurate description of the current shell: hero flow, layout, composer voice states, shell controls, package structure, and test coverage table.

# Input Interpreter — First Slice (Completed)

- Implemented `input/input_interpreter.py`: LLM-assisted input normalization layer sitting between voice normalization and the deterministic router.
- `InterpretedInput` dataclass with all fields from the plan: `normalized_text`, `routing_hint`, `intent_hint`, `entity_hints`, `confidence`, `debug_note`, `skipped`, `raw_input_seen`.
- `InputInterpreter.interpret()` is stateless, fail-safe, and wraps all exceptions — no error ever propagates to the user.
- Hard safety boundaries enforced in code:
  1. Questions never become commands (`question_command_conflict` skip).
  2. Entities are grounded in raw input before passing downstream (alias-aware check against `_APP_ALIASES`).
  3. Low-confidence outputs (`< 0.70`) never substitute normalized text (`low_confidence` skip).
  4. `routing_hint = "unclear"` causes full discard of interpreter output (`unclear` skip).
- Deterministic match guard skips the LLM call entirely for canonical inputs (question starters, reply words, direct command starters with no natural speech markers) — `skip_reason="deterministic_match"`, `latency_ms=0`.
- All failure modes fall back to original text silently: `timeout`, `api_error`, `malformed_response`, `low_confidence`, `unclear`, `question_command_conflict`, `entity_grounding_failed`, `disabled`.
- `JARVIS_INTERPRETER_DISABLED=1` env flag bypasses the interpreter completely; existing pipeline is bit-for-bit identical.
- `_INTERPRETER_CONFIDENCE_THRESHOLD = 0.70` and `_INTERPRETER_MAX_LENGTH_MULTIPLIER = 3` are named constants.
- Wired into `interaction/interaction_manager.py` between `_resolve_pending_interaction_decision()` and `route_interaction()`. `routed_input` replaces `raw_input` downstream when interpreter fires and confidence ≥ 0.70.
- Debug trace: when `JARVIS_QA_DEBUG=1`, the full interpreter result (all plan-specified fields including `latency_ms`, `normalized_text_used`, `skip_reason`) is attached under `"interpreter_result"` in the debug trace. `"normalized_input"` also added to `"routing_decision"` entry for three-value comparison.
- Added `tests/test_input_interpreter.py` with 28 tests: unit tests for all 8 failure modes, forbidden-example regression tests, integration smoke tests verifying hero-flow normalization with mocked API. All pass.
- Zero regressions in existing test suite (9 pre-existing failures confirmed unchanged with `JARVIS_INTERPRETER_DISABLED=1`).

# Input Interpreter — Mismatch Fixes (Completed)

Fixed the 3 highest-impact behavior mismatches identified in the interpreter evaluation.

**Fix 1 — Clarification/confirmation replies bypass the interpreter (`runtime_blocked`).**
- Added runtime-state check in `interaction/interaction_manager.py` before calling the interpreter.
- When `runtime_manager.current_state` is `awaiting_clarification` or `awaiting_confirmation`, interpreter is skipped entirely with `skip_reason="runtime_blocked"` (recorded in debug trace).
- Prevents the stateless interpreter from rewriting bare workspace names or short clarification replies as standalone commands.

**Fix 2 — Polite command forms for v1 intents reach the interpreter.**
- Added `_POLITE_COMMAND_SUBJECTS` / `_POLITE_V1_COMMAND_VERBS` constants and `_is_polite_v1_command()` helper in `input/input_interpreter.py`.
- Verbs included: `"resume"`, `"start work"`, `"start working"` — only the verbs missing from the router's own `_POLITE_COMMAND_PREFIXES`.
- `_looks_like_deterministic_match()` now checks polite V1 command forms before the question-starter check, so `"can you resume my work"` is no longer short-circuited as a question.
- `_is_question_input()` (safety boundary 1) also exempts polite V1 command forms, so the LLM's `routing_hint="command"` for these inputs is not blocked by `question_command_conflict`.
- `"can you open Chrome"` remains a deterministic_match: `"open "` is excluded from `_POLITE_V1_COMMAND_VERBS` because the router already handles `"can you open "` correctly.
- Genuine questions like `"can JARVIS remember things?"` remain deterministic_match questions (no V1 verb match).

**Fix 3 — `"resume ... on <workspace>"` has a deterministic v1 normalization rule.**
- Added `_RESUME_ON_PATTERN = re.compile(r'\bresume\b.*?\bon\s+(\S.*)', re.IGNORECASE)` constant.
- In `interpret()`, pattern is checked before the deterministic_match guard. When matched, returns `"start work on <workspace>"` with `confidence=1.0`, no LLM call (`latency_ms=0`).
- `_looks_like_deterministic_match()` returns `False` for inputs matching `^resume\b.*\bon\s+\S`, so `"resume work on JARVIS"` (which starts with the canonical `"resume work"` prefix) is caught by the rule instead of being skipped unchanged.
- `"resume my work"` (no `"on X"` part) is unaffected — goes to the LLM as before.
- `"resume work"` (exact canonical) remains a deterministic_match — unaffected.

**Tests added:** 16 new tests across `Fix1RuntimeBlockedTests`, `Fix2PolitCommandTests`, `Fix3ResumeOnWorkspaceTests` in `tests/test_input_interpreter.py`. All 44 interpreter tests pass. Zero new regressions in broader suite.

# Input Interpreter — Router Polite-Command Fix (Completed)

- Added four missing polite command prefixes to `_POLITE_COMMAND_PREFIXES` in `interaction/interaction_router.py`:
  `"can you resume "`, `"could you resume "`, `"would you resume "`, `"please resume "`.
- These were the only hero-flow verb forms absent from the router's existing polite-prefix list.
  All other polite verbs (open/launch/start/close/find/search) were already present.
- With this fix, `"can/could/would you resume work"` and `"please resume work"` route as COMMAND
  at confidence 0.95 (`_looks_like_polite_command` path) independent of the interpreter.
  The interpreter's fix-2 polite-command handling now has the router as a guaranteed fallback.
- Added `test_polite_resume_forms_route_to_command` and `test_how_does_resume_work_stays_question`
  to `tests/test_interaction_router.py`. All 100 router+interpreter+manager tests pass.
  Zero new regressions in full suite.

# Dialogue Substrate — First Slice (Completed)

Implemented the three narrowest high-impact dialogue behaviors from `docs/dialogue_substrate_plan.md`.

**Clarification repair.**
- Added `clarification_was_applied(before, after)` to `clarification/clarification_handler.py` — detects when `apply_clarification` made no meaningful change to intent, targets, or parameters.
- Added `clarification_retry_count: int` and `last_clarification_message: str | None` fields to `RuntimeManager`.
- In `_handle_clarification_reply`: when `apply_clarification` patches nothing, the first failure re-asks with "I didn't catch that — <original question>". A second consecutive failure cancels the command with an honest message.
- Retry count resets on successful resolution, command cancellation, new command, and `clear_runtime`.
- The original clarification message is saved when a clarification is first issued, so re-asks are faithful to the original prompt.

**Narrow correction turn.**
- Added `try_apply_correction(command, reply)` to `clarification/clarification_handler.py` — handles "the other one" / "wrong one" / "другой" / etc. when the active clarification has exactly 2 MULTIPLE_MATCHES candidates.
- Called in `_handle_clarification_reply` before `apply_clarification`. Fires only for the exact 2-candidate case with a known correction phrase; everything else falls through to the normal clarification path.

**Voice near-miss recovery.**
- Added `pending_near_miss_phrase: str | None` field and `reset_dialogue_state()` method to `InteractionManager`.
- Added `is_voice_input: bool = False` (keyword-only) to `InteractionManager.handle_input`, threaded through `dispatch_interaction_input`, `EngineFacade.submit_text`, and `ConversationController._submit_via_shell`. Controller's `start_voice_capture` now passes `is_voice_input=True`.
- When the interpreter returns confidence in `[0.55, 0.70)` on voice input with a command routing hint and a rewritten phrase, a "Did you mean: '...'" prompt is surfaced (PendingPromptViewModel with Yes/No chips) instead of routing silently. The canonical phrase is stored in `pending_near_miss_phrase`.
- "Yes" → routes the canonical phrase as a fresh command and clears pending state. "No" → clears pending state and returns an informational message ("Okay — say it again whenever you're ready."). Unrecognised reply → re-surfaces the same prompt.
- `reset_dialogue_state()` is called from `EngineFacade.reset_session()` to clear near-miss state on session reset.

# Changed Files (Dialogue Substrate Slice)

- `clarification/clarification_handler.py` — added `clarification_was_applied`, `try_apply_correction`, `_CORRECTION_PHRASES`, `_targets_fingerprint` helpers.
- `runtime/runtime_manager.py` — added `clarification_retry_count` and `last_clarification_message` fields; updated `set_active_command`, `clear_runtime`, `_validate_and_continue`, `_handle_clarification_reply`.
- `interaction/interaction_manager.py` — added `pending_near_miss_phrase` field, `reset_dialogue_state`, `_handle_near_miss_reply`, `_build_near_miss_result`, `_build_near_miss_dismissed_result`; added `is_voice_input` param to `handle_input`; near-miss detection in interpreter branch.
- `voice/dispatcher.py` — added `is_voice_input=False` to `dispatch_interaction_input`, forwarded to `handle_input`.
- `desktop/backend/engine_facade.py` — added `is_voice_input=False` to `submit_text`; calls `reset_dialogue_state` in `reset_session`.
- `desktop/shell/controllers/conversation_controller.py` — passes `is_voice_input=True` from `start_voice_capture`; added param to `_submit_via_shell`.
- `tests/test_protocol_runtime.py` — added `ClarificationRepairTests` (6 tests) and `CorrectionTurnTests` (3 tests).
- `tests/test_input_interpreter.py` — added `NearMissInteractionTests` (6 tests).
- `tests/test_voice_dispatcher.py` — updated `assert_called_once_with` to include `is_voice_input=False`.

# Remaining Work

- Keep future shell work focused on presenting this hero flow more clearly; do not broaden into additional workflows or hidden resume logic as part of follow-up polish.
- If future work wants deeper resume behavior, it should first define explicit persisted state for it rather than overloading the current lightweight protocol state snapshot.
- Input interpreter v2: add more supported intents (`open_app` with richer alias set, `search_local` continuation), prompt caching via `cache_control` for cost reduction on repeated calls, and real end-to-end integration tests with live API.

# Do Not Change Next

- Do not change routing, runtime, confirmation, or question-answer policy for desktop-specific rendering work.
- Do not rework transcript rendering again when starting Phase 3; build prompt actions and shell controls on top of the current card-based conversation surface.
- Do not invent a second visibility contract in the UI layer; consume the typed presenter/view-model output added in Phase 1.
- Do not turn visible prompt replies into direct runtime mutations; Phase 3 must submit through the existing supervised input path.
- Do not broaden retry into hidden prompt replay or background recovery; it must stay an explicit re-submit of the same prior prompt reply through the normal shell path.
- Do not expand the new voice-first composer into continuous listening, automatic follow-up capture, or background microphone behavior.
- Do not bypass the normal shell submission path when refining voice UX; recognized voice text must keep flowing through the same supervised routing as typed text.
- Do not generalize `resume work` into a larger protocol or memory framework unless a later plan explicitly expands scope.
- Do not add implicit workspace guessing or background restoration; if remembered workspace state is missing, the shell must keep failing honestly and visibly.
- Do not turn this voice-first pass into a full shell redesign; keep future shell changes anchored to the existing hero flow and current supervised runtime surfaces.
