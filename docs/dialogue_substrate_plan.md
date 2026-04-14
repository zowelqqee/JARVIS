# Dialogue Substrate Plan — JARVIS v1

---

## Goal

Make every interaction with JARVIS feel coherent across turns, not just correct within a single turn. The current product handles individual commands and questions well but treats each input as a clean-slate event: there is no recovery from a failed clarification, no correction path, no natural way to switch between asking and commanding in adjacent turns, and no heard-echo on voice input.

The dialogue substrate should produce three user-visible improvements across the whole product:

1. **Repair**: JARVIS can recover from misunderstanding, wrong answers to clarification, and near-miss voice input without requiring a full restart.
2. **Continuity**: short contextual signals carry across adjacent turns — the last completed command, the last answer topic, the last clarification question — so follow-up inputs feel natural rather than detached.
3. **Honesty**: the shell surfaces what JARVIS heard, what state it is in, and what it needs next, in plain language, at every blocked or ambiguous moment.

Nothing in this plan relaxes confirmation boundaries, adds hidden behavior, or changes the deterministic runtime.

---

## Current Interaction Gaps

**1. Clarification failure is a silent hang.**
When `apply_clarification` in `clarification_handler.py` cannot patch the active command (e.g. the user says "umm" or gives an off-topic reply), the runtime stays in `awaiting_clarification` with the same `blocked_reason` message and no indication that the reply failed. There is no re-ask, no retry count, no failure path.

**2. No correction turn.**
After a `MULTIPLE_MATCHES` clarification or any ambiguous resolution, if the user says `"no, the other one"`, `"not that"`, or `"actually X"`, the input is routed as a fresh command (via the `_should_restart_as_fresh_command` check in `runtime_manager.py`), which fails. There is no structured correction path that says: "the user is rejecting the current resolution, let me re-apply clarification with the corrected input."

**3. No voice near-miss recovery.**
The interpreter fires at confidence ≥ 0.70 and rewrites silently. Below 0.70 the original text passes through unchanged to the deterministic router, which may route it wrong or fail with a generic error. There is no middle path that says "I think I heard X, did you mean that?"

**4. Answer follow-up is limited to a fixed surface set.**
`_ANSWER_FOLLOW_UP_SURFACES` in `interaction_router.py` handles explicit follow-up phrases (`"explain more"`, `"why"`, `"which source"`). It does not handle implicit target references in commands that follow a question answer: `"open that"` after a search answer, or `"search for that in my project"` where `"that"` refers to the answer topic stored in `session_context.recent_answer_topic`. These fall through to the clarification path as `TARGET_NOT_FOUND`.

**5. Question/command adjacency is asymmetric.**
After a completed command, `session_context.clear_expired_or_resettable_context(preserve_recent_context=True)` is called, preserving recent targets. After a failed or cancelled command, `preserve_recent_context=False` wipes all context. But after a question answer, the session context is updated with `recent_answer_topic`, `recent_answer_text`, etc. — and an immediately following command has no way to reference the answer topic via `"search for that"` or `"open that file"`. The two modes do not share context signals.

**6. Mixed-interaction re-ask is mechanical.**
When a mixed-interaction clarification is pending and the reply is not parseable (`"Please reply with answer or execute."`), the message is robotic and does not remind the user what the original question or command was.

**7. No heard-echo on voice input.**
After voice capture, the recognized transcript is submitted silently. If the recognizer returned the wrong words, the user has no moment to see what was heard before execution begins.

**8. The shell goes cold after completion.**
After command completion the shell returns to idle with no contextual transition. The user has to remember what they can say next. This is especially jarring after multi-step commands.

---

## Minimal Supported Turn Types

These are the turn types JARVIS should explicitly recognize and route in v1. Rows marked **new** do not exist today.

| Turn Type | Description | Router Signal |
|---|---|---|
| `fresh_command` | A new complete command. | Existing `COMMAND` routing. |
| `fresh_question` | A new question routed to QA. | Existing `QUESTION` routing. |
| `clarification_reply` | A direct reply to an active `awaiting_clarification` prompt. | Existing blocked-state priority routing. |
| `confirmation_reply` | A yes/no/cancel to `awaiting_confirmation`. | Existing blocked-state priority routing. |
| `routing_choice` | A reply to a mixed-interaction clarification (`answer` / `execute`). | Existing `resolve_interaction_clarification_choice`. |
| `answer_follow_up` | A short phrase that continues the last QA answer. | Existing `_ANSWER_FOLLOW_UP_SURFACES`. |
| `correction` | **new** — `"no not that"` / `"the other one"` / `"actually X"` when runtime is blocked on clarification or just completed a command. | New `_looks_like_correction` check in router. |
| `implicit_reference` | **new** — A command or question using `"that"` / `"it"` / `"the result"` that refers to the last answer topic or last resolved target. | New `_resolve_implicit_reference` in parser pre-step. |
| `voice_near_miss_reply` | **new** — A yes/no reply to a pending near-miss recovery prompt. | New `pending_near_miss` state in dialogue context. |
| `failed_clarification_retry` | **new** — Any input when `apply_clarification` has just failed to patch; triggers re-ask once. | New `clarification_retry_count` in dialogue context. |

No other new turn types in v1.

---

## Dialogue State

JARVIS needs one small shared dialogue context struct that travels alongside `SessionContext` and `RuntimeManager`. It holds only the state needed for the turn types above. It is purely in-process; it resets on session reset.

```python
@dataclass(slots=True)
class DialogueContext:
    # Near-miss recovery
    pending_near_miss_phrase: str | None = None      # canonical phrase to confirm
    pending_near_miss_confidence: float | None = None
    pending_near_miss_voice_only: bool = False

    # Clarification retry
    clarification_retry_count: int = 0               # incremented on each failed apply_clarification
    last_clarification_message: str | None = None    # original question text for re-ask

    # Completion context for follow-up commands
    last_completed_intent: str | None = None         # e.g. "prepare_workspace", "open_app"
    last_completed_summary: str | None = None        # the completion_summary text

    # Implicit reference resolution
    # (answer topic/targets already live in SessionContext — no duplication needed)
```

### What must stay out of scope

- No cross-session persistence. `DialogueContext` resets on session reset, same as `SessionContext`.
- No conversation history model, turn list, or transcript summary.
- No background inference between turns.
- No multi-field collection across multiple turns — one clarification field at a time, as today.
- No tracking of what the user "usually" says or prefers.

`SessionContext` already carries the signals needed for implicit reference: `recent_answer_topic`, `recent_answer_text`, `last_resolved_targets`, `recent_primary_target`, `recent_search_results`. The `DialogueContext` does not duplicate these.

---

## Repair Behaviors

### 1. Clarification re-ask (failed clarification reply)

**Trigger:** `apply_clarification` returns a command where nothing was patched (confidence and targets unchanged, no field applied).

**Behavior:**
- Increment `dialogue_context.clarification_retry_count`.
- If count is `1`: re-surface the same `ClarificationRequest` with a short prefix: `"I didn't catch that — <original question>"`. Do not fail.
- If count is `2`: cancel the command with: `"I couldn't understand the reply. The command has been cancelled."` and reset `clarification_retry_count` to `0`.

**Constraint:** The re-ask message is the same `ClarificationRequest.message` stored in `dialogue_context.last_clarification_message` when the clarification was first issued. No new message generation.

---

### 2. Correction turn

**Trigger:** Input matches `_looks_like_correction` heuristics:
- Exact matches: `"no"`, `"not that"`, `"the other one"`, `"never mind"`, `"ignore that"`, `"wrong one"`, `"other one"`.
- Pattern: starts with `"no,"` or `"not "` and is short (≤ 6 tokens).
- Russian equivalents: `"нет"`, `"не то"`, `"другой"`, `"другое"`, `"другую"`, `"отмени"`.

**Behavior when runtime is `awaiting_clarification` (MULTIPLE_MATCHES case):**
- Treat the correction as a re-statement of the clarification reply: pass the input through `apply_clarification` as normal. If the active clarification has candidates, `_select_candidate` will handle `"the other one"` if only two candidates exist — no special casing needed there.
- If `apply_clarification` still fails to patch: use the re-ask path (behavior 1 above).

**Behavior when runtime is `idle` or `completed` (correction after a result):**
- The shell cannot undo a completed command. Respond with a fixed message: `"That action is already done. To change it, run a new command."` — surfaced as an `INFO` transcript entry, not a clarification prompt.
- Do not attempt to execute any reversal or retry.

**Behavior when runtime is `awaiting_confirmation`:**
- `"no"` / `"not that"` / `"нет"` → treat as confirmation denial. Already handled by `_CONFIRM_DENIAL_WORDS` in `runtime_manager.py`.

**Detection:** `_looks_like_correction` check is added to `interaction_router.py` and fires before the general command/question detection. It returns a new `InteractionKind.CORRECTION` routing decision. `InteractionManager` handles `CORRECTION` by branching to `_correction_result`, which applies the above behavior.

---

### 3. Voice near-miss recovery

**Trigger:** Interpreter returns confidence in `[0.55, 0.70)` on a recognized intent, AND the input originated from voice capture (flagged by `is_voice_input=True` passed from the controller).

**Behavior:**
- Set `dialogue_context.pending_near_miss_phrase` to the interpreter's `normalized_text`.
- Return a `PendingPromptViewModel` with message: `"Did you mean: '<canonical_phrase>'?"` and reply options `["Yes", "No"]`.
- Do NOT route to command or question yet.

**On "Yes" reply (while `pending_near_miss_phrase` is set):**
- Route `pending_near_miss_phrase` as a fresh command through the normal submission path.
- Clear `pending_near_miss_phrase`.

**On "No" reply:**
- Clear `pending_near_miss_phrase`.
- Return: `"Okay — say it again whenever you're ready."` as an `INFO` entry.
- Composer returns to idle.

**On typed input (not voice):** Near-miss prompt is never shown. Interpreter continues to rewrite at ≥ 0.70 as today.

**Detection:** `InteractionManager.handle_input` receives an optional `is_voice_input: bool` parameter (default `False`). When `True` and confidence is in `[0.55, 0.70)`, near-miss recovery fires instead of the normal fallback.

---

### 4. Unparseable input in `awaiting_clarification`

Already described under behavior 1. The re-ask fires at count 1. The flow is cancelled at count 2.

`clarification_retry_count` is reset to `0` whenever:
- Clarification is successfully resolved (command moves to `planning`).
- The command is cancelled or the runtime transitions to `idle`.
- A fresh command restarts from the blocked state (`_should_restart_as_fresh_command` in `runtime_manager.py`).

---

## Follow-Up Handling

### Existing answer follow-up (unchanged)

`_ANSWER_FOLLOW_UP_SURFACES` already handles explicit follow-up phrases (`"explain more"`, `"which source"`, `"why"`, etc.) by routing them as `QUESTION` turns. This is preserved as-is.

### New: implicit reference in commands after a question

When a command input contains `"that"`, `"it"`, `"the result"`, `"this"`, `"those"` as a target reference and `session_context.recent_answer_topic` or `session_context.recent_primary_target` is populated, the parser should attempt reference resolution before raising `TARGET_NOT_FOUND`.

**How it works:**
- Add a `_resolve_implicit_references` step in `command_parser.py` (or as a pre-step in `runtime_manager._handle_new_command`) that runs after parsing but before validation.
- If any target in the parsed command has `name` in `{"that", "it", "this", "those", "the result", "the file", "the folder"}` and `session_context.recent_primary_target` is non-null: substitute the recent target.
- If `session_context.recent_answer_topic` is set and the target is a bare `"that"` with intent `search_local` or `open_app`: use the answer topic as the target name.
- If resolution is ambiguous (both `recent_primary_target` and `recent_answer_topic` are set and different): do not substitute; let `TARGET_NOT_FOUND` clarification fire normally.

**Scope:** This covers the `"open that"`, `"search for that"`, `"find that file"` cases only. It does not cover chained commands, compound references, or cross-session references.

### New: follow-up command after command completion

After a command completes, `dialogue_context.last_completed_intent` and `dialogue_context.last_completed_summary` are set. The shell surfaces a single short follow-up line in the transcript (see Shell Implications). No proactive prompt, no chips, no action — informational only.

---

## Question/Command Adjacency

The current product handles the two modes symmetrically in routing but asymmetrically in context preservation. The fix is small:

**After a question answer**, `_remember_answer_context` already stores `recent_answer_topic`, `recent_answer_text`, and `recent_answer_sources` in `SessionContext`. These are now also visible to `_resolve_implicit_references` (above) so a subsequent command can use `"that"` to refer to the answer topic.

**After a command completes**, `dialogue_context.last_completed_intent` is set. A subsequent question that matches `_ANSWER_FOLLOW_UP_SURFACES` still routes to QA mode as today. A subsequent question that does not match any follow-up surface routes as a fresh question — context from the command is available in `_runtime_snapshot()` which is already passed to `answer_question`.

**Switching mid-turn (mixed interaction):** Already handled by `InteractionKind.CLARIFICATION` and `_remember_pending_interaction_clarification`. No change needed.

**The one gap to close:** After a question answer, the existing `clear_expired_or_resettable_context` call on the next command turn uses `preserve_recent_context=True` if the previous runtime state was `completed`. But if the previous interaction was a question (runtime stayed idle), no explicit clear happens, so `recent_answer_topic` persists correctly through the next command — `_resolve_implicit_references` can use it. No change needed to the existing clear logic.

**Explicit rule for adjacency:**

| Previous turn | Next turn | Behaviour |
|---|---|---|
| Command completed | Fresh command | Normal new command; previous targets available for implicit reference. |
| Command completed | Fresh question | Normal QA; `runtime_snapshot` includes completed command summary. |
| Question answered | Fresh command | Command parses normally; implicit `"that"` resolved from `recent_answer_topic` or `recent_primary_target`. |
| Question answered | Answer follow-up | Routes to QA as today. |
| Awaiting clarification | Fresh question | Already handled by `_looks_like_fresh_question_while_blocked` in router. |
| Awaiting clarification | Correction | New `CORRECTION` turn type; re-routes clarification reply. |

---

## Shell Implications

**1. Heard echo in composer.**
After voice capture completes and the transcript is returned, display the recognized text in the composer's input field as read-only text for the moment before submission. This is one line added to `ConversationController.start_voice_capture` — set the composer input field to the transcript before calling `submit_text`. No new widget state needed; the existing `SUBMITTING` voice state already exists.

**2. Clarification re-ask in transcript.**
When the re-ask fires (retry count = 1), a new `PROMPT` transcript entry is appended with the re-ask text. It uses the existing `PendingPromptViewModel` surface. No new card type needed.

**3. Correction acknowledgement in transcript.**
When a post-completion correction fires, the response (`"That action is already done..."`) is an `INFO` transcript entry. No prompt chips, no action path.

**4. Near-miss prompt as a prompt card.**
The `"Did you mean: '...'"` prompt is a standard `PendingPromptViewModel` with two reply chips: `Yes` and `No`. It is rendered via the existing prompt card path. The controller handles the reply via `submit_prompt_action`.

**5. Completion follow-up nudge.**
After command completion, a single short `INFO` transcript entry is appended below the `COMPLETION` card. The text is derived from `dialogue_context.last_completed_summary` plus a contextual hint (e.g. `"Say 'resume work' anytime." `). It is display-only.

**6. Status panel dialogue state.**
The status panel's "Next required action" line should reflect the dialogue state:
- During near-miss: `"Confirm what you meant"`.
- During re-ask: `"Clarify: <short question>"`
- During correction after completion: `"Command is done. Start a new one."`

This is a one-line change in the `VisibilityPayload` that feeds the status panel; the mapping goes into `visibility_mapper.py`.

**7. Composer voice-state after near-miss.**
After the near-miss prompt is shown, the composer should remain in `READY` state (not capture more voice). The near-miss prompt takes over. After the user replies, the composer returns to its normal idle state.

---

## Files To Change

| File | Reason |
|---|---|
| `context/session_context.py` | Add `DialogueContext` as a field (or sibling dataclass); expose get/set/reset methods. |
| `interaction/interaction_router.py` | Add `_looks_like_correction` check and `InteractionKind.CORRECTION` routing; add implicit reference token detection helper. |
| `interaction/interaction_manager.py` | Handle `CORRECTION` turn type; pass `is_voice_input` flag; trigger near-miss prompt at `[0.55, 0.70)` confidence; handle `voice_near_miss_reply` (yes/no); update `DialogueContext` on each turn result. |
| `clarification/clarification_handler.py` | Emit `last_clarification_message` into `DialogueContext` when clarification is built; detect unpatched reply and increment `clarification_retry_count`; generate re-ask prefix. |
| `runtime/runtime_manager.py` | Reset `dialogue_context.clarification_retry_count` on resolution, cancellation, or fresh-command restart; set `last_completed_intent` / `last_completed_summary` on completion. |
| `parser/command_parser.py` | Add `_resolve_implicit_references` step: substitute bare pronoun targets (`"that"`, `"it"`, `"this"`) from `session_context.recent_primary_target` or `recent_answer_topic` before validation. |
| `ui/visibility_mapper.py` | Add completion nudge `INFO` entry; add dialogue-state-aware `next_step_hint` text for near-miss, re-ask, and correction states. |
| `desktop/shell/controllers/conversation_controller.py` | Pass `is_voice_input=True` to `handle_input` from `start_voice_capture`; show transcript text in composer briefly after voice capture; handle near-miss prompt chips. |
| `desktop/shell/widgets/composer.py` | Show recognized voice transcript in input field briefly before submission (one additional voice state or existing `SUBMITTING` state extended). |
| `types/interaction_kind.py` | Add `CORRECTION` value to `InteractionKind` enum. |
| `tests/test_interaction_router.py` | Add correction turn detection tests. |
| `tests/test_protocol_runtime.py` | Add clarification retry-count and re-ask tests. |
| `tests/test_input_interpreter.py` | Add near-miss threshold band tests (`0.55–0.69`). |
| `tests_desktop/test_conversation_controller.py` | Add heard-echo and near-miss prompt chip tests. |
| `tests_desktop/test_desktop_presenters.py` | Add re-ask, correction-ack, and completion-nudge entry presenter tests. |

---

## Out Of Scope

- Any change to the deterministic command/question routing boundary.
- Multi-field clarification collection across multiple turns.
- Cross-session memory or persistent dialogue history.
- Proactive JARVIS-initiated turns (JARVIS only speaks in response to user input).
- Background voice listening, continuous capture, or wake words.
- Natural language generation for answers (QA mode unchanged).
- Any relaxation of confirmation boundaries — all currently-confirmed actions keep their explicit gates.
- Undo or reversal of completed commands.
- Learning user preferences or adapting vocabulary over time.
- Near-miss recovery for typed input (only voice, where recognition errors are common).
- Implicit reference resolution for anything other than the last resolved target and last answer topic — no multi-hop reference chains.
- Dialogue for any flow not already supported by the runtime (no new protocols, intents, or executors).
- Streaming output or partial-answer rendering.
- Internationalization beyond the existing English/Russian scope in each touched file.

---

## Acceptance Criteria

**Clarification repair:**
1. A reply of `"umm"` to any active clarification prompt triggers a re-ask: `"I didn't catch that — <original question>"`. The command stays active.
2. A second invalid reply cancels the command with: `"I couldn't understand the reply. The command has been cancelled."`.
3. A valid reply on the first or second attempt resolves the clarification and continues execution normally.
4. `clarification_retry_count` resets to `0` after cancellation, successful resolution, and session reset.

**Correction turn:**
5. `"no, not that"` while `awaiting_clarification` (MULTIPLE_MATCHES) is treated as a re-statement of the clarification reply, not a fresh command.
6. `"the other one"` while `awaiting_clarification` with exactly two candidates selects the non-chosen candidate.
7. `"no"` or `"not that"` after a completed command produces: `"That action is already done. To change it, run a new command."` — no execution attempt.
8. `"no"` during `awaiting_confirmation` continues to route as confirmation denial (existing behavior, unchanged).

**Voice near-miss recovery:**
9. A voice input that the interpreter rates at confidence `0.60` on a known intent shows: `"Did you mean: '<phrase>'"` with Yes/No chips. No command executes yet.
10. Tapping Yes routes the canonical phrase and executes normally.
11. Tapping No clears the prompt and returns composer to idle: `"Okay — say it again whenever you're ready."`.
12. A typed input at confidence `0.60` is NOT shown a near-miss prompt — interpreter fallback behavior unchanged.

**Implicit reference:**
13. `"search for that in my project"` issued after a question answer whose `recent_answer_topic` is `"async/await"` routes as `search_local` with query `"async/await"` — no `TARGET_NOT_FOUND` clarification.
14. `"open that"` issued after a command that resolved `recent_primary_target` to `Notes.app` routes as `open_app Notes` — no `TARGET_NOT_FOUND` clarification.
15. `"open that"` with no prior context (no `recent_answer_topic`, no `recent_primary_target`) still produces `TARGET_NOT_FOUND` clarification as today.

**Heard echo:**
16. After voice capture, the recognized transcript is visible in the composer input field before submission — the user can see what JARVIS heard.

**Question/command adjacency:**
17. A question answer followed immediately by `"search for that"` resolves the implicit reference correctly (covered by criteria 13).
18. A completed command followed immediately by a fresh question routes as `QUESTION` with the runtime snapshot visible to `answer_question`.
19. All existing routing, confirmation, and clarification behaviors for inputs not matching the new turn types are bit-for-bit unchanged — verified by running the full test suite with `JARVIS_INTERPRETER_DISABLED=1`.

**Regression:**
20. All 100+ existing interaction/router/runtime/interpreter tests pass without modification.
21. The `pending_near_miss_phrase`, `clarification_retry_count`, `last_completed_intent` fields all reset correctly on `reset_session`.
