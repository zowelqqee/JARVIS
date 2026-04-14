"""Persisted protocol state store tests."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from types import SimpleNamespace
from unittest.mock import patch

from protocols.state_store import ProtocolStateStore


class ProtocolStateStoreTests(unittest.TestCase):
    """Verify recent workspace persistence for protocol use."""

    def test_remember_command_persists_workspace_and_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            state_path = str(Path(tempdir) / "protocol_state.json")
            command = SimpleNamespace(
                raw_input="prepare workspace for demo",
                intent="prepare_workspace",
                targets=[],
                parameters={
                    "workspace_path": "/tmp/demo",
                    "workspace_label": "demo",
                },
                confidence=0.9,
                requires_confirmation=False,
                execution_steps=[],
                status_message="Parsed",
            )
            with patch.dict(os.environ, {"JARVIS_PROTOCOL_STATE_PATH": state_path}, clear=False):
                with patch(
                    "protocols.state_store.subprocess.run",
                    return_value=CompletedProcess(args=["git"], returncode=0, stdout="main\n", stderr=""),
                ):
                    store = ProtocolStateStore()
                    store.remember_command(command)
                    payload = store.load()
                    context = store.template_context()

        self.assertEqual(payload["last_workspace_path"], "/tmp/demo")
        self.assertEqual(payload["last_workspace_label"], "demo")
        self.assertEqual(payload["last_git_branch"], "main")
        self.assertEqual(context["branch_suffix"], ", ветка main")
        self.assertEqual(context["resume_context_en"], " Branch: main.")
        self.assertEqual(context["resume_context_ru"], " Ветка: main.")
        self.assertEqual(
            context["last_project_sentence_ru"],
            "Последним у вас был проект demo, ветка main.",
        )
        self.assertEqual(context["home_greeting_ru"], "Приветствую, сэр.")

    def test_template_context_uses_human_fallback_when_project_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            state_path = str(Path(tempdir) / "protocol_state.json")
            with patch.dict(os.environ, {"JARVIS_PROTOCOL_STATE_PATH": state_path}, clear=False):
                store = ProtocolStateStore()
                store.save({})
                context = store.template_context()

        self.assertEqual(context["last_workspace_label"], "последний проект")
        self.assertEqual(context["last_project_sentence_ru"], "Последний проект я пока не успел запомнить.")
        self.assertEqual(context["resume_context_en"], "")
        self.assertEqual(context["resume_context_ru"], "")

    def test_open_file_persists_parent_folder_as_workspace_context(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            state_path = str(Path(tempdir) / "protocol_state.json")
            command = SimpleNamespace(
                raw_input="open /tmp/demo/notes.md",
                intent="open_file",
                targets=[SimpleNamespace(type="file", name="notes.md", path="/tmp/demo/notes.md")],
                parameters={},
                confidence=0.9,
                requires_confirmation=False,
                execution_steps=[],
                status_message="Parsed",
            )
            with patch.dict(os.environ, {"JARVIS_PROTOCOL_STATE_PATH": state_path}, clear=False):
                with patch(
                    "protocols.state_store.subprocess.run",
                    return_value=CompletedProcess(args=["git"], returncode=0, stdout="main\n", stderr=""),
                ):
                    store = ProtocolStateStore()
                    store.remember_command(command)
                    payload = store.load()
                    context = store.template_context()

        self.assertEqual(payload["last_workspace_path"], "/tmp/demo")
        self.assertEqual(payload["last_workspace_label"], "demo")
        self.assertEqual(context["resume_context_en"], " Branch: main. Last file: notes.md.")
        self.assertEqual(context["resume_context_ru"], " Ветка: main. Последний файл: notes.md.")

    def test_remember_command_persists_last_protocol(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            state_path = str(Path(tempdir) / "protocol_state.json")
            command = SimpleNamespace(
                raw_input="protocol clean slate",
                intent="run_protocol",
                targets=[],
                parameters={"protocol_id": "clean_slate", "protocol_display_name": "Clean Slate"},
                confidence=0.98,
                requires_confirmation=True,
                execution_steps=[],
                status_message="Parsed",
            )
            with patch.dict(os.environ, {"JARVIS_PROTOCOL_STATE_PATH": state_path}, clear=False):
                store = ProtocolStateStore()
                store.remember_command(command)
                payload = store.load()

        self.assertEqual(payload["last_protocol_id"], "clean_slate")
        self.assertEqual(payload["last_protocol_title"], "Clean Slate")
