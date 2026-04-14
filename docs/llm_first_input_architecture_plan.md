# LLM-First Input Architecture Plan

## Goal

Make JARVIS understand natural user input reliably — especially voice — without growing
an ever-expanding list of heuristic patches. The LLM interpreter already exists; this plan
makes it the primary path instead of the last resort. Everything downstream of the
interpreter (parser, validator, confirmation, runtime, executor) stays unchanged.

---

## Why The Current Approach Is Not Enough

The current system has an LLM interpreter (`InputInterpreter`) but wraps it in so many
pre-filters that most non-canonical input never reaches it, or reaches it too late.

**Enumerated heuristic patches that have accumulated:**

| Location | Patch | What it covers |
|---|---|---|
| `input_interpreter.py` | Fix 2: `_POLITE_COMMAND_SUBJECTS + _POLITE_V1_COMMAND_VERBS` | "can you resume..." not skipped as question |
| `input_interpreter.py` | Fix 3: `_RESUME_ON_PATTERN` | "resume ... on workspace" → "start work on..." |
| `input_interpreter.py` | Fix 4: 4 `_HERO_NEAR_MISS_*` regexes | STT typo variants of "start work"/"resume work" |
| `input_interpreter.py` | `_NATURAL_SPEECH_MARKERS` (18 markers) | Detect natural speech to avoid skipping LLM |
| `input_interpreter.py` | `_CANONICAL_COMMAND_STARTERS` (14 starters) | Detect "already canonical" to skip LLM |
| `input_interpreter.py` | `_looks_like_deterministic_match` | Combines all of the above into one gate function |
| `interaction_router.py` | `_POLITE_COMMAND_PREFIXES` (21 combinations) | Polite command detection |
| `interaction_router.py` | `_COMMAND_STARTERS` (18 starters) | Command prefix detection |
| `interaction_router.py` | `_QUESTION_STARTERS` (28 starters, EN+RU) | Question prefix detection |
| `interaction_router.py` | `_ANSWER_FOLLOW_UP_SURFACES` (35 frozenset entries) | Follow-up surface matching |
| `parser/command_parser.py` | `_START_WORK_PATTERN` (literal prefix) | Exact "start work" only |

The result: the system understands what it memorized, not what the user meant. Each new
failure produces a new patch. The patches interact in non-obvious ways. Fixing one phrasing
breaks assumptions elsewhere.

**Root cause:** the LLM is used as a fallback rather than a primary path. Its output is
accepted only when the pre-filter decides the input is "not already canonical" — which is
itself a heuristic that can fail in both directions.

---

## Proposed Input Flow

```
raw_input
    │
    ▼
[GATE] Fast-path bypass — skip LLM only for these cases:
    1. Runtime is blocked (awaiting_clarification / awaiting_confirmation)
       → pass through unchanged; these are replies, not new inputs
    2. Short exact replies: "yes", "no", "confirm", "cancel", "answer", "execute"
       → already unambiguous; LLM adds nothing
    3. Explicit protocol reference: text matches "protocol <name>" form
       → registry lookup, no interpretation needed
    (All other inputs continue to the interpreter)
    │
    ▼
[INTERPRETER] LLM interpretation (primary path for all other input)
    → returns InputInterpretation (see contract below)
    │
    ▼ (branch on confidence + mode_hint)
    ├─ confidence ≥ 0.85, mode_hint = "command"
    │   → use normalized_text; pass mode_hint to router as a strong signal
    │
    ├─ confidence ≥ 0.85, mode_hint = "question"
    │   → use normalized_text or raw_input; pass mode_hint to router
    │
    ├─ 0.70 ≤ confidence < 0.85, mode_hint = "command", is_voice_input
    │   → near-miss confirmation prompt (existing dialogue substrate behaviour)
    │
    ├─ 0.70 ≤ confidence < 0.85, mode_hint = "command", typed
    │   → use normalized_text with low-confidence flag; router decides
    │
    ├─ confidence < 0.70 OR mode_hint = "unclear"
    │   → passthrough: use raw_input unchanged
    │
    └─ api_error / timeout
        → passthrough: use raw_input unchanged; no user-visible error
    │
    ▼
[ROUTER] interaction_router.route_interaction (simplified)
    - If interpreter returned mode_hint "command" or "question" with confidence ≥ 0.85:
      trust the hint; skip the prefix-matching heuristics for this input
    - If no strong hint: fall back to current prefix-matching heuristics (unchanged)
    - Blocked-state detection, follow-up surfaces, and mixed-interaction splitting
      remain in the router because they depend on session context the interpreter
      does not have
    │
    ▼
[PARSER → VALIDATOR → RUNTIME → EXECUTOR] unchanged
```

The key shift: the interpreter fires first on all non-obvious inputs. The router's
heuristics become a fallback for when the interpreter returned no strong signal, not the
primary classification logic.

---

## Interpreter Contract

```python
@dataclass(slots=True)
class InputInterpretation:
    normalized_text: str
    # Canonical form of the command or question.
    # If mode_hint is "unclear" or skipped=True, this equals raw_input unchanged.

    mode_hint: Literal["command", "question", "unclear"]
    # "command"  → route to parser / runtime
    # "question" → route to QA
    # "unclear"  → passthrough, let router decide

    intent_hint: str | None
    # One of the known v1 intent identifiers, or None.
    # E.g. "prepare_workspace", "resume_work", "open_app", "close_app", "search_local"
    # The parser ignores this; it is used only for debug tracing and near-miss decisions.

    entity_hints: dict[str, str]
    # Named entities extracted from the raw input and grounded in it.
    # E.g. {"app": "Telegram", "workspace": "JARVIS"}
    # Only entities whose values appear (directly or via alias) in raw_input are kept.
    # The parser may use these as soft hints but must re-extract from normalized_text.

    confidence: float
    # 0.0–1.0. The interpreter's self-assessed confidence that normalized_text is correct.

    debug_note: str | None
    # One short sentence explaining what the interpreter did and why.

    latency_ms: float
    skipped: bool
    # True when the fast-path was taken and no LLM call was made.

    skip_reason: str | None
    # One of: "blocked_runtime", "exact_reply", "protocol_reference",
    #         "api_error", "timeout", "disabled", None
```

**What the interpreter must NOT do:**
- Invent entities not traceable to the raw input
- Return an execution plan or action sequence
- Return a command when the input is clearly a question (existing safety boundary)
- Return confidence > 0.70 when the input is genuinely ambiguous
- Rewrite a clarification or confirmation reply

**What the interpreter is allowed to do:**
- Translate natural or mixed-language phrasing into canonical English command form
- Identify the mode (command vs question) when it is unambiguous
- Name the most plausible v1 intent as a hint
- Return "unclear" for compound, ambiguous, or genuinely unknown inputs

---

## Safety Boundaries

These must be preserved exactly. None of them change.

1. **Questions never become commands.** If raw input is clearly a question and the
   interpreter returns `mode_hint = "command"`, discard the interpreter output and
   passthrough. This check already exists; keep it.

2. **Blocked runtime states bypass the interpreter.** When the runtime is in
   `awaiting_clarification` or `awaiting_confirmation`, the input is a reply to an
   active prompt. The interpreter is stateless and cannot distinguish "notes" (clarification
   reply) from "open notes" (new command). Bypass is mandatory.

3. **Low confidence → passthrough, never guess.** Below the threshold, `normalized_text`
   is discarded and `raw_input` is used unchanged. The router's heuristics then apply.
   This preserves the existing safe fallback behaviour.

4. **Entity grounding.** Any entity in `entity_hints` or embedded in `normalized_text`
   must be traceable to the raw input (substring or known alias match). The interpreter
   must not hallucinate entities.

5. **No interpreter output is ever executed directly.** Interpreter output flows into
   the parser and validator. The parser can reject it. The validator can reject it.
   Confirmation gates remain fully intact.

6. **Timeout and API error → silent passthrough.** The user should never see an
   interpreter failure. The system falls through to the router's heuristics as if
   the interpreter was disabled.

---

## Fast Path vs LLM Path

| Input type | Fast path? | Reason |
|---|---|---|
| `"yes"`, `"no"`, `"confirm"`, `"cancel"` | yes | Exact reply words — unambiguous |
| `"answer"`, `"execute"` | yes | Routing replies — unambiguous |
| Runtime blocked (`awaiting_clarification` / `awaiting_confirmation`) | yes | Reply, not new input |
| `"protocol <name>"` form | yes | Explicit protocol reference — registry handles it |
| All other input (natural speech, mixed language, ambiguous, Russian, voice) | **LLM** | Primary path |

The current `_looks_like_deterministic_match` function with its 14-starter + 18-marker
heuristic is replaced by this narrow list. Inputs that currently bypass the LLM because
they start with `"prepare "` or `"set up "` will now go through the LLM, which will
correctly normalize them or confirm them unchanged.

**Latency:** The LLM call (Haiku) is already present and already fires for ambiguous
inputs. The change is that it fires for more inputs. The fast-path list above still covers
the most frequent terminal inputs (yes/no/confirm/cancel/protocol). Hero-flow inputs like
`"start work"` that are already canonical will be confirmed unchanged by the interpreter
with high confidence, adding one round-trip. This is acceptable; the interpreter result
is cached per-input and can be made prompt-cached for common phrases.

---

## What To Remove Or Simplify

### Remove entirely

| Code | Location | Replacement |
|---|---|---|
| `_HERO_NEAR_MISS_START_T1/T2`, `_HERO_NEAR_MISS_RESUME_T1/T2` (4 regexes) | `input_interpreter.py` | LLM handles STT typo variants natively |
| `_RESUME_ON_PATTERN` and its application block (Fix 3) | `input_interpreter.py` | LLM normalizes "resume work on X" → "start work on X" |
| `_POLITE_COMMAND_SUBJECTS`, `_POLITE_V1_COMMAND_VERBS`, `_is_polite_v1_command` (Fix 2) | `input_interpreter.py` | LLM handles "can you resume..." natively |
| `_NATURAL_SPEECH_MARKERS` (18 markers) | `input_interpreter.py` | No longer needed as gate; LLM is primary path |
| `_CANONICAL_COMMAND_STARTERS` (14 starters) | `input_interpreter.py` | Replaced by narrower fast-path list above |
| `_looks_like_deterministic_match` function | `input_interpreter.py` | Replaced by the fast-path gate |

### Simplify (reduce, not remove)

| Code | Location | What to do |
|---|---|---|
| `_POLITE_COMMAND_PREFIXES` (21 combinations) | `interaction_router.py` | Keep as fallback for when interpreter returned no strong signal; do not call for inputs where interpreter fired with confidence ≥ 0.85 |
| `_COMMAND_STARTERS` / `_QUESTION_STARTERS` prefix checks | `interaction_router.py` | Keep as fallback only; skip when interpreter mode_hint is strong |
| `_START_WORK_PATTERN` literal prefix check | `parser/command_parser.py` | Keep for canonical "start work" inputs; the interpreter normalizes non-canonical forms into this before the parser sees them |

### Keep unchanged

| Code | Why |
|---|---|
| `_ANSWER_FOLLOW_UP_SURFACES` (35 entries) | Context-dependent; interpreter is stateless |
| `_BLOCKED_STATE_QUESTION_MARKERS` | Context-dependent; interpreter bypassed in blocked state |
| `_MIXED_COMMAND_MARKERS` + `split_mixed_interaction_input` | Mixed-interaction splitting is a session-context decision |
| `_GREETING_QUESTION_MARKERS` | Short greetings, already on fast-path candidate |
| Entire parser / validator / planner / executor | Not in scope |
| Entire runtime state machine | Not in scope |
| Confirmation and clarification gates | Not in scope |

---

## Files To Change

| File | Change |
|---|---|
| `input/input_interpreter.py` | Replace `_looks_like_deterministic_match`, `_NATURAL_SPEECH_MARKERS`, `_CANONICAL_COMMAND_STARTERS`, `_is_polite_v1_command`, `_POLITE_COMMAND_SUBJECTS`, `_POLITE_V1_COMMAND_VERBS`, `_RESUME_ON_PATTERN`, and all 4 `_HERO_NEAR_MISS_*` patterns with a single `_is_fast_path_input(text, runtime_state)` gate. `InterpretedInput` → `InputInterpretation` (rename + add `skip_reason` string). |
| `interaction/interaction_manager.py` | Update interpreter invocation: always call interpreter unless fast-path. Pass `mode_hint` to router as a strong signal when confidence ≥ 0.85. Preserve blocked-runtime bypass. Preserve near-miss logic (unchanged). |
| `interaction/interaction_router.py` | Accept optional `mode_hint` parameter. When `mode_hint` is "command" or "question" with high confidence, skip prefix-match heuristics and return the decision directly. Retain all context-dependent logic unchanged (blocked state, follow-ups, mixed interaction). |
| `input/input_interpreter.py` (system prompt) | Expand system prompt to cover Russian-language phrasing for `prepare_workspace` and `resume_work` as canonical examples. The LLM now handles these instead of deterministic pre-norm rules. |
| `protocols/builtin_protocols.py` | Add Russian-locale triggers (`"продолжи работу"`, `"возобновить работу"`) for `resume_work` as a deterministic fallback independent of the interpreter. This is low-cost and zero-latency. |
| `tests/test_input_interpreter.py` | Update tests for removed patches; add tests for new fast-path gate; add tests for Russian normalization via LLM mock. |
| `tests/test_interaction_router.py` | Add tests for `mode_hint` shortcircuit path. |

No changes to: `parser/`, `validator/`, `runtime/`, `planner/`, `executor/`, `clarification/`, `protocols/` (except the Russian trigger addition).

---

## Out Of Scope

- Redesigning the runtime state machine
- Redesigning confirmation or clarification boundaries
- Adding LLM-based execution planning
- Giving the LLM any ability to produce or modify execution steps
- Streaming or multi-turn LLM interaction
- Context-aware interpretation (the interpreter stays stateless)
- Rewriting the router's session-context logic
- Changing how the parser, validator, or executor work
- Supporting new intents not already in v1
- Adding user-configurable phrases or synonyms
- Prompt caching infrastructure (can be added later; not a prerequisite)

---

## Acceptance Criteria

### Correctness

The following inputs must reach the correct intent without error in the new architecture:

| Input | Expected mode | Expected intent |
|---|---|---|
| `start work` | command | `prepare_workspace` |
| `prepare workspace` | command | `prepare_workspace` |
| `prepare JARVIS workspace` | command | `prepare_workspace`, workspace=JARVIS |
| `let's get to work` | command | `prepare_workspace` |
| `can you start working` | command | `prepare_workspace` |
| `начни работу` | command | `prepare_workspace` |
| `подготовь рабочее пространство` | command | `prepare_workspace` |
| `Старт work` | command | `prepare_workspace` |
| `resume work` | command | `resume_work` |
| `get back to work` | command | `resume_work` |
| `продолжи работу` | command | `resume_work` |
| `stat work` (STT typo) | command | `prepare_workspace` |
| `open Telegram` | command | `open_app`, target=Telegram |
| `what can you do` | question | QA mode |
| `how does this work` | question | QA mode |
| `yes` (during clarification) | fast-path | pass through unchanged |
| `confirm` (during confirmation) | fast-path | pass through unchanged |

### Safety

- No question input ever produces a command routing decision
- No interpreter output is accepted when runtime is in `awaiting_clarification` or `awaiting_confirmation`
- Any API timeout or error is invisible to the user and falls back to current heuristic behaviour
- Entity grounding check remains: normalized_text entities must be in raw_input

### Regression

- All existing passing tests continue to pass
- No new runtime states introduced
- No changes to confirmation or clarification gate behaviour
