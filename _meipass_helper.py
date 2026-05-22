import sys
from pathlib import Path


def resource_path(relative: str) -> Path:
    """Resolve a bundled asset path.

    PyInstaller (onedir): sys._MEIPASS == dist/JARVIS/ == Path(sys.executable).parent
    Dev mode:            __file__ is in the project root, so parent is also the root.
    """
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative
