"""
ARIAInputAdapter — receives PCM chunks from the Pi WebSocket handler
and delivers them into VectorLive's out_queue (the queue that _send_realtime
reads and forwards to Gemini).
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import VectorLive

logger = logging.getLogger("aria.input_adapter")


class ARIAInputAdapter:
    def __init__(self, vector: "VectorLive") -> None:
        self._vector = vector

    def feed_chunk(self, pcm_bytes: bytes) -> None:
        """
        Thread-safe: schedule PCM chunk delivery into the V.E.C.T.O.R. event loop.
        pcm_bytes must be 16 kHz mono int16 PCM.
        """
        loop = self._vector.vector_loop
        if loop is None or not loop.is_running():
            return

        queue = self._vector.out_queue
        if queue is None:
            return

        msg = {"data": pcm_bytes, "mime_type": "audio/pcm"}
        try:
            loop.call_soon_threadsafe(queue.put_nowait, msg)
        except asyncio.QueueFull:
            logger.debug("[ARIA] out_queue full, dropping chunk")
        except Exception as e:
            logger.warning(f"[ARIA] feed_chunk error: {e}")
