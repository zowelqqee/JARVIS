"""HTTP transport adapter for OpenAI Responses API calls."""

from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from jarvis_error import ErrorCategory, ErrorCode, JarvisError  # type: ignore  # noqa: E402

_DEFAULT_TIMEOUT_SECONDS = 30.0
_DEFAULT_API_BASE = "https://api.openai.com/v1"
_CA_BUNDLE_ENV = "JARVIS_QA_OPENAI_CA_BUNDLE"
_STD_CA_BUNDLE_ENVS = (_CA_BUNDLE_ENV, "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE")


class OpenAIResponsesTransport:
    """Minimal JSON transport for POST /responses."""

    def create_response(
        self,
        request_payload: dict[str, Any],
        *,
        api_key: str,
        api_base: str | None = None,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        base_url = str(api_base or _DEFAULT_API_BASE).rstrip("/")
        url = f"{base_url}/responses"
        encoded_body = json.dumps(request_payload, ensure_ascii=True).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=encoded_body,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds, context=_ssl_context()) as response:
                response_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace") if exc.fp is not None else ""
            raise JarvisError(
                category=ErrorCategory.ANSWER_ERROR,
                code=ErrorCode.ANSWER_GENERATION_FAILED,
                message=f"OpenAI Responses request failed with HTTP {exc.code}.",
                details={
                    "status_code": exc.code,
                    "body": _truncate(response_body),
                },
                blocking=False,
                terminal=True,
            ) from exc
        except urllib.error.URLError as exc:
            if isinstance(getattr(exc, "reason", None), ssl.SSLCertVerificationError):
                raise JarvisError(
                    category=ErrorCategory.ANSWER_ERROR,
                    code=ErrorCode.ANSWER_GENERATION_FAILED,
                    message=_ssl_cert_error_message(exc.reason),
                    details={
                        "reason": str(exc.reason),
                        "ca_bundle_env": _CA_BUNDLE_ENV,
                        "ca_bundle_path": _ca_bundle_path(),
                    },
                    blocking=False,
                    terminal=True,
                ) from exc
            raise JarvisError(
                category=ErrorCategory.ANSWER_ERROR,
                code=ErrorCode.ANSWER_GENERATION_FAILED,
                message=f"OpenAI Responses request failed: {exc.reason}.",
                details={"reason": str(exc.reason)},
                blocking=False,
                terminal=True,
            ) from exc
        except OSError as exc:
            raise JarvisError(
                category=ErrorCategory.ANSWER_ERROR,
                code=ErrorCode.ANSWER_GENERATION_FAILED,
                message=f"OpenAI Responses transport failed: {exc}.",
                details={"error": str(exc)},
                blocking=False,
                terminal=True,
            ) from exc

        try:
            payload = json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise JarvisError(
                category=ErrorCategory.ANSWER_ERROR,
                code=ErrorCode.ANSWER_GENERATION_FAILED,
                message="OpenAI Responses returned invalid JSON.",
                details={"body": _truncate(response_body)},
                blocking=False,
                terminal=True,
            ) from exc
        if not isinstance(payload, dict):
            raise JarvisError(
                category=ErrorCategory.ANSWER_ERROR,
                code=ErrorCode.ANSWER_GENERATION_FAILED,
                message="OpenAI Responses returned an unexpected payload shape.",
                details={"payload_type": type(payload).__name__},
                blocking=False,
                terminal=True,
            )
        return payload


def _truncate(text: str, *, limit: int = 500) -> str:
    compact = text.strip()
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit]}..."


def _ssl_context() -> ssl.SSLContext:
    ca_bundle_path = _ca_bundle_path()
    if ca_bundle_path:
        return ssl.create_default_context(cafile=ca_bundle_path)
    return ssl.create_default_context()


def _ca_bundle_path(environ: dict[str, str] | None = None) -> str | None:
    env = os.environ if environ is None else environ
    for env_name in _STD_CA_BUNDLE_ENVS:
        bundle_path = str(env.get(env_name, "") or "").strip()
        if bundle_path:
            return bundle_path
    try:
        import certifi
    except ImportError:
        return None
    return str(certifi.where()).strip() or None


def _ssl_cert_error_message(error: ssl.SSLCertVerificationError) -> str:
    return (
        "OpenAI Responses request failed TLS certificate verification. "
        "Retry with a trusted CA bundle via JARVIS_QA_OPENAI_CA_BUNDLE or SSL_CERT_FILE, "
        "or repair the local Python certificate store."
    )
