# JARVIS MVP Release Gate

## Hard Release Criteria
- Deterministic parser/validator/runtime behavior for documented use cases.
- Explicit unsupported behavior for unsupported capabilities.
- No hidden retries or autonomous continuation.
- Supervised blocked-state behavior (`awaiting_clarification`, `awaiting_confirmation`) remains intact.
- Visibility payload remains stable and additive-only.

## Mandatory Automated Checks
- `python3 -m compileall parser/command_parser.py validator/command_validator.py runtime/runtime_manager.py ui/visibility_mapper.py executor/desktop_executor.py tests/test_runtime_smoke.py tests/test_cli_smoke.py tests/test_use_case_parity.py tests/test_parser_validator_contract.py tests/test_executor_contract.py tests/test_visibility_contract.py`
- `python3 -m unittest tests/test_runtime_smoke.py tests/test_cli_smoke.py tests/test_use_case_parity.py tests/test_parser_validator_contract.py tests/test_executor_contract.py tests/test_visibility_contract.py`

## Manual Verification Checklist (Scripted Local Pass)
- Open apps flow (`open Telegram and Safari`) completes predictably.
- Open folder/file flow completes or fails explicitly.
- Workspace flow stays short and deterministic.
- Search-only flow shows capped structured results.
- Search-then-open flow shows both search and open step outcomes.
- Clarification block requires explicit reply and resumes deterministically.
- Confirmation block requires explicit approval/denial and preserves boundaries.
- Fresh command while blocked restarts cleanly and does not execute previously blocked step.
- Unsupported window operations remain explicit failures with no fake success.
- CLI shell commands (`help`, `voice`, `speak on/off`, `reset`, `quit`) stay intercepted and deterministic.
- Use the deterministic command set in `docs/manual_verification_commands.md`.
