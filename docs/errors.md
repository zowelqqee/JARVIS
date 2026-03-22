# JARVIS Error Model (Dual-Mode MVP)

## Purpose
Define the fixed error model used across:
- routing
- parsing
- validation
- clarification
- question answering
- execution
- runtime state transitions

Rules:
- errors must be explicit
- errors must be user-visible when relevant
- errors must not trigger hidden retries or silent fallbacks
- question-answer failures must not trigger execution

## Error Categories
### 1. INPUT_ERROR
- Meaning: input cannot be processed into valid text.
- Occurs when: input intake receives empty or unreadable input.
- Runtime behavior: terminal for current attempt; not an execution-block state.

### 2. VALIDATION_ERROR
- Meaning: parsed command violates validation rules.
- Occurs when: confidence, intent, target, action, or parameters fail validation.
- Runtime behavior: blocking until resolved through clarification, or terminal when explicitly unsupported.

### 3. ANSWER_ERROR
- Meaning: a routed question cannot be answered safely within grounded scope.
- Occurs when: question scope is unsupported, required grounding is missing, current context is insufficient, or answer generation cannot produce a grounded result.
- Runtime behavior: terminal for the current question; must not invoke execution.

### 4. CLARIFICATION_BLOCK
- Meaning: interaction is paused pending clarification.
- Occurs when: command cannot safely continue or routing between question and command is still ambiguous.
- Runtime behavior: blocking and non-terminal until user clarifies or cancels.

### 5. CONFIRMATION_BLOCK
- Meaning: command runtime is paused pending explicit confirmation.
- Occurs when: command-level or step-level confirmation is required.
- Runtime behavior: blocking and non-terminal while pending; terminal if confirmation is denied.

### 6. EXECUTION_ERROR
- Meaning: a step failed during desktop execution.
- Occurs when: execution action cannot be completed.
- Runtime behavior: terminal for current command; remaining steps must not run.

### 7. RUNTIME_ERROR
- Meaning: runtime contract or state transition violation.
- Occurs when: invalid state movement, corrupted blocked state, or scope mismatch is detected.
- Runtime behavior: terminal for current interaction.

### 8. CANCELLATION
- Meaning: command stopped by explicit user cancellation.
- Occurs when: user cancels active command flow.
- Runtime behavior: terminal for current command.

## Fixed Error Codes
### INPUT_ERROR
- `EMPTY_INPUT`: no usable text was provided.
- `UNREADABLE_INPUT`: input could not be converted into reliable text.

### VALIDATION_ERROR
- `LOW_CONFIDENCE`: parser confidence is below threshold.
- `UNKNOWN_INTENT`: parsed intent is not in the fixed command intent list.
- `MISSING_PARAMETER`: one or more required command parameters are absent.
- `TARGET_NOT_FOUND`: required command target could not be resolved.
- `MULTIPLE_MATCHES`: target resolution returned multiple valid matches.
- `UNSUPPORTED_TARGET`: target type is not valid for the command/action.
- `UNSUPPORTED_ACTION`: action is outside the fixed command action catalog.

### ANSWER_ERROR
- `UNSUPPORTED_QUESTION`: question is outside supported grounded QA scope.
- `SOURCE_NOT_AVAILABLE`: the required grounding source is unavailable.
- `INSUFFICIENT_CONTEXT`: current runtime/session context is insufficient for the requested answer.
- `ANSWER_NOT_GROUNDED`: a candidate answer could not be supported by allowed sources.
- `ANSWER_GENERATION_FAILED`: answer building failed without a valid grounded result.

### CLARIFICATION_BLOCK
- `CLARIFICATION_REQUIRED`: clarification is required before interaction can continue.
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
- `terminal` indicates current interaction must end immediately.

## Blocking and Terminal Rules
- `CLARIFICATION_BLOCK` and pending `CONFIRMATION_BLOCK` must set `blocking = true`, `terminal = false`.
- `INPUT_ERROR`, `ANSWER_ERROR`, `EXECUTION_ERROR`, `RUNTIME_ERROR`, and `CANCELLATION` must set `blocking = false`, `terminal = true`.
- `CONFIRMATION_DENIED` must set `blocking = false`, `terminal = true`.
- A terminal error must stop the active interaction and prevent command execution or answer completion.
- A blocking error must pause interaction at the current boundary and require explicit user input.

## Error Surface Rules
- Blocking errors must be shown immediately with clear next action.
- Terminal errors must be shown immediately with failed step/context when available.
- Validation-origin errors that require user input must surface as clarification prompts.
- Answer-origin errors must say whether the issue is unsupported scope, missing source, or insufficient context.
- Errors must propagate without mutation of category/code between components.
- No hidden retries, no silent fallback actions, and no silent state transitions are allowed.
