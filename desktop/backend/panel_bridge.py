"""
PanelBridge — thread-safe bridge between JarvisLive (background thread)
and the PySide6 panel (main Qt thread).

Implements the same public interface as JarvisUI so it can be passed
directly to JarvisLive as `ui`.

Thread-safety strategy: background thread writes to _state under _lock,
then queues a copy.  A QTimer on the main thread drains the queue and
emits state_updated once per tick (~50 ms).
"""
from __future__ import annotations

import queue
import threading
from copy import copy
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from .view_models import PanelState, PendingPrompt


_TOOL_DISPLAY: dict[str, str] = {
    "open_app":          "Opening app",
    "web_search":        "Searching web",
    "weather_report":    "Checking weather",
    "send_message":      "Sending message",
    "reminder":          "Setting reminder",
    "youtube_video":     "YouTube",
    "screen_process":    "Analysing screen",
    "computer_settings": "Computer settings",
    "cmd_control":       "Running command",
    "desktop_control":   "Desktop control",
    "code_helper":       "Code helper",
    "dev_agent":         "Dev agent",
    "agent_task":        "Running task",
    "browser_control":   "Browser control",
    "file_controller":   "File operation",
    "computer_control":  "Computer control",
    "flight_finder":     "Finding flights",
}


def _tool_step(name: str, args: dict) -> str:
    """Short human-readable summary of tool arguments."""
    if name == "open_app":
        return args.get("app_name", "")
    if name == "web_search":
        return args.get("query", "")[:60]
    if name == "weather_report":
        return args.get("city", "")
    if name == "send_message":
        return f"to {args.get('receiver', '')}"
    if name in ("browser_control",):
        return (args.get("url") or args.get("query") or args.get("description", ""))[:60]
    if name == "file_controller":
        return args.get("path", "")[:60]
    if name == "cmd_control":
        return args.get("task", "")[:60]
    if name in ("computer_settings", "computer_control"):
        return (args.get("description") or args.get("action", ""))[:60]
    if name == "agent_task":
        return args.get("goal", "")[:60]
    if name == "youtube_video":
        return (args.get("query") or args.get("action", ""))[:60]
    if name == "flight_finder":
        return f"{args.get('origin', '')} → {args.get('destination', '')}"
    return ""


class PanelBridge(QObject):
    """Thread-safe UI bridge. Emit state_updated on the main thread."""

    state_updated = Signal(object)   # PanelState

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._lock = threading.Lock()
        self._state = PanelState()
        self._queue: queue.SimpleQueue[PanelState] = queue.SimpleQueue()
        self._jarvis_ref = None          # set by desktop/main.py after JarvisLive created

        # Drain queue on main thread at ~20 fps
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._flush)
        self._timer.start(50)

    # ------------------------------------------------------------------ #
    # JarvisUI-compatible interface (may be called from any thread)       #
    # ------------------------------------------------------------------ #

    def write_log(self, text: str) -> None:
        """Called by JarvisLive when a turn completes or system message arrives."""
        t = text.strip()
        lower = t.lower()

        with self._lock:
            s = self._clone()

            if lower.startswith("you:"):
                user_text = t[4:].strip()
                s.last_user = user_text
                s.runtime_state = "thinking"
                s.mode = "VOICE"
                s.current_action_text = "Processing…"

            elif lower.startswith("jarvis:"):
                jarvis_text = t[7:].strip()
                s.last_jarvis = jarvis_text
                s.runtime_state = "answering"
                s.mode = "VOICE"
                # Show up to 140 chars in the Current Action section
                s.current_action_text = (
                    jarvis_text[:140] + "…"
                    if len(jarvis_text) > 140
                    else jarvis_text
                )

            elif "online" in lower or "connected" in lower:
                s.runtime_state = "listening"
                s.mode = "IDLE"
                s.current_action_text = "Listening…"

            self._state = s

        self._queue.put(self._clone_locked())

    def start_speaking(self) -> None:
        with self._lock:
            self._state = self._clone()
            self._state.speaking = True
        self._queue.put(self._clone_locked())

    def stop_speaking(self) -> None:
        with self._lock:
            s = self._clone()
            s.speaking = False
            if s.runtime_state not in ("failed",):
                s.runtime_state = "listening"
                s.current_action_text = "Listening…"
            self._state = s
        self._queue.put(self._clone_locked())

    def wait_for_api_key(self) -> None:
        """Block until config/api_keys.json exists (mirrors JarvisUI.wait_for_api_key)."""
        import time
        api_file = Path(__file__).resolve().parent.parent.parent / "config" / "api_keys.json"
        while not api_file.exists():
            time.sleep(0.2)

    # ------------------------------------------------------------------ #
    # State callbacks — called from JarvisLive via hasattr guards         #
    # ------------------------------------------------------------------ #

    def set_connecting(self) -> None:
        self._set(runtime_state="thinking", mode="IDLE", current_action_text="Connecting…")

    def set_executing(self, tool_name: str, args: dict) -> None:
        display = _TOOL_DISPLAY.get(tool_name, tool_name)
        step = _tool_step(tool_name, args)
        text = f"{display} — {step}" if step else display
        self._set(
            runtime_state="executing",
            mode="COMMAND",
            command_summary=display,
            current_action_text=text,
        )

    def set_idle(self) -> None:
        """After a tool call completes — model is still processing."""
        self._set(
            runtime_state="thinking",
            command_summary=None,
            current_action_text="Processing…",
        )

    def set_failed(self, message: str) -> None:
        self._set(
            runtime_state="failed",
            mode="ERROR",
            current_action_text=message[:200],
        )

    def set_pending_prompt(self, prompt: PendingPrompt) -> None:
        """Surfaces a confirmation or clarification prompt."""
        with self._lock:
            s = self._clone()
            s.pending_prompt = prompt
            s.runtime_state = (
                "awaiting_confirmation"
                if prompt.kind == "confirmation"
                else "awaiting_clarification"
            )
            self._state = s
        self._queue.put(self._clone_locked())

    def clear_pending_prompt(self) -> None:
        with self._lock:
            s = self._clone()
            s.pending_prompt = None
            s.runtime_state = "thinking"
            s.current_action_text = "Processing…"
            self._state = s
        self._queue.put(self._clone_locked())

    def submit_text(self, text: str) -> None:
        """Called from the Input Bar — routes text into the Gemini session."""
        if self._jarvis_ref is not None:
            self._jarvis_ref.speak(text)
        with self._lock:
            s = self._clone()
            s.last_user = text
            s.runtime_state = "thinking"
            s.mode = "VOICE"
            s.current_action_text = "Processing…"
            self._state = s
        self._queue.put(self._clone_locked())

    def get_state(self) -> PanelState:
        with self._lock:
            return self._clone()

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _set(self, **kwargs) -> None:
        """Atomically update listed fields and queue a state copy."""
        with self._lock:
            s = self._clone()
            for k, v in kwargs.items():
                setattr(s, k, v)
            self._state = s
        self._queue.put(self._clone_locked())

    def _clone(self) -> PanelState:
        """Shallow-copy current state. Call inside _lock."""
        return copy(self._state)

    def _clone_locked(self) -> PanelState:
        """Shallow-copy current state with lock acquired."""
        with self._lock:
            return copy(self._state)

    def _flush(self) -> None:
        """Drain queue on main thread, emit only the latest state."""
        latest: PanelState | None = None
        while True:
            try:
                latest = self._queue.get_nowait()
            except Exception:
                break
        if latest is not None:
            self.state_updated.emit(latest)
