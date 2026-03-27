"""Machine-readable manual beta checklist for QA release decisioning."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from qa.rollout_profiles import manual_beta_checklist_artifact_path

_MANUAL_VERIFICATION_DOC = "docs/manual_verification_commands.md"
_MANUAL_BETA_CHECKLIST_GUIDE_COMMAND = "python3 -m qa.manual_beta_checklist"


@dataclass(slots=True, frozen=True)
class ManualBetaChecklistItem:
    """One operator-facing manual beta checklist item."""

    item_id: str
    label: str
    prompt: str
    expected: str
    env_hint: str | None = None
    doc_section: str = "Manual beta checklist scripted scenarios"

    def to_state(self, *, passed: bool) -> dict[str, Any]:
        return {
            "label": self.label,
            "prompt": self.prompt,
            "expected": self.expected,
            "env_hint": self.env_hint or "",
            "doc_section": self.doc_section,
            "passed": passed,
        }


_CHECKLIST_ITEMS = (
    ManualBetaChecklistItem(
        "arbitrary_factual_question",
        "Arbitrary factual question",
        prompt="who is the president of France?",
        expected="mode=question; answer-kind=open_domain_model; provenance=model_knowledge; no fake local sources",
        env_hint="JARVIS_QA_BACKEND=llm JARVIS_QA_LLM_ENABLED=true JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED=true",
    ),
    ManualBetaChecklistItem(
        "arbitrary_explanation_question",
        "Arbitrary explanation question",
        prompt="why is the sky blue?",
        expected="mode=question; explanatory open-domain answer; provenance=model_knowledge; no fake local sources",
        env_hint="JARVIS_QA_BACKEND=llm JARVIS_QA_LLM_ENABLED=true JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED=true",
    ),
    ManualBetaChecklistItem(
        "casual_chat_question",
        "Casual chat question",
        prompt="how's your day going?",
        expected="mode=question; bounded casual reply; no execution; no fake local sources",
        env_hint="JARVIS_QA_BACKEND=llm JARVIS_QA_LLM_ENABLED=true JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED=true",
    ),
    ManualBetaChecklistItem(
        "blocked_state_question",
        "Blocked-state question",
        prompt="close Telegram -> what exactly do you need me to confirm?",
        expected="awaiting_confirmation first; then grounded read-only explanation of the current confirmation boundary",
    ),
    ManualBetaChecklistItem(
        "grounded_docs_question",
        "Grounded docs question",
        prompt="how does clarification work?",
        expected="grounded local answer with sources/support-attributions; no execution",
    ),
    ManualBetaChecklistItem(
        "mixed_question_command",
        "Mixed question + command",
        prompt="what can you do and open Safari",
        expected="routing clarification only; no silent answer+execute behavior",
    ),
    ManualBetaChecklistItem(
        "provider_unavailable_path",
        "Provider unavailable path",
        prompt="who is the president of France? (with provider intentionally unavailable)",
        expected="honest unavailable/failure answer path; no fake answer; no hidden execution fallback",
        env_hint="JARVIS_QA_BACKEND=llm JARVIS_QA_LLM_ENABLED=true JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED=true with the configured API key env unset or invalid",
    ),
)
_CHECKLIST_ITEM_IDS = {item.item_id for item in _CHECKLIST_ITEMS}


@dataclass(slots=True, frozen=True)
class ManualBetaChecklistRecord:
    """Current manual checklist status for beta_question_default."""

    checklist_id: str
    items: dict[str, dict[str, Any]]
    notes: str | None = None

    @property
    def passed_items(self) -> int:
        return sum(1 for item in self.items.values() if bool(item.get("passed")))

    @property
    def total_items(self) -> int:
        return len(_CHECKLIST_ITEMS)

    @property
    def all_passed(self) -> bool:
        return self.passed_items == self.total_items

    @property
    def pending_items(self) -> list[str]:
        pending_items: list[str] = []
        for item in _CHECKLIST_ITEMS:
            item_state = dict(self.items.get(item.item_id, {}) or {})
            if not bool(item_state.get("passed", False)):
                pending_items.append(item.item_id)
        return pending_items

    @property
    def pending_item_details(self) -> list[dict[str, str]]:
        pending_item_details: list[dict[str, str]] = []
        for item in _CHECKLIST_ITEMS:
            item_state = dict(self.items.get(item.item_id, {}) or {})
            if bool(item_state.get("passed", False)):
                continue
            pending_item_details.append(_checklist_item_detail(item, item_state))
        return pending_item_details

    @property
    def next_step_kind(self) -> str:
        if self.all_passed:
            return "manual_beta_checklist_complete"
        return "complete_manual_beta_checklist"

    @property
    def next_step_command(self) -> str | None:
        if self.all_passed:
            return None
        args = manual_beta_checklist_suggested_args(self.pending_items)
        return f"{manual_beta_checklist_guide_command()} {args} --write-artifact"

    def to_dict(self) -> dict[str, Any]:
        return {
            "checklist_id": self.checklist_id,
            "passed_items": self.passed_items,
            "total_items": self.total_items,
            "all_passed": self.all_passed,
            "pending_items": list(self.pending_items),
            "pending_item_details": list(self.pending_item_details),
            "next_step_kind": self.next_step_kind,
            "next_step_command": self.next_step_command or "",
            "verification_doc": _MANUAL_VERIFICATION_DOC,
            "items": dict(self.items),
            "notes": self.notes or "",
        }


def build_manual_beta_checklist_record(
    *,
    passed_item_ids: list[str] | None = None,
    failed_item_ids: list[str] | None = None,
    all_passed: bool = False,
    notes: str | None = None,
    existing_payload: dict[str, Any] | None = None,
    reset: bool = False,
) -> ManualBetaChecklistRecord:
    """Build one manual beta checklist record, optionally updating an existing artifact."""
    existing_items = {} if reset else _existing_item_states(existing_payload)
    item_states: dict[str, dict[str, Any]] = {}
    for item in _CHECKLIST_ITEMS:
        existing_state = dict(existing_items.get(item.item_id, {}) or {})
        item_states[item.item_id] = item.to_state(passed=bool(existing_state.get("passed", False)))
    if all_passed:
        for item_state in item_states.values():
            item_state["passed"] = True
    for item_id in passed_item_ids or []:
        _validate_item_id(item_id)
        item_states[item_id]["passed"] = True
    for item_id in failed_item_ids or []:
        _validate_item_id(item_id)
        item_states[item_id]["passed"] = False
    return ManualBetaChecklistRecord(
        checklist_id="beta_question_default",
        items=item_states,
        notes=str(notes or "").strip() or None,
    )


def format_manual_beta_checklist_record(record: ManualBetaChecklistRecord) -> str:
    """Render one operator-friendly manual beta checklist summary."""
    lines = [
        "JARVIS QA Manual Beta Checklist",
        f"checklist: {record.checklist_id}",
        f"progress: {record.passed_items}/{record.total_items}",
        f"all passed: {'yes' if record.all_passed else 'no'}",
        f"pending items: {', '.join(record.pending_items) if record.pending_items else 'none'}",
        f"next step: {record.next_step_kind}",
        f"next step command: {record.next_step_command or 'n/a'}",
        f"verification doc: {_MANUAL_VERIFICATION_DOC}",
        "items:",
    ]
    for item in _CHECKLIST_ITEMS:
        item_state = dict(record.items.get(item.item_id, {}) or {})
        lines.append(
            f"  - {item.item_id}: {'passed' if bool(item_state.get('passed')) else 'pending'} ({item.label})"
        )
    if record.pending_item_details:
        lines.extend(manual_beta_checklist_detail_lines(record.pending_item_details))
    else:
        lines.append("pending scenario guide: none")
    if record.notes:
        lines.append(f"notes: {record.notes}")
    return "\n".join(lines)


def manual_beta_checklist_artifact_payload(record: ManualBetaChecklistRecord) -> dict[str, Any]:
    """Return the machine-readable manual beta checklist artifact payload."""
    return {
        "schema_version": 1,
        "runner": "qa.manual_beta_checklist",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "report": record.to_dict(),
    }


def write_manual_beta_checklist_artifact(
    record: ManualBetaChecklistRecord,
    *,
    artifact_path: Path | None = None,
) -> Path:
    """Persist one manual beta checklist artifact."""
    resolved_artifact_path = artifact_path or manual_beta_checklist_artifact_path()
    resolved_artifact_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_artifact_path.write_text(
        json.dumps(manual_beta_checklist_artifact_payload(record), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return resolved_artifact_path


def load_manual_beta_checklist_artifact(
    artifact_path: Path | None = None,
) -> tuple[Path, dict[str, Any] | None, str | None]:
    """Load the current manual beta checklist artifact plus any parse error."""
    resolved_artifact_path = artifact_path or manual_beta_checklist_artifact_path()
    if not resolved_artifact_path.exists():
        return resolved_artifact_path, None, None
    try:
        payload = json.loads(resolved_artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return resolved_artifact_path, None, f"{type(exc).__name__}: {exc}"
    if not isinstance(payload, dict):
        return resolved_artifact_path, None, "ValueError: manual beta checklist artifact must be a JSON object."
    return resolved_artifact_path, payload, None


def manual_beta_checklist_status(
    artifact_payload: dict[str, Any] | None,
    artifact_error: str | None,
) -> tuple[str, int | None, int | None, bool]:
    """Return one short manual-checklist status plus progress counts."""
    if artifact_error is not None:
        return "invalid", None, None, False
    if artifact_payload is None:
        return "missing", None, None, False
    report = artifact_payload.get("report")
    if not isinstance(report, dict):
        return "invalid", None, None, False
    passed_items = report.get("passed_items")
    total_items = report.get("total_items")
    all_passed = bool(report.get("all_passed", False))
    if not isinstance(passed_items, int) or not isinstance(total_items, int):
        return "invalid", None, None, False
    if total_items <= 0:
        return "invalid", passed_items, total_items, False
    if all_passed and passed_items == total_items:
        return "complete", passed_items, total_items, True
    return "incomplete", passed_items, total_items, False


def manual_beta_checklist_pending_items(
    artifact_payload: dict[str, Any] | None,
    artifact_error: str | None,
) -> list[str]:
    """Return pending manual-checklist item ids from the latest artifact payload."""
    if artifact_error is not None:
        return []
    report = dict((artifact_payload or {}).get("report", {}) or {})
    items = report.get("items")
    if not isinstance(items, dict):
        return [item.item_id for item in _CHECKLIST_ITEMS]
    pending_items: list[str] = []
    for item in _CHECKLIST_ITEMS:
        item_state = dict(items.get(item.item_id, {}) or {})
        if not bool(item_state.get("passed", False)):
            pending_items.append(item.item_id)
    return pending_items


def manual_beta_checklist_pending_item_details(
    artifact_payload: dict[str, Any] | None,
    artifact_error: str | None,
) -> list[dict[str, str]]:
    """Return pending manual-checklist item details from the latest artifact payload."""
    report = dict((artifact_payload or {}).get("report", {}) or {})
    items = report.get("items")
    if artifact_error is not None or not isinstance(items, dict):
        return [_checklist_item_detail(item, None) for item in _CHECKLIST_ITEMS]
    pending_item_details: list[dict[str, str]] = []
    for item in _CHECKLIST_ITEMS:
        item_state = dict(items.get(item.item_id, {}) or {})
        if bool(item_state.get("passed", False)):
            continue
        pending_item_details.append(_checklist_item_detail(item, item_state))
    return pending_item_details


def manual_beta_checklist_detail_lines(
    pending_item_details: list[dict[str, str]],
    *,
    heading: str = "pending scenario guide:",
) -> list[str]:
    """Render operator-facing lines for one pending manual-checklist scenario guide."""
    lines = [heading]
    for detail in pending_item_details:
        lines.append(f"  - {detail['item_id']}: {detail['label']}")
        lines.append(f"    input: {detail['prompt']}")
        env_hint = str(detail.get("env_hint", "") or "").strip()
        if env_hint:
            lines.append(f"    env: {env_hint}")
        lines.append(f"    expected: {detail['expected']}")
        lines.append(f"    doc section: {detail['doc_section']}")
    return lines


def manual_beta_checklist_guide_command() -> str:
    """Return the base command that prints the current manual beta checklist guide."""
    return _MANUAL_BETA_CHECKLIST_GUIDE_COMMAND


def manual_beta_checklist_verification_doc() -> str:
    """Return the operator doc that defines the manual beta checklist scenarios."""
    return _MANUAL_VERIFICATION_DOC


def manual_beta_checklist_suggested_args(
    pending_item_ids: list[str],
    *,
    force_full_rerun: bool = False,
) -> str:
    """Return suggested CLI args for completing the remaining manual checklist work."""
    if force_full_rerun:
        return "--all-passed"
    pending_item_set = set(pending_item_ids)
    ordered_pending_item_ids = [item.item_id for item in _CHECKLIST_ITEMS if item.item_id in pending_item_set]
    if not ordered_pending_item_ids or len(ordered_pending_item_ids) == len(_CHECKLIST_ITEMS):
        return "--all-passed"
    return " ".join(f"--pass {item_id}" for item_id in ordered_pending_item_ids)


def main(argv: list[str] | None = None) -> int:
    """Inspect or update the manual beta checklist artifact."""
    parser = argparse.ArgumentParser(description="Inspect or update the manual QA beta checklist artifact.")
    parser.add_argument("--pass", dest="passed_item_ids", action="append", default=[], help="Mark one checklist item as passed.")
    parser.add_argument("--fail", dest="failed_item_ids", action="append", default=[], help="Mark one checklist item as pending.")
    parser.add_argument("--all-passed", action="store_true", help="Mark all checklist items as passed.")
    parser.add_argument("--reset", action="store_true", help="Ignore any existing artifact state before applying updates.")
    parser.add_argument("--notes", default="", help="Optional short note stored in the artifact.")
    parser.add_argument("--write-artifact", action="store_true", help="Write the checklist artifact to tmp/qa.")
    parser.add_argument("--json", action="store_true", help="Print the full artifact JSON.")
    args = parser.parse_args(argv)

    artifact_path, existing_payload, existing_error = load_manual_beta_checklist_artifact()
    if existing_error is not None:
        raise SystemExit(existing_error)
    record = build_manual_beta_checklist_record(
        passed_item_ids=list(args.passed_item_ids),
        failed_item_ids=list(args.failed_item_ids),
        all_passed=bool(args.all_passed),
        notes=str(args.notes or "").strip() or None,
        existing_payload=existing_payload,
        reset=bool(args.reset),
    )
    resolved_artifact_path: Path | None = None
    if args.write_artifact:
        resolved_artifact_path = write_manual_beta_checklist_artifact(record, artifact_path=artifact_path)

    if args.json:
        print(json.dumps(manual_beta_checklist_artifact_payload(record), indent=2, sort_keys=True))
    else:
        print(format_manual_beta_checklist_record(record))
        if resolved_artifact_path is not None:
            print(f"artifact: {resolved_artifact_path}")
    return 0 if record.all_passed else 1


def _existing_item_states(existing_payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    report = dict((existing_payload or {}).get("report", {}) or {})
    items = report.get("items")
    if not isinstance(items, dict):
        return {}
    existing_states: dict[str, dict[str, Any]] = {}
    for item_id, item_state in items.items():
        if not isinstance(item_id, str) or item_id not in _CHECKLIST_ITEM_IDS or not isinstance(item_state, dict):
            continue
        existing_states[item_id] = dict(item_state)
    return existing_states


def _checklist_item_detail(
    item: ManualBetaChecklistItem,
    item_state: dict[str, Any] | None,
) -> dict[str, str]:
    state = dict(item_state or {})
    return {
        "item_id": item.item_id,
        "label": str(state.get("label", item.label) or item.label),
        "prompt": str(state.get("prompt", item.prompt) or item.prompt),
        "expected": str(state.get("expected", item.expected) or item.expected),
        "env_hint": str(state.get("env_hint", item.env_hint or "") or ""),
        "doc_section": str(state.get("doc_section", item.doc_section) or item.doc_section),
    }


def _validate_item_id(item_id: str) -> None:
    if item_id not in _CHECKLIST_ITEM_IDS:
        raise ValueError(f"Unsupported manual beta checklist item: {item_id!r}.")


if __name__ == "__main__":
    raise SystemExit(main())
