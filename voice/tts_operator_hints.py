"""Shared operator-facing hints for local TTS backend diagnostics."""

from __future__ import annotations

NATIVE_TTS_DOCTOR_COMMAND = "printf 'voice tts doctor\\nquit\\n' | env JARVIS_TTS_MACOS_NATIVE=1 python3 cli.py"
NATIVE_TTS_TYPECHECK_COMMAND = "xcrun swiftc -typecheck voice/native_hosts/macos_tts_host.swift"
NATIVE_TTS_DEVELOPER_DIR_COMMAND = "xcode-select -p"

_TYPECHECK_ERROR_CODES = {
    "HOST_TOOLCHAIN_MISSING",
    "HOST_SDK_MISMATCH",
    "HOST_SWIFT_BRIDGING_CONFLICT",
    "HOST_COMPILE_FAILED",
}


def native_tts_follow_up_command(error_code: str | None) -> str:
    """Return the most useful follow-up command for one native backend failure."""
    code = str(error_code or "").strip()
    if code in _TYPECHECK_ERROR_CODES:
        return NATIVE_TTS_TYPECHECK_COMMAND
    return NATIVE_TTS_DOCTOR_COMMAND


def native_tts_doctor_guidance(error_code: str | None) -> tuple[str, ...]:
    """Return operator-facing guidance lines for one native backend failure."""
    code = str(error_code or "").strip()
    if code == "HOST_MISSING":
        return (
            "native macOS host file is missing; verify `voice/native_hosts/macos_tts_host.swift` before enabling `JARVIS_TTS_MACOS_NATIVE=1`.",
        )
    if code == "HOST_TOOLCHAIN_MISSING":
        return (
            "native macOS host could not find a working Swift toolchain; check `xcrun`, `swift`, and the selected Command Line Tools.",
        )
    if code == "HOST_SDK_MISMATCH":
        return (
            f"native macOS host hit a Swift compiler/SDK mismatch; align Xcode and Command Line Tools, then rerun `{NATIVE_TTS_TYPECHECK_COMMAND}`.",
            f"confirm the active developer dir with `{NATIVE_TTS_DEVELOPER_DIR_COMMAND}`.",
            "make the selected developer dir match the Xcode or Command Line Tools bundle behind the `sdk toolchain` and `active compiler` detail lines above before retrying native smoke.",
        )
    if code == "HOST_SWIFT_BRIDGING_CONFLICT":
        return (
            f"native macOS host hit a SwiftBridging module conflict; inspect local toolchain overlays and rerun `{NATIVE_TTS_TYPECHECK_COMMAND}`.",
        )
    if code == "HOST_COMPILE_FAILED":
        return (
            f"native macOS host failed to compile or start cleanly; inspect the reported first error and rerun `{NATIVE_TTS_TYPECHECK_COMMAND}`.",
        )
    if code in {"HOST_TIMEOUT", "HOST_PING_FAILED", "HOST_UNAVAILABLE"}:
        return (
            "native macOS host could not start cleanly; check local `xcrun`/`swift` toolchain and Command Line Tools.",
        )
    if code == "UNSUPPORTED_PLATFORM":
        return (
            "native macOS backend is darwin-only; keep the legacy backend on other platforms.",
        )
    return ()


def native_tts_next_step_details(error_code: str | None) -> tuple[str, ...]:
    """Return compact readiness/gate detail lines for one native blocker."""
    code = str(error_code or "").strip()
    if code == "HOST_SDK_MISMATCH":
        return (
            f"confirm active developer dir with: {NATIVE_TTS_DEVELOPER_DIR_COMMAND}",
            "make the selected developer dir match the Xcode or Command Line Tools bundle behind the sdk toolchain detail above, then rerun the native typecheck",
        )
    return ()
