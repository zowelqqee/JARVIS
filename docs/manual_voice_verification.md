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
- Optional earcons can be enabled with `JARVIS_VOICE_EARCONS=1`.
- Interruptible local TTS backends may now stop in-flight speech before a new listening phase begins.
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
- To verify optional earcons, run: `JARVIS_VOICE_EARCONS=1 python3 cli.py`
- Optional offline rollout helpers:
  - `voice mode` inside CLI to inspect whether bounded advanced follow-up mode is currently enabled
  - `voice last` inside CLI to inspect the most recent voice dispatch, follow-up control, or speech interruption handled in this session
  - `voice status` inside CLI to inspect current session voice state, `speak on/off`, bounded-loop counters, and speech interruption counts
  - `voice readiness` inside CLI or `python3 -m voice.readiness`
  - `voice readiness write` inside CLI to persist the final readiness artifact when unblocked
  - `voice gate` inside CLI or `python3 -m voice.gate`
  - shell wrapper: `scripts/run_voice_readiness_gate.sh`
- For offline QA artifacts outside the default `tmp/qa` location, both Python helpers also accept `--artifact-path` and `--telemetry-artifact-path`.
- Optional session metrics helper inside CLI: `voice telemetry`
- `voice telemetry` now also shows `follow-up relisten count` and `follow-up dismiss count` for `listen again` / `stop speaking` style control replies.
- `voice telemetry` also shows `max follow-up chain length` and `follow-up limit hit count` for the bounded multi-turn loop.
- `voice telemetry` now also shows `speech interrupt count` for any local TTS interruption in the session and `speech interrupt for capture count` for the narrower case where the next listening phase barges in on active speech.
- `voice telemetry` also separates `speech interrupt for response count`, so interrupted latency fillers are visible apart from capture-side barging.
- If a new capture cannot interrupt active speech, CLI should print `voice: Cannot interrupt active speech for capture.`, `voice telemetry` should increment `speech interrupt conflict count`, and `voice last` should show an `interruption_conflict` event.
- If a latency filler is interrupted because the final spoken answer is ready, `voice last` should show an `interruption` event with reason `final_answer_start`.
- After `voice telemetry write`, the saved telemetry artifact is also surfaced by `voice readiness` and `voice gate`, including `speech interrupt conflict count` for failed barge-in attempts during live QA.
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
- If the first initial capture looks like locale-noise fallback gibberish, CLI may ask once more with `voice: didn't catch that clearly. speak again.` and retry the initial capture with the alternate locale order before routing.
- If `JARVIS_VOICE_CONTINUOUS_MODE=1` and a voice turn ends in blocking clarification or confirmation, CLI should print `voice: follow-up... speak now.` and may continue for up to two extra follow-up replies in the same bounded loop.
- If `JARVIS_VOICE_CONTINUOUS_MODE=1`, `speak on` is enabled, and a question answer is short enough, CLI may keep the bounded loop alive for one more immediate answer follow-up.
- If the bounded loop still wants another follow-up after those two extra turns, CLI should stop cleanly with `voice: follow-up limit reached.`
- With `JARVIS_VOICE_EARCONS=1`, that limit-reached close may also emit a short error cue.
- With `speak on`, a slow question or answer-follow-up may briefly emit `voice: thinking...` plus a short spoken filler such as `One moment.` or `Одну секунду.` before the final answer.
- If that short filler is still speaking when the next listening phase starts, the local TTS backend may stop it instead of waiting for the whole utterance to finish.
- With `JARVIS_VOICE_EARCONS=1`, CLI may emit short non-verbal cues for listening start, listening stop, error, and speech start.
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
- If the spoken answer is long, TTS may shorten it and suggest a follow-up phrase like `подробнее` or `say more` instead of reading the whole answer aloud.
- For unsafe or refusal question cases, spoken output should stay short; if the refusal includes immediate self-harm safety guidance, it may mention `988` briefly instead of reading a long policy-style answer aloud.

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
- For ambiguous target prompts, spoken clarification should avoid reading full paths aloud and should stay short enough to answer by voice.
- If clarification or failure text accidentally contains debug tails like `Debug:` or `request_id=...`, spoken output should drop them before speaking.
- For short English failures with a known `next_step_hint`, spoken output may include that hint as a second short sentence instead of dropping it.

### 6) Russian clarification follow-up by voice
- Precondition: run CLI with `JARVIS_VOICE_CONTINUOUS_MODE=1`.
- Precondition: trigger the mixed interaction scenario above from one `voice` command.
- Shell input: `voice`
- Spoken input sequence:
  - first turn: `Что ты умеешь и открой сафари`
  - follow-up turn after `voice: follow-up... speak now.`: `ответить`
- Expected result: question branch executes and the pending mixed clarification clears.
- English follow-up variants like `just answer`, `go ahead`, `do it`, or `open it` should also resolve naturally inside the same mixed clarification window.
- Repeat with:
  - first turn: `Что ты умеешь и открой сафари`
  - follow-up turn: `выполнить`
- Expected result: command branch executes and the pending mixed clarification clears.
- If the follow-up reply is missed once, CLI should give one more short prompt like `voice: didn't catch that. speak again.`
- With `JARVIS_VOICE_EARCONS=1`, that missed follow-up retry should also emit a short error cue.
- If the follow-up is still missed after that retry, the window should close cleanly instead of crashing the voice shell.

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
- English voice variants like `tell me more`, `which source`, `where is that from`, `why is that`, and `say that again` should normalize to the same follow-up surface.
- For source-oriented follow-ups, spoken output should shorten absolute file or folder paths to short names instead of reading full `/Users/...` or `/tmp/...` paths aloud.
- In the Russian voice path, short source answers should also use a Russian spoken cue such as `Источник:` or `Источники:` instead of leaving English prefixes like `Relevant sources:`.
- The same source-aware rendering should work when the upstream answer text itself already uses Russian prefixes like `Источник:` or `Источники:`.
- It should also work for dash-style prefixes like `Sources -`, `Источник -`, or `Источники —`, not only for the colon form.
- If a source-oriented spoken answer contains a long list of files or hosts, TTS should shorten it to the first two short labels plus a brief tail like `and 2 more` or `и ещё 2 источника`.
- If a source list mixes file labels and website hosts, spoken output should still keep clean short labels like `clarification_rules.md` and `docs.python.org` and should not leave a raw `and` attached to the final label.
- For a short mixed pair like `file + host`, spoken output may also use a natural conjunction such as `clarification_rules.md and docs.python.org` or `clarification_rules.md и docs.python.org`.
- If the underlying answer text already includes a short source cue after the first sentence, spoken output may keep both pieces: first the answer summary, then a second short phrase like `Sources: ...` or `Источники: ...`.
- Even if that source cue is attached with punctuation like `; Relevant sources: ...`, spoken output should still separate the answer summary from the source phrase cleanly.
- The same cleanup should hold when the source cue appears after parentheses or dash-like punctuation, for example `(Relevant sources: ...)` or `— Relevant sources: ...`.
- The same cleanup should also hold when the source cue is wrapped in quotes or guillemets, so spoken output does not keep stray quote characters around the summary or source labels.
- If such an answer also carries a warning, spoken output should keep a natural order: answer first, then source cue, then warning.
- In those heavier long-answer cases, the closing follow-up prompt may also switch to a shorter form like `Say "say more" for details.` or `Скажи подробнее, если нужны детали.`
- In the same heavier cases, the warning itself may also shorten to a tighter spoken form like `Warning: May be out of date.` or `Предупреждение: Ответ может быть неактуален.`
- Provenance-style warnings about local sources or model knowledge may also switch to a lighter spoken prefix like `Note:` or `Примечание:` in those heavier cases.
- If the spoken answer references repo-relative paths like `docs/clarification_rules.md` or contains light markdown formatting, TTS should still say a short clean phrase such as `clarification_rules.md`, not read slashes, backticks, or formatting markers aloud.
- If the spoken answer includes a website URL, TTS should prefer a short host like `docs.python.org` instead of reading `https://...` literally.
- If QA/debug noise leaks into the answer text, spoken output should drop tails like `Debug:`, `Traceback`, `request_id=...`, or `latency_ms=...` instead of reading them aloud.
- If voice/TTS is running with an explicit locale hint, utterance locale selection should keep that explicit locale even when the spoken message itself is mixed-language or Cyrillic-heavy.
- For longer spoken answers, TTS may end with a short prompt like `Say "say more" if you want more detail.` or `Скажи подробнее, если хочешь больше деталей.`
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
- Natural relisten variants like `послушай снова` or English `try again` should behave the same way inside the current follow-up window.
- With `JARVIS_VOICE_EARCONS=1`, this intentional relisten control should not sound like an error.
- If the immediate follow-up reply is missed without any control phrase, CLI should retry once with `voice: didn't catch that. speak again.`
- If that second follow-up capture is also empty, CLI should print `voice: no follow-up reply detected.` and close the current follow-up window.
- With `JARVIS_VOICE_EARCONS=1`, each missed follow-up attempt may also emit a short error cue before the next retry or close.
- If you want to dismiss the immediate follow-up window, say `замолчи`.
- Expected recognized text: `stop speaking`
- Expected result: the current follow-up window closes without routing `stop speaking` as a command reply.
- Natural dismiss variants like `прекрати говорить` or English `stop talking` should also close the current follow-up window.
- With `JARVIS_VOICE_EARCONS=1`, this intentional dismiss should also stay quiet instead of emitting an error cue.
- For a short-answer follow-up window, `стоп` / `отмена` and natural dismiss replies like `не сейчас`, `not now`, or `no thanks` may also close the offered extra follow-up instead of routing a command-path cancel.

### 8) Confirmation approve by voice
- Precondition: run CLI with `JARVIS_VOICE_CONTINUOUS_MODE=1`.
- Precondition: use a voice command that reaches `awaiting_confirmation`, for example `Джарвис, закрой телеграм`.
- Shell input: `voice`
- Spoken input sequence:
  - first turn: close command
  - follow-up turn after `voice: follow-up... speak now.`: `да`
- Expected spoken confirmation prompt: for destructive close actions, JARVIS should use a short yes-or-no prompt rather than a dry runtime log.
- Expected recognized text: canonical approval reply such as `yes`
- Expected result: blocked command resumes and executes from the confirmation boundary.
- Natural English confirmations like `sure`, `do it`, or `sounds good` should also approve the blocked command.

### 9) Confirmation deny by voice
- Precondition: run CLI with `JARVIS_VOICE_CONTINUOUS_MODE=1`.
- Precondition: use a voice command that reaches `awaiting_confirmation`.
- Shell input: `voice`
- Spoken input sequence:
  - first turn: close command
  - follow-up turn: `нет` or `отмена`
- Expected recognized text: canonical denial reply such as `no` or `cancel`
- Expected result: runtime becomes `cancelled`; blocked step does not execute.
- Natural English denials like `not now` or `no thanks` should also cancel the blocked command.

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
