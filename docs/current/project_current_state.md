# What This Project Is Right Now

JARVIS is a voice-driven personal AI assistant that runs on a desktop computer. It
listens through the microphone continuously, sends audio to the Gemini Live API in
real time, receives spoken responses back, and executes actions on the computer —
opening apps, controlling the browser, managing files, running commands, searching
the web, and more.

The project started as "Mark XXX" (a public YouTube project by FatihMakes) and is
being evolved under the JARVIS name. The original readme still refers to Mark XXX
and FatihMakes. The codebase is mid-transition: the original Tkinter UI and Gemini
Live backend are the functional runtime; a new PySide6 panel layer was recently
added as a first structural pass but is not yet the default launch path.

Primary design target per the code is **Windows 10/11**. Several action modules
contain Windows-only code paths (WinReg, comtypes, pycaw, win10toast). macOS paths
exist in a few modules but are incomplete or untested at the action level.

---

# Main Runtime / Backend

**Entry point:** `main.py`
**UI (current default):** `ui.py` (Tkinter)

`JarvisLive` in `main.py` manages the entire live session:

1. Connects to Google's Gemini Live API (`gemini-2.5-flash-native-audio-preview`) via
   WebSocket using the `google-genai` SDK.
2. Opens a PyAudio microphone stream and continuously sends 16 kHz PCM chunks to the
   session (`_listen_audio`, `_send_realtime`).
3. Receives 24 kHz PCM audio back and plays it in real time (`_play_audio`).
4. Receives transcriptions of both user speech and JARVIS responses
   (`_receive_audio`), writing them to the UI log on turn completion.
5. Receives `tool_call` events from the model and dispatches them synchronously to
   one of 16 action functions (`_execute_tool`). Tool results are sent back to the
   session as `FunctionResponse`.
6. After every 5 turns, optionally extracts personal facts from the conversation and
   updates the long-term memory file (`_update_memory_async`).

The session auto-reconnects on error with a 3-second wait.

**System prompt:** `core/prompt.txt` — loaded at session start along with any stored
user memory (`memory/long_term.json`). Current date/time is injected into the system
prompt on each new connection.

---

# Desktop Layer

Two UI layers exist in the repo. Only the Tkinter one is currently the default
launch path.

## Tkinter UI (`ui.py`) — active default

`JarvisUI` is a full-screen Tkinter canvas (~984×816) with:
- An animated face (loaded from `face.png`), spinning rings, scan arcs, pulse
  rings, and a status text — all redrawn at ~60 fps via `root.after(16, ...)`.
- A `log_text` widget (Courier 10pt, bottom band) that shows conversation history
  with typewriter-effect rendering.
- A first-launch setup frame for entering the Gemini API key if `config/api_keys.json`
  is missing.
- `write_log(text)`, `start_speaking()`, `stop_speaking()` methods consumed by
  `JarvisLive`.

## PySide6 Panel (`desktop/`) — first structural pass, not default

A new `desktop/` package was written as a panel-first replacement. It is NOT wired
to the default `python main.py` launch; it runs via:

```
.venv-desktop-packaging/bin/python -m desktop.main
```

### Files

| File | Role |
|------|------|
| `desktop/main.py` | Entry point; starts QApplication, creates PanelBridge, launches JarvisLive in a daemon thread |
| `desktop/app/application.py` | QApplication setup, dark palette, monospace font |
| `desktop/backend/view_models.py` | `PanelState`, `PendingPrompt` — flat state contract |
| `desktop/backend/panel_bridge.py` | Thread-safe bridge; implements `write_log` / `start_speaking` / `stop_speaking` so JarvisLive treats it as a UI; drains state via QTimer to the main thread |
| `desktop/shell/theme.py` | Dark colour palette + Qt stylesheet |
| `desktop/shell/main_window.py` | Frameless QMainWindow, 400×520, 360–440px width |
| `desktop/shell/panel_widget.py` | Assembles 6 sections; manages PromptZone insert/remove lifecycle |
| `desktop/shell/panel_controller.py` | Wires `bridge.state_updated` ↔ `panel.update_state` |
| `desktop/shell/widgets/titlebar.py` | Section 1 — drag region, ● state dot |
| `desktop/shell/widgets/state_row.py` | Section 2 — mode chip + runtime state chip |
| `desktop/shell/widgets/current_action.py` | Section 3 — current action text, always visible |
| `desktop/shell/widgets/prompt_zone.py` | Section 4 — confirmation / clarification, conditional |
| `desktop/shell/widgets/last_exchange.py` | Section 5 — last user + last JARVIS line, truncated |
| `desktop/shell/widgets/input_bar.py` | Section 6 — single-line text input + send + mic indicator |

### How it connects to JarvisLive

`PanelBridge` implements the same interface as `JarvisUI`. `desktop/main.py` passes
a `PanelBridge` instance to `JarvisLive(bridge)` instead of a `JarvisUI` instance.
Four `hasattr`-guarded callbacks were added to `main.py`:
`set_connecting`, `set_executing`, `set_idle`, `set_failed` — no-ops when `ui` is
the original `JarvisUI`.

The PromptZone (Section 4) is structurally correct but never triggered by the current
backend; the Gemini Live session does not emit clarification or confirmation prompts.

---

# Main Code Areas

| Path | What it is |
|------|-----------|
| `main.py` | Runtime: Gemini Live session loop, tool dispatch, memory update trigger |
| `ui.py` | Default UI: animated Tkinter canvas |
| `desktop/` | New PySide6 panel (first structural pass) |
| `actions/` | 16 tool implementations called by JarvisLive and the agent executor |
| `agent/` | Async-style agent subsystem: planner, executor, error handler, task queue |
| `memory/` | Long-term memory: `memory_manager.py` reads/writes `memory/long_term.json` |
| `core/prompt.txt` | System prompt loaded on each session start |
| `config/` | Runtime config; `api_keys.json` created on first launch (holds Gemini API key) |
| `requirements.txt` | Python package list for `pip install` |
| `setup.py` | `pip install -r requirements.txt` + `playwright install` |

---

# Current User Flow

1. **Launch:** `python main.py` → creates `JarvisUI` (Tkinter window), starts
   `JarvisLive` in a daemon thread.
2. **API key check:** If `config/api_keys.json` is missing, a setup overlay appears
   in the Tkinter window; user enters Gemini API key.
3. **Connection:** `JarvisLive` connects to Gemini Live API, injects system prompt +
   current memory + current date/time.
4. **Mic always on:** PyAudio streams mic audio continuously into the session.
5. **User speaks:** Gemini transcribes it (`input_transcription`), accumulates until
   `turn_complete`, then `write_log("You: {text}")` is called → typewriter display.
6. **Model responds or calls a tool:**
   - If tool call: `_execute_tool` runs the matching action function synchronously
     (in an executor), sends the result back to the session.
   - If text/audio response: audio plays back in real time; `output_transcription`
     accumulates and on `turn_complete` is written to the log as `"Jarvis: {text}"`.
7. **Memory update:** Every 5 turns, a background thread checks the user's input for
   personal facts and updates `memory/long_term.json` via a two-stage Gemini call.
8. **Loop:** Session stays open until error; then reconnects automatically.

**Text input path (panel only, not in Tkinter UI):** The new panel's input bar calls
`bridge.submit_text(text)` → `jarvis.speak(text)` → sends as client text content to
the live session. This path exists in code but has not been tested end-to-end.

---

# What Looks Implemented

- **Continuous voice session** with Gemini Live, mic streaming, audio playback,
  real-time transcription display.
- **Tool dispatch** for all 16 declared actions; each has a corresponding
  implementation file in `actions/`.
- **App launching** (`open_app`) with cross-platform aliases covering Windows/macOS/Linux.
- **Web search** via Gemini `google_search` grounding with DuckDuckGo fallback.
- **Browser control** via Playwright (navigate, click, type, scroll, get text).
- **File operations** (`file_controller`): list, create, delete, move, copy, read, find.
- **Screen capture and vision** (`screen_processor`): full Gemini image session for
  screen or webcam analysis.
- **Computer settings** (`computer_settings`): intent detected via Gemini, then
  dispatched to `pyautogui` / platform-specific APIs.
- **Multi-step agent tasks** (`agent_task`): `TaskQueue` → `AgentExecutor` → `Planner`
  (Gemini) → step-by-step tool execution with retry / replan / error-handler loop.
- **Long-term memory**: user profile (name, age, city, preferences, relationships,
  notes) persisted to JSON, loaded into system prompt on each session.
- **PySide6 panel structure**: layout contract implemented (6 sections, correct
  visibility rules, PromptZone lifecycle, width contract, state-driven content for
  all 8 runtime states) — verified with offscreen Qt tests.

---

# What Looks Partial Or Incomplete

- **PySide6 panel is not the default launch path.** Running `python main.py` still
  uses the Tkinter UI. The panel requires a separate venv and manual launch command.
- **PySide6 is not in `requirements.txt`.** It only exists in `.venv-desktop-packaging`.
- **PromptZone never triggers** in the current backend. Clarification and confirmation
  flows exist in the panel UI but the Gemini Live session has no mechanism to emit them.
- **Input bar text submission is untested end-to-end.** The code path exists
  (`bridge.submit_text` → `jarvis.speak`) but has not been verified with a live session.
- **macOS action support is incomplete.** `browser_control` detects the OS default
  browser but several paths use `winreg`. `computer_settings` has Windows-specific
  volume/brightness paths via `pycaw`/`comtypes`. `desktop/main.py` falls back to
  "demo mode" on macOS when those imports fail.
- **`desktop/main.py` backend import is fragile.** On macOS, importing `main.py`
  (root) may fail at the `from actions.*` import chain due to Windows-only packages
  at module level.
- **Mic toggle in the panel is decorative.** The `[🎙]` button has no wire to actually
  mute/unmute the PyAudio stream; it is a visual indicator only.
- **`face.png` is not in the repo.** The Tkinter UI falls back to a text orb if the
  file is missing, but `main.py` always calls `JarvisUI("face.png")` unconditionally.
- **Agent task cancellation** is implemented in `TaskQueue.cancel()` but there is no
  UI surface for it in either the Tkinter or the panel UI.
- **Memory update is probabilistic.** Updates happen every 5 turns only and require a
  "YES" from a model check before extracting facts — no guaranteed extraction.
- **No session persistence.** Conversation history is in-memory only; closing the app
  loses the transcript. Only the user profile (long_term.json) survives restarts.

---

# Environment / Dependencies

### Runtime to run `main.py` (Tkinter path)

| Requirement | Notes |
|-------------|-------|
| Python 3.10+ | 3.13 confirmed present via venv |
| `google-genai` | Gemini Live API client |
| `google-generativeai` | Used by agent planner, executor, memory updater |
| `pyaudio` | Mic input + audio playback; needs PortAudio system lib |
| `pillow` | Face image loading in `ui.py` |
| `playwright` | Browser control; requires `playwright install` for browser binaries |
| `pyautogui` | GUI automation in `computer_settings`, `computer_control` |
| `pyperclip` | Clipboard access |
| `mss` | Screen capture |
| `opencv-python` | Webcam capture in `screen_processor` |
| `requests`, `beautifulsoup4` | HTTP/HTML in some action modules |
| `duckduckgo-search` | Fallback web search |
| `youtube-transcript-api` | YouTube summarise action |
| `psutil` | Process detection in `open_app` |
| `comtypes`, `pycaw` | **Windows only** — volume control |
| `win10toast` | **Windows only** — system notifications |
| `send2trash` | Safe file deletion |
| `numpy` | Used in vision/screen modules |
| Gemini API key | Stored in `config/api_keys.json`; prompted on first launch |

### Runtime to run the new `desktop/` panel

| Requirement | Notes |
|-------------|-------|
| PySide6 6.11+ | In `.venv-desktop-packaging`; **not** in `requirements.txt` |
| Python 3.13 | Confirmed available in `.venv-desktop-packaging` |
| All of the above | `desktop/main.py` imports `JarvisLive` from root `main.py` |

### System requirements

- Microphone (required for voice session)
- Audio output (required for playback)
- Internet connection (required for all Gemini API calls and most actions)
- Windows 10/11 for full action coverage; macOS gives partial action support

---

# Open Questions From The Current Codebase

1. **Is the Tkinter UI (`ui.py`) still the intended daily-use interface, or is the
   PySide6 panel the target replacement?** There is no flag, config, or script to
   choose between them.

2. **How should the panel launch on the same machine as the Gemini Live audio session?**
   PyAudio initialises at module import (`pya = pyaudio.PyAudio()` in `main.py`).
   Running two processes (Tkinter and panel) would conflict on the audio device.

3. **What should happen when `face.png` is absent?** The Tkinter UI has a fallback
   orb but `main.py` always passes `"face.png"` without checking existence.

4. **Are Windows-only action modules expected to be ported to macOS, or is macOS
   only a development/panel-testing environment?** Several actions silently fail or
   import-error on macOS.

5. **Should PySide6 be added to `requirements.txt`, or managed separately (e.g., a
   `requirements-desktop.txt`) to avoid forcing it on Windows users who don't use the
   panel?**

6. **Is `agent_task` / `AgentExecutor` used in practice?** The planner calls Gemini
   to break goals into steps. If the planning call fails or returns a bad plan, it
   falls back to a single `web_search`. There is no observable indication in the UI
   that an agent task is running beyond the Gemini response.

7. **What is the intended relationship between `readme.md` (still says Mark XXX /
   FatihMakes) and the JARVIS rebrand?** The codebase, prompts, and new docs all use
   JARVIS; the readme has not been updated.
