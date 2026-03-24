"""Shared grounding verification and attribution helpers for QA backends."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from answer_result import AnswerResult, AnswerSourceAttribution  # type: ignore  # noqa: E402
from jarvis_error import ErrorCategory, ErrorCode, JarvisError  # type: ignore  # noqa: E402


_GENERIC_SUPPORT_TEXTS = {
    "grounding source used for this answer.",
    "documentation grounding source for this answer.",
    "capability metadata grounding source for this answer.",
    "session context grounding source for this answer.",
    "runtime visibility grounding source for this answer.",
    "supported by source.",
    "source support.",
    "unsupported source.",
}


@dataclass(slots=True)
class VerifiedGroundedAnswer:
    """Normalized grounded answer facts after verification."""

    answer_text: str
    sources: list[str]
    source_attributions: list[AnswerSourceAttribution]
    warning: str | None = None


def ensure_source_attributions(answer_result: AnswerResult) -> AnswerResult:
    """Populate generic per-source attributions when a backend returned only sources."""
    if getattr(answer_result, "source_attributions", None):
        return answer_result
    sources = [str(source).strip() for source in list(getattr(answer_result, "sources", []) or []) if str(source).strip()]
    if not sources:
        return answer_result
    answer_result.source_attributions = [
        AnswerSourceAttribution(source=source, support=generic_source_support(source))
        for source in sources
    ]
    return answer_result


def parse_source_attributions(raw_source_attributions: list[Any]) -> list[AnswerSourceAttribution]:
    """Parse provider-specific source attribution payloads into the shared contract."""
    parsed: list[AnswerSourceAttribution] = []
    for entry in raw_source_attributions:
        if not isinstance(entry, dict):
            raise _grounding_error(
                code=ErrorCode.ANSWER_GENERATION_FAILED,
                message="Structured answer source attribution is not an object.",
                details={"entry": entry},
            )
        source = str(entry.get("source", "") or "").strip()
        support = str(entry.get("support", "") or "").strip()
        if not source or not support:
            raise _grounding_error(
                code=ErrorCode.ANSWER_NOT_GROUNDED,
                message="Structured answer source attribution is missing source or support text.",
                details={"entry": entry},
            )
        parsed.append(AnswerSourceAttribution(source=source, support=support))
    return parsed


def verify_grounded_answer(
    *,
    answer_text: str,
    source_attributions: list[AnswerSourceAttribution],
    allowed_sources: list[str],
    grounded: bool,
    warning_text: str | None = None,
    details: dict[str, Any] | None = None,
) -> VerifiedGroundedAnswer:
    """Apply provider-agnostic grounding policy to one candidate answer."""
    normalized_answer_text = str(answer_text or "").strip()
    normalized_warning = str(warning_text or "").strip() or None
    if not normalized_answer_text:
        raise _grounding_error(
            code=ErrorCode.ANSWER_GENERATION_FAILED,
            message="Structured answer payload is missing answer_text.",
            details=details,
        )
    if not grounded:
        raise _grounding_error(
            code=ErrorCode.ANSWER_NOT_GROUNDED,
            message=normalized_warning or "Model indicated that grounding was insufficient.",
            details=details,
        )
    if not source_attributions:
        raise _grounding_error(
            code=ErrorCode.ANSWER_NOT_GROUNDED,
            message="Model answer did not declare which grounded sources it used.",
            details=details,
        )

    allowed_source_set = {str(source).strip() for source in allowed_sources if str(source).strip()}
    used_sources = _deduped_sources(source_attributions)
    if any(source not in allowed_source_set for source in used_sources):
        raise _grounding_error(
            code=ErrorCode.ANSWER_NOT_GROUNDED,
            message="Model answer referenced sources outside the allowed grounding bundle.",
            details={
                "used_sources": used_sources,
                "allowed_sources": list(allowed_source_set),
                **(details or {}),
            },
        )
    for attribution in source_attributions:
        if not support_is_meaningful(attribution.support, source=attribution.source):
            raise _grounding_error(
                code=ErrorCode.ANSWER_NOT_GROUNDED,
                message="Model answer included weak or generic source support text.",
                details={
                    "attribution": {
                        "source": attribution.source,
                        "support": attribution.support,
                    },
                    **(details or {}),
                },
            )
    if implies_execution(normalized_answer_text):
        raise _grounding_error(
            code=ErrorCode.ANSWER_NOT_GROUNDED,
            message="Model answer implied command execution in question mode.",
            details={"answer_text": normalized_answer_text, **(details or {})},
        )
    return VerifiedGroundedAnswer(
        answer_text=normalized_answer_text,
        sources=used_sources,
        source_attributions=source_attributions,
        warning=normalized_warning,
    )


def generic_source_support(source: str) -> str:
    """Return a short generic support statement for deterministic sources."""
    normalized = str(source or "").replace("\\", "/")
    if "/docs/" in normalized:
        return "Documentation grounding source for this answer."
    if normalized.endswith("qa/capability_catalog.py"):
        return "Capability metadata grounding source for this answer."
    if normalized.endswith("context/session_context.py"):
        return "Session context grounding source for this answer."
    if "/runtime/" in normalized or normalized.endswith("ui/visibility_mapper.py"):
        return "Runtime visibility grounding source for this answer."
    return "Grounding source used for this answer."


def support_is_meaningful(support: str, *, source: str | None = None) -> bool:
    """Return whether support text is specific enough for model-backed evidence."""
    normalized = " ".join(str(support or "").split()).strip()
    if not normalized:
        return False
    lowered = normalized.lower()
    if lowered in _GENERIC_SUPPORT_TEXTS:
        return False
    if source and normalized == str(source).strip():
        return False
    if "/" in normalized and " " not in normalized:
        return False
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9'_-]*", normalized)
    if len(tokens) < 3:
        return False
    if len(normalized) < 12:
        return False
    return True


def implies_execution(answer_text: str) -> bool:
    """Return whether answer text incorrectly implies command execution happened."""
    lowered = str(answer_text or "").lower()
    phrases = (
        "i opened ",
        "i launched ",
        "i ran ",
        "i executed ",
        "i clicked ",
        "i closed ",
        "i started ",
    )
    return any(phrase in lowered for phrase in phrases)


def _deduped_sources(source_attributions: list[AnswerSourceAttribution]) -> list[str]:
    return list(dict.fromkeys(attribution.source for attribution in source_attributions))


def _grounding_error(*, code: ErrorCode, message: str, details: dict[str, Any] | None) -> JarvisError:
    return JarvisError(
        category=ErrorCategory.ANSWER_ERROR,
        code=code,
        message=message,
        details=details,
        blocking=False,
        terminal=True,
    )
