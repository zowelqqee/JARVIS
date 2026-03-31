# JARVIS Manual Voice Verification

## Purpose
- Provide one focused manual checklist for the current one-shot CLI voice path.
- Keep voice verification separate from the broader shell and QA operator checklists.
- Make the current supported surface and current limitations explicit before live microphone testing.

## Current Scope
- Voice entry point is `voice` or `/voice` inside `python3 cli.py`.
- Voice capture is macOS-only and depends on the local helper in `input/macos_voice_capture.m`.
- The current mode is still not a continuous conversation loop.
- CLI may open a bounded sequence of immediate blocking follow-up replies only when `JARVIS_VOICE_CONTINUOUS_MODE=1`.
- Spoken output is optional and controlled by `speak on` / `speak off`.
- Russian and English are both expected to work for the MVP voice surface.

## Current Limitations
- No managed continuous listening session yet.
- Advanced voice follow-up mode is disabled by default until manual QA is complete.
- No automatic unbounded multi-turn loop even when the flag is enabled.
- When `JARVIS_VOICE_CONTINUOUS_MODE=1`, CLI may auto-capture at most two extra follow-up replies after the initial voice turn.
- Short-answer follow-up opens only when `JARVIS_VOICE_CONTINUOUS_MODE=1` and spoken output is enabled via `speak on`.
- No live microphone smoke is implied by unit tests; this checklist must be run manually.
- Spoken output is summary-oriented and may differ from terminal output by design.

## Setup
- Run: `python3 cli.py`
- To verify automatic blocking follow-up, run: `JARVIS_VOICE_CONTINUOUS_MODE=1 python3 cli.py`
- Optional offline rollout helpers:
  - `voice mode` inside CLI to inspect whether bounded advanced follow-up mode is currently enabled
  - `voice last` inside CLI to inspect the most recent voice dispatch or follow-up control handled in this session
  - `voice status` inside CLI to inspect current session voice state, `speak on/off`, and in-memory bounded-loop counters
  - `voice readiness` inside CLI or `python3 -m voice.readiness`
  - `voice readiness write` inside CLI to persist the final readiness artifact when unblocked
  - `voice gate` inside CLI or `python3 -m voice.gate`
  - shell wrapper: `scripts/run_voice_readiness_gate.sh`
- For offline QA artifacts outside the default `tmp/qa` location, both Python helpers also accept `--artifact-path` and `--telemetry-artifact-path`.
- Optional session metrics helper inside CLI: `voice telemetry`
- `voice telemetry` now also shows `follow-up relisten count` and `follow-up dismiss count` for `listen again` / `stop speaking` style control replies.
- `voice telemetry` also shows `max follow-up chain length` and `follow-up limit hit count` for the bounded multi-turn loop.
- To inspect the saved telemetry artifact later, run: `voice telemetry artifact` inside CLI or `python3 -m voice.telemetry`
- To persist the current session snapshot to `tmp/qa`, run: `voice telemetry write`
- After saving telemetry, `voice readiness` and `voice gate` will also surface the saved follow-up relisten/dismiss counts as rollout evidence.
- Confirm the shell banner includes `voice` and `speak on`.
- On first use, allow macOS `Microphone` and `Speech Recognition` permissions if prompted.
- If capture fails immediately, verify macOS Settings -> Privacy & Security -> Microphone / Speech Recognition.
- If spoken output is needed, run `speak on` first.

## Expected General Behavior
- `voice` prints `voice: listening... speak now.`
- After capture, CLI prints one normalized `recognized: "..."` line.
- If `JARVIS_VOICE_CONTINUOUS_MODE=1` and a voice turn ends in blocking clarification or confirmation, CLI should print `voice: follow-up... speak now.` and may continue for up to two extra follow-up replies in the same bounded loop.
- If `JARVIS_VOICE_CONTINUOUS_MODE=1`, `speak on` is enabled, and a question answer is short enough, CLI may keep the bounded loop alive for one more immediate answer follow-up.
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
- Precondition: run CLI with `JARVIS_VOICE_CONTINUOUS_MODE=1`.
- Precondition: trigger the mixed interaction scenario above from one `voice` command.
- Shell input: `voice`
- Spoken input sequence:
  - first turn: `Что ты умеешь и открой сафари`
  - follow-up turn after `voice: follow-up... speak now.`: `ответить`
- Expected result: question branch executes and the pending mixed clarification clears.
- Repeat with:
  - first turn: `Что ты умеешь и открой сафари`
  - follow-up turn: `выполнить`
- Expected result: command branch executes and the pending mixed clarification clears.
- If the follow-up window is missed, restart with a fresh `voice` command.

### 7) Russian answer follow-up by voice
- Precondition: ask any grounded question that leaves recent answer context, for example `Что ты умеешь`.
- Precondition: if you want the immediate auto-follow-up window, run CLI with `JARVIS_VOICE_CONTINUOUS_MODE=1` and `speak on`.
- Shell input sequence:
  - first `voice` turn: ask the grounded question
  - if the immediate follow-up window opens: say `скажи подробнее`
  - otherwise start a second fresh `voice` turn and say `скажи подробнее`
- Expected recognized text for the follow-up reply: `Explain more`
- Expected result: answer-follow-up path reuses recent answer context and returns a more detailed grounded answer.
- If that follow-up still ends in a short spoken answer, CLI may open one more immediate follow-up window before the bounded loop stops.
- Repeat with:
  - follow-up reply or second fresh `voice` turn: `какой источник`
- Expected recognized text: `Which source?`
- Expected result: answer-follow-up path points to the recent grounded sources instead of falling back to a generic question.
- Repeat with:
  - follow-up reply or second fresh `voice` turn: `где это написано`
- Expected recognized text: `Where is that written`
- Expected result: answer-follow-up path points back to the recent grounded sources in a voice-friendly form.
- Repeat with:
  - follow-up reply or second fresh `voice` turn: `почему`
- Expected recognized text: `Why is that`
- Expected result: answer-follow-up path explains why the previous grounded answer had that boundary or behavior.
- Repeat with:
  - follow-up reply or second fresh `voice` turn: `повтори`
- Expected recognized text: `Repeat that`
- Expected result: answer-follow-up path repeats the previous answer text instead of falling back to a new generic question or command.
- If the follow-up capture was noisy, say `слушай снова`.
- Expected recognized text: `listen again`
- Expected result: the current follow-up window reopens once and waits for the real reply instead of routing `listen again` as a command.
- If you want to dismiss the immediate follow-up window, say `замолчи`.
- Expected recognized text: `stop speaking`
- Expected result: the current follow-up window closes without routing `stop speaking` as a command reply.
- For a short-answer follow-up window, `стоп` / `отмена` may also close the offered extra follow-up instead of routing a command-path cancel.

### 8) Confirmation approve by voice
- Precondition: run CLI with `JARVIS_VOICE_CONTINUOUS_MODE=1`.
- Precondition: use a voice command that reaches `awaiting_confirmation`, for example `Джарвис, закрой телеграм`.
- Shell input: `voice`
- Spoken input sequence:
  - first turn: close command
  - follow-up turn after `voice: follow-up... speak now.`: `да`
- Expected recognized text: canonical approval reply such as `yes`
- Expected result: blocked command resumes and executes from the confirmation boundary.

### 9) Confirmation deny by voice
- Precondition: run CLI with `JARVIS_VOICE_CONTINUOUS_MODE=1`.
- Precondition: use a voice command that reaches `awaiting_confirmation`.
- Shell input: `voice`
- Spoken input sequence:
  - first turn: close command
  - follow-up turn: `нет` or `отмена`
- Expected recognized text: canonical denial reply such as `no` or `cancel`
- Expected result: runtime becomes `cancelled`; blocked step does not execute.

### 10) Repeated follow-up noise
- Precondition: run CLI with `JARVIS_VOICE_CONTINUOUS_MODE=1`.
- Precondition: use a voice command that reaches `awaiting_confirmation`.
- Shell input: `voice`
- Spoken input sequence:
  - first turn: close command
  - follow-up turn: `да да`
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
