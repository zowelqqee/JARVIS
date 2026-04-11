"""Widget tests for structured desktop transcript rendering."""

from __future__ import annotations

import importlib.util
import unittest

from desktop.backend.view_models import (
    AnswerSourceViewModel,
    CommandProgressViewModel,
    EntrySurfaceViewModel,
    PromptActionViewModel,
    ResultListItemViewModel,
    ResultListViewModel,
    SourceAttributionViewModel,
    TranscriptEntry,
)


_PYSIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None


@unittest.skipUnless(_PYSIDE6_AVAILABLE, "PySide6 is not installed in the active environment.")
class ConversationViewTests(unittest.TestCase):
    """Coverage for the structured transcript rendering widget."""

    def test_question_surface_renders_summary_sources_and_evidence(self) -> None:
        from PySide6.QtWidgets import QLabel

        from desktop.app.application import build_application
        from desktop.shell.widgets.conversation_view import ConversationView

        app = build_application([])
        self.addCleanup(app.quit)

        view = ConversationView()
        view.set_entries(
            [
                TranscriptEntry(
                    role="assistant",
                    text="JARVIS can answer grounded repo questions.",
                    entry_kind="answer",
                    surface=EntrySurfaceViewModel(
                        surface_kind="question_answer",
                        answer_summary="Grounded repo help.",
                        sources=(
                            AnswerSourceViewModel(
                                path="/Users/test/JARVIS/docs/repo_structure.md",
                                label="Repo Structure",
                            ),
                        ),
                        source_attributions=(
                            SourceAttributionViewModel(
                                source_path="/Users/test/JARVIS/docs/repo_structure.md",
                                source_label="Repo Structure",
                                support="Maps responsibilities to modules.",
                            ),
                        ),
                    ),
                )
            ]
        )

        widget = view.list_widget.itemWidget(view.list_widget.item(0))
        self.assertIsNotNone(widget)
        texts = [label.text() for label in widget.findChildren(QLabel)]
        self.assertIn("Grounded repo help.", texts)
        self.assertIn("Grounding", texts)
        self.assertIn("• Repo Structure", texts)
        self.assertIn("Why These Sources", texts)
        self.assertIn("• Repo Structure: Maps responsibilities to modules.", texts)

    def test_command_surface_renders_progress_and_result_list(self) -> None:
        from PySide6.QtWidgets import QLabel

        from desktop.app.application import build_application
        from desktop.shell.widgets.conversation_view import ConversationView

        app = build_application([])
        self.addCleanup(app.quit)

        view = ConversationView()
        view.set_entries(
            [
                TranscriptEntry(
                    role="assistant",
                    text="Found 2 matches in JARVIS.",
                    entry_kind="result",
                    surface=EntrySurfaceViewModel(
                        surface_kind="command_completion",
                        command_progress=CommandProgressViewModel(
                            runtime_state="completed",
                            command_summary="search_local markdown files",
                            current_step=None,
                            completed_steps=("search_local markdown files",),
                            next_step_hint=None,
                        ),
                        result_lists=(
                            ResultListViewModel(
                                kind="search_results",
                                title="Search Results",
                                summary='2 matches, query "markdown files", in JARVIS',
                                items=(
                                    ResultListItemViewModel(
                                        item_id="search-1",
                                        title="desktop_shell_plan.md",
                                        subtitle="/Users/test/JARVIS/docs/desktop_shell_plan.md",
                                        detail="file",
                                    ),
                                ),
                            ),
                        ),
                    ),
                )
            ]
        )

        widget = view.list_widget.itemWidget(view.list_widget.item(0))
        self.assertIsNotNone(widget)
        texts = [label.text() for label in widget.findChildren(QLabel)]
        self.assertIn("Runtime Feed", texts)
        self.assertIn("State: Completed", texts)
        self.assertIn("Completed:", texts)
        self.assertIn("• search_local markdown files", texts)
        self.assertIn("Search Results", texts)
        self.assertIn('2 matches, query "markdown files", in JARVIS', texts)
        self.assertIn("• desktop_shell_plan.md", texts)

    def test_prompt_action_chip_emits_submit_text(self) -> None:
        from PySide6.QtWidgets import QPushButton

        from desktop.app.application import build_application
        from desktop.shell.widgets.conversation_view import ConversationView

        app = build_application([])
        self.addCleanup(app.quit)

        view = ConversationView()
        submitted_texts: list[str] = []
        view.prompt_action_requested.connect(submitted_texts.append)
        view.set_entries(
            [
                TranscriptEntry(
                    role="assistant",
                    text="Approve command for Safari?",
                    entry_kind="prompt",
                    surface=EntrySurfaceViewModel(
                        surface_kind="confirmation_prompt",
                        actions=(
                            PromptActionViewModel(action_id="confirm", label="Confirm", submit_text="confirm"),
                            PromptActionViewModel(action_id="cancel", label="Cancel", submit_text="cancel"),
                        ),
                    ),
                )
            ]
        )

        widget = view.list_widget.itemWidget(view.list_widget.item(0))
        self.assertIsNotNone(widget)
        buttons = widget.findChildren(QPushButton)
        self.assertEqual([button.text() for button in buttons], ["Confirm", "Cancel"])
        buttons[0].click()

        self.assertEqual(submitted_texts, ["confirm"])


if __name__ == "__main__":
    unittest.main()
