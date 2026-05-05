import platform

from actions.app_control import launch_app, normalize_app_name


_SYSTEM = platform.system()


def open_app(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    app_name = (parameters or {}).get("app_name", "").strip()

    if not app_name:
        return "No application name provided."

    if _SYSTEM not in {"Windows", "Darwin", "Linux"}:
        return f"Unsupported operating system: {_SYSTEM}"

    normalized = normalize_app_name(app_name)
    print(f"[open_app] Launching: '{app_name}' -> '{normalized}' ({_SYSTEM})")

    if player:
        player.write_log(f"[open_app] {app_name}")

    try:
        if launch_app(normalized):
            return f"Opened {app_name}."
        if normalized.lower() != app_name.lower() and launch_app(app_name):
            return f"Opened {app_name}."
        return (
            f"Could not confirm that {app_name} launched. "
            f"It may still be loading, or it might not be installed."
        )
    except Exception as e:
        print(f"[open_app] Error: {e}")
        return f"Failed to open {app_name}: {e}"
