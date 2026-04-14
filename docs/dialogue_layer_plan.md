# Dialogue Layer Plan — JARVIS v1

---

## Goal

Make JARVIS feel like a calm, capable assistant rather than a command terminal. The current product works deterministically but communicates like a machine: terse error messages, blunt clarification prompts, no sense of conversational continuity across turns. The dialogue layer should close that gap with the minimum set of changes that produce a visible product improvement — without redesigning the runtime, relaxing confirmation boundaries, or introducing hidden behavior.

Specifically, the dialogue layer should:

- Make clarification turns feel like natural back-and-forth, not error messages.
- Let the user express follow-up replies without rephrasing from scratch.
- Recover gracefully when voice input is close to a known phrase but not reliable enough.
- Give the user a clear sense of what JARVIS heard, what it will do, and what it needs next.
- Stay strictly within supervised, deterministic execution — nothing happens without a command shape the runtime already understands.

---

## Current Gaps

**1. Clarification feels like a rejection.**
When bare `start work` is entered, the shell blocks with `What workspace should I prepare?`. This is correct but reads as an error prompt. There is no acknowledgement of what JARVIS understood, no warmth, no context. The user feels corrected rather than guided.

**2. No echo of what was heard.**
After voice input is recognized, JARVIS silently submits the transcript. If the transcript was wrong (e.g. "start fork" instead of "start work"), the user has no moment to catch it before execution begins.

**3. Clarification replies have no continuity.**
If a clarification is active (`awaiting_clarification`) and the user says something unexpected — not a workspace name, not a path — JARVIS has no clear path to re-ask the same question without restarting the flow. The current `apply_clarification` simply fails to patch and returns the unmodified command.

**4. Ambiguous voice input fails silently or hard.**
If the recognized phrase resembles a hero-flow trigger but has low confidence (e.g. "start fork" or "resume walk"), the router either routes it incorrectly or falls back to a generic `CLARIFICATION_REQUIRED`. There is no recovery path that says "I think I heard X — did you mean Y?".

**5. After a completed flow, the shell goes cold.**
When `start work` completes, the shell shows the success state and then waits silently. There is no follow-up prompt and no nudge toward the next natural action. The user has to remember what to say next.

**6. The mixed-interaction clarification message is mechanical.**
`"Do you want an answer first or should I start work on JARVIS?"` is functional but robotic. The turn type exists (`InteractionKind.CLARIFICATION`) but the message does not invite a natural reply.

**7. Re-asking after an unclear clarification reply is impossible without a restart.**
If the user answers a clarification with something that fails `apply_clarification` entirely (wrong format, unrelated word), there is no retry prompt. The runtime stays blocked in `awaiting_clarification` with no visible guidance about what to say.

---

## Minimal Dialogue Behaviors

These are the only dialogue behaviors JARVIS should add in v1:

1. **Heard echo on voice input.** Before submitting a voice transcript, show the recognized text briefly so the user can see what was heard. If it is obviously wrong, they can ignore it and try again; no confirmation gate is added.

2. **Acknowledgement line on clarification ask.** When a command blocks on clarification, prefix the clarification question with a short acknowledgement of what was understood: `"I heard 'start work' — what workspace should I prepare?"` instead of just `"What workspace should I prepare?"`.

3. **Re-ask on failed clarification reply.** If `apply_clarification` patches nothing and the runtime stays blocked, JARVIS should re-surface the same clarification question rather than staying silently blocked. One re-ask per active clarification; no infinite loop.

4. **Voice near-miss recovery prompt.** When the input interpreter signals moderate confidence (`0.55–0.69`) on a hero-flow normalization, surface a short `"Did you mean: <canonical phrase>?"` prompt before routing. The user replies yes/no; only a yes routes to execution.

5. **Completion nudge for hero flow.** After `start work` or `resume work` completes successfully, add one short follow-up line in the transcript: `"You're in <workspace>. Say 'resume work' anytime to pick this back up."` — informational only, no action, no prompt.

6. **Honest re-ask on unexpected clarification input.** When a clarification reply is not parseable by `apply_clarification`, show a short retry message: `"I didn't catch that — <original clarification question>"`. One retry per blocked turn. If the second reply also fails, the flow surfaces a normal failure.

---

## Turn Types

JARVIS v1 should explicitly recognize and handle these turn types:

| Turn Type | Description | Handled by |
|---|---|---|
| `fresh_command` | A new, complete, routable command. | Existing router → runtime. |
| `fresh_question` | A new question routed to QA mode. | Existing router → QA. |
| `clarification_reply` | A direct reply to an active `awaiting_clarification` prompt. | Existing `apply_clarification`. |
| `confirmation_reply` | A yes/no/cancel reply to an active `awaiting_confirmation` prompt. | Existing confirmation handler. |
| `routing_choice` | A reply to a `mixed_interaction` clarification ("answer first" / "execute"). | Existing `resolve_interaction_clarification_choice`. |
| `voice_near_miss` | A voice transcript the interpreter flagged at moderate confidence on a known intent. | **New**: near-miss recovery prompt before routing. |
| `failed_clarification_retry` | A reply that `apply_clarification` could not patch. | **New**: re-ask the same question once. |
| `answer_follow_up` | A short follow-up on the last QA answer (already handled via `_ANSWER_FOLLOW_UP_SURFACES`). | Existing router (`recent_answer_follow_up`). |

No new turn types should be invented for v1 beyond `voice_near_miss` and `failed_clarification_retry`.

---

## State And Continuity

### Short-lived state to add

JARVIS needs only two small pieces of short-lived conversational state beyond what already exists:

**1. `pending_clarification_retry_count: int`**
Stored on the active command shape or in the runtime manager alongside the existing `current_state`. Initialized to `0` when a clarification is issued. Incremented when `apply_clarification` patches nothing. When it reaches `1`, the shell re-asks the same question. When it reaches `2`, the flow surfaces a normal failure. Cleared when the command is resolved, cancelled, or reset.

**2. `pending_near_miss: NearMissState | None`**
A lightweight dataclass holding `{canonical_phrase: str, confidence: float, original_raw: str}`. Set by the interaction manager when the interpreter returns moderate-confidence output on a hero-flow intent. Cleared immediately after the user replies yes/no. If yes: the `canonical_phrase` is routed as a fresh command. If no: the original input is discarded and the composer returns to idle.

### What must stay out of scope

- No cross-session memory. Both state fields are in-process and reset on session reset.
- No conversation history model. JARVIS does not summarize or reference prior turns beyond what the existing `SessionContext.get_recent_answer_context()` already does.
- No background inference about user intent between turns.
- No multi-turn command assembly (i.e., collecting multiple pieces of info across separate turns to build one command). Only one field is collected at a time via the existing clarification path.

---

## Clarification Behavior

### Current behavior
Clarification messages come from `clarification_handler.py::build_clarification`. They are correct but bare: `"What workspace should I prepare?"`.

### Proposed change
Prefix the clarification message with a short acknowledgement of the recognized intent when the command is a hero-flow command:

- For `prepare_workspace` (bare `start work`): `"I heard 'start work' — what workspace should I prepare?"`
- For `run_protocol` with ambiguous protocol: `"I heard 'run' — which protocol should I run?"`
- For all other intents: existing message unchanged (narrow the scope to hero flow only in v1).

The prefix is generated in `build_clarification` using the command's `raw_input` field and intent. It is a display-only label — it does not change the clarification code, options, or downstream `apply_clarification` behavior.

### Re-ask on failed reply
When `apply_clarification` returns an unpatched command (nothing patched, confidence unchanged), the runtime manager should check `pending_clarification_retry_count`. If `0`, increment to `1` and re-surface the same `ClarificationRequest` message. If already `1`, surface a short failure: `"I couldn't understand your reply. The action has been cancelled — try again."` and cancel the command.

The re-ask message should be the same clarification message, prefixed with: `"I didn't catch that — "`.

---

## Misheard Voice Recovery

### Problem
When the voice recognizer returns a transcript that is close to a hero-flow phrase but wrong — `"start fork"`, `"resume walk"`, `"start work on jar fish"` — one of two bad things happens:
1. The wrong text routes and fails unexpectedly (e.g. `"start fork"` routes as `prepare_workspace` with target `"fork"`, which does not exist).
2. The interpreter rewrites it with high confidence and silently executes the wrong thing.

### Proposed recovery path

The interaction manager already has interpreter confidence available. Add one confidence band:

- **Confidence ≥ 0.70**: existing behavior — rewrite and route (already implemented).
- **Confidence 0.55–0.69** on a known hero-flow intent: set `pending_near_miss`, surface a short disambiguation prompt to the user, do not route yet.
- **Confidence < 0.55** or `routing_hint = "unclear"`: existing fallback — original text passes through unchanged.

The disambiguation prompt is rendered as a transcript prompt card (using the existing `PendingPromptViewModel` surface) with message:

`"Did you mean: '<canonical_phrase>'?"`

with two explicit reply options: `["Yes", "No"]`.

On `"Yes"`: route `canonical_phrase` as a fresh command through the normal submission path.
On `"No"`: clear `pending_near_miss`, return composer to idle state, display: `"Okay — say it again whenever you're ready."`.

This reuses the existing prompt-reply chip path (`submit_prompt_action` → `submit_text`) without introducing a new execution path.

### What this does NOT do
- It does not guess which word was misheard.
- It does not offer multiple alternatives (one canonical phrase only, or nothing).
- It does not activate for typed input — only for voice-originated turns (detected by the existing voice capture path in the controller).

---

## Shell Implications

**Heard echo in composer.**
After voice capture completes and the transcript is recognized, display the recognized text briefly in the composer input field before submission (it already passes through `submit_text` — show it as read-only text for ~1.5 seconds or until submission). This is a cosmetic change in `composer.py` or the controller's `start_voice_capture` path.

**Acknowledgement prefix in transcript.**
The acknowledgement prefix (`"I heard 'start work' — ..."`) appears as part of the clarification prompt card in the transcript, not as a separate entry. The existing `PendingPromptViewModel.message` field carries it. No new card type needed.

**Re-ask message in transcript.**
The re-ask (`"I didn't catch that — ..."`) appears as a new `PROMPT` transcript entry using the existing transcript surface. No new entry kind.

**Near-miss prompt as prompt card.**
The `"Did you mean: '...'"` prompt is a standard `PendingPromptViewModel` with two reply chips: `Yes` and `No`. It uses the existing prompt card rendering path. The controller handles the yes/no reply via `submit_prompt_action` as today.

**Completion nudge as info entry.**
The post-completion nudge (`"You're in <workspace>. Say 'resume work'..."`) is a plain `INFO` transcript entry appended after the `COMPLETION` entry by the visibility mapper. No interaction path, no prompt chips. It is display-only.

**Composer idle copy.**
After a successful `start work` or `resume work` flow, the composer's idle voice-ready copy should update from the generic hero-flow prompt to a short contextual one: `"<workspace> is open. Say 'resume work' anytime."`. This is a one-line change in the controller's `_reset_composer_voice_state` call after completion.

---

## Files To Change

| File | Reason |
|---|---|
| `clarification/clarification_handler.py` | Add acknowledgement prefix to hero-flow clarification messages; add re-ask message generation for `failed_clarification_retry` case. |
| `interaction/interaction_manager.py` | Add near-miss detection (confidence band 0.55–0.69 on hero-flow intents); set/clear `pending_near_miss` state; route yes/no near-miss replies; increment and check `pending_clarification_retry_count` on unpatched clarification replies. |
| `runtime/runtime_manager.py` | Track `pending_clarification_retry_count` on the active command; expose reset/increment interface. |
| `ui/visibility_mapper.py` | Emit completion nudge info entry after hero-flow completion; pass near-miss prompt payload as `PendingPromptViewModel`; pass re-ask message as prompt entry. |
| `desktop/shell/controllers/conversation_controller.py` | Show recognized voice transcript in composer briefly before submission; update idle copy after hero-flow completion; handle near-miss yes/no as prompt action replies. |
| `desktop/shell/widgets/composer.py` | Add transient "heard" display state between voice capture completion and submission. |
| `tests/test_interaction_router.py` | Add near-miss routing tests for the 0.55–0.69 confidence band. |
| `tests/test_protocol_runtime.py` | Add retry-count increment and re-ask tests. |
| `tests_desktop/test_conversation_controller.py` | Add heard-echo display and near-miss prompt chip tests. |
| `tests_desktop/test_desktop_presenters.py` | Add completion nudge and re-ask entry presenter tests. |

---

## Out Of Scope

- Multi-turn command assembly across more than one clarification field at a time.
- Any change to the deterministic command/question routing boundary.
- Background voice listening, wake words, or continuous capture.
- Cross-session memory, conversation summaries, or persistent turn history.
- New protocol types or runtime behaviors triggered by dialogue state.
- Proactive JARVIS-initiated conversation (JARVIS does not speak unless responding to input).
- Natural language generation for answers or summaries (QA mode is unchanged).
- Any relaxation of confirmation boundaries — explicit confirmation still required for all currently-confirmed actions.
- Dialogue for any flow other than `start work` / `resume work` in v1.
- Streaming or partial-output rendering.
- Multiple near-miss candidates — one canonical phrase or nothing.

---

## Acceptance Criteria

1. Saying `"start work"` without a workspace shows: `"I heard 'start work' — what workspace should I prepare?"` — not the bare existing message.

2. Replying with an unparseable string to a clarification prompt (e.g. `"umm"`) triggers one re-ask: `"I didn't catch that — what workspace should I prepare?"` — not silent blocking.

3. A second unparseable reply cancels the flow with a clear message: `"I couldn't understand your reply. The action has been cancelled — try again."` — no silent hang.

4. A voice transcript with interpreter confidence 0.55–0.69 on `prepare_workspace` or `run_protocol: resume_work` shows a `"Did you mean: '<phrase>'"` prompt card with Yes/No chips — the command does not execute yet.

5. Tapping `"Yes"` on the near-miss card routes the canonical phrase and executes normally.

6. Tapping `"No"` clears the prompt and returns the composer to idle with: `"Okay — say it again whenever you're ready."` — nothing executes.

7. After `start work on <workspace>` completes, the transcript shows one extra info line: `"You're in <workspace>. Say 'resume work' anytime to pick this back up."` — no prompt chips, no action.

8. After `resume work` completes, the composer idle copy updates to: `"<workspace> is open. Say 'resume work' anytime."`.

9. Recognized voice text is briefly visible in the composer input area before submission — the user can see what JARVIS heard.

10. All existing routing, confirmation, and clarification behaviors for non-hero-flow commands are unchanged — verified by running the full existing test suite with `JARVIS_INTERPRETER_DISABLED=1`.

11. `pending_near_miss` and `pending_clarification_retry_count` are reset on session reset and on successful command completion.

12. Typed input never triggers the near-miss prompt — only voice-originated turns.
