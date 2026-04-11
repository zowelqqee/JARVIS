# Goal

Make the desktop app the primary shell for JARVIS with a unified voice-first composer over the existing command/question runtime: answers must look grounded, commands must look supervised, blocked states must be directly actionable, and voice must sit beside text as an explicit first-class input path.

# In Scope

- Render the existing interaction visibility payload as real desktop surfaces instead of plain transcript text.
- Show question answers with summary, full answer text, warning, sources, and source attributions.
- Show command flow with runtime state, command summary, current step, completed steps, and final success/failure.
- Show clarification and confirmation as explicit pending prompts with visible actions derived from existing prompt options.
- Show structured command result lists for existing `search_results` and `window_results` payloads when present.
- Add desktop-shell controls for `cancel` active flow and `reset` session, while keeping all routing/runtime decisions in the existing core.
- Keep speech toggle as an existing shell control and preserve current TTS integration.
- Expose one explicit desktop voice-capture action in the main composer by reusing the existing one-shot voice input path and routing the captured transcript through the normal supervised shell submission flow.
- Add targeted desktop tests for presenter/controller/widget behavior.

# Out of Scope

- Continuous voice mode, automatic follow-up voice capture, or hidden/background listening in the desktop app.
- Porting CLI operator helpers such as `qa *`, `voice *`, or `help` into the desktop shell.
- New command intents, new executor behavior, or new QA capabilities.
- Any change to routing rules, confirmation policy, or question-mode grounding rules.
- Persistence, tabs, multi-command orchestration, background work, or cross-session history.
- Broad UI redesign beyond what is needed to make this slice coherent and demoable.

# Target UX States

- Idle / ready
- Question answered
- Question failed
- Command parsing
- Command validating
- Command planning
- Command executing
- Awaiting clarification
- Awaiting confirmation
- Command completed
- Command failed
- Command cancelled

# Result Surface Types

- Welcome surface
- Question answer surface
- Clarification prompt surface
- Confirmation prompt surface
- Command progress surface
- Command completion surface
- Command failure / cancellation surface
- Search results surface
- Window results surface
- System warning surface

# Files To Change

- `desktop/backend/engine_facade.py` - expose small desktop-first shell actions such as reset and controlled prompt-option submission over the existing core path.
- `desktop/backend/presenters.py` - turn the current visibility payload into structured desktop-facing surfaces instead of mostly flat text entries.
- `desktop/backend/view_models.py` - make desktop result surfaces and prompt actions explicit in the UI contracts.
- `desktop/backend/session_service.py` - preserve the richer desktop snapshot state needed for structured shell rendering.
- `desktop/shell/controllers/conversation_controller.py` - wire prompt actions, cancel/reset controls, and structured snapshot rendering.
- `desktop/shell/layout.py` - place the new actionable prompt surface and richer conversation rendering in the shell layout.
- `desktop/shell/main_window.py` - expose the added widgets to the controller cleanly.
- `desktop/shell/widgets/conversation_view.py` - render real result cards/surfaces instead of plain list labels only.
- `desktop/shell/widgets/status_panel.py` - add shell-level controls and keep status aligned with the runtime visibility contract.
- `desktop/README.md` - update the package description so the documented desktop surface matches the actual implementation.

# Files To Add

- `desktop/shell/widgets/transcript_entry_widget.py` - reusable rich entry/card renderer for answers, command progress, structured results, and warnings.
- `tests_desktop/test_desktop_presenters.py` - lock the Phase 1 desktop mapping from core interaction visibility into structured UI data.
- `tests_desktop/test_desktop_shell_controller.py` - verify submit, prompt-action, cancel/reset, and end-to-end snapshot rendering flows.

# Phases

- Phase 1: Define the desktop surface contract in `desktop/backend/view_models.py` and `desktop/backend/presenters.py` so question results, command progress, prompts, and structured lists are explicit and testable, and add a narrow presenter-level regression test for that mapping.
- Phase 2: Upgrade `conversation_view` to render structured transcript/result surfaces from the new desktop view models, including answers, command progress, search results, window results, and warnings.
- Phase 3: Add actionable prompt replies on top of the existing transcript-card prompt surface plus shell controls for cancel/reset, wired through `conversation_controller` and existing facade hooks without bypassing normal routing/runtime behavior. Add a retry-prompt control only if the shell has a stable replayable prompt-reply hook.
- Phase 4: Add focused controller/widget integration tests and refresh `desktop/README.md` so the slice is demoable, regression-resistant, and documented.

# Acceptance Criteria

- Launching the desktop app shows a ready shell with welcome state, a unified voice-first composer, status, and speech toggle.
- A grounded question submitted in the desktop shell shows answer summary, answer text, sources, and source attributions without relying on CLI formatting.
- A command submitted in the desktop shell shows runtime state, command summary, current step, completed steps, and final result as the command progresses.
- Clarification and confirmation states are visibly distinct and offer explicit desktop actions that submit through the same supervised core flow.
- `search_results` and `window_results` are visibly rendered when the existing runtime visibility payload includes them.
- Cancel and reset are available from the desktop shell without requiring typed CLI shell commands.
- Retry prompt is exposed only when the shell can safely replay an explicit prior prompt reply through the same supervised input path.
- The main composer exposes a default-visible voice action, clear voice state, and a parallel text path without bypassing the normal supervised submission flow.
- No desktop action bypasses `InteractionManager`, `RuntimeManager`, confirmation boundaries, or the read-only question path.
- Desktop tests cover at least question rendering, confirmation/clarification prompting, command failure/completion visibility, and cancel/reset control behavior.

# Risks / Open Questions

- `BackendSessionService` currently flattens turns into transcript entries; decide whether this slice can stay entry-based or needs minimal turn-level grouping for clean card rendering.
- `desktop/backend/presenters.py` already stores rich data inside entry metadata; confirm whether that metadata can remain the source of truth or should move into explicit view-model fields.
- `ui/visibility_mapper.py` already exposes `search_results` and `window_results`; the desktop shell should consume the current payload shape rather than invent a second result contract.
- Real macOS desktop actions may still fail due to session/permission limits in some environments; the shell slice must present those failures clearly rather than trying to hide or recover from them.
