"""Shared operator-facing hints for local TTS backend diagnostics."""

from __future__ import annotations

import shlex

NATIVE_TTS_DOCTOR_COMMAND = "printf 'voice tts doctor\\nquit\\n' | python3 cli.py"
NATIVE_TTS_TYPECHECK_COMMAND = "xcrun swiftc -typecheck voice/native_hosts/macos_tts_host.swift"
NATIVE_TTS_DEVELOPER_DIR_COMMAND = "xcode-select -p"
NATIVE_TTS_CLI_COMMAND = "python3 cli.py"

_TYPECHECK_ERROR_CODES = {
    "HOST_TOOLCHAIN_MISSING",
    "HOST_SDK_MISMATCH",
    "HOST_SWIFT_BRIDGING_CONFLICT",
    "HOST_COMPILE_FAILED",
}


def native_tts_follow_up_command(error_code: str | None, *, detail_lines: tuple[str, ...] = ()) -> str:
    """Return the most useful follow-up command for one native backend failure."""
    code = str(error_code or "").strip()
    developer_dir_override = _developer_dir_override(detail_lines)
    if code in _TYPECHECK_ERROR_CODES:
        return _typecheck_command(developer_dir_override)
    return _doctor_command(developer_dir_override)


def native_tts_cli_smoke_command(*, developer_dir_override: str | None = None) -> str:
    """Return one CLI smoke command for the current native context."""
    if not developer_dir_override:
        return NATIVE_TTS_CLI_COMMAND
    quoted_override = shlex.quote(developer_dir_override)
    return f"env DEVELOPER_DIR={quoted_override} {NATIVE_TTS_CLI_COMMAND}"


def native_tts_doctor_guidance(error_code: str | None, *, detail_lines: tuple[str, ...] = ()) -> tuple[str, ...]:
    """Return operator-facing guidance lines for one native backend failure."""
    code = str(error_code or "").strip()
    hints: list[str] = []
    if code == "HOST_MISSING":
        hints.append(
            "native macOS host file is missing; verify `voice/native_hosts/macos_tts_host.swift` before retrying native smoke."
        )
    elif code == "HOST_TOOLCHAIN_MISSING":
        hints.append(
            "native macOS host could not find a working Swift toolchain; check `xcrun`, `swift`, and the selected Command Line Tools."
        )
    elif code == "HOST_SDK_MISMATCH":
        hints.extend(
            (
                f"native macOS host hit a Swift compiler/SDK mismatch; align Xcode and Command Line Tools, then rerun `{NATIVE_TTS_TYPECHECK_COMMAND}`.",
                f"confirm the active developer dir with `{NATIVE_TTS_DEVELOPER_DIR_COMMAND}`.",
                "make the selected developer dir match the Xcode or Command Line Tools bundle behind the `sdk toolchain`, `active compiler`, `active developer dir`, and `active swiftc` detail lines above before retrying native smoke.",
            )
        )
    elif code == "HOST_SWIFT_BRIDGING_CONFLICT":
        hints.append(
            f"native macOS host hit a SwiftBridging module conflict; inspect local toolchain overlays and rerun `{NATIVE_TTS_TYPECHECK_COMMAND}`."
        )
    elif code == "HOST_COMPILE_FAILED":
        hints.append(
            f"native macOS host failed to compile or start cleanly; inspect the reported first error and rerun `{NATIVE_TTS_TYPECHECK_COMMAND}`."
        )
    elif code in {"HOST_TIMEOUT", "HOST_PING_FAILED", "HOST_UNAVAILABLE"}:
        hints.extend(
            (
                "native macOS host could not start cleanly; check local `xcrun`/`swift` toolchain and Command Line Tools.",
                f"confirm the active developer dir with `{NATIVE_TTS_DEVELOPER_DIR_COMMAND}`.",
            )
        )
    elif code == "UNSUPPORTED_PLATFORM":
        hints.append(
            "native macOS backend is darwin-only; keep the legacy backend on other platforms."
        )
    override_guidance = _developer_dir_override_guidance(detail_lines)
    if override_guidance:
        hints.extend(override_guidance)
    return tuple(hints)


def native_tts_next_step_details(error_code: str | None, *, detail_lines: tuple[str, ...] = ()) -> tuple[str, ...]:
    """Return compact readiness/gate detail lines for one native blocker."""
    code = str(error_code or "").strip()
    details: list[str] = []
    if code == "HOST_SDK_MISMATCH":
        details.extend(
            (
                f"confirm active developer dir with: {NATIVE_TTS_DEVELOPER_DIR_COMMAND}",
                "make the selected developer dir match the Xcode or Command Line Tools bundle behind the sdk toolchain, active compiler, active developer dir, and active swiftc details above, then rerun the native typecheck",
            )
        )
    elif code == "HOST_TIMEOUT":
        details.extend(
            (
                f"confirm active developer dir with: {NATIVE_TTS_DEVELOPER_DIR_COMMAND}",
                "if the native host keeps timing out, compare the active developer dir and active swiftc details above, then rerun the native doctor helper before retrying smoke",
            )
        )
    override_detail = _developer_dir_override_next_step_detail(detail_lines)
    if override_detail:
        details.append(override_detail)
    return tuple(details)


def _developer_dir_override(detail_lines: tuple[str, ...]) -> str | None:
    prefix = "developer dir override: "
    for line in detail_lines:
        candidate = str(line or "").strip()
        if candidate.startswith(prefix):
            value = candidate[len(prefix) :].strip()
            return value or None
    return None


def _developer_dir_override_guidance(detail_lines: tuple[str, ...]) -> tuple[str, ...]:
    developer_dir_override = _developer_dir_override(detail_lines)
    if not developer_dir_override:
        return ()
    return (
        f"current native diagnostics are running with `DEVELOPER_DIR={developer_dir_override}`; if that override is intentional, keep using it on the next typecheck and CLI smoke, otherwise fix or unset it before retrying.",
    )


def _developer_dir_override_next_step_detail(detail_lines: tuple[str, ...]) -> str | None:
    developer_dir_override = _developer_dir_override(detail_lines)
    if not developer_dir_override:
        return None
    return (
        f"current env override: DEVELOPER_DIR={developer_dir_override}; if that override is intentional, keep using it on the next typecheck and CLI smoke, otherwise fix or unset it before retrying"
    )


def _doctor_command(developer_dir_override: str | None) -> str:
    if not developer_dir_override:
        return NATIVE_TTS_DOCTOR_COMMAND
    quoted_override = shlex.quote(developer_dir_override)
    return (
        "printf 'voice tts doctor\\nquit\\n' | "
        f"env DEVELOPER_DIR={quoted_override} {NATIVE_TTS_CLI_COMMAND}"
    )


def _typecheck_command(developer_dir_override: str | None) -> str:
    if not developer_dir_override:
        return NATIVE_TTS_TYPECHECK_COMMAND
    quoted_override = shlex.quote(developer_dir_override)
    return f"env DEVELOPER_DIR={quoted_override} {NATIVE_TTS_TYPECHECK_COMMAND}"
