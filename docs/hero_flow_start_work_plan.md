# Goal

Deliver one coherent desktop hero flow where the user can say or type `start work` or `resume work`, JARVIS stays in command mode, uses the existing supervised runtime, opens the intended workspace in `Visual Studio Code`, and makes clarification, progress, and failure states explicit in the shell.

# Supported Triggers

- `start work on <workspace>`
- `start work in <workspace>`
- `start work`
- `resume work`

# User-Facing Behavior

- `start work on <workspace>`: route to `prepare_workspace`, resolve the workspace folder, open `Visual Studio Code`, open the folder there, and show visible step progress plus a clear final ready state.
- Bare `start work`: route to a blocked `prepare_workspace` shape that explicitly asks `What workspace should I prepare?`, then continue the same supervised command after the user replies with a workspace.
- Bare `resume work`: route to a built-in `Resume Work` protocol that reuses `open_last_workspace` with `Visual Studio Code`.
- No remembered workspace available: `resume work` must fail visibly and honestly, with a user-facing message that the last workspace is not available yet and that the user should first run `start work on <workspace>`.

# Existing Integration Points

- `desktop/shell/widgets/composer.py` and `desktop/shell/controllers/conversation_controller.py` already send both text and one-shot voice input through the same shell submission path.
- `desktop/backend/engine_facade.py` already hands shell text to `voice.dispatcher.dispatch_interaction_input()`.
- `interaction/interaction_manager.py` already routes command-mode input into `runtime/runtime_manager.py`.
- `parser/command_parser.py` already supports `prepare_workspace` and `run_protocol`.
- `protocols/registry.py`, `protocols/builtin_protocols.py`, and `protocols/planner.py` already support built-in protocol triggers and the `open_last_workspace` action.
- `protocols/state_store.py` already persists `last_workspace_path` after successful workspace-opening commands.
- `validator/command_validator.py` already enforces explicit failure when a protocol needs `open_last_workspace` and no stored workspace exists.
- `ui/visibility_mapper.py` and `voice/speech_presenter.py` already generate the visible and spoken runtime surfaces consumed by the desktop shell.

# Files To Change

- `interaction/interaction_router.py` - route `resume work` as a command while preserving current command vs question boundaries.
- `parser/command_parser.py` - add explicit hero-flow phrase parsing and ensure `start work on <workspace>` maps to `prepare_workspace` with `Visual Studio Code` plus a workspace folder target.
- `clarification/clarification_handler.py` - turn the reply to bare `start work` into an executable `prepare_workspace` command shape instead of only storing raw workspace text.
- `runtime/runtime_manager.py` - treat `resume ...` as a fresh command surface when the runtime is blocked, consistent with current supervised restart behavior.
- `protocols/builtin_protocols.py` - add the built-in `Resume Work` protocol and its exact trigger phrase.
- `ui/visibility_mapper.py` - replace generic protocol/workspace summaries and raw remembered-workspace failure text with clear hero-flow shell copy and next-step hints.
- `voice/speech_presenter.py` - make spoken summaries and failures for this flow sound operational instead of generic `run_protocol` wording.
- `tests/test_interaction_router.py` - cover routing for `resume work`.
- `tests/test_parser_validator_contract.py` - cover parse/validate behavior for `start work`, `start work on <workspace>`, and the clarification handoff.
- `tests/test_protocol_registry.py` - cover built-in trigger matching for `resume work`.
- `tests/test_protocol_runtime.py` - cover `resume work` success with stored workspace state and explicit failure without it.
- `tests/test_protocol_speech.py` - cover spoken summaries for `Resume Work`.

# Files To Add

- None. This slice can stay small by extending the existing router, parser/validator, protocol, runtime, and speech tests.

# Clarification And Confirmation Behavior

- Bare `start work` must require clarification and must use the existing explicit clarification path.
- `start work on <workspace>` must reuse existing target resolution; unresolved or ambiguous workspace references must keep using the existing clarification behavior.
- `resume work` must not introduce a new confirmation step.
- Existing confirmation boundaries elsewhere in the runtime must remain unchanged and explicit.
- Question mode stays read-only and is not part of this flow.

# Shell And Voice Visibility

- The desktop shell should show command mode, runtime state, current step, and final result using the existing transcript and status surfaces.
- Bare `start work` should visibly block on `What workspace should I prepare?`.
- `resume work` should visibly show whether JARVIS is reopening a remembered workspace or cannot do so yet.
- Voice input should keep using the current one-shot composer path, and the spoken output should mirror the same clarification, progress, completion, and honest failure states.

# Out Of Scope

- Any new memory system beyond `ProtocolStateStore`.
- Continuous listening, wake-word behavior, or background voice capture.
- New protocol framework abstractions beyond one built-in `Resume Work` protocol.
- Multi-step autonomous tasking after the workspace opens.
- Browser/session restoration, recent-file reopening, or branch recovery.
- Broad desktop shell redesign unrelated to this hero flow.

# Acceptance Criteria

- Typing or speaking `start work on <workspace>` routes to command mode, runs the supervised `prepare_workspace` path, and opens `Visual Studio Code` on the resolved workspace.
- Typing or speaking bare `start work` visibly asks `What workspace should I prepare?`, and the reply continues the same command into workspace preparation.
- Typing or speaking bare `resume work` routes to command mode and runs the built-in `Resume Work` protocol when remembered workspace state exists.
- If no remembered workspace exists, `resume work` fails visibly with honest guidance instead of guessing or silently falling back.
- The desktop shell shows readable progress and final state for the flow, not raw debug text.
- Voice and text stay on the same controller -> facade -> dispatch -> interaction -> runtime path.
- One active command flow at a time, explicit supervision, and current command/question boundaries remain unchanged.

# Risks / Open Questions

- The current bare-`start work` clarification path asks the right question, but a small targeted bridge is still needed so the clarification reply becomes executable `prepare_workspace` targets.
- The current generic `prepare_workspace` helper defaults to additional workspace targets like Chrome; the hero phrases should avoid that and stay `Visual Studio Code`-only.
- `resume work` remains dependent on the quality of the existing stored `last_workspace_path`; stale or missing state must be surfaced clearly rather than hidden.
