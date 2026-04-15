# actions/protocol_manager.py
# JARVIS Protocol Engine
#
# Protocols are named sequences of steps stored in config/protocols.json.
# Each step uses the same tool names as the main JARVIS tool system,
# plus built-ins: speak | wait | close_all_windows
#
# Designed to scale: users and JARVIS can add/edit/remove protocols at runtime.
#
# Public API:
#   run_protocol(name_or_phrase, speak, player) → str
#   add_protocol(protocol_id, data)             → str
#   remove_protocol(protocol_id)                → str
#   list_protocols()                            → str
#   protocol(parameters, ..., speak)            → str   ← called from main.py

import json
import sys
import time
import platform
import subprocess
from pathlib import Path
from typing import Callable


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR       = get_base_dir()
PROTOCOLS_PATH = BASE_DIR / "config" / "protocols.json"


# ─── Storage ──────────────────────────────────────────────────────────────────

def _load() -> dict:
    try:
        return json.loads(PROTOCOLS_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"[Protocol] Failed to load protocols: {e}")
        return {}


def _save(data: dict) -> None:
    PROTOCOLS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROTOCOLS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


# ─── Built-in step actions ─────────────────────────────────────────────────────

def _close_all_windows() -> str:
    """
    Gracefully closes all visible application windows on Windows.
    Excludes system processes and the JARVIS/Python process itself.
    """
    if platform.system() != "Windows":
        return "close_all_windows: not on Windows — skipped."

    script = r"""
$sys = @('explorer','python','pythonw','py','python3','powershell','pwsh',
         'conhost','dwm','winlogon','csrss','wininit','services','lsass',
         'smss','svchost','system','idle','registry','taskhostw','sihost',
         'runtimebroker','startmenuexperiencehost','searchui','shellexperiencehost')
Get-Process | Where-Object {
    $_.MainWindowHandle -ne 0 -and
    $sys -notcontains $_.Name.ToLower()
} | ForEach-Object {
    try { $_.CloseMainWindow() | Out-Null } catch {}
}
"""
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", script.strip()],
            capture_output=True,
            timeout=10
        )
        print("[Protocol] All windows closed.")
        return "All windows closed."
    except Exception as e:
        return f"close_all_windows failed: {e}"


def _builtin_wait(seconds: float) -> str:
    time.sleep(max(0.0, float(seconds)))
    return f"Waited {seconds}s."


# ─── Step executor ─────────────────────────────────────────────────────────────

def _run_step(step: dict, speak: Callable | None, player) -> str:
    """Execute a single protocol step. Returns result string."""
    tool   = step.get("tool", "")
    params = step.get("parameters", {})
    desc   = step.get("description", tool)

    print(f"[Protocol] Step: [{tool}] {desc}")

    # ── Built-ins ──────────────────────────────────────────
    if tool == "speak":
        text = params.get("text", "")
        if text and speak:
            speak(text)
        return f"Spoke: {text[:60]}"

    if tool == "wait":
        return _builtin_wait(params.get("seconds", 1.0))

    if tool == "close_all_windows":
        return _close_all_windows()

    # ── Delegate to existing JARVIS tools ──────────────────
    try:
        from agent.executor import _call_tool
        return _call_tool(tool, params, speak) or "Done."
    except Exception as e:
        raise RuntimeError(f"Step [{tool}] failed: {e}") from e


# ─── Protocol runner ───────────────────────────────────────────────────────────

def _resolve_protocol(name_or_phrase: str, protocols: dict) -> tuple[str, dict] | tuple[None, None]:
    """
    Find a protocol by:
      1. Exact ID match (e.g. "work", "home")
      2. Trigger phrase substring match (case-insensitive)
      3. Protocol name match
    Returns (protocol_id, protocol_data) or (None, None).
    """
    query = name_or_phrase.lower().strip()

    # 1. Exact ID
    if query in protocols:
        return query, protocols[query]

    # 2. Trigger phrase
    for pid, pdata in protocols.items():
        for phrase in pdata.get("trigger_phrases", []):
            if phrase.lower() in query or query in phrase.lower():
                return pid, pdata

    # 3. Protocol display name
    for pid, pdata in protocols.items():
        if pdata.get("name", "").lower() in query:
            return pid, pdata

    return None, None


def run_protocol(
    name_or_phrase: str,
    speak: Callable | None = None,
    player=None,
) -> str:
    protocols = _load()

    pid, pdata = _resolve_protocol(name_or_phrase, protocols)
    if not pdata:
        available = ", ".join(
            f"'{p.get('name', k)}'" for k, p in protocols.items()
        )
        return (
            f"Protocol '{name_or_phrase}' not found, sir. "
            f"Available: {available or 'none'}."
        )

    display_name = pdata.get("name", pid)
    steps        = pdata.get("steps", [])

    print(f"[Protocol] Activating: {display_name} ({len(steps)} steps)")
    if player:
        player.write_log(f"[Protocol] {display_name}")

    results  = []
    failures = []

    for i, step in enumerate(steps, 1):
        optional = step.get("optional", False)
        try:
            result = _run_step(step, speak=speak, player=player)
            results.append(result)
            print(f"[Protocol] Step {i} OK: {result[:60]}")
        except Exception as e:
            msg = f"Step {i} [{step.get('tool')}]: {e}"
            print(f"[Protocol] {msg}")
            if not optional:
                failures.append(msg)

    if failures:
        return (
            f"Protocol '{display_name}' completed with errors:\n"
            + "\n".join(failures)
        )

    return f"Protocol '{display_name}' activated successfully, sir."


# ─── Management API ────────────────────────────────────────────────────────────

def add_protocol(protocol_id: str, data: dict) -> str:
    """Add or update a protocol."""
    if not protocol_id or not data.get("steps"):
        return "Protocol must have an ID and at least one step."
    protocols = _load()
    protocols[protocol_id.lower().strip()] = data
    _save(protocols)
    return f"Protocol '{data.get('name', protocol_id)}' saved."


def remove_protocol(protocol_id: str) -> str:
    """Remove a protocol by ID."""
    protocols = _load()
    pid = protocol_id.lower().strip()
    if pid not in protocols:
        return f"Protocol '{protocol_id}' not found."
    name = protocols[pid].get("name", pid)
    del protocols[pid]
    _save(protocols)
    return f"Protocol '{name}' removed."


def list_protocols() -> str:
    """Return a human-readable list of all protocols."""
    protocols = _load()
    if not protocols:
        return "No protocols defined yet, sir."
    lines = ["Available protocols:"]
    for pid, pdata in protocols.items():
        name    = pdata.get("name", pid)
        desc    = pdata.get("description", "")
        phrases = pdata.get("trigger_phrases", [])
        lines.append(f"\n  [{pid}] {name}")
        if desc:
            lines.append(f"    {desc}")
        if phrases:
            lines.append(f"    Trigger: {', '.join(phrases[:3])}")
    return "\n".join(lines)


# ─── Main entry point (called from main.py) ────────────────────────────────────

def protocol(
    parameters:     dict,
    response=None,
    player=None,
    session_memory=None,
    speak:          Callable | None = None,
) -> str:
    """
    Called from main.py when Gemini invokes the 'protocol' tool.

    parameters:
        name   : Protocol ID or trigger phrase (e.g. 'work', 'home', 'за работу')
        action : list | add | remove  (optional, default: run)
        data   : JSON string with protocol definition for 'add' action
    """
    p      = parameters or {}
    action = p.get("action", "run").lower().strip()
    name   = p.get("name", "").strip()

    if action == "list":
        return list_protocols()

    if action == "remove":
        if not name:
            return "Please specify which protocol to remove, sir."
        return remove_protocol(name)

    if action == "add":
        raw = p.get("data", "")
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError as e:
            return f"Invalid protocol data: {e}"
        return add_protocol(name, data)

    # Default: run
    if not name:
        return "Please specify which protocol to activate, sir."
    return run_protocol(name, speak=speak, player=player)
