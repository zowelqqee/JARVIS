"""Local model-based Piper TTS backend."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from threading import Lock
from typing import Any
from typing import Mapping
import wave

from voice.tts_models import BackendCapabilities, VoiceDescriptor
from voice.tts_provider import SpeechUtterance, TTSResult
from voice.voice_profiles import (
    VOICE_PROFILE_EN_ASSISTANT_ANY,
    VOICE_PROFILE_EN_ASSISTANT_FEMALE,
    VOICE_PROFILE_EN_ASSISTANT_MALE,
    VOICE_PROFILE_RU_ASSISTANT_ANY,
    VOICE_PROFILE_RU_ASSISTANT_FEMALE,
    VOICE_PROFILE_RU_ASSISTANT_MALE,
    fallback_voice_profile_ids,
)

_BACKEND_NAME = "local_piper"
_BINARY_ENV = "JARVIS_TTS_PIPER_BIN"
_PLAYER_ENV = "JARVIS_TTS_PIPER_PLAYER"
_RUNTIME_ROOT_ENV = "JARVIS_TTS_PIPER_ROOT"
_DEFAULT_RUNTIME_ROOT = Path(__file__).resolve().parents[2] / "tmp" / "runtime" / "piper"
_MANIFEST_RELATIVE_PATH = Path("manifest.json")
_DEFAULT_BINARY_RELATIVE_CANDIDATES = (
    Path("venv/bin/piper"),
    Path("bin/piper"),
    Path("piper"),
)

_MODEL_ENV_BY_PROFILE = {
    VOICE_PROFILE_RU_ASSISTANT_MALE: ("JARVIS_TTS_PIPER_MODEL_RU_MALE", "JARVIS_TTS_PIPER_MODEL_RU"),
    VOICE_PROFILE_RU_ASSISTANT_FEMALE: ("JARVIS_TTS_PIPER_MODEL_RU_FEMALE", "JARVIS_TTS_PIPER_MODEL_RU"),
    VOICE_PROFILE_RU_ASSISTANT_ANY: ("JARVIS_TTS_PIPER_MODEL_RU",),
    VOICE_PROFILE_EN_ASSISTANT_MALE: ("JARVIS_TTS_PIPER_MODEL_EN_MALE", "JARVIS_TTS_PIPER_MODEL_EN"),
    VOICE_PROFILE_EN_ASSISTANT_FEMALE: ("JARVIS_TTS_PIPER_MODEL_EN_FEMALE", "JARVIS_TTS_PIPER_MODEL_EN"),
    VOICE_PROFILE_EN_ASSISTANT_ANY: ("JARVIS_TTS_PIPER_MODEL_EN",),
}
_MODEL_ENV_BY_LANGUAGE = {
    "ru": ("JARVIS_TTS_PIPER_MODEL_RU_MALE", "JARVIS_TTS_PIPER_MODEL_RU_FEMALE", "JARVIS_TTS_PIPER_MODEL_RU"),
    "en": ("JARVIS_TTS_PIPER_MODEL_EN_MALE", "JARVIS_TTS_PIPER_MODEL_EN_FEMALE", "JARVIS_TTS_PIPER_MODEL_EN"),
}
_DEFAULT_PLAYER_BY_PLATFORM = {
    "darwin": ("afplay",),
}
_DEFAULT_LOCALE_BY_LANGUAGE = {
    "ru": "ru-RU",
    "en": "en-US",
}
_DEFAULT_MODEL_SLOT_BY_ENV = {
    "JARVIS_TTS_PIPER_MODEL_RU_MALE": {
        "path": Path("models/ru_male.onnx"),
        "display_name": "Russian Male",
        "locale": "ru-RU",
        "gender_hint": "male",
    },
    "JARVIS_TTS_PIPER_MODEL_RU_FEMALE": {
        "path": Path("models/ru_female.onnx"),
        "display_name": "Russian Female",
        "locale": "ru-RU",
        "gender_hint": "female",
    },
    "JARVIS_TTS_PIPER_MODEL_RU": {
        "path": Path("models/ru.onnx"),
        "display_name": "Russian",
        "locale": "ru-RU",
        "gender_hint": None,
    },
    "JARVIS_TTS_PIPER_MODEL_EN_MALE": {
        "path": Path("models/en_male.onnx"),
        "display_name": "English Male",
        "locale": "en-US",
        "gender_hint": "male",
    },
    "JARVIS_TTS_PIPER_MODEL_EN_FEMALE": {
        "path": Path("models/en_female.onnx"),
        "display_name": "English Female",
        "locale": "en-US",
        "gender_hint": "female",
    },
    "JARVIS_TTS_PIPER_MODEL_EN": {
        "path": Path("models/en.onnx"),
        "display_name": "English",
        "locale": "en-US",
        "gender_hint": None,
    },
}
_SLOT_KEY_BY_ENV = {
    "JARVIS_TTS_PIPER_MODEL_RU_MALE": "ru_male",
    "JARVIS_TTS_PIPER_MODEL_RU_FEMALE": "ru_female",
    "JARVIS_TTS_PIPER_MODEL_RU": "ru",
    "JARVIS_TTS_PIPER_MODEL_EN_MALE": "en_male",
    "JARVIS_TTS_PIPER_MODEL_EN_FEMALE": "en_female",
    "JARVIS_TTS_PIPER_MODEL_EN": "en",
}
_QUALITY_TOKENS = ("x_low", "low", "medium", "high")
_PROFILE_FAMILY_BY_PROFILE = {
    VOICE_PROFILE_RU_ASSISTANT_MALE: "male",
    VOICE_PROFILE_RU_ASSISTANT_FEMALE: "female",
    VOICE_PROFILE_RU_ASSISTANT_ANY: "any",
    VOICE_PROFILE_EN_ASSISTANT_MALE: "male",
    VOICE_PROFILE_EN_ASSISTANT_FEMALE: "female",
    VOICE_PROFILE_EN_ASSISTANT_ANY: "any",
}
_PROFILE_BY_LANGUAGE_AND_FAMILY = {
    ("ru", "male"): VOICE_PROFILE_RU_ASSISTANT_MALE,
    ("ru", "female"): VOICE_PROFILE_RU_ASSISTANT_FEMALE,
    ("ru", "any"): VOICE_PROFILE_RU_ASSISTANT_ANY,
    ("en", "male"): VOICE_PROFILE_EN_ASSISTANT_MALE,
    ("en", "female"): VOICE_PROFILE_EN_ASSISTANT_FEMALE,
    ("en", "any"): VOICE_PROFILE_EN_ASSISTANT_ANY,
}
_PIPER_ARG_BY_MANIFEST_KEY = {
    "length_scale": "--length-scale",
    "sentence_silence": "--sentence-silence",
}
_ELLIPSIS_RE = re.compile(r"(?:\.{3,}|\u2026)+")
_MULTISPACE_RE = re.compile(r"\s+")
_SPACE_BEFORE_PUNCTUATION_RE = re.compile(r"\s+([,.;:!?])")
_DOUBLE_COMMA_RE = re.compile(r"(,\s*){2,}")
_DOUBLE_SENTENCE_BREAK_RE = re.compile(r"([.!?])(?:\s*[,:;])+\s*")
_RU_DASH_BREAK_RE = re.compile(r"\s*[\u2013\u2014]\s*|(?<=\s)-(?=\s)")
_RU_SOFT_COMMA_BEFORE_RE = re.compile(
    r",\s+(?=(?:что|чтобы|чтоб|как|если|когда|где|куда|откуда|почему|зачем|"
    r"котор[а-яё]*|потому|поэтому|то есть|например|и|или)\b)",
    flags=re.IGNORECASE,
)
_RU_SOFT_COMMA_AFTER_RE = re.compile(
    r"\b(?P<lead>да|нет|окей|ладно|хорошо|смотри|слушай|кажется|похоже|например|то есть),\s+",
    flags=re.IGNORECASE,
)
_RU_SOFT_PAUSE_MARKER = "__JARVIS_TTS_SHORT_PAUSE__"
_LANGUAGE_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё]+")
_LATIN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'_-]*")
_ENGLISH_ISLAND_RE = re.compile(
    r"(?<![A-Za-z0-9_./-])"
    r"(?P<island>[A-Za-z][A-Za-z0-9'_-]*(?:[ \t]+[A-Za-z][A-Za-z0-9'_-]*)+)"
    r"(?![A-Za-z0-9_./-])"
)
_RU_TECH_TOKEN_PRONUNCIATIONS = {
    "API": "эй пи ай",
    "ASR": "эй эс ар",
    "CLI": "си эль ай",
    "Docker": "докер",
    "FAQ": "эф эй кью",
    "Git": "гит",
    "GitHub": "Гитхаб",
    "GUI": "джи ю ай",
    "HTTP": "эйч ти ти пи",
    "HTTPS": "эйч ти ти пи эс",
    "JSON": "джейсон",
    "JARVIS": "Джарвис",
    "LLM": "эль эль эм",
    "MVP": "эм ви пи",
    "OpenAI": "Оупен эй ай",
    "Piper": "Пайпер",
    "Postgres": "постгрес",
    "Python": "Пайтон",
    "QA": "кью эй",
    "Swift": "свифт",
    "TOML": "томл",
    "TTS": "ти ти эс",
    "URL": "ю ар эл",
    "YAML": "ямл",
    "macOS": "мак о эс",
}
_PLAYBACK_LEADING_SILENCE_MS = 30
_PLAYBACK_TRAILING_SILENCE_MS = 45
_PLAYBACK_INTER_SEGMENT_SILENCE_MS = 35


@dataclass(frozen=True)
class _PiperSpeechSegment:
    text: str
    descriptor: VoiceDescriptor
    slot_config: Mapping[str, object] | None


class PiperTTSBackend:
    """Speak through a local Piper model plus a platform audio player."""

    def __init__(
        self,
        *,
        environ: Mapping[str, str] | None = None,
        binary: str | None = None,
        player_command: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        self._environ = environ
        self._lock = Lock()
        self._current_process: subprocess.Popen[str] | None = None
        self._binary_override = str(binary or "").strip() or None
        self._player_command_override = tuple(str(part) for part in tuple(player_command or ())) or None
        self._availability: bool | None = None
        self._availability_error_code: str | None = None
        self._availability_error_message: str | None = None
        self._availability_detail_lines: tuple[str, ...] = ()

    def speak(self, utterance: SpeechUtterance | None) -> TTSResult:
        message = str(getattr(utterance, "text", "") or "").strip()
        if not message:
            return TTSResult(ok=True, attempted=False, backend_name=_BACKEND_NAME)

        if not self.is_available():
            return TTSResult(
                ok=False,
                error_code=self._availability_error_code or "TTS_UNAVAILABLE",
                error_message=self._availability_error_message or "Local Piper TTS backend is unavailable.",
                backend_name=_BACKEND_NAME,
            )

        model_descriptor = self._descriptor_for_utterance(utterance)
        if model_descriptor is None:
            return TTSResult(
                ok=False,
                error_code="MODEL_NOT_CONFIGURED",
                error_message="No Piper model is configured for this utterance locale/profile.",
                backend_name=_BACKEND_NAME,
            )

        binary_path = self._binary_path()
        player_command = self._player_command()
        if binary_path is None or not player_command:
            return TTSResult(
                ok=False,
                error_code="TTS_UNAVAILABLE",
                error_message="Local Piper runtime is unavailable.",
                backend_name=_BACKEND_NAME,
            )

        speech_segments = self._speech_segments_for_utterance(
            utterance,
            fallback_descriptor=model_descriptor,
        )
        output_paths: list[Path] = []

        try:
            for segment in speech_segments:
                with tempfile.NamedTemporaryFile(prefix="jarvis_piper_", suffix=".wav", delete=False) as handle:
                    output_path = Path(handle.name)
                output_paths.append(output_path)
                generation_result = self._generate_speech_segment(
                    binary_path=binary_path,
                    segment=segment,
                    output_path=output_path,
                )
                if generation_result is not None:
                    return generation_result
                _pad_wav_file_edges(
                    output_path,
                    leading_silence_ms=_PLAYBACK_LEADING_SILENCE_MS,
                    trailing_silence_ms=_PLAYBACK_TRAILING_SILENCE_MS,
                )

            playback_paths = list(output_paths)
            if len(output_paths) > 1:
                with tempfile.NamedTemporaryFile(prefix="jarvis_piper_combined_", suffix=".wav", delete=False) as handle:
                    combined_path = Path(handle.name)
                output_paths.append(combined_path)
                if _combine_wav_files(
                    playback_paths,
                    combined_path,
                    inter_segment_silence_ms=_PLAYBACK_INTER_SEGMENT_SILENCE_MS,
                ):
                    playback_paths = [combined_path]

            for output_path in playback_paths:
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

                if process.returncode != 0:
                    return TTSResult(
                        ok=False,
                        error_code="TTS_FAILED",
                        error_message=_first_meaningful_line(stderr or stdout) or "Local Piper audio playback failed.",
                        backend_name=_BACKEND_NAME,
                        voice_id=model_descriptor.id,
                    )
            return TTSResult(ok=True, backend_name=_BACKEND_NAME, voice_id=model_descriptor.id)
        finally:
            for output_path in output_paths:
                try:
                    output_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def stop(self) -> bool:
        """Stop active playback when one is running."""
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
        """Expose configured local models as synthetic voices."""
        requested_language = _language_from_locale(locale_hint)
        descriptors: list[VoiceDescriptor] = []
        for language in ("ru", "en"):
            if requested_language and requested_language != language:
                continue
            descriptors.extend(self._configured_descriptors_for_language(language))
        return descriptors

    def resolve_voice(self, profile: str | None, locale: str | None = None) -> VoiceDescriptor | None:
        """Resolve a product-level profile to a configured Piper model."""
        explicit_voice_id = ""
        if isinstance(profile, str):
            explicit_voice_id = ""
        descriptor = self._descriptor_for_profile(profile, locale)
        return descriptor

    def is_available(self) -> bool:
        """Return whether the local Piper runtime is configured and executable."""
        if self._availability is None:
            self._availability = self._compute_availability()
        return self._availability

    def availability_diagnostic(self) -> tuple[str | None, str | None]:
        """Return the last known availability failure."""
        return self._availability_error_code, self._availability_error_message

    def availability_detail_lines(self) -> tuple[str, ...]:
        """Return operator-facing availability details."""
        return self._availability_detail_lines

    def capabilities(self) -> BackendCapabilities:
        """Return structured capability metadata."""
        return BackendCapabilities(
            backend_name=_BACKEND_NAME,
            supports_stop=True,
            supports_voice_listing=True,
            supports_voice_resolution=True,
            supports_explicit_voice_id=True,
            is_fallback=False,
        )

    def _compute_availability(self) -> bool:
        binary_path = self._binary_path()
        player_command = self._player_command()
        configured = self.list_voices()
        if binary_path is None:
            self._set_availability(
                "PIPER_BINARY_MISSING",
                "Local Piper binary is not available; configure `JARVIS_TTS_PIPER_BIN` or install `piper`.",
                self._availability_context(binary_path=None, player_command=player_command, configured=configured),
            )
            return False
        if not configured:
            self._set_availability(
                "PIPER_MODEL_MISSING",
                "No Piper models are configured; set `JARVIS_TTS_PIPER_MODEL_RU`/`EN` or profile-specific model paths.",
                self._availability_context(binary_path=binary_path, player_command=player_command, configured=configured),
            )
            return False
        if not player_command:
            self._set_availability(
                "PIPER_PLAYER_MISSING",
                "No local audio player is available for Piper output; configure `JARVIS_TTS_PIPER_PLAYER`.",
                self._availability_context(binary_path=binary_path, player_command=player_command, configured=configured),
            )
            return False
        self._set_availability(None, None, ())
        return True

    def _availability_context(
        self,
        *,
        binary_path: str | None,
        player_command: tuple[str, ...],
        configured: list[VoiceDescriptor],
    ) -> tuple[str, ...]:
        lines: list[str] = [f"runtime root: {self._runtime_root()}"]
        if binary_path:
            lines.append(f"piper binary: {binary_path}")
        else:
            for candidate in self._default_binary_candidates():
                lines.append(f"expected binary candidate: {candidate}")
        if player_command:
            lines.append(f"audio player: {' '.join(player_command)}")
        if configured:
            for descriptor in configured:
                lines.append(f"configured model: {descriptor.display_name} -> {descriptor.id}")
        else:
            for env_name in (
                "JARVIS_TTS_PIPER_MODEL_RU",
                "JARVIS_TTS_PIPER_MODEL_RU_MALE",
                "JARVIS_TTS_PIPER_MODEL_RU_FEMALE",
                "JARVIS_TTS_PIPER_MODEL_EN",
                "JARVIS_TTS_PIPER_MODEL_EN_MALE",
                "JARVIS_TTS_PIPER_MODEL_EN_FEMALE",
            ):
                default_slot = self._default_model_slot_path(env_name)
                if default_slot is not None:
                    lines.append(f"expected model slot: {env_name} -> {default_slot}")
                else:
                    lines.append(f"missing model env: {env_name}")
        return tuple(lines)

    def _descriptor_for_utterance(self, utterance: SpeechUtterance | None) -> VoiceDescriptor | None:
        current = utterance or SpeechUtterance(text="")
        explicit_voice_id = str(current.voice_id or "").strip()
        if explicit_voice_id:
            return _descriptor_from_model_path(explicit_voice_id, locale=current.locale)
        text_language = _dominant_language_from_text(current.text)
        locale_language = _language_from_locale(current.locale)
        if text_language and text_language != locale_language:
            switched_profile = _profile_for_language(current.voice_profile, text_language)
            switched_locale = _DEFAULT_LOCALE_BY_LANGUAGE.get(text_language)
            descriptor = self._descriptor_for_profile(switched_profile, switched_locale)
            if descriptor is not None:
                return descriptor
        return self._descriptor_for_profile(current.voice_profile, current.locale)

    def _descriptor_for_profile(self, profile: str | None, locale: str | None) -> VoiceDescriptor | None:
        for profile_id in fallback_voice_profile_ids(profile, locale):
            descriptor = self._descriptor_for_profile_id(profile_id, locale)
            if descriptor is not None:
                return descriptor
        language = _language_from_locale(locale)
        for env_name in _MODEL_ENV_BY_LANGUAGE.get(language, ()):
            descriptor = self._explicit_descriptor_for_env(env_name, locale=locale)
            if descriptor is not None:
                return descriptor
        for env_name in _MODEL_ENV_BY_LANGUAGE.get(language, ()):
            descriptor = self._default_descriptor_for_env(env_name, locale=locale)
            if descriptor is not None:
                return descriptor
        return None

    def _descriptor_for_profile_id(self, profile_id: str, locale: str | None) -> VoiceDescriptor | None:
        for env_name in _MODEL_ENV_BY_PROFILE.get(profile_id, ()):
            descriptor = self._explicit_descriptor_for_env(env_name, locale=locale)
            if descriptor is not None:
                return descriptor
        for env_name in _MODEL_ENV_BY_PROFILE.get(profile_id, ()):
            descriptor = self._default_descriptor_for_env(env_name, locale=locale)
            if descriptor is not None:
                return descriptor
        return None

    def _configured_descriptors_for_language(self, language: str) -> list[VoiceDescriptor]:
        seen: set[str] = set()
        descriptors: list[VoiceDescriptor] = []
        locale = _DEFAULT_LOCALE_BY_LANGUAGE.get(language)
        for env_name in _MODEL_ENV_BY_LANGUAGE.get(language, ()):
            descriptor = self._explicit_descriptor_for_env(env_name, locale=locale)
            if descriptor is None:
                descriptor = self._default_descriptor_for_env(env_name, locale=locale)
            if descriptor is None or descriptor.id in seen:
                continue
            seen.add(descriptor.id)
            descriptors.append(descriptor)
        return descriptors

    def _binary_path(self) -> str | None:
        candidate = self._binary_override or self._env(_BINARY_ENV)
        if candidate:
            return _resolve_binary_candidate(candidate)
        for default_candidate in self._default_binary_candidates():
            if default_candidate.exists():
                return str(default_candidate)
        return shutil.which("piper")

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

    def _env(self, name: str) -> str:
        return str((self._environ or os.environ).get(name, "") or "").strip()

    def _runtime_root(self) -> Path:
        override = self._env(_RUNTIME_ROOT_ENV)
        if override:
            return Path(override).expanduser()
        return _DEFAULT_RUNTIME_ROOT

    def _default_binary_candidates(self) -> tuple[Path, ...]:
        root = self._runtime_root()
        return tuple(root / candidate for candidate in _DEFAULT_BINARY_RELATIVE_CANDIDATES)

    def _default_model_slot_path(self, env_name: str) -> Path | None:
        slot = self._slot_config_for_env(env_name)
        if slot is None:
            return None
        path_value = slot.get("path")
        if not isinstance(path_value, (str, Path)):
            return None
        return self._runtime_root() / Path(path_value)

    def _explicit_descriptor_for_env(self, env_name: str, *, locale: str | None) -> VoiceDescriptor | None:
        env_value = self._env(env_name)
        if not env_value:
            return None
        slot = self._slot_config_for_env(env_name) or {}
        return _descriptor_from_model_path(
            env_value,
            locale=locale or str(slot.get("locale") or ""),
            display_name=str(slot.get("display_name") or "").strip() or None,
            gender_hint=str(slot.get("gender_hint") or "").strip() or None,
        )

    def _default_descriptor_for_env(self, env_name: str, *, locale: str | None) -> VoiceDescriptor | None:
        slot = self._slot_config_for_env(env_name) or {}
        default_path = self._default_model_slot_path(env_name)
        model_path = str(default_path) if default_path is not None else ""
        return _descriptor_from_model_path(
            model_path,
            locale=locale or str(slot.get("locale") or ""),
            display_name=str(slot.get("display_name") or "").strip() or None,
            gender_hint=str(slot.get("gender_hint") or "").strip() or None,
        )

    def _slot_config_for_env(self, env_name: str) -> Mapping[str, object] | None:
        base_slot = _DEFAULT_MODEL_SLOT_BY_ENV.get(env_name)
        manifest_slot = self._manifest_slot_for_env(env_name)
        if base_slot is None:
            return manifest_slot
        if not manifest_slot:
            return base_slot
        merged = dict(base_slot)
        merged.update(
            {
                key: value
                for key, value in manifest_slot.items()
                if key in {"path", "display_name", "locale", "gender_hint", "piper_args", "audio_postprocess"}
            }
        )
        return merged

    def _manifest_slot_for_env(self, env_name: str) -> Mapping[str, object] | None:
        slot_key = _SLOT_KEY_BY_ENV.get(env_name)
        if not slot_key:
            return None
        slots = self._manifest_slots()
        raw_slot = slots.get(slot_key)
        if isinstance(raw_slot, Mapping):
            return raw_slot
        return None

    def _manifest_slots(self) -> dict[str, Mapping[str, object]]:
        payload = _load_runtime_manifest(self._runtime_root())
        raw_slots = payload.get("slots")
        if not isinstance(raw_slots, Mapping):
            return {}
        normalized: dict[str, Mapping[str, object]] = {}
        for key, value in raw_slots.items():
            if isinstance(key, str) and isinstance(value, Mapping):
                normalized[key] = value
        return normalized

    def _slot_config_for_model_path(self, model_path: str) -> Mapping[str, object] | None:
        candidate = str(model_path or "").strip()
        if not candidate:
            return None
        for env_name in _SLOT_KEY_BY_ENV:
            explicit = self._explicit_descriptor_for_env(env_name, locale=None)
            if explicit is not None and explicit.id == candidate:
                return self._slot_config_for_env(env_name)
            default = self._default_descriptor_for_env(env_name, locale=None)
            if default is not None and default.id == candidate:
                return self._slot_config_for_env(env_name)
        return None

    def _speech_segments_for_utterance(
        self,
        utterance: SpeechUtterance | None,
        *,
        fallback_descriptor: VoiceDescriptor,
    ) -> tuple[_PiperSpeechSegment, ...]:
        current = utterance or SpeechUtterance(text="")
        fallback_slot = self._slot_config_for_model_path(fallback_descriptor.id)
        fallback_segment = _PiperSpeechSegment(
            text=self._prepare_message_for_piper(
                current.text,
                locale=current.locale,
                slot_config=fallback_slot,
            ),
            descriptor=fallback_descriptor,
            slot_config=fallback_slot,
        )
        raw_segments = _split_mixed_language_segments(current.text)
        if len(raw_segments) <= 1:
            return _speech_segments_from_prepared_text(
                fallback_segment.text,
                descriptor=fallback_descriptor,
                slot_config=fallback_slot,
            )

        segments: list[_PiperSpeechSegment] = []
        for language, raw_text in raw_segments:
            locale = _DEFAULT_LOCALE_BY_LANGUAGE.get(language)
            profile = _profile_for_language(current.voice_profile, language)
            descriptor = self._descriptor_for_profile(profile, locale)
            if descriptor is None:
                return (fallback_segment,)
            slot_config = self._slot_config_for_model_path(descriptor.id)
            prepared_text = self._prepare_message_for_piper(
                raw_text,
                locale=locale,
                slot_config=slot_config,
            )
            for prepared_part in _split_prepared_text_on_soft_pause(prepared_text):
                segments.append(
                    _PiperSpeechSegment(
                        text=prepared_part,
                        descriptor=descriptor,
                        slot_config=slot_config,
                    )
                )
        return tuple(segments) if len(segments) > 1 else _speech_segments_from_prepared_text(
            fallback_segment.text,
            descriptor=fallback_descriptor,
            slot_config=fallback_slot,
        )

    def _generate_speech_segment(
        self,
        *,
        binary_path: str,
        segment: _PiperSpeechSegment,
        output_path: Path,
    ) -> TTSResult | None:
        generation_command = [binary_path, "--model", segment.descriptor.id]
        config_path = _model_config_path(segment.descriptor.id)
        if config_path is not None:
            generation_command.extend(["--config", config_path])
        generation_command.extend(_piper_args_from_slot_config(segment.slot_config))
        generation_command.extend(["--output_file", str(output_path)])
        generation = subprocess.run(
            generation_command,
            input=segment.text,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if generation.returncode != 0:
            return TTSResult(
                ok=False,
                error_code="TTS_FAILED",
                error_message=_first_meaningful_line(generation.stderr or generation.stdout)
                or "Local Piper speech generation failed.",
                backend_name=_BACKEND_NAME,
                voice_id=segment.descriptor.id,
            )
        _postprocess_wav_file(output_path, slot_config=segment.slot_config)
        return None

    def _prepare_message_for_piper(
        self,
        message: str,
        *,
        locale: str | None,
        slot_config: Mapping[str, object] | None,
    ) -> str:
        current = str(message or "").strip()
        if not current:
            return current
        current = _ELLIPSIS_RE.sub(". ", current)
        current = _DOUBLE_SENTENCE_BREAK_RE.sub(r"\1 ", current)
        current = _SPACE_BEFORE_PUNCTUATION_RE.sub(r"\1", current)
        current = _DOUBLE_COMMA_RE.sub(", ", current)
        current = _MULTISPACE_RE.sub(" ", current).strip()
        slot_locale = ""
        if isinstance(slot_config, Mapping):
            slot_locale = str(slot_config.get("locale", "") or "").strip()
        language = (
            _language_from_locale(slot_locale)
            or _dominant_language_from_text(current)
            or _language_from_locale(locale)
        )
        if language == "ru":
            current = _prepare_russian_piper_text(current)
        return current.strip()

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


def piper_backend_requested(environ: Mapping[str, str] | None = None) -> bool:
    """Return whether the local Piper backend should be wired into the manager."""
    current = environ or os.environ
    enabled_value = str(current.get("JARVIS_TTS_PIPER_ENABLED", "") or "").strip().lower()
    if enabled_value in {"0", "false", "no", "off"}:
        return False
    if enabled_value in {"1", "true", "yes", "on"}:
        return True
    if any(str(current.get(name, "") or "").strip() for names in _MODEL_ENV_BY_LANGUAGE.values() for name in names):
        return True
    root = _runtime_root_from_environ(current)
    return any((root / slot["path"]).exists() for slot in _DEFAULT_MODEL_SLOT_BY_ENV.values())


def _descriptor_from_model_path(
    model_path: str | None,
    *,
    locale: str | None,
    display_name: str | None = None,
    gender_hint: str | None = None,
) -> VoiceDescriptor | None:
    candidate = str(model_path or "").strip()
    if not candidate:
        return None
    path = Path(candidate).expanduser()
    if not path.exists():
        return None
    metadata = _model_metadata(path)
    resolved_display_name = (
        str(metadata.get("display_name") or "").strip()
        or str(display_name or "").strip()
        or path.stem
    )
    resolved_locale = (
        str(metadata.get("locale") or "").strip()
        or _normalize_locale(locale)
    )
    resolved_gender_hint = (
        str(metadata.get("gender_hint") or "").strip()
        or str(gender_hint or "").strip()
        or None
    )
    resolved_quality_hint = (
        str(metadata.get("quality_hint") or "").strip()
        or "local-model"
    )
    return VoiceDescriptor(
        id=str(path),
        display_name=resolved_display_name,
        locale=resolved_locale,
        gender_hint=resolved_gender_hint,
        quality_hint=resolved_quality_hint,
        source="piper",
    )


def _normalize_locale(locale: str | None) -> str | None:
    normalized = str(locale or "").strip().replace("_", "-")
    return normalized or None


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


def _runtime_root_from_environ(environ: Mapping[str, str]) -> Path:
    override = str(environ.get(_RUNTIME_ROOT_ENV, "") or "").strip()
    if override:
        return Path(override).expanduser()
    return _DEFAULT_RUNTIME_ROOT


def _resolve_binary_candidate(candidate: str) -> str | None:
    value = str(candidate or "").strip()
    if not value:
        return None
    if "/" in value:
        return value if Path(value).expanduser().exists() else None
    return shutil.which(value)


def _model_metadata(model_path: Path) -> dict[str, str]:
    sidecar = _load_model_sidecar(model_path)
    metadata: dict[str, str] = {}
    if sidecar:
        display_name = _sidecar_display_name(sidecar)
        if display_name:
            metadata["display_name"] = display_name
        locale = _sidecar_locale(sidecar)
        if locale:
            metadata["locale"] = locale
        gender_hint = _sidecar_gender_hint(sidecar)
        if gender_hint:
            metadata["gender_hint"] = gender_hint
    quality_hint = _quality_hint_from_filename(model_path.stem)
    if quality_hint:
        metadata["quality_hint"] = quality_hint
    return metadata


def _load_model_sidecar(model_path: Path) -> dict[str, Any]:
    for sidecar_path in (
        Path(f"{model_path}.json"),
        model_path.with_suffix(".json"),
    ):
        try:
            payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, IsADirectoryError, PermissionError, json.JSONDecodeError, OSError):
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def _load_runtime_manifest(runtime_root: Path) -> dict[str, Any]:
    manifest_path = runtime_root / _MANIFEST_RELATIVE_PATH
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, IsADirectoryError, PermissionError, json.JSONDecodeError, OSError):
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _sidecar_display_name(payload: dict[str, Any]) -> str | None:
    for key in ("display_name", "name", "speaker", "speaker_name"):
        value = str(payload.get(key, "") or "").strip()
        if value:
            return value
    speaker_map = payload.get("speaker_id_map")
    if isinstance(speaker_map, dict) and len(speaker_map) == 1:
        return _humanize_name(next(iter(speaker_map)))
    return None


def _sidecar_locale(payload: dict[str, Any]) -> str | None:
    value = payload.get("locale")
    if isinstance(value, str) and value.strip():
        return _normalize_locale(value)
    language = payload.get("language")
    if isinstance(language, str) and language.strip():
        return _normalize_locale(language)
    if isinstance(language, dict):
        for key in ("code", "locale"):
            nested_value = str(language.get(key, "") or "").strip()
            if nested_value:
                return _normalize_locale(nested_value)
    return None


def _sidecar_gender_hint(payload: dict[str, Any]) -> str | None:
    for key in ("gender", "speaker_gender"):
        value = str(payload.get(key, "") or "").strip().lower()
        if value in {"male", "female"}:
            return value
    return None


def _quality_hint_from_filename(stem: str) -> str | None:
    lower_stem = str(stem or "").lower()
    for token in _QUALITY_TOKENS:
        if token in lower_stem:
            return token.replace("_", "-")
    return None


def _humanize_name(raw_value: object) -> str | None:
    candidate = str(raw_value or "").strip().replace("_", " ").replace("-", " ")
    if not candidate:
        return None
    return " ".join(part.capitalize() for part in candidate.split())


def _profile_for_language(profile: str | None, language: str) -> str | None:
    family = _PROFILE_FAMILY_BY_PROFILE.get(str(profile or "").strip(), "any")
    return _PROFILE_BY_LANGUAGE_AND_FAMILY.get((language, family))


def _speech_segments_from_prepared_text(
    prepared_text: str,
    *,
    descriptor: VoiceDescriptor,
    slot_config: Mapping[str, object] | None,
) -> tuple[_PiperSpeechSegment, ...]:
    parts = _split_prepared_text_on_soft_pause(prepared_text)
    return tuple(
        _PiperSpeechSegment(text=part, descriptor=descriptor, slot_config=slot_config)
        for part in parts
    )


def _split_prepared_text_on_soft_pause(prepared_text: str) -> tuple[str, ...]:
    parts = tuple(part.strip() for part in str(prepared_text or "").split(_RU_SOFT_PAUSE_MARKER))
    return tuple(part for part in parts if part)


def _dominant_language_from_text(text: str | None) -> str:
    candidate = _text_without_ru_tech_tokens(str(text or ""))
    first_language = _first_language_signal_from_text(candidate)
    if first_language:
        return first_language
    latin_letters = sum(1 for char in candidate if ("a" <= char.lower() <= "z"))
    cyrillic_letters = sum(1 for char in candidate if _is_cyrillic(char))
    if latin_letters >= max(4, cyrillic_letters + 1):
        return "en"
    if cyrillic_letters >= max(4, latin_letters + 1):
        return "ru"
    return ""


def _first_language_signal_from_text(text: str | None) -> str:
    for match in _LANGUAGE_WORD_RE.finditer(str(text or "")):
        token = match.group(0)
        if any(_is_cyrillic(character) for character in token):
            return "ru"
        if any("a" <= character.lower() <= "z" for character in token):
            normalized = token.lower()
            if normalized in {"ok", "okay"}:
                continue
            return "en"
    return ""


def _is_cyrillic(character: str) -> bool:
    if not character:
        return False
    codepoint = ord(character)
    return 0x0400 <= codepoint <= 0x04FF or 0x0500 <= codepoint <= 0x052F


def _model_config_path(model_path: str | None) -> str | None:
    candidate = str(model_path or "").strip()
    if not candidate:
        return None
    path = Path(candidate).expanduser()
    for config_path in (Path(f"{path}.json"), path.with_suffix(".json")):
        if config_path.exists():
            return str(config_path)
    return None


def _piper_args_from_slot_config(slot_config: Mapping[str, object] | None) -> list[str]:
    if not isinstance(slot_config, Mapping):
        return []
    raw_args = slot_config.get("piper_args")
    if not isinstance(raw_args, Mapping):
        return []
    command_args: list[str] = []
    for key, option in _PIPER_ARG_BY_MANIFEST_KEY.items():
        value = raw_args.get(key)
        if value is None or value == "":
            continue
        command_args.extend([option, str(value)])
    return command_args


def _postprocess_wav_file(path: Path, *, slot_config: Mapping[str, object] | None) -> None:
    options = _audio_postprocess_options(slot_config)
    if not options:
        return
    try:
        with wave.open(str(path), "rb") as reader:
            nchannels = reader.getnchannels()
            sampwidth = reader.getsampwidth()
            framerate = reader.getframerate()
            comptype = reader.getcomptype()
            compname = reader.getcompname()
            frames = reader.readframes(reader.getnframes())
    except (EOFError, wave.Error, OSError):
        return
    if sampwidth != 2 or not frames:
        return

    processed = _apply_pcm16_bass_boost(
        frames,
        nchannels=nchannels,
        framerate=framerate,
        bass_boost=options["bass_boost"],
        bass_cutoff_hz=options["bass_cutoff_hz"],
        output_gain=options["output_gain"],
    )
    if processed == frames:
        return
    output_framerate = max(1, int(round(framerate * options["sample_rate_scale"])))
    try:
        with wave.open(str(path), "wb") as writer:
            writer.setnchannels(nchannels)
            writer.setsampwidth(sampwidth)
            writer.setframerate(output_framerate)
            writer.setcomptype(comptype, compname)
            writer.writeframes(processed)
    except (EOFError, wave.Error, OSError):
        return


def _pad_wav_file_edges(path: Path, *, leading_silence_ms: int, trailing_silence_ms: int) -> None:
    leading_ms = max(0, int(leading_silence_ms))
    trailing_ms = max(0, int(trailing_silence_ms))
    if leading_ms <= 0 and trailing_ms <= 0:
        return
    try:
        with wave.open(str(path), "rb") as reader:
            nchannels = reader.getnchannels()
            sampwidth = reader.getsampwidth()
            framerate = reader.getframerate()
            comptype = reader.getcomptype()
            compname = reader.getcompname()
            frames = reader.readframes(reader.getnframes())
    except (EOFError, wave.Error, OSError):
        return
    if comptype != "NONE" or nchannels <= 0 or sampwidth <= 0 or framerate <= 0 or not frames:
        return

    leading = _pcm_silence_bytes(
        nchannels=nchannels,
        sampwidth=sampwidth,
        framerate=framerate,
        duration_ms=leading_ms,
    )
    trailing = _pcm_silence_bytes(
        nchannels=nchannels,
        sampwidth=sampwidth,
        framerate=framerate,
        duration_ms=trailing_ms,
    )
    try:
        with wave.open(str(path), "wb") as writer:
            writer.setnchannels(nchannels)
            writer.setsampwidth(sampwidth)
            writer.setframerate(framerate)
            writer.setcomptype(comptype, compname)
            writer.writeframes(leading + frames + trailing)
    except (EOFError, wave.Error, OSError):
        return


def _combine_wav_files(
    input_paths: list[Path],
    output_path: Path,
    *,
    inter_segment_silence_ms: int,
) -> bool:
    if not input_paths:
        return False

    target_nchannels: int | None = None
    target_sampwidth: int | None = None
    target_framerate: int | None = None
    combined_frames: list[bytes] = []

    for input_path in input_paths:
        try:
            with wave.open(str(input_path), "rb") as reader:
                nchannels = reader.getnchannels()
                sampwidth = reader.getsampwidth()
                framerate = reader.getframerate()
                comptype = reader.getcomptype()
                frames = reader.readframes(reader.getnframes())
        except (EOFError, wave.Error, OSError):
            return False

        if comptype != "NONE" or nchannels <= 0 or sampwidth != 2 or framerate <= 0 or not frames:
            return False
        if target_nchannels is None:
            target_nchannels = nchannels
            target_sampwidth = sampwidth
            target_framerate = framerate
        if nchannels != target_nchannels or sampwidth != target_sampwidth:
            return False
        if target_framerate is not None and framerate != target_framerate:
            frames = _resample_pcm16_frames(
                frames,
                nchannels=nchannels,
                source_framerate=framerate,
                target_framerate=target_framerate,
            )
        combined_frames.append(frames)

    if target_nchannels is None or target_sampwidth is None or target_framerate is None:
        return False

    silence = _pcm_silence_bytes(
        nchannels=target_nchannels,
        sampwidth=target_sampwidth,
        framerate=target_framerate,
        duration_ms=max(0, int(inter_segment_silence_ms)),
    )
    combined = bytearray()
    for index, frames in enumerate(combined_frames):
        if index > 0:
            combined.extend(silence)
        combined.extend(frames)

    try:
        with wave.open(str(output_path), "wb") as writer:
            writer.setnchannels(target_nchannels)
            writer.setsampwidth(target_sampwidth)
            writer.setframerate(target_framerate)
            writer.writeframes(bytes(combined))
    except (EOFError, wave.Error, OSError):
        return False
    return True


def _resample_pcm16_frames(
    frames: bytes,
    *,
    nchannels: int,
    source_framerate: int,
    target_framerate: int,
) -> bytes:
    if nchannels <= 0 or source_framerate <= 0 or target_framerate <= 0 or source_framerate == target_framerate:
        return frames

    frame_width = nchannels * 2
    source_frame_count = len(frames) // frame_width
    if source_frame_count <= 1:
        return frames

    source_samples = [
        int.from_bytes(frames[index : index + 2], byteorder="little", signed=True)
        for index in range(0, source_frame_count * frame_width, 2)
    ]
    target_frame_count = max(1, int(round(source_frame_count * target_framerate / source_framerate)))
    resampled = bytearray()
    for target_index in range(target_frame_count):
        source_position = min(
            float(source_frame_count - 1),
            target_index * source_framerate / target_framerate,
        )
        left_frame = int(math.floor(source_position))
        right_frame = min(left_frame + 1, source_frame_count - 1)
        fraction = source_position - left_frame
        for channel_index in range(nchannels):
            left_sample = source_samples[(left_frame * nchannels) + channel_index]
            right_sample = source_samples[(right_frame * nchannels) + channel_index]
            sample = int(round(left_sample + ((right_sample - left_sample) * fraction)))
            sample = max(-32768, min(32767, sample))
            resampled.extend(sample.to_bytes(2, byteorder="little", signed=True))
    return bytes(resampled)


def _pcm_silence_bytes(*, nchannels: int, sampwidth: int, framerate: int, duration_ms: int) -> bytes:
    if nchannels <= 0 or sampwidth <= 0 or framerate <= 0 or duration_ms <= 0:
        return b""
    frame_count = int(round(framerate * (duration_ms / 1000.0)))
    return b"\x00" * max(0, frame_count) * nchannels * sampwidth


def _audio_postprocess_options(slot_config: Mapping[str, object] | None) -> dict[str, float]:
    if not isinstance(slot_config, Mapping):
        return {}
    raw_options = slot_config.get("audio_postprocess")
    if not isinstance(raw_options, Mapping):
        return {}
    try:
        bass_boost = float(raw_options.get("bass_boost", 0.0))
        bass_cutoff_hz = float(raw_options.get("bass_cutoff_hz", 0.0))
        output_gain = float(raw_options.get("output_gain", 1.0))
        sample_rate_scale = float(raw_options.get("sample_rate_scale", 1.0))
    except (TypeError, ValueError):
        return {}
    if bass_boost <= 0.0 or bass_cutoff_hz <= 0.0 or output_gain <= 0.0 or sample_rate_scale <= 0.0:
        return {}
    return {
        "bass_boost": bass_boost,
        "bass_cutoff_hz": bass_cutoff_hz,
        "output_gain": output_gain,
        "sample_rate_scale": sample_rate_scale,
    }


def _apply_pcm16_bass_boost(
    frames: bytes,
    *,
    nchannels: int,
    framerate: int,
    bass_boost: float,
    bass_cutoff_hz: float,
    output_gain: float,
) -> bytes:
    if nchannels <= 0 or framerate <= 0:
        return frames
    frame_size = nchannels * 2
    if frame_size <= 0:
        return frames
    total_frames = len(frames) // frame_size
    if total_frames <= 0:
        return frames

    dt = 1.0 / float(framerate)
    rc = 1.0 / max(1.0, 2.0 * math.pi * bass_cutoff_hz)
    alpha = dt / (rc + dt)
    low_state = [0.0] * nchannels
    data = bytearray(frames)
    for frame_index in range(total_frames):
        frame_offset = frame_index * frame_size
        for channel_index in range(nchannels):
            offset = frame_offset + (channel_index * 2)
            sample = int.from_bytes(data[offset : offset + 2], byteorder="little", signed=True)
            low_state[channel_index] += alpha * (sample - low_state[channel_index])
            boosted = (sample + (low_state[channel_index] * bass_boost)) * output_gain
            clamped = max(-32768, min(32767, int(round(boosted))))
            data[offset : offset + 2] = clamped.to_bytes(2, byteorder="little", signed=True)
    return bytes(data)


def _prepare_russian_piper_text(message: str) -> str:
    current = str(message or "").strip()
    if not current:
        return current
    current = _replace_ru_tech_tokens_for_speech(current)
    current = _soften_russian_punctuation_for_piper(current)
    current = current.replace(": ", ". ")
    current = current.replace(";", ",")
    current = _MULTISPACE_RE.sub(" ", current).strip()
    if current and current[-1] not in ".!?":
        current = f"{current}."
    return current


def _soften_russian_punctuation_for_piper(message: str) -> str:
    current = str(message or "").strip()
    if not current:
        return current
    current = _RU_DASH_BREAK_RE.sub(" ", current)
    current = _RU_SOFT_COMMA_AFTER_RE.sub(rf"\g<lead> {_RU_SOFT_PAUSE_MARKER} ", current)
    current = _RU_SOFT_COMMA_BEFORE_RE.sub(f" {_RU_SOFT_PAUSE_MARKER} ", current)
    current = _SPACE_BEFORE_PUNCTUATION_RE.sub(r"\1", current)
    current = _DOUBLE_COMMA_RE.sub(", ", current)
    return _MULTISPACE_RE.sub(" ", current).strip()


def _split_mixed_language_segments(message: str | None) -> tuple[tuple[str, str], ...]:
    current = str(message or "").strip()
    if not current or not any(_is_cyrillic(character) for character in current):
        return ()
    segments: list[tuple[str, str]] = []
    cursor = 0
    for match in _ENGLISH_ISLAND_RE.finditer(current):
        island = str(match.group("island") or "")
        if not _should_split_english_island(island):
            continue
        start, end = match.span("island")
        while end < len(current) and current[end] in ",.;:!?":
            end += 1
        _append_language_segment(segments, "ru", current[cursor:start])
        _append_language_segment(segments, "en", current[start:end])
        cursor = end
    _append_language_segment(segments, "ru", current[cursor:])
    languages = {language for language, text in segments if text.strip()}
    if len(segments) <= 1 or not {"ru", "en"}.issubset(languages):
        return ()
    return tuple(segments)


def _append_language_segment(segments: list[tuple[str, str]], language: str, text: str) -> None:
    normalized_text = str(text or "").strip()
    if not normalized_text:
        return
    if segments and segments[-1][0] == language:
        previous_language, previous_text = segments[-1]
        segments[-1] = (previous_language, f"{previous_text} {normalized_text}".strip())
        return
    segments.append((language, normalized_text))


def _should_split_english_island(island: str) -> bool:
    words = _LATIN_WORD_RE.findall(str(island or ""))
    non_tech_words = [word for word in words if not _is_ru_tech_token(word)]
    if len(non_tech_words) >= 3:
        return True
    return len(non_tech_words) >= 2 and sum(len(word) for word in non_tech_words) >= 14


def _is_ru_tech_token(token: str) -> bool:
    normalized = str(token or "").strip().lower()
    return normalized in {key.lower() for key in _RU_TECH_TOKEN_PRONUNCIATIONS}


def _replace_ru_tech_tokens_for_speech(message: str) -> str:
    current = str(message or "")
    for token in sorted(_RU_TECH_TOKEN_PRONUNCIATIONS, key=len, reverse=True):
        current = _replace_standalone_latin_token(
            current,
            token,
            _RU_TECH_TOKEN_PRONUNCIATIONS[token],
        )
    return current


def _replace_standalone_latin_token(message: str, token: str, replacement: str) -> str:
    pattern = re.compile(
        rf"(?<![A-Za-z0-9_./-]){re.escape(token)}(?![A-Za-z0-9_/-]|\.[A-Za-z0-9])",
        flags=re.IGNORECASE,
    )
    return pattern.sub(replacement, message)


def _text_without_ru_tech_tokens(message: str) -> str:
    current = str(message or "")
    for token in sorted(_RU_TECH_TOKEN_PRONUNCIATIONS, key=len, reverse=True):
        current = _replace_standalone_latin_token(current, token, " ")
    return current
