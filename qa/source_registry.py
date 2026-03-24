"""Central registry for grounded QA source selection."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types"
if str(_TYPES_PATH) not in sys.path:
    sys.path.insert(0, str(_TYPES_PATH))

from question_request import QuestionType  # type: ignore  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class GroundingSource:
    """One grounded source record with stable support metadata."""

    path: str
    support: str
    kind: str
    section_hint: str | None = None
    priority: int = 100

    def describe(self) -> str:
        """Return a stable text form suitable for provider payloads."""
        parts = [self.path, f"kind={self.kind}"]
        if self.section_hint:
            parts.append(f"section={self.section_hint}")
        parts.append(f"support={self.support}")
        return " | ".join(parts)


@dataclass(frozen=True, slots=True)
class SourceTopicEntry:
    """Topic-level grounded source mapping for one answer family."""

    question_type: QuestionType
    topic: str
    sources: tuple[GroundingSource, ...]


def get_registered_sources(question_type: QuestionType | str | None, *, topic: str = "default") -> list[GroundingSource]:
    """Return the registered sources for one question family/topic pair."""
    normalized_topic = str(topic or "default").strip() or "default"
    for entry in _SOURCE_TOPIC_REGISTRY:
        if entry.question_type == question_type and entry.topic == normalized_topic:
            return list(entry.sources)
    return []


def get_registered_sources_for_paths(paths: list[str] | tuple[str, ...] | None) -> list[GroundingSource]:
    """Resolve registered source metadata for an explicit ordered list of source paths."""
    if not paths:
        return []

    by_path: dict[str, GroundingSource] = {}
    for entry in _SOURCE_TOPIC_REGISTRY:
        for source in entry.sources:
            existing = by_path.get(source.path)
            if existing is None or source.priority < existing.priority:
                by_path[source.path] = source

    resolved: list[GroundingSource] = []
    seen_paths: set[str] = set()
    for raw_path in paths:
        path = str(raw_path or "").strip()
        if not path or path in seen_paths:
            continue
        seen_paths.add(path)
        source = by_path.get(path)
        if source is None:
            source = GroundingSource(
                path=path,
                support="Previous answer grounding source reused for safe follow-up continuity.",
                kind="previous_answer_source",
                priority=500,
            )
        resolved.append(source)
    return resolved


def _source(
    relative_path: str,
    *,
    support: str,
    kind: str,
    section_hint: str | None = None,
    priority: int = 100,
) -> GroundingSource:
    return GroundingSource(
        path=str(_REPO_ROOT / relative_path),
        support=support,
        kind=kind,
        section_hint=section_hint,
        priority=priority,
    )


_SOURCE_TOPIC_REGISTRY: tuple[SourceTopicEntry, ...] = (
    SourceTopicEntry(
        question_type=QuestionType.BLOCKED_STATE,
        topic="default",
        sources=(
            _source(
                "docs/question_answer_mode.md",
                support="Blocked-state questions are a supported read-only question family.",
                kind="docs",
                section_hint="Supported Question Families (v1)",
                priority=10,
            ),
            _source(
                "docs/product_rules.md",
                support="Question-answer mode must stay read-only and must not imply confirmation or execution.",
                kind="docs",
                section_hint="Question-answer mode",
                priority=20,
            ),
            _source(
                "docs/clarification_rules.md",
                support="Clarification blocks progress when ambiguity, missing data, or low confidence is unresolved.",
                kind="docs",
                section_hint="When Clarification Is Required",
                priority=30,
            ),
            _source(
                "docs/runtime_flow.md",
                support="Runtime flow exposes awaiting_clarification and awaiting_confirmation as blocked command states.",
                kind="docs",
                section_hint="Command Runtime State Model",
                priority=40,
            ),
        ),
    ),
    SourceTopicEntry(
        question_type=QuestionType.RECENT_RUNTIME,
        topic="default",
        sources=(
            _source(
                "docs/session_context.md",
                support="Session context allows grounded reads of recent targets, workspace context, and confirmation state.",
                kind="docs",
                section_hint="QA Access Rules",
                priority=10,
            ),
            _source(
                "docs/runtime_flow.md",
                support="Question mode may answer from visible runtime state without executing any command steps.",
                kind="docs",
                section_hint="Question branch: build grounded answer",
                priority=20,
            ),
            _source(
                "context/session_context.py",
                support="SessionContext stores recent primary targets, actions, workspace context, and search results.",
                kind="session_context",
                priority=30,
            ),
        ),
    ),
    SourceTopicEntry(
        question_type=QuestionType.RUNTIME_STATUS,
        topic="default",
        sources=(
            _source(
                "docs/runtime_flow.md",
                support="Runtime flow defines visible states such as idle, executing, awaiting_clarification, and awaiting_confirmation.",
                kind="docs",
                section_hint="Command Runtime State Model",
                priority=10,
            ),
            _source(
                "docs/session_context.md",
                support="Session context may be read to answer narrow grounded status questions about the active supervised session.",
                kind="docs",
                section_hint="QA Access Rules",
                priority=20,
            ),
        ),
    ),
    SourceTopicEntry(
        question_type=QuestionType.RUNTIME_STATUS,
        topic="workspace_context",
        sources=(
            _source(
                "context/session_context.py",
                support="SessionContext stores recent project and workspace context for grounded follow-ups and status answers.",
                kind="session_context",
                priority=15,
            ),
        ),
    ),
    SourceTopicEntry(
        question_type=QuestionType.CAPABILITIES,
        topic="default",
        sources=(
            _source(
                "qa/capability_catalog.py",
                support="Capability catalog enumerates supported command intents, action classes, and question families.",
                kind="capability_metadata",
                priority=10,
            ),
            _source(
                "docs/product_rules.md",
                support="Product rules define execution scope, safety boundaries, and the read-only answer mode.",
                kind="docs",
                section_hint="Product Definition",
                priority=20,
            ),
            _source(
                "docs/question_answer_mode.md",
                support="Question-answer mode scope is grounded, read-only, and limited to supported families.",
                kind="docs",
                section_hint="Supported Question Families (v1)",
                priority=30,
            ),
            _source(
                "docs/command_model.md",
                support="Command mode remains an execution-only contract separate from question answering.",
                kind="docs",
                priority=40,
            ),
        ),
    ),
    SourceTopicEntry(
        question_type=QuestionType.DOCS_RULES,
        topic="default",
        sources=(
            _source(
                "docs/question_answer_mode.md",
                support="Question-answer mode is grounded from explicit local sources and fails honestly when support is missing.",
                kind="docs",
                section_hint="Grounding Sources",
                priority=10,
            ),
            _source(
                "docs/runtime_components.md",
                support="Runtime components separate the command branch from the read-only question branch.",
                kind="docs",
                section_hint="Component Interaction Order",
                priority=20,
            ),
            _source(
                "docs/runtime_flow.md",
                support="Runtime flow keeps question answering outside the command execution state machine.",
                kind="docs",
                section_hint="Interaction Stages",
                priority=30,
            ),
        ),
    ),
    SourceTopicEntry(
        question_type=QuestionType.DOCS_RULES,
        topic="clarification",
        sources=(
            _source(
                "docs/clarification_rules.md",
                support="Clarification rules define when ambiguity, missing data, low confidence, or routing ambiguity must block progress.",
                kind="docs",
                section_hint="When Clarification Is Required",
                priority=10,
            ),
            _source(
                "docs/runtime_flow.md",
                support="Runtime flow shows clarification as a stop before planning or execution can continue.",
                kind="docs",
                section_hint="5. Clarify if needed",
                priority=20,
            ),
        ),
    ),
    SourceTopicEntry(
        question_type=QuestionType.DOCS_RULES,
        topic="confirmation",
        sources=(
            _source(
                "docs/product_rules.md",
                support="Sensitive actions require explicit confirmation before execution continues.",
                kind="docs",
                section_hint="Sensitive actions (require explicit confirmation)",
                priority=10,
            ),
            _source(
                "docs/runtime_flow.md",
                support="Runtime flow pauses on confirmation boundaries until the user explicitly approves or denies.",
                kind="docs",
                section_hint="8. Pause on confirmation boundary",
                priority=20,
            ),
        ),
    ),
    SourceTopicEntry(
        question_type=QuestionType.DOCS_RULES,
        topic="session_context",
        sources=(
            _source(
                "docs/session_context.md",
                support="Session context is short-lived state for the active supervised session and is not long-term memory.",
                kind="docs",
                section_hint="Purpose",
                priority=10,
            ),
        ),
    ),
    SourceTopicEntry(
        question_type=QuestionType.DOCS_RULES,
        topic="runtime",
        sources=(
            _source(
                "docs/runtime_flow.md",
                support="Runtime flow separates command stages from the read-only question branch.",
                kind="docs",
                section_hint="Interaction Stages",
                priority=10,
            ),
            _source(
                "docs/runtime_components.md",
                support="Runtime components map each command and question responsibility to one module boundary.",
                kind="docs",
                section_hint="Core Components",
                priority=20,
            ),
        ),
    ),
    SourceTopicEntry(
        question_type=QuestionType.REPO_STRUCTURE,
        topic="default",
        sources=(
            _source(
                "docs/repo_structure.md",
                support="Repo structure maps top-level responsibilities and required files to concrete modules.",
                kind="docs",
                section_hint="Required Files Per Module",
                priority=10,
            ),
        ),
    ),
    SourceTopicEntry(
        question_type=QuestionType.REPO_STRUCTURE,
        topic="planner",
        sources=(
            _source(
                "planner/execution_planner.py",
                support="Execution planning lives here and produces ordered execution_steps.",
                kind="repo_code",
                priority=10,
            ),
            _source(
                "docs/repo_structure.md",
                support="Repo structure maps execution planning to planner/execution_planner.py.",
                kind="docs",
                section_hint="Required Files Per Module",
                priority=20,
            ),
        ),
    ),
    SourceTopicEntry(
        question_type=QuestionType.REPO_STRUCTURE,
        topic="parser",
        sources=(
            _source(
                "parser/command_parser.py",
                support="Command parsing lives here and produces preliminary Command objects from natural language input.",
                kind="repo_code",
                priority=10,
            ),
            _source(
                "docs/repo_structure.md",
                support="Repo structure maps command parsing to parser/command_parser.py.",
                kind="docs",
                section_hint="Required Files Per Module",
                priority=20,
            ),
        ),
    ),
    SourceTopicEntry(
        question_type=QuestionType.REPO_STRUCTURE,
        topic="validator",
        sources=(
            _source(
                "validator/command_validator.py",
                support="Command validation lives here and enforces legality before planning.",
                kind="repo_code",
                priority=10,
            ),
            _source(
                "docs/repo_structure.md",
                support="Repo structure maps validation to validator/command_validator.py.",
                kind="docs",
                section_hint="Required Files Per Module",
                priority=20,
            ),
        ),
    ),
    SourceTopicEntry(
        question_type=QuestionType.REPO_STRUCTURE,
        topic="runtime",
        sources=(
            _source(
                "runtime/runtime_manager.py",
                support="RuntimeManager owns command runtime orchestration and active command lifecycle.",
                kind="repo_code",
                priority=10,
            ),
            _source(
                "runtime/state_machine.py",
                support="State-machine transitions for command runtime live here.",
                kind="repo_code",
                priority=20,
            ),
            _source(
                "docs/repo_structure.md",
                support="Repo structure maps command runtime orchestration to runtime/runtime_manager.py and runtime/state_machine.py.",
                kind="docs",
                section_hint="Required Files Per Module",
                priority=30,
            ),
        ),
    ),
    SourceTopicEntry(
        question_type=QuestionType.REPO_STRUCTURE,
        topic="visibility",
        sources=(
            _source(
                "ui/visibility_mapper.py",
                support="Visibility mapping lives here and converts runtime truth into stable UI payloads.",
                kind="repo_code",
                priority=10,
            ),
            _source(
                "ui/interaction_presenter.py",
                support="Interaction presenter renders the final dual-mode output for the CLI.",
                kind="repo_code",
                priority=20,
            ),
            _source(
                "docs/repo_structure.md",
                support="Repo structure maps visibility work to ui/visibility_mapper.py and ui/interaction_presenter.py.",
                kind="docs",
                section_hint="Required Files Per Module",
                priority=30,
            ),
        ),
    ),
    SourceTopicEntry(
        question_type=QuestionType.REPO_STRUCTURE,
        topic="interaction",
        sources=(
            _source(
                "interaction/interaction_router.py",
                support="Top-level routing between command, question, and clarification lives here.",
                kind="repo_code",
                priority=10,
            ),
            _source(
                "interaction/interaction_manager.py",
                support="InteractionManager orchestrates top-level command vs question handling.",
                kind="repo_code",
                priority=20,
            ),
            _source(
                "docs/repo_structure.md",
                support="Repo structure maps interaction orchestration to interaction/interaction_router.py and interaction/interaction_manager.py.",
                kind="docs",
                section_hint="Required Files Per Module",
                priority=30,
            ),
        ),
    ),
    SourceTopicEntry(
        question_type=QuestionType.REPO_STRUCTURE,
        topic="answer_engine",
        sources=(
            _source(
                "qa/answer_engine.py",
                support="Answer engine classification and backend dispatch start here.",
                kind="repo_code",
                priority=10,
            ),
            _source(
                "qa/source_selector.py",
                support="Grounded source selection and topic-aware bundle assembly live here.",
                kind="repo_code",
                priority=20,
            ),
            _source(
                "qa/source_registry.py",
                support="The source registry maps question families and topics to grounded local sources.",
                kind="repo_code",
                priority=30,
            ),
            _source(
                "docs/repo_structure.md",
                support="Repo structure maps answer generation responsibilities under qa/.",
                kind="docs",
                section_hint="Required Files Per Module",
                priority=40,
            ),
        ),
    ),
    SourceTopicEntry(
        question_type=QuestionType.SAFETY_EXPLANATIONS,
        topic="default",
        sources=(
            _source(
                "docs/product_rules.md",
                support="Product rules define confirmation boundaries and the read-only nature of question mode.",
                kind="docs",
                section_hint="Safety Model",
                priority=10,
            ),
            _source(
                "docs/clarification_rules.md",
                support="Clarification rules explain why ambiguity and missing data stop execution.",
                kind="docs",
                section_hint="When Clarification Is Required",
                priority=20,
            ),
            _source(
                "docs/runtime_flow.md",
                support="Runtime flow pauses instead of continuing blindly when confirmation or clarification is required.",
                kind="docs",
                section_hint="Resume Rules",
                priority=30,
            ),
        ),
    ),
)
