"""
PanelBridge — thread-safe bridge between VectorLive (background thread)
and the PySide6 panel (main Qt thread).

Implements the same public interface as VectorUI so it can be passed
directly to VectorLive as `ui`.

Thread-safety strategy: background thread writes to _state under _lock,
then queues a copy.  A QTimer on the main thread drains the queue and
emits state_updated once per tick (~50 ms).

All public methods are None-safe: if Qt/PySide6 is unavailable or the
bridge is used in headless mode the methods simply log to stdout.
"""
from __future__ import annotations

import logging
import queue
import threading
from copy import copy
from pathlib import Path

logger = logging.getLogger("panel_bridge")

# ---------------------------------------------------------------------------
# Optional Qt import — graceful degradation for headless mode
# ---------------------------------------------------------------------------

try:
    from PySide6.QtCore import QObject, QTimer, Signal as _Signal
    _QT_AVAILABLE = True
except ImportError:
    _QT_AVAILABLE = False
    QObject = object   # type: ignore[misc,assignment]

    class _Signal:  # type: ignore[no-redef]
        """No-op signal stub used when PySide6 is not installed."""
        def __init__(self, *args, **kwargs):
            self._callbacks: list = []
        def connect(self, cb):
            self._callbacks.append(cb)
        def emit(self, *args):
            for cb in self._callbacks:
                try:
                    cb(*args)
                except Exception:
                    pass

try:
    from .view_models import PanelState, PendingPrompt
except ImportError:
    # Minimal stubs for headless usage
    from dataclasses import dataclass, field

    @dataclass
    class PendingPrompt:  # type: ignore[no-redef]
        kind: str = "confirmation"
        message: str = ""

    @dataclass
    class PanelState:  # type: ignore[no-redef]
        mode: str = "IDLE"
        runtime_state: str = "idle"
        current_action_text: str = ""
        pending_prompt: PendingPrompt | None = None
        last_user: str = ""
        last_vector: str = ""
        speaking: bool = False
        command_summary: str | None = None


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
    "protocol":          "Protocol",
}


def _tool_step(name: str, args: dict) -> str:
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
    """Thread-safe UI bridge. Emits state_updated on the main thread.
    Falls back to stdout logging when Qt is not available (headless mode).
    """

    state_updated = _Signal(object)

    def __init__(self, parent=None) -> None:
        if _QT_AVAILABLE:
            super().__init__(parent)
        else:
            # object.__init__ takes no args with PySide6 stub
            super().__init__()

        self._lock      = threading.Lock()
        self._state     = PanelState()
        self._queue: queue.SimpleQueue = queue.SimpleQueue()
        self._vector_ref = None

        if _QT_AVAILABLE:
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._flush)
            self._timer.start(50)
        else:
            self._timer = None

    # ------------------------------------------------------------------ #
    # VectorUI-compatible interface (may be called from any thread)       #
    # ------------------------------------------------------------------ #

    def write_log(self, text: str) -> None:
        if text is None:
            return
        t     = text.strip()
        lower = t.lower()

        print(f"[VECTOR] {t}")

        if not _QT_AVAILABLE:
            return

        with self._lock:
            s = self._clone()

            if lower.startswith("you:"):
                user_text = t[4:].strip()
                s.last_user          = user_text
                s.runtime_state      = "thinking"
                s.mode               = "VOICE"
                s.current_action_text = "Processing…"

            elif lower.startswith("v.e.c.t.o.r.:"):
                jarvis_text = t[13:].strip()
                s.last_vector        = jarvis_text
                s.runtime_state      = "answering"
                s.mode               = "VOICE"
                s.current_action_text = (
                    jarvis_text[:140] + "…"
                    if len(jarvis_text) > 140
                    else jarvis_text
                )

            elif "online" in lower or "connected" in lower:
                s.runtime_state      = "listening"
                s.mode               = "IDLE"
                s.current_action_text = "Listening…"

            self._state = s

        self._queue.put(self._clone_locked())

    def start_speaking(self) -> None:
        if not _QT_AVAILABLE:
            return
        with self._lock:
            self._state       = self._clone()
            self._state.speaking = True
        self._queue.put(self._clone_locked())

    def stop_speaking(self) -> None:
        if not _QT_AVAILABLE:
            return
        with self._lock:
            s = self._clone()
            s.speaking = False
            if s.runtime_state not in ("failed",):
                s.runtime_state      = "listening"
                s.current_action_text = "Listening…"
            self._state = s
        self._queue.put(self._clone_locked())

    def wait_for_api_key(self) -> None:
        import time
        api_file = Path(__file__).resolve().parent.parent.parent / "config" / "api_keys.json"
        while not api_file.exists():
            time.sleep(0.2)

    # ------------------------------------------------------------------ #
    # State callbacks
    # ------------------------------------------------------------------ #

    def set_connecting(self) -> None:
        self._set(runtime_state="thinking", mode="IDLE", current_action_text="Connecting…")

    def set_executing(self, tool_name: str | None = None, args: dict | None = None) -> None:
        tool_name = tool_name or ""
        args      = args or {}
        display   = _TOOL_DISPLAY.get(tool_name, tool_name)
        step      = _tool_step(tool_name, args)
        text      = f"{display} — {step}" if step else display
        self._set(
            runtime_state="executing",
            mode="COMMAND",
            command_summary=display,
            current_action_text=text,
        )

    def set_idle(self) -> None:
        self._set(
            runtime_state="thinking",
            command_summary=None,
            current_action_text="Processing…",
        )

    def set_failed(self, message: str | None = None) -> None:
        self._set(
            runtime_state="failed",
            mode="ERROR",
            current_action_text=(message or "Error")[:200],
        )

    def set_pending_prompt(self, prompt: "PendingPrompt | None") -> None:
        if prompt is None:
            return
        with self._lock:
            s = self._clone()
            s.pending_prompt = prompt
            s.runtime_state  = (
                "awaiting_confirmation"
                if prompt.kind == "confirmation"
                else "awaiting_clarification"
            )
            self._state = s
        self._queue.put(self._clone_locked())

    def clear_pending_prompt(self) -> None:
        with self._lock:
            s = self._clone()
            s.pending_prompt      = None
            s.runtime_state       = "thinking"
            s.current_action_text = "Processing…"
            self._state = s
        self._queue.put(self._clone_locked())

    def submit_text(self, text: str | None) -> None:
        if not text:
            return
        if self._vector_ref is not None:
            try:
                self._vector_ref.speak(text)
            except Exception as e:
                logger.warning(f"submit_text speak error: {e}")
        with self._lock:
            s = self._clone()
            s.last_user           = text
            s.runtime_state       = "thinking"
            s.mode                = "VOICE"
            s.current_action_text = "Processing…"
            self._state = s
        self._queue.put(self._clone_locked())

    def get_state(self) -> PanelState:
        with self._lock:
            return self._clone()

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    def _set(self, **kwargs) -> None:
        with self._lock:
            s = self._clone()
            for k, v in kwargs.items():
                setattr(s, k, v)
            self._state = s
        self._queue.put(self._clone_locked())

    def _clone(self) -> PanelState:
        return copy(self._state)

    def _clone_locked(self) -> PanelState:
        with self._lock:
            return copy(self._state)

    def _flush(self) -> None:
        if not _QT_AVAILABLE:
            return
        latest = None
        while True:
            try:
                latest = self._queue.get_nowait()
            except Exception:
                break
        if latest is not None:
            try:
                self.state_updated.emit(latest)
            except Exception as e:
                logger.debug(f"_flush emit error: {e}")


# ---------------------------------------------------------------------------
# HeadlessUI — minimal VectorUI-compatible stub for ARIA / server mode
# ---------------------------------------------------------------------------

class HeadlessUI:
    """
    Drop-in replacement for VectorUI when running V.E.C.T.O.R. without any GUI.
    All methods are safe to call; output goes to stdout.
    """

    def write_log(self, text: str) -> None:
        if text:
            print(f"[V.E.C.T.O.R.] {text.strip()}")

    def wait_for_api_key(self) -> None:
        import time
        api_file = Path(__file__).resolve().parent.parent.parent / "config" / "api_keys.json"
        while not api_file.exists():
            time.sleep(0.2)

    def set_connecting(self) -> None:
        print("[V.E.C.T.O.R.] Connecting…")

    def set_executing(self, tool_name: str | None = None, args: dict | None = None) -> None:
        print(f"[V.E.C.T.O.R.] Executing: {tool_name}")

    def set_idle(self) -> None:
        pass

    def set_failed(self, message: str | None = None) -> None:
        print(f"[V.E.C.T.O.R.] Failed: {message}")
