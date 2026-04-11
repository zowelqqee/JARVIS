# JARVIS MVP macOS Capability Matrix

## Purpose
- Declare current MVP action capabilities and reliability assumptions.
- Keep unsupported behavior explicit and deterministic.
- Prepare clear seams for future platform work without changing current behavior.

## Action Capability Matrix

| Action | macOS MVP Status | Deterministic Behavior | Failure Shape |
| --- | --- | --- | --- |
| `open_app` | Supported | Uses `open -a <App>`; returns success only on real launch/focus request success. | `APP_UNAVAILABLE`, `EXECUTION_FAILED`, `PERMISSION_DENIED` |
| `focus_app` | Supported | Activates only running app; does not auto-launch. | `APP_NOT_RUNNING`, `EXECUTION_FAILED` |
| `open_file` | Supported | Requires existing file path; supports explicit app via `open -a <App> <Path>`. | `TARGET_NOT_FOUND`, `APP_UNAVAILABLE`, `EXECUTION_FAILED` |
| `open_folder` | Supported | Requires existing folder path; supports explicit app via `open -a <App> <Path>`. | `TARGET_NOT_FOUND`, `APP_UNAVAILABLE`, `EXECUTION_FAILED` |
| `open_website` | Supported | Requires valid `http://` or `https://` URL. | `INVALID_URL`, `EXECUTION_FAILED` |
| `list_windows` | Supported (session-dependent) | Returns visible windows from CoreGraphics when available. | `UNSUPPORTED_ACTION`, `EXECUTION_FAILED` |
| `focus_window` | Explicitly unsupported | Fails deterministically; no fake app-level fallback. | `UNSUPPORTED_ACTION` |
| `close_window` | Explicitly unsupported | Fails deterministically; no forced close behavior. | `UNSUPPORTED_ACTION` |
| `close_app` | Supported (safe quit only) | Requests normal quit; no force-quit path. | `APP_NOT_RUNNING`, `EXECUTION_FAILED` |
| `search_local` | Supported | Performs deterministic filesystem traversal in explicit scope. | `MISSING_PARAMETER`, `UNSUPPORTED_TARGET`, `EXECUTION_FAILED` |
| `prepare_workspace` | Executor-direct unsupported | Must run as planned sub-steps only. | `UNSUPPORTED_ACTION` |

## Portability-Preparation Seams (Design-Only)
- Keep executor dispatch centralized in `executor/desktop_executor.py::execute_step`.
- Keep action-specific behavior isolated by per-action helper functions.
- Keep unsupported actions explicit at dispatch-time and action-helper level.
- Keep platform gate explicit (`sys.platform == "darwin"`) at runtime entry to executor.
- Keep structured error codes stable so future adapters can preserve current contracts.

## Migration Checklist (Future, Not Implemented in this Cycle)
- Define per-platform action capability table with same action names and error codes.
- Preserve current `ActionResult` shape and deterministic failure semantics.
- Implement adapter-specific window behavior only where reliable and testable.
- Add parity tests that run shared behavior scenarios against each platform adapter.
- Keep unsupported paths explicit when capability confidence is below MVP safety threshold.

