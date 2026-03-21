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
- Latest full run: `86 tests`, all passing.

## Locked Contracts
- Stable runtime entrypoint: `RuntimeManager.handle_input(...)`
- Stable visibility output contracts:
  - `next_step_hint`
  - `search_results`
  - `window_results`
- Explicit unsupported window-management behavior remains enforced.

## Outstanding Manual Checks
- Run the scripted local CLI checklist in:
  - `docs/manual_verification_commands.md`
- Confirm behavior in a real interactive macOS desktop session for:
  - app launch/open behavior with installed apps
  - window-listing availability by session permissions
  - voice helper permission/access behavior

## Latest Manual Pass (2026-03-22, local shell run)
- `run telegram` -> parsed as `open_app`; no clarification loop.
- Clarification restart (`htlp` -> `open Safari`) -> fresh command restart worked.
- Confirmation boundary (`close Telegram` -> `yes` / `no`) -> boundary behavior correct (`failed` with app state or `cancelled` on denial).
- Search follow-up (`search the JARVIS folder for markdown files` -> `open 1`) -> search results persisted and indexed follow-up resolved deterministically.
- Window listing (`list windows`) -> explicit honest failure in this session (`Visible window inspection is unavailable...`), no fake data.
- CLI shell command interception (`help`, `voice`, `speak on/off`, `reset`, `quit`) -> deterministic and isolated from runtime parsing.

Note:
- In this specific shell session, desktop `open` actions fail with LaunchServices `-10661` for app/file/folder opening. Runtime behavior remains explicit and contract-correct (structured failure, no hidden fallback success).
