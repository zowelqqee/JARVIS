"""
ARIAOutputAdapter — broadcasts JARVIS output to all connected /ws/display WebSocket clients.
Registered as on_text_response and on_status_change callbacks on JarvisLive.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

from aria.oled_formatter import format_for_oled

if TYPE_CHECKING:
    from main import JarvisLive

logger = logging.getLogger("aria.output_adapter")


class ARIAOutputAdapter:
    def __init__(self) -> None:
        self._clients: list = []  # list[WebSocket]
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Called from FastAPI startup event with the uvicorn event loop."""
        self._loop = loop

    def add_client(self, ws) -> None:
        if ws not in self._clients:
            self._clients.append(ws)
        logger.info(f"[ARIA] Display client added (total={len(self._clients)})")

    def remove_client(self, ws) -> None:
        try:
            self._clients.remove(ws)
        except ValueError:
            pass
        logger.info(f"[ARIA] Display client removed (total={len(self._clients)})")

    def register_callbacks(self, jarvis: "JarvisLive") -> None:
        """Wire self into JarvisLive callbacks."""
        jarvis.on_text_response = self.on_text
        jarvis.on_status_change = self.on_status

    # ------------------------------------------------------------------
    # Callback methods (called from JARVIS asyncio thread)
    # ------------------------------------------------------------------

    def on_text(self, text: str) -> None:
        lines = format_for_oled(text)
        self._broadcast({"type": "response", "lines": lines})

    def on_status(self, status: str) -> None:
        self._broadcast({"type": "status", "text": status})

    # ------------------------------------------------------------------
    # Internal broadcast
    # ------------------------------------------------------------------

    def _broadcast(self, payload: dict) -> None:
        if not self._clients or self._loop is None:
            return
        msg = json.dumps(payload, ensure_ascii=False)
        asyncio.run_coroutine_threadsafe(self._async_broadcast(msg), self._loop)

    async def _async_broadcast(self, msg: str) -> None:
        dead = []
        for ws in list(self._clients):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.remove_client(ws)
