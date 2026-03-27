"""Contract tests for the manual QA beta checklist artifact."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from qa.manual_beta_checklist import (
    build_manual_beta_checklist_record,
    format_manual_beta_checklist_record,
    load_manual_beta_checklist_artifact,
    manual_beta_checklist_pending_items,
    manual_beta_checklist_suggested_args,
    manual_beta_checklist_status,
    write_manual_beta_checklist_artifact,
)


class ManualBetaChecklistTests(unittest.TestCase):
    """Keep the manual beta checklist machine-readable and deterministic."""

    def test_build_manual_beta_checklist_record_marks_all_items_passed(self) -> None:
        record = build_manual_beta_checklist_record(all_passed=True, notes="All manual checks passed.")

        self.assertEqual(record.passed_items, record.total_items)
        self.assertTrue(record.all_passed)
        self.assertEqual(record.pending_items, [])
        self.assertEqual(record.pending_item_details, [])
        self.assertEqual(record.next_step_kind, "manual_beta_checklist_complete")
        self.assertIsNone(record.next_step_command)
        self.assertEqual(record.to_dict()["notes"], "All manual checks passed.")

    def test_write_manual_beta_checklist_artifact_persists_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "manual_beta_checklist.json"
            record = build_manual_beta_checklist_record(
                passed_item_ids=["arbitrary_factual_question", "grounded_docs_question"],
                notes="Partial pass.",
            )
            resolved_path = write_manual_beta_checklist_artifact(record, artifact_path=artifact_path)
            payload = json.loads(artifact_path.read_text(encoding="utf-8"))

        self.assertEqual(resolved_path, artifact_path)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["runner"], "qa.manual_beta_checklist")
        self.assertEqual(payload["report"]["passed_items"], 2)
        self.assertFalse(payload["report"]["all_passed"])
        self.assertEqual(
            payload["report"]["items"]["arbitrary_factual_question"]["prompt"],
            "who is the president of France?",
        )
        self.assertEqual(
            payload["report"]["items"]["provider_unavailable_path"]["env_hint"],
            "JARVIS_QA_BACKEND=llm JARVIS_QA_LLM_ENABLED=true JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED=true with the configured API key env unset or invalid",
        )
        self.assertEqual(
            payload["report"]["pending_items"],
            [
                "arbitrary_explanation_question",
                "casual_chat_question",
                "blocked_state_question",
                "mixed_question_command",
                "provider_unavailable_path",
            ],
        )
        self.assertEqual(
            payload["report"]["pending_item_details"][0],
            {
                "item_id": "arbitrary_explanation_question",
                "label": "Arbitrary explanation question",
                "prompt": "why is the sky blue?",
                "expected": "mode=question; explanatory open-domain answer; provenance=model_knowledge; no fake local sources",
                "env_hint": "JARVIS_QA_BACKEND=llm JARVIS_QA_LLM_ENABLED=true JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED=true",
                "doc_section": "Manual beta checklist scripted scenarios",
            },
        )
        self.assertEqual(payload["report"]["next_step_kind"], "complete_manual_beta_checklist")
        self.assertEqual(
            payload["report"]["next_step_command"],
            "python3 -m qa.manual_beta_checklist --pass arbitrary_explanation_question --pass casual_chat_question --pass blocked_state_question --pass mixed_question_command --pass provider_unavailable_path --write-artifact",
        )

    def test_manual_beta_checklist_status_reads_complete_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "manual_beta_checklist.json"
            record = build_manual_beta_checklist_record(all_passed=True)
            write_manual_beta_checklist_artifact(record, artifact_path=artifact_path)
            _path, payload, error = load_manual_beta_checklist_artifact(artifact_path)
            status, passed_items, total_items, completed = manual_beta_checklist_status(payload, error)

        self.assertEqual(status, "complete")
        self.assertEqual((passed_items, total_items), (7, 7))
        self.assertTrue(completed)

    def test_manual_beta_checklist_pending_items_returns_remaining_ids(self) -> None:
        record = build_manual_beta_checklist_record(
            passed_item_ids=["arbitrary_factual_question", "grounded_docs_question"],
        )

        pending_items = manual_beta_checklist_pending_items(
            {"report": record.to_dict()},
            None,
        )

        self.assertEqual(
            pending_items,
            [
                "arbitrary_explanation_question",
                "casual_chat_question",
                "blocked_state_question",
                "mixed_question_command",
                "provider_unavailable_path",
            ],
        )

    def test_manual_beta_checklist_suggested_args_uses_incremental_pass_flags(self) -> None:
        self.assertEqual(
            manual_beta_checklist_suggested_args(
                ["blocked_state_question", "provider_unavailable_path"],
            ),
            "--pass blocked_state_question --pass provider_unavailable_path",
        )

    def test_manual_beta_checklist_suggested_args_falls_back_to_all_passed_for_full_rerun(self) -> None:
        self.assertEqual(
            manual_beta_checklist_suggested_args(
                [
                    "arbitrary_factual_question",
                    "arbitrary_explanation_question",
                    "casual_chat_question",
                    "blocked_state_question",
                    "grounded_docs_question",
                    "mixed_question_command",
                    "provider_unavailable_path",
                ]
            ),
            "--all-passed",
        )

    def test_manual_beta_checklist_suggested_args_can_force_full_rerun(self) -> None:
        self.assertEqual(
            manual_beta_checklist_suggested_args(
                ["blocked_state_question", "provider_unavailable_path"],
                force_full_rerun=True,
            ),
            "--all-passed",
        )

    def test_format_manual_beta_checklist_record_lists_pending_items_and_next_step(self) -> None:
        record = build_manual_beta_checklist_record(
            passed_item_ids=["arbitrary_factual_question", "grounded_docs_question"],
        )

        text = format_manual_beta_checklist_record(record)

        self.assertIn(
            "pending items: arbitrary_explanation_question, casual_chat_question, blocked_state_question, mixed_question_command, provider_unavailable_path",
            text,
        )
        self.assertIn("next step: complete_manual_beta_checklist", text)
        self.assertIn(
            "next step command: python3 -m qa.manual_beta_checklist --pass arbitrary_explanation_question --pass casual_chat_question --pass blocked_state_question --pass mixed_question_command --pass provider_unavailable_path --write-artifact",
            text,
        )
        self.assertIn("verification doc: docs/manual_verification_commands.md", text)
        self.assertIn("pending scenario guide:", text)
        self.assertIn("  - arbitrary_explanation_question: Arbitrary explanation question", text)
        self.assertIn("    input: why is the sky blue?", text)
        self.assertIn(
            "    env: JARVIS_QA_BACKEND=llm JARVIS_QA_LLM_ENABLED=true JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED=true",
            text,
        )
        self.assertIn(
            "    expected: mode=question; explanatory open-domain answer; provenance=model_knowledge; no fake local sources",
            text,
        )
        self.assertIn("    doc section: Manual beta checklist scripted scenarios", text)


if __name__ == "__main__":
    unittest.main()
