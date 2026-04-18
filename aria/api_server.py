"""
ARIA FastAPI server.

Endpoints:
  WS  /ws/audio   — Pi sends PCM audio chunks (16 kHz mono int16) → Gemini
  WS  /ws/display — Pi receives status/response JSON from JARVIS
  POST /tool/{name} — call any tool directly without Gemini
  GET  /tools       — list available tools
  GET  /status      — {"jarvis_running": bool, "aria_connected": bool}

Auth: all endpoints require  Authorization: Bearer <aria_secret>
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger("aria.api_server")

app = FastAPI(title="ARIA Gateway", version="1.0.0")
security = HTTPBearer(auto_error=False)

# ---------------------------------------------------------------------------
# Global state injected by server_runner.py at startup
# ---------------------------------------------------------------------------

_jarvis_instance = None          # JarvisLive instance
_input_adapter   = None          # ARIAInputAdapter
_output_adapter  = None          # ARIAOutputAdapter
_server_loop: Optional[asyncio.AbstractEventLoop] = None  # FastAPI/uvicorn loop


def inject(jarvis, input_adapter, output_adapter):
    """Called by server_runner after JarvisLive starts."""
    global _jarvis_instance, _input_adapter, _output_adapter
    _jarvis_instance = jarvis
    _input_adapter   = input_adapter
    _output_adapter  = output_adapter


@app.on_event("startup")
async def _capture_loop():
    global _server_loop
    _server_loop = asyncio.get_running_loop()
    if _output_adapter is not None:
        _output_adapter.set_loop(_server_loop)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _load_secret() -> str:
    cfg = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
        return data.get("aria_secret", "")
    except Exception:
        return ""


def _verify(credentials: HTTPAuthorizationCredentials = Depends(security)):
    secret = _load_secret()
    if not secret:
        raise HTTPException(status_code=503, detail="aria_secret not configured in config/api_keys.json")
    if credentials is None or credentials.credentials != secret:
        raise HTTPException(status_code=401, detail="Invalid or missing Bearer token")
    return credentials.credentials


# ---------------------------------------------------------------------------
# WebSocket /ws/audio  — Pi microphone → Gemini
# ---------------------------------------------------------------------------

@app.websocket("/ws/audio")
async def ws_audio(websocket: WebSocket):
    # Manual token check for WebSocket (headers)
    token = websocket.headers.get("authorization", "")
    secret = _load_secret()
    if not secret or not token.lower().startswith("bearer ") or token[7:] != secret:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    logger.info("[ARIA] Pi audio WebSocket connected")

    try:
        while True:
            data = await websocket.receive_bytes()
            if _input_adapter is not None:
                _input_adapter.feed_chunk(data)
    except WebSocketDisconnect:
        logger.info("[ARIA] Pi audio WebSocket disconnected")
    except Exception as e:
        logger.error(f"[ARIA] ws_audio error: {e}")


# ---------------------------------------------------------------------------
# WebSocket /ws/display — JARVIS → Pi OLED
# ---------------------------------------------------------------------------

@app.websocket("/ws/display")
async def ws_display(websocket: WebSocket):
    token  = websocket.headers.get("authorization", "")
    secret = _load_secret()
    if not secret or not token.lower().startswith("bearer ") or token[7:] != secret:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    logger.info("[ARIA] Pi display WebSocket connected")

    if _output_adapter is not None:
        _output_adapter.add_client(websocket)

    try:
        while True:
            # Keep connection alive; Pi doesn't send display data
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info("[ARIA] Pi display WebSocket disconnected")
    except Exception as e:
        logger.error(f"[ARIA] ws_display error: {e}")
    finally:
        if _output_adapter is not None:
            _output_adapter.remove_client(websocket)


# ---------------------------------------------------------------------------
# POST /tool/{name} — direct tool call without Gemini
# ---------------------------------------------------------------------------

@app.post("/tool/{name}")
async def call_tool(name: str, request: Request, _: str = Depends(_verify)):
    from actions.registry import TOOL_REGISTRY

    handler = TOOL_REGISTRY.get(name)
    if handler is None:
        raise HTTPException(status_code=404, detail=f"Tool '{name}' not found")

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    parameters = body.get("parameters", {})

    ui    = _jarvis_instance.ui if _jarvis_instance else None
    speak = _jarvis_instance.speak if _jarvis_instance else (lambda t: None)

    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            None, lambda: handler(parameters, ui, speak)
        )
        return {"result": result or "Done."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# GET /tools
# ---------------------------------------------------------------------------

@app.get("/tools")
def list_tools(_: str = Depends(_verify)):
    from actions.registry import TOOL_REGISTRY
    return {"tools": list(TOOL_REGISTRY.keys())}


# ---------------------------------------------------------------------------
# GET /status
# ---------------------------------------------------------------------------

@app.get("/status")
def get_status(_: str = Depends(_verify)):
    jarvis_running  = _jarvis_instance is not None and _jarvis_instance.session is not None
    aria_connected  = (
        _output_adapter is not None
        and len(_output_adapter._clients) > 0
    )
    return {"jarvis_running": jarvis_running, "aria_connected": aria_connected}
