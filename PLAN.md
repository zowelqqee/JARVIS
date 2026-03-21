## JARVIS MVP Perfection Plan (Deterministic Hardening, macOS-first, Portability-Ready)

### Summary
- Goal: make the current MVP production-stable for supervised local use by hardening determinism, safety boundaries, and documented use-case parity.
- Chosen direction: deterministic hardening first, phased milestones, macOS-only runtime behavior with explicit portability preparation tasks.
- Done gate: documented MVP use-case parity plus fully green deterministic test suite.
- Non-goals for this plan: no new actions, no architecture redesign, no autonomous behavior, no cross-platform implementation in this cycle.

### Public Interfaces and Contract Policy
- Keep existing runtime/component interfaces stable (`handle_input`, parser/validator/planner/executor contracts, shared types).
- Keep existing visibility fields stable and additive-only behavior.
- Treat `next_step_hint`, `search_results`, and `window_results` as stable output contracts.
- Any new metadata introduced during hardening must be optional and internal-only unless required for deterministic behavior.
- Portability prep must not change current external behavior; it should only improve isolation and explicit capability signaling.

### Milestones (Decision-Complete)
1. **Milestone 1: Contract Lock and Deterministic Baseline**
- Build a requirements traceability matrix mapping docs use-cases/rules to concrete runtime behaviors and tests.
- Freeze deterministic precedence rules for parser, validation, blocked-state handling, and visibility hint selection.
- Remove remaining text-derived branching from user-facing hint decisions; structured-code/context only.
- Standardize canonical error-code routing for blocked vs failed states.
- Exit criteria: contract matrix committed, no behavior ambiguity in precedence paths, current smoke suites green.

2. **Milestone 2: Parser + Validator Hardening (No Surface Expansion)**
- Lock explicit parse precedence for command families that currently overlap (workspace vs open vs search vs follow-up references).
- Canonicalize alias handling and reference resolution order so the same phrase always maps identically.
- Harden validator to reject unresolved/ambiguous forms with the right error code and no target-type drift.
- Ensure unsupported requests fail as structured unsupported outcomes, not accidental clarify/pass-through.
- Exit criteria: deterministic parse/validate fixtures for high-risk phrases, no flaky branch behavior, no regression in existing follow-up/search/workspace flows.

3. **Milestone 3: Runtime + Session Invariant Hardening**
- Enforce runtime invariants in all blocked/resume paths: one active command, one active step boundary, no silent continuation.
- Harden clarification resume and confirmation resume/deny paths with explicit state persistence and reset semantics.
- Stabilize short-lived session context update rules (recent target/search/folder/project overwrite behavior).
- Ensure terminal states (`failed`, `cancelled`, `completed`) restart predictably on next command.
- Exit criteria: blocked-resume scenario matrix fully deterministic and green; no context leakage across incompatible commands.

4. **Milestone 4: Executor Reliability Hardening (macOS Behavior, No New Actions)**
- Normalize macOS command execution error classification for current supported actions (`open_*`, `close_app`, `search_local`, `list_windows`).
- Keep `focus_window` and `close_window` explicitly unsupported unless a narrow, reliable, deterministic implementation is proven.
- Harden permission/session-unavailable handling for window inspection and return explicit structured failures.
- Keep “specified app” behavior strict: no silent fallback when a specific app was requested and unavailable.
- Exit criteria: executor behavior deterministic under mocked failures and local real-run checks; unsupported paths remain honest.

5. **Milestone 5: Visibility + CLI Usability Stabilization**
- Stabilize visibility payload output rules so fields appear only when meaningful and never conflict.
- Keep failure/blocked summaries concise and deterministic; one next-step hint max with explicit precedence.
- Ensure CLI remains compact and practical: blocked prompts, completion/failure summaries, and shell command separation stay reliable.
- Keep voice mode thin and safe: one-shot behavior, concise diagnostics, no runtime bypass.
- Exit criteria: visibility-level tests cover success/blocked/failure contracts and cap behavior; CLI smoke tests remain green.

6. **Milestone 6: Portability Preparation (Design-Only, No Behavior Change)**
- Produce an explicit capability matrix for action support and reliability assumptions, scoped to current action surface.
- Isolate macOS-specific behavior boundaries cleanly in executor internals to reduce future cross-platform coupling.
- Define migration checklist for future platform adapters without introducing adapter architecture now.
- Exit criteria: documented capability/readiness map and clear future implementation seam; zero behavioral change for current MVP.

7. **Milestone 7: Final MVP Release Gate**
- Run full deterministic test stack and use-case parity checks.
- Execute scripted manual verification pass for all documented use-cases with expected blocked/failure/completion outcomes.
- Freeze release checklist: deterministic behavior, explicit unsupported behavior, no hidden retries, clear visibility at each runtime state.
- Exit criteria: all automated checks green, use-case parity signed off, no unresolved deterministic gaps.

### Test Plan (Exact Scenarios)
- Add/maintain deterministic tests for each documented use-case path: open apps, open file/folder, workspace setup, search+open, clarification, safe failure, context follow-up, window listing.
- Add/maintain deterministic blocked/resume tests: clarification loop, confirmation approve/deny, cancellation, post-terminal fresh command behavior.
- Add/maintain visibility contract tests: field presence rules, completion/failure/blocked summaries, capped result lists, one-hint-only rule.
- Add/maintain executor failure-shape tests: unavailable app, invalid URL, permission/session unavailability, unsupported actions.
- Add/maintain CLI smoke tests: shell command interception, voice failure diagnostics, speak toggles, runtime routing separation.
- Mandatory validation commands per milestone gate:
- `python3 -m compileall ...` for touched modules.
- `python3 -m unittest tests/test_runtime_smoke.py tests/test_cli_smoke.py`.
- Use-case parity test command set (to be added in this plan) must run fully deterministic and green before release.

### Assumptions and Defaults
- “Perfect MVP” means deterministic and reliable within existing MVP boundaries, not feature breadth expansion.
- macOS remains the only execution platform in this cycle; portability work is preparation-only.
- Unsupported capabilities remain explicit failures unless reliability and safety standards are met without architecture expansion.
- Existing action surface and shared type contracts remain fixed.
- Preference for strictness over clever inference when ambiguity exists.
