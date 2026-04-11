# Desktop Shell Repo Map

## 1. Relevant existing files and directories

| Path | Responsibility |
| --- | --- |
| `cli.py` | Current interactive shell baseline. Wires `RuntimeManager`, `InteractionManager`, `SessionContext`, QA config, and voice/TTS helpers. Also owns shell-only commands like `help`, `reset`, `qa *`, and `voice *`. |
| `interaction/interaction_router.py` | Top-level routing between `command`, `question`, and mixed-input clarification. Handles blocked-state priority and recent-answer follow-ups. |
| `interaction/interaction_manager.py` | Dual-mode orchestrator. Command path goes to `RuntimeManager`; question path goes to `qa.answer_engine`; final user-visible payload comes from `ui.visibility_mapper`. |
| `runtime/runtime_manager.py` | Supervised command loop: normalize, parse, validate, plan, execute, confirm/clarify, then build visible runtime state. Syncs `SessionContext`. |
| `runtime/state_machine.py` | Legal runtime-state transitions. |
| `ui/visibility_mapper.py` | Canonical visibility contract for command and question results, including runtime state, prompts, answer summaries, sources, search results, window results, and cancelability. |
| `ui/interaction_presenter.py` | CLI-oriented rendering of the visibility payload. |
| `desktop/main.py` | Desktop entrypoint. |
| `desktop/app/application.py` | Qt bootstrap and app/window startup. |
| `desktop/shell/main_window.py` | Creates the shell window and wires widgets to the controller. |
| `desktop/shell/layout.py` | Composes the conversation view, composer, and status panel. |
| `desktop/shell/controllers/conversation_controller.py` | UI controller. Sends text to the backend facade and re-renders the session snapshot. |
| `desktop/backend/engine_facade.py` | Desktop boundary into the existing core. Submits text turns, applies speech toggles, and owns the desktop-only shell commands currently supported (`speak on/off`). |
| `desktop/backend/presenters.py` | Maps core interaction results into desktop view models. |
| `desktop/backend/view_models.py` | Desktop transcript/status/prompt data contracts. |
| `desktop/backend/session_service.py` | Desktop-local transcript history and latest visible state above the core session context. |
| `desktop/shell/widgets/conversation_view.py` | Read-only transcript list UI. |
| `desktop/shell/widgets/composer.py` | Text input and send action. |
| `desktop/shell/widgets/status_panel.py` | Sidebar showing mode, runtime, command, step, blocked/result text, and speech state. |
| `desktop/backend/speech_service.py` | Desktop TTS state and provider lifecycle. |
| `voice/dispatcher.py` | Shared text/voice dispatch helper used by the desktop facade to get interaction results, speech utterances, and follow-up hints. |
| `qa/answer_engine.py` | Question classification and backend dispatch. |
| `qa/deterministic_backend.py` | Current grounded/local answer generator. |
| `qa/grounding.py`, `qa/source_selector.py`, `qa/source_registry.py` | Build grounded source bundles for repo/runtime/docs questions and safe answer follow-ups. |
| `qa/capability_catalog.py` | Fixed capability metadata used by deterministic QA. |
| `qa/answer_config.py` | QA backend and rollout configuration. |
| `context/session_context.py` | Short-lived session memory used by runtime resumes, follow-up commands, and grounded status answers. |
| `executor/desktop_executor.py` | Real macOS-first desktop action execution surface used by the runtime command path. |
| `confirmation/confirmation_gate.py` | Builds confirmation prompts for command and step boundaries. |
| `docs/repo_structure.md` | Module ownership contract. |
| `docs/runtime_flow.md` | End-to-end supervised interaction flow. |
| `docs/runtime_components.md` | Command/question component boundaries. |
| `docs/ui_visibility.md` | Required visible information for command and question mode. |
| `docs/desktop_execution.md` | Desktop execution contract and supported capabilities. |
| `docs/desktop_actions.md` | Action catalog expected by the executor/planner path. |
| `docs/question_answer_mode.md` | Read-only QA mode, routing, and grounding rules. |
| `docs/session_context.md` | Session-context scope and QA access rules. |
| `docs/product_rules.md` | Product-level command vs question rules and visibility requirements. |
| `docs/mvp_release_status.md` | Current release status; notes deterministic MVP is hardened and that a real desktop pass is still optional environment verification. |
| `desktop/README.md` | Desktop package note, but currently stale relative to the actual package contents. |

## 2. Real integration points for a first desktop shell slice

- App boot: `desktop/main.py` -> `desktop/app/application.py` -> `desktop/shell/main_window.py`.
- UI composition: `MainWindow` uses `desktop/shell/layout.py` to mount `ConversationView`, `ComposerWidget`, and `StatusPanel`.
- Text turn path: `desktop/shell/controllers/conversation_controller.py` -> `desktop/backend/engine_facade.py::submit_text`.
- Shared interaction core: `EngineFacade.submit_text()` calls `voice/dispatcher.py::dispatch_interaction_input()`, which calls `InteractionManager.handle_input()`.
- Command path: `interaction/interaction_manager.py` -> `runtime/runtime_manager.py` -> parser/validator/planner/executor flow -> `ui/visibility_mapper.py`.
- Question path: `interaction/interaction_manager.py` -> `qa/answer_engine.py` -> `qa/grounding.py` + `qa/source_selector.py` + `qa/source_registry.py` -> `ui/visibility_mapper.py`.
- Desktop rendering path: `desktop/backend/presenters.py` converts the interaction result into `TurnViewModel` / `StatusViewModel`, `desktop/backend/session_service.py` stores the snapshot, and the controller pushes it into the widgets.
- Speech output path: `EngineFacade.submit_text()` passes the prepared utterance to `desktop/backend/speech_service.py`, which wraps the existing TTS provider stack. This is the direct `voice/` impact on the desktop shell today.
- Session continuity: `runtime/runtime_manager.py` keeps `context/session_context.py` updated so desktop follow-ups, blocked replies, recent answer follow-ups, and runtime-status QA can work across turns.

## 3. Gaps or weak points blocking a coherent desktop shell product

- The desktop shell does not expose the full visibility contract it already computes. `ui/visibility_mapper.py` produces `completed_steps`, `can_cancel`, `answer_sources`, `answer_source_attributions`, `search_results`, and `window_results`, but the desktop widgets only show a small subset.
- `desktop/backend/presenters.py` stores answer sources, attributions, and prompt options in entry metadata, while `desktop/shell/widgets/conversation_view.py` only renders plain role/text labels. The data exists but is effectively invisible.
- `desktop/shell/widgets/status_panel.py` has no cancel or reset control, even though runtime cancelability is tracked and `EngineFacade.reset_session()` exists.
- Desktop shell command parity is narrow. `cli.py` owns the real operator shell surface (`help`, `reset`, `qa *`, `voice *`), while `desktop/backend/engine_facade.py` only intercepts `speak on/off`.
- There are two presentation seams over the same interaction truth: `ui/interaction_presenter.py` for CLI and `desktop/backend/presenters.py` for desktop. That duplication is a real drift risk for shell coherence.
- `desktop/README.md` still says the package is scaffold-only, but the repo now contains a working Qt shell/backend/widget stack. The desktop docs are behind the code.
- `docs/mvp_release_status.md` still frames a real interactive desktop pass as optional environment verification. The hardened, validated path is still mainly the CLI/runtime path, not an explicitly finished desktop product path.

## 4. Most likely files to change first

- `desktop/backend/engine_facade.py`
- `desktop/backend/presenters.py`
- `desktop/shell/controllers/conversation_controller.py`
- `desktop/shell/widgets/conversation_view.py`
- `desktop/shell/widgets/status_panel.py`
- `desktop/README.md`
