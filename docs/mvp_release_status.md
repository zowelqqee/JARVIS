# JARVIS MVP Release Status

## Scope
- Deterministic hardening across parser, validator, runtime/session invariants, executor reliability, visibility/CLI usability.
- macOS-first executor behavior with explicit unsupported boundaries.

## Current Gate Status
- Automated compile checks: PASS
- Automated deterministic test suites: PASS
  - `tests/test_runtime_smoke.py`
  - `tests/test_cli_smoke.py`
  - `tests/test_use_case_parity.py`
  - `tests/test_parser_validator_contract.py`
  - `tests/test_executor_contract.py`
  - `tests/test_visibility_contract.py`
  - `tests/test_voice_input_contract.py`
- Latest full run: `95 tests`, all passing.
- Manual scripted verification pass: PASS (`docs/manual_verification_commands.md`, 2026-03-22)

## Locked Contracts
- Stable runtime entrypoint: `RuntimeManager.handle_input(...)`
- Stable visibility output contracts:
  - `next_step_hint`
  - `search_results`
  - `window_results`
- Explicit unsupported window-management behavior remains enforced.

## Remaining To Final 100%
- None for the current deterministic MVP scope.
- Optional environment verification only:
  - repeat one interactive desktop pass in a session with full macOS app-launch/window-inspection permissions.

## Release Hygiene
- Clean release commit created:
  - `3ed5bd4` (`release: harden executor/voice and lock deterministic MVP gates`)
- MVP release tag created:
  - `mvp-2026-03-22`

## Latest Hardening Delta (2026-03-22)
- Executor now classifies LaunchServices/session-unavailable failures for `open_*` actions deterministically as structured `EXECUTION_FAILED` outcomes.
- User-facing failure message for that class is explicit and actionable:
  - run JARVIS from an active macOS desktop login session and retry.
- Added contract tests for:
  - folder open with LaunchServices `-10661`/`kLSExecutableIncorrectFormat`
  - app open error text that contains both "Unable to find application" and LaunchServices signals (must not misclassify as `APP_UNAVAILABLE`).
- Executor now includes deterministic `.app` bundle-path fallback for known app names when `open -a <name>` lookup fails.
- Explicit app-targeted `open_file` / `open_folder` now reuse the same fallback path resolution.
- Added contract tests for:
  - open-app fallback success via resolved bundle path
  - app-targeted open-file fallback success via resolved bundle path
  - fallback miss remains explicit `APP_UNAVAILABLE`
  - non-launchable app bundle (`kLSNoExecutableErr`) maps to explicit `APP_UNAVAILABLE`
- Voice helper crash diagnostics were hardened:
  - negative helper exit codes (for example `-6`/`SIGABRT`) now map to explicit `VOICE_HELPER_CRASH` with a concise actionable hint.
- Added deterministic voice-input error normalization tests in `tests/test_voice_input_contract.py`.

## Latest Manual Pass (2026-03-22, scripted CLI sweep)
- Open app alias:
  - `run telegram` -> deterministic `open_app` path; explicit `APP_UNAVAILABLE` on this session (`/Applications/Telegram.app` not launchable).
- Clarification resume:
  - `htlp` -> `awaiting_clarification`
  - follow-up `open Safari` -> fresh-command restart path works; deterministic `open_app` execution path.
- Confirmation boundary:
  - `close Telegram` -> `awaiting_confirmation`
  - `yes` -> resumes boundary and fails explicitly as `APP_NOT_RUNNING`
  - `no` -> deterministic `cancelled`, blocked step not executed.
- Search + indexed follow-up:
  - `search the JARVIS folder for markdown files` -> completed search with visible capped results (`20` matches)
  - `open 1` -> deterministic follow-up target resolution; explicit execution failure (`desktop session unavailable for opening files`).
- Workspace path resolution:
  - `prepare workspace for JARVIS` -> structured workspace plan (`Visual Studio Code`, `JARVIS`, `Safari`) with explicit `APP_UNAVAILABLE` on current macOS session.
- Window listing:
  - `list windows` -> explicit honest failure (`Visible window inspection is unavailable in the current macOS session.`), no fake data.
- CLI shell command interception:
  - `help`, `speak on`, `speak off`, `reset`, `quit` -> handled by shell layer, not runtime parsing.
- Voice diagnostics:
  - `voice` -> explicit structured denial path with actionable privacy hint, no generic failure text.

Note:
- This session still has macOS desktop execution limits for real `open_*` operations and window inspection. Runtime remains contract-correct with explicit structured failures and no hidden retries.
