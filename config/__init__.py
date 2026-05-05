# config/__init__.py
import json
import platform
from pathlib import Path

_CONFIG_PATH = Path(__file__).parent / "api_keys.json"

def get_config() -> dict:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def get_os() -> str:
    """Returns: 'windows' | 'mac' | 'linux'"""
    runtime_os = {
        "Windows": "windows",
        "Darwin": "mac",
        "Linux": "linux",
    }.get(platform.system())
    if runtime_os:
        return runtime_os

    try:
        configured = get_config().get("os_system", "").lower()
    except Exception:
        configured = ""
    return configured if configured in {"windows", "mac", "linux"} else "windows"

def is_windows() -> bool: return get_os() == "windows"
def is_mac()     -> bool: return get_os() == "mac"
def is_linux()   -> bool: return get_os() == "linux"
