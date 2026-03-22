# JARVIS Session Context (Dual-Mode MVP)

## Purpose
Define what JARVIS may remember during one active supervised session to support short follow-up commands, blocked-state resume, and grounded session-aware answers.

## Session Context Responsibilities
Session context exists only to:
- keep the immediate active command coherent
- support short follow-up commands
- preserve current execution state when blocked or interrupted
- avoid asking the user to repeat obvious immediate context
- ground narrow status questions about the current supervised session

Session context is not:
- long-term memory
- user profile storage
- autonomous planning memory
- cross-session persistence
- a source of hidden execution authority

## Context Scope (MVP)
### Current active command
- Stores: the current validated command object being handled.
- Needed: keeps follow-up behavior tied to the active supervised task.
- Expires: when the task completes and no follow-up occurs within a short interaction window.

### Current execution state
- Stores: current step index, step statuses, and command runtime status.
- Needed: supports visible progress, pause/resume, safe interruption handling, and grounded status answers.
- Expires: when command execution finishes, is cancelled, or fails.

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
- Expires: when the gated command or step completes, is cancelled, or fails.

### Recent workspace or app context
- Stores: the most recent active workspace/app context established in-session (for example, active project folder or primary app used in current task).
- Needed: supports short follow-ups such as "now open browser too" and narrow status answers about current context.
- Expires: when an unrelated command starts, the user cancels, or the session ends.

### Recent search results
- Stores: the latest ordered local search result set plus the search query and scope.
- Needed: supports numbered follow-up opens and bounded answers such as which file was most recently found.
- Expires: when an unrelated command replaces the search context or the session resets.

## QA Access Rules
Question-answer mode may read session context only to answer grounded questions about the current supervised session.

Allowed QA reads:
- active command summary
- current runtime state
- current step index and visible step statuses
- recent resolved targets
- recent workspace context
- recent search results
- recent confirmation status

Not allowed:
- treating session context as long-term memory
- fabricating preferences from stale context
- silently rewriting active command state
- approving or denying confirmation through answer mode
- resuming blocked execution because a question was asked

## Allowed Follow-up Behavior
Follow-up commands may use only active or very recent explicit session context.

Examples:
- "now open browser too"
- "also open Telegram"
- "close that one"
- "use the same folder"

Grounded status questions may use only active or very recent explicit session context.

Examples:
- "what are you doing now"
- "which file did you just open"
- "why are you blocked"
- "what folder are you using"

Rules:
- follow-up may reference only recent, explicit context
- question-answer mode may describe only recent, explicit context
- JARVIS must not invent hidden context
- if a reference is unclear, JARVIS must ask for clarification or report insufficient context

## Context Resolution Rules
Resolve omitted command references in this order:
1. current active task context
2. last explicit resolved target
3. most recent clarification result
4. recent search results when the form explicitly refers to a search result
5. otherwise ask the user

Resolve status-answer context in this order:
1. current active task context
2. current visible execution state
3. last explicit resolved target
4. recent search results when explicitly relevant
5. otherwise report insufficient context

Strict rules:
- do not use stale context from older unrelated commands
- do not assume long-term preferences in MVP
- never silently reinterpret unclear follow-ups
- never convert missing context into guessed answers

## Expiration Rules
Session context expires:
- when the active task completes and no follow-up occurs after a short interaction window
- when the user starts an unrelated new command
- when the user explicitly cancels the task
- when the system resets or the session ends

Expired context must not influence new command resolution or question answers.

## Blocked / Interrupted State
If execution is blocked, preserve only:
- current command
- current step index
- completed steps
- pending confirmation state
- relevant targets already resolved
- relevant search/result context already visible

Resume rules:
- resume requires explicit user input
- no auto-resume
- question-answer mode may describe blocked state but must not unblock it

## Safety Rules
- session context must not store secrets, passwords, or sensitive form input
- session context must not be used to bypass confirmation
- session context must not silently expand command scope
- session context must not silently expand answer scope beyond the active session

## Constraints
- No cross-session persistence
- No background memory growth
- No autonomous context chaining
- No hidden state that changes execution behavior invisibly
