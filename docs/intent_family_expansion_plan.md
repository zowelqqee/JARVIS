# Intent Family Expansion Plan

## Goal

Expand input coverage for existing high-frequency intent families so that semantically
adjacent and mixed-language phrasing maps reliably into the current deterministic pipeline.
No new protocols. No new intents. No NLP infrastructure.

The product should understand an intent family — not memorize one phrase.

---

## Current Failures

| Input | Expected result | Actual result |
|---|---|---|
| `prepare JARVIS workspace` | `prepare_workspace` | falls through to question or parse failure |
| `let's get to work` | `prepare_workspace` | treated as natural-speech question or unclear |
| `get me back to work` | `resume_work` protocol | not matched |
| `Старт work` | `prepare_workspace` | fails — mixed-script, not in near-miss patterns |
| `начни работу` | `prepare_workspace` | fails — Russian phrasing, no equivalent path |
| `продолжи работу` | `resume_work` | fails — Russian phrasing not in builtin triggers |
| `можешь продолжить работу` | `resume_work` | fails |
| `open up Telegram` | `open_app` | partially works (depends on parser's `open ` prefix detection) |

Root causes (three distinct failure modes):

1. **`resume_work` protocol trigger is English-only exact-match.** The builtin only has
   `"resume work"` (en-US). No Russian trigger exists despite the product supporting
   `ru-RU` locale throughout.

2. **`_parse_start_work_command` is a literal prefix check.** It requires the text to
   start with exactly `"start work"`. `prepare JARVIS workspace`, `get to work`, and
   anything that doesn't start with that literal prefix fails immediately.

3. **The interpreter's deterministic pre-normalization (`_CANONICAL_COMMAND_STARTERS`)
   treats `"prepare "` as already canonical** — it skips the LLM and passes the text
   through unchanged. The parser then receives `"prepare JARVIS workspace"`, which has
   no matching branch. So even the LLM rescue path is bypassed.

---

## Target Intent Families

### 1. `prepare_workspace` (start work)

Backing intent: open VS Code with an optional workspace folder.
Canonical parser input: `start work` or `start work on <workspace>`.

User intent signatures:
- "I want to start working"
- "prepare my workspace"
- "set up my environment"
- "let's get to work"
- "open VS Code and get started"

Russian-language user intent signatures:
- "начни работу" / "начинаем работать"
- "подготовь рабочее пространство"
- "открой VS Code"

### 2. `resume_work` (run_protocol: resume_work)

Backing intent: run the `resume_work` builtin protocol (exact trigger match required by registry).
Canonical input: exactly `"resume work"`.

User intent signatures:
- "get back to work"
- "pick up where I left off"
- "continue my work"
- "let's resume"
- "go back to what I was doing"

Russian-language user intent signatures:
- "продолжи работу"
- "возобновить работу"
- "вернись к работе"
- "продолжи с того места"

### 3. `open_app` (reference only)

Already has robust coverage via `_APP_ALIASES` dict and the `"open "` prefix in the parser
and router. Included here only as a comparison point to confirm the approach is consistent.
No changes needed for this family.

---

## V1 Phrase Whitelist

This is the binding list of phrases v1 will support. Anything not in this table is not
supported. LLM-assisted entries are best-effort and not individually tested; deterministic
entries are tested and guaranteed.

### `prepare_workspace`

**Deterministic (parser + pre-normalization — tested, guaranteed)**

| Exact phrase | Route | Status | Observed failure? |
|---|---|---|---|
| `start work` | parser: `_parse_start_work_command` | existing | — |
| `start work on <workspace>` | parser: `_parse_start_work_command` | existing | — |
| `prepare workspace` | parser: new branch | **new** | not directly observed, but adjacent to observed failure |
| `prepare <workspace> workspace` | parser: new branch | **new** | yes — `prepare JARVIS workspace` |
| `set up workspace` | parser: new branch | **new** | not directly observed |
| `начни работу` | pre-norm → `start work` | **new** | yes — observed |
| `начать работу` | pre-norm → `start work` | **new** | plausible conjugate of observed |
| `подготовь рабочее пространство` | pre-norm → `start work` | **new** | yes — observed |
| `Старт work` | near-miss pattern extension | **new** | yes — observed |
| `Старт work on <workspace>` | near-miss pattern extension | **new** | yes — observed variant |

**LLM-assisted (best-effort, not individually tested)**

| Phrase | Notes |
|---|---|
| `get to work` | `_NATURAL_SPEECH_MARKERS` triggers LLM; LLM system prompt covers it |
| `let's get to work` | same — `let's` is in natural speech marker list |
| `prepare my workspace` | `my ` is in natural speech marker list — reaches LLM |
| `set up my workspace` | `my ` triggers LLM |

### `resume_work`

**Deterministic (protocol trigger + pre-normalization — tested, guaranteed)**

| Exact phrase | Route | Status | Observed failure? |
|---|---|---|---|
| `resume work` | protocol trigger (en-US exact) | existing | — |
| `продолжи работу` | protocol trigger (ru-RU exact) + pre-norm fallback | **new** | yes — observed |
| `возобновить работу` | protocol trigger (ru-RU exact) + pre-norm fallback | **new** | yes — observed |
| `вернись к работе` | pre-norm → `resume work` | **new** | plausible conjugate of observed |

**LLM-assisted (best-effort, not individually tested)**

| Phrase | Notes |
|---|---|
| `get back to work` | natural speech markers trigger LLM; system prompt covers it |
| `continue working` | same |

### Explicitly Excluded Variants

The following phrasings are NOT supported in v1. They are listed because they are tempting
extensions that were considered and rejected.

| Excluded phrase | Family | Reason for exclusion |
|---|---|---|
| `начинаем работать` | prepare_workspace | Conjugated plural form — low real frequency, adds regex complexity |
| `set up my environment` | prepare_workspace | "environment" is ambiguous — doesn't map cleanly to workspace intent |
| `open VS Code` | prepare_workspace | Routes to `open_app`, not `prepare_workspace` — different intent |
| `let's start working` | prepare_workspace | LLM-path only; conjugation makes deterministic matching fragile |
| `get me back to work` | ambiguous | Ambiguous between start and resume — excluded to avoid wrong routing |
| `let's resume` | resume_work | "resume" alone without "work" is too short and ambiguous |
| `pick up where I left off` | resume_work | Too verbose for a deterministic rule; LLM reliability uncertain |
| `go back to what I was doing` | resume_work | Too verbose and idiomatic for reliable normalization |
| `можешь продолжить работу` | resume_work | Polite Russian form — one observed instance is insufficient to justify a deterministic rule |
| `продолжи с того места` | resume_work | Verbose, low frequency — not observed in actual usage |
| `поехали` / `приступим` | prepare_workspace | Too idiomatic, single-word — too much collision risk with unrelated input |
| `continue my project` | resume_work | "project" entity requires resolution — outside scope |

---

## Mixed-Language Handling

Three forms appear in practice. Only the first two are in scope for v1.

**Form 1 — Cyrillic first word, English second word** (observed: `"Старт work"`):
Extend existing `_HERO_NEAR_MISS_START_T1` regex to match Cyrillic `Старт` as a leading
word variant. Result: `"start work"`. Also cover `"Старт work on <workspace>"` → `"start work on <workspace>"`.
No LLM. Deterministic only.

In scope: `Старт work`, `Старт work on <workspace>`.
Not in scope: `Старт wrk`, `Резюме work`, or any other Cyrillic+English combination not
in the whitelist above.

**Form 2 — Full Russian phrasing** (observed: `"продолжи работу"`, `"начни работу"`):
Handled by two mechanisms:
- Protocol trigger (ru-RU exact): for `продолжи работу`, `возобновить работу`.
- Deterministic pre-normalization rule: for all other Russian phrases in the whitelist
  above, before the LLM call.

**Form 3 — Latin-script near-miss of Russian phonetics** (e.g. `"rezume work"`):
Already handled by existing `_HERO_NEAR_MISS_RESUME_T1` patterns. No change needed.

---

## Normalization Strategy

The pipeline has three interception points, in priority order:

```
raw_input
    │
    ▼
[1] input_interpreter.py — deterministic pre-normalization rules (before LLM call)
    │   Fix 3 / near-miss patterns already live here.
    │   New: Russian synonym rules for prepare_workspace and resume_work.
    │   New: Cyrillic "Старт" extension in near-miss patterns.
    │
    ▼
[2] input_interpreter.py — LLM normalization call (skipped if deterministic match)
    │   System prompt already covers English natural-speech forms.
    │   New: Add Russian-language examples to the system prompt intent table.
    │
    ▼
[3] parser/command_parser.py — command parsing
        _parse_start_work_command: extend from literal prefix to cover
        "prepare workspace", "set up workspace" as aliases that call
        _build_start_work_command directly.
```

**Point 1 is preferred** for Russian phrasing — zero latency, fully auditable, testable
without API calls.

**Point 2 (LLM)** already handles English natural-speech variants. Add Russian examples to
the system prompt's intent table so the LLM normalizes them correctly when reached.

**Point 3 (parser)** needs one small fix: the parser currently only enters the
`prepare_workspace` branch from `_parse_start_work_command` (literal `"start work"` prefix).
Add two more parser starters: `"prepare workspace"` and `"set up workspace"`, each calling
`_build_start_work_command` with the workspace extracted from the suffix.

**Protocol triggers** (builtin_protocols.py): Add Russian-locale exact triggers for
`resume_work` for the two most stable phrases (`"продолжи работу"`, `"возобновить работу"`).
These map directly through the registry without any interpreter involvement.

---

## Files To Change

| File | Change |
|---|---|
| `input/input_interpreter.py` | Add deterministic pre-normalization rules for Russian `prepare_workspace` and `resume_work` synonyms. Extend `_HERO_NEAR_MISS_START_T1` to also match Cyrillic `Старт`. Add Russian-locale examples to `_SYSTEM_PROMPT` intent table. |
| `parser/command_parser.py` | Add `"prepare workspace"` and `"set up workspace"` as starter branches in `_infer_command`, calling `_build_start_work_command`. Remove `"prepare "` from `_CANONICAL_COMMAND_STARTERS` in `input_interpreter.py` if it is causing LLM bypass for unhandled variants. |
| `protocols/builtin_protocols.py` | Add `ProtocolTrigger(type="exact", phrase="продолжи работу", locale="ru-RU")` and one more stable Russian synonym to `resume_work`. |
| `tests/test_input_interpreter.py` | Add tests for Russian pre-normalization rules and Cyrillic near-miss extension. |
| `tests/test_parser_validator_contract.py` | Add tests for `"prepare workspace"` and `"set up workspace"` parsing to `prepare_workspace`. |
| `tests/test_protocol_registry.py` | Add test asserting Russian triggers match `resume_work`. |

No changes to: `interaction_router.py`, `runtime_manager.py`, `clarification_handler.py`,
`validator/`, `planner/`, `executor/`.

---

## Out Of Scope

- Any phrase not in the V1 Phrase Whitelist above, including all entries in "Explicitly Excluded Variants"
- Broad Russian NLP or intent classification
- Any new intents or protocols
- Implicit reference resolution ("that", "it", "this")
- Arbitrary conjugation or dialect variants beyond the exact whitelisted phrases
- Semantic similarity / embedding-based matching
- Any change to the deterministic runtime state machine
- Weakening confirmation or safety boundaries
- Russian phrasing for any intent other than `prepare_workspace` and `resume_work`
- Mixed-language phrasing for `open_app`, `close_app`, or any other intent
- User-configurable synonym lists
- Expanding the LLM system prompt beyond adding the whitelisted Russian phrases as examples

---

## Acceptance Criteria

The following deterministic entries must reach the correct intent without error,
confirmation, or clarification being triggered. Each must have a passing unit test.
LLM-assisted entries are not individually tested.

| Input | Route | Expected outcome |
|---|---|---|
| `prepare workspace` | parser: new branch | `prepare_workspace`, no workspace target |
| `prepare JARVIS workspace` | parser: new branch | `prepare_workspace`, workspace=JARVIS |
| `set up workspace` | parser: new branch | `prepare_workspace`, no workspace target |
| `начни работу` | pre-norm → `"start work"` → parser | `prepare_workspace` |
| `начать работу` | pre-norm → `"start work"` → parser | `prepare_workspace` |
| `подготовь рабочее пространство` | pre-norm → `"start work"` → parser | `prepare_workspace` |
| `Старт work` | near-miss pattern → `"start work"` → parser | `prepare_workspace` |
| `Старт work on JARVIS` | near-miss pattern → `"start work on JARVIS"` → parser | `prepare_workspace`, workspace=JARVIS |
| `продолжи работу` | protocol trigger (ru-RU) | `resume_work` protocol |
| `возобновить работу` | protocol trigger (ru-RU) | `resume_work` protocol |
| `вернись к работе` | pre-norm → `"resume work"` → protocol trigger | `resume_work` protocol |

All existing tests must continue to pass. No new runtime states. No new clarification
scenarios introduced for any whitelisted phrase.
