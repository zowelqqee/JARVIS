# JARVIS Runtime Flow (MVP)

## Purpose
Define the end-to-end supervised runtime loop from user input to visible completion, failure, clarification, or confirmation boundary.

## Runtime Stages
### 1. Input intake
- Input: user text input, or voice input converted to text first.
- Output: `raw_input` string.
- Blocking conditions: empty input.
- Next transition: `parse command`.

### 2. Parse command
- Input: `raw_input`, optional active session context.
- Output: preliminary `Command`.
- Blocking conditions: parse fails or intent unresolved.
- Next transition: `validate command` or `clarify if needed`.

### 3. Validate command
- Input: preliminary `Command`.
- Output: validated `Command` or clarification requirement.
- Blocking conditions: low confidence, ambiguity, missing required parameters, unresolved target, unknown intent.
- Next transition: `build execution plan` or `clarify if needed`.

### 4. Clarify if needed
- Input: clarification requirement and current blocked `Command`.
- Output: updated command fields from user response.
- Blocking conditions: user response still unclear.
- Next transition: `validate command` (resume from validation).

### 5. Build execution plan
- Input: validated `Command`.
- Output: ordered `execution_steps`, `status_message`, command-level and step-level confirmation gates.
- Blocking conditions: planning cannot map intent/targets to supported steps.
- Next transition: `execute steps` or `fail`.

### 6. Execute steps
- Input: planned `Command` with `execution_steps`.
- Output: step status updates (`pending` -> `executing` -> `done`/`failed`) and runtime progress.
- Blocking conditions: step failure, runtime ambiguity, confirmation boundary reached.
- Next transition: next step, `pause on confirmation boundary`, or `complete or fail`.

### 7. Pause on confirmation boundary when required
- Input: command-level or step-level confirmation gate.
- Output: blocked runtime state plus explicit confirmation request.
- Blocking conditions: awaiting explicit user approval or denial.
- Next transition: `execute steps` on approval, `cancelled` or `failed` on denial/cancel path.

### 8. Complete or fail
- Input: final step outcome or terminal error.
- Output (complete): success result and final runtime state.
- Output (fail): failed step id, reason, suggested next action.
- Blocking conditions: none (terminal stage).
- Next transition: `idle`.

## Stage Details
### 1. Input intake
- Receive user input as text.
- If voice exists, convert to text before runtime flow.
- Output: `raw_input` string.

### 2. Parse command
- Convert raw input into a `Command` object.
- May use session context.
- Output: preliminary `Command`.

### 3. Validate command
- Apply confidence, ambiguity, target, and parameter rules.
- If invalid -> clarification.
- If valid -> continue.

### 4. Clarify if needed
- Block execution.
- Ask one minimal clarification question.
- Update command from user response.
- Resume from validation, not from scratch unless necessary.

### 5. Build execution plan
- Produce ordered `execution_steps`.
- Attach `status_message`.
- Determine command-level and step-level confirmation gates.

### 6. Execute steps
- Run sequentially.
- Update visible step status.
- Stop on failure, ambiguity, or confirmation boundary.

### 7. Pause on confirmation boundary
- Preserve runtime state.
- Request explicit user approval.
- Resume only after explicit user input.

### 8. Complete or fail
- Complete: report success and final state.
- Fail: report exact failed step, reason, and suggested next action.

## Runtime State Model
### idle
- Entered when no active command exists.
- Allowed transitions: `parsing`.

### parsing
- Entered after input intake begins command handling.
- Allowed transitions: `validating`, `awaiting_clarification`, `failed`.

### validating
- Entered after preliminary `Command` is produced.
- Allowed transitions: `planning`, `awaiting_clarification`, `failed`.

### awaiting_clarification
- Entered when validation or runtime requires clarification.
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
- Entered when user cancels active flow.
- Allowed transitions: `idle`.

## Runtime Invariants
- only one active command at a time
- only one active step at a time
- no execution without validated command
- no execution through ambiguity
- no silent state transitions
- no auto-resume after blocked state
- no execution outside visible runtime flow

## Resume Rules
After clarification:
- preserve current command and completed steps
- update only blocked fields
- resume at `validating`

After confirmation:
- preserve current command and completed steps
- resume from the blocked command/step boundary

After interruption:
- preserve current command, step index, completed steps, and block reason
- resume from blocked point after explicit user input

General rule:
- do not restart full flow unless command structure changed materially

## Cancellation Rules
- user may cancel at any point
- cancellation stops active execution immediately
- completed steps remain recorded in current runtime state
- no further steps run after cancellation
- no implicit resume after cancellation

## User Visibility Rules
Runtime-visible information must include:
- current runtime state
- current command summary
- current step
- completed steps
- blocked reason if blocked
- failure reason if failed

Runtime progress must remain visible to the user. No silent execution or invisible state mutation is allowed.

## Constraints
- No background continuation
- No hidden retries
- No multi-command execution
- No autonomous branching
- No invisible mutation of command scope
