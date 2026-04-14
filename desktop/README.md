# JARVIS Desktop Shell

PySide6-based desktop application that wraps the existing JARVIS command/question runtime in a voice-first shell.

## What it does

- Accepts voice and typed input through a unified composer surface
- Routes every request through the same supervised `InteractionManager` → `RuntimeManager` core as the CLI
- Renders grounded question answers, command progress, clarification/confirmation prompts, and structured result lists as explicit transcript cards
- Provides shell controls for cancel, reset, retry prompt, and speech toggle without requiring typed CLI commands

## Hero flow

The shell ships with one supported hero flow out of the box:

| Phrase | Behaviour |
| --- | --- |
| `start work on <workspace>` | Opens the workspace folder in Visual Studio Code via the supervised `prepare_workspace` path |
| `start work` | Asks "What workspace should I prepare?" and continues the same supervised command after the reply |
| `resume work` | Reopens the most recently remembered workspace in Visual Studio Code; includes remembered git branch and last-work context when available |
| `resume work` (no remembered workspace) | Fails visibly with a clear next-step hint to run `start work on <workspace>` first |
| `resume work` (stale remembered path) | Fails visibly at the validation stage with a workspace-specific message; never surfaces a raw executor error |

## Layout

```
┌─────────────────────────────────────────────────┬──────────────┐
│  Composer (voice-first, always on top)          │              │
│  ┌──────────────────┐  │  ┌───────────────────┐ │  Status      │
│  │ Voice panel      │ or │ Text panel         │ │  Panel       │
│  │ Start Listening  │     │ Ctrl+Enter submits │ │              │
│  └──────────────────┘     └───────────────────┘ │  - State     │
├─────────────────────────────────────────────────│  - Controls  │
│  Conversation transcript (structured cards)     │  - Speech    │
│  - Question answer with sources/attributions    │              │
│  - Command progress with current step           │              │
│  - Clarification / confirmation prompts + chips │              │
│  - Search / window result lists                 │              │
│  - Failure and warning surfaces                 │              │
└─────────────────────────────────────────────────┴──────────────┘
```

## Composer voice states

| State | Meaning |
| --- | --- |
| Ready | Waiting for one spoken request |
| Listening | Microphone is active; capturing one request |
| Submitting | Recognized text is being submitted through the normal shell path |
| Issue | Capture failed; user can retry or type instead |
| Unavailable | Voice input is only available on macOS |

## Shell controls (status panel)

| Control | Behaviour |
| --- | --- |
| Cancel Flow | Submits `cancel` through the normal input path when the runtime is cancelable |
| Retry Prompt | Replays the last explicit prompt reply when the same prompt is still active |
| New Session | Resets the session via `EngineFacade.reset_session()` |
| Speech Toggle | Enables or disables TTS output for command and answer results |

## Package layout

```
desktop/
  main.py                        # Entrypoint
  app/
    application.py               # Qt bootstrap
  shell/
    main_window.py               # Top-level window; wires controller on startup
    layout.py                    # Builds left column (composer + conversation) and status panel
    controllers/
      conversation_controller.py # Data flow between widgets and backend facade
    widgets/
      composer.py                # Voice-first unified input surface
      conversation_view.py       # Transcript list with structured card rendering
      transcript_entry_widget.py # Per-entry card renderer
      status_panel.py            # Runtime state display and shell controls
    theme.py                     # Shell stylesheet
  backend/
    engine_facade.py             # Desktop boundary into the JARVIS core
    presenters.py                # Maps core visibility payloads to desktop view models
    view_models.py               # Desktop surface contracts (answer, command, prompt, result lists)
    session_service.py           # Desktop transcript history
    speech_service.py            # Desktop TTS state and provider lifecycle
```

## Tests

All desktop tests are in `tests_desktop/`. They run without a display (PySide6 widget tests are skipped automatically when no display is available).

| File | Coverage |
| --- | --- |
| `test_desktop_presenters.py` | Presenter mapping: question answers, confirmation/clarification prompts, command failure/completion, search/window result lists |
| `test_conversation_controller.py` | Controller: submit, voice capture, prompt actions, cancel, reset, retry, backend error handling |
| `test_main_window.py` | Shell composition, widget labels, layout order, hero-flow composer copy (PySide6 required) |
| `test_backend_facade.py` | Facade: question turns, confirmation prompts, speech toggle, voice capture, reset |
| `test_conversation_view.py` | Transcript card rendering, prompt action chip signals (PySide6 required) |
| `test_speech_service.py` | TTS provider lifecycle |
| `test_theme.py` | Stylesheet surface targets |

## Constraints

- Voice input is explicit and bounded: one click starts one capture, recognized text routes through the normal supervised path, nothing listens in the background.
- No desktop action bypasses `InteractionManager`, `RuntimeManager`, confirmation boundaries, or the read-only question path.
- The hero flow uses `ProtocolStateStore` for remembered workspace state; it does not introduce any broader memory or background recovery system.
