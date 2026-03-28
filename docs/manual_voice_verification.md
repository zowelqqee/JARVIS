# JARVIS Manual Voice Verification

## Purpose
- Provide one focused manual checklist for the current one-shot CLI voice path.
- Keep voice verification separate from the broader shell and QA operator checklists.
- Make the current supported surface and current limitations explicit before live microphone testing.

## Current Scope
- Voice entry point is `voice` or `/voice` inside `python3 cli.py`.
- Voice capture is macOS-only and depends on the local helper in `input/macos_voice_capture.m`.
- The current mode is single-turn capture, not a continuous conversation loop.
- Spoken output is optional and controlled by `speak on` / `speak off`.
- Russian and English are both expected to work for the MVP voice surface.

## Current Limitations
- No managed continuous listening session yet.
- No automatic return to listening after a spoken reply.
- No live microphone smoke is implied by unit tests; this checklist must be run manually.
- Spoken output is summary-oriented and may differ from terminal output by design.

## Setup
- Run: `python3 cli.py`
- Confirm the shell banner includes `voice` and `speak on`.
- On first use, allow macOS `Microphone` and `Speech Recognition` permissions if prompted.
- If capture fails immediately, verify macOS Settings -> Privacy & Security -> Microphone / Speech Recognition.
- If spoken output is needed, run `speak on` first.

## Expected General Behavior
- `voice` prints `voice: listening... speak now.`
- After capture, CLI prints one normalized `recognized: "..."` line.
- The normalized line may be English even for Russian fixed phrases and follow-ups.
- Runtime behavior must stay deterministic after normalization.
- Spoken output should be shorter and friendlier than terminal output.

## Checklist

### 1) Russian open-app command
- Shell input: `voice`
- Spoken input: `Джарвис, открой телеграм`
- Expected recognized text: `open telegram`
- Expected result: command path executes or returns explicit `APP_UNAVAILABLE`; no question fallback.

### 2) English open-app command
- Shell input: `voice`
- Spoken input: `open Safari`
- Expected recognized text: `open Safari`
- Expected result: command path executes or returns explicit app availability failure.

### 3) Russian open-domain question
- Shell input: `voice`
- Spoken input: `Кто президент Франции`
- Expected recognized text: `Кто президент Франции`
- Expected result: question path, no command execution.
- Important: answer freshness depends on the configured QA backend and environment.

### 4) Fixed Russian capabilities prompt
- Shell input: `voice`
- Spoken input: `Что ты умеешь что ты умеешь`
- Expected recognized text: `what can you do`
- Expected result: grounded question answer, no clarification loop.

### 5) Russian mixed question + command
- Shell input: `voice`
- Spoken input: `Что ты умеешь и открой сафари`
- Expected recognized text: `Что ты умеешь and open safari`
- Expected result: routing clarification only; no silent answer-plus-execute behavior.

### 6) Russian clarification follow-up by voice
- Precondition: trigger the mixed interaction scenario above.
- Shell input: `voice`
- Spoken input: `ответить`
- Expected result: question branch executes and the pending mixed clarification clears.
- Repeat:
  - Shell input: `voice`
  - Spoken input: `выполнить`
  - Expected result: command branch executes and the pending mixed clarification clears.

### 7) Confirmation approve by voice
- Precondition: reach `awaiting_confirmation`, for example with `close Telegram` or a voice close command.
- Shell input: `voice`
- Spoken input: `да`
- Expected recognized text: canonical approval reply such as `yes`
- Expected result: blocked command resumes and executes from the confirmation boundary.

### 8) Confirmation deny by voice
- Precondition: reach `awaiting_confirmation`.
- Shell input: `voice`
- Spoken input: `нет` or `отмена`
- Expected recognized text: canonical denial reply such as `no` or `cancel`
- Expected result: runtime becomes `cancelled`; blocked step does not execute.

### 9) Repeated follow-up noise
- Precondition: reach `awaiting_confirmation`.
- Shell input: `voice`
- Spoken input: `да да`
- Expected recognized text: canonical single approval reply
- Expected result: same as one clean approval reply.

### 10) Russian spoken output
- Shell input:
  - `speak on`
  - `voice`
- Spoken input: `Джарвис, открой телеграм`
- Expected result:
  - TTS attempts a Russian spoken confirmation when the voice input was Russian.
  - Spoken output should not read raw terminal traces like `Completed open_app with 1 step(s).`

### 11) Voice failure diagnostics
- Shell input: `voice`
- Induce one failure path if possible:
  - deny permission;
  - mute/incorrect input device;
  - unsupported environment.
- Expected result: concise `voice: ...` message plus `hint: ...` when available, without generic misleading success text.

## Regression Notes
- English text-first behavior must remain unchanged when voice is not used.
- `speak off` must suppress TTS attempts but keep normal terminal output.
- Russian fixed prompts may normalize to English canonical text; this is expected for the current MVP.
- Live microphone behavior should be recorded separately from unit-test results.
