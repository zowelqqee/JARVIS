import os
import platform
import shlex
import shutil
import subprocess
import time
from pathlib import Path

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

try:
    import pyautogui
    _PYAUTOGUI = True
except ImportError:
    _PYAUTOGUI = False


_SYSTEM = platform.system()  # "Windows" | "Darwin" | "Linux"

_APP_ALIASES: dict[str, dict[str, str]] = {
    "chrome":             {"Windows": "chrome",                  "Darwin": "Google Chrome",        "Linux": "google-chrome"},
    "google chrome":      {"Windows": "chrome",                  "Darwin": "Google Chrome",        "Linux": "google-chrome"},
    "firefox":            {"Windows": "firefox",                 "Darwin": "Firefox",              "Linux": "firefox"},
    "edge":               {"Windows": "msedge",                  "Darwin": "Microsoft Edge",       "Linux": "microsoft-edge"},
    "brave":              {"Windows": "brave",                   "Darwin": "Brave Browser",        "Linux": "brave-browser"},
    "safari":             {"Windows": "msedge",                  "Darwin": "Safari",               "Linux": "firefox"},
    "opera":              {"Windows": "opera",                   "Darwin": "Opera",                "Linux": "opera"},
    "whatsapp":           {"Windows": "WhatsApp",                "Darwin": "WhatsApp",             "Linux": "whatsapp"},
    "telegram":           {"Windows": "Telegram",                "Darwin": "Telegram",             "Linux": "telegram"},
    "discord":            {"Windows": "Discord",                 "Darwin": "Discord",              "Linux": "discord"},
    "slack":              {"Windows": "Slack",                   "Darwin": "Slack",                "Linux": "slack"},
    "zoom":               {"Windows": "Zoom",                    "Darwin": "zoom.us",              "Linux": "zoom"},
    "teams":              {"Windows": "msteams",                 "Darwin": "Microsoft Teams",      "Linux": "teams"},
    "skype":              {"Windows": "skype",                   "Darwin": "Skype",                "Linux": "skype"},
    "signal":             {"Windows": "signal",                  "Darwin": "Signal",               "Linux": "signal"},
    "spotify":            {"Windows": "Spotify",                 "Darwin": "Spotify",              "Linux": "spotify"},
    "vlc":                {"Windows": "vlc",                     "Darwin": "VLC",                  "Linux": "vlc"},
    "netflix":            {"Windows": "Netflix",                 "Darwin": "Netflix",              "Linux": "firefox"},
    "vscode":             {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "visual studio code": {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "code":               {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "terminal":           {"Windows": "wt",                      "Darwin": "Terminal",             "Linux": "gnome-terminal"},
    "cmd":                {"Windows": "cmd.exe",                 "Darwin": "Terminal",             "Linux": "bash"},
    "powershell":         {"Windows": "powershell.exe",          "Darwin": "Terminal",             "Linux": "bash"},
    "postman":            {"Windows": "Postman",                 "Darwin": "Postman",              "Linux": "postman"},
    "git":                {"Windows": "git-bash",                "Darwin": "Terminal",             "Linux": "bash"},
    "figma":              {"Windows": "Figma",                   "Darwin": "Figma",                "Linux": "figma"},
    "blender":            {"Windows": "blender",                 "Darwin": "Blender",              "Linux": "blender"},
    "word":               {"Windows": "winword",                 "Darwin": "Microsoft Word",       "Linux": "libreoffice --writer"},
    "excel":              {"Windows": "excel",                   "Darwin": "Microsoft Excel",      "Linux": "libreoffice --calc"},
    "powerpoint":         {"Windows": "powerpnt",                "Darwin": "Microsoft PowerPoint", "Linux": "libreoffice --impress"},
    "libreoffice":        {"Windows": "soffice",                 "Darwin": "LibreOffice",          "Linux": "libreoffice"},
    "notepad":            {"Windows": "notepad.exe",             "Darwin": "TextEdit",             "Linux": "gedit"},
    "textedit":           {"Windows": "notepad.exe",             "Darwin": "TextEdit",             "Linux": "gedit"},
    "explorer":           {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "file explorer":      {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "finder":             {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "task manager":       {"Windows": "taskmgr.exe",             "Darwin": "Activity Monitor",     "Linux": "gnome-system-monitor"},
    "settings":           {"Windows": "ms-settings:",            "Darwin": "System Preferences",   "Linux": "gnome-control-center"},
    "calculator":         {"Windows": "calc.exe",                "Darwin": "Calculator",           "Linux": "gnome-calculator"},
    "paint":              {"Windows": "mspaint.exe",             "Darwin": "Preview",              "Linux": "gimp"},
    "instagram":          {"Windows": "Instagram",               "Darwin": "Instagram",            "Linux": "firefox"},
    "tiktok":             {"Windows": "TikTok",                  "Darwin": "TikTok",               "Linux": "firefox"},
    "notion":             {"Windows": "Notion",                  "Darwin": "Notion",               "Linux": "notion"},
    "obsidian":           {"Windows": "Obsidian",                "Darwin": "Obsidian",             "Linux": "obsidian"},
    "capcut":             {"Windows": "CapCut",                  "Darwin": "CapCut",               "Linux": "capcut"},
    "steam":              {"Windows": "steam",                   "Darwin": "Steam",                "Linux": "steam"},
    "epic":               {"Windows": "EpicGamesLauncher",       "Darwin": "Epic Games Launcher",  "Linux": "legendary"},
    "epic games":         {"Windows": "EpicGamesLauncher",       "Darwin": "Epic Games Launcher",  "Linux": "legendary"},
}


def get_platform_key() -> str:
    return {
        "Windows": "windows",
        "Darwin": "mac",
        "Linux": "linux",
    }.get(_SYSTEM, _SYSTEM.lower())


def _canonicalize(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _matching_aliases(raw: str) -> list[tuple[str, dict[str, str]]]:
    key = raw.lower().strip()
    matches: list[tuple[str, dict[str, str]]] = []

    if key in _APP_ALIASES:
        matches.append((key, _APP_ALIASES[key]))

    for alias_key, os_map in _APP_ALIASES.items():
        if alias_key == key:
            continue
        if alias_key in key or key in alias_key:
            matches.append((alias_key, os_map))

    return matches


def normalize_app_name(raw: str) -> str:
    for _, os_map in _matching_aliases(raw):
        return os_map.get(_SYSTEM, raw)
    return raw.strip()


def app_name_candidates(raw: str) -> list[str]:
    raw = raw.strip()
    values: list[str] = [raw]
    normalized = normalize_app_name(raw)
    if normalized:
        values.append(normalized)

    for alias_key, os_map in _matching_aliases(raw):
        values.append(alias_key)
        values.extend(v for v in os_map.values() if v)

    expanded: list[str] = []
    for value in values:
        if not value:
            continue
        expanded.append(value)
        if value.lower().endswith(".app"):
            expanded.append(value[:-4])
        try:
            parts = shlex.split(value, posix=_SYSTEM != "Windows")
        except ValueError:
            parts = [value]
        command_like = (
            len(parts) == 1
            or any(part.startswith("-") for part in parts[1:])
            or "/" in parts[0]
            or "\\" in parts[0]
        )
        if parts and command_like:
            expanded.append(parts[0])
            expanded.append(Path(parts[0]).stem)
        lowered = value.lower()
        expanded.extend(
            [
                lowered,
                lowered.replace(" ", "-"),
                lowered.replace(" ", "_"),
                lowered.replace(" ", ""),
            ]
        )

    seen: set[str] = set()
    unique: list[str] = []
    for value in expanded:
        value = value.strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(value)
    return unique


def _looks_like_scheme(value: str) -> bool:
    return len(value) > 1 and ":" in value and not value.startswith("/")


def _try_spawn_command(command: str) -> bool:
    try:
        parts = shlex.split(command, posix=_SYSTEM != "Windows")
    except ValueError:
        parts = [command]
    if not parts:
        return False

    executable = parts[0]
    if Path(executable).exists():
        subprocess.Popen(parts, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True

    resolved = shutil.which(executable)
    if not resolved:
        return False

    subprocess.Popen([resolved, *parts[1:]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True


def _launch_windows(app_name: str) -> bool:
    for candidate in app_name_candidates(app_name):
        try:
            if hasattr(os, "startfile"):
                os.startfile(candidate)  # type: ignore[attr-defined]
                time.sleep(1.2)
                return True
        except Exception:
            pass

        try:
            if _try_spawn_command(candidate):
                time.sleep(1.2)
                return True
        except Exception:
            pass

        if _looks_like_scheme(candidate):
            try:
                subprocess.Popen(
                    ["cmd", "/c", "start", "", candidate],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                time.sleep(1.2)
                return True
            except Exception:
                pass

    if _PYAUTOGUI:
        try:
            pyautogui.PAUSE = 0.1
            pyautogui.press("win")
            time.sleep(0.7)
            pyautogui.write(normalize_app_name(app_name), interval=0.05)
            time.sleep(0.9)
            pyautogui.press("enter")
            time.sleep(2.0)
            return True
        except Exception:
            pass

    return False


def _find_macos_bundle(app_name: str) -> Path | None:
    roots = [
        Path("/Applications"),
        Path("/System/Applications"),
        Path.home() / "Applications",
    ]
    candidates = app_name_candidates(app_name)
    wanted = {_canonicalize(name.removesuffix(".app")) for name in candidates}

    for root in roots:
        for name in candidates:
            bundle_name = name if name.lower().endswith(".app") else f"{name}.app"
            bundle_path = root / bundle_name
            if bundle_path.exists():
                return bundle_path

        if not root.exists():
            continue
        try:
            for bundle_path in root.glob("*.app"):
                if _canonicalize(bundle_path.stem) in wanted:
                    return bundle_path
        except Exception:
            continue
    return None


def _launch_macos(app_name: str) -> bool:
    for candidate in app_name_candidates(app_name):
        app_target = candidate[:-4] if candidate.lower().endswith(".app") else candidate
        try:
            result = subprocess.run(["open", "-a", app_target], capture_output=True, timeout=8)
            if result.returncode == 0:
                time.sleep(1.0)
                return True
        except Exception:
            pass

    bundle = _find_macos_bundle(app_name)
    if bundle is not None:
        try:
            result = subprocess.run(["open", str(bundle)], capture_output=True, timeout=8)
            if result.returncode == 0:
                time.sleep(1.0)
                return True
        except Exception:
            pass

    for candidate in app_name_candidates(app_name):
        try:
            if _try_spawn_command(candidate):
                time.sleep(1.0)
                return True
        except Exception:
            pass

    if _PYAUTOGUI:
        try:
            pyautogui.hotkey("command", "space")
            time.sleep(0.6)
            pyautogui.write(normalize_app_name(app_name), interval=0.05)
            time.sleep(0.8)
            pyautogui.press("enter")
            time.sleep(1.5)
            return True
        except Exception:
            pass

    return False


def _launch_linux(app_name: str) -> bool:
    for candidate in app_name_candidates(app_name):
        try:
            if _try_spawn_command(candidate):
                time.sleep(1.0)
                return True
        except Exception:
            pass

    for candidate in app_name_candidates(app_name):
        desktop_id = candidate.lower().replace(" ", "-")
        try:
            result = subprocess.run(["gtk-launch", desktop_id], capture_output=True, timeout=5)
            if result.returncode == 0:
                time.sleep(1.0)
                return True
        except Exception:
            pass

    return False


_OS_LAUNCHERS = {
    "Windows": _launch_windows,
    "Darwin": _launch_macos,
    "Linux": _launch_linux,
}


def launch_app(app_name: str) -> bool:
    launcher = _OS_LAUNCHERS.get(_SYSTEM)
    if not launcher:
        return False
    return launcher(app_name)


def close_active_app() -> bool:
    if not _PYAUTOGUI:
        return False
    try:
        if _SYSTEM == "Darwin":
            pyautogui.hotkey("command", "q")
        else:
            pyautogui.hotkey("alt", "f4")
        return True
    except Exception:
        return False


def _process_metadata(proc) -> set[str]:
    data: set[str] = set()
    try:
        info = proc.info
        if info.get("name"):
            data.add(str(info["name"]))
            data.add(Path(str(info["name"])).stem)
        if info.get("exe"):
            data.add(Path(str(info["exe"])).stem)
        cmdline = info.get("cmdline") or []
        if cmdline:
            data.add(Path(str(cmdline[0])).stem)
        for item in cmdline[1:]:
            text = str(item)
            if "/" in text or "\\" in text:
                data.add(Path(text).stem)
    except Exception:
        return data
    return data


def _matches_process(proc, targets: set[str]) -> bool:
    try:
        if proc.pid == os.getpid():
            return False
    except Exception:
        return False

    proc_values = {_canonicalize(value) for value in _process_metadata(proc) if value}
    if not proc_values:
        return False

    return any(
        target and (target in value or value in target)
        for target in targets
        for value in proc_values
        if len(target) >= 4 and len(value) >= 4
    )


def _count_matching_processes(app_name: str) -> int:
    if not _PSUTIL:
        return 0

    targets = {_canonicalize(name) for name in app_name_candidates(app_name)}
    count = 0
    for proc in psutil.process_iter(["name", "exe", "cmdline"]):
        try:
            if _matches_process(proc, targets):
                count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return count


def _terminate_with_psutil(app_name: str) -> int:
    if not _PSUTIL:
        return 0

    targets = {_canonicalize(name) for name in app_name_candidates(app_name)}
    matched = []
    for proc in psutil.process_iter(["name", "exe", "cmdline"]):
        try:
            if _matches_process(proc, targets):
                matched.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    for proc in matched:
        try:
            proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    gone, alive = psutil.wait_procs(matched, timeout=2)
    for proc in alive:
        try:
            proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return len(gone) + len(alive)


def _close_windows_by_name(app_name: str) -> int:
    closed = 0
    for candidate in app_name_candidates(app_name):
        process_name = candidate
        if not process_name.lower().endswith(".exe") and process_name.isascii() and " " not in process_name:
            process_name = f"{process_name}.exe"
        try:
            result = subprocess.run(
                ["taskkill", "/IM", process_name, "/T", "/F"],
                capture_output=True,
                timeout=6,
            )
            if result.returncode == 0:
                closed += 1
        except Exception:
            continue
    return closed


def _close_unix_by_name(app_name: str) -> int:
    closed = 0
    for candidate in app_name_candidates(app_name):
        for mode in (["pkill", "-ix", candidate], ["pkill", "-if", candidate]):
            try:
                result = subprocess.run(mode, capture_output=True, timeout=5)
                if result.returncode == 0:
                    closed += 1
            except Exception:
                continue
    return closed


def close_app(app_name: str | None = None) -> str:
    target = (app_name or "").strip()
    if not target:
        if close_active_app():
            return "Closed the active application."
        return "Could not close the active application."

    initial_matches = _count_matching_processes(target)

    if _SYSTEM == "Darwin":
        for candidate in app_name_candidates(target):
            app_target = candidate[:-4] if candidate.lower().endswith(".app") else candidate
            script = f'tell application "{app_target}" to quit'
            try:
                subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
            except Exception:
                continue

    closed = _terminate_with_psutil(target)
    if _SYSTEM == "Windows":
        closed += _close_windows_by_name(target)
    elif _SYSTEM in {"Darwin", "Linux"}:
        closed += _close_unix_by_name(target)

    remaining_matches = _count_matching_processes(target)
    if closed > 0 or (initial_matches > 0 and remaining_matches < initial_matches):
        return f"Closed {target}."
    return f"Could not find a running app matching {target}."
