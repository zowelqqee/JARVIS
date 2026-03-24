"""Grounding bundle selection for question-answer backends."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from qa.debug_trace import set_debug_payload
from qa.source_registry import GroundingSource
from qa.source_selector import select_sources

if TYPE_CHECKING:
    from context.session_context import SessionContext
    from types.answer_result import AnswerSourceAttribution
    from types.question_request import QuestionRequest

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from question_request import QuestionType  # type: ignore  # noqa: E402


@dataclass(slots=True)
class GroundingBundle:
    """Local source and state bundle allowed for grounded answers."""

    scope: str
    sources: list[GroundingSource] = field(default_factory=list)
    source_notes: list[str] = field(default_factory=list)
    runtime_facts: dict[str, Any] = field(default_factory=dict)
    session_facts: dict[str, Any] = field(default_factory=dict)

    @property
    def source_paths(self) -> list[str]:
        return [source.path for source in self.sources]

    def build_source_attributions(self) -> list[AnswerSourceAttribution]:
        from answer_result import AnswerSourceAttribution  # type: ignore  # noqa: E402

        return [
            AnswerSourceAttribution(source=source.path, support=source.support)
            for source in self.sources
        ]

    def describe_sources(self) -> list[str]:
        return [source.describe() for source in self.sources]


def build_grounding_bundle(
    question: QuestionRequest,
    *,
    session_context: SessionContext | None = None,
    runtime_snapshot: dict[str, Any] | None = None,
    debug_trace: dict[str, Any] | None = None,
) -> GroundingBundle:
    """Select the local sources and visible facts allowed for one answer."""
    runtime_facts = _non_empty_mapping(runtime_snapshot)
    session_facts = _session_facts(question, session_context=session_context)
    notes = [
        "Answer only from the listed local sources and supplied runtime/session facts.",
        "Question mode is read-only and must not imply command execution.",
        "When citing docs, prefer the registered section-aware support claim instead of a bare file path.",
    ]
    bundle = GroundingBundle(
        scope=str(getattr(question, "scope", "question") or "question"),
        sources=select_sources(question),
        source_notes=notes,
        runtime_facts=runtime_facts,
        session_facts=session_facts,
    )
    set_debug_payload(
        debug_trace,
        "source_selection",
        {
            "scope": bundle.scope,
            "source_count": len(bundle.sources),
            "sources": bundle.source_paths,
            "source_kinds": [source.kind for source in bundle.sources],
            "section_hints": [source.section_hint for source in bundle.sources if source.section_hint],
            "runtime_fact_keys": sorted(runtime_facts.keys()),
            "session_fact_keys": sorted(session_facts.keys()),
        },
    )
    return bundle


def _session_facts(question: QuestionRequest, *, session_context: SessionContext | None) -> dict[str, Any]:
    if session_context is None:
        return {}
    lowered = str(getattr(question, "raw_input", "")).lower()
    facts: dict[str, Any] = {}
    if "folder" in lowered:
        recent_project_context = session_context.get_recent_project_context()
        if recent_project_context:
            facts["recent_project_context"] = recent_project_context
    if getattr(question, "question_type", None) == QuestionType.RECENT_RUNTIME:
        recent_primary_target = session_context.get_recent_primary_target()
        if recent_primary_target is not None:
            facts["recent_primary_target"] = {
                "type": str(getattr(getattr(recent_primary_target, "type", ""), "value", getattr(recent_primary_target, "type", ""))),
                "name": str(getattr(recent_primary_target, "name", "") or "").strip(),
                "path": str(getattr(recent_primary_target, "path", "") or "").strip() or None,
            }
        recent_primary_action = session_context.get_recent_primary_action()
        if recent_primary_action:
            facts["recent_primary_action"] = recent_primary_action
        recent_project_context = session_context.get_recent_project_context()
        if recent_project_context:
            facts["recent_project_context"] = recent_project_context
        recent_search_results = session_context.get_recent_search_results()
        if recent_search_results:
            facts["recent_search_results"] = recent_search_results
    if getattr(question, "question_type", None) == QuestionType.ANSWER_FOLLOW_UP:
        recent_answer_context = session_context.get_recent_answer_context()
        if recent_answer_context:
            facts["recent_answer_context"] = recent_answer_context
    return facts


def _non_empty_mapping(mapping: dict[str, Any] | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in dict(mapping or {}).items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, (list, tuple, set, dict)) and not value:
            continue
        result[str(key)] = value
    return result
