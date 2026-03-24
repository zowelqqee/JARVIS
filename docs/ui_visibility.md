# JARVIS UI Visibility (Dual-Mode MVP)

## Purpose
Define the minimum user-visible interaction information required for supervised command execution and grounded question answering.

- Visibility is mandatory.
- Command runtime state must always be externally legible when command mode is active.
- Answer mode must always make its grounding and non-executing nature clear.
- No silent execution or hidden blocked states are allowed.

## Visibility Goals
The UI must always let the user understand:
- what JARVIS understood
- whether the input became a command or a question
- what JARVIS is doing now
- what JARVIS already did
- what JARVIS needs from the user
- whether execution succeeded, failed, was blocked, or a question was answered

## Required Visible Elements
### 1. Interaction mode
- What it shows: whether the current interaction is `command` or `question`.
- When it appears: for every handled input.
- When it updates: immediately after routing completes.

### 2. Current command summary
- What it shows: concise normalized command intent and main target(s).
- When it appears: in command mode after parsing starts.
- When it updates: after clarification or confirmation changes command meaning.

### 3. Current runtime state
- What it shows: one active command runtime state label (`idle`, `parsing`, `validating`, `awaiting_clarification`, `planning`, `executing`, `awaiting_confirmation`, `completed`, `failed`, `cancelled`).
- When it appears: in command mode.
- When it updates: immediately on every valid state transition.

### 4. Current step
- What it shows: active step id/description for command execution.
- When it appears: in command mode `executing` and `awaiting_confirmation` when a step is in scope.
- When it updates: when step changes or step status changes.

### 5. Completed steps
- What it shows: ordered list of steps finished with `done` status.
- When it appears: in command mode after the first completed step in the active command.
- When it updates: immediately when a step becomes `done`.

### 6. Blocked reason
- What it shows: explicit reason interaction is paused or cannot continue cleanly.
- When it appears: in clarification/confirmation states and other visible blocked cases.
- When it updates: whenever the blocking reason changes.

### 7. Confirmation prompt
- What it shows: pending confirmation request for command-level or step-level gate.
- When it appears: in command mode `awaiting_confirmation`.
- When it updates: when pending confirmation target/action changes.

### 8. Answer text
- What it shows: the grounded question answer.
- When it appears: in question mode on successful answer.
- When it updates: once per answered question.

### 9. Answer summary
- What it shows: one short summary line for the answered question, optimized for CLI history scanning and speech output.
- When it appears: in question mode on successful answer.
- When it updates: once per answered question.

### 10. Answer sources
- What it shows: human-readable source labels plus the raw absolute source paths used to ground the answer.
- When it appears: in question mode when the answer is grounded from docs or structured runtime data.
- When it updates: once per answered question.

### 11. Answer source attributions
- What it shows: short per-source support statements explaining what each cited source grounds.
- When it appears: in question mode when the answer backend can expose stronger evidence mapping.
- When it updates: once per answered question.

### 12. Answer warning
- What it shows: bounded uncertainty or partial-context note for the answer.
- When it appears: in question mode only when needed.
- When it updates: once per answered question.

### 13. Failure message
- What it shows: concise failure reason with error code/message.
- When it appears: in failed command interactions or failed question interactions.
- When it updates: once at failure entry; remains visible for the interaction result.

### 14. Completion result
- What it shows: concise success summary of completed command execution.
- When it appears: in command mode `completed`.
- When it updates: once at completion entry.

### 15. Stop / cancel control
- What it shows: explicit control to cancel the active command.
- When it appears: during active command states (`parsing`, `validating`, `planning`, `executing`, `awaiting_clarification`, `awaiting_confirmation`).
- When it updates: enabled while a command is active; disabled in `idle`, `completed`, `failed`, `cancelled`, and question mode.

## Command Mode Mapping
### idle
- show input only
- no active command panel

### parsing
- show interaction mode = `command`
- show short parsing status
- show raw or normalized command summary

### validating
- show interaction mode = `command`
- show validation status
- do not show execution progress yet

### awaiting_clarification
- show interaction mode = `command`
- show clarification question
- show blocked state clearly
- do not show execution as active

### planning
- show interaction mode = `command`
- show short plan-building state
- may show "preparing steps"

### executing
- show interaction mode = `command`
- show active command
- show current step
- show completed steps
- show stop control

### awaiting_confirmation
- show interaction mode = `command`
- show confirmation request
- show exact action waiting for approval
- show affected target(s)
- show blocked state clearly

### completed
- show interaction mode = `command`
- show success summary
- show completed steps
- allow user to continue with follow-up command

### failed
- show interaction mode = `command`
- show failure summary
- show failed step if known
- show suggested next action when available

### cancelled
- show interaction mode = `command`
- show cancellation result
- show what was completed before cancellation

## Question Mode Mapping
### answered question
- show interaction mode = `question`
- show answer summary first
- show answer text
- show answer sources with readable labels and raw paths when available
- show answer source attributions when available
- show answer warning only when needed
- do not show execution steps unless the answer explicitly describes already-visible runtime state
- do not show stop/cancel control as if execution were active

### failed question
- show interaction mode = `question`
- show a short failure boundary
- explain whether the problem is unsupported scope, missing source, or insufficient context
- do not imply execution was attempted

## Step Visibility Rules
- Each executed command step must become visible before or during execution.
- Completed command steps must remain visible for the active command.
- Failed command step must be visibly marked.
- Blocked command step must be visibly marked.
- No command step may execute without corresponding visible state.
- Question mode must not invent command steps.

## Clarification UI Rules
- Clarification must appear as one short actionable question.
- If options exist, show them clearly.
- User must understand whether execution is paused or routing is unresolved.
- No unrelated system chatter.

## Confirmation UI Rules
- Confirmation must show action description.
- Confirmation must show affected target(s).
- Confirmation must show approve option.
- Confirmation must show cancel/deny option.
- Confirmation state must visibly block execution.
- No implied or hidden approval.

## Answer UI Rules
- Answer text must be concise and direct.
- Provide one short answer summary line suitable for CLI history scanning and speech output.
- If the answer is grounded in docs or runtime data, show the source set with readable labels and raw paths.
- If the backend provides stronger per-source support mapping, show it without implying hidden retrieval.
- If the answer is partial, show one bounded warning.
- Answer mode must not imply that desktop actions ran.
- If the user input was actually a command, the UI must not render an answer as if it handled the request fully.

## Failure UI Rules
- Failure message must be short and concrete.
- If a command step is known, show which step failed.
- If next action is known, show one suggested next step.
- Failure must end visible command progress for the command.
- Question failure must not imply that execution or planning occurred.

## Completion UI Rules
- Show concise success result for command completion.
- Show what was completed.
- Keep enough context visible for immediate follow-up command.
- Question mode should end with answer visibility, not command completion language.

## Constraints
- No hidden execution
- No invisible blocked state
- No progress indicator without actual runtime state behind it
- No UI state that implies execution continued when it did not
- No suppression of error, confirmation, or clarification states
- No answer card that conceals missing grounding
