"""Protocol registry coverage for built-in and user-defined protocols."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from protocols.registry import match_protocol_trigger, resolve_protocol_reference


class ProtocolRegistryTests(unittest.TestCase):
    """Verify named protocol lookup and user extensibility."""

    def test_builtin_trigger_matches_i_am_home(self) -> None:
        matches = match_protocol_trigger("я дома")

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].definition.id, "i_am_home")
        self.assertEqual(matches[0].definition.title, "I Am Home")

    def test_user_defined_json_protocol_is_loaded_from_directory(self) -> None:
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
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"JARVIS_PROTOCOLS_DIR": tempdir}, clear=False):
                trigger_matches = match_protocol_trigger("protocol demo focus")
                reference_matches = resolve_protocol_reference("demo focus")

        self.assertEqual(len(trigger_matches), 1)
        self.assertEqual(trigger_matches[0].definition.id, "demo_focus")
        self.assertEqual(len(reference_matches), 1)
        self.assertEqual(reference_matches[0].definition.title, "Demo Focus")
