"""Experimental native macOS TTS backend backed by a Swift host process."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from threading import Lock

from voice.tts_models import BackendCapabilities, VoiceDescriptor
from voice.tts_provider import SpeechUtterance, TTSResult

_BACKEND_NAME = "macos_native"
_HOST_SOURCE_PATH = Path(__file__).resolve().parents[1] / "native_hosts" / "macos_tts_host.swift"
_HOST_PING_TIMEOUT_SECONDS = 15.0
_HOST_METADATA_TIMEOUT_SECONDS = 15.0
_HOST_TYPECHECK_TIMEOUT_SECONDS = 3.0
_HOST_DEVELOPER_DIR_TIMEOUT_SECONDS = 1.0
_HOST_SWIFTC_PATH_TIMEOUT_SECONDS = 1.0
_HOST_MODULE_CACHE_PATH = Path(tempfile.gettempdir()) / "jarvis_swift_module_cache"
_PREFERRED_DEVELOPER_DIR = Path("/Applications/Xcode.app/Contents/Developer")
_DEFAULT_RATE_BY_LANGUAGE = {
    "en": 190,
    "ru": 184,
}
_RATE_ENV_BY_LANGUAGE = {
    "en": "JARVIS_TTS_EN_RATE",
    "ru": "JARVIS_TTS_RU_RATE",
}
_GLOBAL_RATE_ENV = "JARVIS_TTS_RATE"
_NATIVE_BASELINE_RATE = 180.0


class MacOSNativeTTSBackend:
    """Talk to the experimental native macOS Swift host over stdin/stdout."""

    def __init__(
        self,
        *,
        host_path: Path | None = None,
        host_command: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        self._lock = Lock()
        self._current_process: subprocess.Popen[str] | None = None
        self._availability: bool | None = None
        self._availability_error_code: str | None = None
        self._availability_error_message: str | None = None
        self._availability_detail_lines: tuple[str, ...] = ()
        self._host_path = Path(host_path) if host_path is not None else _HOST_SOURCE_PATH
        self._has_explicit_host_command = host_command is not None
        self._host_command = tuple(str(part) for part in (host_command or _default_host_command(self._host_path)))

    def speak(self, utterance: SpeechUtterance | None) -> TTSResult:
        """Speak one prepared utterance through the native Swift host."""
        message = str(getattr(utterance, "text", "") or "").strip()
        if not message:
            return TTSResult(ok=True, attempted=False, backend_name=_BACKEND_NAME)
        if sys.platform != "darwin":
            return TTSResult(
                ok=False,
                error_code="UNSUPPORTED_PLATFORM",
                error_message="Native macOS text-to-speech is available only on macOS.",
                backend_name=_BACKEND_NAME,
            )
        if not self._host_is_configured():
            return TTSResult(
                ok=False,
                error_code="TTS_UNAVAILABLE",
                error_message=f"Native macOS TTS host not found at {self._host_path}.",
                backend_name=_BACKEND_NAME,
            )

        payload = _speak_payload(utterance)
        self._ensure_host_module_cache_path()
        host_environment = self._host_environment()
        try:
            popen_kwargs: dict[str, object] = {
                "stdin": subprocess.PIPE,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "text": True,
            }
            if host_environment is not None:
                popen_kwargs["env"] = host_environment
            process = subprocess.Popen(
                list(self._host_command),
                **popen_kwargs,
            )
        except OSError as exc:
            return TTSResult(
                ok=False,
                error_code="TTS_UNAVAILABLE",
                error_message=str(exc),
                backend_name=_BACKEND_NAME,
            )
        self._set_current_process(process)
        try:
            stdout, stderr = process.communicate(_json_payload(payload))
        finally:
            self._clear_current_process(process)

        response = _parse_host_response(stdout)
        if response is not None:
            return _tts_result_from_payload(
                response,
                fallback_voice_id=str(payload.get("voice_id", "") or "").strip() or None,
            )

        detail = _first_meaningful_line(stderr or stdout)
        return TTSResult(
            ok=False,
            error_code="TTS_FAILED",
            error_message=detail or "Native macOS speech synthesis failed.",
            backend_name=_BACKEND_NAME,
            voice_id=str(payload.get("voice_id", "") or "").strip() or None,
        )

    def stop(self) -> bool:
        """Stop the currently running host process when a speech request is active."""
        with self._lock:
            process = self._current_process
        if process is None or process.poll() is not None:
            return False
        try:
            process.terminate()
            try:
                process.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=0.2)
        except OSError:
            return False
        finally:
            self._clear_current_process(process)
        return True

    def list_voices(self, locale_hint: str | None = None) -> list[VoiceDescriptor]:
        """Return native macOS voices visible through the Swift host."""
        response = self._invoke_host(
            {
                "op": "list_voices",
                "locale_hint": str(locale_hint or "").strip() or None,
            },
            timeout_seconds=_HOST_METADATA_TIMEOUT_SECONDS,
        )
        if not response or not bool(response.get("ok", False)):
            return []
        voices = response.get("voices")
        if not isinstance(voices, list):
            return []
        return [voice for voice in (_voice_descriptor_from_payload(item) for item in voices) if voice is not None]

    def resolve_voice(self, profile: str | None, locale: str | None = None) -> VoiceDescriptor | None:
        """Resolve one product profile to a native macOS voice."""
        response = self._invoke_host(
            {
                "op": "resolve_voice",
                "voice_profile": str(profile or "").strip() or None,
                "locale": str(locale or "").strip() or None,
            },
            timeout_seconds=_HOST_METADATA_TIMEOUT_SECONDS,
        )
        if not response or not bool(response.get("ok", False)):
            return None
        return _voice_descriptor_from_payload(response.get("voice"))

    def is_available(self) -> bool:
        """Return whether the native macOS host can be started in the current runtime."""
        if self._availability is None:
            self._availability = self._ping_host()
        return self._availability

    def availability_diagnostic(self) -> tuple[str | None, str | None]:
        """Return the last known availability failure, if any."""
        return self._availability_error_code, self._availability_error_message

    def availability_detail_lines(self) -> tuple[str, ...]:
        """Return operator-facing detail lines for the last availability failure."""
        return self._availability_detail_lines

    def capabilities(self) -> BackendCapabilities:
        """Return capability metadata for the native macOS host backend."""
        return BackendCapabilities(
            backend_name=_BACKEND_NAME,
            supports_stop=True,
            supports_voice_listing=True,
            supports_voice_resolution=True,
            supports_explicit_voice_id=True,
            supports_rate=True,
            supports_volume=True,
            is_fallback=False,
        )

    def _invoke_host(
        self,
        payload: dict[str, object],
        *,
        timeout_seconds: float,
    ) -> dict[str, object] | None:
        if sys.platform != "darwin" or not self._host_is_configured():
            return None
        self._ensure_host_module_cache_path()
        host_environment = self._host_environment()
        try:
            run_kwargs: dict[str, object] = {
                "input": _json_payload(payload),
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "text": True,
                "check": False,
                "timeout": timeout_seconds,
            }
            if host_environment is not None:
                run_kwargs["env"] = host_environment
            result = subprocess.run(
                list(self._host_command),
                **run_kwargs,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        return _parse_host_response(result.stdout)

    def _ping_host(self) -> bool:
        if sys.platform != "darwin":
            self._set_availability_diagnostic(
                "UNSUPPORTED_PLATFORM",
                "Native macOS text-to-speech is available only on macOS.",
            )
            return False
        if not self._host_is_configured():
            self._set_availability_diagnostic(
                "HOST_MISSING",
                f"Native macOS TTS host not found at {self._host_path}.",
            )
            return False
        self._ensure_host_module_cache_path()
        host_environment = self._host_environment()
        try:
            run_kwargs: dict[str, object] = {
                "input": _json_payload({"op": "ping"}),
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "text": True,
                "check": False,
                "timeout": _HOST_PING_TIMEOUT_SECONDS,
            }
            if host_environment is not None:
                run_kwargs["env"] = host_environment
            result = subprocess.run(
                list(self._host_command),
                **run_kwargs,
            )
        except subprocess.TimeoutExpired:
            error_code, error_message = _classify_host_failure(
                default_code="HOST_TIMEOUT",
                default_message="Native macOS TTS host ping timed out.",
            )
            self._set_availability_diagnostic(
                error_code,
                error_message,
                _diagnostic_detail_lines(error_code, environ=host_environment),
            )
            return False
        except OSError as exc:
            error_code, error_message = _classify_host_failure(
                stderr=str(exc),
                default_code="HOST_UNAVAILABLE",
                default_message=str(exc),
            )
            self._set_availability_diagnostic(
                error_code,
                error_message,
                _diagnostic_detail_lines(error_code, stderr=str(exc), environ=host_environment),
            )
            return False

        response = _parse_host_response(result.stdout)
        if response and bool(response.get("ok", False)) and str(response.get("backend_name", "") or "") == _BACKEND_NAME:
            self._set_availability_diagnostic(None, None)
            return True

        error_code = str((response or {}).get("error_code", "") or "").strip() or "HOST_PING_FAILED"
        error_message = str((response or {}).get("error_message", "") or "").strip()
        classified_error_code, classified_error_message = _classify_host_failure(
            stderr=result.stderr,
            stdout=result.stdout,
            default_code=error_code,
            default_message=error_message or "Native macOS TTS host ping failed.",
        )
        refined_error_code, refined_error_message, refined_detail_lines = self._refine_failure_with_typecheck(
            classified_error_code,
            classified_error_message,
            environ=host_environment,
        )
        if not refined_detail_lines:
            refined_detail_lines = _diagnostic_detail_lines(
                refined_error_code or classified_error_code,
                stderr=result.stderr,
                stdout=result.stdout,
                environ=host_environment,
            )
        self._set_availability_diagnostic(
            refined_error_code,
            refined_error_message,
            refined_detail_lines,
        )
        return False

    def _refine_failure_with_typecheck(
        self,
        error_code: str | None,
        error_message: str | None,
        *,
        detail_lines: tuple[str, ...] = (),
        environ: dict[str, str] | None = None,
    ) -> tuple[str | None, str | None, tuple[str, ...]]:
        if not _should_refine_failure_with_typecheck(error_code) or not self._can_typecheck_host_source():
            return error_code, error_message, detail_lines
        host_environment = environ or self._host_environment()
        try:
            _HOST_MODULE_CACHE_PATH.mkdir(parents=True, exist_ok=True)
            run_kwargs: dict[str, object] = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "text": True,
                "check": False,
                "timeout": _HOST_TYPECHECK_TIMEOUT_SECONDS,
            }
            if host_environment is not None:
                run_kwargs["env"] = host_environment
            result = subprocess.run(
                list(_typecheck_command(self._host_path)),
                **run_kwargs,
            )
        except subprocess.TimeoutExpired:
            return error_code, error_message, detail_lines
        except OSError as exc:
            refined_error_code, refined_error_message = _classify_host_failure(
                stderr=str(exc),
                default_code="HOST_UNAVAILABLE",
                default_message=str(exc),
            )
            refined_detail_lines = _diagnostic_detail_lines(
                refined_error_code,
                stderr=str(exc),
                environ=host_environment,
            )
            return (
                refined_error_code or error_code,
                refined_error_message or error_message,
                refined_detail_lines or detail_lines,
            )

        if result.returncode == 0:
            return error_code, error_message, detail_lines

        refined_error_code, refined_error_message = _classify_host_failure(
            stderr=result.stderr,
            stdout=result.stdout,
            default_code="HOST_COMPILE_FAILED",
            default_message=_first_meaningful_line(result.stderr or result.stdout)
            or "Native macOS TTS host failed to compile or start.",
        )
        refined_detail_lines = _diagnostic_detail_lines(
            refined_error_code,
            stderr=result.stderr,
            stdout=result.stdout,
            environ=host_environment,
        )
        if not _should_override_failure(error_code, refined_error_code):
            return error_code, error_message, detail_lines
        return refined_error_code, refined_error_message, refined_detail_lines or detail_lines

    def _can_typecheck_host_source(self) -> bool:
        return (not self._has_explicit_host_command) and self._host_path.exists() and self._host_path.suffix == ".swift"

    def _host_environment(self) -> dict[str, str] | None:
        explicit_developer_dir = str(os.environ.get("DEVELOPER_DIR", "") or "").strip()
        if explicit_developer_dir:
            return dict(os.environ)
        if self._has_explicit_host_command:
            return None
        preferred_developer_dir = _preferred_developer_dir()
        if not preferred_developer_dir:
            return None
        environment = dict(os.environ)
        environment["DEVELOPER_DIR"] = preferred_developer_dir
        return environment

    def _host_is_configured(self) -> bool:
        return self._has_explicit_host_command or self._host_path.exists()

    def _ensure_host_module_cache_path(self) -> None:
        if self._has_explicit_host_command:
            return
        _HOST_MODULE_CACHE_PATH.mkdir(parents=True, exist_ok=True)

    def _set_availability_diagnostic(
        self,
        error_code: str | None,
        error_message: str | None,
        detail_lines: tuple[str, ...] = (),
    ) -> None:
        self._availability_error_code = str(error_code or "").strip() or None
        self._availability_error_message = str(error_message or "").strip() or None
        self._availability_detail_lines = tuple(
            line
            for line in (str(item or "").strip() for item in tuple(detail_lines or ()))
            if line
        )

    def _set_current_process(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            self._current_process = process

    def _clear_current_process(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            if self._current_process is process:
                self._current_process = None


def _speak_payload(utterance: SpeechUtterance | None) -> dict[str, object]:
    current = utterance or SpeechUtterance(text="")
    return {
        "op": "speak",
        "text": str(current.text or ""),
        "locale": str(current.locale or "").strip() or None,
        "voice_profile": str(current.voice_profile or "").strip() or None,
        "voice_id": str(current.voice_id or "").strip() or None,
        "rate": _resolved_native_rate(current.rate, current.locale),
        "pitch": current.pitch,
        "volume": current.volume,
        "style_hint": str(current.style_hint or "").strip() or None,
        "interruptible": bool(current.interruptible),
    }


def _json_payload(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"


def _parse_host_response(stdout: str | None) -> dict[str, object] | None:
    text = str(stdout or "").strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _voice_descriptor_from_payload(payload: object) -> VoiceDescriptor | None:
    if not isinstance(payload, dict):
        return None
    voice_id = str(payload.get("id", "") or "").strip()
    if not voice_id:
        return None
    return VoiceDescriptor(
        id=voice_id,
        display_name=str(payload.get("display_name", "") or voice_id).strip() or voice_id,
        locale=_normalized_locale(payload.get("locale")),
        gender_hint=str(payload.get("gender_hint", "") or "").strip() or None,
        quality_hint=str(payload.get("quality_hint", "") or "").strip() or None,
        source=str(payload.get("source", "") or _BACKEND_NAME).strip() or _BACKEND_NAME,
        is_default=bool(payload.get("is_default", False)),
    )


def _tts_result_from_payload(payload: dict[str, object], *, fallback_voice_id: str | None) -> TTSResult:
    return TTSResult(
        ok=bool(payload.get("ok", False)),
        attempted=bool(payload.get("attempted", True)),
        error_code=str(payload.get("error_code", "") or "").strip() or None,
        error_message=str(payload.get("error_message", "") or "").strip() or None,
        backend_name=str(payload.get("backend_name", "") or _BACKEND_NAME).strip() or _BACKEND_NAME,
        voice_id=str(payload.get("voice_id", "") or fallback_voice_id or "").strip() or fallback_voice_id,
    )


def _normalized_locale(raw_value: object | None) -> str | None:
    locale = str(raw_value or "").strip().replace("_", "-")
    return locale or None


def _first_meaningful_line(text: str | None) -> str:
    for line in str(text or "").splitlines():
        candidate = line.strip()
        if candidate:
            return candidate
    return ""


def _classify_host_failure(
    *,
    stderr: str | None = None,
    stdout: str | None = None,
    default_code: str | None = None,
    default_message: str | None = None,
) -> tuple[str | None, str | None]:
    error_code = str(default_code or "").strip() or "HOST_PING_FAILED"
    first_output_detail = _first_meaningful_line(stderr) or _first_meaningful_line(stdout)
    detail = str(default_message or "").strip() or first_output_detail
    if error_code not in {"HOST_PING_FAILED", "HOST_UNAVAILABLE", "HOST_TIMEOUT", "HOST_COMPILE_FAILED"}:
        return error_code, detail or None
    if error_code == "HOST_TIMEOUT":
        return error_code, detail or "Native macOS TTS host ping timed out."

    haystack = "\n".join(part for part in (str(stderr or ""), str(stdout or ""), detail) if part).lower()
    if _looks_like_toolchain_missing(haystack):
        return (
            "HOST_TOOLCHAIN_MISSING",
            "Native macOS Swift toolchain is unavailable; check `xcrun`, `swift`, and Command Line Tools.",
        )
    if _looks_like_swift_bridging_conflict(haystack):
        return (
            "HOST_SWIFT_BRIDGING_CONFLICT",
            "Native macOS Swift toolchain reported a SwiftBridging module conflict.",
        )
    if _looks_like_sdk_mismatch(haystack):
        return (
            "HOST_SDK_MISMATCH",
            "Native macOS Swift compiler and SDK appear mismatched; align Xcode and Command Line Tools.",
        )
    if _looks_like_compile_failure(haystack):
        compile_detail = first_output_detail or detail
        if compile_detail:
            return (
                "HOST_COMPILE_FAILED",
                f"Native macOS TTS host failed to compile or start. First error: {compile_detail}",
            )
        return "HOST_COMPILE_FAILED", "Native macOS TTS host failed to compile or start."
    return error_code, detail or None


def _typecheck_command(host_path: Path) -> tuple[str, ...]:
    return (
        "xcrun",
        "swiftc",
        "-module-cache-path",
        str(_HOST_MODULE_CACHE_PATH),
        "-typecheck",
        str(host_path),
    )


def _default_host_command(host_path: Path) -> tuple[str, ...]:
    return (
        "xcrun",
        "swift",
        "-module-cache-path",
        str(_HOST_MODULE_CACHE_PATH),
        str(host_path),
    )


def _should_refine_failure_with_typecheck(error_code: str | None) -> bool:
    return str(error_code or "").strip() in {
        "HOST_PING_FAILED",
        "HOST_UNAVAILABLE",
        "HOST_TIMEOUT",
        "HOST_SDK_MISMATCH",
        "HOST_COMPILE_FAILED",
    }


def _should_override_failure(current_code: str | None, refined_code: str | None) -> bool:
    current = str(current_code or "").strip()
    refined = str(refined_code or "").strip()
    if not refined or refined == current:
        return False
    if refined in {"HOST_TOOLCHAIN_MISSING", "HOST_SWIFT_BRIDGING_CONFLICT", "HOST_SDK_MISMATCH"}:
        return True
    if refined == "HOST_COMPILE_FAILED":
        return current in {"HOST_PING_FAILED", "HOST_UNAVAILABLE", "HOST_TIMEOUT", "HOST_COMPILE_FAILED"}
    return False


def _diagnostic_detail_lines(
    error_code: str | None,
    *,
    stderr: str | None = None,
    stdout: str | None = None,
    environ: dict[str, str] | None = None,
) -> tuple[str, ...]:
    code = str(error_code or "").strip()
    haystack = "\n".join(part for part in (str(stderr or ""), str(stdout or "")) if part)
    if code == "HOST_SDK_MISMATCH":
        sdk_toolchain, compiler_toolchain = _extract_sdk_mismatch_versions(haystack)
        lines: list[str] = []
        if sdk_toolchain:
            lines.append(f"sdk toolchain: {sdk_toolchain}")
        if compiler_toolchain:
            lines.append(f"active compiler: {compiler_toolchain}")
        lines.extend(_runtime_toolchain_detail_lines(environ=environ))
        return tuple(lines)
    if code in {"HOST_TIMEOUT", "HOST_PING_FAILED", "HOST_UNAVAILABLE", "HOST_COMPILE_FAILED"}:
        return _runtime_toolchain_detail_lines(environ=environ)
    return ()


def _runtime_toolchain_detail_lines(*, environ: dict[str, str] | None = None) -> tuple[str, ...]:
    lines: list[str] = []
    developer_dir_override = _developer_dir_override_line()
    if developer_dir_override:
        lines.append(developer_dir_override)
    developer_dir = _active_developer_dir_line(environ=environ)
    if developer_dir:
        lines.append(developer_dir)
    swiftc_path = _active_swiftc_path_line(environ=environ)
    if swiftc_path:
        lines.append(swiftc_path)
    return tuple(lines)


def _developer_dir_override_line() -> str | None:
    developer_dir_override = str(os.environ.get("DEVELOPER_DIR", "") or "").strip()
    if not developer_dir_override:
        return None
    return f"developer dir override: {developer_dir_override}"


def _active_developer_dir_line(*, environ: dict[str, str] | None = None) -> str | None:
    try:
        run_kwargs: dict[str, object] = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "check": False,
            "timeout": _HOST_DEVELOPER_DIR_TIMEOUT_SECONDS,
        }
        if environ is not None:
            run_kwargs["env"] = environ
        result = subprocess.run(
            ["xcode-select", "-p"],
            **run_kwargs,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    developer_dir = _first_meaningful_line(result.stdout)
    if not developer_dir:
        return None
    return f"active developer dir: {developer_dir}"


def _active_swiftc_path_line(*, environ: dict[str, str] | None = None) -> str | None:
    try:
        run_kwargs: dict[str, object] = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "check": False,
            "timeout": _HOST_SWIFTC_PATH_TIMEOUT_SECONDS,
        }
        if environ is not None:
            run_kwargs["env"] = environ
        result = subprocess.run(
            ["xcrun", "--find", "swiftc"],
            **run_kwargs,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    swiftc_path = _first_meaningful_line(result.stdout)
    if not swiftc_path:
        return None
    return f"active swiftc: {swiftc_path}"


def _preferred_developer_dir() -> str | None:
    try:
        exists = _PREFERRED_DEVELOPER_DIR.exists()
    except OSError:
        return None
    if not exists:
        return None
    return str(_PREFERRED_DEVELOPER_DIR)


def _resolved_native_rate(explicit_rate: float | None, locale: str | None) -> float | None:
    if explicit_rate is not None:
        return explicit_rate
    legacy_rate = _preferred_legacy_rate_for_locale(locale)
    if legacy_rate is None:
        return None
    return float(legacy_rate) / _NATIVE_BASELINE_RATE


def _preferred_legacy_rate_for_locale(locale: str | None) -> int | None:
    language = _language_from_locale(locale)
    for env_name in (_RATE_ENV_BY_LANGUAGE.get(language, ""), _GLOBAL_RATE_ENV):
        parsed_rate = _parse_rate(os.environ.get(env_name, ""))
        if parsed_rate is not None:
            return parsed_rate
    return _DEFAULT_RATE_BY_LANGUAGE.get(language)


def _language_from_locale(locale: str | None) -> str:
    normalized_locale = str(locale or "").strip().lower().replace("_", "-")
    if not normalized_locale:
        return ""
    return normalized_locale.split("-", maxsplit=1)[0]


def _parse_rate(raw_value: str | None) -> int | None:
    value = str(raw_value or "").strip()
    if not value:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def _extract_sdk_mismatch_versions(text: str) -> tuple[str | None, str | None]:
    match = re.search(
        r"SDK is built with '([^']+)'.*?compiler is '([^']+)'",
        str(text or ""),
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match is None:
        return None, None
    sdk_toolchain = str(match.group(1) or "").strip() or None
    compiler_toolchain = str(match.group(2) or "").strip() or None
    return sdk_toolchain, compiler_toolchain


def _looks_like_toolchain_missing(haystack: str) -> bool:
    if "no such file or directory" in haystack and ("xcrun" in haystack or "swift" in haystack):
        return True
    if "xcrun:" in haystack and "unable to find utility" in haystack:
        return True
    if "invalid active developer path" in haystack:
        return True
    if "requires xcode" in haystack and "command line tools" in haystack:
        return True
    return False


def _looks_like_swift_bridging_conflict(haystack: str) -> bool:
    return "swiftbridging" in haystack and any(
        marker in haystack
        for marker in (
            "duplicate module",
            "redefinition of module",
            "compiled module",
            "conflicting",
        )
    )


def _looks_like_sdk_mismatch(haystack: str) -> bool:
    return any(
        marker in haystack
        for marker in (
            "sdk is not supported by the compiler",
            "sdk is not supported by compiler",
            "compiled module was created by a different version of the compiler",
            "module was created for incompatible target",
            "unable to load standard library for target",
            "failed to build module 'corefoundation'",
            "failed to build module 'accessibility'",
        )
    )


def _looks_like_compile_failure(haystack: str) -> bool:
    return any(
        marker in haystack
        for marker in (
            "error:",
            "failed to build module",
            "could not build",
            "compilation failed",
        )
    )
