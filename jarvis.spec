# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for JARVIS — onedir, no console, Windows 10/11 x64
# Build:  python -m pyinstaller jarvis.spec --clean

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# ── Optional: generate face.ico from face.png ─────────────────────────────
_icon = None
try:
    from PIL import Image as _PILImage
    _img = _PILImage.open("face.png").convert("RGBA")
    _ico_path = Path("face.ico")
    _img.save(
        str(_ico_path), format="ICO",
        sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)],
    )
    _icon = str(_ico_path)
    print(f"[spec] face.ico generated → {_ico_path.resolve()}")
except Exception as _e:
    print(f"[spec] WARNING: Could not create .ico from face.png ({_e!r}). Building without custom icon.")

# ── Data files (bundled into the dist/JARVIS/ directory) ──────────────────
_datas = [
    ("face.png",        "."),       # → dist/JARVIS/face.png
    ("core/prompt.txt", "core"),    # → dist/JARVIS/core/prompt.txt
]

# YOLO model weights (optional, used by ARIA vision)
for _pt in ("yolov8n.pt", "yolov8l.pt"):
    if Path(_pt).exists():
        _datas.append((_pt, "."))

# OpenCV haarcascade XML files (needed for cv2.data.haarcascades)
try:
    _datas += collect_data_files("cv2")
except Exception as _e:
    print(f"[spec] WARNING: collect_data_files('cv2') failed ({_e!r}). Haarcascades may be missing.")

# ── Hidden imports ─────────────────────────────────────────────────────────
_hidden = [
    # PyQt6
    "PyQt6", "PyQt6.QtCore", "PyQt6.QtGui", "PyQt6.QtWidgets",
    "PyQt6.QtNetwork", "PyQt6.sip",
    # audio
    "sounddevice", "soundfile", "cffi", "_cffi_backend",
    # system monitoring
    "psutil",
    # imaging
    "PIL", "PIL.Image", "PIL.ImageDraw", "PIL.ImageFilter",
    "PIL.ImageOps", "PIL.ImageEnhance",
    # numerics
    "numpy",
    # networking / HTTP
    "requests", "requests.adapters", "requests.packages",
    "urllib3", "certifi", "charset_normalizer", "idna",
    "httpx", "httpcore",
    # browser automation (Playwright; browsers installed separately)
    "playwright", "playwright.sync_api", "playwright.async_api",
    # input / desktop control
    "pyautogui", "pyperclip", "pygetwindow",
    # screen capture
    "mss", "mss.tools",
    # ML utilities
    "sklearn", "sklearn.ensemble", "sklearn.preprocessing",
    "joblib",
    # office formats
    "pptx",
    # YouTube
    "youtube_transcript_api",
    # HTML parsing
    "bs4", "lxml",
    # Windows-only (silently absent on other platforms at runtime)
    "win10toast", "pycaw", "pycaw.pycaw",
    "comtypes", "comtypes.client", "comtypes.automation",
    "pywinauto", "pywinauto.application",
    # asyncio
    "asyncio", "asyncio.queues", "asyncio.tasks", "asyncio.events",
    # project root modules
    "config",
    "_meipass_helper",
    "assistant_identity",
    "audio_gate",
    "tool_response",
    # actions package
    "actions",
    "actions.app_control",
    "actions.aria_vision",
    "actions.browser_control",
    "actions.code_helper",
    "actions.computer_control",
    "actions.computer_settings",
    "actions.desktop",
    "actions.dev_agent",
    "actions.file_controller",
    "actions.file_processor",
    "actions.flight_finder",
    "actions.game_updater",
    "actions.open_app",
    "actions.reminder",
    "actions.screen_processor",
    "actions.send_message",
    "actions.weather_report",
    "actions.web_search",
    "actions.youtube_video",
    # agent package
    "agent",
    "agent.error_handler",
    "agent.executor",
    "agent.planner",
    "agent.task_queue",
    # memory package
    "memory",
    "memory.config_manager",
    "memory.memory_manager",
    # core package
    "core",
    "core.interrupts",
    # aria package (vision only — standalone scripts excluded below)
    "aria",
    "aria.vision",
]

# google-genai and its dependencies — collect all sub-packages
for _pkg in ("google.genai", "google.api_core", "google.auth", "google.protobuf"):
    try:
        _hidden += collect_submodules(_pkg)
    except Exception as _e:
        print(f"[spec] WARNING: collect_submodules({_pkg!r}) failed ({_e!r}).")
        _hidden.append(_pkg)

# Optional heavy deps (cv2, ultralytics, face_recognition) — ok if absent
for _pkg in ("cv2", "ultralytics", "face_recognition"):
    try:
        _hidden += collect_submodules(_pkg)
    except Exception:
        _hidden.append(_pkg)

# ── Analysis ───────────────────────────────────────────────────────────────
a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=_datas,
    hiddenimports=_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # test / dev artifacts
        "tests",
        "mlruns",
        "intent_classifier",
        "__pycache__",
        ".ipynb_checkpoints",
        # standalone ARIA scripts — NOT importable modules, excluded explicitly
        # (they contain module-level while-True loops and must never be imported)
        "aria.face_detect",
        "aria.face_id",
        "aria.object_detect",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,          # onedir: binaries collected separately by COLLECT
    name="JARVIS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                      # UPX disabled — avoids antivirus false positives
    console=False,                  # no terminal window on Windows
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="JARVIS",
)
