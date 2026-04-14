# Input Interpreter Plan

## Problem

The current input pipeline is brittle in the following concrete ways.

| Pain point | Where it bites |
| --- | --- |
| Protocol triggers are **exact-match only** (`registry.py::_trigger_matches` does `candidate == trigger_phrase`). "resume my work", "let's get back to work", "pick up where I left off" all silently fail to trigger `resume_work`. | `protocols/registry.py:94` |
| The router is **keyword-prefix only**. Voice transcripts with natural filler ("I'd like to open Chrome", "let me pull up VS Code") don't match any entry in `_POLITE_COMMAND_PREFIXES` or `_COMMAND_STARTERS`. | `interaction/interaction_router.py:39-98` |
| The command parser is **regex-pattern only**. Natural spoken forms like "pull up my JARVIS project in code" or "get VS Code going with the JARVIS folder" parse to `clarify` with an unknown target. | `parser/command_parser.py:261` |
| Voice normalization handles a **fixed lexicon**. It strips known filler and translates a fixed list of Russian verbs, but cannot generalize beyond what is hardcoded. | `input/voice_normalization.py` |

The deterministic runtime, confirmation boundaries, and supervised execution are not the problem. The problem is that raw input — especially voice transcripts — often doesn't reach those layers in a form they can use.

---

## Where the layer sits

```
Voice transcript / typed text
        │
        ▼
input/voice_normalization.py        (existing: strip wake word, Russian verbs, fillers)
        │
        ▼
┌───────────────────────────────┐
│  input/input_interpreter.py  │  ◄── NEW: LLM-assisted normalization layer
│  InputInterpreter.interpret() │
└───────────────────────────────┘
        │ returns InterpretedInput
        │ (normalized_text, routing_hint, entity_hints, confidence)
        ▼
interaction/interaction_router.py   (existing: deterministic keyword routing)
        │
        ▼
parser/command_parser.py            (existing: regex/structural parsing)
        │
        ▼
validator / planner / executor / confirmation (all existing, all unchanged)
```

The interpreter sits **after** voice normalization and **before** the deterministic router and parser. It is a pre-processing step inside `InteractionManager.handle_input()`, called only when the normalized input is not already an unambiguous deterministic match.

---

## Exact responsibilities

The interpreter may:

- **Normalize natural phrasing into canonical command text.** "resume my work" → "resume work". "pull up VS Code with the JARVIS folder" → "start work on JARVIS". "let's get back to the project" → "resume work".
- **Produce a routing hint** (command / question / unclear). Used only to nudge the existing deterministic router, not to override it.
- **Extract entity hints** for intent and named entities. "open my notes app" → `{intent_hint: "open_app", entity: "Notes"}`. These become optional seeds for the parser, not parsed commands.
- **Normalize protocol trigger text.** "resume my work" → "resume work" so the existing exact-match trigger fires correctly.
- **Emit a debug note** describing what it interpreted and why, usable in the existing debug trace.

---

## Strict non-responsibilities

The interpreter must **not**:

- Execute any action.
- Bypass or replace `route_interaction()`, `parse_command()`, `validate_command()`, `build_execution_plan()`, or `execute_step()`.
- Add, remove, or modify confirmation or clarification requirements.
- Change the command vs question routing decision when the deterministic router is already confident.
- Decide whether a command is safe or unsafe.
- Access session context, protocol state, or file system.
- Initiate follow-up turns or multi-step orchestration.
- Communicate anything to the user directly.
- Run when disabled or when the deterministic path already produced a confident match.

---

## Hard safety boundaries

These are absolute constraints enforced in code, not just in the prompt.

**1. Questions must never become commands.**

If the input is a question — syntactically or semantically — the interpreter must return `routing_hint = "question"` or `routing_hint = None`. It must never return `routing_hint = "command"` for a question. The downstream deterministic router still makes the final call; the interpreter must not push a question toward command execution.

Enforcement: before accepting any interpreted output, the caller in `InteractionManager` checks — if the original input looks like a question by the existing deterministic heuristics (`_looks_like_question` returns `True`) and `routing_hint == "command"`, the `routing_hint` is discarded and the original deterministic decision is used.

**2. Entities must be grounded in the input.**

The interpreter must not invent entities that are not present or strongly implied in the raw input text. "open something" must not produce `entity: "Safari"` because Safari is not in the input. "open my usual app" must not produce a specific app name. Unresolvable entities must remain absent from `entity_hints`, forcing the deterministic path to trigger normal clarification.

Enforcement: any `entity_hints` value that does not appear as a substring or a known alias of a substring in the raw input is stripped before passing downstream.

**3. Low-confidence outputs fall back to the original normalized text, not to a guess.**

If `confidence < 0.70`, `normalized_text` is not used. The original voice-normalized text is passed downstream unchanged. This is not a soft advisory — it is a hard branch in the caller code.

Enforcement: `InteractionManager` checks `interpreted.confidence` before substituting `normalized_text`. The threshold is defined as a named constant (`_INTERPRETER_CONFIDENCE_THRESHOLD = 0.70`) so it can be audited and adjusted without searching call sites.

**4. Unclear cases must preserve downstream clarification.**

If the interpreter is unsure, it must return `routing_hint = "unclear"` and leave `normalized_text` equal to the original. It must never resolve an ambiguous input to a specific command just to avoid surfacing a clarification turn. The existing clarification machinery is the correct path for genuine ambiguity.

Enforcement: `routing_hint = "unclear"` causes the caller to discard the interpreter's `routing_hint` entirely and pass the original normalized text downstream. The deterministic router then handles it, which may produce a clarification block — as intended.

---

## Rewrite policy

### Allowed rewrites

The interpreter may rewrite input only when all of the following are true:
- The rewritten form is a known canonical phrase or intent pattern from the fixed supported-intent vocabulary.
- The entities in the rewritten form are grounded in the original input.
- The rewrite does not change the semantic type (command stays command; question stays question).
- Confidence is at or above 0.70.

**Allowed examples (input → normalized_text):**

| Raw input | normalized_text | Reason |
| --- | --- | --- |
| `"resume my work"` | `"resume work"` | Paraphrase of exact protocol trigger; entity-free |
| `"let's get back to the project"` | `"resume work"` | Colloquial variant of protocol trigger; entity-free |
| `"pick up where I left off"` | `"resume work"` | Same intent, no entity invented |
| `"start working on JARVIS"` | `"start work on JARVIS"` | Minor verb normalization; entity JARVIS is in input |
| `"pull up VS Code with the JARVIS folder"` | `"start work on JARVIS"` | Natural phrasing → hero flow; both entities grounded in input |
| `"open my notes app"` | `"open Notes"` | Known alias (`notes app` → `Notes`); grounded |
| `"let me find files named roadmap in the JARVIS folder"` | `"find files named roadmap in JARVIS"` | Filler removal; entities grounded |
| `"hey can you search the JARVIS project for TODO"` | `"search the JARVIS project for TODO"` | Polite filler stripped; entities grounded |
| `"закрой телеграм"` | `"close Telegram"` | Russian command already handled by voice_normalization; interpreter leaves unchanged or confirms |
| `"get VS Code open"` | `"open Visual Studio Code"` | Known app alias; grounded |

### Forbidden rewrites

**Forbidden examples (input → what must NOT happen):**

| Raw input | Forbidden output | Reason |
| --- | --- | --- |
| `"what can you do?"` | `normalized_text = "list capabilities"`, `routing_hint = "command"` | Question converted to command — hard boundary violation |
| `"how does resume work work?"` | `normalized_text = "resume work"`, `routing_hint = "command"` | Question about a feature converted to execution of that feature |
| `"open something"` | `entity_hints = {"app": "Safari"}` | Entity not grounded in input |
| `"open my usual app"` | `entity_hints = {"app": "Visual Studio Code"}` | Entity invented from context not in the input |
| `"resume work and then open Chrome"` | `normalized_text = "resume work"` | Multi-command input silently truncated; downstream must see full input for routing |
| `"close everything"` | `normalized_text = "close all apps"` | Interpreter must not resolve unsupported intents; pass through for deterministic failure |
| `"I'm not sure what I want"` | `routing_hint = "command"`, `normalized_text = "start work"` | Ambiguous input resolved to specific command — hard boundary violation |
| `"open the file"` (no prior context) | `entity_hints = {"file": "/last/known/path"}` | Entity from session state not visible to interpreter — interpreter is stateless |

---

## Structured output

```python
@dataclass(slots=True)
class InterpretedInput:
    normalized_text: str          # canonical text to pass downstream; equals original if no rewrite
    routing_hint: str | None      # "command" | "question" | "unclear" | None
    intent_hint: str | None       # one of the supported intent strings, or None
    entity_hints: dict[str, str]  # grounded entities only; e.g. {"app": "Notes", "workspace": "JARVIS"}
    confidence: float             # 0.0–1.0; below 0.70 → normalized_text not used
    debug_note: str | None        # free-text explanation for debug trace; not shown to user
    skipped: bool                 # True if interpreter was bypassed (fallback path)
    raw_input_seen: str           # the exact string the interpreter received (for trace comparison)
```

`normalized_text` is the only field the downstream pipeline is required to use when `confidence >= 0.70` and `skipped == False`. All other fields are advisory. The runtime never sees `InterpretedInput` directly.

---

## How it fails safely

Every failure mode falls back to the original normalized text silently.

| Failure | Behavior |
| --- | --- |
| API timeout | `skipped=True`, original text passed downstream, no user-visible error |
| API error / non-2xx | `skipped=True`, original text passed downstream |
| Malformed / unparseable JSON response | `skipped=True`, original text passed downstream |
| `confidence < 0.70` | `routing_hint` and `entity_hints` ignored; `normalized_text` not used; original text passed downstream |
| `normalized_text` is empty or longer than 3× the input | original text used, `skipped=True` |
| `routing_hint = "command"` contradicts deterministic question signal | `routing_hint` discarded; original deterministic decision preserved |
| Entity in `entity_hints` not grounded in raw input | that entity stripped before passing downstream |
| `routing_hint = "unclear"` | interpreter output discarded entirely; original text passes through |
| Interpreter disabled via `JARVIS_INTERPRETER_DISABLED=1` | not called at all; deterministic path runs unchanged |

No exception from the interpreter propagates to the user. The interpreter wraps all calls in a top-level try/except and always returns a valid `InterpretedInput`.

The existing behavior in `interaction/interaction_manager.py` must be bit-for-bit identical when the interpreter is disabled.

---

## Visibility and debuggability

### What is logged

Every interpreter call logs the following into the `debug_trace` dict under `"interpreter_result"`:

```json
{
  "raw_input_seen": "resume my work",
  "normalized_text": "resume work",
  "normalized_text_used": true,
  "routing_hint": "command",
  "routing_hint_used": true,
  "intent_hint": "run_protocol",
  "entity_hints": {},
  "confidence": 0.91,
  "debug_note": "Paraphrase of 'resume work' protocol trigger. No entities to ground.",
  "skipped": false,
  "skip_reason": null,
  "latency_ms": 312
}
```

When the interpreter is bypassed or falls back:

```json
{
  "raw_input_seen": "open Safari",
  "normalized_text": "open Safari",
  "normalized_text_used": false,
  "skipped": true,
  "skip_reason": "deterministic_match",
  "latency_ms": 0
}
```

`skip_reason` is one of: `"deterministic_match"`, `"disabled"`, `"api_error"`, `"timeout"`, `"low_confidence"`, `"malformed_response"`, `"entity_grounding_failed"`, `"question_command_conflict"`, `"unclear"`.

### Comparing raw, normalized, and interpreted text during testing

The debug trace records three text values in sequence:

1. `raw_input_seen` — the string the interpreter received (post voice-normalization, pre-interpretation).
2. `normalized_text` — the interpreter's proposed canonical form.
3. The actual string passed to `route_interaction()` — recorded as `"routed_input"` in the existing `"routing_decision"` trace entry.

When `normalized_text_used == true`, values 2 and 3 will match. When `skipped == true`, values 1 and 3 will match. A test that needs to verify the interpreter's behavior compares all three and asserts which pair is equal.

Test helper pseudocode:
```python
def assert_interpreter_rewrote(trace, expected_normalized):
    result = trace["interpreter_result"]
    assert result["normalized_text_used"] is True
    assert result["normalized_text"] == expected_normalized
    assert trace["routing_decision"]["normalized_input"] == expected_normalized

def assert_interpreter_skipped(trace, expected_reason=None):
    result = trace["interpreter_result"]
    assert result["skipped"] is True
    assert trace["routing_decision"]["normalized_input"] == result["raw_input_seen"]
    if expected_reason:
        assert result["skip_reason"] == expected_reason
```

---

## First-slice scope limits

### Intents included in v1

The interpreter is aware of and may normalize toward these intents only:

| Intent | Canonical trigger examples |
| --- | --- |
| `run_protocol: resume_work` | "resume work", "pick up where I left off", "get back to work", "resume my work" |
| `prepare_workspace` | "start work on X", "start working on X", "open X in VS Code", "set up X in code", "pull up X in VS Code" |
| `open_app` | "open X", "launch X", "start X" — where X resolves to a known app alias |
| `open_folder` | "open the X folder", "open X directory" |
| `search_local` | "search X for Y", "find files named Y in X", "look for Y in X" |

"Aware of" means the prompt includes these intents and their canonical forms. The interpreter may produce `normalized_text` and `intent_hint` for these intents only.

### Intents excluded from v1

The interpreter must not produce `intent_hint` or `normalized_text` targeting any of the following in v1. If the input appears to target one of these, `routing_hint = "unclear"` and `normalized_text` equals the original.

| Excluded intent | Reason |
| --- | --- |
| `close_app` / `close_window` | Destructive; requires confirmation boundary; interpreter must not soften the path to it |
| `open_website` | URL entities are high-precision and should not be guessed |
| `list_windows` / `focus_window` / `close_window` | Window management is session-state-dependent; interpreter is stateless |
| `confirm` / `cancel` | Confirmation replies must not be rewritten; they must reach the parser as-is |
| `search_local` with open-result continuation | Two-step flow; interpreter must not merge steps |
| Any protocol other than `resume_work` | Scope; add others explicitly in later slices |
| Any multi-step or compound command | "open X and then close Y" — pass through unchanged for deterministic handling |
| Any input that the deterministic router already classifies confidently | Interpreter not called at all |

---

## Exact files likely to change

**New files:**
- `input/input_interpreter.py` — `InputInterpreter` class, `InterpretedInput` dataclass, prompt template, API call, output parsing, entity grounding check, fallback logic, confidence threshold constant.

**Existing files with targeted edits:**
- `interaction/interaction_manager.py` — call `InputInterpreter.interpret()` before `route_interaction()` for non-confident inputs; pass `interpreted.normalized_text` downstream when `confidence >= 0.70` and `skipped == False`; enforce hard safety boundary checks; attach full interpreter trace to `debug_trace`; skip entirely when interpreter is disabled.
- `input/voice_normalization.py` — optional: expose the cleaned normalized text to the interpreter so it isn't duplicating the wake-word stripping work.

**Likely unchanged:**
- `interaction/interaction_router.py` — routing logic unchanged; receives a cleaner string.
- `parser/command_parser.py` — parser logic unchanged; receives a cleaner string.
- `protocols/registry.py` — trigger matching unchanged; interpreter produces canonical trigger text so exact matching still works.
- `clarification/clarification_handler.py` — unchanged.
- `validator/command_validator.py` — unchanged.
- `runtime/runtime_manager.py` — unchanged.
- `desktop/` — unchanged; interpreter is invisible above the facade boundary.

---

## Acceptance criteria for a first slice

A first slice is complete when all of the following hold.

**Functional:**
1. `"resume my work"` → normalized to `"resume work"` → `resume_work` protocol fires correctly.
2. `"let's get back to the project"` → normalized to `"resume work"` → same result.
3. `"pick up where I left off"` → normalized to `"resume work"` → same result.
4. `"start working on JARVIS"` → normalized to `"start work on JARVIS"` → `prepare_workspace` path with VS Code fires correctly.
5. `"pull up VS Code with the JARVIS folder"` → normalized to `"start work on JARVIS"` → same result.
6. `"open my notes app"` → normalized to `"open Notes"` → existing `open_app` path fires.
7. An unambiguous input (`"open Safari"`) bypasses the interpreter entirely; deterministic path unchanged; `skipped=True`, `skip_reason="deterministic_match"` in trace.
8. Any input that today correctly routes and parses still routes and parses identically.

**Safety — hard boundary enforcement:**
9. `"how does resume work work?"` → interpreter does not fire `resume_work`; routes to question mode; command never executes.
10. `"open something"` → `entity_hints` contains no invented app name; downstream clarification fires as normal.
11. `"I'm not sure what I want"` → `routing_hint = "unclear"`, original text passes through, clarification or fallback-command fires as normal.
12. `"close everything"` → passes through unchanged; deterministic failure path fires; no invented target.
13. Disabling the interpreter via `JARVIS_INTERPRETER_DISABLED=1` produces bit-for-bit identical output to today's pipeline.
14. A simulated API failure results in the original input reaching the router unchanged; `skipped=True`; the user sees no error.
15. Confirmation and clarification boundaries are identical with the interpreter enabled or disabled.
16. Entity grounding check: any `entity_hints` value that does not appear in the raw input (as substring or known alias) is stripped before passing downstream, verified by unit test.

**Visibility:**
17. With `JARVIS_QA_DEBUG=1`, the debug trace includes `"interpreter_result"` with all fields defined in the structured output section, including `raw_input_seen`, `normalized_text_used`, `skip_reason`, and `latency_ms`.
18. Three-value comparison (`raw_input_seen`, `normalized_text`, `routed_input`) is verifiable from the trace alone; no additional logging needed.

**Tests:**
19. Unit tests for `InputInterpreter` cover: successful normalization with confidence ≥ 0.70, API timeout fallback (`skip_reason="timeout"`), malformed JSON fallback (`skip_reason="malformed_response"`), disabled-flag bypass (`skip_reason="disabled"`), low-confidence suppression (`skip_reason="low_confidence"`), question-to-command conflict rejection (`skip_reason="question_command_conflict"`), entity grounding strip.
20. Integration smoke tests verify criteria 1–6 end-to-end with mocked API responses (no live API call in CI).
21. Regression tests assert that the 8 forbidden examples in the rewrite policy produce either `skipped=True` or the correct safe output.

---

## Design constraints

- The prompt sent to the LLM must be **narrow and task-specific**: normalize this spoken/typed input for a voice-first desktop assistant that supports a fixed set of intents. Include only the v1 supported intent list. Do not let the LLM invent new intents.
- The LLM response must be **structured JSON** with a fixed schema. If it is not valid JSON matching the schema → `skipped=True`, `skip_reason="malformed_response"`.
- The prompt must include an explicit **non-execution constraint**: "Do not produce any action, command, or executable output. Return only a JSON normalization object. Do not resolve ambiguous entities."
- The interpreter must be **stateless**: no session context, no protocol state, no file system access. It sees only the one current input string and the fixed intent/entity vocabulary.
- Use **prompt caching** on the system prompt and intent vocabulary section to keep latency and cost low on repeated calls.
- The first slice targets English and Russian inputs only, matching the existing voice normalization scope.
- The confidence threshold (`0.70`) and the max-length guard (3× input length) are named constants, not magic numbers.
