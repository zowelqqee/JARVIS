import unittest
from unittest.mock import patch


class TestCodeHelperVisibleFile(unittest.TestCase):

    def test_detect_intent_explain_for_visible_file_reference(self):
        from actions.code_helper import _detect_intent

        action = _detect_intent(
            "объясни как работает код из этого файла",
            file_path="",
            code="",
        )

        self.assertEqual(action, "explain")

    def test_detect_intent_edit_for_visible_file_reference(self):
        from actions.code_helper import _detect_intent

        action = _detect_intent(
            "исправь код в этом файле",
            file_path="",
            code="",
        )

        self.assertEqual(action, "edit")

    def test_code_helper_uses_screen_context_before_explain(self):
        with patch(
            "actions.code_helper._extract_current_file_context_from_screen",
            return_value=(
                {
                    "is_code_file": True,
                    "file_path": "",
                    "file_name": "main.py",
                    "language": "python",
                    "visible_code": "def hello():\n    return 'hi'",
                },
                "",
            ),
        ), patch(
            "actions.code_helper._explain_action",
            return_value="explanation from visible code",
        ) as mock_explain:
            from actions.code_helper import code_helper

            result = code_helper({
                "action": "auto",
                "description": "explain how this file works",
            })

        mock_explain.assert_called_once_with(
            "",
            "def hello():\n    return 'hi'",
            None,
        )
        self.assertEqual(result, "explanation from visible code")

    def test_run_current_visible_file_requires_real_path(self):
        with patch(
            "actions.code_helper._extract_current_file_context_from_screen",
            return_value=(
                {
                    "is_code_file": True,
                    "file_path": "",
                    "file_name": "script.py",
                    "language": "python",
                    "visible_code": "print('hi')",
                },
                "",
            ),
        ):
            from actions.code_helper import code_helper

            result = code_helper({
                "action": "auto",
                "description": "run this file",
            })

        self.assertIn("need the actual file path", result)
