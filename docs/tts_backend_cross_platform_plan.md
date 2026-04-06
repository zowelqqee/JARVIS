# JARVIS Cross-Platform TTS Backend Plan

## Goal
- Replace the current macOS-only, `say`-centric TTS path with a backend architecture that stays stable when JARVIS later moves to Windows.
- Keep the text-first core intact: CLI, speech presenter, dispatcher, and follow-up logic should not care which OS-specific speech engine is active.
- Make voice choice explicit through product-level profiles like `ru_assistant_male`, not through platform-specific voice names like `Milena` or `Daniel`.

## Current Problem
- The current provider in `voice/tts_macos.py` is tightly coupled to the macOS `say` command.
- macOS exposes different voice sets through different APIs. A voice visible in UI may not be surfaced in the same way via `say`.
- The current code can choose a better English voice, but Russian male/system-assistant voices are inconsistent and fragile.
- This design will not port cleanly to Windows because the current control surface is built around macOS voice names and `say` semantics.

## Target End State
- JARVIS uses one stable TTS contract across all operating systems.
- Platform-specific backends live behind a shared backend manager.
- Voice selection is based on abstract profiles:
  - `ru_assistant_male`
  - `ru_assistant_female`
  - `en_assistant_male`
  - `en_assistant_female`
- Every backend can:
  - list voices
  - resolve a profile to a native voice
  - speak text
  - stop active speech
  - report capabilities and structured errors
- macOS and Windows implementations use the same JSON command protocol, so CLI and voice logic stay unchanged.

## Non-Goals
- Do not turn this into a full “voice operating system” rewrite.
- Do not move routing, interaction state, or speech presentation into OS-specific code.
- Do not hardcode “Siri Voice 1” or any single vendor voice as the only valid product target.
- Do not depend on GUI automation or Settings scraping at runtime.

## Architecture

### 1. Core Abstractions
- Keep `voice/tts_provider.py` as the public contract boundary, but expand it.
- Introduce a backend-neutral manager:
  - `voice/tts_manager.py`
- Introduce voice profiles and resolution policy:
  - `voice/voice_profiles.py`
- Introduce backend metadata types:
  - `voice/tts_models.py`

### 2. Public Data Model
- `SpeechUtterance`
  - `text`
  - `locale`
  - `voice_profile`
  - `voice_id`
  - `rate`
  - `pitch`
  - `volume`
  - `style_hint`
  - `interruptible`
- `TTSResult`
  - `ok`
  - `attempted`
  - `error_code`
  - `error_message`
  - `backend_name`
  - `voice_id`
- `VoiceDescriptor`
  - `id`
  - `display_name`
  - `locale`
  - `gender_hint`
  - `quality_hint`
  - `source`
  - `is_default`

### 3. Backend Contract
- `speak(utterance) -> TTSResult`
- `stop() -> bool`
- `list_voices(locale_hint=None) -> list[VoiceDescriptor]`
- `resolve_voice(profile, locale) -> VoiceDescriptor | None`
- `is_available() -> bool`
- `capabilities() -> BackendCapabilities`

## Product-Level Voice Profiles
- Never let CLI or speech presenter choose raw native voice names directly.
- Define profile resolution in `voice/voice_profiles.py`.

### Initial Profiles
- `ru_assistant_male`
- `ru_assistant_female`
- `ru_assistant_any`
- `en_assistant_male`
- `en_assistant_female`
- `en_assistant_any`

### Resolution Rules
- Prefer exact locale first.
- Prefer gender hint second.
- Prefer quality third.
- Prefer “assistant/system” voices over compact fallback voices when both exist.
- Phase 1 clarification:
  - product-level profile ids remain language-scoped;
  - exact locale ranking is still applied inside each backend adapter.
- Fall back in this order:
  - exact profile
  - same locale + any gender
  - same language + any gender
  - system default
  - null/no-op backend only as last resort

## Backend Strategy

### Option Chosen
- Use one shared Python-side manager plus OS-specific native host processes.
- Avoid direct CLI dependence on `say`, PowerShell, or raw OS shell syntax.

### Why Native Host Processes
- Easier to keep the cross-platform contract identical.
- Better support for structured `list_voices`, `speak`, and `stop`.
- Easier to test as standalone components.
- Cleaner path to Windows than embedding all OS logic in Python.

## JSON Host Protocol
- The Python process launches an OS-specific host binary/script and talks via `stdin/stdout`.

### Commands
- `ping`
- `list_voices`
- `resolve_voice`
- `speak`
- `stop`

### Example Request
```json
{
  "op": "speak",
  "text": "Привет, чем помочь?",
  "locale": "ru-RU",
  "voice_profile": "ru_assistant_male",
  "rate": 1.0,
  "pitch": 1.0,
  "volume": 1.0,
  "interruptible": true
}
```

### Example Response
```json
{
  "ok": true,
  "backend_name": "macos_native",
  "voice_id": "com.apple.voice.ru-RU.assistant.male"
}
```

## macOS Implementation Plan

### Backend
- Add:
  - `voice/backends/macos_native.py`
- This Python adapter should talk to:
  - `voice/native_hosts/macos_tts_host.swift`

### Why Swift Host
- Best access to native speech frameworks.
- Better control over voice enumeration than `say`.
- Better future support for richer voices and interruption.

### Required macOS Host Features
- Enumerate all voices available through the chosen native framework.
- Return stable identifiers and display names.
- Support explicit rate, pitch, and volume.
- Support synchronous `speak` result and explicit `stop`.
- Return structured errors instead of shell stderr text.

### macOS Fallback Policy
- Phase 1 fallback:
  - native host
  - existing `say` backend as legacy fallback
- Phase 2:
  - keep `say` only as emergency fallback, not as the primary path

## Windows Implementation Plan

### Backend
- Add:
  - `voice/backends/windows_native.py`
- This Python adapter should talk to:
  - `voice/native_hosts/windows_tts_host.cs`

### Why C#/.NET Host
- Best access to native Windows speech APIs.
- Easier packaging and process model than pywin32 glue.
- Strong fit for voice enumeration and interruption support.

### Windows Host Requirements
- Enumerate installed voices with locale and quality hints.
- Resolve voice profiles using the same JSON protocol as macOS.
- Support `speak` and `stop`.
- Return structured voice metadata so the Python manager remains identical.

## Backend Manager Plan

### New File
- `voice/tts_manager.py`

### Responsibilities
- Detect OS and choose backend.
- Resolve profile to voice.
- Apply fallback policy.
- Normalize backend errors into stable `TTSResult`.
- Expose a clean entry point used by CLI and dispatcher.

### CLI Impact
- `cli.py` should stop constructing platform behavior directly.
- CLI should only call:
  - `build_default_tts_provider()` or equivalent manager factory
  - `tts_manager.speak(utterance)`
  - `tts_manager.stop()`

## Debug and Operator Tooling
- Add CLI helpers:
  - `voice tts backend`
  - `voice tts voices`
  - `voice tts current`
  - `voice tts doctor`

### Purpose
- Show which backend is active.
- Show which voices are visible to that backend.
- Show how a profile was resolved.
- Make voice mismatch bugs debuggable without reading source.

## Testing Plan

### 1. Unit Tests
- profile resolution
- fallback policy
- voice registry sorting
- backend selection per OS

### 2. Contract Tests
- each backend adapter obeys the same `list_voices` / `speak` / `stop` behavior
- host protocol request/response validation

### 3. Integration Tests
- CLI with mock backend manager
- speech presenter + dispatcher + backend manager
- interruption behavior before follow-up capture

### 4. Manual Smoke
- `voice tts voices`
- `voice tts current`
- `speak on`
- `voice`
- interruption before follow-up
- Russian male profile on macOS
- Russian male profile on Windows

## Rollout Plan

### Phase 1. Prepare the Contract
- Expand `voice/tts_provider.py`.
- Add `voice/tts_models.py`.
- Add `voice/voice_profiles.py`.
- Add `voice/tts_manager.py`.
- Keep current `voice/tts_macos.py` wired as legacy backend.

### Phase 2. Add Native macOS Host
- Implement `voice/native_hosts/macos_tts_host.swift`.
- Add `voice/backends/macos_native.py`.
- Add `voice tts voices` and `voice tts backend`.
- Make macOS native backend opt-in behind a flag first.

### Phase 3. Promote macOS Native Backend
- Run manual QA.
- Compare against legacy `say`.
- Make native backend default on macOS.
- Keep legacy `say` as fallback only.

### Phase 4. Add Windows Host
- Implement `voice/native_hosts/windows_tts_host.cs`.
- Add `voice/backends/windows_native.py`.
- Reuse the same manager and profile resolution.
- Add Windows-specific smoke and packaging steps.

### Phase 5. Remove Platform Logic from Core
- Make CLI, dispatcher, and speech flow backend-agnostic.
- Ensure all platform branching is contained in manager/backend code.

## File-by-File Implementation Roadmap

### New Files
- `voice/tts_models.py`
- `voice/voice_profiles.py`
- `voice/tts_manager.py`
- `voice/backends/__init__.py`
- `voice/backends/macos_native.py`
- `voice/backends/windows_native.py`
- `voice/backends/null_tts.py`
- `voice/native_hosts/macos_tts_host.swift`
- `voice/native_hosts/windows_tts_host.cs`
- `tests/test_tts_manager.py`
- `tests/test_voice_profiles.py`
- `tests/test_tts_backend_contract.py`

### Existing Files To Update
- `voice/tts_provider.py`
- `voice/tts_macos.py`
- `cli.py`
- `voice/status.py`
- `voice/telemetry.py`
- `docs/manual_voice_verification.md`

## Risks
- macOS may expose different voices through different frameworks.
- Windows voice naming will not match macOS naming.
- Interruption semantics may differ by OS.
- Packaging native hosts will add release complexity.

## Risk Mitigation
- Use profile-based resolution instead of raw voice names.
- Keep host protocol identical across OSes.
- Keep legacy backend as fallback during rollout.
- Add explicit debug commands to inspect backend state.

## Definition of Done
- `ru_assistant_male` resolves predictably on macOS and Windows.
- CLI no longer depends on raw platform voice names.
- TTS can be listed, resolved, spoken, and stopped through one manager.
- Debug helpers show active backend and resolved native voice.
- macOS and Windows backends pass the same contract tests.
- Legacy fallback still works if native host is unavailable.

## Recommended First Slice
- Do not start with Windows code.
- First ship this minimal vertical slice:
  - expand TTS models
  - add profile resolution
  - add manager
  - keep current macOS backend behind manager
  - add `voice tts voices` and `voice tts current`
- After that, build the native macOS host.

## Practical Success Metric
- A user can say:
  - “I want a Russian male assistant voice”
- And JARVIS can answer deterministically:
  - which backend is active
  - which voice profile is requested
  - which native voice was selected
  - why that voice was selected
  - what fallback was used if the preferred voice is unavailable
