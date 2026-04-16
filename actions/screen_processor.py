"""
actions/screen_processor.py — Fast Vision Module v9
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
v9 Changes (replaces v8 Live-API approach):
  - Gemini 2.0 Flash Lite REST API instead of Live WebSocket → ~0.5–1s vs 5–20s
  - Persistent singleton camera — opens once, reuses across calls
  - Local OCR via pytesseract (optional, ~100ms) with Gemini fallback
  - Local object detection via YOLO nano (optional, ~100ms) with Gemini fallback
  - Returns text → main Gemini session speaks it (no separate audio session)
  - action parameter: "analyze" | "ocr" | "objects"
"""

import io
import json
import sys
import time
import threading
import cv2
import mss
import mss.tools
from pathlib import Path

try:
    import PIL.Image
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

try:
    import pytesseract
    _TESSERACT = True
except ImportError:
    _TESSERACT = False

try:
    from ultralytics import YOLO as _YOLO_CLS
    _YOLO_OK = True
except ImportError:
    _YOLO_OK = False

from google import genai
from google.genai import types

IMG_MAX_W = 640
IMG_MAX_H = 480
JPEG_Q    = 72

VISION_PROMPT = (
    "You are JARVIS from Iron Man. Analyze the image with technical precision. "
    "Be concise — 1 to 3 sentences. Address the user as 'sir'."
)


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


# ─── Singleton Camera ──────────────────────────────────────────────────────────

class _CameraManager:
    """
    Keeps a single cv2.VideoCapture open across calls.
    On module import, opens the camera in a background thread so it's
    warm and ready by the time the user first asks for it.
    Thread-safe via a lock.
    """

    def __init__(self):
        self._cap   = None
        self._lock  = threading.Lock()
        self._index = None
        self.ready  = False

    # ── Index resolution ──────────────────────────────────────────────────────

    def _cfg_index(self) -> int | None:
        try:
            with open(API_CONFIG_PATH, "r") as f:
                cfg = json.load(f)
            return int(cfg["camera_index"]) if "camera_index" in cfg else None
        except Exception:
            return None

    def _detect_index(self) -> int:
        for idx in range(6):
            cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap.release()
                continue
            for _ in range(3):
                cap.read()
            ret, frame = cap.read()
            cap.release()
            if ret and frame is not None and frame.mean() > 5:
                print(f"[Camera] ✅ Auto-detected index {idx}")
                try:
                    cfg = {}
                    if API_CONFIG_PATH.exists():
                        with open(API_CONFIG_PATH, "r") as f:
                            cfg = json.load(f)
                    cfg["camera_index"] = idx
                    with open(API_CONFIG_PATH, "w") as f:
                        json.dump(cfg, f, indent=4)
                except Exception:
                    pass
                return idx
        return 0

    # ── Open / close ──────────────────────────────────────────────────────────

    def _open(self, idx: int):
        self._cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        if self._cap.isOpened():
            # Flush stale frames from the buffer
            for _ in range(5):
                self._cap.read()
            self.ready = True
            print(f"[Camera] ✅ Singleton open (index {idx})")
        else:
            print(f"[Camera] ⚠️ Could not open index {idx}")

    def warmup(self):
        """Open camera in background — call at import time."""
        def _bg():
            idx = self._cfg_index()
            if idx is None:
                idx = self._detect_index()
            self._index = idx
            with self._lock:
                self._open(idx)

        threading.Thread(target=_bg, daemon=True, name="CameraWarmup").start()

    # ── Frame capture ─────────────────────────────────────────────────────────

    def capture_jpeg(self) -> bytes:
        with self._lock:
            # Re-open if camera was closed or never opened
            if self._cap is None or not self._cap.isOpened():
                idx = self._index or self._cfg_index() or self._detect_index()
                self._index = idx
                self._open(idx)

            if not (self._cap and self._cap.isOpened()):
                raise RuntimeError(f"Camera unavailable at index {self._index}")

            ret, frame = self._cap.read()

        if not ret or frame is None:
            raise RuntimeError("Camera returned empty frame.")

        return self._to_jpeg(frame)

    @staticmethod
    def _to_jpeg(frame) -> bytes:
        if _PIL_OK:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = PIL.Image.fromarray(rgb)
            img.thumbnail([IMG_MAX_W, IMG_MAX_H], PIL.Image.BILINEAR)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=JPEG_Q, optimize=False)
            return buf.getvalue()
        _, enc = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_Q])
        return enc.tobytes()


_camera = _CameraManager()
_camera.warmup()  # background warmup on import — camera is ready before user asks


# ─── Screen Capture ────────────────────────────────────────────────────────────

def _capture_screenshot() -> bytes:
    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
        png  = mss.tools.to_png(shot.rgb, shot.size)
    if _PIL_OK:
        img = PIL.Image.open(io.BytesIO(png)).convert("RGB")
        img.thumbnail([IMG_MAX_W, IMG_MAX_H], PIL.Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=JPEG_Q, optimize=False)
        return buf.getvalue()
    return png


# ─── Local OCR (pytesseract) ───────────────────────────────────────────────────

def _local_ocr(image_bytes: bytes) -> str | None:
    """Extract text locally via Tesseract. Returns None if unavailable."""
    if not _TESSERACT or not _PIL_OK:
        return None
    try:
        img  = PIL.Image.open(io.BytesIO(image_bytes))
        text = pytesseract.image_to_string(img, config="--psm 6").strip()
        return text or None
    except Exception as e:
        print(f"[Camera] Tesseract error: {e}")
        return None


# ─── Local Object Detection (YOLO nano) ────────────────────────────────────────

_yolo_model     = None
_yolo_load_lock = threading.Lock()


def _get_yolo():
    global _yolo_model
    if not _YOLO_OK:
        return None
    with _yolo_load_lock:
        if _yolo_model is None:
            try:
                _yolo_model = _YOLO_CLS("yolov8n.pt")
                print("[Camera] ✅ YOLOv8 nano loaded")
            except Exception as e:
                print(f"[Camera] YOLO load failed: {e}")
    return _yolo_model


def _local_detect(image_bytes: bytes) -> str | None:
    """Detect objects locally via YOLOv8 nano. Returns None if unavailable."""
    model = _get_yolo()
    if model is None:
        return None
    try:
        import numpy as np
        buf     = np.frombuffer(image_bytes, dtype=np.uint8)
        frame   = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        results = model(frame, verbose=False)[0]
        names   = results.names
        counts: dict[str, int] = {}
        for cls_id in results.boxes.cls.tolist():
            label = names[int(cls_id)]
            counts[label] = counts.get(label, 0) + 1
        if not counts:
            return "No objects detected."
        parts = [f"{v}× {k}" if v > 1 else k for k, v in counts.items()]
        return "Detected: " + ", ".join(parts) + "."
    except Exception as e:
        print(f"[Camera] YOLO detect error: {e}")
        return None


# ─── Gemini REST Analysis ──────────────────────────────────────────────────────

def _gemini_analyze(image_bytes: bytes, question: str) -> str:
    """
    Analyze image via Gemini 2.0 Flash Lite REST API.
    Typical latency: 0.4–1.5s (vs 5–20s for Live API).
    """
    client = genai.Client(api_key=_get_api_key())
    full_q = f"{VISION_PROMPT}\n\nUser: {question}"
    resp   = client.models.generate_content(
        model="gemini-2.0-flash-lite",
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
            full_q,
        ],
    )
    return resp.text.strip()


# ─── Public Entry Point ────────────────────────────────────────────────────────

def screen_process(
    parameters:     dict,
    response:       str | None = None,
    player=None,
    session_memory=None,
    speak=None,
) -> str:
    """
    Captures image and analyzes it. Returns text for main session to speak.

    parameters:
        text   : User question / instruction (required)
        angle  : "camera" (default) | "screen"
        action : "analyze" (default) | "ocr" | "objects"

    Routing:
        ocr     → pytesseract locally, then Gemini REST fallback
        objects → YOLOv8 nano locally, then Gemini REST fallback
        analyze → Gemini REST directly
    """
    params    = parameters or {}
    user_text = (params.get("text") or params.get("user_text") or "").strip()
    angle     = params.get("angle", "camera").lower().strip()
    action    = params.get("action", "analyze").lower().strip()

    if not user_text:
        user_text = "What do you see? Describe briefly."

    print(f"[Camera] angle={angle!r}  action={action!r}  q={user_text!r}")

    if player:
        player.write_log("[Camera] Capturing...")

    # ── Capture ───────────────────────────────────────────────────────────────
    t0 = time.perf_counter()
    try:
        image_bytes = _camera.capture_jpeg() if angle == "camera" else _capture_screenshot()
        t_cap = time.perf_counter() - t0
        print(f"[Camera] 📷 Captured {len(image_bytes):,} bytes in {t_cap:.3f}s")
    except Exception as e:
        print(f"[Camera] ❌ Capture failed: {e}")
        return f"Camera capture failed, sir: {e}"

    # ── Analyze ───────────────────────────────────────────────────────────────
    t1     = time.perf_counter()
    result = None

    if action == "ocr":
        result = _local_ocr(image_bytes)
        if result:
            print(f"[Camera] OCR via Tesseract in {time.perf_counter()-t1:.3f}s")
        else:
            result = _gemini_analyze(
                image_bytes,
                "Extract ALL text visible in this image exactly as it appears. "
                "Return only the raw text with no explanation or formatting."
            )
            print(f"[Camera] OCR via Gemini in {time.perf_counter()-t1:.3f}s")

    elif action == "objects":
        result = _local_detect(image_bytes)
        if result:
            print(f"[Camera] Detection via YOLO in {time.perf_counter()-t1:.3f}s")
        else:
            result = _gemini_analyze(
                image_bytes,
                "List every distinct object, person, or item you can see. "
                "Return as a brief comma-separated list."
            )
            print(f"[Camera] Detection via Gemini in {time.perf_counter()-t1:.3f}s")

    else:  # analyze (default)
        result = _gemini_analyze(image_bytes, user_text)
        print(f"[Camera] Analysis via Gemini in {time.perf_counter()-t1:.3f}s")

    result = result or "Could not analyze the image, sir."

    total = time.perf_counter() - t0
    print(f"[Camera] ✅ Total: {total:.3f}s | {result[:100]}")

    if player:
        player.write_log(f"[Camera] {result[:60]}")

    if speak:
        speak(result)

    return result


# ─── Legacy warmup stub (backward compat) ─────────────────────────────────────

def warmup_session(player=None):
    """No-op: camera warmup happens at import time now."""
    pass


# ─── Standalone test ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("[TEST] screen_processor.py v9 — fast REST vision")
    print("=" * 50)
    mode   = input("screen / camera (default: camera): ").strip().lower() or "camera"
    action = input("analyze / ocr / objects (default: analyze): ").strip().lower() or "analyze"
    q      = input("Question (Enter for default): ").strip() or "What do you see? Be brief."

    print(f"\nCapturing with angle={mode!r}, action={action!r}...\n")
    t0 = time.perf_counter()
    r  = screen_process({"angle": mode, "action": action, "text": q})
    print(f"\n✅ Done in {time.perf_counter()-t0:.2f}s")
    print(f"Result:\n{r}")
