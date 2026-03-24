"""Configuration and env loading for question-answer backends."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Mapping

from qa.answer_backend import AnswerBackendKind
from qa.llm_provider import LlmProviderKind

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from jarvis_error import ErrorCategory, ErrorCode, JarvisError  # type: ignore  # noqa: E402

_ENV_BACKEND = "JARVIS_QA_BACKEND"
_ENV_LLM_ENABLED = "JARVIS_QA_LLM_ENABLED"
_ENV_LLM_PROVIDER = "JARVIS_QA_LLM_PROVIDER"
_ENV_LLM_MODEL = "JARVIS_QA_LLM_MODEL"
_ENV_LLM_API_BASE = "JARVIS_QA_LLM_API_BASE"
_ENV_LLM_API_KEY_ENV = "JARVIS_QA_LLM_API_KEY_ENV"
_ENV_LLM_FALLBACK_ENABLED = "JARVIS_QA_LLM_FALLBACK_ENABLED"
_ENV_LLM_TIMEOUT_SECONDS = "JARVIS_QA_LLM_TIMEOUT_SECONDS"
_ENV_LLM_MAX_OUTPUT_TOKENS = "JARVIS_QA_LLM_MAX_OUTPUT_TOKENS"
_ENV_LLM_STRICT_MODE = "JARVIS_QA_LLM_STRICT_MODE"
_ENV_LLM_MAX_RETRIES = "JARVIS_QA_LLM_MAX_RETRIES"
_ENV_LLM_REASONING_EFFORT = "JARVIS_QA_LLM_REASONING_EFFORT"
_DEFAULT_OPENAI_MODEL = "gpt-5-nano"
_DEFAULT_TIMEOUT_SECONDS = 30.0
_DEFAULT_MAX_OUTPUT_TOKENS = 800
_DEFAULT_MAX_RETRIES = 1
_DEFAULT_REASONING_EFFORT = "minimal"


@dataclass(slots=True, frozen=True)
class LlmBackendConfig:
    """Model-backed answer settings kept behind an explicit feature flag."""

    enabled: bool = False
    provider: LlmProviderKind = LlmProviderKind.OPENAI_RESPONSES
    model: str = _DEFAULT_OPENAI_MODEL
    api_key_env: str = "OPENAI_API_KEY"
    api_base: str | None = None
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS
    max_output_tokens: int = _DEFAULT_MAX_OUTPUT_TOKENS
    reasoning_effort: str = _DEFAULT_REASONING_EFFORT
    strict_mode: bool = True
    max_retries: int = _DEFAULT_MAX_RETRIES
    fallback_enabled: bool = True


@dataclass(slots=True, frozen=True)
class AnswerBackendConfig:
    """Resolved answer backend configuration."""

    backend_kind: AnswerBackendKind = AnswerBackendKind.DETERMINISTIC
    llm: LlmBackendConfig = field(default_factory=LlmBackendConfig)

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "AnswerBackendConfig":
        """Load answer backend settings from environment variables."""
        env = dict(os.environ if environ is None else environ)
        backend_kind = _parse_backend_kind(env.get(_ENV_BACKEND, AnswerBackendKind.DETERMINISTIC.value))
        llm_enabled = _parse_bool(env.get(_ENV_LLM_ENABLED), env_name=_ENV_LLM_ENABLED, default=False)
        llm_provider = _parse_provider_kind(env.get(_ENV_LLM_PROVIDER, LlmProviderKind.OPENAI_RESPONSES.value))
        llm_model = str(env.get(_ENV_LLM_MODEL, _DEFAULT_OPENAI_MODEL) or _DEFAULT_OPENAI_MODEL).strip() or _DEFAULT_OPENAI_MODEL
        llm_api_base = str(env.get(_ENV_LLM_API_BASE, "") or "").strip() or None
        llm_api_key_env = str(env.get(_ENV_LLM_API_KEY_ENV, "OPENAI_API_KEY") or "OPENAI_API_KEY").strip() or "OPENAI_API_KEY"
        llm_timeout_seconds = _parse_positive_float(
            env.get(_ENV_LLM_TIMEOUT_SECONDS),
            env_name=_ENV_LLM_TIMEOUT_SECONDS,
            default=_DEFAULT_TIMEOUT_SECONDS,
        )
        llm_max_output_tokens = _parse_non_negative_int(
            env.get(_ENV_LLM_MAX_OUTPUT_TOKENS),
            env_name=_ENV_LLM_MAX_OUTPUT_TOKENS,
            default=_DEFAULT_MAX_OUTPUT_TOKENS,
        )
        llm_reasoning_effort = _parse_reasoning_effort(
            env.get(_ENV_LLM_REASONING_EFFORT),
            env_name=_ENV_LLM_REASONING_EFFORT,
            default=_DEFAULT_REASONING_EFFORT,
        )
        llm_strict_mode = _parse_bool(
            env.get(_ENV_LLM_STRICT_MODE),
            env_name=_ENV_LLM_STRICT_MODE,
            default=True,
        )
        llm_max_retries = _parse_non_negative_int(
            env.get(_ENV_LLM_MAX_RETRIES),
            env_name=_ENV_LLM_MAX_RETRIES,
            default=_DEFAULT_MAX_RETRIES,
        )
        llm_fallback_enabled = _parse_bool(
            env.get(_ENV_LLM_FALLBACK_ENABLED),
            env_name=_ENV_LLM_FALLBACK_ENABLED,
            default=True,
        )
        return cls(
            backend_kind=backend_kind,
            llm=LlmBackendConfig(
                enabled=llm_enabled,
                provider=llm_provider,
                model=llm_model,
                api_key_env=llm_api_key_env,
                api_base=llm_api_base,
                timeout_seconds=llm_timeout_seconds,
                max_output_tokens=llm_max_output_tokens,
                reasoning_effort=llm_reasoning_effort,
                strict_mode=llm_strict_mode,
                max_retries=llm_max_retries,
                fallback_enabled=llm_fallback_enabled,
            ),
        )

    def with_backend_kind(self, backend_kind: AnswerBackendKind | str | None) -> "AnswerBackendConfig":
        """Return a config with an explicit backend override when one is provided."""
        if backend_kind is None:
            return self
        kind_value = getattr(backend_kind, "value", backend_kind)
        return replace(self, backend_kind=_parse_backend_kind(kind_value))


def load_answer_backend_config(environ: Mapping[str, str] | None = None) -> AnswerBackendConfig:
    """Convenience wrapper used by callers that load config lazily."""
    return AnswerBackendConfig.from_env(environ=environ)


def _parse_backend_kind(raw_value: str) -> AnswerBackendKind:
    value = str(raw_value or "").strip() or AnswerBackendKind.DETERMINISTIC.value
    try:
        return AnswerBackendKind(value)
    except ValueError as exc:
        raise _config_error(
            env_name=_ENV_BACKEND,
            raw_value=value,
            message="Unknown answer backend configuration value.",
        ) from exc


def _parse_provider_kind(raw_value: str) -> LlmProviderKind:
    value = str(raw_value or "").strip() or LlmProviderKind.OPENAI_RESPONSES.value
    try:
        return LlmProviderKind(value)
    except ValueError as exc:
        raise _config_error(
            env_name=_ENV_LLM_PROVIDER,
            raw_value=value,
            message="Unknown LLM provider configuration value.",
        ) from exc


def _parse_bool(raw_value: str | None, *, env_name: str, default: bool) -> bool:
    if raw_value is None:
        return default
    value = str(raw_value).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise _config_error(env_name=env_name, raw_value=str(raw_value), message="Boolean config value is invalid.")


def _parse_positive_float(raw_value: str | None, *, env_name: str, default: float) -> float:
    if raw_value is None:
        return default
    try:
        value = float(str(raw_value).strip())
    except ValueError as exc:
        raise _config_error(env_name=env_name, raw_value=str(raw_value), message="Numeric config value is invalid.") from exc
    if value <= 0:
        raise _config_error(env_name=env_name, raw_value=str(raw_value), message="Numeric config value must be positive.")
    return value


def _parse_non_negative_int(raw_value: str | None, *, env_name: str, default: int) -> int:
    if raw_value is None:
        return default
    try:
        value = int(str(raw_value).strip())
    except ValueError as exc:
        raise _config_error(env_name=env_name, raw_value=str(raw_value), message="Integer config value is invalid.") from exc
    if value < 0:
        raise _config_error(env_name=env_name, raw_value=str(raw_value), message="Integer config value must be non-negative.")
    return value


def _parse_reasoning_effort(raw_value: str | None, *, env_name: str, default: str) -> str:
    if raw_value is None:
        return default
    value = str(raw_value).strip().lower()
    if value in {"none", "minimal", "low", "medium", "high", "xhigh"}:
        return value
    raise _config_error(env_name=env_name, raw_value=str(raw_value), message="Reasoning effort config value is invalid.")


def _config_error(*, env_name: str, raw_value: str, message: str) -> JarvisError:
    return JarvisError(
        category=ErrorCategory.ANSWER_ERROR,
        code=ErrorCode.MODEL_BACKEND_UNAVAILABLE,
        message=f"{message} {env_name}={raw_value!r}.",
        details={"env": env_name, "value": raw_value},
        blocking=False,
        terminal=True,
    )
