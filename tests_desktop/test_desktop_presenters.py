"""Tests for Phase 1 desktop presenter surface mapping."""

from __future__ import annotations

from types import SimpleNamespace
import unittest

from desktop.backend.presenters import present_interaction_result


class DesktopPresenterTests(unittest.TestCase):
    def test_question_answer_surface_exposes_sources_and_attributions(self) -> None:
        result = SimpleNamespace(
            interaction_mode="question",
            visibility={
                "interaction_mode": "question",
                "answer_text": "JARVIS can answer grounded repo questions.",
                "answer_summary": "Grounded repo help.",
                "answer_kind": "grounded_local",
                "answer_provenance": "local_sources",
                "answer_sources": ["/repo/docs/repo_structure.md"],
                "answer_source_labels": ["Repo Structure"],
                "answer_source_attributions": [
                    {
                        "source": "/repo/docs/repo_structure.md",
                        "support": "Maps responsibilities to modules.",
                    }
                ],
            },
            metadata={"reason": "question"},
        )

        turn = present_interaction_result("What can you do?", result)

        self.assertEqual(turn.interaction_mode, "question")
        self.assertEqual(len(turn.entries), 1)
        self.assertEqual(turn.entries[0].entry_kind, "answer")
        self.assertIsNotNone(turn.entries[0].surface)
        self.assertEqual(turn.entries[0].surface.surface_kind, "question_answer")
        self.assertEqual(turn.entries[0].surface.answer_summary, "Grounded repo help.")
        self.assertEqual(turn.entries[0].surface.sources[0].label, "Repo Structure")
        self.assertEqual(turn.entries[0].surface.source_attributions[0].support, "Maps responsibilities to modules.")

    def test_confirmation_prompt_surface_exposes_actions_and_command_progress(self) -> None:
        result = SimpleNamespace(
            interaction_mode="command",
            visibility={
                "interaction_mode": "command",
                "runtime_state": "awaiting_confirmation",
                "command_summary": "open_app Safari",
                "current_step": "open_app Safari",
                "completed_steps": ["resolve Safari"],
                "blocked_reason": "Approve command for Safari?",
                "next_step_hint": "Reply yes to continue or no to cancel.",
                "confirmation_request": {
                    "message": "Approve command for Safari?",
                    "boundary_type": "command",
                    "affected_targets": ["Safari"],
                },
                "can_cancel": True,
            },
            metadata={"reason": "command"},
        )

        turn = present_interaction_result("Open Safari", result)

        self.assertIsNotNone(turn.pending_prompt)
        self.assertEqual(turn.pending_prompt.kind, "confirmation")
        self.assertEqual([action.submit_text for action in turn.pending_prompt.actions], ["confirm", "cancel"])
        self.assertEqual(turn.entries[0].surface.surface_kind, "confirmation_prompt")
        self.assertEqual(turn.entries[0].surface.command_progress.runtime_state, "awaiting_confirmation")
        self.assertEqual(turn.entries[0].surface.command_progress.completed_steps, ("resolve Safari",))

    def test_command_completion_surface_exposes_search_results(self) -> None:
        result = SimpleNamespace(
            interaction_mode="command",
            visibility={
                "interaction_mode": "command",
                "runtime_state": "completed",
                "command_summary": "search_local markdown files",
                "completed_steps": ["search_local markdown files"],
                "completion_result": "Found 2 matches in JARVIS.",
                "search_results": {
                    "flow": "search_only",
                    "total_matches": 2,
                    "query": "markdown files",
                    "scope_path": "/Users/test/JARVIS",
                    "matches": [
                        {
                            "name": "desktop_shell_plan.md",
                            "path": "/Users/test/JARVIS/docs/desktop_shell_plan.md",
                            "type": "file",
                        },
                        {
                            "name": "desktop_shell_repo_map.md",
                            "path": "/Users/test/JARVIS/docs/desktop_shell_repo_map.md",
                            "type": "file",
                        },
                    ],
                },
                "can_cancel": False,
            },
            metadata={"reason": "command"},
        )

        turn = present_interaction_result("Search the JARVIS folder for markdown files", result)

        self.assertEqual(turn.entries[0].surface.surface_kind, "command_completion")
        self.assertEqual(len(turn.entries[0].surface.result_lists), 1)
        result_list = turn.entries[0].surface.result_lists[0]
        self.assertEqual(result_list.kind, "search_results")
        self.assertEqual(result_list.title, "Search Results")
        self.assertEqual(result_list.summary, '2 matches, query "markdown files", in JARVIS')
        self.assertEqual(result_list.items[0].title, "desktop_shell_plan.md")
        self.assertEqual(turn.status.result_lists[0].kind, "search_results")
        self.assertEqual(turn.status.completed_steps, ("search_local markdown files",))


    def test_clarification_prompt_surface_exposes_question_and_pending_prompt(self) -> None:
        result = SimpleNamespace(
            interaction_mode="command",
            clarification_request=SimpleNamespace(options=[], code="MISSING_PARAMETER"),
            visibility={
                "interaction_mode": "command",
                "runtime_state": "awaiting_clarification",
                "command_summary": "start_work: Visual Studio Code",
                "clarification_question": "What workspace should I prepare?",
                "blocked_reason": "What workspace should I prepare?",
                "next_step_hint": "Reply with one project folder.",
                "can_cancel": True,
            },
            metadata={"reason": "command"},
        )

        turn = present_interaction_result("start work", result)

        self.assertIsNotNone(turn.pending_prompt)
        self.assertEqual(turn.pending_prompt.kind, "clarification")
        self.assertEqual(turn.pending_prompt.message, "What workspace should I prepare?")
        self.assertEqual(len(turn.entries), 1)
        self.assertEqual(turn.entries[0].entry_kind, "prompt")
        self.assertEqual(turn.entries[0].surface.surface_kind, "clarification_prompt")
        self.assertIsNotNone(turn.entries[0].surface.command_progress)
        self.assertEqual(turn.entries[0].surface.command_progress.runtime_state, "awaiting_clarification")
        self.assertTrue(turn.status.can_cancel)

    def test_command_failure_surface_exposes_failure_message_and_command_progress(self) -> None:
        result = SimpleNamespace(
            interaction_mode="command",
            visibility={
                "interaction_mode": "command",
                "runtime_state": "failed",
                "command_summary": "resume_work: last workspace",
                "completed_steps": [],
                "failure_message": 'The remembered workspace "JARVIS" no longer exists at the stored path. Run "start work on <workspace>" to set a new one.',
                "next_step_hint": "Start work on a workspace first.",
                "can_cancel": False,
            },
            metadata={"reason": "command"},
        )

        turn = present_interaction_result("resume work", result)

        self.assertIsNone(turn.pending_prompt)
        self.assertEqual(len(turn.entries), 1)
        self.assertEqual(turn.entries[0].entry_kind, "error")
        self.assertEqual(turn.entries[0].surface.surface_kind, "command_failure")
        self.assertIsNotNone(turn.entries[0].surface.command_progress)
        self.assertEqual(turn.entries[0].surface.command_progress.runtime_state, "failed")
        self.assertEqual(turn.entries[0].surface.command_progress.command_summary, "resume_work: last workspace")
        self.assertIn("no longer exists", turn.entries[0].text)
        self.assertEqual(turn.status.failure_message, 'The remembered workspace "JARVIS" no longer exists at the stored path. Run "start work on <workspace>" to set a new one.')
        self.assertEqual(turn.status.next_step_hint, "Start work on a workspace first.")

    def test_window_results_surface_exposes_visible_windows(self) -> None:
        result = SimpleNamespace(
            interaction_mode="command",
            visibility={
                "interaction_mode": "command",
                "runtime_state": "completed",
                "command_summary": "list_windows",
                "completed_steps": ["list_windows"],
                "completion_result": "Found 2 visible windows.",
                "window_results": {
                    "total_windows": 2,
                    "filter": None,
                    "windows": [
                        {"app_name": "Visual Studio Code", "window_title": "JARVIS", "window_id": 42},
                        {"app_name": "Safari", "window_title": None, "window_id": 99},
                    ],
                },
                "can_cancel": False,
            },
            metadata={"reason": "command"},
        )

        turn = present_interaction_result("show windows", result)

        self.assertEqual(turn.entries[0].surface.surface_kind, "command_completion")
        self.assertEqual(len(turn.entries[0].surface.result_lists), 1)
        window_list = turn.entries[0].surface.result_lists[0]
        self.assertEqual(window_list.kind, "window_results")
        self.assertEqual(window_list.title, "Visible Windows")
        self.assertIn("2 windows", window_list.summary)
        self.assertEqual(window_list.items[0].title, "JARVIS")
        self.assertEqual(window_list.items[0].subtitle, "Visual Studio Code")
        self.assertEqual(window_list.items[1].title, "Safari")


if __name__ == "__main__":
    unittest.main()
