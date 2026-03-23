# JARVIS Runtime Components (Dual-Mode MVP)

## Purpose
Define the minimum runtime components required for JARVIS dual-mode MVP and the responsibility of each component.

## Core Components
### 1. Input Adapter
- Purpose: receive user interaction and normalize it into runtime input.
- Input: raw user interaction (text, or voice already converted to text by input pipeline).
- Output: normalized `raw_input` string.
- Allowed to do: basic normalization (trim, encoding normalization, noise cleanup).
- Must NOT do: route interaction mode, parse intents, validate commands, answer questions, or execute actions.

### 2. Interaction Router
- Purpose: decide whether normalized input is a command reply, a fresh command, a question, or a routing clarification case.
- Input: normalized `raw_input`, active blocked-state context, optional session context.
- Output: interaction decision (`command`, `question`, or clarification requirement).
- Allowed to do: apply deterministic precedence and routing rules.
- Must NOT do: execute actions, create execution plans, or fabricate answers.

### 3. Command Parser
- Purpose: convert command-mode input into a preliminary `Command` object.
- Input: routed command input plus optional session context.
- Output: preliminary `Command`.
- Allowed to do: map language to fixed MVP intents, targets, and parameters.
- Must NOT do: execute actions, answer questions, bypass ambiguity rules, or create new intent types.

### 4. Command Validator
- Purpose: validate confidence, targets, parameters, and intent legality for command-mode inputs.
- Input: preliminary `Command`.
- Output: validated `Command` or clarification requirement.
- Allowed to do: enforce validation rules and block invalid commands.
- Must NOT do: guess missing values silently, answer questions, run steps, or bypass blocked states.

### 5. Clarification Handler
- Purpose: generate minimal clarification questions and apply user answers.
- Input: clarification requirement plus blocked command state or routing ambiguity.
- Output: updated command fields or clarified routing input.
- Allowed to do: ask one concrete question tied to the immediate next decision.
- Must NOT do: ask broad/open-ended questions, chain multiple questions, answer unrelated questions, or execute steps.

### 6. Session Context Store
- Purpose: hold active-session context needed for short follow-ups, blocked-state resume, and grounded status answers.
- Input: current command, runtime updates, and explicit recent context.
- Output: recent context for router, parser, validator, and answer engine.
- Allowed to do: store short-lived context for the active supervised session.
- Must NOT do: persist cross-session memory, store user profile data, or grow background memory.

### 7. Execution Planner
- Purpose: translate a validated command into ordered executable steps.
- Input: validated `Command`.
- Output: `execution_steps`, confirmation boundaries, and `status_message`.
- Allowed to do: build sequential, supported MVP step plans.
- Must NOT do: invent unsupported capabilities, answer questions, create new intents, or execute steps.

### 8. Desktop Executor
- Purpose: execute one desktop step at a time.
- Input: current `Step`.
- Output: step result plus updated step status.
- Allowed to do: perform only mapped desktop operations in validated scope.
- Must NOT do: continue after failure, answer questions, run hidden fallback actions, or run parallel steps.

### 9. Confirmation Gate
- Purpose: enforce explicit approval boundaries for sensitive command actions.
- Input: command-level or step-level confirmation requirement.
- Output: `approved`, `denied`, or `pending`.
- Allowed to do: pause command runtime and request explicit user confirmation.
- Must NOT do: auto-confirm, infer approval, answer unrelated questions, or bypass confirmation requirements.

### 10. Command Runtime State Manager
- Purpose: track deterministic command-runtime states and state transitions.
- Input: outputs/events from parser, validator, clarification, planner, executor, and confirmation gate.
- Output: current command runtime state.
- Allowed to do: enforce valid command transitions (`idle`, `parsing`, `validating`, `awaiting_clarification`, `planning`, `executing`, `awaiting_confirmation`, `completed`, `failed`, `cancelled`).
- Must NOT do: mutate command scope silently, trigger hidden execution branches, or represent question answers as command execution.

### 11. Answer Engine
- Purpose: build grounded answers for question-mode inputs.
- Input: routed question input, allowed sources, optional session context, visible runtime state, and answer-backend configuration.
- Output: `AnswerResult` containing answer text, sources, confidence, and optional warning.
- Allowed to do: select an internal answer backend, classify supported question families, select explicit sources, and return grounded read-only answers.
- Must NOT do: execute actions, approve confirmations, create `Command` execution plans, or guess beyond allowed sources.

### 12. User Visibility Layer
- Purpose: expose visible interaction progress, answers, and blocking/failure reasons to the user.
- Input: interaction mode, command runtime state, step updates, answer results, and clarification/confirmation/failure events.
- Output: user-facing status, current step, completed steps, prompts, or grounded answer payload.
- Allowed to do: render concise runtime updates and answer results for supervised interaction.
- Must NOT do: hide execution events, suppress blocked/failure reporting, imply execution in question mode, or directly control execution.

## Component Details
### Input Adapter
The Input Adapter is the shared entry point. It must convert raw user interaction into a normalized `raw_input` string and pass it forward unchanged in meaning. It may normalize text form, but it must not decide whether the input is a command or a question.

### Interaction Router
The Interaction Router is the top-level dispatcher. It must apply deterministic precedence for blocked replies, fresh command requests, fresh question requests, and mixed/unclear requests. It is the only component allowed to decide whether input should enter command mode or question-answer mode.

### Command Parser
The Command Parser converts routed command input into a `Command` object defined by the command model. It may read short-lived session context to resolve immediate references, but it must not answer questions or bypass ambiguity constraints.

### Command Validator
The Command Validator enforces command legality before planning or execution. It must check confidence thresholds, target resolvability, required parameters, and fixed-intent legality. Invalid commands must produce clarification requirements or terminal failures, not execution attempts.

### Clarification Handler
The Clarification Handler creates exactly one minimal question needed to unblock routing or command execution and applies the user response to the blocked state. It must keep clarification deterministic and narrow. It must not open-endedly converse.

### Session Context Store
The Session Context Store keeps only active-session context: current command state, recent resolved targets, recent clarification/confirmation outcomes, blocked-state data required for resume, and recent runtime context that may ground a read-only answer.

### Execution Planner
The Execution Planner transforms a validated command into ordered `execution_steps` plus confirmation gates and `status_message`. Planner output is an execution contract, not an execution action.

### Desktop Executor
The Desktop Executor runs steps sequentially and updates each step status (`pending` -> `executing` -> `done`/`failed`). It must stop on failure, ambiguity, or confirmation boundary and return explicit results.

### Confirmation Gate
The Confirmation Gate is a hard command boundary. At command-level or step-level confirmation points, it must block command execution until explicit user approval or denial is received.

### Command Runtime State Manager
The Command Runtime State Manager is the source of truth for command execution state. Question-answer mode may read that state through allowed interfaces, but it must not force command state transitions or silently resume blocked execution.

### Answer Engine
The Answer Engine builds grounded read-only answers. It may use docs, structured capability metadata, current runtime visibility, and session context. In v1 it may use a deterministic backend only. Future versions may add an LLM-backed backend behind the same `Answer Engine` contract, but routing, grounding, and safety policy must remain outside the backend. The Answer Engine must return bounded failures when grounding is missing or the question is out of scope.

### User Visibility Layer
The User Visibility Layer must continuously publish either:
- supervised command runtime information, or
- grounded answer information.

Visibility is mandatory and cannot be optional.

## Component Interaction Order
### Command branch
1. Input Adapter
2. Interaction Router
3. Command Parser
4. Command Validator
5. Clarification Handler (if needed)
6. Execution Planner
7. Confirmation Gate (if command-level)
8. Desktop Executor
9. Confirmation Gate (if step-level)
10. Command Runtime State Manager
11. User Visibility Layer

### Question branch
1. Input Adapter
2. Interaction Router
3. Answer Engine
4. User Visibility Layer

Flow rules:
- blocked clarification and confirmation replies have precedence over new routing
- clarification and confirmation are hard blocking points for command mode
- command runtime state updates continuously across command stages only
- question mode is read-only and returns directly after answer generation
- execution continues only when blocking conditions are explicitly resolved

## Responsibility Boundaries
- Interaction routing and command parsing must be separate.
- Command parsing and question answering must be separate.
- Validation and execution must remain command-only responsibilities.
- Planning and execution must remain separate.
- Context storage and decision logic must remain separate.
- Visibility/reporting must not directly control execution.
- `Command` must remain action-only and must not absorb question-answer semantics.
- Any future LLM backend must remain an implementation detail of `Answer Engine`, not a new top-level authority.

Overlap is not allowed because it creates hidden behavior, weakens blocking guarantees, and breaks deterministic supervised interaction.

## Constraints
- No background orchestration
- No multi-command scheduler
- No autonomous task queue
- No hidden component side effects
- No overlapping ownership between components
- No hidden answer-triggered execution
