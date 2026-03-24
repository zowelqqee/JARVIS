"""Grounding bundle selection for question-answer backends."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from context.session_context import SessionContext
    from types.question_request import QuestionRequest

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from question_request import QuestionType  # type: ignore  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(slots=True)
class GroundingBundle:
    """Local source and state bundle allowed for grounded answers."""

    scope: str
    source_paths: list[str] = field(default_factory=list)
    source_notes: list[str] = field(default_factory=list)
    runtime_facts: dict[str, Any] = field(default_factory=dict)
    session_facts: dict[str, Any] = field(default_factory=dict)


def build_grounding_bundle(
    question: QuestionRequest,
    *,
    session_context: SessionContext | None = None,
    runtime_snapshot: dict[str, Any] | None = None,
) -> GroundingBundle:
    """Select the local sources and visible facts allowed for one answer."""
    lowered = str(getattr(question, "raw_input", "")).lower()
    runtime_facts = _non_empty_mapping(runtime_snapshot)
    session_facts = _session_facts(question, session_context=session_context)
    notes = [
        "Answer only from the listed local sources and supplied runtime/session facts.",
        "Question mode is read-only and must not imply command execution.",
    ]

    question_type = getattr(question, "question_type", None)
    if question_type == QuestionType.CAPABILITIES:
        return GroundingBundle(
            scope="capabilities",
            source_paths=_paths(
                "qa/capability_catalog.py",
                "docs/product_rules.md",
                "docs/question_answer_mode.md",
                "docs/command_model.md",
            ),
            source_notes=notes,
            runtime_facts=runtime_facts,
            session_facts=session_facts,
        )

    if question_type == QuestionType.RUNTIME_STATUS:
        sources = _paths("docs/runtime_flow.md", "docs/session_context.md")
        if "folder" in lowered:
            sources.extend(_paths("context/session_context.py"))
        return GroundingBundle(
            scope="runtime",
            source_paths=_dedupe(sources),
            source_notes=notes,
            runtime_facts=runtime_facts,
            session_facts=session_facts,
        )

    if question_type == QuestionType.DOCS_RULES:
        if "clarification" in lowered:
            sources = _paths("docs/clarification_rules.md", "docs/runtime_flow.md")
        elif "confirmation" in lowered:
            sources = _paths("docs/product_rules.md", "docs/runtime_flow.md")
        elif "session context" in lowered:
            sources = _paths("docs/session_context.md")
        else:
            sources = _paths("docs/runtime_flow.md", "docs/runtime_components.md", "docs/question_answer_mode.md")
        return GroundingBundle(
            scope="docs",
            source_paths=_dedupe(sources),
            source_notes=notes,
            runtime_facts=runtime_facts,
            session_facts=session_facts,
        )

    if question_type == QuestionType.REPO_STRUCTURE:
        sources = _repo_structure_sources(lowered)
        return GroundingBundle(
            scope="repo_structure",
            source_paths=_dedupe(sources),
            source_notes=notes,
            runtime_facts=runtime_facts,
            session_facts=session_facts,
        )

    if question_type == QuestionType.SAFETY_EXPLANATIONS:
        return GroundingBundle(
            scope="safety",
            source_paths=_paths("docs/product_rules.md", "docs/clarification_rules.md", "docs/runtime_flow.md"),
            source_notes=notes,
            runtime_facts=runtime_facts,
            session_facts=session_facts,
        )

    return GroundingBundle(
        scope=str(getattr(question, "scope", "question") or "question"),
        source_paths=_paths("docs/question_answer_mode.md"),
        source_notes=notes,
        runtime_facts=runtime_facts,
        session_facts=session_facts,
    )


def _repo_structure_sources(lowered: str) -> list[str]:
    if "planner" in lowered or "execution plan" in lowered:
        return _paths("planner/execution_planner.py", "docs/repo_structure.md")
    if "parser" in lowered or "parse command" in lowered:
        return _paths("parser/command_parser.py", "docs/repo_structure.md")
    if "validator" in lowered or "validate command" in lowered:
        return _paths("validator/command_validator.py", "docs/repo_structure.md")
    if "runtime" in lowered or "state machine" in lowered or "runtime state" in lowered:
        return _paths("runtime/runtime_manager.py", "runtime/state_machine.py", "docs/repo_structure.md")
    if "visibility" in lowered or "ui" in lowered:
        return _paths("ui/visibility_mapper.py", "ui/interaction_presenter.py", "docs/repo_structure.md")
    if "interaction" in lowered or "route interaction" in lowered:
        return _paths("interaction/interaction_router.py", "interaction/interaction_manager.py", "docs/repo_structure.md")
    if "answer engine" in lowered or "qa" in lowered or "question-answer" in lowered:
        return _paths(
            "qa/answer_engine.py",
            "qa/deterministic_backend.py",
            "qa/llm_backend.py",
            "qa/openai_responses_provider.py",
            "docs/repo_structure.md",
        )
    return _paths("docs/repo_structure.md")


def _session_facts(question: QuestionRequest, *, session_context: SessionContext | None) -> dict[str, Any]:
    if session_context is None:
        return {}
    lowered = str(getattr(question, "raw_input", "")).lower()
    facts: dict[str, Any] = {}
    if "folder" in lowered:
        recent_project_context = session_context.get_recent_project_context()
        if recent_project_context:
            facts["recent_project_context"] = recent_project_context
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


def _paths(*relative_paths: str) -> list[str]:
    return [str(_REPO_ROOT / relative_path) for relative_path in relative_paths]


def _dedupe(paths: list[str]) -> list[str]:
    return list(dict.fromkeys(paths))
