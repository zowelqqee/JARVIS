"""Contract tests for the manual QA beta checklist artifact."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from qa.manual_beta_checklist import (
    build_manual_beta_checklist_record,
    load_manual_beta_checklist_artifact,
    manual_beta_checklist_status,
    write_manual_beta_checklist_artifact,
)


class ManualBetaChecklistTests(unittest.TestCase):
    """Keep the manual beta checklist machine-readable and deterministic."""

    def test_build_manual_beta_checklist_record_marks_all_items_passed(self) -> None:
        record = build_manual_beta_checklist_record(all_passed=True, notes="All manual checks passed.")

        self.assertEqual(record.passed_items, record.total_items)
        self.assertTrue(record.all_passed)
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


if __name__ == "__main__":
    unittest.main()
