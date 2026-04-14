"""
Entry point for the panel-first JARVIS desktop.

Run with the desktop venv:
  .venv-desktop-packaging/bin/python -m desktop.main
  or
  .venv-desktop-packaging/bin/python desktop/main.py

The backend (JarvisLive from root main.py) runs in a daemon thread.
The PySide6 event loop runs on the main thread.
Communication between threads goes through PanelBridge (QTimer-drained queue).
"""
from __future__ import annotations

import asyncio
import sys
import threading
from pathlib import Path

# Ensure repo root is on sys.path so root main.py is importable
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from desktop.app.application  import build_application
from desktop.backend.panel_bridge import PanelBridge
from desktop.shell.main_window import MainWindow


def main() -> int:
    app = build_application(sys.argv)

    bridge = PanelBridge()
    window = MainWindow(bridge)
    window.show()

    # ── Try to load the backend ──────────────────────────────────────── #
    JarvisLive = _load_backend()

    if JarvisLive is not None:
        jarvis = JarvisLive(bridge)
        bridge._jarvis_ref = jarvis

        def _runner() -> None:
            bridge.set_connecting()
            bridge.wait_for_api_key()
            try:
                asyncio.run(jarvis.run())
            except KeyboardInterrupt:
                pass
            except Exception as exc:
                bridge.set_failed(f"Backend error: {exc}")

        threading.Thread(target=_runner, daemon=True).start()
    else:
        # Demo mode — panel is functional but backend is unavailable
        bridge.write_log("JARVIS panel started in demo mode.")

    return app.exec()


def _load_backend():
    """
    Import JarvisLive from root main.py.
    Returns None if backend dependencies are unavailable (e.g., on macOS
    where some Windows-only packages may not be installed).
    """
    try:
        import importlib
        mod = importlib.import_module("main")
        return mod.JarvisLive
    except Exception as exc:
        print(f"[JARVIS Panel] Backend unavailable: {exc}")
        return None


if __name__ == "__main__":
    sys.exit(main())
