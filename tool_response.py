from __future__ import annotations


def _is_failure(text: str) -> bool:
    lowered = (text or "").strip().lower()
    if not lowered:
        return False

    failure_markers = (
        "failed",
        "error",
        "timed out",
        "timeout",
        "access denied",
        "permission denied",
        "unknown action",
        "unknown tool",
        "could not",
        "not found",
        "please provide",
        "please specify",
        "unsupported",
        "cancelled",
    )
    return any(marker in lowered for marker in failure_markers)


def _map_action(action: str, mapping: dict[str, str], fallback: str | None = None) -> str | None:
    if not action:
        return fallback
    return mapping.get(action, fallback)


def format_tool_result_for_assistant(tool_name: str, args: dict | None, raw_result: str) -> str:
    text = str(raw_result or "").strip()
    if not text:
        return "Done."

    args = args or {}
    action = str(args.get("action", "") or "").strip().lower()

    if _is_failure(text):
        return text

    if tool_name == "open_app" and text.lower().startswith("opened "):
        return "App opened."

    if tool_name == "browser_control":
        if text == "No active browser session.":
            return "No active browser."
        if text == "No active browser sessions.":
            return "No active browsers."
        mapped = _map_action(
            action,
            {
                "go_to": "Site opened.",
                "search": "Search opened.",
                "click": "Clicked.",
                "smart_click": "Clicked.",
                "type": "Entered.",
                "smart_type": "Entered.",
                "scroll": "Scrolled.",
                "fill_form": "Form filled.",
                "press": "Pressed.",
                "new_tab": "Tab opened.",
                "close_tab": "Tab closed.",
                "back": "Went back.",
                "forward": "Went forward.",
                "reload": "Page reloaded.",
                "switch": "Browser changed.",
                "close": "Browser closed.",
                "close_all": "Browsers closed.",
                "screenshot": "Screenshot saved.",
            },
        )
        return mapped or text

    if tool_name == "file_controller":
        mapped = _map_action(
            action,
            {
                "open": "Folder opened.",
                "open_project": "Project opened.",
                "create_file": "File created.",
                "create_folder": "Folder created.",
                "delete": "Deleted.",
                "move": "Moved.",
                "copy": "Copied.",
                "rename": "Renamed.",
                "write": "Saved.",
                "organize_desktop": "Desktop organized.",
            },
        )
        return mapped or text

    if tool_name == "computer_control":
        mapped = _map_action(
            action,
            {
                "type": "Typed.",
                "smart_type": "Typed.",
                "click": "Clicked.",
                "double_click": "Clicked.",
                "right_click": "Clicked.",
                "hotkey": "Done.",
                "press": "Pressed.",
                "scroll": "Scrolled.",
                "move": "Cursor moved.",
                "copy": "Copied.",
                "paste": "Pasted.",
                "screenshot": "Screenshot saved.",
                "clear_field": "Field cleared.",
                "focus_window": "Window focused.",
                "screen_click": "Clicked.",
                "wait": "Done.",
            },
        )
        return mapped or text

    if tool_name == "computer_settings":
        mapped = _map_action(
            action,
            {
                "volume_set": "Volume changed.",
                "volume_up": "Volume changed.",
                "volume_down": "Volume changed.",
                "mute": "Sound off.",
                "unmute": "Sound on.",
                "brightness_set": "Brightness changed.",
                "brightness_up": "Brightness changed.",
                "brightness_down": "Brightness changed.",
                "reload_page": "Page reloaded.",
                "scroll_up": "Scrolled.",
                "scroll_down": "Scrolled.",
                "type_text": "Typed.",
                "press_key": "Pressed.",
                "close_window": "Closed.",
                "close_app": "Closed.",
                "switch_window": "Switched window.",
                "open_settings": "Settings opened.",
                "toggle_wifi": "Wi-Fi updated.",
                "lock_screen": "Locked.",
                "screenshot": "Screenshot saved.",
            },
            fallback="Done.",
        )
        return mapped or text

    return text
