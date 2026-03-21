# JARVIS Error Model (MVP)

## Purpose
Define the fixed MVP error model used across:
- parsing
- validation
- clarification
- execution
- runtime state transitions

Rules:
- errors must be explicit
- errors must be user-visible when relevant
- errors must not trigger hidden retries or silent fallbacks

## Error Categories
### 1. INPUT_ERROR
- Meaning: input cannot be processed into valid command text.
- Occurs when: input intake receives empty or unreadable input.
- Runtime behavior: terminal for current attempt; not an execution-block state.

### 2. VALIDATION_ERROR
- Meaning: parsed command violates validation rules.
- Occurs when: confidence, intent, target, action, or parameters fail validation.
- Runtime behavior: blocking until resolved through clarification; not terminal by default.

### 3. CLARIFICATION_BLOCK
- Meaning: runtime is paused pending clarification.
- Occurs when: command cannot safely continue due to ambiguity or unresolved references.
- Runtime behavior: blocking and non-terminal until user clarifies or cancels.

### 4. CONFIRMATION_BLOCK
- Meaning: runtime is paused pending explicit confirmation.
- Occurs when: command-level or step-level confirmation is required.
- Runtime behavior: blocking and non-terminal while pending; terminal if confirmation is denied.

### 5. EXECUTION_ERROR
- Meaning: a step failed during desktop execution.
- Occurs when: execution action cannot be completed.
- Runtime behavior: terminal for current command; remaining steps must not run.

### 6. RUNTIME_ERROR
- Meaning: runtime contract or state transition violation.
- Occurs when: invalid state movement, corrupted blocked state, or scope mismatch is detected.
- Runtime behavior: terminal for current command.

### 7. CANCELLATION
- Meaning: command stopped by explicit user cancellation.
- Occurs when: user cancels active flow.
- Runtime behavior: terminal for current command.

## Fixed Error Codes
### INPUT_ERROR
- `EMPTY_INPUT`: no usable text was provided.
- `UNREADABLE_INPUT`: input could not be converted into reliable text.

### VALIDATION_ERROR
- `LOW_CONFIDENCE`: parser confidence is below threshold.
- `UNKNOWN_INTENT`: parsed intent is not in the fixed MVP intent list.
- `MISSING_PARAMETER`: one or more required parameters are absent.
- `TARGET_NOT_FOUND`: required target could not be resolved.
- `MULTIPLE_MATCHES`: target resolution returned multiple valid matches.
- `UNSUPPORTED_TARGET`: target type is not valid for the command/action.
- `UNSUPPORTED_ACTION`: action is outside the fixed MVP action catalog.

### CLARIFICATION_BLOCK
- `CLARIFICATION_REQUIRED`: clarification is required before execution can continue.
- `FOLLOWUP_REFERENCE_UNCLEAR`: follow-up reference cannot be resolved from session context.

### CONFIRMATION_BLOCK
- `CONFIRMATION_REQUIRED`: explicit approval is required before execution can continue.
- `CONFIRMATION_DENIED`: user denied confirmation, so execution must stop.

### EXECUTION_ERROR
- `PERMISSION_DENIED`: OS or environment denied the requested operation.
- `APP_NOT_RUNNING`: action requires a running app that is not running.
- `WINDOW_UNAVAILABLE`: target window is missing, closed, or not focusable/closable.
- `APP_UNAVAILABLE`: target app is unavailable for requested operation.
- `INVALID_URL`: URL is invalid for `open_website`.
- `EXECUTION_FAILED`: action failed with a non-specific runtime failure.
- `STEP_FAILED`: a specific planned step failed and halted the command.

### RUNTIME_ERROR
- `INVALID_STATE_TRANSITION`: attempted transition is not allowed by runtime state model.
- `BLOCKED_STATE_CORRUPTED`: blocked-state data is missing or inconsistent.
- `COMMAND_SCOPE_MISMATCH`: active runtime command scope no longer matches executable state.

### CANCELLATION
- `USER_CANCELLED`: user explicitly cancelled the active command.

## Error Object Shape
```text
JarvisError {
  category: string,
  code: string,
  message: string,
  details?: object,
  blocking: boolean,
  terminal: boolean
}
```

Field rules:
- `category` must be one of the fixed categories in this document.
- `code` must be a fixed code belonging to that category only.
- `message` must be concise, user-safe, and actionable.
- `details` is optional structured context for runtime handling.
- `blocking` indicates runtime pause awaiting user input.
- `terminal` indicates current command must end immediately.

## Blocking and Terminal Rules
- `CLARIFICATION_BLOCK` and pending `CONFIRMATION_BLOCK` must set `blocking = true`, `terminal = false`.
- `INPUT_ERROR`, `EXECUTION_ERROR`, `RUNTIME_ERROR`, and `CANCELLATION` must set `blocking = false`, `terminal = true`.
- `CONFIRMATION_DENIED` must set `blocking = false`, `terminal = true`.
- A terminal error must stop the active command and prevent remaining step execution.
- A blocking error must pause runtime at the current boundary and require explicit user input.

## Error Surface Rules
- Blocking errors must be shown immediately with clear next action.
- Terminal errors must be shown immediately with failed step/context when available.
- Validation-origin errors that require user input must surface as clarification prompts.
- Errors must propagate without mutation of category/code between components.
- No hidden retries, no silent fallback actions, and no silent state transitions are allowed.
