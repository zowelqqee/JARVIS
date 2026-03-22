Great. Here is the exact plan to get MVP from ~90% to **100% release-ready**.

**1. Define “100%” (done criteria)**
1. All supervised flows work deterministically in real local use.
2. Core actions succeed when environment is valid: `open_app`, `open_file`, `open_folder`, `open_website`, `search_local`.
3. Blocked/confirmation/clarification behavior remains strict and unchanged.
4. Voice mode is reliable enough for one-shot local testing (or fails with clear actionable diagnostics).
5. Full automated suite is green.
6. Manual verification checklist is green in your real shell session.
7. Repo is clean for release (no `pyc/__pycache__` tracked, clear commit set).

**2. Milestone A: Fix macOS execution environment reliability (highest priority)**
1. Run a focused LaunchServices diagnostic pass from your exact shell.
2. Validate these commands directly:
   1. `open -a Finder /Users/arseniyabramidze/JARVIS`
   2. `open -a Safari`
   3. `open /Users/arseniyabramidze/JARVIS`
   4. `osascript -e 'tell application "Finder" to activate'`
3. If `-10661` persists, implement deterministic executor classification for this condition with clear message and no fake fallback success.
4. Add a small executor preflight check for desktop-session availability before `open_*` actions.
5. Exit criteria: open-actions either succeed in real session or fail with precise structured reason + actionable message.

**3. Milestone B: Executor hardening to production-stable behavior**
1. Keep action surface unchanged.
2. Tighten failure-code mapping for `open_app/open_file/open_folder/open_website/list_windows`.
3. Keep strict “explicit app requested” behavior (no silent default fallback when app is missing).
4. Keep `focus_window` and `close_window` explicitly unsupported.
5. Add targeted executor contract tests for:
   1. LaunchServices unavailable/session unavailable shape
   2. permission denied shape
   3. app unavailable shape
   4. invalid URL shape
6. Exit criteria: deterministic failure-shape matrix fully covered and green.

**4. Milestone C: Voice stability**
1. Stabilize `voice` one-shot helper lifecycle (compile/run/error mapping).
2. Guarantee concise error categories:
   1. microphone permission denied
   2. speech permission denied
   3. helper compile/run failure
   4. empty/no recognition
3. Keep `/voice` and `voice` command behavior unchanged.
4. Add CLI smoke tests for voice failure-path messaging consistency.
5. Exit criteria: no vague `Voice capture failed` path remains.

**5. Milestone D: Visibility + CLI polish lock**
1. Keep current visibility contracts stable.
2. Ensure optional fields appear only when meaningful.
3. Ensure one `next_step_hint` max, deterministic precedence only.
4. Add/keep tests for blocked/success/failure payload consistency and CLI command interception.
5. Exit criteria: visibility and CLI tests fully green and stable.

**6. Milestone E: Final release gate**
1. Run full automated gate:
   1. `python3 -m compileall parser/command_parser.py validator/command_validator.py runtime/runtime_manager.py ui/visibility_mapper.py executor/desktop_executor.py tests/test_runtime_smoke.py tests/test_cli_smoke.py tests/test_use_case_parity.py tests/test_parser_validator_contract.py tests/test_executor_contract.py tests/test_visibility_contract.py`
   2. `python3 -m unittest tests/test_runtime_smoke.py tests/test_cli_smoke.py tests/test_use_case_parity.py tests/test_parser_validator_contract.py tests/test_executor_contract.py tests/test_visibility_contract.py`
2. Run manual checklist from `docs/manual_verification_commands.md`.
3. Update `docs/mvp_release_status.md` with final pass/fail and exact date.
4. Exit criteria: automated + manual pass both green.

**7. Release hygiene**
1. Keep `.gitignore` active for Python cache artifacts.
2. Remove tracked cache artifacts from index once (already started).
3. Create one clean release commit with only source/docs/tests changes.
4. Tag MVP release commit.

If you want, I can start executing Milestone A right now and drive it to closure step-by-step.