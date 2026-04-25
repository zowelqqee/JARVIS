"""
WebSocketUI  —  VectorUI-compatible bridge that broadcasts HUD events
to the Tauri/React frontend over WebSocket on ws://localhost:8765.

Drop-in replacement for ui.VectorUI; pass directly to VectorLive as `ui`.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path


class WebSocketUI:
    HOST = "localhost"
    PORT = 8765

    def __init__(self) -> None:
        self._clients: set = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._current_tool: str | None = None

    # ── internal ───────────────────────────────────────────────────────────

    def _broadcast(self, msg: dict) -> None:
        """Thread-safe fire-and-forget. Safe to call from any thread or coroutine."""
        if self._loop is None or self._loop.is_closed():
            return
        data = json.dumps(msg, ensure_ascii=False)
        try:
            current = asyncio.get_running_loop()
        except RuntimeError:
            current = None
        if current is self._loop:
            self._loop.create_task(self._send_all(data))
        else:
            asyncio.run_coroutine_threadsafe(self._send_all(data), self._loop)

    async def _send_all(self, data: str) -> None:
        for ws in set(self._clients):
            try:
                await ws.send(data)
            except Exception:
                self._clients.discard(ws)

    async def _ws_handler(self, ws) -> None:
        self._clients.add(ws)
        try:
            await ws.wait_closed()
        finally:
            self._clients.discard(ws)

    async def serve_forever(self) -> None:
        import websockets
        print(f"[WS] Listening on ws://{self.HOST}:{self.PORT}")
        async with websockets.serve(self._ws_handler, self.HOST, self.PORT):
            await asyncio.Future()  # run until cancelled

    # ── VectorUI-compatible interface ──────────────────────────────────────

    def wait_for_api_key(self) -> None:
        import time
        while not os.getenv("GEMINI_API_KEY"):
            cfg = Path(__file__).parent / "config" / "api_keys.json"
            if cfg.exists():
                break
            time.sleep(0.2)

    def write_log(self, text: str) -> None:
        if not text:
            return
        t = text.strip()
        lower = t.lower()
        if lower.startswith("you:"):
            sender, content = "You", t[4:].strip()
        elif lower.startswith("v.e.c.t.o.r.:"):
            sender, content = "V.E.C.T.O.R.", t[13:].strip()
        else:
            sender, content = "SYS", t
        print(f"[{sender}] {content}")
        self._broadcast({"type": "log", "sender": sender, "text": content})

    def set_connecting(self) -> None:
        self._broadcast({"type": "status", "value": "CONNECTING"})

    def set_executing(self, tool_name: str | None = None, args: dict | None = None) -> None:
        name = tool_name or ""
        self._current_tool = name
        self._broadcast({"type": "status", "value": "EXECUTING"})
        if name:
            self._broadcast({"type": "tool", "name": name, "state": "start"})

    def set_idle(self) -> None:
        if self._current_tool:
            self._broadcast({"type": "tool", "name": self._current_tool, "state": "end"})
            self._current_tool = None
        self._broadcast({"type": "status", "value": "LISTENING"})

    def set_failed(self, message: str | None = None) -> None:
        print(f"[V.E.C.T.O.R.] Error: {message}")
        if self._current_tool:
            self._broadcast({"type": "tool", "name": self._current_tool, "state": "end"})
            self._current_tool = None
        self._broadcast({"type": "status", "value": "OFFLINE"})

    def start_speaking(self) -> None:
        pass

    def stop_speaking(self) -> None:
        self._broadcast({"type": "status", "value": "LISTENING"})
