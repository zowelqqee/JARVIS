# JARVIS Cross-Platform TTS Backend Plan

## Purpose
- Keep one living source of truth for the TTS backend rollout.
- Reflect the real state of the codebase, not an outdated greenfield architecture sketch.
- Continue the work in small vertical slices without a broad voice-stack rewrite.

## Goal
- Keep the current text-first core intact.
- Keep CLI, dispatcher, and speech presenter dependent only on a shared TTS abstraction.
- Preserve the legacy macOS `say` path as a fallback until the native backend is actually proven in live use.
- Make the future Windows port straightforward by keeping product-level voice selection backend-neutral.

## What “Alive” Means Here
- Not “more diagnostics.”
- “Alive” means JARVIS can actually run through the real CLI voice path with the native backend selected, speak through the shared abstraction, survive fallback cleanly, and be understandable to operate without source-diving.
- The next work should therefore move from architecture polishing to rollout proof, native startup stability, and a clear default-backend decision.

## Current Reality Snapshot

### Already Done
- `voice/tts_provider.py` is already expanded beyond the old `say`-only contract.
- Backend-neutral models already exist in `voice/tts_models.py`.
- Product-level voice profiles already exist in `voice/voice_profiles.py`.
- `voice/tts_manager.py` already owns backend selection, profile resolution, and fallback.
- The current macOS `say` backend is already wrapped as a legacy backend behind the manager.
- CLI/operator helpers already exist:
  - `voice tts backend`
  - `voice tts voices`
  - `voice tts current`
  - `voice tts doctor`
  - `voice readiness`
  - `voice gate`
- Experimental native macOS backend already exists:
  - `voice/backends/macos_native.py`
  - `voice/native_hosts/macos_tts_host.swift`
- Native macOS backend is now preferred by default on macOS.
- `JARVIS_TTS_MACOS_NATIVE=0` is the explicit opt-out to force legacy `say`.
- `JARVIS_TTS_MACOS_NATIVE=1` remains a valid explicit pin during rollout smoke.
- Native diagnostics already expose backend state, fallback reason, toolchain mismatch context, developer-dir override context, and follow-up commands.
- With `DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer`, the native backend can already become the active backend in the current environment.

### Not Done Yet
- Native macOS is already the default code path on macOS, but that default is not yet signed off by one successful live microphone turn.
- One successful live microphone turn under the native path is not yet signed off end-to-end because local `Speech Recognition` permission blocked the latest manual smoke.
- The final voice-readiness artifact is still intentionally missing because live manual verification cannot be recorded honestly while that permission blocker remains.
- Windows host/backend work has not started.

### Current Bottleneck
- The main bottleneck is no longer “missing architecture.”
- The main bottleneck is proving and stabilizing the native macOS path in real usage, then promoting it safely.

### Latest Observed Native Smoke
- On April 9, 2026, the plain native CLI smoke under
  - `python3 cli.py`
  - default macOS native preference
  confirmed:
  - `voice tts backend` reports `macos_native`
  - `voice tts doctor` reports the native backend as selected and available
  - `voice readiness` reports `native tts smoke status: ready`
  - `speak on` plus a text-first question path completes without `speech: unavailable.`
  - the first real `voice` turn does not expose a TTS runtime bug; it stops at `Speech recognition access was denied`
  - `voice telemetry write` records that same blocker in `tmp/qa/voice_telemetry.json`
  - `voice gate` reports `grant_live_voice_permissions`
- Until that permission is granted and one live turn succeeds, the rollout should be treated as “native TTS path proven for text-first CLI output, but live microphone sign-off still blocked by local macOS permission state.”
- The rollout helper surface now also preserves that live blocker through `voice telemetry write`:
  - `voice telemetry artifact` shows the latest recorded capture blocker and hint
  - `voice readiness` and `voice gate` can now switch their `next step` directly to the permission-recovery path instead of only reporting missing manual verification
- The rollout helper surface can now also detect that blocker proactively through live-capture permission preflight:
  - even on an empty telemetry path, `voice readiness` / `voice gate` can report `live capture preflight status: blocked`
  - this reduces the need for a sacrificial failed `voice` turn just to learn that macOS permissions are the current blocker

## Non-Negotiable Constraints
- Do not do a large voice-stack refactor.
- Do not move routing, dispatcher, or answer logic into backend-specific code.
- Do not let CLI or speech presenter depend on raw platform voice names.
- Raw native voice ids may exist only inside backend adapters, host protocol payloads, or backend diagnostics.
- Do not remove `voice/tts_macos.py` until the native backend is proven as a stable primary path.
- Do not spend more time polishing helper wording unless a real failing smoke needs it.

## Current Source of Truth in Code
- Public contract:
  - `voice/tts_provider.py`
- Backend-neutral models:
  - `voice/tts_models.py`
- Product voice profiles:
  - `voice/voice_profiles.py`
- Backend selection and fallback:
  - `voice/tts_manager.py`
- Legacy macOS fallback:
  - `voice/tts_macos.py`
- Native macOS adapter:
  - `voice/backends/macos_native.py`
- Native macOS host:
  - `voice/native_hosts/macos_tts_host.swift`
- Operator/debug helpers:
  - `voice/status.py`
  - `voice/readiness.py`
  - `voice/gate.py`
  - `voice/tts_operator_hints.py`
- Manual smoke checklist:
  - `docs/manual_voice_verification.md`

## Backend Model We Are Keeping

### Stable Core Contract
- `speak(utterance) -> TTSResult`
- `stop() -> bool`
- `list_voices(locale_hint=None) -> list[VoiceDescriptor]`
- `resolve_voice(profile, locale) -> VoiceDescriptor | None`
- `is_available() -> bool`
- `capabilities() -> BackendCapabilities`

### Stable Product-Level Voice Model
- Core code works with product-level profiles such as:
  - `ru_assistant_male`
  - `ru_assistant_female`
  - `ru_assistant_any`
  - `en_assistant_male`
  - `en_assistant_female`
  - `en_assistant_any`
- Locale-specific ranking remains backend-specific.
- Core code must never need to know raw Apple or future Windows voice identifiers.

### Stable Fallback Model
- On macOS, backend preference currently remains:
  - native macOS backend by default when not explicitly disabled and available
  - legacy `say` backend as fallback
- This fallback chain is intentional and should stay intact until native rollout promotion is complete.

## Phase Status

### Phase 1. Foundation
Status:
- Done

What is already complete:
- expanded TTS contract
- backend-neutral models
- voice profiles
- backend manager
- legacy macOS backend behind manager

### Phase 2. Operator Surface
Status:
- Done

What is already complete:
- backend introspection
- visible voice listing
- current profile resolution display
- doctor/debug aggregation
- readiness/gate helpers

### Phase 3. Native macOS Opt-In Rollout
Status:
- In progress

This is now the critical path.

### Phase 4. Native macOS as Default
Status:
- Code path landed; live sign-off pending

### Phase 5. Windows Backend
Status:
- Not started

## Critical Path From Here
1. Stop treating native macOS as only a diagnostic experiment.
2. Prove the real native path in manual CLI usage.
3. Decide the supported launch path for native development and smoke.
4. Promote native to default on macOS only after real proof, not just unit coverage.
5. Start Windows only after the macOS rollout policy is settled.

## Execution Plan

### Slice 1. Native macOS Manual Smoke Sign-Off
Goal:
- Prove the native backend in the actual CLI path, not just through helper commands.

Why this is next:
- The manager, profiles, legacy fallback, and operator tooling are already good enough.
- More architecture work now gives little value compared with a real smoke result.

Expected work:
- Mostly manual verification and only targeted code changes if the smoke reveals a concrete runtime bug.

Primary commands:
```bash
python3 cli.py
```

Inside CLI:
```text
voice tts backend
voice tts doctor
speak on
что ты умеешь
voice
```

Interpretation rules:
- If `voice tts backend` shows `macos_native`, native selection is working.
- If text-first spoken output completes without `speech: unavailable.`, the shared spoken-output path is working.
- If `voice` fails because `Speech Recognition` or `Microphone` permission is denied, treat that as an environment blocker, not a TTS architecture regression.
- If capture succeeds but spoken output fails under native, that is a real code/runtime bug and becomes the next slice.

Done when:
- native backend is selected in the real CLI path
- text-first spoken output works through the shared path
- and either:
  - one live `voice` turn succeeds, or
  - the only remaining blocker is explicitly documented as local permission state

Current status:
- native backend selection: confirmed
- text-first spoken output through native path: confirmed
- live `voice` turn: blocked by local `Speech Recognition` permission, not by a confirmed TTS runtime failure
- `voice readiness` / `voice gate`: aligned with the real blocker and already point to `grant_live_voice_permissions`
- final `voice readiness` artifact: intentionally still missing until live manual verification can be recorded honestly

Stop condition:
- If the smoke fails, fix only the specific failing runtime issue revealed by the smoke.
- Do not drift into more helper polish unless the failure is opaque without it.

### Slice 2. Reduce Native Startup Friction
Goal:
- Decide one supported native development/smoke launch path that operators can trust.

Current reality:
- `DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer` is currently the known working path in this environment.
- plain `python3 cli.py` now also reaches the native path because the backend auto-selects the known-good Xcode developer dir when no explicit override is present.
- `scripts/run_voice_native_smoke.sh` remains an explicit pinned shortcut for manual smoke and override debugging.

Options in preferred order:
1. Use plain `python3 cli.py` as the normal macOS development workflow now that native startup no longer depends on a shell-level env override.
2. Allow explicit `DEVELOPER_DIR=... python3 cli.py` or `scripts/run_voice_native_smoke.sh` when local toolchain debugging needs a pinned override.
3. Only outside the repo, if needed, align global `xcode-select` manually.

Do not do in code:
- Do not change machine-global developer-tool selection from the repository.
- Do not hide environment assumptions silently.

Done when:
- one canonical command is documented and used consistently by helpers and manual verification
- helper output and manual docs no longer disagree about how native smoke should be launched

Current status:
- normal default path works: `python3 cli.py`
- explicit pinned shortcut still exists: `scripts/run_voice_native_smoke.sh`
- native backend is now preferred by default on macOS unless `JARVIS_TTS_MACOS_NATIVE=0` disables it
- remaining work is live sign-off after macOS `Microphone` / `Speech Recognition` permissions are granted

### Slice 3. Promote Native macOS to the Default Backend
Goal:
- Make native macOS the normal backend on macOS while preserving safe fallback.

Preconditions:
- Slice 1 is signed off
- Slice 2 has one canonical launch path
- fallback to legacy `say` still works
- relevant manager tests cover selection and fallback

Expected code touchpoints:
- `voice/tts_manager.py`
- `voice/backends/macos_native.py`
- `tests/test_tts_manager.py`
- `tests/test_tts_macos_native.py`
- possibly CLI smoke coverage if default selection semantics change

Done when:
- native backend is preferred by default on macOS
- legacy `say` remains an emergency fallback
- operator helpers still make fallback and selected backend obvious

Current status:
- code path landed: native backend is now preferred by default on macOS
- plain `python3 cli.py` on this machine now also selects `macos_native` because the native backend auto-selects the known-good Xcode developer dir when no explicit `DEVELOPER_DIR` override is present
- helper output now prefers plain `python3 cli.py` when no explicit override is needed
- `scripts/run_voice_native_smoke.sh` remains a useful pinned shortcut for explicit smoke and override debugging

### Slice 4. Native Rollout Cleanup
Goal:
- Remove rollout-era rough edges after native is already the default.

Examples:
- simplify opt-in/override logic if no longer needed
- trim duplicated rollout-specific branches in operator helpers
- tighten native readiness wording once the default policy is stable

Do not start this early:
- no cleanup before the default-backend decision lands

### Slice 5. Prepare Windows Without Reopening Core Design
Goal:
- Start Windows from the already-proven manager/profile/host model.

Work order:
1. Freeze the contract lessons learned from macOS.
2. Add:
  - `voice/backends/windows_native.py`
  - `voice/native_hosts/windows_tts_host.cs`
3. Reuse the same profile and manager model.
4. Add Windows-specific smoke and contract tests.

Done when:
- Windows speaks through the same Python-side manager contract
- CLI and speech presenter still do not care which platform backend is active

## What We Should Not Do Next
- Do not redesign the contract again unless macOS rollout exposes a real gap.
- Do not add more backend doctor variants “just in case.”
- Do not start Windows before macOS native default policy is decided.
- Do not reintroduce raw voice-name coupling into CLI or presenter code.
- Do not remove the legacy backend early.

## Testing Strategy From This Point

### For Code Changes
- Run only the relevant unit tests for touched backend/manager/helper files.
- Keep CLI smoke tests around backend interception and current-path compatibility green.

### For Rollout Progress
- Prefer real operator/manual smoke over more synthetic diagnostic expansion.
- Update `docs/manual_voice_verification.md` only when the supported workflow or real blocker interpretation changes.

### Evidence We Actually Care About Now
- native backend selected in CLI
- text-first spoken path works
- one real microphone turn works, or is blocked only by permissions
- fallback still works when native is unavailable

## Session Workflow
1. Run `git status --short`.
2. Read this file and only the code touched by the next slice.
3. Pick one slice from the critical path.
4. Implement only that slice.
5. Run relevant tests.
6. If reality changed, update this document locally instead of letting it drift.

## Immediate Next Step
- The next logical step is still Slice 1, but only after granting `Microphone` and `Speech Recognition` to the plain CLI path:
  - run `python3 cli.py`
  - verify `voice tts backend`
  - verify `speak on` plus a text-first spoken answer
  - run `voice`
  - if capture succeeds, run `voice telemetry write`
  - if the turn is genuinely unblocked, run `voice readiness write`
- If the only blocker remains permissions, keep treating it as an environment blocker rather than reopening TTS architecture work.
- If a real runtime bug appears, the next code slice must fix that bug directly rather than expanding helper output again.
