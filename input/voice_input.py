"""One-shot macOS voice capture for the JARVIS CLI."""

from __future__ import annotations

import math
import os
import signal
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


class VoiceInputError(RuntimeError):
    """Raised when one-shot voice capture or transcription fails."""

    def __init__(self, code: str, message: str, hint: str | None = None) -> None:
        self.code = code
        self.hint = hint
        super().__init__(message)


_HELPER_SOURCE = Path(__file__).with_name("macos_voice_capture.m")
_HELPER_INFO_PLIST = Path(__file__).with_name("macos_voice_capture_info.plist")
_HELPER_BINARY = Path("/tmp/jarvis_macos_voice_capture")
_HELPER_APP_BUNDLE = Path("/tmp/JARVISVoiceCapture.app")
_HELPER_APP_CONTENTS = _HELPER_APP_BUNDLE / "Contents"
_HELPER_APP_BINARY = _HELPER_APP_CONTENTS / "MacOS" / "jarvis_macos_voice_capture"
_HELPER_APP_INFO_PLIST = _HELPER_APP_CONTENTS / "Info.plist"
_DEFAULT_TIMEOUT_SECONDS = 8.0
_PRIVACY_HINT = "Check macOS Settings -> Privacy & Security -> Microphone / Speech Recognition."
_VOICE_CRASH_HINT = "Try again. If it keeps failing, check macOS Settings -> Privacy & Security -> Microphone / Speech Recognition."
_VOICE_EMPTY_HINT = "Speak right after 'voice: listening...' and verify the active input device in macOS Sound settings."


def capture_voice_input(timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS) -> str:
    """Capture one spoken utterance on macOS and return recognized text."""
    if sys.platform != "darwin":
        raise VoiceInputError("UNSUPPORTED_PLATFORM", "Voice input is available only on macOS.")

    _ensure_helper_binary()

    effective_timeout = max(2.0, float(timeout_seconds))
    result = _run_helper(effective_timeout)
    if result.returncode != 0 and _should_rebuild_after_helper_failure(result):
        _ensure_helper_binary(force_rebuild=True)
        result = _run_helper(effective_timeout)
    if result.returncode != 0 and _should_retry_with_open(result):
        fallback_result = _run_helper_via_open_bundle(effective_timeout)
        if fallback_result is not None and (fallback_result.returncode == 0 or "|" in (fallback_result.stderr or "")):
            result = fallback_result

    if result.returncode != 0:
        raise _voice_error_from_result(result.returncode, result.stderr or result.stdout)

    recognized_text = (result.stdout or "").strip()
    if not recognized_text:
        raise VoiceInputError("EMPTY_RECOGNITION", "No speech was recognized. Try again.")
    return recognized_text


def _ensure_helper_binary(force_rebuild: bool = False) -> None:
    source_mtime = _HELPER_SOURCE.stat().st_mtime
    plist_mtime = _HELPER_INFO_PLIST.stat().st_mtime if _HELPER_INFO_PLIST.exists() else 0.0
    newest_source_mtime = max(source_mtime, plist_mtime)
    if (
        not force_rebuild
        and _HELPER_BINARY.exists()
        and _HELPER_BINARY.stat().st_mtime >= newest_source_mtime
        and os.access(_HELPER_BINARY, os.X_OK)
    ):
        return

    if not _HELPER_INFO_PLIST.exists():
        raise VoiceInputError("VOICE_SETUP_FAILED", "Voice helper privacy plist is missing.")

    _prepare_helper_output_directory()

    compile_command = [
        "clang",
        "-fobjc-arc",
        "-fblocks",
        f"-Wl,-sectcreate,__TEXT,__info_plist,{_HELPER_INFO_PLIST}",
        "-framework",
        "AppKit",
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

    _codesign_helper_binary()
    _prepare_helper_app_bundle()


def _prepare_helper_output_directory() -> None:
    try:
        _HELPER_BINARY.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise VoiceInputError("VOICE_SETUP_FAILED", f"Voice helper output setup failed: {exc}.") from exc


def _codesign_helper_binary() -> None:
    sign_command = [
        "codesign",
        "--force",
        "--sign",
        "-",
        "--identifier",
        "com.jarvis.voice.capture.helper",
        "--timestamp=none",
        str(_HELPER_BINARY),
    ]
    try:
        result = subprocess.run(sign_command, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise VoiceInputError("VOICE_SETUP_FAILED", f"Voice helper codesign failed: {exc}.") from exc

    if result.returncode != 0:
        summary = _first_meaningful_line(result.stderr or result.stdout) or "Voice helper codesign failed."
        raise VoiceInputError("VOICE_SETUP_FAILED", summary)


def _prepare_helper_app_bundle() -> None:
    try:
        (_HELPER_APP_CONTENTS / "MacOS").mkdir(parents=True, exist_ok=True)
        shutil.copy2(_HELPER_BINARY, _HELPER_APP_BINARY)
        shutil.copy2(_HELPER_INFO_PLIST, _HELPER_APP_INFO_PLIST)
        os.chmod(_HELPER_APP_BINARY, 0o755)
    except OSError as exc:
        raise VoiceInputError("VOICE_SETUP_FAILED", f"Voice helper app bundle setup failed: {exc}.") from exc

    sign_command = [
        "codesign",
        "--force",
        "--sign",
        "-",
        "--identifier",
        "com.jarvis.voice.capture.helper",
        "--timestamp=none",
        str(_HELPER_APP_BUNDLE),
    ]
    try:
        result = subprocess.run(sign_command, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise VoiceInputError("VOICE_SETUP_FAILED", f"Voice helper app bundle codesign failed: {exc}.") from exc

    if result.returncode != 0:
        summary = _first_meaningful_line(result.stderr or result.stdout) or "Voice helper app bundle codesign failed."
        raise VoiceInputError("VOICE_SETUP_FAILED", summary)


def _run_helper(timeout_seconds: float) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [str(_HELPER_BINARY), str(timeout_seconds)],
            capture_output=True,
            text=True,
            check=False,
            timeout=int(math.ceil(timeout_seconds)) + 5,
        )
    except subprocess.TimeoutExpired as exc:
        raise VoiceInputError("RECOGNITION_FAILED", "Voice capture timed out. Try again.") from exc
    except OSError as exc:
        raise VoiceInputError("VOICE_SETUP_FAILED", f"Voice helper failed to start: {exc}.") from exc


def _run_helper_via_open_bundle(timeout_seconds: float) -> subprocess.CompletedProcess[str] | None:
    if not _HELPER_APP_BUNDLE.exists() or not _HELPER_APP_BINARY.exists():
        return None

    output_fd, output_path = tempfile.mkstemp(prefix="jarvis_voice_out_", suffix=".txt")
    error_fd, error_path = tempfile.mkstemp(prefix="jarvis_voice_err_", suffix=".txt")
    os.close(output_fd)
    os.close(error_fd)

    try:
        open_result = subprocess.run(
            [
                "open",
                "-W",
                "-n",
                str(_HELPER_APP_BUNDLE),
                "--args",
                str(timeout_seconds),
                output_path,
                error_path,
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=int(math.ceil(timeout_seconds)) + 10,
        )
    except (subprocess.TimeoutExpired, OSError):
        _safe_unlink(output_path)
        _safe_unlink(error_path)
        return None

    output_text = _read_text_file(output_path)
    error_text = _read_text_file(error_path)
    _safe_unlink(output_path)
    _safe_unlink(error_path)

    if output_text.strip():
        return subprocess.CompletedProcess(
            args=open_result.args,
            returncode=0,
            stdout=output_text,
            stderr=error_text,
        )

    if error_text.strip():
        return subprocess.CompletedProcess(
            args=open_result.args,
            returncode=1,
            stdout=output_text,
            stderr=error_text,
        )

    if open_result.returncode != 0:
        return subprocess.CompletedProcess(
            args=open_result.args,
            returncode=open_result.returncode,
            stdout=output_text,
            stderr=open_result.stderr or open_result.stdout,
        )

    return None


def _should_rebuild_after_helper_failure(result: subprocess.CompletedProcess[str]) -> bool:
    if result.returncode < 0:
        return True
    detail = (result.stderr or result.stdout or "").strip()
    if not detail:
        return True
    return "|" not in detail


def _should_retry_with_open(result: subprocess.CompletedProcess[str]) -> bool:
    detail = (result.stderr or result.stdout or "").strip()
    return "VOICE_SETUP_FAILED|Voice helper crashed with SIGABRT." in detail


def _voice_error_from_result(returncode: int, raw_message: str) -> VoiceInputError:
    message = raw_message.strip()
    code = "RECOGNITION_FAILED"
    detail = message
    structured = _extract_structured_error(message)
    if structured is not None:
        code, detail = structured
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
        normalized = detail or "No speech was recognized. Try again."
        return VoiceInputError(code, normalized, hint=_VOICE_EMPTY_HINT)

    if code == "VOICE_SETUP_FAILED":
        return VoiceInputError(code, detail or "Voice helper failed to start.", hint=_PRIVACY_HINT)

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


def _extract_structured_error(message: str) -> tuple[str, str] | None:
    for line in reversed(message.splitlines()):
        if "|" not in line:
            continue
        raw_code, raw_detail = line.split("|", 1)
        code = raw_code.strip()
        if not code or not code.replace("_", "").isalnum() or not code.isupper():
            continue
        return code, raw_detail.strip()
    return None


def _read_text_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""


def _safe_unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        return
