"""One-shot macOS voice capture for the JARVIS CLI."""

from __future__ import annotations

import math
import os
import signal
import subprocess
import sys
from pathlib import Path


class VoiceInputError(RuntimeError):
    """Raised when one-shot voice capture or transcription fails."""

    def __init__(self, code: str, message: str, hint: str | None = None) -> None:
        self.code = code
        self.hint = hint
        super().__init__(message)


_HELPER_SOURCE = Path(__file__).with_name("macos_voice_capture.m")
_HELPER_BINARY = Path("/tmp/jarvis_macos_voice_capture")
_DEFAULT_TIMEOUT_SECONDS = 8.0
_PRIVACY_HINT = "Check macOS Settings -> Privacy & Security -> Microphone / Speech Recognition."
_VOICE_CRASH_HINT = "Try again. If it keeps failing, check macOS Settings -> Privacy & Security -> Microphone / Speech Recognition."


def capture_voice_input(timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS) -> str:
    """Capture one spoken utterance on macOS and return recognized text."""
    if sys.platform != "darwin":
        raise VoiceInputError("UNSUPPORTED_PLATFORM", "Voice input is available only on macOS.")

    _ensure_helper_binary()

    effective_timeout = max(2.0, float(timeout_seconds))
    try:
        result = subprocess.run(
            [str(_HELPER_BINARY), str(effective_timeout)],
            capture_output=True,
            text=True,
            check=False,
            timeout=int(math.ceil(effective_timeout)) + 5,
        )
    except subprocess.TimeoutExpired as exc:
        raise VoiceInputError("RECOGNITION_FAILED", "Voice capture timed out. Try again.") from exc
    except OSError as exc:
        raise VoiceInputError("VOICE_SETUP_FAILED", f"Voice helper failed to start: {exc}.") from exc

    if result.returncode != 0:
        raise _voice_error_from_result(result.returncode, result.stderr or result.stdout)

    recognized_text = (result.stdout or "").strip()
    if not recognized_text:
        raise VoiceInputError("EMPTY_RECOGNITION", "No speech was recognized. Try again.")
    return recognized_text


def _ensure_helper_binary() -> None:
    source_mtime = _HELPER_SOURCE.stat().st_mtime
    if _HELPER_BINARY.exists() and _HELPER_BINARY.stat().st_mtime >= source_mtime and os.access(_HELPER_BINARY, os.X_OK):
        return

    compile_command = [
        "clang",
        "-fobjc-arc",
        "-fblocks",
        "-framework",
        "Foundation",
        "-framework",
        "Speech",
        "-framework",
        "AVFoundation",
        str(_HELPER_SOURCE),
        "-o",
        str(_HELPER_BINARY),
    ]

    try:
        result = subprocess.run(compile_command, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise VoiceInputError("VOICE_SETUP_FAILED", f"Voice helper compile failed: {exc}.") from exc

    if result.returncode != 0:
        summary = _first_meaningful_line(result.stderr or result.stdout) or "Voice helper compile failed."
        raise VoiceInputError("VOICE_SETUP_FAILED", summary)


def _voice_error_from_result(returncode: int, raw_message: str) -> VoiceInputError:
    message = raw_message.strip()
    code = "RECOGNITION_FAILED"
    detail = message
    if "|" in message:
        code, detail = message.split("|", 1)
        code = code.strip() or "RECOGNITION_FAILED"
        detail = detail.strip()
    else:
        detail = _first_meaningful_line(message)

    if returncode < 0 and code == "RECOGNITION_FAILED":
        return _voice_helper_crash_error(returncode, detail)

    if code == "PERMISSION_DENIED":
        normalized = detail or "Speech recognition permission was denied."
        return VoiceInputError(code, normalized, hint=_PRIVACY_HINT)

    if code == "MICROPHONE_UNAVAILABLE":
        normalized = detail or "Microphone access is unavailable."
        return VoiceInputError(code, normalized, hint=_PRIVACY_HINT)

    if code == "EMPTY_RECOGNITION":
        return VoiceInputError(code, "No speech was recognized. Try again.")

    if code == "VOICE_SETUP_FAILED":
        return VoiceInputError(code, detail or "Voice helper failed to start.")

    if code == "UNSUPPORTED_PLATFORM":
        return VoiceInputError(code, detail or "Voice input is available only on macOS.")

    if detail:
        return VoiceInputError(code, detail)

    return VoiceInputError(
        "RECOGNITION_FAILED",
        f"Voice helper failed unexpectedly with exit code {returncode}.",
    )


def _voice_helper_crash_error(returncode: int, detail: str) -> VoiceInputError:
    signal_number = abs(int(returncode))
    signal_name = _signal_name(signal_number)
    if signal_name:
        message = f"Voice helper crashed with {signal_name}. Try again."
    else:
        message = f"Voice helper crashed with signal {signal_number}. Try again."

    normalized_detail = detail.strip()
    if normalized_detail and "abort trap" not in normalized_detail.lower():
        message = f"{message} {normalized_detail}"

    return VoiceInputError("VOICE_HELPER_CRASH", message, hint=_VOICE_CRASH_HINT)


def _signal_name(signal_number: int) -> str | None:
    try:
        return signal.Signals(signal_number).name
    except ValueError:
        return None


def _first_meaningful_line(text: str) -> str:
    for line in text.splitlines():
        candidate = " ".join(line.strip().split())
        if candidate:
            return candidate[:240]
    return ""
