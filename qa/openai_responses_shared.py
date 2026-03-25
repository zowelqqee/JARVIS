"""Shared low-level helpers for OpenAI Responses request/response handling."""

from __future__ import annotations

from typing import Any


def extract_response_output(response_payload: dict[str, Any]) -> tuple[str | None, list[str]]:
    """Return assistant output text plus any refusal chunks discovered in the payload."""
    direct_output_text = str(response_payload.get("output_text", "") or "").strip()
    if direct_output_text:
        return direct_output_text, []

    response_output = list(response_payload.get("output", []) or [])
    text_chunks: list[str] = []
    refusal_chunks: list[str] = []
    for item in response_output:
        if not isinstance(item, dict):
            continue
        if str(item.get("type", "")) != "message":
            continue
        if str(item.get("role", "")) != "assistant":
            continue
        for content_item in list(item.get("content", []) or []):
            if not isinstance(content_item, dict):
                continue
            content_type = str(content_item.get("type", "") or "")
            if content_type == "output_text":
                text = str(content_item.get("text", "") or "").strip()
                if text:
                    text_chunks.append(text)
            elif content_type == "refusal":
                refusal = str(content_item.get("refusal", "") or "").strip()
                if refusal:
                    refusal_chunks.append(refusal)

    if text_chunks:
        return "\n".join(text_chunks).strip(), refusal_chunks
    return None, refusal_chunks


def response_debug_details(response_payload: dict[str, Any]) -> dict[str, Any]:
    """Return the safe provider debug fields carried back from transport."""
    raw_debug = response_payload.get("_jarvis_debug")
    if not isinstance(raw_debug, dict):
        return {}
    allowed_keys = ("provider", "request_id", "correlation_id", "status_code", "retryable")
    return {
        key: raw_debug[key]
        for key in allowed_keys
        if raw_debug.get(key) not in (None, "")
    }


def response_usage_summary(response_payload: dict[str, Any]) -> dict[str, Any]:
    """Return the safe token-usage summary when the provider returned it."""
    usage = dict(response_payload.get("usage", {}) or {})
    summary: dict[str, Any] = {}
    for source_key, target_key in (
        ("input_tokens", "input_tokens"),
        ("output_tokens", "output_tokens"),
        ("total_tokens", "total_tokens"),
    ):
        value = usage.get(source_key)
        if isinstance(value, int) and value >= 0:
            summary[target_key] = value
    return summary
