# JARVIS Desktop Execution (MVP)

## Purpose
Define how JARVIS translates validated command steps into desktop operations.

This contract applies only after parsing and validation are complete.

## Execution Responsibilities
The execution layer is responsible for:
- receiving validated steps
- resolving desktop targets
- executing one step at a time
- reporting visible status
- stopping on failure, ambiguity, or confirmation boundary

The execution layer is not responsible for:
- interpreting product strategy
- creating new intents
- continuing autonomously after a blocked state

Parsing and product logic happen before execution. Execution only runs validated scope.

## Supported Desktop Capabilities (MVP)
### Application launch / focus
- can open an installed app
- can focus an already running app
- cannot install apps
- cannot change app settings

### File open
- can open a local file in the default or specified app
- can report target-not-found when file does not resolve
- cannot edit file contents automatically
- cannot move or delete files

### Folder open
- can open a local folder in the system file manager
- can focus an already open folder window when supported
- cannot create, rename, move, or delete folders
- cannot change folder permissions

### Website open
- can open a URL in a browser
- can focus browser if already running
- cannot submit forms automatically
- cannot perform authenticated actions

### Window discovery
- can list currently available windows for supported apps
- can return window identity metadata needed for focus/close
- cannot inspect private document contents
- cannot monitor windows in background

### Window focus
- can bring a selected window to foreground
- can switch active context to that window
- cannot modify window content
- cannot bypass ambiguity when multiple matching windows exist

### Window close
- can request close for a selected window
- can stop and request confirmation when close is sensitive
- cannot force destructive close without confirmation
- cannot ignore unsaved-change prompts

### Local search
- can search local files/folders by validated query and scope
- can return matching results for user selection
- cannot search external services
- cannot execute hidden follow-up actions

### Simple workspace setup
- can execute a short validated sequence (for example: open IDE, open folder, open browser)
- can run steps sequentially with visible progress
- cannot run long workflows
- cannot continue after completion without a new explicit command

## Step Execution Contract
1. Receive Step: load next validated step from the command.
2. Resolve target: resolve the step target using target resolution rules.
3. Check whether confirmation is required: if required, enter blocked state before execution.
4. Execute desktop action: run the mapped desktop operation for the step action.
5. Mark status: update step status to `done` or `failed` (and `executing` while running).
6. Report result: emit visible status update for user supervision.
7. Move to next step only if current step succeeded.

Runtime rules:
- one active step at a time
- no parallel execution
- no skipped steps

## Target Resolution Rules
- Use exact match first.
- Use known aliases second.
- Use fuzzy matching only if still safe.
- If target remains unresolved, stop and return clarification need.

Strict rules:
- never silently substitute unrelated targets
- never guess when multiple valid matches exist

Ambiguity blocks execution until clarified by the user.

## Confirmation Boundary Rules
- If command-level confirmation exists, block before step 1.
- If step-level confirmation exists, block before that step.
- Execution resumes only after explicit user confirmation.

Blocked-state requirements:
- preserve current command and step index
- preserve step statuses already completed
- no silent resume

Confirmation is a hard execution boundary. Implicit continuation is not allowed.

## Failure Handling Rules
On failure:
- mark current step as `failed`
- stop command immediately
- do not continue remaining steps
- return structured failure result

Common failure classes:
- target not found
- permission denied
- multiple matches
- app/window unavailable
- unsupported action

Failure result must include:
- failed step id
- failure class
- concise reason
- suggested next action

No autonomous retries. No hidden recovery behavior.

## Visibility Rules
During execution, user-visible state must include:
- current command
- current step
- completed steps
- blocked or failed state
- confirmation request when applicable

No silent execution allowed.

## Platform Notes (MVP)
- MVP may start on one desktop platform first.
- A platform adapter is allowed internally.
- The command model must stay platform-neutral.
- Platform-specific execution details must not leak into product behavior.

## Constraints
- No background execution
- No autonomous retries
- No hidden recovery logic
- No destructive fallback behavior
- No execution outside validated scope
