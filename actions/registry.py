"""
Central tool registry.
All if/elif dispatch from _execute_tool lives here.
Each handler signature: (parameters: dict, player, speak) -> str
"""
from __future__ import annotations

from typing import Callable

from actions.open_app         import open_app
from actions.weather_report   import weather_action
from actions.browser_control  import browser_control
from actions.file_controller  import file_controller
from actions.send_message     import send_message
from actions.reminder         import reminder
from actions.youtube_video    import youtube_video
from actions.screen_processor import screen_process
from actions.computer_settings import computer_settings
from actions.cmd_control      import cmd_control
from actions.desktop          import desktop_control
from actions.code_helper      import code_helper
from actions.dev_agent        import dev_agent
from actions.web_search       import web_search as web_search_action
from actions.computer_control import computer_control
from actions.flight_finder    import flight_finder
from actions.protocol_manager import protocol as protocol_action


def _agent_task_handler(parameters: dict, player, speak) -> str:
    goal         = parameters.get("goal", "")
    priority_str = parameters.get("priority", "normal").lower()
    from agent.task_queue import get_queue, TaskPriority
    priority_map = {
        "low":    TaskPriority.LOW,
        "normal": TaskPriority.NORMAL,
        "high":   TaskPriority.HIGH,
    }
    q       = get_queue()
    task_id = q.submit(
        goal=goal,
        priority=priority_map.get(priority_str, TaskPriority.NORMAL),
        speak=speak,
    )
    return f"Task started (ID: {task_id}). I'll update you as I make progress, sir."


TOOL_REGISTRY: dict[str, Callable] = {
    "open_app":          lambda p, ui, speak: open_app(parameters=p, response=None, player=ui) or f"Opened {p.get('app_name')} successfully.",
    "weather_report":    lambda p, ui, speak: weather_action(parameters=p, player=ui) or f"Weather report for {p.get('city')} delivered.",
    "browser_control":   lambda p, ui, speak: browser_control(parameters=p, player=ui) or "Browser action completed.",
    "file_controller":   lambda p, ui, speak: file_controller(parameters=p, player=ui) or "File operation completed.",
    "send_message":      lambda p, ui, speak: send_message(parameters=p, response=None, player=ui, session_memory=None) or f"Message sent to {p.get('receiver')}.",
    "reminder":          lambda p, ui, speak: reminder(parameters=p, response=None, player=ui) or f"Reminder set for {p.get('date')} at {p.get('time')}.",
    "youtube_video":     lambda p, ui, speak: youtube_video(parameters=p, response=None, player=ui) or "Done.",
    "screen_process":    lambda p, ui, speak: screen_process(parameters=p, response=None, player=ui, session_memory=None) or "Vision analysis complete, sir.",
    "computer_settings": lambda p, ui, speak: computer_settings(parameters=p, response=None, player=ui) or "Done.",
    "cmd_control":       lambda p, ui, speak: cmd_control(parameters=p, player=ui) or "Command executed.",
    "desktop_control":   lambda p, ui, speak: desktop_control(parameters=p, player=ui) or "Desktop action completed.",
    "code_helper":       lambda p, ui, speak: code_helper(parameters=p, player=ui, speak=speak) or "Done.",
    "dev_agent":         lambda p, ui, speak: dev_agent(parameters=p, player=ui, speak=speak) or "Done.",
    "web_search":        lambda p, ui, speak: web_search_action(parameters=p, player=ui) or "Search completed.",
    "computer_control":  lambda p, ui, speak: computer_control(parameters=p, player=ui) or "Done.",
    "flight_finder":     lambda p, ui, speak: flight_finder(parameters=p, player=ui) or "Done.",
    "protocol":          lambda p, ui, speak: protocol_action(parameters=p, player=ui, speak=speak) or "Done.",
    "agent_task":        _agent_task_handler,
}


TOOL_DECLARATIONS = [
    {
        "name": "open_app",
        "description": (
            "Opens any application on the Windows computer. "
            "Use this whenever the user asks to open, launch, or start any app, "
            "website, or program. Always call this tool — never just say you opened it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Exact name of the application (e.g. 'WhatsApp', 'Chrome', 'Spotify')"
                }
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "web_search",
        "description": "Searches the web for any information.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "Search query"},
                "mode":   {"type": "STRING", "description": "search (default) or compare"},
                "items":  {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Items to compare"},
                "aspect": {"type": "STRING", "description": "price | specs | reviews"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "weather_report",
        "description": "Gets real-time weather information for a city.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING", "description": "City name"}
            },
            "required": ["city"]
        }
    },
    {
        "name": "send_message",
        "description": "Sends a text message via WhatsApp, Telegram, or other messaging platform.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver":     {"type": "STRING", "description": "Recipient contact name"},
                "message_text": {"type": "STRING", "description": "The message to send"},
                "platform":     {"type": "STRING", "description": "Platform: WhatsApp, Telegram, etc."}
            },
            "required": ["receiver", "message_text", "platform"]
        }
    },
    {
        "name": "reminder",
        "description": "Sets a timed reminder using Windows Task Scheduler.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date":    {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
                "time":    {"type": "STRING", "description": "Time in HH:MM format (24h)"},
                "message": {"type": "STRING", "description": "Reminder message text"}
            },
            "required": ["date", "time", "message"]
        }
    },
    {
        "name": "youtube_video",
        "description": (
            "Controls YouTube. Use for: playing videos, summarizing a video's content, "
            "getting video info, or showing trending videos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | summarize | get_info | trending (default: play)"},
                "query":  {"type": "STRING", "description": "Search query for play action"},
                "save":   {"type": "BOOLEAN", "description": "Save summary to Notepad (summarize only)"},
                "region": {"type": "STRING", "description": "Country code for trending e.g. TR, US"},
                "url":    {"type": "STRING", "description": "Video URL for get_info action"},
            },
            "required": []
        }
    },
    {
        "name": "screen_process",
        "description": (
            "Captures and analyzes the screen or webcam image. "
            "Call when user asks: what is on screen, what do you see, "
            "read the text, detect objects, look at camera, analyze screen, etc. "
            "You have NO visual ability without this tool. "
            "The tool returns the analysis as text — speak it naturally."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle":  {"type": "STRING", "description": "'screen' to capture display, 'camera' for webcam. Default: 'camera'"},
                "text":   {"type": "STRING", "description": "The user's question or instruction about the image"},
                "action": {"type": "STRING", "description": "'analyze' — general image Q&A (default); 'ocr' — extract all text; 'objects' — list all objects/people visible"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "computer_settings",
        "description": (
            "Controls the computer: volume, brightness, window management, keyboard shortcuts, "
            "typing text on screen, closing apps, fullscreen, dark mode, WiFi, restart, shutdown, "
            "scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page. "
            "ALSO use for: snapping windows — snap_left/snap_right (active window), "
            "snap_app_left/snap_app_right with value=AppName (targets a specific app by name). "
            "ALSO use for repeated actions: 'refresh 10 times' → action: reload_n, value: 10. "
            "Use for ANY single computer control command. "
            "NEVER route simple computer commands to agent_task."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "The action: snap_left | snap_right | snap_app_left | snap_app_right | minimize | maximize | volume_set | reload_n | type_text | press_key | ... or any other"},
                "description": {"type": "STRING", "description": "Natural language description of what to do"},
                "value":       {"type": "STRING", "description": "Optional value: app name for snap_app_*, volume level, text to type, count, etc."}
            },
            "required": []
        }
    },
    {
        "name": "browser_control",
        "description": (
            "Controls the web browser. Use for: opening websites, searching the web, "
            "clicking elements, filling forms, scrolling, finding cheapest products, "
            "booking flights, any web-based task."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | press | close"},
                "url":         {"type": "STRING", "description": "URL for go_to action"},
                "query":       {"type": "STRING", "description": "Search query for search action"},
                "selector":    {"type": "STRING", "description": "CSS selector for click/type"},
                "text":        {"type": "STRING", "description": "Text to click or type"},
                "description": {"type": "STRING", "description": "Element description for smart_click/smart_type"},
                "direction":   {"type": "STRING", "description": "up or down for scroll"},
                "key":         {"type": "STRING", "description": "Key name for press action"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_controller",
        "description": (
            "Manages files and folders. Use for: listing files, creating/deleting/moving/copying "
            "files, reading file contents, finding files by name or extension, checking disk usage, "
            "organizing the desktop, getting file info."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "list | create_file | create_folder | delete | move | copy | rename | read | write | find | largest | disk_usage | organize_desktop | info"},
                "path":        {"type": "STRING", "description": "File/folder path or shortcut: desktop, downloads, documents, home"},
                "destination": {"type": "STRING", "description": "Destination path for move/copy"},
                "new_name":    {"type": "STRING", "description": "New name for rename"},
                "content":     {"type": "STRING", "description": "Content for create_file/write"},
                "name":        {"type": "STRING", "description": "File name to search for"},
                "extension":   {"type": "STRING", "description": "File extension to search (e.g. .pdf)"},
                "count":       {"type": "INTEGER", "description": "Number of results for largest"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "cmd_control",
        "description": (
            "Runs CMD/terminal commands by understanding natural language. "
            "Use when user wants to: find large files, check disk space, list processes, "
            "get system info, navigate folders, check network, find files by name, "
            "or do ANYTHING in the command line they don't know how to do themselves."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "task":    {"type": "STRING", "description": "Natural language description of what to do."},
                "visible": {"type": "BOOLEAN", "description": "Open visible CMD window so user can see. Default: true"},
                "command": {"type": "STRING", "description": "Optional: exact command if already known"},
            },
            "required": ["task"]
        }
    },
    {
        "name": "desktop_control",
        "description": (
            "Controls the desktop. Use for: changing wallpaper, organizing desktop files, "
            "cleaning the desktop, listing desktop contents, or ANY other desktop-related task "
            "the user describes in natural language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "wallpaper | wallpaper_url | organize | clean | list | stats | task"},
                "path":   {"type": "STRING", "description": "Image path for wallpaper"},
                "url":    {"type": "STRING", "description": "Image URL for wallpaper_url"},
                "mode":   {"type": "STRING", "description": "by_type or by_date for organize"},
                "task":   {"type": "STRING", "description": "Natural language description of any desktop task"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_helper",
        "description": (
            "Writes, edits, explains, runs, builds, optimizes, or screen-debugs code files. "
            "Use for ANY coding request: writing a script, fixing a file, editing existing code, "
            "running a file, building and testing automatically, optimizing code, "
            "or analyzing an error visible on the screen."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "write | edit | explain | run | build | optimize | screen_debug | auto (default: auto)"},
                "description": {"type": "STRING", "description": "What the code should do, what change to make, or what problem to analyze"},
                "language":    {"type": "STRING", "description": "Programming language (default: python)"},
                "output_path": {"type": "STRING", "description": "Where to save the file (full path or filename)"},
                "file_path":   {"type": "STRING", "description": "Path to existing file for edit / explain / run / build / optimize / screen_debug"},
                "code":        {"type": "STRING", "description": "Raw code string for explain or optimize"},
                "args":        {"type": "STRING", "description": "CLI arguments for run/build"},
                "timeout":     {"type": "INTEGER", "description": "Execution timeout in seconds (default: 30)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "dev_agent",
        "description": (
            "Builds complete multi-file projects from scratch. "
            "Plans structure, writes all files, installs dependencies, "
            "opens VSCode, runs the project, and fixes errors automatically. "
            "Use for any project larger than a single script."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description":  {"type": "STRING", "description": "What the project should do"},
                "language":     {"type": "STRING", "description": "Programming language (default: python)"},
                "project_name": {"type": "STRING", "description": "Optional project folder name"},
                "timeout":      {"type": "INTEGER", "description": "Run timeout in seconds (default: 30)"},
            },
            "required": ["description"]
        }
    },
    {
        "name": "agent_task",
        "description": (
            "Executes complex multi-step tasks that require MULTIPLE DIFFERENT tools. "
            "Always respond to the user in the language they spoke. "
            "Examples: 'research X and save to file', 'find files and organize them', "
            "'fill a form on a website', 'write and test code'. "
            "DO NOT use for simple computer commands like volume, refresh, close, scroll, "
            "minimize, screenshot, restart, shutdown — use computer_settings for those. "
            "DO NOT use if the task can be done with a single tool call."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal":     {"type": "STRING", "description": "Complete description of what needs to be accomplished"},
                "priority": {"type": "STRING", "description": "low | normal | high (default: normal)"}
            },
            "required": ["goal"]
        }
    },
    {
        "name": "computer_control",
        "description": (
            "Direct computer control: type text, click buttons, use keyboard shortcuts, "
            "scroll, move mouse, take screenshots, fill forms, find elements on screen. "
            "Use when the user wants to interact with any app on the computer directly. "
            "Can generate random data for forms or use user's real info from memory."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data"},
                "text":        {"type": "STRING", "description": "Text to type or paste"},
                "x":           {"type": "INTEGER", "description": "X coordinate for click/move"},
                "y":           {"type": "INTEGER", "description": "Y coordinate for click/move"},
                "keys":        {"type": "STRING", "description": "Key combination e.g. 'ctrl+c'"},
                "key":         {"type": "STRING", "description": "Single key to press e.g. 'enter'"},
                "direction":   {"type": "STRING", "description": "Scroll direction: up | down | left | right"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount (default: 3)"},
                "seconds":     {"type": "NUMBER", "description": "Seconds to wait"},
                "title":       {"type": "STRING", "description": "Window title for focus_window"},
                "description": {"type": "STRING", "description": "Element description for screen_find/screen_click"},
                "type":        {"type": "STRING", "description": "Data type for random_data: name|email|username|password|phone|birthday|address"},
                "field":       {"type": "STRING", "description": "Field for user_data: name|email|city"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
                "path":        {"type": "STRING", "description": "Save path for screenshot"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "flight_finder",
        "description": (
            "Searches for flights on Google Flights and speaks the best options. "
            "Use when user asks about flights, plane tickets, uçuş, bilet, etc."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin":      {"type": "STRING",  "description": "Departure city or airport code"},
                "destination": {"type": "STRING",  "description": "Arrival city or airport code"},
                "date":        {"type": "STRING",  "description": "Departure date (any format)"},
                "return_date": {"type": "STRING",  "description": "Return date for round trips"},
                "passengers":  {"type": "INTEGER", "description": "Number of passengers (default: 1)"},
                "cabin":       {"type": "STRING",  "description": "economy | premium | business | first"},
                "save":        {"type": "BOOLEAN", "description": "Save results to Notepad"},
            },
            "required": ["origin", "destination", "date"]
        }
    },
    {
        "name": "protocol",
        "description": (
            "Activates a named V.E.C.T.O.R. protocol — a saved sequence of actions. "
            "Use when the user says a protocol trigger phrase like 'за работу', 'work mode', "
            "'я дома', 'home mode', or any custom protocol name. "
            "Also use for: listing protocols (action: list), "
            "adding a new protocol (action: add), removing one (action: remove)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "name":   {"type": "STRING", "description": "Protocol name or trigger phrase (e.g. 'work', 'home', 'за работу')"},
                "action": {"type": "STRING", "description": "run (default) | list | add | remove"},
                "data":   {"type": "STRING", "description": "JSON string with protocol definition for 'add' action"},
            },
            "required": ["name"]
        }
    },
]
