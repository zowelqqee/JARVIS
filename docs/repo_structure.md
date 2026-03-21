# JARVIS Repo Structure (MVP)

## Purpose
Define the minimal codebase structure required to implement the supervised desktop assistant MVP.

- The structure must follow existing runtime contracts.
- Each runtime component must have one clear home.
- The repo must stay minimal and implementation-oriented.

## Top-Level Modules
### `input/`
- Purpose: normalize incoming user interaction into `raw_input`.
- Owns: input normalization and voice-to-text handoff boundary.
- Must not own: parsing, validation, planning, execution, or UI logic.

### `parser/`
- Purpose: build preliminary `Command` from `raw_input`.
- Owns: intent/target/parameter extraction into command shape.
- Must not own: execution, confirmation decisions, or runtime state control.

### `validator/`
- Purpose: enforce command legality before planning.
- Owns: confidence checks, target/parameter checks, intent/action legality checks.
- Must not own: clarification prompting logic, execution, or UI output.

### `clarification/`
- Purpose: create and apply clarification updates.
- Owns: minimal clarification request generation and command patching from reply.
- Must not own: parsing from scratch, execution, or runtime transitions.

### `context/`
- Purpose: hold short-lived active session context.
- Owns: current command context, recent resolved targets, blocked-state resume data.
- Must not own: cross-session persistence, user profile memory, or decision policy.

### `planner/`
- Purpose: convert validated `Command` into executable steps.
- Owns: ordered `execution_steps`, confirmation boundaries, command `status_message`.
- Must not own: step execution, runtime state transitions, or UI mapping.

### `executor/`
- Purpose: execute desktop actions one step at a time.
- Owns: action dispatch and `ActionResult` production for each step.
- Must not own: parsing, validation, clarification, or hidden fallback behavior.

### `confirmation/`
- Purpose: enforce command-level and step-level confirmation boundaries.
- Owns: confirmation request lifecycle (`pending`, `approved`, `denied`).
- Must not own: planning, action execution, or automatic approval behavior.

### `runtime/`
- Purpose: orchestrate runtime flow and state transitions.
- Owns: state machine, transition validity, active command lifecycle.
- Must not own: UI rendering, desktop action internals, or parser logic.

### `ui/`
- Purpose: map runtime truth to visible user status.
- Owns: visibility mapping for current state, current step, blocked/failure/completion views.
- Must not own: execution control decisions or command mutation.

### `types/`
- Purpose: define shared runtime contracts.
- Owns: canonical type definitions used across modules.
- Must not own: UI-only behavior or component-specific business logic.

### `docs/`
- Purpose: hold MVP contracts and behavior specs.
- Owns: product/runtime contract documents.
- Must not own: runtime implementation code.

## Required Files Per Module
### `input/`
- `adapter.py` (or equivalent language filename)

### `parser/`
- `command_parser.py`

### `validator/`
- `command_validator.py`

### `clarification/`
- `clarification_handler.py`

### `context/`
- `session_context.py`

### `planner/`
- `execution_planner.py`

### `executor/`
- `desktop_executor.py`
- `desktop_actions.py`

### `confirmation/`
- `confirmation_gate.py`

### `runtime/`
- `runtime_manager.py`
- `state_machine.py`

### `ui/`
- `visibility_mapper.py`

### `types/`
- `command.py`
- `target.py`
- `step.py`
- `action_result.py`
- `jarvis_error.py`
- `runtime_state.py`
- `clarification_request.py`
- `confirmation_request.py`
- `validation_result.py`
- `planned_command.py`

### `docs/`
- `product_rules.md`
- `command_model.md`
- `desktop_execution.md`
- `runtime_flow.md`
- `runtime_components.md`
- `desktop_actions.md`
- `session_context.md`
- `clarification_rules.md`
- `errors.md`
- `ui_visibility.md`
- `use_cases.md`

## Component-to-Module Mapping
| Runtime Component | Module | File |
| --- | --- | --- |
| Input Adapter | `input/` | `adapter.py` |
| Command Parser | `parser/` | `command_parser.py` |
| Command Validator | `validator/` | `command_validator.py` |
| Clarification Handler | `clarification/` | `clarification_handler.py` |
| Session Context Store | `context/` | `session_context.py` |
| Execution Planner | `planner/` | `execution_planner.py` |
| Desktop Executor | `executor/` | `desktop_executor.py` |
| Confirmation Gate | `confirmation/` | `confirmation_gate.py` |
| Runtime State Manager | `runtime/` | `runtime_manager.py` |
| User Visibility Layer | `ui/` | `visibility_mapper.py` |

Each runtime component has one primary implementation home.

## Core Interface Contracts
```text
parse_command(raw_input, session_context) -> Command
validate_command(command) -> ValidationResult
build_clarification(validation_issue, command) -> ClarificationRequest
apply_clarification(command, user_reply) -> Command
build_execution_plan(command) -> PlannedCommand
execute_step(step) -> ActionResult
request_confirmation(boundary) -> ConfirmationResult
transition_runtime(state, event) -> RuntimeState
```

Interface responsibilities:
- `parse_command`: produce preliminary `Command` only.
- `validate_command`: enforce command legality; return validated state or blocking issue.
- `build_clarification`: create one minimal clarification request from a validation/runtime issue.
- `apply_clarification`: patch only blocked command fields from user reply.
- `build_execution_plan`: produce ordered `execution_steps` with confirmation boundaries.
- `execute_step`: run one step and return one `ActionResult`.
- `request_confirmation`: return `approved`, `denied`, or `pending`; never auto-approve.
- `transition_runtime`: enforce legal state transitions only.

## Shared Types
| Type | Represents | Consumed By |
| --- | --- | --- |
| `Command` | Parsed/validated command contract | `parser`, `validator`, `clarification`, `planner`, `runtime`, `ui` |
| `Target` | Resolved target entity for actions | `parser`, `validator`, `planner`, `executor`, `ui` |
| `Step` | One executable unit in plan | `planner`, `executor`, `runtime`, `ui` |
| `ActionResult` | Result of one executed step | `executor`, `runtime`, `ui`, `errors` handling |
| `JarvisError` | Unified error contract | all runtime modules |
| `RuntimeState` | Current runtime lifecycle state | `runtime`, `ui`, `confirmation`, `clarification` |
| `ClarificationRequest` | Minimal clarification prompt contract | `validator`, `clarification`, `runtime`, `ui` |
| `ConfirmationRequest` | Confirmation boundary contract | `planner`, `confirmation`, `runtime`, `ui` |
| `ValidationResult` | Validator output contract | `validator`, `runtime`, `clarification`, `planner` |
| `PlannedCommand` | Validated command plus execution plan | `planner`, `runtime`, `executor`, `ui` |

All shared types must live in `types/` and remain free of UI-only logic.

## Dependency Rules
- Parser cannot call executor.
- Executor cannot mutate parser output shape.
- UI cannot control execution directly.
- Runtime manager is the only source of truth for active runtime state.
- Shared types must not contain UI-only logic.
- Dependencies must remain one-directional and minimal.

Allowed direction (high level):
- `input -> parser -> validator -> clarification/planner -> confirmation/executor -> runtime -> ui`
- `types` is shared but passive and has no runtime dependencies.

## MVP Constraints
- no plugin architecture
- no event bus
- no background worker system
- no multi-command scheduler
- no deep abstraction layers
- no speculative interfaces for future features
