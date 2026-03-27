"""Contract tests for offline QA beta-readiness artifacts."""

from __future__ import annotations

import json
import tempfile
import unittest
import io
import os
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from qa.beta_release_review import build_beta_release_review_record, write_beta_release_review_artifact
from qa.beta_readiness import (
    build_beta_readiness_record,
    format_beta_readiness_record,
    main,
    write_beta_readiness_artifact,
)
from qa.manual_beta_checklist import build_manual_beta_checklist_record, write_manual_beta_checklist_artifact


class BetaReadinessTests(unittest.TestCase):
    """Keep beta-decision helpers deterministic and operator-readable."""

    def test_build_beta_readiness_record_prefers_strict_candidate_when_both_are_green(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_candidate_artifacts(tmpdir, "llm_env", fallback_enabled=True)
            self._write_candidate_artifacts(tmpdir, "llm_env_strict", fallback_enabled=False)
            with self._patch_candidate_paths(tmpdir):
                record = build_beta_readiness_record(
                    environ=self._env(),
                )

        self.assertEqual(record.recommended_candidate, "llm_env_strict")
        self.assertEqual(record.chosen_candidate, "llm_env_strict")
        self.assertEqual(record.candidate_selection_source, "recommended_candidate")
        self.assertEqual(record.technical_ready_candidates, ["llm_env", "llm_env_strict"])
        self.assertFalse(record.beta_ready)
        self.assertEqual(record.next_step_kind, "complete_manual_beta_checklist")
        self.assertEqual(
            record.next_step_command,
            "python3 -m qa.manual_beta_checklist --all-passed --write-artifact",
        )
        self.assertEqual(
            record.next_step_reason,
            "manual beta checklist evidence is missing, incomplete, or stale",
        )
        self.assertIn("manual verification checklist is not completed", record.blockers)
        self.assertIn("manual beta checklist artifact is missing or incomplete", record.blockers)
        self.assertIn("beta release review artifact is missing or incomplete", record.blockers)
        self.assertIn("product approval for beta_question_default is missing", record.blockers)
        self.assertIn("arbitrary_factual_question", record.manual_checklist_pending_items)
        self.assertIn("provider_unavailable_path", record.manual_checklist_pending_items)
        self.assertEqual(
            record.manual_checklist_pending_item_details[0],
            {
                "item_id": "arbitrary_factual_question",
                "label": "Arbitrary factual question",
                "prompt": "who is the president of France?",
                "expected": "mode=question; answer-kind=open_domain_model; provenance=model_knowledge; no fake local sources",
                "env_hint": "JARVIS_QA_BACKEND=llm JARVIS_QA_LLM_ENABLED=true JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED=true",
                "doc_section": "Manual beta checklist scripted scenarios",
            },
        )
        self.assertEqual(
            record.manual_checklist_command,
            "python3 -m qa.manual_beta_checklist --all-passed --write-artifact",
        )
        self.assertEqual(record.manual_checklist_guide_command, "python3 -m qa.manual_beta_checklist")
        self.assertEqual(record.manual_checklist_verification_doc, "docs/manual_verification_commands.md")
        self.assertEqual(
            record.release_review_pending_checks,
            ["latency_review", "cost_review", "operator_signoff", "product_approval"],
        )
        self.assertEqual(len(record.candidate_states), 2)
        self.assertTrue(all(candidate_state.technical_ready for candidate_state in record.candidate_states))

    def test_write_beta_readiness_artifact_persists_ready_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_candidate_artifacts(tmpdir, "llm_env", fallback_enabled=True)
            self._write_candidate_artifacts(tmpdir, "llm_env_strict", fallback_enabled=False)
            self._write_manual_artifact(tmpdir, all_passed=True)
            self._write_release_review_artifact(tmpdir, candidate_profile="llm_env_strict", all_completed=True)
            with self._patch_candidate_paths(tmpdir):
                record = build_beta_readiness_record(
                    candidate_profile="llm_env_strict",
                    notes="Latest artifacts are green; awaiting explicit default switch meeting.",
                    environ=self._env(),
                )
                artifact_path = Path(tmpdir) / "beta_readiness.json"
                resolved_path = write_beta_readiness_artifact(record, artifact_path=artifact_path)
                payload = json.loads(artifact_path.read_text(encoding="utf-8"))

        self.assertTrue(record.beta_ready)
        self.assertEqual(record.candidate_selection_source, "explicit")
        self.assertEqual(resolved_path, artifact_path)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["runner"], "qa.beta_readiness")
        self.assertEqual(payload["report"]["chosen_candidate"], "llm_env_strict")
        self.assertEqual(payload["report"]["candidate_selection_source"], "explicit")
        self.assertTrue(payload["report"]["beta_ready"])
        self.assertEqual(payload["report"]["manual_checklist_artifact_status"], "complete")
        self.assertTrue(payload["report"]["manual_checklist_artifact_completed"])
        self.assertEqual(payload["report"]["manual_checklist_pending_items"], [])
        self.assertEqual(payload["report"]["manual_checklist_pending_item_details"], [])
        self.assertTrue(payload["report"]["manual_checklist_artifact_created_at"])
        self.assertTrue(payload["report"]["manual_checklist_artifact_sha256"])
        self.assertEqual(payload["report"]["release_review_artifact_status"], "complete")
        self.assertTrue(payload["report"]["release_review_artifact_completed"])
        self.assertEqual(payload["report"]["release_review_artifact_candidate"], "llm_env_strict")
        self.assertTrue(payload["report"]["release_review_artifact_consistent"])
        self.assertEqual(payload["report"]["release_review_pending_checks"], [])
        self.assertEqual(payload["report"]["manual_checklist_command"], "python3 -m qa.manual_beta_checklist --all-passed --write-artifact")
        self.assertEqual(payload["report"]["manual_checklist_guide_command"], "python3 -m qa.manual_beta_checklist")
        self.assertEqual(payload["report"]["manual_checklist_verification_doc"], "docs/manual_verification_commands.md")
        self.assertEqual(
            payload["report"]["release_review_command"],
            "python3 -m qa.beta_release_review --candidate-profile llm_env_strict --latency-reviewed --cost-reviewed --operator-signoff --product-approval --write-artifact",
        )
        self.assertEqual(payload["report"]["next_step_kind"], "write_beta_readiness_artifact")
        self.assertEqual(
            payload["report"]["next_step_reason"],
            "supporting evidence is complete; record the consolidated beta readiness artifact",
        )
        self.assertEqual(
            payload["report"]["next_step_command"],
            "python3 -m qa.beta_readiness --candidate-profile llm_env_strict --write-artifact",
        )
        self.assertTrue(payload["report"]["release_review_artifact_created_at"])
        self.assertTrue(payload["report"]["release_review_artifact_sha256"])
        self.assertTrue(payload["report"]["candidate_states"]["llm_env_strict"]["smoke_artifact_created_at"])
        self.assertTrue(payload["report"]["candidate_states"]["llm_env_strict"]["smoke_artifact_sha256"])
        self.assertEqual(
            payload["report"]["candidate_states"]["llm_env_strict"]["stability_gate_passes"],
            2,
        )

    def test_format_beta_readiness_record_lists_blockers_and_candidate_states(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_candidate_artifacts(tmpdir, "llm_env", fallback_enabled=True)
            self._write_candidate_artifacts(tmpdir, "llm_env_strict", fallback_enabled=False)
            self._write_manual_artifact(tmpdir, all_passed=True)
            with self._patch_candidate_paths(tmpdir):
                record = build_beta_readiness_record(
                    candidate_profile="llm_env",
                    environ=self._env(),
                )

        text = format_beta_readiness_record(record)
        self.assertIn("JARVIS QA Beta Readiness", text)
        self.assertIn("recommended candidate: llm_env_strict", text)
        self.assertIn("chosen candidate: llm_env", text)
        self.assertIn("candidate selection: explicit", text)
        self.assertIn("beta_question_default ready: no", text)
        self.assertIn("manual checklist artifact: complete(7/7)", text)
        self.assertIn("manual checklist pending items: none", text)
        self.assertIn("manual checklist guide command: python3 -m qa.manual_beta_checklist", text)
        self.assertIn("manual checklist verification doc: docs/manual_verification_commands.md", text)
        self.assertIn("manual checklist scenario guide: none", text)
        self.assertIn("release review artifact: missing", text)
        self.assertIn(
            "release review pending checks: latency_review, cost_review, operator_signoff, product_approval",
            text,
        )
        self.assertIn(
            "release review command: python3 -m qa.beta_release_review --candidate-profile llm_env --latency-reviewed --cost-reviewed --operator-signoff --product-approval --write-artifact",
            text,
        )
        self.assertIn("next step: record_beta_release_review", text)
        self.assertIn(
            "next step reason: beta release review evidence is missing, incomplete, stale, or tied to a different candidate/manual snapshot",
            text,
        )
        self.assertIn(
            "next step command: python3 -m qa.beta_release_review --candidate-profile llm_env --latency-reviewed --cost-reviewed --operator-signoff --product-approval --write-artifact",
            text,
        )
        self.assertIn("latency review is not completed", text)
        self.assertIn("candidate states:", text)
        self.assertIn("llm_env_strict: technical-ready=yes; smoke=green; stability=green(2/2); fallback=off", text)

    def test_format_beta_readiness_record_lists_manual_scenario_guide_when_checklist_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_candidate_artifacts(tmpdir, "llm_env", fallback_enabled=True)
            self._write_candidate_artifacts(tmpdir, "llm_env_strict", fallback_enabled=False)
            with self._patch_candidate_paths(tmpdir):
                record = build_beta_readiness_record(
                    environ=self._env(),
                )

        text = format_beta_readiness_record(record)
        self.assertIn("manual checklist scenario guide:", text)
        self.assertIn("  - arbitrary_factual_question: Arbitrary factual question", text)
        self.assertIn("    input: who is the president of France?", text)
        self.assertIn(
            "    env: JARVIS_QA_BACKEND=llm JARVIS_QA_LLM_ENABLED=true JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED=true",
            text,
        )
        self.assertIn(
            "    expected: mode=question; answer-kind=open_domain_model; provenance=model_knowledge; no fake local sources",
            text,
        )

    def test_build_beta_readiness_record_blocks_stale_release_review_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_candidate_artifacts(tmpdir, "llm_env", fallback_enabled=True)
            self._write_candidate_artifacts(tmpdir, "llm_env_strict", fallback_enabled=False)
            self._write_manual_artifact(tmpdir, all_passed=True)
            self._write_release_review_artifact(tmpdir, candidate_profile="llm_env_strict", all_completed=True)
            self._write_manual_artifact(tmpdir, all_passed=False)
            with self._patch_candidate_paths(tmpdir):
                record = build_beta_readiness_record(
                    candidate_profile="llm_env_strict",
                    environ=self._env(),
                )

        self.assertFalse(record.release_review_artifact_consistent)
        self.assertIn(
            "beta release review artifact is stale against the latest manual checklist evidence",
            record.blockers,
        )
        self.assertIn(
            "recorded manual checklist artifact fingerprint no longer matches the latest artifact",
            record.release_review_artifact_consistency_reason or "",
        )
        self.assertEqual(record.next_step_kind, "complete_manual_beta_checklist")
        self.assertEqual(
            record.next_step_command,
            "python3 -m qa.manual_beta_checklist --all-passed --write-artifact",
        )

    def test_build_beta_readiness_record_blocks_stale_manual_and_release_review_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_candidate_artifacts(tmpdir, "llm_env", fallback_enabled=True)
            self._write_candidate_artifacts(tmpdir, "llm_env_strict", fallback_enabled=False)
            self._write_manual_artifact(tmpdir, all_passed=True, created_at="2026-03-24T00:00:00+00:00")
            self._write_release_review_artifact(
                tmpdir,
                candidate_profile="llm_env_strict",
                all_completed=True,
                created_at="2026-03-24T00:00:00+00:00",
            )
            with self._patch_candidate_paths(tmpdir), patch(
                "qa.beta_readiness._artifact_now",
                return_value=datetime(2026, 3, 26, tzinfo=timezone.utc),
            ):
                record = build_beta_readiness_record(
                    candidate_profile="llm_env_strict",
                    environ=self._env(),
                )

        self.assertFalse(record.manual_checklist_completed)
        self.assertFalse(record.manual_checklist_artifact_fresh)
        self.assertFalse(record.release_review_artifact_fresh)
        self.assertFalse(record.release_review_artifact_consistent)
        self.assertIn("manual beta checklist artifact is stale", record.blockers)
        self.assertIn("beta release review artifact is stale", record.blockers)
        self.assertIn(
            "beta release review artifact is stale against the latest manual checklist evidence",
            record.blockers,
        )
        self.assertEqual(record.release_review_artifact_consistency_reason, "latest manual checklist artifact is stale")
        self.assertEqual(record.next_step_kind, "complete_manual_beta_checklist")
        self.assertEqual(
            record.next_step_command,
            "python3 -m qa.manual_beta_checklist --all-passed --write-artifact",
        )
        self.assertIn("manual checklist artifact: complete(7/7); fresh=no (48.0h)", format_beta_readiness_record(record))

    def test_build_beta_readiness_record_suggests_final_write_command_when_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_candidate_artifacts(tmpdir, "llm_env", fallback_enabled=True)
            self._write_candidate_artifacts(tmpdir, "llm_env_strict", fallback_enabled=False)
            self._write_manual_artifact(tmpdir, all_passed=True)
            self._write_release_review_artifact(tmpdir, candidate_profile="llm_env_strict", all_completed=True)
            with self._patch_candidate_paths(tmpdir):
                record = build_beta_readiness_record(
                    candidate_profile="llm_env_strict",
                    environ=self._env(),
                )

        self.assertTrue(record.beta_ready)
        self.assertEqual(record.candidate_selection_source, "explicit")
        self.assertEqual(record.next_step_kind, "write_beta_readiness_artifact")
        self.assertEqual(
            record.next_step_reason,
            "supporting evidence is complete; record the consolidated beta readiness artifact",
        )
        self.assertEqual(
            record.next_step_command,
            "python3 -m qa.beta_readiness --candidate-profile llm_env_strict --write-artifact",
        )

    def test_main_rejects_legacy_release_decision_flags(self) -> None:
        legacy_flags = (
            "--manual-checklist",
            "--latency-reviewed",
            "--cost-reviewed",
            "--operator-signoff",
            "--product-approval",
        )
        for flag in legacy_flags:
            with self.subTest(flag=flag):
                with redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as raised:
                        main([flag])

            self.assertEqual(raised.exception.code, 2)

    def test_main_rejects_write_artifact_without_explicit_candidate(self) -> None:
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                main(["--write-artifact"])

        self.assertEqual(raised.exception.code, 2)

    def test_main_reports_current_recorded_beta_readiness_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_candidate_artifacts(tmpdir, "llm_env", fallback_enabled=True)
            self._write_candidate_artifacts(tmpdir, "llm_env_strict", fallback_enabled=False)
            self._write_manual_artifact(tmpdir, all_passed=True)
            self._write_release_review_artifact(tmpdir, candidate_profile="llm_env_strict", all_completed=True)
            artifact_path = Path(tmpdir) / "beta_readiness.json"
            with self._patch_candidate_paths(tmpdir):
                record = build_beta_readiness_record(
                    candidate_profile="llm_env_strict",
                    environ=self._env(),
                )
                write_beta_readiness_artifact(record, artifact_path=artifact_path)
                stdout = io.StringIO()
                with patch.dict(os.environ, self._env(), clear=False):
                    with redirect_stdout(stdout):
                        exit_code = main([])

        text = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("next step: beta_readiness_artifact_already_recorded", text)
        self.assertIn(
            f"next step reason: current beta readiness artifact is already recorded at {artifact_path} and remains consistent with the latest evidence",
            text,
        )
        self.assertIn("next step command: n/a", text)

    def test_write_beta_readiness_artifact_rejects_blocked_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_candidate_artifacts(tmpdir, "llm_env", fallback_enabled=True)
            self._write_candidate_artifacts(tmpdir, "llm_env_strict", fallback_enabled=False)
            with self._patch_candidate_paths(tmpdir):
                record = build_beta_readiness_record(
                    candidate_profile="llm_env_strict",
                    environ=self._env(),
                )

            artifact_path = Path(tmpdir) / "beta_readiness.json"
            with self.assertRaisesRegex(ValueError, "blocked; refusing to write final artifact"):
                write_beta_readiness_artifact(record, artifact_path=artifact_path)

        self.assertFalse(artifact_path.exists())

    def _env(self) -> dict[str, str]:
        return {
            "JARVIS_QA_BACKEND": "llm",
            "JARVIS_QA_LLM_ENABLED": "true",
            "JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED": "true",
            "JARVIS_QA_LLM_STRICT_MODE": "true",
            "OPENAI_API_KEY": "test-key",
        }

    def _write_candidate_artifacts(self, tmpdir: str, candidate_profile: str, *, fallback_enabled: bool) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        smoke_path = Path(tmpdir) / f"openai_live_smoke_{candidate_profile}.json"
        smoke_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "runner": "tests.smoke_openai_responses_provider_live",
                    "created_at": timestamp,
                    "question": "Why is the sky blue?",
                    "success": True,
                    "issues": [],
                    "error": None,
                    "open_domain_verified": True,
                    "diagnostics": {
                        "provider": "openai_responses",
                        "model": "gpt-5-nano",
                        "strict_mode": True,
                        "fallback_enabled": fallback_enabled,
                        "open_domain_enabled": True,
                        "answer_kind": "open_domain_model",
                        "provenance": "model_knowledge",
                        "source_count": 0,
                        "deterministic_fallback": False,
                    },
                }
            ),
            encoding="utf-8",
        )
        stability_path = Path(tmpdir) / f"rollout_stability_{candidate_profile}.json"
        stability_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "runner": "qa.rollout_stability",
                    "created_at": timestamp,
                    "report": {
                        "baseline_profile": "deterministic",
                        "candidate_profile": candidate_profile,
                        "runs_requested": 2,
                        "gate_passes": 2,
                        "runs": [],
                        "blocker_counts": {},
                        "failed_case_counts": {},
                        "fallback_case_counts": {},
                    },
                }
            ),
            encoding="utf-8",
        )

    def _write_manual_artifact(self, tmpdir: str, *, all_passed: bool, created_at: str | None = None) -> None:
        artifact_path = Path(tmpdir) / "manual_beta_checklist.json"
        record = build_manual_beta_checklist_record(all_passed=all_passed)
        write_manual_beta_checklist_artifact(record, artifact_path=artifact_path)
        if created_at is not None:
            payload = json.loads(artifact_path.read_text(encoding="utf-8"))
            payload["created_at"] = created_at
            artifact_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _write_release_review_artifact(
        self,
        tmpdir: str,
        *,
        candidate_profile: str,
        all_completed: bool,
        created_at: str | None = None,
    ) -> None:
        artifact_path = Path(tmpdir) / "beta_release_review.json"
        manual_path = Path(tmpdir) / "manual_beta_checklist.json"
        with patch("qa.beta_release_review.manual_beta_checklist_artifact_path", return_value=manual_path):
            record = build_beta_release_review_record(candidate_profile=candidate_profile, all_completed=all_completed)
            write_beta_release_review_artifact(record, artifact_path=artifact_path)
        if created_at is not None:
            payload = json.loads(artifact_path.read_text(encoding="utf-8"))
            payload["created_at"] = created_at
            artifact_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _patch_candidate_paths(self, tmpdir: str):
        smoke_paths = {
            "llm_env": Path(tmpdir) / "openai_live_smoke_llm_env.json",
            "llm_env_strict": Path(tmpdir) / "openai_live_smoke_llm_env_strict.json",
        }
        stability_paths = {
            "llm_env": Path(tmpdir) / "rollout_stability_llm_env.json",
            "llm_env_strict": Path(tmpdir) / "rollout_stability_llm_env_strict.json",
        }
        manual_path = Path(tmpdir) / "manual_beta_checklist.json"
        release_review_path = Path(tmpdir) / "beta_release_review.json"
        return patch.multiple(
            "qa.beta_readiness",
            live_smoke_artifact_path_for_candidate=lambda candidate_profile: smoke_paths[candidate_profile],
            rollout_stability_artifact_path_for_candidate=lambda candidate_profile: stability_paths[candidate_profile],
            manual_beta_checklist_artifact_path=lambda: manual_path,
            beta_release_review_artifact_path=lambda: release_review_path,
            beta_readiness_artifact_path=lambda: Path(tmpdir) / "beta_readiness.json",
        )


if __name__ == "__main__":
    unittest.main()
