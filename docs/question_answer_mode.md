# JARVIS Question-Answer Mode (MVP)

## Purpose
Define the read-only question-answer mode that lets JARVIS answer grounded user questions without executing desktop actions.

Question-answer mode is an interaction mode parallel to command mode.
It must not weaken the existing command safety model.

## Mode Definition
JARVIS operates in two top-level interaction modes:
- `command`: parse, validate, plan, and execute a supervised desktop action.
- `question`: answer a grounded question about capabilities, current runtime state, documented behavior, or repository structure.

Strict rule:
- `Command` remains an execution-only contract.
- Question handling must not be represented as a `Command` intent.
- Question handling must not create `execution_steps`.
- Answering a question must not trigger desktop execution.

## Goals
Question-answer mode exists to answer:
- what JARVIS can do
- what JARVIS is doing now
- how JARVIS works
- where key runtime pieces live in the repo
- why a command is blocked or requires confirmation

## Non-Goals
Question-answer mode is not:
- a general-purpose knowledge assistant
- an internet-backed search system
- a hidden planning mode
- an approval bypass for blocked commands
- a way to execute actions indirectly through phrasing

## Routing Rules
Interaction routing must apply this order:
1. blocked confirmation reply forms for an active blocked command
2. blocked clarification reply forms for an active blocked command
3. explicit command requests
4. explicit grounded question requests
5. mixed or unclear command/question requests -> clarification

Routing rules:
- If the system is waiting for confirmation, explicit confirmation semantics win.
- If the system is waiting for clarification, clarification semantics win.
- A polite command is still a command if the requested outcome is execution.
- A question about how to do something is a question if no execution is requested.
- A mixed request must not answer and execute in one silent pass.

Examples:
- "Open Safari." -> `command`
- "Can you open Safari?" -> `command`
- "How do you open Safari?" -> `question`
- "What can you do and open Safari." -> clarification

## Supported Question Families (v1)
Question-answer mode is read-only and grounded.

Supported families:
- `capabilities`: supported actions, limits, and non-goals
- `runtime_status`: current visible state, blocked reason, current command, completed steps
- `docs_rules`: clarification, confirmation, safety, validation, runtime behavior
- `repo_structure`: where components and files live in the repo
- `safety_explanations`: why execution is blocked, why confirmation is required, why unsupported behavior stays unsupported

Unsupported in v1:
- open-ended world knowledge
- internet lookups
- arbitrary codebase Q&A outside documented/runtime-grounded scope
- autonomous answer-then-execute behavior

## Grounding Sources
Question-answer mode may use only explicit grounded sources.

Allowed sources:
- repository documentation under `docs/`
- capability catalog or equivalent fixed runtime metadata
- active session context
- current visible runtime state
- current command summary, blocked reason, and completed visible steps

Not allowed:
- hidden assumptions about capabilities not present in code/docs
- unstated long-term user memory
- silent external lookups
- fabricated sources

## Backend Strategy
Question-answer mode should be built around one stable `Answer Engine` contract with replaceable internal backends.

Recommended shape:
- v1 backend: deterministic, rules/templates plus explicit source selection
- future backend: model-backed `llm` backend for more flexible answer wording and synthesis

Hard rules:
- routing into `question` vs `command` must happen before backend selection
- source selection and grounding policy must happen before answer generation
- backend choice must not change safety policy
- no backend may create `Command` objects or `execution_steps`
- no backend may approve confirmation or resume blocked execution

Future-ready rule:
- a later LLM backend may use an external model API such as OpenAI Responses API, but only behind the `Answer Engine` seam
- the selected model must stay configurable, so a lower-latency model can be swapped without changing routing or visibility contracts
- the LLM backend should receive explicit source bundles and answer instructions, not raw unrestricted authority over the session
- if the LLM backend is unavailable or returns an ungrounded answer, the system must fall back to deterministic answering or fail honestly

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

## Answer Contract
Suggested internal answer shape:

```text
AnswerResult {
  interaction_mode: "question",
  answer_text: string,
  sources: string[],
  confidence: float (0-1),
  warning?: string
}
```

Rules:
- `answer_text` must be concise and direct.
- `sources` should name the source files or structured runtime source used.
- `warning` is optional and used for partial context or bounded uncertainty.
- No answer may imply that an action has already run unless command runtime visibility proves it.

## Answer Rules
- Answer only from grounded sources.
- Prefer the smallest source set that fully supports the answer.
- Cite sources when answering from docs or repo structure.
- If runtime state is the source, say so directly.
- If grounding is insufficient, return a bounded failure instead of guessing.
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

## Visibility Rules
Question-answer mode should expose:
- `interaction_mode = question`
- `answer_text`
- `sources` when grounded from docs or structured runtime data
- `warning` when answer is partial or bounded

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
