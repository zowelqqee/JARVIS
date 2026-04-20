"""
Starts the ARIA FastAPI/uvicorn server in a daemon thread.
Call start_aria_server(vector_instance) after VectorLive.run() sets self.vector_loop.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import VectorLive

logger = logging.getLogger("aria.server_runner")

_server_started = False


def _load_port() -> int:
    cfg = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
        return int(data.get("aria_port", 8765))
    except Exception:
        return 8765


def start_aria_server(vector: "VectorLive") -> None:
    """
    Launch uvicorn in a daemon thread and wire up ARIA adapters.
    Safe to call multiple times — only starts once.
    """
    global _server_started
    if _server_started:
        return
    _server_started = True

    from aria.input_adapter  import ARIAInputAdapter
    from aria.output_adapter import ARIAOutputAdapter
    from aria.api_server     import app, inject

    input_adapter  = ARIAInputAdapter(vector)
    output_adapter = ARIAOutputAdapter()

    # Wire callbacks into VectorLive
    output_adapter.register_callbacks(vector)

    inject(vector, input_adapter, output_adapter)

    port = _load_port()

    def _run():
        import uvicorn
        logger.info(f"[ARIA] Starting server on port {port}")
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")

    t = threading.Thread(target=_run, daemon=True, name="aria-server")
    t.start()
    logger.info(f"[ARIA] Server thread started (port={port})")
