"""Deterministic parser/validator contract fixtures for high-risk phrase overlaps."""

from __future__ import annotations

import unittest
from pathlib import Path

from context.session_context import SessionContext
from parser.command_parser import parse_command
from validator.command_validator import validate_command


class ParserValidatorContractTests(unittest.TestCase):
    """Lock parse/validate precedence and error routing for overlapping command families."""

    def setUp(self) -> None:
        self.session_context = SessionContext()
        repo_name = Path.cwd().name
        seeded_folder_command = parse_command(f"open {repo_name} folder", self.session_context)
        folder_target = list(seeded_folder_command.targets or [])[0]
        self.session_context.set_recent_targets([folder_target])
        self.session_context.set_recent_folder_context(folder_target)
        self.session_context.set_recent_search_results(
            matches=[
                {"name": "roadmap.md", "path": "/tmp/demo/roadmap.md", "type": "file"},
                {"name": "notes.md", "path": "/tmp/demo/notes.md", "type": "file"},
            ],
            query="markdown files",
            scope_path="/tmp/demo",
        )

    def test_list_windows_phrase_wins_over_open_family(self) -> None:
        command = parse_command("show Safari windows", self.session_context)
        validation = validate_command(command)

        self.assertEqual(getattr(command.intent, "value", ""), "list_windows")
        self.assertEqual(
            [(getattr(target.type, "value", ""), target.name) for target in command.targets],
            [("application", "Safari")],
        )
        self.assertTrue(validation.valid)

    def test_open_latest_markdown_in_folder_maps_to_search_then_open_shape(self) -> None:
        command = parse_command("open the latest markdown file in this folder", self.session_context)
        validation = validate_command(command)

        self.assertEqual(getattr(command.intent, "value", ""), "search_local")
        self.assertEqual(command.parameters.get("open_requested"), True)
        self.assertEqual(command.parameters.get("sort_hint"), "latest")
        self.assertEqual(command.parameters.get("file_type"), "markdown")
        self.assertTrue(validation.valid)

    def test_open_project_in_code_maps_to_prepare_workspace(self) -> None:
        repo_name = Path.cwd().name
        command = parse_command(f"open {repo_name} in code", self.session_context)
        validation = validate_command(command)

        self.assertEqual(getattr(command.intent, "value", ""), "prepare_workspace")
        self.assertTrue(validation.valid)
        target_pairs = {(getattr(target.type, "value", ""), target.name, target.path) for target in command.targets}
        self.assertIn(("application", "Visual Studio Code", None), target_pairs)
        self.assertIn(("folder", repo_name, str(Path.cwd())), target_pairs)

    def test_run_alias_maps_to_open_app(self) -> None:
        command = parse_command("run telegram", self.session_context)
        validation = validate_command(command)

        self.assertEqual(getattr(command.intent, "value", ""), "open_app")
        self.assertTrue(validation.valid)
        self.assertEqual(
            [(getattr(target.type, "value", ""), target.name) for target in command.targets],
            [("application", "Telegram")],
        )

    def test_open_dot_net_host_maps_to_open_website(self) -> None:
        command = parse_command("open example.net", self.session_context)
        validation = validate_command(command)

        self.assertEqual(getattr(command.intent, "value", ""), "open_website")
        self.assertTrue(validation.valid)
        target = list(command.targets or [])[0]
        self.assertEqual((getattr(target.type, "value", ""), target.name), ("browser", "Safari"))
        self.assertEqual((target.metadata or {}).get("url"), "https://example.net")

    def test_open_filename_with_extension_maps_to_open_file(self) -> None:
        command = parse_command("open notes.txt", self.session_context)
        validation = validate_command(command)

        self.assertEqual(getattr(command.intent, "value", ""), "open_file")
        self.assertTrue(validation.valid)
        self.assertEqual(
            [(getattr(target.type, "value", ""), target.name, target.path) for target in command.targets],
            [("file", "notes.txt", None)],
        )

    def test_russian_notes_alias_maps_to_notes_application(self) -> None:
        command = parse_command("open заметки", self.session_context)
        validation = validate_command(command)

        self.assertEqual(getattr(command.intent, "value", ""), "open_app")
        self.assertTrue(validation.valid)
        self.assertEqual(
            [(getattr(target.type, "value", ""), target.name) for target in command.targets],
            [("application", "Notes")],
        )

    def test_ambiguous_open_maps_to_multiple_matches(self) -> None:
        command = parse_command("open telegram or safari", self.session_context)
        validation = validate_command(command)

        self.assertEqual(getattr(command.intent, "value", ""), "open_app")
        self.assertFalse(validation.valid)
        self.assertEqual(getattr(validation.error.code, "value", ""), "MULTIPLE_MATCHES")

    def test_explicit_unsupported_window_management_is_not_clarified(self) -> None:
        command = parse_command("close everything except VS Code", self.session_context)
        validation = validate_command(command)

        self.assertEqual(getattr(command.intent, "value", ""), "switch_window")
        self.assertFalse(validation.valid)
        self.assertEqual(getattr(validation.error.code, "value", ""), "UNSUPPORTED_ACTION")

    def test_search_result_index_followup_is_deterministic(self) -> None:
        command = parse_command("open 1", self.session_context)
        validation = validate_command(command)

        self.assertEqual(getattr(command.intent, "value", ""), "open_file")
        self.assertTrue(validation.valid)
        self.assertEqual(
            [(getattr(target.type, "value", ""), target.name, target.path) for target in command.targets],
            [("file", "roadmap.md", "/tmp/demo/roadmap.md")],
        )

    def test_search_result_ambiguous_followup_routes_to_multiple_matches(self) -> None:
        command = parse_command("open that file", self.session_context)
        validation = validate_command(command)

        self.assertEqual(getattr(command.intent, "value", ""), "open_file")
        self.assertFalse(validation.valid)
        self.assertEqual(getattr(validation.error.code, "value", ""), "MULTIPLE_MATCHES")


if __name__ == "__main__":
    unittest.main()
