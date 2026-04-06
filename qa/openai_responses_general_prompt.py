"""Prompt and request-content builders for OpenAI Responses open-domain answers."""

from __future__ import annotations

import json
import uuid
from typing import Any

from qa.general_qa_safety import inspect_general_qa_safety, policy_tags_text
from qa.openai_responses_general_schema import GENERAL_ANSWER_SCHEMA_VERSION

if False:  # pragma: no cover
    from qa.answer_config import AnswerBackendConfig
    from qa.grounding import GroundingBundle
    from types.question_request import QuestionRequest


def build_general_request_metadata(
    *,
    question: QuestionRequest,
    grounding_bundle: GroundingBundle,
    provider: str,
) -> dict[str, str]:
    """Build stable string-only metadata for one open-domain provider request."""
    question_type = getattr(getattr(question, "question_type", None), "value", None)
    policy = inspect_general_qa_safety(getattr(question, "raw_input", ""))
    return _metadata(
        jarvis_mode="question",
        answer_mode="open_domain",
        question_type=question_type,
        grounding_scope=grounding_bundle.scope,
        source_count=len(grounding_bundle.source_paths),
        policy_tags=policy_tags_text(policy),
        policy_response_mode=policy.response_mode,
        policy_warning_hint=policy.warning_hint,
        provider=provider,
        answer_schema_version=GENERAL_ANSWER_SCHEMA_VERSION,
        correlation_id=str(uuid.uuid4()),
    )


def build_general_instructions(*, config: AnswerBackendConfig) -> str:
    """Build the provider instruction block for open-domain read-only answers."""
    strict_text = "strictly follow the JSON schema" if config.llm.strict_mode else "follow the JSON schema"
    return (
        "You are the JARVIS open-domain question backend. Answer the user directly in read-only mode. "
        "Do not claim that you executed commands, clicked UI, opened apps, or changed runtime state. "
        "Do not pretend to quote local docs or local sources because this answer mode is model knowledge, not local grounding. "
        "Follow the Expected boundary, Policy tags, Warning hint, and Policy guidance supplied in the user message. "
        "When Expected boundary is refusal, set answer_kind to refusal and do not return open_domain_model. "
        "If the question depends on current or changing real-world facts, add a short warning that the answer may be out of date. "
        "When a Warning hint is provided for an open_domain_model answer, copy that warning into the warning field verbatim instead of burying it only inside answer_text. "
        "If the request is unsafe or disallowed, return answer_kind refusal with a short refusal answer_text. "
        "For self-harm refusal scenarios, use brief supportive safety language and point the user toward immediate human help or crisis resources mentioned in Policy guidance. "
        f"Return schema_version exactly {GENERAL_ANSWER_SCHEMA_VERSION}. "
        "Keep answer_text concise and under 120 words, and keep warning empty unless it is needed. "
        f"{strict_text}."
    )


def build_general_user_text(question: QuestionRequest, *, grounding_bundle: GroundingBundle) -> str:
    """Build the user-visible prompt content for one open-domain provider request."""
    policy = inspect_general_qa_safety(getattr(question, "raw_input", ""))
    return "\n\n".join(
        section
        for section in (
            _question_section(question),
            _policy_section(policy),
            _answer_follow_up_section(question, grounding_bundle=grounding_bundle),
            "Local grounded sources: none for this answer mode. Do not invent citations.",
            _json_section("Runtime facts", grounding_bundle.runtime_facts),
            _json_section("Session facts", grounding_bundle.session_facts),
        )
        if section
    )


def _question_section(question: QuestionRequest) -> str:
    question_type = getattr(getattr(question, "question_type", None), "value", "question")
    return f"Question type: {question_type}\nQuestion: {getattr(question, 'raw_input', '')}"


def _policy_section(policy) -> str:
    lines = [f"Expected boundary: {policy.response_mode}"]
    if policy.policy_tags:
        lines.append(f"Policy tags: {', '.join(policy.policy_tags)}")
    if policy.warning_hint:
        lines.append(f"Warning hint: {policy.warning_hint}")
    if policy.guidance_lines:
        lines.append("Policy guidance:")
        lines.extend(f"- {line}" for line in policy.guidance_lines)
    return "\n".join(lines)


def _answer_follow_up_section(question: QuestionRequest, *, grounding_bundle: GroundingBundle) -> str:
    question_type = getattr(getattr(question, "question_type", None), "value", getattr(question, "question_type", None))
    if str(question_type or "").strip() != "answer_follow_up":
        return ""

    raw_context_refs = getattr(question, "context_refs", {}) or {}
    context_refs = raw_context_refs if isinstance(raw_context_refs, dict) else {}
    recent_answer_context = dict((grounding_bundle.session_facts or {}).get("recent_answer_context", {}) or {})
    if not recent_answer_context:
        return ""

    follow_up_kind = str(context_refs.get("follow_up_kind", "") or "").strip()
    answer_kind = str(recent_answer_context.get("answer_kind", "") or "").strip()
    answer_provenance = str(recent_answer_context.get("answer_provenance", "") or "").strip()
    answer_warning = str(recent_answer_context.get("answer_warning", "") or "").strip()
    answer_text = str(recent_answer_context.get("answer_text", "") or "").strip()
    uses_model_knowledge = answer_kind == "open_domain_model" or answer_provenance == "model_knowledge"

    lines: list[str] = []
    if uses_model_knowledge:
        lines.append("This follow-up continues the previous model-knowledge answer, not a new unrelated question.")
        lines.append("Use recent_answer_context.answer_text as the anchor and answer directly instead of asking what the user wants explained.")
        lines.append("Keep the same topic unless the user explicitly changes it.")
        if follow_up_kind == "explain_more":
            lines.append("For explain_more, provide a fuller explanation of the same subject with extra detail, context, or examples.")
        elif follow_up_kind == "why":
            lines.append("For why follow-ups, explain the reasoning behind the previous answer directly.")
        if answer_text:
            lines.append(f"Recent answer anchor: {answer_text}")
        if answer_warning:
            lines.append("If the recent answer already carried a warning, preserve that warning unless the safety boundary changes.")
        lines.append("Do not ask a clarification question unless the recent answer context is actually missing or unusable.")
        lines.append("Do not invent citations or claim grounded local sources for this follow-up.")
    if not lines:
        return ""
    return "Question-specific follow-up guidance:\n" + "\n".join(f"- {line}" for line in lines)


def _json_section(title: str, data: dict[str, Any]) -> str:
    if not data:
        return ""
    return f"{title}:\n{json.dumps(data, sort_keys=True, ensure_ascii=True)}"


def _metadata(**values: object) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for key, value in values.items():
        if value is None:
            continue
        normalized = str(value).strip()
        if normalized:
            metadata[key] = normalized
    return metadata
