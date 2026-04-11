"""Runtime protocol smoke tests."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from context.session_context import SessionContext
from runtime.runtime_manager import RuntimeManager


def _successful_action_result(step: object) -> SimpleNamespace:
    action = getattr(getattr(step, "action", None), "value", getattr(step, "action", ""))
    target = getattr(step, "target", None)
    return SimpleNamespace(
        action=action,
        success=True,
        target=target,
        details={"stubbed": True},
        error=None,
    )


class ProtocolRuntimeTests(unittest.TestCase):
    """Protect the first protocol integration slice."""

    def setUp(self) -> None:
        self.runtime_manager = RuntimeManager()
        self.session_context = SessionContext()

    def test_clean_slate_protocol_requires_confirmation_then_runs(self) -> None:
        executed_actions: list[str] = []

        def execute_stub(step: object) -> SimpleNamespace:
            executed_actions.append(getattr(getattr(step, "action", None), "value", ""))
            return _successful_action_result(step)

        with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
            blocked_result = self.runtime_manager.handle_input("протокол чистый лист", self.session_context)
            approved_result = self.runtime_manager.handle_input("yes", self.session_context)

        self.assertEqual(blocked_result.runtime_state, "awaiting_confirmation")
        self.assertEqual(blocked_result.command_summary, "run_protocol: Clean Slate")
        self.assertEqual(approved_result.runtime_state, "completed")
        self.assertEqual(
            executed_actions,
            ["close_app", "close_app", "close_app", "close_app"],
        )
        self.assertEqual(approved_result.completion_summary, 'Завершил протокол "чистый лист".')

    def test_i_am_home_protocol_opens_home_soundtrack_and_names_last_project(self) -> None:
        executed_actions: list[str] = []

        def execute_stub(step: object) -> SimpleNamespace:
            executed_actions.append(getattr(getattr(step, "action", None), "value", ""))
            return _successful_action_result(step)

        with tempfile.TemporaryDirectory() as tempdir:
            state_path = Path(tempdir) / "protocol_state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "last_workspace_path": "/tmp/demo",
                        "last_workspace_label": "demo",
                        "last_git_branch": "main",
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"JARVIS_PROTOCOL_STATE_PATH": str(state_path)}, clear=False):
                with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
                    result = self.runtime_manager.handle_input("я дома", self.session_context)
                    persisted = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertEqual(result.runtime_state, "completed")
        self.assertEqual(result.command_summary, "run_protocol: I Am Home")
        self.assertEqual(executed_actions, ["open_website"])
        self.assertEqual(
            result.completion_summary,
            "Приветствую, сэр. Последним у вас был проект demo, ветка main.",
        )
        self.assertEqual(persisted.get("last_protocol_id"), "i_am_home")

    def test_user_defined_protocol_runs_through_same_runtime_pipeline(self) -> None:
        executed_actions: list[str] = []

        def execute_stub(step: object) -> SimpleNamespace:
            executed_actions.append(getattr(getattr(step, "action", None), "value", ""))
            return _successful_action_result(step)

        with tempfile.TemporaryDirectory() as tempdir:
            protocol_path = Path(tempdir) / "demo_focus.json"
            protocol_path.write_text(
                json.dumps(
                    {
                        "id": "demo_focus",
                        "title": "Demo Focus",
                        "enabled": True,
                        "triggers": [{"type": "exact", "phrase": "protocol demo focus"}],
                        "confirmation_policy": {"mode": "never"},
                        "steps": [{"action_type": "open_app", "inputs": {"app_name": "Notes"}}],
                        "completion_message": 'Completed protocol "Demo Focus".',
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"JARVIS_PROTOCOLS_DIR": tempdir}, clear=False):
                with patch("runtime.runtime_manager.execute_step", side_effect=execute_stub):
                    result = self.runtime_manager.handle_input("protocol demo focus", self.session_context)

        self.assertEqual(result.runtime_state, "completed")
        self.assertEqual(result.command_summary, "run_protocol: Demo Focus")
        self.assertEqual(executed_actions, ["open_app"])
        self.assertEqual(result.completion_summary, 'Completed protocol "Demo Focus".')
