"""Pure presentation helpers for top-level interaction results."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from interaction_kind import InteractionKind, interaction_kind_value  # type: ignore  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[1]


def interaction_output_lines(result: object) -> list[str]:
    """Return deterministic CLI output lines for a top-level interaction result."""
    mode = _interaction_mode_value(result)
    visibility = _interaction_visibility(result)

    if mode == InteractionKind.QUESTION.value:
        return _question_output_lines(result=result, visibility=visibility)

    if mode == InteractionKind.CLARIFICATION.value:
        return _clarification_output_lines(result=result, visibility=visibility)

    return _command_output_lines(visibility)


def interaction_speech_message(result: object) -> str | None:
    """Return the single top-level interaction message worth speaking."""
    mode = _interaction_mode_value(result)
    visibility = _interaction_visibility(result)

    if mode == InteractionKind.QUESTION.value:
        summary = _question_summary(result=result, visibility=visibility)
        if summary:
            warning = str(visibility.get("answer_warning", "") or "").strip()
            if not warning:
                answer_result = getattr(result, "answer_result", None)
                warning = str(getattr(answer_result, "warning", "") or "").strip()
            if warning:
                return f"{summary} Warning: {warning}"
            return summary
        answer_text = str(visibility.get("answer_text", "") or "").strip()
        if not answer_text:
            answer_result = getattr(result, "answer_result", None)
            answer_text = str(getattr(answer_result, "answer_text", "") or "").strip()
        if answer_text:
            return answer_text
        failure_message = str(visibility.get("failure_message", "") or "").strip()
        if not failure_message:
            error = getattr(result, "error", None)
            failure_message = _interaction_error_message(error) if error is not None else ""
        return failure_message or None

    if mode == InteractionKind.CLARIFICATION.value:
        clarification_question = str(visibility.get("clarification_question", "") or "").strip()
        if not clarification_question:
            clarification_request = getattr(result, "clarification_request", None)
            clarification_question = str(getattr(clarification_request, "message", "") or "").strip()
        if clarification_question:
            return clarification_question
        failure_message = str(visibility.get("failure_message", "") or "").strip()
        if not failure_message:
            error = getattr(result, "error", None)
            failure_message = _interaction_error_message(error) if error is not None else ""
        return failure_message or None

    return _command_speech_message(visibility)


def _question_output_lines(*, result: object, visibility: dict[str, Any]) -> list[str]:
    lines = [f"mode: {visibility.get('interaction_mode', InteractionKind.QUESTION.value)}"]

    answer_summary = _question_summary(result=result, visibility=visibility)
    if answer_summary:
        lines.append(f"summary: {answer_summary}")

    answer_text = str(visibility.get("answer_text", "") or "").strip()
    if not answer_text:
        answer_result = getattr(result, "answer_result", None)
        answer_text = str(getattr(answer_result, "answer_text", "") or "").strip()
    if answer_text and answer_text != answer_summary:
        lines.append(f"answer: {answer_text}")

    sources = list(visibility.get("answer_sources", []) or [])
    if not sources:
        answer_result = getattr(result, "answer_result", None)
        sources = list(getattr(answer_result, "sources", []) or [])

    answer_kind = str(visibility.get("answer_kind", "") or "").strip()
    answer_provenance = str(visibility.get("answer_provenance", "") or "").strip()
    should_show_taxonomy = bool(answer_kind or answer_provenance) and (answer_kind != "grounded_local" or not sources)
    if should_show_taxonomy and answer_kind:
        lines.append(f"answer-kind: {answer_kind}")
    if should_show_taxonomy and answer_provenance:
        lines.append(f"provenance: {answer_provenance}")

    source_labels = list(visibility.get("answer_source_labels", []) or [])
    if not source_labels and sources:
        source_labels = [_source_label(source) for source in sources]
    if source_labels:
        lines.append(f"sources: {', '.join(str(label) for label in source_labels)}")
    if sources:
        lines.append(f"paths: {', '.join(str(source) for source in sources)}")

    source_attributions = _question_source_attributions(result=result, visibility=visibility)
    source_label_map = _source_label_map(sources, source_labels)
    for attribution in source_attributions:
        source_name = source_label_map.get(attribution["source"], attribution["source"])
        lines.append(f"evidence: {source_name} -> {attribution['support']}")

    warning = str(visibility.get("answer_warning", "") or "").strip()
    if not warning:
        answer_result = getattr(result, "answer_result", None)
        warning = str(getattr(answer_result, "warning", "") or "").strip()
    if warning:
        lines.append(f"warning: {warning}")

    failure_message = str(visibility.get("failure_message", "") or "").strip()
    if not failure_message:
        error = getattr(result, "error", None)
        failure_message = _interaction_error_message(error) if error is not None else ""
    if failure_message:
        lines.append(f"error: {failure_message}")

    return lines


def _clarification_output_lines(*, result: object, visibility: dict[str, Any]) -> list[str]:
    lines = [f"mode: {visibility.get('interaction_mode', InteractionKind.CLARIFICATION.value)}"]

    clarification_question = str(visibility.get("clarification_question", "") or "").strip()
    if not clarification_question:
        clarification_request = getattr(result, "clarification_request", None)
        clarification_question = str(getattr(clarification_request, "message", "") or "").strip()
    if clarification_question:
        lines.append(f"clarify: {clarification_question}")

    failure_message = str(visibility.get("failure_message", "") or "").strip()
    if not failure_message:
        error = getattr(result, "error", None)
        failure_message = _interaction_error_message(error) if error is not None else ""
    if failure_message:
        lines.append(f"error: {failure_message}")

    return lines


def _command_output_lines(visibility: dict[str, Any]) -> list[str]:
    runtime_state = visibility.get("runtime_state") or "idle"
    lines = [f"state: {runtime_state}"]

    command_summary = visibility.get("command_summary")
    if command_summary:
        lines.append(f"command: {command_summary}")

    current_step = visibility.get("current_step")
    if current_step:
        lines.append(f"current: {current_step}")

    completed_steps = list(visibility.get("completed_steps", []) or [])
    if completed_steps:
        lines.append(f"done: {', '.join(str(step) for step in completed_steps)}")

    blocked_reason = visibility.get("blocked_reason")
    clarification_question = visibility.get("clarification_question")
    confirmation_request = visibility.get("confirmation_request")

    if blocked_reason and blocked_reason != clarification_question and (
        not confirmation_request or blocked_reason != confirmation_request.get("message")
    ):
        lines.append(f"blocked: {blocked_reason}")

    if clarification_question:
        lines.append(f"clarify: {clarification_question}")

    if confirmation_request:
        lines.append(f"confirm: {confirmation_request.get('message')}")

    failure_message = visibility.get("failure_message")
    if failure_message:
        lines.append(f"error: {failure_message}")

    completion_result = visibility.get("completion_result")
    if completion_result:
        lines.append(f"result: {completion_result}")

    return lines


def _question_source_attributions(*, result: object, visibility: dict[str, Any]) -> list[dict[str, str]]:
    source_attributions = list(visibility.get("answer_source_attributions", []) or [])
    if source_attributions:
        return [
            {
                "source": str(attribution.get("source", "")).strip(),
                "support": str(attribution.get("support", "")).strip(),
            }
            for attribution in source_attributions
            if str(attribution.get("source", "")).strip() and str(attribution.get("support", "")).strip()
        ]

    answer_result = getattr(result, "answer_result", None)
    fallback_attributions: list[dict[str, str]] = []
    for attribution in list(getattr(answer_result, "source_attributions", []) or []):
        source = str(getattr(attribution, "source", "") or "").strip()
        support = str(getattr(attribution, "support", "") or "").strip()
        if source and support:
            fallback_attributions.append({"source": source, "support": support})
    return fallback_attributions


def _question_summary(*, result: object, visibility: dict[str, Any]) -> str:
    summary = str(visibility.get("answer_summary", "") or "").strip()
    if summary:
        return summary
    answer_text = str(visibility.get("answer_text", "") or "").strip()
    if not answer_text:
        answer_result = getattr(result, "answer_result", None)
        answer_text = str(getattr(answer_result, "answer_text", "") or "").strip()
    return _answer_summary(answer_text)


def _source_label_map(sources: list[str], labels: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for source, label in zip(sources, labels):
        source_text = str(source).strip()
        label_text = str(label).strip()
        if source_text and label_text:
            result[source_text] = label_text
    return result


def _source_label(source: str) -> str:
    raw_source = str(source or "").strip()
    if not raw_source:
        return ""
    source_path = Path(raw_source)
    try:
        relative_source = source_path.resolve().relative_to(_REPO_ROOT)
    except (ValueError, OSError):
        relative_source = Path(source_path.name or raw_source)
    label_seed = relative_source.stem or relative_source.name or raw_source
    words = str(label_seed).replace("_", " ").replace("-", " ").split()
    if not words:
        return raw_source
    return " ".join(word.capitalize() for word in words)


def _answer_summary(answer_text: str) -> str:
    normalized = " ".join(str(answer_text or "").split()).strip()
    if not normalized:
        return ""
    for punctuation in (". ", "! ", "? "):
        split_index = normalized.find(punctuation)
        if 0 < split_index <= 110:
            return normalized[: split_index + 1].strip()
    if len(normalized) <= 110:
        return normalized
    clipped = normalized[:107].rsplit(" ", 1)[0].strip() or normalized[:107].strip()
    return f"{clipped}..."


def _command_speech_message(visibility: dict[str, Any]) -> str | None:
    clarification_question = visibility.get("clarification_question")
    if clarification_question:
        return str(clarification_question)

    confirmation_request = visibility.get("confirmation_request")
    if isinstance(confirmation_request, dict):
        message = confirmation_request.get("message")
        if message:
            return str(message)

    failure_message = visibility.get("failure_message")
    if failure_message:
        return str(failure_message)

    completion_result = visibility.get("completion_result")
    if completion_result:
        return str(completion_result)

    return None


def _interaction_visibility(result: object) -> dict[str, Any]:
    result_visibility = dict(getattr(result, "visibility", {}) or {})
    if result_visibility:
        return result_visibility

    runtime_result = getattr(result, "runtime_result", None)
    runtime_visibility = dict(getattr(runtime_result, "visibility", {}) or {})
    if runtime_visibility:
        return runtime_visibility

    return {}


def _interaction_mode_value(result: object) -> str:
    interaction_mode = getattr(result, "interaction_mode", "")
    return interaction_kind_value(interaction_mode).strip()


def _interaction_error_message(error: object) -> str:
    code = str(getattr(getattr(error, "code", ""), "value", getattr(error, "code", ""))).strip()
    message = str(getattr(error, "message", "")).strip()
    if code and message:
        return f"{code}: {message}"
    return message or code
