"""
Stub native/platform-specific modules so tests run on macOS without a full
V.E.C.T.O.R. install (the real app targets Windows).
"""
import sys
import types
from unittest.mock import MagicMock


class _FakeVideoCapture:
    def __init__(self, *args, **kwargs):
        pass

    def isOpened(self):
        return False

    def read(self):
        return False, None

    def release(self):
        return None


if "cv2" not in sys.modules:
    _cv2 = types.ModuleType("cv2")
    _cv2.CAP_DSHOW = 0
    _cv2.VideoCapture = _FakeVideoCapture
    sys.modules["cv2"] = _cv2

_STUBS = [
    "pyaudio",
    "pyautogui",
    "ui",
    "google",
    "google.genai",
    "google.genai.types",
    "send2trash",
    "mss",
    "mss.tools",
    "pytesseract",
    "ultralytics",
    "comtypes",
    "comtypes.client",
    "win32api",
    "win32con",
    "win32gui",
    "pywintypes",
    "winreg",
    "pycaw",
    "pycaw.pycaw",
]

for _mod in _STUBS:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()
