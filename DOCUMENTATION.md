# V.E.C.T.O.R. — Technical Documentation

## Overview

V.E.C.T.O.R. (Voice-Enabled Cognitive Tool and Operations Runtime) is a local AI assistant that uses Google's Gemini Live Native Audio API for real-time voice interaction. It runs primarily on Windows but has partial macOS support. The system listens to microphone input, processes speech through Gemini's multimodal live session, executes tool calls on the host machine, and responds with synthesized voice.

The assistant supports a large action surface: web search, browser automation, file management, application control, desktop automation, system settings, reminders, messaging, multi-step agent tasks, and more. An optional ARIA gateway extends the system to a Raspberry Pi running OLED glasses (Pi ARIA).

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        main.py (VectorLive)                  │
│                                                              │
│  ┌─────────────┐   ┌──────────────┐   ┌──────────────────┐  │
│  │ _listen_    │   │ _receive_    │   │ _play_audio()    │  │
│  │ audio()     │   │ audio()      │   │                  │  │
│  │ (mic PCM    │   │ (responses,  │   │ (queued PCM      │  │
│  │  → Gemini)  │   │  tool_calls) │   │  → speaker)      │  │
│  └──────┬──────┘   └──────┬───────┘   └──────────────────┘  │
│         │                 │                                  │
│         └────────┬────────┘                                  │
│                  ▼                                           │
│         Gemini Live WebSocket                                │
│    (models/gemini-2.5-flash-native-audio-preview)            │
└──────────────────────────┬───────────────────────────────────┘
                           │ tool_call
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                    actions/registry.py                       │
│               TOOL_REGISTRY + TOOL_DECLARATIONS              │
└──────────────────────────┬───────────────────────────────────┘
                           │ dispatch
          ┌────────────────┼─────────────────┐
          ▼                ▼                 ▼
   actions/*.py     agent/executor.py   memory/memory_manager.py
   (direct tools)  (multi-step tasks)   (facts, context)
          │
          ▼
   ws_ui.py (WebSocket HUD server → Tauri React frontend)
          │
          ▼
   aria/ (optional ARIA Pi gateway — FastAPI + uvicorn)
```

Data flow for a voice interaction:

1. Microphone PCM frames are captured via `sounddevice` and queued in `out_queue`.
2. `_send_realtime()` reads the queue and sends `realtime_input` chunks to Gemini Live.
3. Gemini returns either audio output, transcription text, or a `tool_call`.
4. Audio output is queued in `audio_queue` and played by `_play_audio()`.
5. Tool calls are dispatched by `_execute_tool()` via `loop.run_in_executor()` so the async loop is never blocked.
6. Tool results are sent back to Gemini as `tool_response` parts.
7. HUD events (status, logs, tool state) are broadcast to the Tauri frontend via `ws_ui.py`.

---

## Core Components

### Runtime (`main.py`)

**Class:** `VectorLive`

The central orchestrator. Manages a single `asyncio` event loop that runs four concurrent coroutines:

| Coroutine | Purpose |
|---|---|
| `_listen_audio()` | Captures mic via `sounddevice.InputStream`, puts PCM into `out_queue` |
| `_send_realtime()` | Drains `out_queue`, sends `realtime_input` to Gemini session |
| `_receive_audio()` | Handles all server messages: audio delta, transcription, tool_call, turn_complete |
| `_play_audio()` | Drains `audio_queue`, writes PCM to `sounddevice.OutputStream` |

**Key methods:**

`speak(text: str)` — Thread-safe. Queues a `client_content` turn containing the text as a model part, which causes Gemini to speak it immediately.

`_build_config()` — Builds the `LiveConnectConfig`. Assembles the system prompt from a base persona string, the current memory blob (from `memory_manager.get_memory_context()`), and desktop context (from `computer_settings.get_desktop_context()`). Attaches all `TOOL_DECLARATIONS`.

`_execute_tool(fc)` — Called from `_receive_audio()` on each `tool_call` part. Looks up the handler in `TOOL_REGISTRY`, runs it via `loop.run_in_executor(None, lambda: handler(...))`, and sends the result back as `tool_response`. UI is updated to `EXECUTING` state during the call.

**Reconnect logic:** On any exception in the main session, the loop backs off exponentially (2 → 4 → 8 → ... → 30 s) and reconnects. The Tauri UI is set to `CONNECTING` during backoff and `OFFLINE` if all retries fail.

**Memory update loop:** Every 5 turns (tracked by `_turn_count`), a background thread runs a two-stage Gemini call: first asks "should memory be updated? YES/NO", then if YES runs extraction. Result is merged into `memory_manager`. A dedup guard using `_last_memory_input` (protected by `_memory_turn_lock`) prevents duplicate calls when the same utterance is processed multiple times.

**Session start:** `get_desktop_context()` is called once at startup to inject OS version, username, screen resolution, and running apps into the system prompt.

---

### Tool Registry (`actions/registry.py`)

**`TOOL_REGISTRY`** — `dict[str, Callable]` mapping tool name → handler function.

**`TOOL_DECLARATIONS`** — `list[dict]` of Gemini function declaration objects. Each entry specifies the tool name, description, and parameter schema. This list is passed directly to `LiveConnectConfig.tools`.

Each handler has the signature:
```python
def my_tool(
    parameters: dict,
    response: str | None = None,
    player=None,             # WebSocketUI instance (or None in executor context)
    session_memory=None,     # memory_manager module reference
    speak: Callable | None = None,
) -> str:
```

Not all handlers use every parameter. The return value is a string sent back to Gemini as the tool result.

---

### Actions Layer (`actions/`)

| Module | Tool name | Description |
|---|---|---|
| `open_app.py` | `open_app` | Launches applications by name. Uses `subprocess.Popen` first (Windows registry lookup via `winreg`), falls back to `pyautogui` Start Menu search. Validates launch by checking if process is running after 3 s. |
| `web_search.py` | `web_search` | DuckDuckGo or Google search via HTTP scraping. Returns text results. |
| `browser_control.py` | `browser_control` | Playwright-based browser automation. Reuses existing Chrome via CDP at port 9222; falls back to launching fresh browser. Actions: `open`, `click`, `type`, `scroll`, `get_text`, `screenshot`, `navigate`, `close`. |
| `file_controller.py` | `file_controller` | File and folder operations: `read`, `write`, `create_file`, `create_folder`, `delete`, `move`, `copy`, `list`, `search`, `get_largest_files` (capped at 50 k files). |
| `cmd_control.py` | `cmd_control` | Runs shell commands via `subprocess.run`. Windows: PowerShell; macOS/Linux: bash. Output truncated to 2000 chars. |
| `code_helper.py` | `code_helper` | Opens VS Code with specific files or projects via `code` CLI. |
| `dev_agent.py` | `dev_agent` | Full project builder. Plans project structure with `gemini-2.5-flash`, writes each file with `gemini-2.5-flash-lite`, installs deps, opens VS Code, runs the project, and auto-fixes errors (up to 4 attempts). Projects saved to `~/Desktop/JarvisProjects/`. |
| `screen_processor.py` | `screen_process` | Captures screen via OpenCV (`CAP_DSHOW` on Windows, `CAP_ANY` elsewhere) or PIL fallback. Sends frame to Gemini vision for analysis. Camera index auto-detected and cached in `api_keys.json`. |
| `send_message.py` | `send_message` | Sends messages via WhatsApp (desktop), Instagram (web), Telegram (desktop), or any generic app using `pyautogui` automation. |
| `reminder.py` | `reminder` | Schedules Windows Task Scheduler jobs. Writes a temporary `.pyw` script that shows a toast notification (`win10toast`) and plays a beep, then registers it with `schtasks`. |
| `youtube_video.py` | `youtube_video` | Play: opens browser, searches YouTube, uses CV2 edge detection to locate thumbnails, clicks the second result. Summarize: shows tkinter URL dialog, fetches transcript via `youtube_transcript_api`, summarizes with Gemini. |
| `weather_report.py` | `weather_report` | Fetches weather data from an external weather API. |
| `computer_settings.py` | `computer_settings` | 100+ named actions in `ACTION_MAP` covering brightness, volume, Wi-Fi, Bluetooth, time zone, screen saver, UAC, firewall, dark mode, etc. If `action` param is absent, Gemini detects intent from `description`. Volume control uses `pycaw`/`comtypes` on Windows. `get_desktop_context()` returns system info string for session prompt injection. |
| `desktop.py` | `desktop_control` | Desktop management: `set_wallpaper` (ctypes on Windows, osascript on macOS), `organize` (by_type, by_date), `clean` (archives to folder), `list`, `stats`. `task` action: Gemini generates `pyautogui` code → sandboxed `exec()` with restricted builtins (no `subprocess`, no file deletion). |
| `computer_control.py` | `computer_control` | Mouse and keyboard control via `pyautogui`. |
| `flight_finder.py` | `flight_finder` | Opens Google Flights via `browser_control`, waits for load, scrapes text, parses with Gemini into structured flight JSON. Optionally saves results to Notepad. |
| `protocol_manager.py` | `protocol` | Runs named step sequences from `config/protocols.json`. See **Protocols** section below. |

#### Protocols (`config/protocols.json`)

A protocol is a named list of steps. Each step specifies a `tool` and `parameters`. Built-in step tools: `speak`, `wait`, `close_all_windows`. All other tool names are delegated to `agent/executor._call_tool()`.

Protocols run in a background daemon thread so voice interaction is not blocked. A global interrupt flag (`agent/task_queue.is_interrupted()`) is checked between steps.

Management: `add`, `remove`, `list` actions on the `protocol` tool. Protocols are resolved by exact ID match, trigger phrase substring, or display name.

---

### Agent Subsystem (`agent/`)

Used when the user's request requires a multi-step plan. Invoked via the `agent_task` tool or internally by some actions.

#### Planner (`agent/planner.py`)

`create_plan(goal: str) -> dict` — Calls `gemini-2.5-flash-lite` to produce a JSON plan:
```json
{
  "steps": [
    {"step": 1, "tool": "web_search", "description": "...", "parameters": {...}},
    ...
  ]
}
```
Maximum 5 steps. `generated_code` steps are replaced with `web_search` automatically. Falls back to a single `web_search` step if JSON parsing fails.

`replan(goal, completed_steps, failed_step, error) -> dict` — Calls `gemini-2.5-flash` to produce a revised plan given what has been completed and what failed.

#### Executor (`agent/executor.py`)

**`AgentExecutor.execute(goal, speak, cancel_flag)`** — Main execution loop:

1. Calls `create_plan(goal)`.
2. Iterates steps, calling `_call_tool(tool, params, speak)` for each.
3. On failure, calls `analyze_error()` which returns an `ErrorDecision`:
   - `RETRY` — wait 2 s, try again (up to 3 attempts).
   - `SKIP` — mark step complete, continue.
   - `ABORT` — stop and return error message.
   - `REPLAN` — try `generate_fix()` for an alternative step; if that fails, call `replan()`.
4. Max 2 replan attempts before aborting.
5. On success, calls `_summarize()` which asks `gemini-2.5-flash-lite` for a one-sentence summary addressed to "sir".

**`_run_generated_code(description, speak)`** — Asks `gemini-2.5-flash` to write Python code, writes it to a temp file, executes it with `subprocess.run(timeout=120)`, cleans up in `finally`. Used for tasks without a dedicated tool.

**`_inject_context(params, tool, step_results, goal)`** — For `file_controller` write steps with missing content, injects accumulated results from previous steps, optionally translated to the goal's language via Gemini.

#### Error Handler (`agent/error_handler.py`)

`analyze_error(step, error_msg, attempt) -> dict` — Returns `{decision, user_message, reason, fix_suggestion}`.

`generate_fix(step, error_msg, fix_suggestion) -> dict` — Returns a revised step dict.

#### Task Queue (`agent/task_queue.py`)

`TaskQueue` is a singleton priority queue. Tasks have a `cancel_flag` (`threading.Event`) and a `task_id`.

`_run_task()` wraps `AgentExecutor.execute()` in a `concurrent.futures.ThreadPoolExecutor` with a 300 s timeout. On timeout, `cancel_flag` is set and `TimeoutError` is raised. `_active_count` is always decremented in `finally`.

Global interrupt: `set_interrupt()` / `clear_interrupt()` / `is_interrupted()` — checked by both task execution and protocol steps.

---

### Memory Subsystem (`memory/`)

#### Memory Manager (`memory/memory_manager.py`)

Default backend. Stores facts as a JSON file at `config/memory.json`. Thread-safe via `threading.Lock`. 

`save_memory(memory: dict)` — Writes JSON to disk inside a lock; errors are caught and logged (do not propagate).

`get_memory_context() -> str` — Returns a formatted string of all facts for injection into the system prompt.

`update_memory(new_facts: dict)` — Merges new facts into existing memory; string values for the same key are appended, not overwritten.

#### Qdrant Store (`memory/qdrant_store.py`)

Optional vector memory backend. Activated by setting `memory_backend: "qdrant"` in `config/api_keys.json`.

- Embedded Qdrant instance stored at `./data/qdrant`.
- Model: `paraphrase-multilingual-MiniLM-L12-v2` (384-dimensional vectors, cosine distance).
- Point IDs are stable SHA-256 hashes of `category:key` so upserts are idempotent.
- `search_facts(query, top_k=5)` — semantic similarity search.
- `migrate_from_json(json_path)` — one-shot import from the JSON memory file.

#### Config Manager (`memory/config_manager.py`)

Manages `config/api_keys.json`. Functions: `save_api_keys()`, `load_api_keys()`, `get_gemini_key()`, `is_configured()`.

---

### WebSocket UI Bridge (`ws_ui.py`)

WebSocketUI runs a WebSocket server on `ws://localhost:8765`. The Tauri frontend connects to it on startup.

Message types (JSON):

| type | fields | meaning |
|---|---|---|
| `status` | `value` | `LISTENING`, `THINKING`, `EXECUTING`, `CONNECTING`, `OFFLINE` |
| `log` | `sender`, `text` | Chat log entry |
| `tool` | `name`, `state` | Tool started (`start`) or finished (`end`) |

State-setting methods: `set_connecting()`, `set_thinking()`, `set_executing(tool_name)`, `set_idle()` (→ LISTENING), `set_failed()` (→ OFFLINE).

`write_log(sender, text)` — Broadcasts a log message. Called by action modules to surface activity in the HUD.

---

### ARIA Gateway (`aria/`)

Optional subsystem for the ARIA Pi glasses. Disabled unless `aria_secret` is present in `config/api_keys.json`.

#### API Server (`aria/api_server.py`)

FastAPI application. Started by `start_aria_server(vector)` in `aria/server_runner.py` on a daemon thread via uvicorn. Binds to `0.0.0.0` on port from `api_keys.json["aria_port"]` (default 8765 — note: this conflicts with `ws_ui.py` if both are active; ensure distinct ports in config).

**Endpoints:**

| Endpoint | Auth | Description |
|---|---|---|
| `WS /ws/audio` | Bearer token | Receives PCM audio chunks from Pi; feeds into `ARIAInputAdapter` |
| `WS /ws/display` | Bearer token | Pushes text/status JSON to Pi's OLED display |
| `POST /tool/{name}` | Bearer token | Calls any registered tool by name; runs via `loop.run_in_executor` |
| `GET /tools` | Bearer token | Returns list of available tool names |
| `GET /status` | Bearer token | Returns `{"status": "online"}` |

Authentication: HTTP header `Authorization: Bearer <aria_secret>`.

#### Input Adapter (`aria/input_adapter.py`)

`ARIAInputAdapter.feed_chunk(pcm_bytes)` — Thread-safe. Uses `loop.call_soon_threadsafe(queue.put_nowait, msg)` to push PCM into `VectorLive.out_queue`. Drops chunks silently if queue is full (`maxsize=10`).

#### Output Adapter (`aria/output_adapter.py`)

`ARIAOutputAdapter` — Registers two callbacks on the `VectorLive` instance: `on_text(text)` and `on_status(status)`. When V.E.C.T.O.R. speaks or changes state, the adapter broadcasts a JSON message to all `/ws/display` WebSocket clients using `asyncio.run_coroutine_threadsafe`.

#### OLED Formatter (`aria/oled_formatter.py`)

`format_for_oled(text: str) -> str` — Wraps text to 4 lines × 20 characters. Word-safe: does not break mid-word unless a single word exceeds 20 characters, in which case it is truncated. Returns a string with `\n` separators.

---

## Desktop UI (`desktop/tauri/`)

Built with Tauri v2, React 18, and TypeScript. Run with `npm run tauri dev` from `desktop/tauri/`.

### Frontend (`src/App.tsx`)

Connects to `ws://localhost:8765` on mount. Maintains:
- `status` state — drives the central reactor ring color and pulse animation.
- `logs` array — capped at `MAX_LOGS = 50` entries, shown as a scrolling chat list.

Status → visual mapping:
- `LISTENING` — cyan ring, steady glow
- `THINKING` — amber ring, `thinking-pulse` animation (1.4 s)
- `EXECUTING` — cyan ring, active tool name shown
- `CONNECTING` — muted pulse
- `OFFLINE` — red indicator

### Styles (`src/App.css`)

Cyan primary: `#00fff7`. Amber accent: `#FFB300`. Dark background with Iron Man reactor aesthetic. `thinking-pulse` keyframe animation at 1.4 s cycle.

---

## Setup & Configuration

### Prerequisites

- Python 3.11+
- Node.js 18+ and Rust (for Tauri build)
- Google Gemini API key with access to `gemini-2.5-flash-native-audio-preview-12-2025`
- Windows 10/11 recommended; macOS has partial support (no reminders, no volume control)

### Installation

```bash
# Python dependencies
pip install -r requirements.txt
playwright install

# Tauri frontend
cd desktop/tauri
npm install
```

### Configuration (`config/api_keys.json`)

```json
{
  "gemini_api_key": "YOUR_KEY_HERE",
  "aria_secret": "optional-bearer-token",
  "aria_port": 8766,
  "memory_backend": "json",
  "camera_index": null
}
```

| Key | Required | Description |
|---|---|---|
| `gemini_api_key` | Yes | Google Gemini API key |
| `aria_secret` | No | Enables ARIA gateway; sets bearer token |
| `aria_port` | No | ARIA server port (default 8765 — use a different port if ws_ui.py is also running) |
| `memory_backend` | No | `"json"` (default) or `"qdrant"` |
| `camera_index` | No | OpenCV camera index; `null` = auto-detect and cache |

### Running

```bash
# Backend only
python main.py

# With Tauri UI (development)
cd desktop/tauri && npm run tauri dev

# With Tauri UI (production build)
cd desktop/tauri && npm run tauri build
```

---

## Adding New Tools

### 1. Create the action module

Create `actions/my_tool.py`:

```python
from typing import Callable

def my_tool(
    parameters: dict,
    response: str | None = None,
    player=None,
    session_memory=None,
    speak: Callable | None = None,
) -> str:
    # parameters contains whatever fields Gemini will send
    value = parameters.get("my_param", "")
    # ... do work ...
    return "Result string sent back to Gemini."
```

### 2. Register the tool

In `actions/registry.py`, add to `TOOL_REGISTRY`:

```python
from actions.my_tool import my_tool

TOOL_REGISTRY["my_tool"] = my_tool
```

Add to `TOOL_DECLARATIONS`:

```python
{
    "name": "my_tool",
    "description": "What this tool does. Be specific — Gemini uses this to decide when to call it.",
    "parameters": {
        "type": "object",
        "properties": {
            "my_param": {
                "type": "string",
                "description": "Description of the parameter"
            }
        },
        "required": ["my_param"]
    }
}
```

### 3. Register in executor (if used in agent tasks)

In `agent/executor._call_tool()`, add an `elif` branch:

```python
elif tool == "my_tool":
    from actions.my_tool import my_tool
    return my_tool(parameters=parameters, player=None, speak=speak) or "Done."
```

That's all. The tool is immediately available to Gemini in the next session.

---

## Known Limitations & Platform Notes

### Windows-only features

- **Reminders** (`reminder.py`) — Uses Windows Task Scheduler (`schtasks`) and `win10toast`. No macOS/Linux equivalent.
- **Volume control** (`computer_settings.py`) — Uses `pycaw` and `comtypes`. Guarded with `if _OS == "Windows"`. On other platforms, volume actions return an unsupported message.
- **Send message** (`send_message.py`) — Uses Win key automation via `pyautogui` to open apps. Requires Windows desktop environment.
- **Camera backend** (`screen_processor.py`) — Uses `cv2.CAP_DSHOW` on Windows for lower latency, `cv2.CAP_ANY` elsewhere.

### macOS support

- `close_all_windows` in `protocol_manager.py` supports macOS via `osascript`.
- Wallpaper setting in `desktop.py` supports macOS via `osascript`.
- `open_app.py` has macOS fallback via `subprocess.Popen(["open", "-a", app_name])`.
- Most `computer_settings.py` actions are Windows-only and silently fail on macOS.

### Agent / task limitations

- **Planner** produces a maximum of 5 steps. Complex tasks requiring more steps will be truncated or require the user to chain multiple requests.
- **Generated code** (`_run_generated_code`) runs arbitrary Python from Gemini with no sandboxing beyond a subprocess boundary. The generated code has full access to the host system.
- **Task timeout** is 300 seconds. Tasks that genuinely require longer will be cancelled.
- **Replan** is attempted at most 2 times before the task is aborted.

### Gemini Live API

- The Native Audio model (`gemini-2.5-flash-native-audio-preview-12-2025`) is a preview endpoint. API behavior, rate limits, and availability may change.
- Function calling within a live session follows Gemini's sequential constraint: only one tool can be in-flight at a time. Parallel tool dispatch is not supported.
- The `speak()` method injects text as a model content part to force speech. This is a workaround for triggering TTS without a user turn and may behave differently across model versions.

### Memory

- JSON memory (`memory_manager.py`) is unbounded. Large memory blobs increase prompt token usage on every session start.
- Qdrant backend requires `sentence-transformers` and downloads the embedding model (~90 MB) on first use.
- Memory extraction is best-effort: the two-stage Gemini call can miss facts or extract incorrect values. No ground-truth validation is performed.

### ARIA Gateway

- The ARIA gateway and `ws_ui.py` both default to port 8765. If running both, set `aria_port` to a different value in `config/api_keys.json`.
- OLED output is formatted for 4 × 20 characters. Longer responses are truncated; the Pi display receives only the first 4 lines.
- PCM chunks from the Pi are dropped if `out_queue` is full (maxsize=10). Under high mic load from both sources simultaneously, ARIA audio may be silently discarded.

### Browser automation

- `browser_control.py` attempts to reuse an existing Chrome instance via CDP at port 9222. Chrome must be launched with `--remote-debugging-port=9222` for reuse to work; otherwise a fresh instance is launched.
- Playwright operations are synchronous and block the thread pool worker they run in. Long-running browser actions (e.g., waiting for page load) hold a thread for their duration.

### `dev_agent` (project builder)

- Auto-fix loop runs up to 4 times. If the generated project fails to run after 4 fixes, the agent reports failure without cleanup. Generated projects remain at `~/Desktop/JarvisProjects/`.
- The `exec()` sandbox in `desktop_control` restricts `subprocess` and file deletion but does not prevent network access or reading arbitrary files.
