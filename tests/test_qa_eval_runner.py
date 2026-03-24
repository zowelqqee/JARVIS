"""Eval-harness contract tests for centralized QA cases."""

from __future__ import annotations

import unittest

from evals.run_qa_eval import DEFAULT_CORPUS_PATH, format_report, load_qa_eval_cases, run_eval_cases, select_eval_cases


class QaEvalRunnerTests(unittest.TestCase):
    """Lock the centralized corpus and eval runner behavior."""

    def test_corpus_loads_with_unique_ids_and_expected_case_types(self) -> None:
        cases = load_qa_eval_cases(DEFAULT_CORPUS_PATH)

        self.assertTrue(cases)
        self.assertEqual(len({case.id for case in cases}), len(cases))
        self.assertTrue(any(case.case_type == "interaction" for case in cases))
        self.assertTrue(any(case.case_type == "voice" for case in cases))
        self.assertTrue(any(case.case_type == "live_smoke" for case in cases))

    def test_full_corpus_runs_green_under_default_profile(self) -> None:
        report = run_eval_cases(load_qa_eval_cases(DEFAULT_CORPUS_PATH))

        self.assertEqual(report.failed_cases, 0)
        self.assertEqual(report.total_cases, len(report.results))
        self.assertGreater(report.routing_total, 0)
        self.assertGreater(report.grounding_total, 0)
        self.assertGreater(report.command_regression_total, 0)
        self.assertIn("failed cases: none", format_report(report))

    def test_case_selection_filters_corpus(self) -> None:
        cases = load_qa_eval_cases(DEFAULT_CORPUS_PATH)

        selected = select_eval_cases(cases, ["route_open_app_command", "voice_repeat_question"])
        report = run_eval_cases(selected)

        self.assertEqual([case.id for case in selected], ["route_open_app_command", "voice_repeat_question"])
        self.assertEqual(report.total_cases, 2)
        self.assertEqual(report.failed_cases, 0)

    def test_default_profile_can_force_llm_fallback_path(self) -> None:
        cases = load_qa_eval_cases(DEFAULT_CORPUS_PATH)
        selected = select_eval_cases(cases, ["route_capabilities_question"])

        report = run_eval_cases(selected, default_profile="llm_missing_key_fallback")

        self.assertEqual(report.failed_cases, 0)
        self.assertIn("LLM backend fallback", str(report.results[0].details.get("actual_warning", "")))


if __name__ == "__main__":
    unittest.main()
