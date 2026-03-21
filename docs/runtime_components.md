# JARVIS Runtime Components (MVP)

## Purpose
Define the minimum runtime components required for JARVIS MVP and the responsibility of each component.

## Core Components
### 1. Input Adapter
- Purpose: receive user interaction and normalize it into runtime input.
- Input: raw user interaction (text, or voice already converted to text by input pipeline).
- Output: normalized `raw_input` string.
- Allowed to do: basic normalization (trim, encoding normalization, noise cleanup).
- Must NOT do: parse intents, infer targets, validate commands, or execute actions.

### 2. Command Parser
- Purpose: convert `raw_input` into a preliminary `Command` object.
- Input: `raw_input` plus optional session context.
- Output: preliminary `Command`.
- Allowed to do: map language to fixed MVP intents, targets, and parameters.
- Must NOT do: execute actions, bypass ambiguity rules, or create new intent types.

### 3. Command Validator
- Purpose: validate confidence, targets, parameters, and intent legality.
- Input: preliminary `Command`.
- Output: validated `Command` or clarification requirement.
- Allowed to do: enforce validation rules and block invalid commands.
- Must NOT do: guess missing values silently, run steps, or bypass blocked states.

### 4. Clarification Handler
- Purpose: generate minimal clarification questions and apply user answers.
- Input: clarification requirement and blocked command state.
- Output: updated command fields for re-validation.
- Allowed to do: ask one concrete question tied to immediate next action.
- Must NOT do: ask broad/open-ended questions, chain multiple questions, or execute steps.

### 5. Session Context Store
- Purpose: hold active-session context needed for short follow-ups and blocked-state resume.
- Input: current command and runtime updates.
- Output: recent context for parser/validator resolution.
- Allowed to do: store short-lived context for the active supervised session.
- Must NOT do: persist cross-session memory, store user profile data, or grow background memory.

### 6. Execution Planner
- Purpose: translate validated command into ordered executable steps.
- Input: validated `Command`.
- Output: `execution_steps`, confirmation boundaries, and `status_message`.
- Allowed to do: build sequential, supported MVP step plans.
- Must NOT do: invent unsupported capabilities, create new intents, or execute steps.

### 7. Desktop Executor
- Purpose: execute one desktop step at a time.
- Input: current `Step`.
- Output: step result plus updated step status.
- Allowed to do: perform only mapped desktop operations in validated scope.
- Must NOT do: continue after failure, run hidden fallback actions, or run parallel steps.

### 8. Confirmation Gate
- Purpose: enforce explicit approval boundaries for sensitive actions.
- Input: command-level or step-level confirmation requirement.
- Output: `approved`, `denied`, or `pending`.
- Allowed to do: pause runtime and request explicit user confirmation.
- Must NOT do: auto-confirm, infer approval, or bypass confirmation requirements.

### 9. Runtime State Manager
- Purpose: track deterministic runtime states and state transitions.
- Input: outputs/events from parser, validator, clarification, planner, executor, and confirmation gate.
- Output: current runtime state.
- Allowed to do: enforce valid transitions (`idle`, `parsing`, `validating`, `awaiting_clarification`, `planning`, `executing`, `awaiting_confirmation`, `completed`, `failed`, `cancelled`).
- Must NOT do: mutate command scope silently or trigger hidden execution branches.

### 10. User Visibility Layer
- Purpose: expose visible runtime progress and blocking/failure reasons to the user.
- Input: runtime state, step updates, and clarification/confirmation/failure events.
- Output: user-facing status, current step, completed steps, and prompts.
- Allowed to do: render concise runtime updates for supervised execution.
- Must NOT do: hide execution events, suppress blocked/failure reporting, or directly control execution.

## Component Details
### 1. Input Adapter
The Input Adapter is the runtime entry point. It must convert raw user interaction into a normalized `raw_input` string and pass it forward unchanged in meaning. It may normalize text form, but it must not perform intent or target inference.

### 2. Command Parser
The Command Parser converts `raw_input` into a preliminary `Command` object defined by the MVP command model. It may read short-lived session context to resolve immediate references, but it must not execute actions or bypass ambiguity constraints.

### 3. Command Validator
The Command Validator enforces command legality before planning or execution. It must check confidence thresholds, target resolvability, required parameters, and fixed-intent legality. Invalid commands must produce clarification requirements, not execution attempts.

### 4. Clarification Handler
The Clarification Handler creates exactly one minimal question needed to unblock execution and applies the user response to blocked command fields. It must keep clarification deterministic and narrow. It must not open-endedly converse or chain unresolved questions.

### 5. Session Context Store
The Session Context Store keeps only active-session context: current command state, recent resolved targets, recent clarification/confirmation outcomes, and blocked-state data required for resume. It must expire context per session rules and must not persist memory across sessions.

### 6. Execution Planner
The Execution Planner transforms a validated command into ordered `execution_steps` plus confirmation gates and `status_message`. Plan output must be sequential, explicit, and constrained to supported MVP capabilities. Planner output is an execution contract, not an execution action.

### 7. Desktop Executor
The Desktop Executor runs steps sequentially and updates each step status (`pending` -> `executing` -> `done`/`failed`). It must stop on failure, ambiguity, or confirmation boundary and return explicit results. It must not skip steps or attempt hidden recovery.

### 8. Confirmation Gate
The Confirmation Gate is a hard boundary. At command-level or step-level confirmation points, it must block execution until explicit user approval or denial is received. It must preserve blocked state and cannot infer confirmation from context.

### 9. Runtime State Manager
The Runtime State Manager is the source of truth for runtime state. It must apply explicit transition rules and maintain consistent blocked, completed, failed, and cancelled states. State transitions must be observable and must not mutate command meaning.

### 10. User Visibility Layer
The User Visibility Layer must continuously publish supervised runtime information: current state, command summary, active step, completed steps, blocked reasons, and failure reasons. Visibility is mandatory and cannot be optional at runtime.

## Component Interaction Order
1. Input Adapter
2. Command Parser
3. Command Validator
4. Clarification Handler (if needed)
5. Execution Planner
6. Confirmation Gate (if command-level)
7. Desktop Executor
8. Confirmation Gate (if step-level)
9. Runtime State Manager
10. User Visibility Layer

Flow rules:
- Clarification and confirmation are hard blocking points.
- Runtime State Manager updates continuously across all stages.
- User Visibility Layer updates continuously from runtime state and step events.
- Execution continues only when blocking conditions are explicitly resolved.

## Responsibility Boundaries
- Parsing and validation must be separate: parser extracts structure; validator enforces execution legality.
- Planning and execution must be separate: planner defines ordered steps; executor performs steps.
- Context storage and decision logic must be separate: context store holds data; parser/validator/planner decide behavior.
- Visibility/reporting must not directly control execution: visibility reflects runtime state but cannot mutate it.

Overlap is not allowed because it creates hidden behavior, weakens blocking guarantees, and breaks deterministic supervised execution.

## Constraints
- No background orchestration
- No multi-command scheduler
- No autonomous task queue
- No hidden component side effects
- No overlapping ownership between components
