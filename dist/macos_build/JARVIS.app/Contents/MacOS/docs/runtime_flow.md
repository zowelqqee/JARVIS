# JARVIS Runtime Flow (Dual-Mode MVP)

## Purpose
Define the end-to-end supervised interaction loop from user input to visible completion, failure, clarification, confirmation boundary, or grounded answer.

## Interaction Stages
### 1. Input intake
- Input: user text input, or voice input converted to text first.
- Output: `raw_input` string.
- Blocking conditions: empty input.
- Next transition: `route interaction`.

### 2. Route interaction
- Input: `raw_input`, optional active blocked-state context, optional session context.
- Output: routed interaction (`command`, `question`, or clarification requirement).
- Blocking conditions: mixed request or unresolved routing ambiguity.
- Next transition: `command branch`, `question branch`, or `clarify if needed`.

### 3. Command branch: parse command
- Input: routed command input, optional active session context.
- Output: preliminary `Command`.
- Blocking conditions: parse fails or intent unresolved.
- Next transition: `validate command` or `clarify if needed`.

### 4. Command branch: validate command
- Input: preliminary `Command`.
- Output: validated `Command` or clarification requirement.
- Blocking conditions: low confidence, ambiguity, missing required parameters, unresolved target, unknown intent.
- Next transition: `build execution plan` or `clarify if needed`.

### 5. Clarify if needed
- Input: clarification requirement and current blocked interaction state.
- Output: updated command fields or clarified routing choice.
- Blocking conditions: user response still unclear.
- Next transition: `validate command`, `route interaction`, or cancellation.

### 6. Command branch: build execution plan
- Input: validated `Command`.
- Output: ordered `execution_steps`, `status_message`, command-level and step-level confirmation gates.
- Blocking conditions: planning cannot map intent/targets to supported steps.
- Next transition: `execute steps` or `fail`.

### 7. Command branch: execute steps
- Input: planned `Command` with `execution_steps`.
- Output: step status updates (`pending` -> `executing` -> `done`/`failed`) and runtime progress.
- Blocking conditions: step failure, runtime ambiguity, confirmation boundary reached.
- Next transition: next step, `pause on confirmation boundary`, or `complete or fail`.

### 8. Pause on confirmation boundary when required
- Input: command-level or step-level confirmation gate.
- Output: blocked runtime state plus explicit confirmation request.
- Blocking conditions: awaiting explicit user approval or denial.
- Next transition: `execute steps` on approval, `cancelled` or `failed` on denial/cancel path.

### 9. Question branch: build grounded answer
- Input: routed question input, allowed grounded sources, optional session context, visible runtime state.
- Output: `AnswerResult` or bounded answer failure.
- Blocking conditions: unsupported question scope, insufficient grounding, or missing runtime context for status question.
- Next transition: `return answer or fail`.

### 10. Return answer or complete/fail
- Output (question success): grounded answer with sources.
- Output (command complete): success result and final runtime state.
- Output (failure): explicit reason and suggested next action when available.
- Blocking conditions: none (terminal stage for the current interaction).
- Next transition: `idle` / ready for next input.

## Stage Details
### 1. Input intake
- Receive user input as text.
- If voice exists, convert to text before routing.
- Output: `raw_input` string.

### 2. Route interaction
- Determine whether input is a blocked-state reply, a fresh command, a fresh question, or an ambiguous mixed request.
- Apply deterministic precedence before any command parsing or answer generation.

### 3. Command branch: parse command
- Convert command input into a `Command` object.
- May use session context.
- Output: preliminary `Command`.

### 4. Command branch: validate command
- Apply confidence, ambiguity, target, and parameter rules.
- If invalid -> clarification or failure.
- If valid -> continue.

### 5. Clarify if needed
- Block further progress.
- Ask one minimal clarification question.
- Update blocked routing or command state from user response.
- Resume from the blocked decision point, not from scratch unless necessary.

### 6. Command branch: build execution plan
- Produce ordered `execution_steps`.
- Attach `status_message`.
- Determine command-level and step-level confirmation gates.

### 7. Command branch: execute steps
- Run sequentially.
- Update visible step status.
- Stop on failure, ambiguity, or confirmation boundary.

### 8. Pause on confirmation boundary
- Preserve command runtime state.
- Request explicit user approval.
- Resume only after explicit user input.

### 9. Question branch: build grounded answer
- Classify the supported question family.
- Select the minimal grounded source set.
- Build a read-only answer.
- Return bounded failure instead of guessing when grounding is missing.

### 10. Return answer or complete/fail
- Question success: report answer and sources.
- Command complete: report success and final state.
- Failure: report exact reason and suggested next action when useful.

## Command Runtime State Model
The existing runtime state model remains command-specific.
Question-answer mode does not create command execution steps and does not use command execution states as if work were running.

### idle
- Entered when no active command exists.
- Allowed transitions: `parsing`.

### parsing
- Entered after routed command intake begins command handling.
- Allowed transitions: `validating`, `awaiting_clarification`, `failed`.

### validating
- Entered after preliminary `Command` is produced.
- Allowed transitions: `planning`, `awaiting_clarification`, `failed`.

### awaiting_clarification
- Entered when routing, validation, or runtime requires clarification.
- Allowed transitions: `validating`, `cancelled`.

### planning
- Entered after command is validated.
- Allowed transitions: `executing`, `failed`.

### executing
- Entered when step execution starts.
- Allowed transitions: `executing` (next step), `awaiting_confirmation`, `completed`, `failed`, `awaiting_clarification`, `cancelled`.

### awaiting_confirmation
- Entered at command-level or step-level confirmation gate.
- Allowed transitions: `executing`, `cancelled`, `failed`.

### completed
- Entered when all steps finish successfully.
- Allowed transitions: `idle`.

### failed
- Entered when any terminal runtime failure occurs.
- Allowed transitions: `idle`.

### cancelled
- Entered when user cancels active command flow.
- Allowed transitions: `idle`.

## Interaction Invariants
- blocked confirmation/clarification replies outrank fresh routing
- only one active command at a time
- only one active step at a time
- no execution without validated command
- no execution through ambiguity
- no silent state transitions
- no answer may imply command execution occurred when it did not
- no question answer may auto-resume blocked execution
- no execution outside visible command runtime flow

## Resume Rules
After command clarification:
- preserve current command and completed steps
- update only blocked fields
- resume at the blocked command decision point

After command confirmation:
- preserve current command and completed steps
- resume from the blocked command/step boundary

After interaction-routing clarification:
- preserve only the information needed to choose command vs question
- do not silently execute after an answer-oriented clarification unless command intent becomes explicit

General rule:
- do not restart full command flow unless command structure changed materially
- do not convert a question answer into command execution without explicit routed command input

## Cancellation Rules
- user may cancel an active command at any point
- cancellation stops active execution immediately
- completed steps remain recorded in current runtime state
- no further steps run after cancellation
- no implicit resume after cancellation

## User Visibility Rules
Visible information must include either:
- command runtime state, command summary, current step, completed steps, blocked/failure reason, or
- question answer text, sources, and answer warning when applicable

No silent execution or invisible answer-source substitution is allowed.

## Constraints
- No background continuation
- No hidden retries
- No multi-command execution
- No autonomous branching
- No invisible mutation of command scope
- No hidden answer-triggered action
