# actions/open_app.py
# MARK XXV — Cross-Platform App Launcher

import re
import time
import threading
import subprocess
import platform
import shutil

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

_APP_ALIASES = {
    "whatsapp":           {"Windows": "WhatsApp",               "Darwin": "WhatsApp",            "Linux": "whatsapp"},
    "chrome":             {"Windows": "chrome",                 "Darwin": "Google Chrome",       "Linux": "google-chrome"},
    "google chrome":      {"Windows": "chrome",                 "Darwin": "Google Chrome",       "Linux": "google-chrome"},
    "firefox":            {"Windows": "firefox",                "Darwin": "Firefox",             "Linux": "firefox"},
    "spotify":            {"Windows": "Spotify",                "Darwin": "Spotify",             "Linux": "spotify"},
    "vscode":             {"Windows": "code",                   "Darwin": "Visual Studio Code",  "Linux": "code"},
    "visual studio code": {"Windows": "code",                   "Darwin": "Visual Studio Code",  "Linux": "code"},
    "discord":            {"Windows": "Discord",                "Darwin": "Discord",             "Linux": "discord"},
    "telegram":           {"Windows": "Telegram",               "Darwin": "Telegram",            "Linux": "telegram"},
    "instagram":          {"Windows": "Instagram",              "Darwin": "Instagram",           "Linux": "instagram"},
    "tiktok":             {"Windows": "TikTok",                 "Darwin": "TikTok",              "Linux": "tiktok"},
    "notepad":            {"Windows": "notepad.exe",            "Darwin": "TextEdit",            "Linux": "gedit"},
    "calculator":         {"Windows": "calc.exe",               "Darwin": "Calculator",          "Linux": "gnome-calculator"},
    "terminal":           {"Windows": "cmd.exe",                "Darwin": "Terminal",            "Linux": "gnome-terminal"},
    "cmd":                {"Windows": "cmd.exe",                "Darwin": "Terminal",            "Linux": "bash"},
    "command prompt":     {"Windows": "cmd.exe",                "Darwin": "Terminal",            "Linux": "bash"},
    "explorer":           {"Windows": "explorer.exe",           "Darwin": "Finder",              "Linux": "nautilus"},
    "file explorer":      {"Windows": "explorer.exe",           "Darwin": "Finder",              "Linux": "nautilus"},
    "paint":              {"Windows": "mspaint.exe",            "Darwin": "Preview",             "Linux": "gimp"},
    "word":               {"Windows": "winword",                "Darwin": "Microsoft Word",      "Linux": "libreoffice --writer"},
    "excel":              {"Windows": "excel",                  "Darwin": "Microsoft Excel",     "Linux": "libreoffice --calc"},
    "powerpoint":         {"Windows": "powerpnt",               "Darwin": "Microsoft PowerPoint","Linux": "libreoffice --impress"},
    "vlc":                {"Windows": "vlc",                    "Darwin": "VLC",                 "Linux": "vlc"},
    "zoom":               {"Windows": "Zoom",                   "Darwin": "zoom.us",             "Linux": "zoom"},
    "slack":              {"Windows": "Slack",                  "Darwin": "Slack",               "Linux": "slack"},
    "steam":              {"Windows": "steam",                  "Darwin": "Steam",               "Linux": "steam"},
    "task manager":       {"Windows": "taskmgr.exe",            "Darwin": "Activity Monitor",    "Linux": "gnome-system-monitor"},
    "settings":           {"Windows": "ms-settings:",           "Darwin": "System Preferences",  "Linux": "gnome-control-center"},
    "powershell":         {"Windows": "powershell.exe",         "Darwin": "Terminal",            "Linux": "bash"},
    "pwsh":               {"Windows": "pwsh.exe",               "Darwin": "Terminal",            "Linux": "bash"},
    "edge":               {"Windows": "msedge",                 "Darwin": "Microsoft Edge",      "Linux": "microsoft-edge"},
    "brave":              {"Windows": "brave",                  "Darwin": "Brave Browser",       "Linux": "brave-browser"},
    "obsidian":           {"Windows": "Obsidian",               "Darwin": "Obsidian",            "Linux": "obsidian"},
    "notion":             {"Windows": "Notion",                 "Darwin": "Notion",              "Linux": "notion"},
    "blender":            {"Windows": "blender",                "Darwin": "Blender",             "Linux": "blender"},
    "capcut":             {"Windows": "CapCut",                 "Darwin": "CapCut",              "Linux": "capcut"},
    "postman":            {"Windows": "Postman",                "Darwin": "Postman",             "Linux": "postman"},
    "figma":              {"Windows": "Figma",                  "Darwin": "Figma",               "Linux": "figma"},
}

# Maps every name a user might say (or that appears as a Windows alias above)
# to the actual .exe process name (without extension, lowercase).
# Used by _is_running and _focus_existing_window for exact process matching.
_WIN_PROCESS: dict[str, str] = {
    "chrome":                "chrome",
    "google chrome":         "chrome",
    "firefox":               "firefox",
    "spotify":               "spotify",
    "code":                  "code",
    "vscode":                "code",
    "visual studio code":    "code",
    "discord":               "discord",
    "telegram":              "telegram",
    "whatsapp":              "whatsapp",
    "instagram":             "instagram",
    "tiktok":                "tiktok",
    "notepad":               "notepad",
    "notepad.exe":           "notepad",
    "calculator":            "calculator",
    "calc.exe":              "calculator",
    "cmd":                   "cmd",
    "cmd.exe":               "cmd",
    "command prompt":        "cmd",
    "terminal":              "cmd",
    "explorer":              "explorer",
    "explorer.exe":          "explorer",
    "file explorer":         "explorer",
    "paint":                 "mspaint",
    "mspaint.exe":           "mspaint",
    "word":                  "winword",
    "winword":               "winword",
    "excel":                 "excel",
    "powerpoint":            "powerpnt",
    "powerpnt":              "powerpnt",
    "vlc":                   "vlc",
    "zoom":                  "zoom",
    "slack":                 "slack",
    "steam":                 "steam",
    "task manager":          "taskmgr",
    "taskmgr.exe":           "taskmgr",
    "powershell":            "powershell",
    "powershell.exe":        "powershell",
    "pwsh":                  "pwsh",
    "pwsh.exe":              "pwsh",
    "edge":                  "msedge",
    "msedge":                "msedge",
    "brave":                 "brave",
    "obsidian":              "obsidian",
    "notion":                "notion",
    "blender":               "blender",
    "capcut":                "capcut",
    "postman":               "postman",
    "figma":                 "figma",
}


def _normalize(raw: str) -> str:
    system = platform.system()
    key    = raw.lower().strip()
    # Exact match first
    if key in _APP_ALIASES:
        return _APP_ALIASES[key].get(system, raw)
    # Word-boundary match: prevents "word" from matching "password",
    # "code" from matching "vscode", etc.
    for alias_key, os_map in _APP_ALIASES.items():
        if re.search(r'\b' + re.escape(alias_key) + r'\b', key) or \
           re.search(r'\b' + re.escape(key) + r'\b', alias_key):
            return os_map.get(system, raw)
    return raw


def _compact_app_key(app_name: str) -> str:
    return app_name.lower().strip().replace(".exe", "").replace(" ", "")


_TERMINAL_APPS = {"terminal", "cmd", "commandprompt", "powershell", "pwsh"}


def _is_terminal_app(app_name: str) -> bool:
    return _compact_app_key(app_name) in _TERMINAL_APPS


def _terminal_launch_args(app_name: str) -> list[str]:
    key = _compact_app_key(app_name)
    if key in {"terminal", "cmd", "commandprompt"}:
        return ["cmd.exe"]
    if key == "powershell":
        return ["powershell.exe", "-NoExit"]
    if key == "pwsh":
        return ["pwsh.exe", "-NoExit"]
    return [app_name]

SW_RESTORE      = 9
SW_SHOWMAXIMIZED = 3

def _is_running(app_name: str) -> bool:
    if not _PSUTIL:
        return False
    key = app_name.lower().strip()
    # Resolve to the real process name; fall back to stripping spaces/.exe
    target = _WIN_PROCESS.get(key, key.replace(" ", "").replace(".exe", ""))
    try:
        for proc in psutil.process_iter(["name"]):
            try:
                proc_name = (proc.info["name"] or "").lower().replace(".exe", "").replace(" ", "")
                if proc_name == target:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        pass
    return False

def _focus_existing_window(app_name: str, show_cmd: int = SW_RESTORE) -> bool:
    system = platform.system()

    if system == "Windows":
        try:
            import ctypes
            user32 = ctypes.windll.user32

            found = [None]

            candidates = {
                app_name.lower().strip(),
                app_name.lower().replace(".exe", "").strip(),
                app_name.lower().replace(" ", "").strip(),
            }

            target_pids: set[int] = set()
            if _PSUTIL:
                key = app_name.lower().strip()
                proc_target = _WIN_PROCESS.get(key, key.replace(" ", "").replace(".exe", ""))
                try:
                    for proc in psutil.process_iter(["pid", "name"]):
                        try:
                            pname = (proc.info["name"] or "").lower().replace(".exe", "").replace(" ", "")
                            if pname == proc_target:
                                target_pids.add(proc.info["pid"])
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            continue
                except Exception:
                    pass

            def enum_handler(hwnd, _):
                # Include iconic (minimized) windows in addition to visible ones
                if not user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
                    return True
                length = user32.GetWindowTextLengthW(hwnd)
                if length == 0:
                    return True
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                title = buffer.value.lower().strip()
                if not title:
                    return True
                for candidate in candidates:
                    compact_title = title.replace(" ", "")
                    if candidate in title or candidate in compact_title:
                        found[0] = hwnd
                        return False
                if target_pids:
                    pid = ctypes.c_ulong()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    if pid.value in target_pids:
                        found[0] = hwnd
                        return False
                return True

            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            user32.EnumWindows(EnumWindowsProc(enum_handler), 0)

            if found[0]:
                hwnd = found[0]
                user32.ShowWindow(hwnd, show_cmd)
                user32.BringWindowToTop(hwnd)
                # Attach input threads so SetForegroundWindow succeeds even when
                # another app has focus (e.g. after minimize/background state).
                try:
                    fg_hwnd = user32.GetForegroundWindow()
                    fg_tid  = user32.GetWindowThreadProcessId(fg_hwnd, None)
                    tgt_tid = user32.GetWindowThreadProcessId(hwnd, None)
                    if fg_tid and fg_tid != tgt_tid:
                        user32.AttachThreadInput(fg_tid, tgt_tid, True)
                        user32.SetForegroundWindow(hwnd)
                        user32.AttachThreadInput(fg_tid, tgt_tid, False)
                    else:
                        user32.SetForegroundWindow(hwnd)
                except Exception:
                    user32.SetForegroundWindow(hwnd)
                time.sleep(0.4)
                return True

        except Exception as e:
            print(f"[open_app] ⚠️ focus existing window failed: {e}")

        return False

    if system == "Darwin":
        try:
            script = f'''
            tell application "{app_name}"
                activate
            end tell
            '''
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception as e:
            print(f"[open_app] ⚠️ macOS focus failed: {e}")
            return False

    if system == "Linux":
        try:
            wmctrl = shutil.which("wmctrl")
            if wmctrl:
                result = subprocess.run(
                    [wmctrl, "-a", app_name],
                    capture_output=True,
                    timeout=5
                )
                return result.returncode == 0
        except Exception as e:
            print(f"[open_app] ⚠️ Linux focus failed: {e}")

        return False

    return False


def _wait_for_process(app_name: str, timeout: float = 4.0) -> bool:
    """Poll until app_name appears in running processes or timeout expires."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _is_running(app_name):
            return True
        time.sleep(0.4)
    return False


def _maximize_later(app_name: str, delay: float = 2.0) -> None:
    """Maximize the app window in a background thread after a short delay."""
    def _do():
        time.sleep(delay)
        _focus_existing_window(app_name, SW_SHOWMAXIMIZED)
    threading.Thread(target=_do, daemon=True, name="MaximizeWindow").start()


def _launch_windows(app_name: str) -> bool:
    # 0. Terminal apps must open with a visible console window
    key = _compact_app_key(app_name)
    if key in _TERMINAL_APPS:
        try:
            subprocess.Popen(
                _terminal_launch_args(app_name),
                creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
            )
            time.sleep(0.8)
            _maximize_later(app_name)
            return True
        except Exception as e:
            print(f"[open_app] ⚠️ Terminal launch failed: {e}")

    # 1. Direct subprocess launch (works for .exe and PATH binaries like "code", "chrome")
    try:
        subprocess.Popen(
            [app_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        if _wait_for_process(app_name, 4.0):
            _maximize_later(app_name)
            return True
    except (FileNotFoundError, OSError):
        pass
    except Exception as e:
        print(f"[open_app] ⚠️ Direct launch failed: {e}")

    # 2. shutil.which — find binary in PATH, then launch
    binary = shutil.which(app_name) or shutil.which(app_name.lower())
    if binary:
        try:
            subprocess.Popen(
                [binary],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            )
            if _wait_for_process(app_name, 4.0):
                _maximize_later(app_name)
                return True
        except Exception as e:
            print(f"[open_app] ⚠️ which-path launch failed: {e}")

    # 3. os.startfile — Windows native, works for ms-settings:, .exe, registered file types
    try:
        import os
        os.startfile(app_name)
        time.sleep(1.5)
        _maximize_later(app_name)
        return True
    except (FileNotFoundError, OSError):
        pass
    except Exception as e:
        print(f"[open_app] ⚠️ os.startfile failed: {e}")

    # 4. PowerShell — find and launch Windows Store (AppX) app by name
    try:
        ps_script = (
            f"$pkg = Get-AppxPackage | "
            f"Where-Object {{ $_.Name -like '*{app_name}*' -or $_.PackageFamilyName -like '*{app_name}*' }} | "
            f"Select-Object -First 1; "
            f"if ($pkg) {{ "
            f"  $appId = (Get-AppxPackageManifest $pkg).Package.Applications.Application | "
            f"    Select-Object -First 1 -ExpandProperty Id; "
            f"  Start-Process (\"shell:AppsFolder\\\" + $pkg.PackageFamilyName + \"!\" + $appId) "
            f"}}"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True, timeout=12
        )
        if result.returncode == 0 and not result.stderr.strip():
            time.sleep(2.0)
            _maximize_later(app_name)
            return True
        print(f"[open_app] ⚠️ AppX launch stderr: {result.stderr.decode(errors='ignore')[:100]}")
    except Exception as e:
        print(f"[open_app] ⚠️ AppX launch failed: {e}")

    # 5. Windows "start" command via shell — works for some UWP/registered apps
    try:
        result = subprocess.run(
            f'start "" "{app_name}"',
            shell=True,
            capture_output=True,
            timeout=6,
        )
        if result.returncode == 0:
            time.sleep(2.0)
            _maximize_later(app_name)
            return True
    except Exception as e:
        print(f"[open_app] ⚠️ shell start failed: {e}")

    # 6. Last resort: pyautogui Start Menu search (handles any installed app)
    try:
        import pyautogui
        pyautogui.PAUSE = 0.1
        pyautogui.press("win")
        time.sleep(1.0)
        try:
            import pyperclip
            pyperclip.copy(app_name)
            pyautogui.hotkey("ctrl", "v")
        except Exception:
            pyautogui.write(app_name.lower(), interval=0.07)
        time.sleep(1.2)
        pyautogui.press("enter")
        time.sleep(3.0)
        _maximize_later(app_name)
        return True
    except Exception as e:
        print(f"[open_app] ⚠️ pyautogui fallback failed: {e}")
        return False

def _launch_macos(app_name: str) -> bool:
    try:
        result = subprocess.run(["open", "-a", app_name], capture_output=True, timeout=8)
        if result.returncode == 0:
            time.sleep(1.0)
            return True
    except Exception:
        pass

    try:
        result = subprocess.run(["open", "-a", f"{app_name}.app"], capture_output=True, timeout=8)
        if result.returncode == 0:
            time.sleep(1.0)
            return True
    except Exception:
        pass

    try:
        import pyautogui
        try:
            import pyperclip
            pyautogui.hotkey("command", "space")
            time.sleep(0.6)
            pyperclip.copy(app_name)
            pyautogui.hotkey("command", "v")
        except ImportError:
            pyautogui.hotkey("command", "space")
            time.sleep(0.6)
            pyautogui.write(app_name, interval=0.05)
        time.sleep(0.8)
        pyautogui.press("enter")
        time.sleep(1.5)
        return True
    except Exception as e:
        print(f"[open_app] ⚠️ macOS Spotlight failed: {e}")
        return False



def _launch_linux(app_name: str) -> bool:
    binary = (
        shutil.which(app_name) or
        shutil.which(app_name.lower()) or
        shutil.which(app_name.lower().replace(" ", "-"))
    )
    if binary:
        try:
            subprocess.Popen([binary], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1.0)
            return True
        except Exception:
            pass

    try:
        subprocess.run(["xdg-open", app_name], capture_output=True, timeout=5)
        return True
    except Exception:
        pass

    try:
        desktop_name = app_name.lower().replace(" ", "-")
        subprocess.run(["gtk-launch", desktop_name], capture_output=True, timeout=5)
        return True
    except Exception:
        pass

    return False


_OS_LAUNCHERS = {
    "Windows": _launch_windows,
    "Darwin":  _launch_macos,
    "Linux":   _launch_linux,
}


def open_app(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    app_name = (parameters or {}).get("app_name", "").strip()

    if not app_name:
        return "Please specify which application to open, sir."

    system   = platform.system()
    launcher = _OS_LAUNCHERS.get(system)

    if launcher is None:
        return f"Unsupported OS: {system}"

    normalized = _normalize(app_name)
    print(f"[open_app] 🚀 Requested: {app_name} → {normalized} ({system})")

    if player:
        player.write_log(f"[open_app] {app_name}")

    try:
        # Terminal requests should always create a fresh console window on Windows.
        if system == "Windows" and (_is_terminal_app(normalized) or _is_terminal_app(app_name)):
            success = launcher(normalized)
            if success:
                return f"Opened {app_name} successfully, sir."

            if normalized != app_name:
                success = launcher(app_name)
                if success:
                    return f"Opened {app_name} successfully, sir."

            return (
                f"I tried to open {app_name}, sir, but couldn't confirm it launched. "
                f"It may still be loading or might not be installed."
            )

        # 1. If already running, try to bring existing window to front / restore
        if _is_running(normalized) or _is_running(app_name):
            focused = (
                _focus_existing_window(normalized, SW_RESTORE)
                or _focus_existing_window(app_name, SW_RESTORE)
            )
            if focused:
                return f"Focused existing {app_name} window, sir."

            # Process alive but no visible window found (e.g. app was closed but
            # background service still runs) — launch a fresh instance instead.
            print(f"[open_app] ℹ️ {app_name} process alive but no window found — relaunching")
            success = launcher(normalized) or (normalized != app_name and launcher(app_name))
            if success:
                return f"Opened {app_name} successfully, sir."
            return f"{app_name} is already running, sir, but I couldn't bring its window to the front."

        # 2. Otherwise launch normally
        success = launcher(normalized)

        if success:
            return f"Opened {app_name} successfully, sir."

        if normalized != app_name:
            success = launcher(app_name)
            if success:
                return f"Opened {app_name} successfully, sir."

        return (
            f"I tried to open {app_name}, sir, but couldn't confirm it launched. "
            f"It may still be loading or might not be installed."
        )

    except Exception as e:
        print(f"[open_app] ❌ {e}")
        return f"Failed to open {app_name}, sir: {e}"
