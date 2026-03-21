# JARVIS UI Visibility (MVP)

## Purpose
Define the minimum user-visible runtime information required for supervised desktop execution.

- Visibility is mandatory.
- Runtime state must always be externally legible.
- No silent execution or hidden blocked states are allowed.

## Visibility Goals
The UI must always let the user understand:
- what JARVIS understood
- what JARVIS is doing now
- what JARVIS already did
- what JARVIS needs from the user
- whether execution succeeded, failed, or is blocked

## Required Visible Elements
### 1. Current command summary
- What it shows: concise normalized command intent and main target(s).
- When it appears: after parsing starts.
- When it updates: after clarification or confirmation changes command meaning.

### 2. Current runtime state
- What it shows: one active runtime state label (`idle`, `parsing`, `validating`, `awaiting_clarification`, `planning`, `executing`, `awaiting_confirmation`, `completed`, `failed`, `cancelled`).
- When it appears: always.
- When it updates: immediately on every valid state transition.

### 3. Current step
- What it shows: active step id/description for execution.
- When it appears: in `executing` and `awaiting_confirmation` when a step is in scope.
- When it updates: when step changes or step status changes.

### 4. Completed steps
- What it shows: ordered list of steps finished with `done` status.
- When it appears: after first completed step in active command.
- When it updates: immediately when a step becomes `done`.

### 5. Blocked reason
- What it shows: explicit reason execution is paused (clarification or confirmation boundary).
- When it appears: in blocked states.
- When it updates: whenever the blocking reason changes.

### 6. Confirmation prompt
- What it shows: pending confirmation request for command-level or step-level gate.
- When it appears: in `awaiting_confirmation`.
- When it updates: when pending confirmation target/action changes.

### 7. Failure message
- What it shows: concise failure reason with error code/message.
- When it appears: in `failed`.
- When it updates: once at failure entry; remains visible for the command result.

### 8. Completion result
- What it shows: concise success summary of completed command.
- When it appears: in `completed`.
- When it updates: once at completion entry.

### 9. Stop / cancel control
- What it shows: explicit control to cancel active runtime command.
- When it appears: during active command states (`parsing`, `validating`, `planning`, `executing`, `awaiting_clarification`, `awaiting_confirmation`).
- When it updates: enabled while command is active; disabled in `idle`, `completed`, `failed`, `cancelled`.

## State-to-UI Mapping
### idle
- show input only
- no active command panel

### parsing
- show short parsing status
- show raw or normalized command summary

### validating
- show validation status
- do not show execution progress yet

### awaiting_clarification
- show clarification question
- show blocked state clearly
- do not show execution as active

### planning
- show short plan-building state
- may show "preparing steps"

### executing
- show active command
- show current step
- show completed steps
- show stop control

### awaiting_confirmation
- show confirmation request
- show exact action waiting for approval
- show affected target(s)
- show blocked state clearly

### completed
- show success summary
- show completed steps
- allow user to continue with follow-up command

### failed
- show failure summary
- show failed step if known
- show suggested next action when available

### cancelled
- show cancellation result
- show what was completed before cancellation

## Step Visibility Rules
- Each executed step must become visible before or during execution.
- Completed steps must remain visible for the active command.
- Failed step must be visibly marked.
- Blocked step must be visibly marked.
- No step may execute without corresponding visible state.

## Clarification UI Rules
- Clarification must appear as one short actionable question.
- If options exist, show them clearly.
- User must understand execution is paused.
- No unrelated system chatter.

## Confirmation UI Rules
- Confirmation must show action description.
- Confirmation must show affected target(s).
- Confirmation must show approve option.
- Confirmation must show cancel/deny option.
- Confirmation state must visibly block execution.
- No implied or hidden approval.

## Failure UI Rules
- Failure message must be short and concrete.
- If step is known, show which step failed.
- If next action is known, show one suggested next step.
- Failure must end visible progress for the command.

## Completion UI Rules
- Show concise success result.
- Show what was completed.
- Keep enough context visible for immediate follow-up command.

## Constraints
- No hidden execution
- No invisible blocked state
- No progress indicator without actual runtime state behind it
- No UI state that implies execution continued when it did not
- No suppression of error, confirmation, or clarification states
