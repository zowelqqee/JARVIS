"""
Stub native/platform-specific modules so tests run on macOS without a full
V.E.C.T.O.R. install (the real app targets Windows).
"""
import sys
from unittest.mock import MagicMock

_STUBS = [
    "pyaudio",
    "ui",
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
