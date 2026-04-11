"""Desktop application entry point for JARVIS."""

from __future__ import annotations

import sys


def main() -> int:
    """Launch the desktop shell."""
    try:
        from desktop.app.application import run_desktop_application
    except ImportError as exc:
        if getattr(exc, "name", "") == "PySide6":
            raise SystemExit(
                "PySide6 is required to run the JARVIS desktop app. "
                "Install PySide6 in the active Python environment and try again."
            ) from exc
        raise
    return run_desktop_application(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
