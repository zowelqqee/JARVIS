"""Contract tests for QA structured debug tracing."""

from __future__ import annotations

import unittest

from qa.debug_trace import debug_flag_name, qa_debug_enabled, set_debug_payload, update_debug_payload


class QaDebugTraceTests(unittest.TestCase):
    """Lock the debug flag and safe trace helpers."""

    def test_debug_flag_is_disabled_by_default(self) -> None:
        self.assertFalse(qa_debug_enabled({}))
        self.assertEqual(debug_flag_name(), "JARVIS_QA_DEBUG")

    def test_debug_flag_accepts_truthy_values(self) -> None:
        self.assertTrue(qa_debug_enabled({"JARVIS_QA_DEBUG": "1"}))
        self.assertTrue(qa_debug_enabled({"JARVIS_QA_DEBUG": "true"}))

    def test_trace_helpers_prune_empty_fields(self) -> None:
        debug_trace: dict[str, object] = {}

        set_debug_payload(
            debug_trace,
            "routing_decision",
            {"interaction_kind": "question", "reason": "", "nested": {"kept": "yes", "drop": ""}},
        )
        update_debug_payload(debug_trace, "routing_decision", {"confidence": 0.9, "extra": None})

        self.assertEqual(
            debug_trace,
            {
                "routing_decision": {
                    "interaction_kind": "question",
                    "nested": {"kept": "yes"},
                    "confidence": 0.9,
                }
            },
        )


if __name__ == "__main__":
    unittest.main()
