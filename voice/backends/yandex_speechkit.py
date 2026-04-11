"""Optional cloud-backed Yandex SpeechKit TTS adapter."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import io
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
from threading import Lock
from typing import Any
from typing import Mapping
import urllib.error
import urllib.request
import wave

from voice.tts_models import BackendCapabilities, VoiceDescriptor
from voice.tts_provider import SpeechUtterance, TTSResult
from voice.voice_profiles import (
    VOICE_PROFILE_RU_ASSISTANT_ANY,
    VOICE_PROFILE_RU_ASSISTANT_FEMALE,
    VOICE_PROFILE_RU_ASSISTANT_MALE,
)

_BACKEND_NAME = "yandex_speechkit"
_ENABLED_ENV = "JARVIS_TTS_YANDEX_ENABLED"
_API_KEY_ENV = "JARVIS_TTS_YANDEX_API_KEY"
_IAM_TOKEN_ENV = "JARVIS_TTS_YANDEX_IAM_TOKEN"
_FOLDER_ID_ENV = "JARVIS_TTS_YANDEX_FOLDER_ID"
_VOICE_ENV = "JARVIS_TTS_YANDEX_VOICE"
_ROLE_ENV = "JARVIS_TTS_YANDEX_ROLE"
_SPEED_ENV = "JARVIS_TTS_YANDEX_SPEED"
_PITCH_SHIFT_ENV = "JARVIS_TTS_YANDEX_PITCH_SHIFT"
_ENDPOINT_ENV = "JARVIS_TTS_YANDEX_ENDPOINT"
_TIMEOUT_ENV = "JARVIS_TTS_YANDEX_TIMEOUT_SECONDS"
_PLAYER_ENV = "JARVIS_TTS_YANDEX_PLAYER"
_CA_BUNDLE_ENV = "JARVIS_TTS_YANDEX_CA_BUNDLE"
_DEFAULT_ENDPOINT = "https://tts.api.cloud.yandex.net/tts/v3/utteranceSynthesis"
_DEFAULT_VOICE = "ermil"
_DEFAULT_ROLE = "good"
_DEFAULT_TIMEOUT_SECONDS = 12.0
_DEFAULT_MAX_TEXT_CHARS = 220
_DEFAULT_JOIN_SILENCE_MS = 90
_STD_CA_BUNDLE_ENVS = (_CA_BUNDLE_ENV, "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE")
_FALLBACK_CA_BUNDLE_PATHS = (
    "/etc/ssl/cert.pem",
    "/private/etc/ssl/cert.pem",
    "/opt/homebrew/etc/openssl@3/cert.pem",
    "/usr/local/etc/openssl@3/cert.pem",
)
_DEFAULT_PLAYER_BY_PLATFORM = {
    "darwin": ("afplay",),
}
_RU_PROFILES = {
    VOICE_PROFILE_RU_ASSISTANT_MALE,
    VOICE_PROFILE_RU_ASSISTANT_FEMALE,
    VOICE_PROFILE_RU_ASSISTANT_ANY,
}
_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё]+")
_NEUTRAL_LATIN_TOKENS = {
    "api",
    "asr",
    "cli",
    "github",
    "http",
    "https",
    "jarvis",
    "json",
    "llm",
    "macos",
    "mvp",
    "ok",
    "okay",
    "openai",
    "piper",
    "python",
    "qa",
    "tts",
}


@dataclass(frozen=True)
class _YandexSpeechKitConfig:
    endpoint: str
    authorization_header: str
    folder_id: str | None
    voice: str
    role: str
    speed: str | None
    pitch_shift: str | None
    timeout_seconds: float


class YandexSpeechKitTTSBackend:
    """Speak Russian through Yandex SpeechKit while keeping local TTS as fallback."""

    def __init__(
        self,
        *,
        environ: Mapping[str, str] | None = None,
        player_command: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        self._environ = environ
        self._player_command_override = tuple(str(part) for part in tuple(player_command or ())) or None
        self._lock = Lock()
        self._current_process: subprocess.Popen[str] | None = None
        self._availability_error_code: str | None = None
        self._availability_error_message: str | None = None
        self._availability_detail_lines: tuple[str, ...] = ()

    def speak(self, utterance: SpeechUtterance | None) -> TTSResult:
        message = str(getattr(utterance, "text", "") or "").strip()
        if not message:
            return TTSResult(ok=True, attempted=False, backend_name=_BACKEND_NAME)
        if not self._should_handle_utterance(utterance):
            return TTSResult(
                ok=False,
                attempted=False,
                error_code="UNSUPPORTED_LOCALE",
                error_message="Yandex SpeechKit TTS backend is configured only for Russian utterances.",
                backend_name=_BACKEND_NAME,
            )
        if not self.is_available():
            return TTSResult(
                ok=False,
                error_code=self._availability_error_code or "TTS_UNAVAILABLE",
                error_message=self._availability_error_message or "Yandex SpeechKit TTS backend is unavailable.",
                backend_name=_BACKEND_NAME,
            )

        config = self._config()
        player_command = self._player_command()
        if config is None or not player_command:
            return TTSResult(
                ok=False,
                error_code="TTS_UNAVAILABLE",
                error_message="Yandex SpeechKit TTS runtime is unavailable.",
                backend_name=_BACKEND_NAME,
            )

        with tempfile.NamedTemporaryFile(prefix="jarvis_yandex_tts_", suffix=".wav", delete=False) as handle:
            output_path = Path(handle.name)
        try:
            audio_result = self._synthesize_to_file(
                message,
                utterance=utterance,
                config=config,
                output_path=output_path,
            )
            if audio_result is not None:
                return audio_result

            process = subprocess.Popen(
                [*player_command, str(output_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self._set_current_process(process)
            try:
                stdout, stderr = process.communicate()
            finally:
                self._clear_current_process(process)

            if process.returncode == 0:
                return TTSResult(ok=True, backend_name=_BACKEND_NAME, voice_id=_voice_id(config))
            return TTSResult(
                ok=False,
                error_code="TTS_FAILED",
                error_message=_first_meaningful_line(stderr or stdout) or "Yandex SpeechKit audio playback failed.",
                backend_name=_BACKEND_NAME,
                voice_id=_voice_id(config),
            )
        finally:
            try:
                output_path.unlink(missing_ok=True)
            except OSError:
                pass

    def stop(self) -> bool:
        """Stop active playback when audio has reached the local player."""
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
        """Expose the configured Yandex voice as one product-level Russian voice."""
        if _language_from_locale(locale_hint) not in {"", "ru"}:
            return []
        config = self._config()
        if config is None:
            voice = self._env(_VOICE_ENV) or _DEFAULT_VOICE
            role = self._env(_ROLE_ENV) or _DEFAULT_ROLE
        else:
            voice = config.voice
            role = config.role
        return [
            VoiceDescriptor(
                id=_voice_id_from_parts(voice=voice, role=role),
                display_name=f"Yandex SpeechKit {voice} ({role})",
                locale="ru-RU",
                gender_hint="male",
                quality_hint="cloud",
                source="yandex_speechkit",
                is_default=True,
            )
        ]

    def resolve_voice(self, profile: str | None, locale: str | None = None) -> VoiceDescriptor | None:
        """Resolve only Russian assistant profiles to the configured Yandex voice."""
        language = _language_from_locale(locale)
        profile_id = str(profile or "").strip()
        if language and language != "ru":
            return None
        if profile_id and profile_id not in _RU_PROFILES:
            return None
        voices = self.list_voices(locale_hint="ru-RU")
        return voices[0] if voices else None

    def is_available(self) -> bool:
        """Return local configuration readiness without performing a network request."""
        config = self._config()
        player_command = self._player_command()
        if not _enabled(self._environ):
            self._set_availability(
                "YANDEX_TTS_DISABLED",
                "Yandex SpeechKit TTS is disabled; set `JARVIS_TTS_YANDEX_ENABLED=1` to enable it.",
                self._availability_context(config=config, player_command=player_command),
            )
            return False
        if config is None:
            self._set_availability(
                "YANDEX_AUTH_MISSING",
                "Yandex SpeechKit TTS requires `JARVIS_TTS_YANDEX_API_KEY` or `JARVIS_TTS_YANDEX_IAM_TOKEN`.",
                self._availability_context(config=config, player_command=player_command),
            )
            return False
        if not player_command:
            self._set_availability(
                "YANDEX_PLAYER_MISSING",
                "Yandex SpeechKit TTS requires a local audio player such as `afplay`.",
                self._availability_context(config=config, player_command=player_command),
            )
            return False
        self._set_availability(None, None, self._availability_context(config=config, player_command=player_command))
        return True

    def availability_diagnostic(self) -> tuple[str | None, str | None]:
        """Return the last local availability diagnostic without exposing secrets."""
        return self._availability_error_code, self._availability_error_message

    def availability_detail_lines(self) -> tuple[str, ...]:
        """Return operator-facing configuration details without secret values."""
        return self._availability_detail_lines

    def capabilities(self) -> BackendCapabilities:
        """Return structured capability metadata for diagnostics."""
        return BackendCapabilities(
            backend_name=_BACKEND_NAME,
            supports_stop=True,
            supports_voice_listing=True,
            supports_voice_resolution=True,
            supports_explicit_voice_id=True,
            supports_rate=True,
            supports_pitch=True,
            is_fallback=False,
        )

    def _synthesize_to_file(
        self,
        message: str,
        *,
        utterance: SpeechUtterance | None,
        config: _YandexSpeechKitConfig,
        output_path: Path,
    ) -> TTSResult | None:
        chunks = _split_text_for_yandex(message, max_chars=_DEFAULT_MAX_TEXT_CHARS)
        rendered_chunks: list[bytes] = []
        for chunk in chunks:
            audio, error = self._synthesize_audio_bytes(chunk, utterance=utterance, config=config)
            if error is not None:
                return error
            rendered_chunks.append(audio)
        if not rendered_chunks:
            return TTSResult(
                ok=False,
                error_code="YANDEX_RESPONSE_INVALID",
                error_message="Yandex SpeechKit response did not include an audio chunk.",
                backend_name=_BACKEND_NAME,
                voice_id=_voice_id(config),
            )
        audio = (
            rendered_chunks[0]
            if len(rendered_chunks) == 1
            else _combine_wav_segments(rendered_chunks, silence_ms=_DEFAULT_JOIN_SILENCE_MS)
        )
        if not audio:
            return TTSResult(
                ok=False,
                error_code="TTS_FAILED",
                error_message="Could not combine Yandex SpeechKit audio segments.",
                backend_name=_BACKEND_NAME,
                voice_id=_voice_id(config),
            )
        try:
            output_path.write_bytes(audio)
        except OSError as exc:
            return TTSResult(
                ok=False,
                error_code="TTS_FAILED",
                error_message=f"Could not write Yandex SpeechKit audio: {exc}",
                backend_name=_BACKEND_NAME,
                voice_id=_voice_id(config),
            )
        return None

    def _synthesize_audio_bytes(
        self,
        message: str,
        *,
        utterance: SpeechUtterance | None,
        config: _YandexSpeechKitConfig,
    ) -> tuple[bytes, TTSResult | None]:
        request = self._request_for_message(message, utterance=utterance, config=config)
        try:
            with urllib.request.urlopen(
                request,
                timeout=config.timeout_seconds,
                context=_ssl_context(self._environ),
            ) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            return b"", TTSResult(
                ok=False,
                error_code="YANDEX_HTTP_ERROR",
                error_message=_http_error_message(exc),
                backend_name=_BACKEND_NAME,
                voice_id=_voice_id(config),
            )
        except urllib.error.URLError as exc:
            return b"", TTSResult(
                ok=False,
                error_code="YANDEX_TRANSPORT_ERROR",
                error_message=f"Yandex SpeechKit request failed: {exc.reason}",
                backend_name=_BACKEND_NAME,
                voice_id=_voice_id(config),
            )
        except ssl.SSLCertVerificationError as exc:
            return b"", TTSResult(
                ok=False,
                error_code="YANDEX_TLS_CERT_ERROR",
                error_message=_ssl_cert_error_message(exc),
                backend_name=_BACKEND_NAME,
                voice_id=_voice_id(config),
            )
        except OSError as exc:
            return b"", TTSResult(
                ok=False,
                error_code="YANDEX_TLS_CERT_ERROR" if isinstance(exc, ssl.SSLCertVerificationError) else "YANDEX_TRANSPORT_ERROR",
                error_message=_ssl_cert_error_message(exc) if isinstance(exc, ssl.SSLCertVerificationError) else f"Yandex SpeechKit request failed: {exc}",
                backend_name=_BACKEND_NAME,
                voice_id=_voice_id(config),
            )

        audio = _audio_bytes_from_response_body(body)
        if not audio:
            return b"", TTSResult(
                ok=False,
                error_code="YANDEX_RESPONSE_INVALID",
                error_message="Yandex SpeechKit response did not include an audio chunk.",
                backend_name=_BACKEND_NAME,
                voice_id=_voice_id(config),
            )
        return audio, None

    def _request_for_message(
        self,
        message: str,
        *,
        utterance: SpeechUtterance | None,
        config: _YandexSpeechKitConfig,
    ) -> urllib.request.Request:
        payload = _request_payload(
            message,
            voice=_voice_from_utterance(utterance, fallback=config.voice),
            role=config.role,
            speed=_speed_from_utterance(utterance, fallback=config.speed),
            pitch_shift=config.pitch_shift,
        )
        headers = {
            "Authorization": config.authorization_header,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if config.folder_id:
            headers["x-folder-id"] = config.folder_id
        return urllib.request.Request(
            config.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )

    def _should_handle_utterance(self, utterance: SpeechUtterance | None) -> bool:
        current = utterance or SpeechUtterance(text="")
        voice_id = str(current.voice_id or "").strip()
        if voice_id and not _looks_like_yandex_voice_id(voice_id):
            return False
        locale_language = _language_from_locale(current.locale)
        if locale_language == "ru":
            return True
        if locale_language and locale_language != "ru":
            return False
        profile = str(current.voice_profile or "").strip()
        if profile in _RU_PROFILES:
            return True
        return _preferred_language_from_text(current.text) == "ru"

    def _config(self) -> _YandexSpeechKitConfig | None:
        authorization_header = _authorization_header(self._environ)
        if not authorization_header:
            return None
        return _YandexSpeechKitConfig(
            endpoint=self._env(_ENDPOINT_ENV) or _DEFAULT_ENDPOINT,
            authorization_header=authorization_header,
            folder_id=self._env(_FOLDER_ID_ENV) or None,
            voice=self._env(_VOICE_ENV) or _DEFAULT_VOICE,
            role=self._env(_ROLE_ENV) or _DEFAULT_ROLE,
            speed=self._env(_SPEED_ENV) or None,
            pitch_shift=self._env(_PITCH_SHIFT_ENV) or None,
            timeout_seconds=_timeout_seconds(self._env(_TIMEOUT_ENV)),
        )

    def _player_command(self) -> tuple[str, ...]:
        override = self._player_command_override
        if override:
            return override
        env_value = self._env(_PLAYER_ENV)
        if env_value:
            return (env_value,)
        default = _DEFAULT_PLAYER_BY_PLATFORM.get(sys.platform, ())
        if not default:
            return ()
        binary = shutil.which(default[0])
        if binary is None:
            return ()
        return (binary, *default[1:])

    def _availability_context(
        self,
        *,
        config: _YandexSpeechKitConfig | None,
        player_command: tuple[str, ...],
    ) -> tuple[str, ...]:
        voice = config.voice if config is not None else (self._env(_VOICE_ENV) or _DEFAULT_VOICE)
        role = config.role if config is not None else (self._env(_ROLE_ENV) or _DEFAULT_ROLE)
        endpoint = config.endpoint if config is not None else (self._env(_ENDPOINT_ENV) or _DEFAULT_ENDPOINT)
        lines = [
            f"enabled: {'yes' if _enabled(self._environ) else 'no'}",
            f"endpoint: {endpoint}",
            f"voice: {voice}",
            f"role: {role}",
            f"auth: {'configured' if _authorization_header(self._environ) else 'missing'}",
            f"ca bundle: {_ca_bundle_path(self._environ) or 'system default'}",
            f"folder id: {'configured' if config is not None and config.folder_id else 'not configured'}",
        ]
        if player_command:
            lines.append(f"audio player: {' '.join(player_command)}")
        else:
            lines.append("audio player: missing")
        return tuple(lines)

    def _set_availability(
        self,
        error_code: str | None,
        error_message: str | None,
        detail_lines: tuple[str, ...],
    ) -> None:
        self._availability_error_code = str(error_code or "").strip() or None
        self._availability_error_message = str(error_message or "").strip() or None
        self._availability_detail_lines = tuple(line for line in detail_lines if str(line or "").strip())

    def _set_current_process(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            self._current_process = process

    def _clear_current_process(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            if self._current_process is process:
                self._current_process = None

    def _env(self, name: str) -> str:
        current = os.environ if self._environ is None else self._environ
        return str(current.get(name, "") or "").strip()


def yandex_speechkit_backend_requested(environ: Mapping[str, str] | None = None) -> bool:
    """Return whether the Yandex SpeechKit backend should be wired into the manager."""
    return _enabled(environ)


def yandex_speechkit_backend_configured(environ: Mapping[str, str] | None = None) -> bool:
    """Return whether any explicit Yandex SpeechKit runtime config is present."""
    current = os.environ if environ is None else environ
    tracked_env_names = (
        _ENABLED_ENV,
        _API_KEY_ENV,
        _IAM_TOKEN_ENV,
        _FOLDER_ID_ENV,
        _VOICE_ENV,
        _ROLE_ENV,
        _SPEED_ENV,
        _PITCH_SHIFT_ENV,
        _ENDPOINT_ENV,
        _TIMEOUT_ENV,
        _PLAYER_ENV,
    )
    return any(str(current.get(name, "") or "").strip() for name in tracked_env_names)


def _enabled(environ: Mapping[str, str] | None = None) -> bool:
    current = os.environ if environ is None else environ
    value = str(current.get(_ENABLED_ENV, "") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _authorization_header(environ: Mapping[str, str] | None = None) -> str:
    current = os.environ if environ is None else environ
    api_key = str(current.get(_API_KEY_ENV, "") or "").strip()
    if api_key:
        return f"Api-Key {api_key}"
    iam_token = str(current.get(_IAM_TOKEN_ENV, "") or "").strip()
    if iam_token:
        return f"Bearer {iam_token}"
    return ""


def _request_payload(
    message: str,
    *,
    voice: str,
    role: str,
    speed: str | None,
    pitch_shift: str | None,
) -> dict[str, object]:
    hints: list[dict[str, object]] = [
        {"voice": voice},
        {"role": role},
    ]
    if speed:
        hints.append({"speed": speed})
    if pitch_shift:
        hints.append({"pitchShift": pitch_shift})
    return {
        "text": str(message or "").strip(),
        "hints": hints,
        "outputAudioSpec": {
            "containerAudio": {
                "containerAudioType": "WAV",
            },
        },
    }


def _audio_bytes_from_response_body(body: bytes) -> bytes:
    text = body.decode("utf-8", errors="replace").strip()
    if not text:
        return b""

    chunks = _audio_chunks_from_json_text(text)
    if not chunks:
        chunks = _audio_chunks_from_json_lines(text)
    decoded: list[bytes] = []
    for chunk in chunks:
        try:
            decoded.append(base64.b64decode(chunk, validate=True))
        except (ValueError, TypeError):
            return b""
    return b"".join(decoded)


def _split_text_for_yandex(text: str, *, max_chars: int) -> list[str]:
    current = re.sub(r"\s+", " ", str(text or "").strip())
    if not current:
        return []
    if len(current) <= max_chars:
        return [current]
    sentences = _sentence_like_chunks(current)
    chunks: list[str] = []
    buffer = ""
    for sentence in sentences:
        if len(sentence) > max_chars:
            for fragment in _split_oversized_chunk(sentence, max_chars=max_chars):
                buffer = _append_chunk(buffer, fragment, max_chars=max_chars, target=chunks)
            continue
        buffer = _append_chunk(buffer, sentence, max_chars=max_chars, target=chunks)
    if buffer:
        chunks.append(buffer)
    return chunks


def _sentence_like_chunks(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?;:])\s+", text)
    return [str(part or "").strip() for part in parts if str(part or "").strip()]


def _split_oversized_chunk(text: str, *, max_chars: int) -> list[str]:
    parts = re.split(r"(?<=[,])\s+", text)
    normalized_parts = [str(part or "").strip() for part in parts if str(part or "").strip()]
    if len(normalized_parts) <= 1:
        return _split_oversized_words(text, max_chars=max_chars)
    chunks: list[str] = []
    buffer = ""
    for part in normalized_parts:
        if len(part) > max_chars:
            for word_chunk in _split_oversized_words(part, max_chars=max_chars):
                buffer = _append_chunk(buffer, word_chunk, max_chars=max_chars, target=chunks)
            continue
        buffer = _append_chunk(buffer, part, max_chars=max_chars, target=chunks)
    if buffer:
        chunks.append(buffer)
    return chunks


def _split_oversized_words(text: str, *, max_chars: int) -> list[str]:
    words = [str(word or "").strip() for word in text.split(" ") if str(word or "").strip()]
    chunks: list[str] = []
    buffer = ""
    for word in words:
        if not buffer:
            buffer = word
            continue
        candidate = f"{buffer} {word}"
        if len(candidate) <= max_chars:
            buffer = candidate
            continue
        chunks.append(buffer)
        buffer = word
    if buffer:
        chunks.append(buffer)
    return chunks


def _append_chunk(current: str, addition: str, *, max_chars: int, target: list[str]) -> str:
    if not current:
        return addition
    candidate = f"{current} {addition}"
    if len(candidate) <= max_chars:
        return candidate
    target.append(current)
    return addition


def _combine_wav_segments(segments: list[bytes], *, silence_ms: int) -> bytes:
    if not segments:
        return b""
    output = io.BytesIO()
    base_params: tuple[int, int, int, str, str] | None = None
    rendered_frames: list[bytes] = []
    for segment in segments:
        with wave.open(io.BytesIO(segment), "rb") as reader:
            params = (
                reader.getnchannels(),
                reader.getsampwidth(),
                reader.getframerate(),
                reader.getcomptype(),
                reader.getcompname(),
            )
            if base_params is None:
                base_params = params
            elif params != base_params:
                return b""
            rendered_frames.append(reader.readframes(reader.getnframes()))
    if base_params is None:
        return b""
    channels, sample_width, frame_rate, comp_type, comp_name = base_params
    frame_size = channels * sample_width
    silence_frame_count = int(frame_rate * max(silence_ms, 0) / 1000)
    silence = b"\x00" * frame_size * silence_frame_count
    with wave.open(output, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(sample_width)
        writer.setframerate(frame_rate)
        writer.setcomptype(comp_type, comp_name)
        for index, frames in enumerate(rendered_frames):
            writer.writeframes(frames)
            if index < len(rendered_frames) - 1 and silence:
                writer.writeframes(silence)
    return output.getvalue()


def _ssl_context(environ: Mapping[str, str] | None = None) -> ssl.SSLContext:
    ca_bundle_path = _ca_bundle_path(environ)
    if ca_bundle_path:
        return ssl.create_default_context(cafile=ca_bundle_path)
    return ssl.create_default_context()


def _ca_bundle_path(environ: Mapping[str, str] | None = None) -> str | None:
    current = os.environ if environ is None else environ
    for env_name in _STD_CA_BUNDLE_ENVS:
        bundle_path = str(current.get(env_name, "") or "").strip()
        if bundle_path and Path(bundle_path).is_file():
            return bundle_path
    try:
        import certifi
    except ImportError:
        certifi_path = None
    else:
        certifi_path = str(certifi.where()).strip() or None
    if certifi_path and Path(certifi_path).is_file():
        return certifi_path

    default_verify_paths = ssl.get_default_verify_paths()
    for candidate in (
        str(getattr(default_verify_paths, "cafile", "") or "").strip(),
        *(_FALLBACK_CA_BUNDLE_PATHS),
    ):
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def _ssl_cert_error_message(error: BaseException) -> str:
    return (
        "Yandex SpeechKit request failed TLS certificate verification. "
        f"Reason: {error}. "
        "Retry with a trusted CA bundle via JARVIS_TTS_YANDEX_CA_BUNDLE or SSL_CERT_FILE, "
        "or repair the local Python certificate store."
    )


def _audio_chunks_from_json_text(text: str) -> list[str]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    return _audio_chunk_strings(payload)


def _audio_chunks_from_json_lines(text: str) -> list[str]:
    chunks: list[str] = []
    for line in text.splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            return []
        chunks.extend(_audio_chunk_strings(payload))
    return chunks


def _audio_chunk_strings(payload: object) -> list[str]:
    chunks: list[str] = []
    if isinstance(payload, dict):
        audio_chunk = payload.get("audioChunk")
        if isinstance(audio_chunk, dict):
            data = audio_chunk.get("data")
            if isinstance(data, str) and data.strip():
                chunks.append(data.strip())
        for value in payload.values():
            chunks.extend(_audio_chunk_strings(value))
    elif isinstance(payload, list):
        for value in payload:
            chunks.extend(_audio_chunk_strings(value))
    return chunks


def _http_error_message(exc: urllib.error.HTTPError) -> str:
    status = getattr(exc, "code", None)
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except OSError:
        body = ""
    detail = _first_meaningful_line(body)
    if detail:
        return f"Yandex SpeechKit request failed with HTTP {status}: {detail}"
    return f"Yandex SpeechKit request failed with HTTP {status}."


def _voice_from_utterance(utterance: SpeechUtterance | None, *, fallback: str) -> str:
    voice_id = str(getattr(utterance, "voice_id", "") or "").strip()
    if _looks_like_yandex_voice_id(voice_id):
        if voice_id.startswith("yandex:"):
            parts = [part for part in voice_id.split(":") if part]
            return parts[1] if len(parts) >= 2 else fallback
        return voice_id
    return fallback


def _speed_from_utterance(utterance: SpeechUtterance | None, *, fallback: str | None) -> str | None:
    rate = getattr(utterance, "rate", None)
    if isinstance(rate, (float, int)) and rate > 0:
        return str(rate)
    return fallback


def _looks_like_yandex_voice_id(voice_id: str) -> bool:
    current = str(voice_id or "").strip()
    if not current:
        return False
    if current.startswith("yandex:"):
        return True
    return "/" not in current and "\\" not in current and not current.endswith(".onnx")


def _voice_id(config: _YandexSpeechKitConfig) -> str:
    return _voice_id_from_parts(voice=config.voice, role=config.role)


def _voice_id_from_parts(*, voice: str, role: str) -> str:
    voice_name = str(voice or "").strip() or _DEFAULT_VOICE
    role_name = str(role or "").strip() or _DEFAULT_ROLE
    return f"yandex:{voice_name}:{role_name}"


def _timeout_seconds(value: str) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        return _DEFAULT_TIMEOUT_SECONDS
    return timeout if timeout > 0 else _DEFAULT_TIMEOUT_SECONDS


def _preferred_language_from_text(text: str | None) -> str:
    current = str(text or "")
    first_signal = _first_meaningful_language_signal(current)
    if first_signal:
        return first_signal
    latin_letters = sum(1 for char in current if _LATIN_RE.fullmatch(char))
    cyrillic_letters = sum(1 for char in current if _CYRILLIC_RE.fullmatch(char))
    if cyrillic_letters > latin_letters:
        return "ru"
    if latin_letters > cyrillic_letters:
        return "en"
    return ""


def _first_meaningful_language_signal(text: str) -> str:
    for match in _WORD_RE.finditer(text):
        token = match.group(0)
        if _CYRILLIC_RE.search(token):
            return "ru"
        if _LATIN_RE.search(token):
            normalized = token.lower()
            if normalized in _NEUTRAL_LATIN_TOKENS:
                continue
            return "en"
    return ""


def _language_from_locale(locale: str | None) -> str:
    normalized = str(locale or "").strip().lower().replace("_", "-")
    if not normalized:
        return ""
    return normalized.split("-", maxsplit=1)[0]


def _first_meaningful_line(text: str | None) -> str:
    for line in str(text or "").splitlines():
        candidate = line.strip()
        if candidate:
            return candidate
    return ""
