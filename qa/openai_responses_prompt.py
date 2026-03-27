"""Prompt and request-content builders for OpenAI Responses QA answers."""

from __future__ import annotations

import json
import uuid
from typing import Any

from qa.openai_responses_schema import ANSWER_SCHEMA_VERSION

if False:  # pragma: no cover
    from qa.answer_config import AnswerBackendConfig
    from qa.grounding import GroundingBundle
    from types.question_request import QuestionRequest


def build_request_metadata(
    *,
    question: QuestionRequest,
    grounding_bundle: GroundingBundle,
    provider: str,
) -> dict[str, str]:
    """Build stable string-only metadata for one provider request."""
    question_type = getattr(getattr(question, "question_type", None), "value", None)
    return _metadata(
        jarvis_mode="question",
        question_type=question_type,
        grounding_scope=grounding_bundle.scope,
        source_count=len(grounding_bundle.source_paths),
        provider=provider,
        answer_schema_version=ANSWER_SCHEMA_VERSION,
        correlation_id=str(uuid.uuid4()),
    )


def build_instructions(*, config: AnswerBackendConfig) -> str:
    """Build the provider instruction block for grounded structured answers."""
    strict_text = "strictly follow the JSON schema" if config.llm.strict_mode else "follow the JSON schema"
    return (
        "You are the JARVIS answer backend. Answer only from the provided local grounding bundle, do not invent sources, "
        "and do not imply that any command was executed. If grounding is insufficient, set grounded to false and explain that in warning. "
        "If the supplied Runtime facts or Session facts directly answer the question, use those concrete values explicitly instead of replacing them with a generic summary. "
        f"Return schema_version exactly {ANSWER_SCHEMA_VERSION}. "
        "Keep answer_text concise but complete, usually 1 to 4 short sentences. "
        "Use enough source_attributions to support each distinct claim in answer_text; do not artificially cap citations when multiple grounded sources are materially relevant. "
        "In each source_attributions.source field, return only the raw source path, not the annotated kind/section text. "
        f"Keep each support field to one short factual sentence, and {strict_text}."
    )


def build_user_text(question: QuestionRequest, *, grounding_bundle: GroundingBundle) -> str:
    """Build the user-visible grounding bundle section for one provider request."""
    prompt_source_lines = [_source_line(source) for source in grounding_bundle.sources]
    return "\n\n".join(
        section for section in (
            _question_section(question),
            _question_guidance_section(question, grounding_bundle=grounding_bundle),
            _sources_section(prompt_source_lines),
            _notes_section(grounding_bundle.source_notes),
            _json_section("Runtime facts", grounding_bundle.runtime_facts),
            _json_section("Session facts", grounding_bundle.session_facts),
        )
        if section
    )


def _question_section(question: QuestionRequest) -> str:
    question_type = getattr(getattr(question, "question_type", None), "value", "question")
    return f"Question type: {question_type}\nQuestion: {getattr(question, 'raw_input', '')}"


def _sources_section(source_lines: list[str]) -> str:
    if not source_lines:
        return "Allowed local sources: none"
    rendered = "\n".join(f"- {line}" for line in source_lines)
    return f"Allowed local sources:\n{rendered}"


def _notes_section(source_notes: list[str]) -> str:
    if not source_notes:
        return ""
    note_lines = "\n".join(f"- {note}" for note in source_notes)
    return f"Grounding rules:\n{note_lines}"


def _question_guidance_section(question: QuestionRequest, *, grounding_bundle: GroundingBundle) -> str:
    question_type = getattr(getattr(question, "question_type", None), "value", getattr(question, "question_type", None))
    lowered = str(getattr(question, "raw_input", "") or "").lower()
    runtime_facts = dict(getattr(grounding_bundle, "runtime_facts", {}) or {})
    session_facts = dict(getattr(grounding_bundle, "session_facts", {}) or {})
    guidance_lines: list[str] = []

    if question_type == "capabilities":
        guidance_lines.extend(
            [
                "Answer broad capability questions with enough grounded coverage to mention supported command families, question scope, and major limits.",
                "Name concrete command intent identifiers such as open_app, open_file, search_local, or prepare_workspace when the capability catalog is available in the bundle.",
                "Make it explicit that question-answer mode is read-only, grounded, and separate from command execution.",
                "When multiple allowed sources each support a different capability claim, cite each materially relevant source instead of collapsing to one or two citations.",
                "If the allowed bundle spans capability metadata, product rules, question-mode docs, and command-model docs, broad capability answers should usually cite each of those source families.",
                "When that broad capabilities bundle is present, keep at least three distinct source_attributions in the grounded answer.",
            ]
        )
    if question_type == "runtime_status" and any(token in lowered for token in ("folder", "workspace", "project")):
        workspace_path = str(session_facts.get("recent_project_context", "") or "").strip()
        if workspace_path:
            guidance_lines.append(f"Use the exact recent workspace or folder path when answering: {workspace_path}")
        guidance_lines.append(
            "When runtime-status and workspace-context sources are both available, keep at least two source_attributions in the grounded answer."
        )
    if question_type == "repo_structure":
        guidance_lines.extend(
            [
                "If an allowed source path directly answers where a module lives, name that exact file path in answer_text.",
                "Prefer using both the repo code path and the supporting repo-structure doc when both are present.",
                "When the bundle includes both the exact module path and docs/repo_structure.md, keep both sources in source_attributions.",
            ]
        )
    if question_type == "blocked_state":
        confirmation_message = str(runtime_facts.get("confirmation_message", "") or "").strip()
        clarification_question = str(runtime_facts.get("clarification_question", "") or "").strip()
        blocked_reason = str(runtime_facts.get("blocked_reason", "") or "").strip()
        runtime_state = str(runtime_facts.get("runtime_state", "") or "").strip()
        concrete_boundary = confirmation_message or clarification_question or blocked_reason
        if concrete_boundary:
            guidance_lines.append(f"Preserve the concrete blocked-state boundary when answering: {concrete_boundary}")
            guidance_lines.append("Repeat that concrete blocked-state boundary verbatim in answer_text when it is present.")
        elif runtime_state == "awaiting_confirmation":
            guidance_lines.append(
                "If no concrete confirmation message is present, say that explicit confirmation before execution can continue and do not invent a different item or option to confirm."
            )
        if runtime_state in {"awaiting_confirmation", "awaiting_clarification"}:
            guidance_lines.append(
                "When blocked-state sources cover question-mode rules, product boundaries, and runtime flow, keep at least three source_attributions in the grounded answer."
            )
        guidance_lines.append("Use enough grounded sources to cover the read-only QA boundary, the blocked state, and the runtime pause semantics.")
    if question_type == "answer_follow_up":
        recent_answer_context = dict(session_facts.get("recent_answer_context", {}) or {})
        recent_topic = str(recent_answer_context.get("topic", "") or "").strip()
        recent_sources = [str(source or "").strip() for source in list(recent_answer_context.get("sources", []) or []) if str(source or "").strip()]
        if recent_topic:
            guidance_lines.append(f"Keep the follow-up grounded in the recent answer topic: {recent_topic}")
        guidance_lines.append("Reuse the provided recent-answer sources when expanding or explaining the previous grounded answer.")
        if len(recent_sources) >= 2:
            guidance_lines.append("When two or more recent-answer sources are provided, keep at least two source_attributions in the grounded answer.")
            guidance_lines.append("Reuse both recent-answer source paths in source_attributions; do not collapse a follow-up explanation to a single citation.")
        if any(token in lowered for token in ("explain more", "more detail", "more details", "expand")):
            guidance_lines.append("For explain-more follow-ups, expand the prior grounded answer using those recent-answer sources instead of falling back to a generic summary.")
            if recent_topic == "clarification":
                guidance_lines.append(
                    "Make it explicit that clarification happens before planning or execution when ambiguity, missing data, low confidence, or mixed question-and-command intent is present."
                )
                guidance_lines.append(
                    "Open the explanation with wording close to: In more detail: clarification happens before planning or execution when ambiguity, missing data, low confidence, or mixed question-and-command intent is present."
                )
                guidance_lines.append(
                    "Preserve the hard-boundary framing: clarification pauses progress until the missing detail or ambiguity is resolved."
                )
        if any(token in lowered for token in ("which source", "where written", "where is that written")):
            guidance_lines.append("If the user asks which source was used, answer with the exact raw source path(s) verbatim in answer_text.")
            guidance_lines.append("For source-identification follow-ups, cite those same exact source paths in source_attributions instead of paraphrasing the document names.")
    if question_type == "docs_rules" and "clarification" in lowered:
        guidance_lines.append("Clarification answers should mention ambiguity, missing data, low confidence, or routing ambiguity when those rules are supported by the bundle.")
        guidance_lines.append("Make it explicit that clarification is a hard boundary before planning or execution continues.")
    if question_type == "safety_explanations":
        guidance_lines.append("Safety explanations should preserve that confirmation or clarification prevents unintended or hidden execution before proceeding.")
        guidance_lines.append("Use wording that makes explicit approval or agreement visible when that is part of the grounded safety boundary.")

    if not guidance_lines:
        return ""
    rendered = "\n".join(f"- {line}" for line in guidance_lines)
    return f"Question-specific guidance:\n{rendered}"


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


def _source_line(source) -> str:
    parts = [source.path, f"kind={source.kind}"]
    if source.section_hint:
        parts.append(f"section={source.section_hint}")
    return " | ".join(parts)
