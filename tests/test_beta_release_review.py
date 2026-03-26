"""Contract tests for the beta release-review artifact."""

from __future__ import annotations

import json
import tempfile
import unittest
import io
from contextlib import redirect_stderr
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from qa.beta_release_review import (
    beta_release_review_artifact_consistency,
    beta_release_review_pending_checks,
    beta_release_review_suggested_args,
    beta_release_review_status,
    build_beta_release_review_record,
    load_beta_release_review_artifact,
    main,
    write_beta_release_review_artifact,
)
from qa.manual_beta_checklist import build_manual_beta_checklist_record, write_manual_beta_checklist_artifact


class BetaReleaseReviewTests(unittest.TestCase):
    """Keep the beta release-review artifact machine-readable and deterministic."""

    def test_build_beta_release_review_record_marks_all_checks_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manual_artifact = self._write_manual_artifact(tmpdir, all_passed=True)
            with patch("qa.beta_release_review.manual_beta_checklist_artifact_path", return_value=manual_artifact):
                record = build_beta_release_review_record(
                    candidate_profile="llm_env_strict",
                    all_completed=True,
                    notes="Latency, cost, sign-off, and approval all recorded.",
                )

        self.assertEqual(record.completed_checks, record.total_checks)
        self.assertTrue(record.all_completed)
        self.assertEqual(record.candidate_profile, "llm_env_strict")
        self.assertEqual(record.candidate_selection_source, "explicit")
        self.assertEqual(record.manual_checklist_artifact_status, "complete")
        self.assertEqual(record.to_dict()["notes"], "Latency, cost, sign-off, and approval all recorded.")

    def test_write_beta_release_review_artifact_persists_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "beta_release_review.json"
            manual_artifact = self._write_manual_artifact(tmpdir, all_passed=True)
            with patch("qa.beta_release_review.manual_beta_checklist_artifact_path", return_value=manual_artifact):
                record = build_beta_release_review_record(
                    candidate_profile="llm_env",
                    latency_review_completed=True,
                    operator_signoff_completed=True,
                    notes="Partial release review.",
                )
            resolved_path = write_beta_release_review_artifact(record, artifact_path=artifact_path)
            payload = json.loads(artifact_path.read_text(encoding="utf-8"))

        self.assertEqual(resolved_path, artifact_path)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["runner"], "qa.beta_release_review")
        self.assertEqual(payload["report"]["candidate_profile"], "llm_env")
        self.assertEqual(payload["report"]["candidate_selection_source"], "explicit")
        self.assertEqual(payload["report"]["completed_checks"], 2)
        self.assertEqual(payload["report"]["manual_checklist_artifact_status"], "complete")
        self.assertFalse(payload["report"]["all_completed"])

    def test_beta_release_review_status_reads_complete_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "beta_release_review.json"
            manual_artifact = self._write_manual_artifact(tmpdir, all_passed=True)
            with patch("qa.beta_release_review.manual_beta_checklist_artifact_path", return_value=manual_artifact), patch(
                "qa.beta_release_review._artifact_now",
                return_value=datetime(2026, 3, 26, tzinfo=timezone.utc),
            ):
                record = build_beta_release_review_record(candidate_profile="llm_env_strict", all_completed=True)
            write_beta_release_review_artifact(record, artifact_path=artifact_path)
            _path, payload, error = load_beta_release_review_artifact(artifact_path)
            status, completed_checks, total_checks, completed, candidate_profile = beta_release_review_status(
                payload,
                error,
            )

        self.assertEqual(status, "complete")
        self.assertEqual((completed_checks, total_checks), (4, 4))
        self.assertTrue(completed)
        self.assertEqual(candidate_profile, "llm_env_strict")

    def test_build_beta_release_review_record_marks_stale_manual_checklist_as_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manual_artifact = self._write_manual_artifact(
                tmpdir,
                all_passed=True,
                created_at="2026-03-24T00:00:00+00:00",
            )
            with patch("qa.beta_release_review.manual_beta_checklist_artifact_path", return_value=manual_artifact), patch(
                "qa.beta_release_review._artifact_now",
                return_value=datetime(2026, 3, 26, tzinfo=timezone.utc),
            ):
                record = build_beta_release_review_record(candidate_profile="llm_env_strict", all_completed=True)

        self.assertEqual(record.manual_checklist_artifact_status, "complete")
        self.assertFalse(record.manual_checklist_artifact_fresh)
        self.assertFalse(record.all_completed)

    def test_release_review_consistency_detects_manual_checklist_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manual_artifact = self._write_manual_artifact(tmpdir, all_passed=True)
            with patch("qa.beta_release_review.manual_beta_checklist_artifact_path", return_value=manual_artifact):
                record = build_beta_release_review_record(candidate_profile="llm_env_strict", all_completed=True)
            artifact_path = Path(tmpdir) / "beta_release_review.json"
            write_beta_release_review_artifact(record, artifact_path=artifact_path)
            _artifact_path, artifact_payload, artifact_error = load_beta_release_review_artifact(artifact_path)
            manual_artifact.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": "qa.manual_beta_checklist",
                        "created_at": "2026-03-26T00:00:00+00:00",
                        "report": {
                            "checklist_id": "beta_question_default",
                            "passed_items": 6,
                            "total_items": 7,
                            "all_passed": False,
                            "items": {},
                            "notes": "",
                        },
                    }
                ),
                encoding="utf-8",
            )
            manual_payload = json.loads(manual_artifact.read_text(encoding="utf-8"))
            consistent, reason = beta_release_review_artifact_consistency(
                artifact_payload=artifact_payload,
                manual_checklist_artifact_payload=manual_payload,
                manual_checklist_artifact_path=manual_artifact,
                manual_checklist_artifact_error=artifact_error,
                expected_candidate="llm_env_strict",
            )

            self.assertFalse(consistent)
            self.assertEqual(
                reason,
                "recorded manual checklist artifact fingerprint no longer matches the latest artifact",
            )

    def test_release_review_consistency_rejects_stale_manual_checklist(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manual_artifact = self._write_manual_artifact(
                tmpdir,
                all_passed=True,
                created_at="2026-03-24T00:00:00+00:00",
            )
            with patch("qa.beta_release_review.manual_beta_checklist_artifact_path", return_value=manual_artifact), patch(
                "qa.beta_release_review._artifact_now",
                return_value=datetime(2026, 3, 24, tzinfo=timezone.utc),
            ):
                record = build_beta_release_review_record(candidate_profile="llm_env_strict", all_completed=True)
            artifact_path = Path(tmpdir) / "beta_release_review.json"
            write_beta_release_review_artifact(record, artifact_path=artifact_path)
            _artifact_path, artifact_payload, artifact_error = load_beta_release_review_artifact(artifact_path)
            manual_payload = json.loads(manual_artifact.read_text(encoding="utf-8"))
            with patch(
                "qa.beta_release_review._artifact_now",
                return_value=datetime(2026, 3, 26, tzinfo=timezone.utc),
            ):
                consistent, reason = beta_release_review_artifact_consistency(
                    artifact_payload=artifact_payload,
                    manual_checklist_artifact_payload=manual_payload,
                    manual_checklist_artifact_path=manual_artifact,
                    manual_checklist_artifact_error=artifact_error,
                    expected_candidate="llm_env_strict",
                )

            self.assertFalse(consistent)
            self.assertEqual(reason, "latest manual checklist artifact is stale")

    def test_release_review_consistency_rejects_missing_candidate_selection_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manual_artifact = self._write_manual_artifact(tmpdir, all_passed=True)
            with patch("qa.beta_release_review.manual_beta_checklist_artifact_path", return_value=manual_artifact):
                record = build_beta_release_review_record(candidate_profile="llm_env_strict", all_completed=True)
            artifact_path = Path(tmpdir) / "beta_release_review.json"
            write_beta_release_review_artifact(record, artifact_path=artifact_path)
            payload = json.loads(artifact_path.read_text(encoding="utf-8"))
            del payload["report"]["candidate_selection_source"]
            artifact_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            _artifact_path, artifact_payload, artifact_error = load_beta_release_review_artifact(artifact_path)
            manual_payload = json.loads(manual_artifact.read_text(encoding="utf-8"))

            consistent, reason = beta_release_review_artifact_consistency(
                artifact_payload=artifact_payload,
                manual_checklist_artifact_payload=manual_payload,
                manual_checklist_artifact_path=manual_artifact,
                manual_checklist_artifact_error=artifact_error,
                expected_candidate="llm_env_strict",
            )

        self.assertFalse(consistent)
        self.assertEqual(reason, "recorded beta release review candidate selection source is missing")

    def test_beta_release_review_pending_checks_returns_remaining_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manual_artifact = self._write_manual_artifact(tmpdir, all_passed=True)
            with patch("qa.beta_release_review.manual_beta_checklist_artifact_path", return_value=manual_artifact):
                record = build_beta_release_review_record(
                    candidate_profile="llm_env_strict",
                    latency_review_completed=True,
                    product_approval_completed=True,
                )

        pending_checks = beta_release_review_pending_checks({"report": record.to_dict()}, None)

        self.assertEqual(
            pending_checks,
            ["cost_review", "operator_signoff"],
        )

    def test_beta_release_review_suggested_args_uses_incremental_flags(self) -> None:
        self.assertEqual(
            beta_release_review_suggested_args(["cost_review", "operator_signoff"]),
            "--cost-reviewed --operator-signoff",
        )

    def test_beta_release_review_suggested_args_falls_back_to_full_review_flags(self) -> None:
        self.assertEqual(
            beta_release_review_suggested_args([]),
            "--latency-reviewed --cost-reviewed --operator-signoff --product-approval",
        )

    def test_beta_release_review_suggested_args_can_force_full_rerun(self) -> None:
        self.assertEqual(
            beta_release_review_suggested_args(
                ["cost_review", "operator_signoff"],
                force_full_rerun=True,
            ),
            "--latency-reviewed --cost-reviewed --operator-signoff --product-approval",
        )

    def test_main_rejects_write_artifact_without_explicit_candidate(self) -> None:
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                main(["--write-artifact"])

        self.assertEqual(raised.exception.code, 2)

    def _write_manual_artifact(
        self,
        tmpdir: str,
        *,
        all_passed: bool,
        created_at: str | None = None,
    ) -> Path:
        artifact_path = Path(tmpdir) / "manual_beta_checklist.json"
        record = build_manual_beta_checklist_record(all_passed=all_passed)
        write_manual_beta_checklist_artifact(record, artifact_path=artifact_path)
        if created_at is not None:
            payload = json.loads(artifact_path.read_text(encoding="utf-8"))
            payload["created_at"] = created_at
            artifact_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return artifact_path


if __name__ == "__main__":
    unittest.main()
