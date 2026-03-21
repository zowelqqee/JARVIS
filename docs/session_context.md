# JARVIS Session Context (MVP)

## Purpose
Define what JARVIS may remember during one active supervised session to support short follow-up commands and maintain coherent interaction.

## Session Context Responsibilities
Session context exists only to:
- keep the immediate active task coherent
- support short follow-up commands
- preserve current execution state when blocked or interrupted
- avoid asking the user to repeat obvious immediate context

Session context is not:
- long-term memory
- user profile storage
- autonomous planning memory
- cross-session persistence

## Context Scope (MVP)
### Current active command
- Stores: the current validated command object being handled.
- Needed: keeps follow-up behavior tied to the active supervised task.
- Expires: when the task completes and no follow-up occurs within a short interaction window.

### Current execution state
- Stores: current step index, step statuses, and command runtime status.
- Needed: supports visible progress, pause/resume, and safe interruption handling.
- Expires: when command execution finishes, is canceled, or fails.

### Last resolved targets
- Stores: the most recent explicitly resolved app/file/folder/window/browser targets.
- Needed: supports short references such as "that one" or "same folder."
- Expires: when a new unrelated command starts or the short interaction window closes.

### Recent clarification answer
- Stores: the latest user-provided disambiguation answer.
- Needed: allows immediate continuation after clarification without re-asking.
- Expires: after the related command step is executed or context is replaced by newer clarification.

### Recent confirmation state
- Stores: whether confirmation is pending, granted, or denied for the current command/step.
- Needed: enforces confirmation boundaries in supervised execution.
- Expires: when the gated command or step completes, is canceled, or fails.

### Recent workspace or app context
- Stores: the most recent active workspace/app context established in-session (for example, active project folder or primary app used in current task).
- Needed: supports short follow-ups such as "now open browser too."
- Expires: when an unrelated command starts, the user cancels, or the session ends.

## Allowed Follow-up Behavior
Follow-up commands may use only active or very recent explicit session context.

Examples:
- "now open browser too"
- "also open Telegram"
- "close that one"
- "use the same folder"

Rules:
- follow-up may reference only recent, explicit context
- JARVIS must not invent hidden context
- if a reference is unclear, JARVIS must ask for clarification

## Context Resolution Rules
Resolve omitted references in this order:
1. current active task context
2. last explicit resolved target
3. most recent clarification result
4. otherwise ask the user

Strict rules:
- do not use stale context from older unrelated commands
- do not assume long-term preferences in MVP
- never silently reinterpret unclear follow-ups

Unclear follow-ups block automatic resolution and require clarification.

## Expiration Rules
Session context expires:
- when the active task completes and no follow-up occurs after a short interaction window
- when the user starts an unrelated new command
- when the user explicitly cancels the task
- when the system resets or the session ends

Expired context must not influence new command resolution.

## Blocked / Interrupted State
If execution is blocked, preserve only:
- current command
- current step index
- completed steps
- pending confirmation state
- relevant targets already resolved

Resume rules:
- resume requires explicit user input
- no auto-resume

## Safety Rules
- session context must not store secrets, passwords, or sensitive form input
- session context must not be used to bypass confirmation
- session context must not silently expand command scope

## Constraints
- No cross-session persistence
- No background memory growth
- No autonomous context chaining
- No hidden state that changes execution behavior invisibly
