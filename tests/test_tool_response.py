from tool_response import format_tool_result_for_assistant


def test_browser_close_response_becomes_short():
    result = format_tool_result_for_assistant(
        "browser_control",
        {"action": "close"},
        "Browser closed.",
    )

    assert result == "Browser closed."


def test_browser_navigation_response_becomes_clean():
    result = format_tool_result_for_assistant(
        "browser_control",
        {"action": "go_to"},
        "Opened: https://google.com",
    )

    assert result == "Site opened."


def test_file_open_project_response_becomes_short():
    result = format_tool_result_for_assistant(
        "file_controller",
        {"action": "open_project"},
        "Opened project: JARVIS — /Users/name/JARVIS",
    )

    assert result == "Project opened."


def test_contentful_file_tree_response_is_not_shortened():
    tree = "repo/\n├── src/\n└── README.md"
    result = format_tool_result_for_assistant(
        "file_controller",
        {"action": "tree"},
        tree,
    )

    assert result == tree


def test_failures_are_preserved():
    result = format_tool_result_for_assistant(
        "browser_control",
        {"action": "go_to"},
        "Could not open: https://bad.example",
    )

    assert result == "Could not open: https://bad.example"
