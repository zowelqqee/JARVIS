# JARVIS Question-Answer Mode

## Purpose
Define the read-only question-answer mode that lets JARVIS answer user questions without executing desktop actions.

Current interactive CLI state:
- grounded local answers remain the default path for docs/runtime/session/repo questions
- plain `python3 cli.py` now bootstraps hybrid question defaults, so open-domain questions can use the model path when the provider is available
- command mode remains separate and deterministic

Planned expansion direction:
- broader GPT-backed answers under the same top-level `question` mode across wider rollout stages, not only the local interactive CLI bootstrap
- still read-only
- still separate from `command`
- still subject to explicit provenance and safety boundaries

General-QA product policy lives in `docs/general_qa_policy.md`.

Question-answer mode is an interaction mode parallel to command mode.
It must not weaken the existing command safety model.

## Mode Definition
JARVIS operates in two top-level interaction modes:
- `command`: parse, validate, plan, and execute a supervised desktop action.
- `question`: answer either:
  - a grounded local question about capabilities, current runtime state, documented behavior, or repository structure
  - or, in a later staged rollout, a broader GPT-backed question that remains read-only and provenance-labeled

Strict rule:
- `Command` remains an execution-only contract.
- Question handling must not be represented as a `Command` intent.
- Question handling must not create `execution_steps`.
- Answering a question must not trigger desktop execution.

## Goals
Current shipped goals:
- what JARVIS can do
- what JARVIS is doing now
- how JARVIS works
- where key runtime pieces live in the repo
- why a command is blocked or requires confirmation

Planned expansion goals:
- answer broader user questions through GPT without crossing into execution
- keep grounded local answers and model-knowledge answers visibly distinct
- preserve routing and command safety invariants while broadening question coverage

## Non-Goals
Question-answer mode is not:
- a hidden execution or planning mode
- an approval bypass for blocked commands
- a way to execute actions indirectly through phrasing
- an internet-backed search system by default
- a source of fake local citations for model-knowledge answers
- a persistent memory system or hidden personalization layer

Current shipped v1 still does not support open-domain general knowledge answers by default.

## Routing Rules
Interaction routing must apply this order:
1. blocked confirmation reply forms for an active blocked command
2. blocked clarification reply forms for an active blocked command
3. explicit command requests
4. explicit question requests
5. mixed or unclear command/question requests -> clarification

Routing rules:
- If the system is waiting for confirmation, explicit confirmation semantics win.
- If the system is waiting for clarification, clarification semantics win.
- A polite command is still a command if the requested outcome is execution.
- A question about how to do something is a question if no execution is requested.
- A mixed request must not answer and execute in one silent pass.
- A later general-QA expansion may widen what happens inside question mode, but it must not change top-level routing precedence.

Examples:
- "Open Safari." -> `command`
- "Can you open Safari?" -> `command`
- "How do you open Safari?" -> `question`
- "What can you do and open Safari." -> clarification

## Supported Question Families (v1)
Question-answer mode is read-only and grounded.

Supported families:
- `blocked_state`: what JARVIS is waiting on, what input is needed, and what must be confirmed or clarified
- `recent_runtime`: the most recent visible command, target, app/file, or workspace context
- `capabilities`: supported actions, limits, and non-goals
- `runtime_status`: current visible state, blocked reason, current command, completed steps
- `docs_rules`: clarification, confirmation, safety, validation, runtime behavior
- `repo_structure`: where components and files live in the repo
- `safety_explanations`: why execution is blocked, why confirmation is required, why unsupported behavior stays unsupported

Supported safe answer follow-ups in the current session:
- `Explain more`
- `Which source?`
- `Where is that written?`
- `Why?`

These follow-ups are allowed only when they clearly refer to the most recent grounded answer.
They must reuse the recent answer topic/scope/source bundle and must not become hidden execution.

Unsupported in v1:
- open-ended world knowledge
- internet lookups
- arbitrary codebase Q&A outside documented/runtime-grounded scope
- autonomous answer-then-execute behavior

## Planned General QA Expansion
A later expansion may let JARVIS answer broader open-domain questions through GPT under the same `question` mode.

That expansion must keep these invariants:
- command routing precedence stays unchanged
- mixed question + action stays clarification-first
- grounded local answers stay grounded and source-backed
- broader model-backed answers stay explicitly labeled as model-knowledge answers
- no broader answer path may create hidden execution, hidden browsing, or fake local grounding

## Grounding Sources
Grounding rules below apply to the grounded local answer path.
Broader model-backed answers must not fabricate local `sources` or local support claims.

Allowed sources:
- repository documentation under `docs/`
- capability catalog or equivalent fixed runtime metadata
- active session context
- recent grounded answer context from the same session (`recent_answer_topic`, `recent_answer_scope`, `recent_answer_sources`)
- current visible runtime state
- current command summary, blocked reason, and completed visible steps

Grounding selection rule:
- source selection should run through one explicit registry/selector layer
- docs grounding should prefer section-aware support claims, not only bare file paths
- runtime grounding should distinguish runtime visibility, session context, and docs support when multiple kinds are used

Not allowed:
- hidden assumptions about capabilities not present in code/docs
- unstated long-term user memory
- silent external lookups
- fabricated sources
- answer follow-up chaining that introduces new execution or new hidden source selection

## Backend Strategy
Question-answer mode should be built around one stable `Answer Engine` contract with replaceable internal backends.

Recommended shape:
- default v1 backend: deterministic, rules/templates plus explicit source selection
- opt-in model-backed backend: `llm` behind the same answer-engine seam, not the default product path
- backend config should stay externalized so backend kind, provider, and model can be changed without touching routing code
- grounding should be assembled into an explicit source bundle before any backend generates answer text
- a later general-QA expansion may add an open-domain model-answer path behind the same `Answer Engine` seam, but it must remain visibly distinct from grounded local answering

Hard rules:
- routing into `question` vs `command` must happen before backend selection
- source selection and grounding policy must happen before answer generation
- source selection should be explainable through a topic-aware source registry / selector seam
- backend choice must not change safety policy
- no backend may create `Command` objects or `execution_steps`
- no backend may approve confirmation or resume blocked execution

Future-ready rule:
- a later LLM backend may use an external model API such as OpenAI Responses API, but only behind the `Answer Engine` seam
- the current opt-in OpenAI Responses path keeps deterministic as the default backend and uses `gpt-5-nano` as the default small-model setting
- the selected model must stay configurable, so a lower-latency model can be swapped without changing routing or visibility contracts
- the LLM backend should receive explicit source bundles and answer instructions, not raw unrestricted authority over the session
- prompt/instructions building, schema building, and structured response parsing should stay behind explicit seams instead of living inline in one provider method
- source-attribution parsing and groundedness verification should live in a shared verifier layer, not inside one provider implementation
- provider-specific request construction should live behind a provider seam such as an OpenAI Responses adapter
- transport concerns should live behind a provider transport adapter, not inside routing or CLI
- provider settings should stay externalized and include model, timeout, max output tokens, reasoning effort, strict mode, retry policy, and fallback mode
- retries must be limited to transient transport/provider failures such as 429/500/502/503 and network timeouts
- schema mismatch, malformed structured output, and grounding failures must fail honestly without retry loops
- if the LLM backend is unavailable or returns an ungrounded answer, the system must fall back to deterministic answering or fail honestly
- the model-backed answer payload must stay versioned; the current frozen schema version is `qa_answer_v1`
- the manual live smoke path is `scripts/run_openai_live_smoke.sh` and requires `OPENAI_API_KEY`
- the optional QA debug flag is `JARVIS_QA_DEBUG=1`; when enabled, question interactions attach structured safe debug payloads for routing decision, question classification, source selection, provider response parse, grounding verification, and deterministic fallback state
- live smoke output should print the chosen provider, chosen model, grounded source count, and whether deterministic fallback happened
- model-backed question answering must not become the default product path until the comparative gate in `docs/llm_default_decision_gate.md` passes on the shared eval corpus
- operator runbook and smoke guidance live in `docs/qa_operator_guide.md`

## Question Contract
Suggested internal request shape:

```text
QuestionRequest {
  raw_input: string,
  question_type: string,
  scope: string,
  context_refs: object,
  confidence: float (0-1),
  requires_grounding: boolean
}
```

Field intent:
- `question_type`: one of the supported question families.
- `scope`: answer scope such as `capabilities`, `runtime`, `docs`, or `repo_structure`.
- `context_refs`: structured pointers to runtime state or explicit source files.
- `confidence`: routing/classification confidence.
- `requires_grounding`: whether answer must cite source-backed support before being returned.

Note:
- the current shape reflects grounded-local question handling
- a later phase may add explicit question classes for broader open-domain GPT answers without changing the top-level `question` mode

## Answer Contract
Suggested internal answer shape:

```text
AnswerResult {
  interaction_mode: "question",
  answer_text: string,
  answer_kind: "grounded_local" | "open_domain_model" | "refusal",
  provenance?: "local_sources" | "model_knowledge",
  sources: string[],
  source_attributions?: { source: string, support: string }[],
  confidence: float (0-1),
  warning?: string
}
```

Rules:
- `answer_text` must be concise and direct.
- `answer_kind` distinguishes grounded local answers from broader model-backed answers and refusal-style answer outputs.
- `provenance` must truthfully describe whether the answer came from local sources or model knowledge.
- `sources` should name the source files or structured runtime source used for grounded local answers.
- `source_attributions` should explain which source supports which part of the answer when that detail is available.
- model-backed answers must pass shared groundedness verification against the allowed source bundle before they can be returned.
- model-backed `source_attributions` must be claim-bearing and specific; generic placeholders or bare file paths are not sufficient support text.
- `warning` is optional and used for partial context or bounded uncertainty.
- No answer may imply that an action has already run unless command runtime visibility proves it.

## Answer Rules
- Grounded local answers must answer only from grounded sources.
- Grounded local answers should prefer the smallest source set that fully supports the answer.
- Cite sources when answering from docs or repo structure.
- If runtime state is the source, say so directly.
- If grounding is insufficient, return a bounded failure instead of guessing.
- A future broader model-backed answer path must stay read-only, must not fabricate local citations, and must be clearly marked as model knowledge rather than local grounding.
- If the request is really an action, route to command mode instead of answering.
- If the request mixes action and question, ask one short clarification.

## Failure Rules
Question-answer mode must fail honestly when:
- the question is outside supported scope
- the needed source is unavailable
- the answer cannot be grounded confidently
- current runtime/session context is insufficient for the requested status answer

Failure behavior:
- do not guess
- do not execute anything
- state the boundary clearly
- suggest the narrowest next user action when useful
- if a safe answer follow-up has no recent grounded answer context, fail with bounded insufficient-context output

Current shipped behavior:
- questions outside grounded local scope still fail honestly
- broader GPT answering is not the default shipped path yet

## Visibility Rules
Question-answer mode should expose:
- `interaction_mode = question`
- `answer_summary` for concise CLI/speech rendering
- `answer_text`
- `answer_kind`
- `answer_provenance`
- human-readable source labels plus raw `sources` when grounded from docs or structured runtime data
- `warning` when answer is partial or bounded
- broader model-backed answers should expose truthful provenance instead of fake local source fields

Question-answer mode must not expose:
- fake execution progress
- command steps for non-command inputs
- confirmation state unless a blocked command is actually active

## Examples
### Capability Question
User: "What can you do?"
- Route: `question`
- Source: capability catalog and product/docs rules
- Output: concise supported action list and key limits

### Runtime Status Question
User: "What are you waiting for?"
- Route: `question`
- Source: current blocked runtime state
- Output: current blocked reason and what input is needed

### Documentation Question
User: "How does clarification work?"
- Route: `question`
- Source: `docs/clarification_rules.md`, `docs/runtime_flow.md`
- Output: concise explanation with sources

### Mixed Request
User: "What can you do and open Safari"
- Route: clarification
- Output: one short question asking whether to answer or execute

### Planned Future General Question
User: "Why is the sky blue?"
- Route: `question`
- Source: planned broader GPT-backed question path, not local docs/runtime grounding
- Output: concise read-only answer with truthful provenance labeling once that expansion ships
