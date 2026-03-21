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

