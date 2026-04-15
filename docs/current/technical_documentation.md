# JARVIS — Technical Documentation

This document describes how the project works internally: processes, data flows,
component responsibilities, and the exact mechanics of every subsystem.

---

## Table of Contents

1. [Project Structure](#1-project-structure)
2. [Startup Sequence](#2-startup-sequence)
3. [Gemini Live Session](#3-gemini-live-session)
4. [Audio Pipeline](#4-audio-pipeline)
5. [Tool Dispatch Mechanism](#5-tool-dispatch-mechanism)
6. [Memory System](#6-memory-system)
7. [Agent Subsystem](#7-agent-subsystem)
8. [Action Modules](#8-action-modules)
9. [Desktop Panel (PySide6)](#9-desktop-panel-pyside6)
10. [Configuration](#10-configuration)
11. [Data Flows — Sequence Diagrams](#11-data-flows--sequence-diagrams)

---

## 1. Project Structure

```
JARVIS/
├── main.py                     # Runtime entry point + JarvisLive class
├── ui.py                       # Tkinter animated UI (current default)
├── core/
│   └── prompt.txt              # System prompt loaded on every session start
├── config/
│   └── api_keys.json           # Gemini API key (and camera_index if detected)
├── memory/
│   ├── memory_manager.py       # Read/write memory JSON
│   └── long_term.json          # Persisted user facts
├── actions/
│   ├── open_app.py             # Launch applications
│   ├── web_search.py           # Search via Gemini grounding + DuckDuckGo fallback
│   ├── browser_control.py      # Playwright browser automation
│   ├── computer_settings.py    # Volume, brightness, window management, etc.
│   ├── computer_control.py     # PyAutoGUI direct control
│   ├── file_controller.py      # File system operations
│   ├── screen_processor.py     # Screen / camera capture + Gemini vision session
│   ├── reminder.py             # Windows Task Scheduler reminders
│   ├── send_message.py         # WhatsApp / Telegram via PyAutoGUI
│   ├── weather_report.py       # Weather lookup
│   ├── youtube_video.py        # YouTube play / summarize / trending
│   ├── cmd_control.py          # Natural language → CMD/terminal commands
│   ├── desktop.py              # Wallpaper, desktop organization
│   ├── code_helper.py          # Write / edit / run code files
│   ├── dev_agent.py            # Build complete multi-file projects
│   └── flight_finder.py        # Google Flights search via Playwright
├── agent/
│   ├── task_queue.py           # Background task queue with priorities
│   ├── planner.py              # Gemini-powered plan generator
│   ├── executor.py             # Step-by-step plan executor with retry/replan
│   └── error_handler.py        # Per-error recovery decision logic
└── desktop/
    ├── main.py                 # PySide6 entry point
    ├── app/application.py      # QApplication + dark palette
    ├── backend/
    │   ├── view_models.py      # PanelState, PendingPrompt data contracts
    │   └── panel_bridge.py     # Thread-safe JarvisLive ↔ PySide6 bridge
    └── shell/
        ├── main_window.py      # Frameless QMainWindow
        ├── panel_widget.py     # 6-section panel container
        ├── panel_controller.py # Signal wiring
        ├── theme.py            # Color palette + Qt stylesheet
        └── widgets/            # titlebar, state_row, current_action,
                                # prompt_zone, last_exchange, input_bar
```

---

## 2. Startup Sequence

### Tkinter path (`python main.py`)

```
main()
  │
  ├─ JarvisUI("face.png")          # Creates Tkinter window, starts animation loop
  │
  └─ threading.Thread(runner)      # Daemon thread
       │
       ├─ ui.wait_for_api_key()    # Blocks until config/api_keys.json exists
       │                           # (shows setup overlay in Tkinter if missing)
       │
       └─ asyncio.run(jarvis.run())
```

`JarvisUI` starts its own Tkinter `mainloop()` on the main thread. The daemon thread
runs the asyncio event loop with `JarvisLive`. The two never share state directly —
`JarvisUI` exposes `write_log()`, `start_speaking()`, `stop_speaking()` which
`JarvisLive` calls. These methods are thread-safe because Tkinter operations are
scheduled via `root.after()` internally.

### PySide6 path (`.venv-desktop-packaging/bin/python -m desktop.main`)

```
main()
  │
  ├─ build_application()           # QApplication + dark palette + monospace font
  │
  ├─ PanelBridge()                 # Thread-safe bridge object
  │
  ├─ MainWindow(bridge)            # Frameless PySide6 window (400×520)
  │  └─ PanelController._bind()   # Wires bridge.state_updated → panel.update_state
  │
  ├─ _load_backend()               # importlib.import_module("main") with try/except
  │  Returns JarvisLive class or None (demo mode on import failure)
  │
  └─ threading.Thread(_runner)     # Daemon thread
       │
       ├─ bridge.set_connecting()
       ├─ bridge.wait_for_api_key()
       └─ asyncio.run(jarvis.run())
```

The PySide6 event loop runs on the main thread. The asyncio loop runs in the
daemon thread. Communication is done through `PanelBridge` (see §9).

---

## 3. Gemini Live Session

**Model:** `models/gemini-2.5-flash-native-audio-preview-12-2025`  
**Protocol:** WebSocket via `google-genai` SDK  
**API version:** `v1beta`

### Session configuration (`_build_config`)

Before connecting, `JarvisLive._build_config()` assembles `LiveConnectConfig`:

| Field | Value |
|-------|-------|
| `response_modalities` | `["AUDIO"]` — model responds in audio only |
| `output_audio_transcription` | `{}` — enables text transcription of JARVIS speech |
| `input_audio_transcription` | `{}` — enables text transcription of user speech |
| `system_instruction` | time context + user memory + `core/prompt.txt` |
| `tools` | `[{"function_declarations": TOOL_DECLARATIONS}]` — all 16 tools |
| `session_resumption` | `SessionResumptionConfig()` — default resumption |
| `speech_config` | Voice: `"Charon"` (deep male voice) |

**System prompt construction order:**

```
[CURRENT DATE & TIME]
Right now it is: Monday, April 14, 2026 — 02:30 PM
...

[USER MEMORY — if long_term.json is non-empty]
Name: ..., Age: ..., etc.

[core/prompt.txt]
You are JARVIS, Tony Stark's AI assistant...
```

### Connection loop

`JarvisLive.run()` is a `while True` loop:

1. Calls `ui.set_connecting()` (panel bridge only, no-op on Tkinter)
2. Calls `_build_config()` — rebuilds system prompt with fresh timestamp and memory
3. Opens `client.aio.live.connect(model, config)` — establishes WebSocket
4. Stores `session`, `_loop`, creates `audio_in_queue` and `out_queue`
5. Calls `ui.write_log("JARVIS online.")`
6. Launches 4 coroutines via `asyncio.TaskGroup`:
   - `_send_realtime()` — drains `out_queue` → WebSocket
   - `_listen_audio()` — PyAudio mic → `out_queue`
   - `_receive_audio()` — WebSocket messages → transcription + tool dispatch
   - `_play_audio()` — `audio_in_queue` → PyAudio speaker
7. On any exception: prints error, calls `ui.set_failed()`, waits 3 seconds,
   then loops back to reconnect

The reconnect builds a fresh config, which re-injects the current time and
latest memory. Each reconnect is effectively a new session with a fresh context.

---

## 4. Audio Pipeline

### Microphone input (`_listen_audio`)

```
PyAudio.open(
    format=paInt16,
    channels=1,
    rate=16000,          # 16 kHz — Gemini Live requirement
    input=True,
    frames_per_buffer=1024
)
```

Each `stream.read(1024)` call returns 1024 samples = 64ms of audio at 16 kHz.
These are wrapped as `{"data": bytes, "mime_type": "audio/pcm"}` and put into
`out_queue` (maxsize=10, backpressure if the sender falls behind).

### Sending to Gemini (`_send_realtime`)

Drains `out_queue` and calls `session.send_realtime_input(media=msg)` for each
chunk. This is the continuous streaming path — audio flows regardless of whether
the user is speaking.

Gemini Live handles VAD (voice activity detection) on the server side. It knows
when the user starts and stops speaking.

### Receiving from Gemini (`_receive_audio`)

Each `response` object from `session.receive()` can contain:

| Field | Meaning |
|-------|---------|
| `response.data` | Raw 24 kHz PCM audio bytes from JARVIS voice response |
| `server_content.input_transcription.text` | Chunk of user speech transcription |
| `server_content.output_transcription.text` | Chunk of JARVIS response transcription |
| `server_content.turn_complete` | End of a turn — flush transcript buffers |
| `response.tool_call` | Model wants to call one or more tools |

Transcription arrives in streaming chunks. The code accumulates them in
`in_buf` and `out_buf` lists, then joins them on `turn_complete` and writes
to the UI log:

```python
self.ui.write_log(f"You: {full_in}")
self.ui.write_log(f"Jarvis: {full_out}")
```

After every turn with a user message longer than 5 characters, `_update_memory_async`
is launched in a background thread.

### Speaker output (`_play_audio`)

```
PyAudio.open(
    format=paInt16,
    channels=1,
    rate=24000,          # 24 kHz — Gemini output rate
    output=True
)
```

Drains `audio_in_queue` and writes chunks directly to the audio stream. This
runs concurrently with the receive loop — audio plays as it arrives without
waiting for the full response.

---

## 5. Tool Dispatch Mechanism

### How tools are declared

`TOOL_DECLARATIONS` is a Python list of dicts. Each dict has:
- `name` — string identifier matching the dispatch `elif name == ...` branches
- `description` — natural language description shown to the model
- `parameters` — JSON Schema object describing the parameters

All 16 declarations are passed to `LiveConnectConfig.tools` at session start.
The model decides when to call a tool based on user intent and descriptions.

### Dispatch flow

When `response.tool_call` arrives in `_receive_audio`:

```python
for fc in response.tool_call.function_calls:
    fr = await self._execute_tool(fc)  # calls one function call
    fn_responses.append(fr)

await self.session.send_tool_response(function_responses=fn_responses)
```

Multiple function calls can arrive in one `tool_call` event. Each is dispatched
and all results sent back in a single `send_tool_response`.

### Inside `_execute_tool`

1. Extracts `name` and `args` from the function call
2. Calls `ui.set_executing(name, args)` — no-op on Tkinter, updates panel state
3. Dispatches via a chain of `if/elif` statements to the appropriate action function
4. All action functions run via `loop.run_in_executor(None, lambda: ...)` — they
   execute synchronously in a thread pool, never blocking the asyncio event loop
5. **Exception for `screen_process`**: runs in its own `threading.Thread` because
   it manages an independent async event loop. Returns immediately with a
   "stay silent" message to the model.
6. **Exception for `agent_task`**: submits to `TaskQueue` (background thread),
   returns "Task started" immediately. The agent runs asynchronously.
7. After execution: calls `ui.set_idle()`
8. Returns `types.FunctionResponse(id=fc.id, name=name, response={"result": result})`

The model receives the `result` string and uses it to formulate a spoken response
(or stays silent if instructed, as with `screen_process`).

### Tool signature convention

All action functions use the same signature:

```python
def action_name(
    parameters: dict,
    response=None,      # unused in most cases
    player=None,        # UI reference for write_log calls
    session_memory=None # unused in most cases
) -> str:
```

`player` is the UI object. Action functions call `player.write_log(...)` to
add status lines to the UI log during execution.

---

## 6. Memory System

### Storage format (`memory/long_term.json`)

```json
{
  "identity": {
    "name":  {"value": "Arseny"},
    "age":   {"value": "25"},
    "city":  {"value": "Moscow"},
    "email": {"value": "..."}
  },
  "preferences": {
    "hobby": {"value": "..."}
  },
  "relationships": {
    "friend_1": {"value": "..."}
  },
  "notes": {
    "job": {"value": "..."}
  }
}
```

The format is a nested dict. Top-level keys are categories. Second-level keys
are field names. Each field is `{"value": "..."}` — a simple wrapper that could
hold metadata in the future.

### Reading memory (`memory_manager.py`)

`load_memory()` — reads and parses `long_term.json`. Returns `{}` if missing or corrupt.

`format_memory_for_prompt(memory)` — converts the memory dict to a flat string:

```
[USER MEMORY]
Name: Arseny
Age: 25
City: Moscow
Hobby: coding
```

This string is prepended to the system prompt on every session start. The model
reads it and treats it as known facts about the user.

### Writing memory (`update_memory`)

`update_memory(data)` — merges a new dict into the existing memory using deep merge:
- If a category exists: inner keys are updated
- If a category is new: it is added
- Existing keys not in `data` are preserved

### Memory extraction pipeline (`_update_memory_async`)

Triggered on every 5th turn (counter tracks turns, thread-local lock prevents races).
Runs entirely in a background thread using `google.generativeai` (not the Live API).

**Stage 1 — YES/NO gate:**
```
Does this message contain personal facts about the user
(name, age, city, job, hobby, relationship, birthday, preference)?
Reply only YES or NO.

Message: {user_text[:300]}
```
Model: `gemini-2.5-flash-lite`. If response does not contain "YES" — stops here.

**Stage 2 — Extraction:**
```
Extract personal facts from this message. Any language.
Return ONLY valid JSON or {} if nothing found.
Extract: name, age, birthday, city, job, hobbies, preferences, relationships, language.
Skip: weather, reminders, search results, commands.

Message: {user_text[:500]}
JSON:
```
Model: `gemini-2.5-flash-lite`. Response is stripped of markdown backticks,
parsed as JSON, then merged via `update_memory()`.

**Deduplication:** The module tracks `_last_memory_input` and skips if the
same text would be processed twice (e.g., reconnect after error on the same turn).

---

## 7. Agent Subsystem

The agent subsystem handles multi-step goals that require several different tools
in sequence. It runs entirely in a background thread off the main asyncio loop.

### Entry point

When `agent_task` tool is called:

```python
queue = get_queue()          # Singleton TaskQueue
task_id = queue.submit(
    goal=goal,
    priority=priority,       # LOW | NORMAL | HIGH (maps to 3 | 2 | 1)
    speak=self.speak,        # JarvisLive.speak — thread-safe text submission
)
# Returns immediately — agent runs in background
```

### TaskQueue (`agent/task_queue.py`)

- Singleton created once via `get_queue()`
- Uses `queue.PriorityQueue` internally
- A single worker thread loops forever, pulling tasks and executing them via `AgentExecutor`
- Tasks have a `cancel_flag: threading.Event` — calling `task.cancel()` sets the flag;
  the executor checks it between steps
- Status transitions: `PENDING → RUNNING → COMPLETED | FAILED | CANCELLED`

### Planning (`agent/planner.py`)

`create_plan(goal)` calls `gemini-2.5-flash` and asks for a JSON plan:

```json
{
  "steps": [
    {
      "step": 1,
      "tool": "web_search",
      "description": "Search for X",
      "parameters": {"query": "..."}
    },
    {
      "step": 2,
      "tool": "file_controller",
      "description": "Save results to file",
      "parameters": {"action": "create_file", "path": "desktop", "name": "results.txt", "content": ""}
    }
  ]
}
```

The model receives a list of available tools and their descriptions in the system
prompt. Response is stripped of markdown, parsed as JSON. On parse failure, falls
back to `{"steps": [{"step": 1, "tool": "web_search", "description": goal, "parameters": {"query": goal}}]}`.

`replan(goal, completed_steps, failed_step, error)` — same process but includes
context about what was already done and what failed.

### Execution loop (`agent/executor.py`)

`AgentExecutor.execute(goal, speak, cancel_flag)`:

```
plan = create_plan(goal)

while True:
    for step in plan["steps"]:
        attempt = 1
        while attempt <= 3:
            try:
                result = _call_tool(tool, params, speak)
                step_results[step_num] = result
                step_ok = True
                break
            except Exception as e:
                recovery = analyze_error(step, error, attempt)

                if RETRY:    attempt += 1; sleep(2)
                if SKIP:     mark as done, continue
                if ABORT:    speak(msg); return
                if FIX:      generate_fix(step) → try alternative tool/params

    if all steps ok:
        return _summarize(goal, completed_steps, speak)

    if replan_attempts >= 2:
        speak(failure msg); return

    plan = replan(goal, completed_steps, failed_step, error)
    replan_attempts += 1
```

**Context injection (`_inject_context`):** Before running a `file_controller`
`write` or `create_file` step with empty content, the executor looks at all
previous `step_results` and injects the most substantial result as the file
content. It also detects the language of the user's goal and translates the
content to match.

**Generated code fallback:** If a step uses the special tool `generated_code`,
or if a tool name is unknown, the executor calls `_run_generated_code()`:

1. Asks `gemini-2.5-flash` to write a Python script for the task description
2. Strips markdown, writes to a temp `.py` file
3. Runs via `subprocess.run([sys.executable, tmp_path])` with a 120s timeout
4. Returns stdout on success, raises `RuntimeError` on error

### Error analysis (`agent/error_handler.py`)

`analyze_error(step, error_msg, attempt)` returns:

```python
{
    "decision":       ErrorDecision.RETRY | SKIP | FIX | ABORT,
    "user_message":   "Trying again, sir.",
    "fix_suggestion": "...",
    "reason":         "..."
}
```

Decisions are heuristic:
- Attempt 1: `RETRY` for most errors
- Attempt 2: `FIX` — asks Gemini to suggest an alternative approach
- Attempt 3: `SKIP` for non-critical steps, `ABORT` for critical ones

`generate_fix(step, error, fix_suggestion)` — asks Gemini to rewrite the step
with a different tool or parameters. Returns a modified step dict.

### Summarization

After all steps complete successfully, `_summarize()` asks `gemini-2.5-flash-lite`
to write one natural sentence describing what was accomplished. Passed to
`speak()` — the text is sent to the Gemini Live session which reads it aloud.

---

## 8. Action Modules

### `open_app` — Application launcher

**How it works:**
1. Normalizes app name: looks up in `_APP_ALIASES` dict (50+ entries, cross-platform)
2. Selects launcher function by `platform.system()`: Windows / Darwin / Linux
3. **Windows**: opens Start menu via `pyautogui.press("win")`, types app name, presses Enter
4. **macOS**: tries `subprocess.run(["open", "-a", app_name])`, falls back to Spotlight
5. **Linux**: tries `shutil.which()` → `Popen`, then `xdg-open`, then `gtk-launch`

Checks if already running via `psutil.process_iter()` (if psutil available).

---

### `web_search` — Web search

**Modes:**
- **search (default):** Calls `gemini-2.5-flash` with `google_search` grounding tool enabled.
  The model searches and returns results in a concise format. Falls back to DuckDuckGo
  (`duckduckgo_search` library) if the Gemini search returns nothing useful.
- **compare:** Submits an item-by-item comparison query to Gemini with structured
  prompt asking for comparison across a specified aspect (price / specs / reviews).

Returns a string of search results passed back to the Live session as tool result.

---

### `browser_control` — Playwright browser automation

**Architecture:**

`_BrowserThread` is a module-level singleton. It manages:
- A dedicated `asyncio` event loop running in a separate thread
- A Playwright browser instance (Chromium by default, or the system default browser
  detected via OS registry/settings on first use)
- A `_CommandQueue` for thread-safe command submission from the main thread

Commands are submitted via `asyncio.run_coroutine_threadsafe()` to the browser
thread's event loop. The browser thread holds the Playwright page context.

**Supported actions:**

| Action | What it does |
|--------|-------------|
| `go_to` | Navigate to URL |
| `search` | Open search engine and search query |
| `click` | Click by CSS selector |
| `smart_click` | Find element by text description via `page.get_by_text()` / `page.get_by_role()` |
| `type` | Type text into a CSS selector |
| `smart_type` | Find input by description and type into it |
| `fill_form` | Fill multiple form fields from a dict |
| `scroll` | Scroll up or down |
| `press` | Press a key (Enter, Tab, etc.) |
| `get_text` | Return page text content |
| `close` | Close the browser |

**Browser detection (Windows):** Reads `HKEY_CURRENT_USER\Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice\ProgId` from the registry.

---

### `computer_settings` — System settings control

**Architecture:**

1. Receives either an explicit `action` string or a natural-language `description`
2. If only description: sends it to `gemini-2.5-flash-lite` for intent detection.
   Model returns the action keyword from a predefined list.
3. Looks up the action in `ACTION_MAP` — a dict mapping 100+ aliases to handler functions
4. Executes the handler

**Intent detection prompt:**
```
Return ONLY the action keyword from this list: [volume_up, volume_down, mute, ...].
User wants to: {description}
```

**Example action mappings:**

| Alias | Handler |
|-------|---------|
| `volume_up`, `louder`, `increase volume` | `_volume_up()` via pycaw (Windows) / osascript (macOS) |
| `screenshot`, `take screenshot` | `pyautogui.screenshot()` |
| `close_app`, `quit`, `exit` | `pyautogui.hotkey("alt", "f4")` |
| `fullscreen` | `pyautogui.press("f11")` |
| `lock_screen` | `subprocess("rundll32.exe user32.dll,LockWorkStation")` |
| `restart` | `os.system("shutdown /r /t 5")` |
| `dark_mode` | Windows registry toggle via `winreg` |
| `reload_n` | Presses F5 `value` times with 0.5s delay |

---

### `computer_control` — PyAutoGUI direct control

Handles low-level, atomic GUI operations. Does not do intent detection — the model
passes an explicit `action` parameter.

**Key capabilities:**

- `type` / `smart_type`: Types text. `smart_type` clears the field first; for text >20
  chars, uses clipboard paste (faster and more reliable than `typewrite`)
- `screen_find` / `screen_click`: Takes a screenshot, passes it to `gemini-2.5-flash-lite`
  with a description, gets back pixel coordinates, optionally clicks
- `random_data`: Generates realistic fake form data (name, email, password, phone, etc.)
- `user_data`: Returns real user data from `memory/long_term.json` (name, email, city)

**Safety:** `pyautogui.FAILSAFE = True` — moving the mouse to the top-left corner
stops all PyAutoGUI operations.

---

### `file_controller` — File system operations

**Path resolution:** Supports shortcuts `desktop`, `downloads`, `documents`,
`pictures`, `music`, `videos`, `home` → resolved via `Path.home() / "..."`.
All other paths go through `Path(raw).expanduser()`.

**Deletion behavior:** Prefers `send2trash.send2trash()` (moves to Recycle Bin / Trash).
Falls back to permanent delete via `shutil.rmtree` or `Path.unlink()` only if
`send2trash` is unavailable.

**`organize_desktop`:** Moves all desktop files into category folders:
Images, Documents, Videos, Music, Archives, Code, Others. Skips existing
conflicts without overwriting.

**`find_files`:** Uses `Path.rglob(pattern)` for recursive search. Supports
name substring matching and extension filtering. Returns at most `max_results`
entries.

---

### `screen_processor` — Screen / camera vision

**Architecture:**

`_LiveSession` is a module-level singleton. It maintains an independent Gemini
Live session on its own asyncio event loop in its own thread:

```
Main thread:
  screen_process(params) → _ensure_started() → _live.analyze(image, mime, text)

Vision thread (asyncio loop):
  _main() → connect to Gemini Live (IMAGE-ONLY session)
    └─ _send_loop():  dequeues (image, mime, text) → session.send_client_content
    └─ _recv_loop():  receives audio + transcription → plays audio, writes log
    └─ _play_loop():  PyAudio speaker for vision responses
```

Key property: **no microphone** in this session (`response_modalities=["AUDIO"]`
only, no `send_realtime_input` mic stream). This avoids conflicting with the
main Gemini Live session's mic.

**Image capture:**

- `angle="screen"`: Uses `mss` to grab the primary monitor (`monitors[1]`).
  If PIL is available, resizes to max 640×360 and compresses to JPEG at quality 55
  before sending. This keeps image size under ~20-40KB for fast transmission.
- `angle="camera"`: Opens webcam via `cv2.VideoCapture`. Auto-detects camera index
  on first use by testing indices 0–5, saving the working index to `config/api_keys.json`.
  Reads 10 warmup frames before capturing (avoids dark initial frames).

**Threading:** `screen_process()` is called from `_execute_tool` in a separate
`threading.Thread` (not via executor) because starting and running the vision
session involves its own asyncio loop. The main function returns immediately;
the vision thread speaks the response directly.

---

### `reminder` — Scheduled notifications

**Platform:** Windows only (uses `schtasks.exe`).

**How it works:**

1. Validates date/time format, ensures it is in the future
2. Writes a Python script to `%TEMP%\MARKReminder_YYYYMMDD_HHMM.pyw`:
   - Plays a beep sequence via `winsound.Beep`
   - Shows a toast notification via `win10toast.ToastNotifier`
   - Falls back to `msg * /TIME:30 "message"` if toast fails
   - Self-deletes after running
3. Writes a Task Scheduler XML file to `%TEMP%` with a `TimeTrigger`
4. Runs `schtasks /Create /TN "..." /XML "..." /F`
5. Deletes the XML file; the `.pyw` script is deleted by itself at runtime

---

### `cmd_control` — Natural language → terminal commands

Sends the `task` description to Gemini and asks it to return a shell command.
Runs the command via `subprocess` either visibly (opens a CMD window) or
silently (`capture_output=True`). Returns stdout/stderr as the tool result.

---

### `code_helper` — Code writing and execution

Supports modes: `write`, `edit`, `explain`, `run`, `build`, `auto`.

- `write`: Asks Gemini to generate code for a description, saves to file
- `edit`: Reads an existing file, sends it to Gemini with change description, saves result
- `run`: Runs an existing file via `subprocess` and returns output
- `build`: Writes then immediately runs the code, returns output
- `auto`: Detects intent from description and picks the right mode

Uses `gemini-2.5-flash` for code generation.

---

### `dev_agent` — Full project builder

For multi-file projects:
1. Asks Gemini to plan the file structure
2. Generates each file's content individually
3. Runs `pip install` for detected dependencies
4. Opens VS Code (`code .`) in the project directory
5. Runs the entry point and returns output

---

### `flight_finder` — Google Flights search

Uses `browser_control` internally to navigate Google Flights, extract flight
data, and speak the top results. Round-trip support via `return_date` parameter.

---

### `weather_report` — Weather

Fetches current conditions and forecast for a city. Returns a formatted string
read aloud by the model.

---

### `send_message` — Messaging apps

Uses PyAutoGUI to open WhatsApp / Telegram desktop app, find the contact,
and type/send the message. Requires the desktop app to be installed.

---

### `youtube_video` — YouTube control

- `play`: Opens YouTube in browser and searches / plays the video
- `summarize`: Uses `youtube_transcript_api` to fetch the transcript, sends
  to Gemini for a summary. Optionally saves to Notepad.
- `get_info`: Returns video metadata
- `trending`: Fetches trending videos for a region code

---

### `desktop_control` — Desktop management

- `wallpaper`: Sets wallpaper from a local path (Windows: `ctypes.windll.user32.SystemParametersInfoW`)
- `wallpaper_url`: Downloads image and sets as wallpaper
- `organize` / `clean`: Delegates to `file_controller.organize_desktop()`
- `list` / `stats`: Lists desktop contents or returns file counts by type
- `task`: Natural language desktop task — routes to Gemini for sub-command generation

---

## 9. Desktop Panel (PySide6)

### Threading model

```
Background thread:
  JarvisLive callbacks → PanelBridge public methods (write_log, set_executing, etc.)
                          └─ Each method puts a state mutation into SimpleQueue

Main thread (Qt event loop):
  QTimer (50ms interval) → PanelBridge._flush()
                             └─ Drains SimpleQueue
                                └─ Applies mutations to self._state (PanelState)
                                   └─ Emits state_updated(PanelState) signal
                                      └─ PanelController → panel.update_state(state)
```

No Qt signals are ever emitted from the background thread. All state changes
are batched through the queue and processed on the main thread.

### PanelState

```python
@dataclass
class PanelState:
    mode: str = "IDLE"             # COMMAND | QUESTION | VOICE | IDLE
    runtime_state: str = "idle"    # idle | listening | thinking | executing |
                                   # answering | awaiting_clarification |
                                   # awaiting_confirmation | failed
    current_action_text: str = "Ready."
    pending_prompt: PendingPrompt | None = None
    last_user: str | None = None
    last_jarvis: str | None = None
    speaking: bool = False
    command_summary: str | None = None
```

### State transitions in PanelBridge

| Trigger | State transition |
|---------|-----------------|
| `set_connecting()` | runtime_state → `thinking`, action → "Connecting..." |
| `write_log("JARVIS online.")` | runtime_state → `listening`, action → "Listening..." |
| `write_log("You: ...")` | runtime_state → `thinking`, last_user updated |
| `set_executing(name, args)` | runtime_state → `executing`, action → human-readable step |
| `set_idle()` | runtime_state → `thinking` (model processing tool result) |
| `write_log("Jarvis: ...")` | runtime_state → `answering`, last_jarvis updated |
| `stop_speaking()` | runtime_state → `listening` |
| `set_failed(msg)` | runtime_state → `failed`, action → error message |

**Tool display names (`_TOOL_DISPLAY`):**

| Tool | Display |
|------|---------|
| `open_app` | "Opening {app_name}" |
| `web_search` | "Searching: {query}" |
| `browser_control` | "Browser: {action}" |
| `file_controller` | "Files: {action}" |
| `screen_process` | "Analyzing screen..." |
| `computer_settings` | "Setting: {description}" |
| `agent_task` | "Planning task..." |
| ... | ... |

### 6-section layout

```
┌─────────────────────────────┐  ← Section 1: TitleBar (32px fixed)
│  ● JARVIS             [–][×]│     State dot + window controls
├─────────────────────────────┤
│  [VOICE]  [LISTENING]       │  ← Section 2: StateRow (28px fixed)
├─────────────────────────────┤     Mode chip + runtime state chip
│  Listening...               │  ← Section 3: CurrentAction (min 48px, max 3 lines)
│                             │
├ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┤  ← Section 4: PromptZone (conditional)
│  Confirm: Delete this file? │     Only present when pending_prompt is not None
│  [CONFIRM]  [CANCEL]        │     Inserted/removed from widget tree (not hidden)
├ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┤
│                             │  ← stretch spacer (flexible height)
├─────────────────────────────┤
│ ▸ You: what's the weather   │  ← Section 5: LastExchange (fixed, 2 rows)
│ ▸ JARVIS: It's 18°C in...   │
├─────────────────────────────┤
│ [🎙]  Type a message...  [▶]│  ← Section 6: InputBar
└─────────────────────────────┘
```

**Width contract:** min 360px, preferred 400px, max 440px.
**Height:** 520px default, min 420px. No horizontal resize.

**PromptZone lifecycle:**

```python
# Inserting:
self._prompt_zone = PromptZoneWidget(self)
self._layout.insertWidget(3, self._prompt_zone)  # pushes stretch from index 3 to 4

# Removing:
self._layout.removeWidget(self._prompt_zone)
self._prompt_zone.deleteLater()
self._prompt_zone = None
```

The widget is destroyed and recreated, not hidden. This ensures the layout
reflows correctly and no invisible widget consumes space.

### Input bar

Text submitted via Enter or ▶ button emits `submitted(str)` signal →
`PanelBridge.submit_text(text)` → `jarvis.speak(text)` → `session.send_client_content`.

The `[🎙]` button is a visual-only mic indicator. It does not mute PyAudio.

**Disabled states:** The input field is disabled and shows a state-specific
placeholder for: `thinking`, `executing`, `answering`, `awaiting_clarification`,
`awaiting_confirmation`.

---

## 10. Configuration

### `config/api_keys.json`

```json
{
    "gemini_api_key": "AIza...",
    "camera_index": 0
}
```

Created manually or via the Tkinter first-launch overlay. `camera_index` is
added automatically by `screen_processor.py` on first camera use.

### `core/prompt.txt`

Loaded on every session start (every reconnect). Contains the base JARVIS
persona instructions. Key rules in the prompt:
- Never simulate tool results — always call the real tool
- Be concise, direct, Tony Stark's AI style
- Use "sir" to address the user
- After calling `screen_process`, stay completely silent

### `memory/long_term.json`

Written by `memory_manager.update_memory()`. Read and injected into every
session's system prompt. If the file does not exist or is empty, memory
section is omitted from the prompt.

---

## 11. Data Flows — Sequence Diagrams

### Normal voice interaction

```
User speaks
    │
    ▼
PyAudio (16kHz PCM)
    │
    ▼
out_queue → _send_realtime() → Gemini Live WebSocket
                                        │
                                        ▼ (VAD detects speech end)
                                 processes audio
                                        │
                         ┌─────────────┼──────────────────┐
                         ▼             ▼                   ▼
               input_transcription   audio           tool_call (if needed)
                    chunks           chunks
                         │             │                   │
                         ▼             ▼                   ▼
                    in_buf[]    audio_in_queue        _execute_tool()
                                       │                   │
                                       ▼                   ▼
                               _play_audio()         action function
                               (speaker)                   │
                                                           ▼
                                                    FunctionResponse
                                                           │
                                                           ▼
                                                  send_tool_response()
                                                           │
                                                           ▼
                                                   Gemini generates
                                                   spoken reply
                                                           │
                          ┌────────────────────────────────┘
                          ▼
              output_transcription + audio chunks
                          │
                          ▼
              out_buf[] accumulates text
              audio_in_queue receives audio
                          │
                    turn_complete
                          │
                    ┌─────┴────────────────────────────┐
                    ▼                                   ▼
           ui.write_log("Jarvis: ...")      _update_memory_async()
           (UI log display)                (background thread, every 5 turns)
```

### Agent task flow

```
User: "Research X and save to a file"
    │
    ▼
Gemini Live calls tool: agent_task{goal: "..."}
    │
    ▼
_execute_tool("agent_task")
    │
    ▼
TaskQueue.submit(goal, priority, speak)
    │
    ▼
Returns: "Task started (ID: xyz), sir."  ── sent back to Gemini Live ──▶ spoken aloud
    │
    ▼ (async, worker thread)
AgentExecutor.execute(goal, speak)
    │
    ▼
create_plan(goal) → Gemini → JSON plan with steps
    │
    ├─ Step 1: web_search → DuckDuckGo/Gemini → result text
    │
    ├─ Step 2: file_controller write
    │    └─ _inject_context: inserts step 1 result as file content
    │    └─ _translate_to_goal_language: translates to user's language
    │
    ▼
_summarize(goal, steps, speak)
    │
    ▼
speak("Research complete, file saved to Desktop, sir.")
    └─ JarvisLive.speak() → session.send_client_content → Gemini speaks it
```
