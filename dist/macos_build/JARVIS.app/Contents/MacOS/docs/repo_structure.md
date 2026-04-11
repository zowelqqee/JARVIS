# JARVIS Repo Structure (Dual-Mode MVP)

## Purpose
Define the minimal codebase structure required to implement the supervised dual-mode assistant.

- The structure must follow runtime and interaction contracts.
- Each major responsibility must have one clear home.
- The repo must stay minimal and implementation-oriented.

## Top-Level Modules
### `input/`
- Purpose: normalize incoming user interaction into `raw_input`.
- Owns: input normalization and voice-to-text handoff boundary.
- Must not own: routing, parsing, validation, answering, execution, or UI logic.

### `interaction/`
- Purpose: route normalized input into command mode or question-answer mode.
- Owns: interaction routing and top-level interaction orchestration.
- Must not own: command parsing details, answer content, desktop execution, or UI rendering.

### `parser/`
- Purpose: build preliminary `Command` from routed command input.
- Owns: command intent/target/parameter extraction into command shape.
- Must not own: execution, confirmation decisions, answer generation, or runtime state control.

### `validator/`
- Purpose: enforce command legality before planning.
- Owns: confidence checks, target/parameter checks, intent/action legality checks.
- Must not own: clarification prompting logic, answering, execution, or UI output.

### `clarification/`
- Purpose: create and apply clarification updates.
- Owns: minimal clarification request generation and blocked-state patching from reply.
- Must not own: parsing from scratch, answering unrelated questions, execution, or runtime transitions.

### `context/`
- Purpose: hold short-lived active session context.
- Owns: current command context, recent resolved targets, blocked-state resume data, and recent grounded session context for status answers.
- Must not own: cross-session persistence, user profile memory, or decision policy.

### `planner/`
- Purpose: convert validated `Command` into executable steps.
- Owns: ordered `execution_steps`, confirmation boundaries, command `status_message`.
- Must not own: step execution, answer generation, runtime state transitions, or UI mapping.

### `executor/`
- Purpose: execute desktop actions one step at a time.
- Owns: action dispatch and `ActionResult` production for each step.
- Must not own: routing, parsing, answering, validation, clarification, or hidden fallback behavior.

### `confirmation/`
- Purpose: enforce command-level and step-level confirmation boundaries.
- Owns: confirmation request lifecycle (`pending`, `approved`, `denied`).
- Must not own: planning, answer generation, action execution, or automatic approval behavior.

### `qa/`
- Purpose: build grounded answers for question-mode inputs.
- Owns: question classification, source selection, capability catalog access, backend selection, and answer generation.
- Must not own: desktop execution, confirmation control, or command planning.

### `runtime/`
- Purpose: orchestrate command runtime flow and state transitions.
- Owns: command state machine, transition validity, active command lifecycle.
- Must not own: top-level interaction routing, UI rendering, answer generation, or desktop action internals.

### `ui/`
- Purpose: map interaction truth to visible user status.
- Owns: visibility mapping for command runtime state, prompts, failures, and answer payloads.
- Must not own: execution control decisions or command mutation.

### `types/`
- Purpose: define shared contracts.
- Owns: canonical type definitions used across modules.
- Must not own: UI-only behavior or component-specific business logic.

### `docs/`
- Purpose: hold product, runtime, question-answer, and behavior specs.
- Owns: contract documents.
- Must not own: runtime implementation code.

### `scripts/`
- Purpose: hold local developer wrappers for manual smoke checks and repeated operational commands.
- Owns: convenience entrypoints only.
- Must not own: runtime logic, routing policy, or answer-generation rules.

### `evals/`
- Purpose: hold centralized eval corpora and standalone evaluation runners.
- Owns: reproducible QA case datasets and reporting harnesses.
- Must not own: product runtime logic, routing policy, or unit-test-only assertions.

## Required Files Per Module
### `input/`
- `adapter.py`

### `interaction/`
- `interaction_router.py`
- `interaction_manager.py`

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

### `qa/`
- `answer_engine.py`
- `answer_backend.py`
- `answer_config.py`
- `deterministic_backend.py`
- `grounding.py`
- `debug_trace.py`
- `source_registry.py`
- `source_selector.py`
- `grounding_verifier.py`
- `capability_catalog.py`
- `llm_backend.py`
- `llm_provider.py`
- `llm_response_parser.py`
- `openai_responses_provider.py`
- `openai_responses_prompt.py`
- `openai_responses_schema.py`
- `openai_responses_parser.py`
- `openai_responses_transport.py`

Future-ready note:
- `llm_backend.py` stays disabled by default in v1 and exists only behind the same `answer_backend.py` seam.

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
- `interaction_kind.py`
- `runtime_state.py`
- `clarification_request.py`
- `confirmation_request.py`
- `validation_result.py`
- `planned_command.py`
- `question_request.py`
- `answer_result.py`
- `interaction_result.py`

### `docs/`
- `product_rules.md`
- `question_answer_mode.md`
- `command_model.md`
- `runtime_flow.md`
- `runtime_components.md`
- `session_context.md`
- `clarification_rules.md`
- `errors.md`
- `ui_visibility.md`
- `use_cases.md`
- `repo_structure.md`
- `llm_default_decision_gate.md`
- `qa_operator_guide.md`

### `scripts/`
- `run_openai_live_smoke.sh`

### `evals/`
- `qa_cases.json`
- `run_qa_eval.py`

## Component-to-Module Mapping
| Runtime / Interaction Component | Module | File |
| --- | --- | --- |
| Input Adapter | `input/` | `adapter.py` |
| Interaction Router | `interaction/` | `interaction_router.py` |
| Command Parser | `parser/` | `command_parser.py` |
| Command Validator | `validator/` | `command_validator.py` |
| Clarification Handler | `clarification/` | `clarification_handler.py` |
| Session Context Store | `context/` | `session_context.py` |
| Execution Planner | `planner/` | `execution_planner.py` |
| Desktop Executor | `executor/` | `desktop_executor.py` |
| Confirmation Gate | `confirmation/` | `confirmation_gate.py` |
| Answer Engine | `qa/` | `answer_engine.py`, `grounding.py`, `debug_trace.py`, `source_registry.py`, `source_selector.py`, `grounding_verifier.py`, `answer_config.py`, `openai_responses_prompt.py`, `openai_responses_schema.py`, `openai_responses_parser.py` |
| Command Runtime State Manager | `runtime/` | `runtime_manager.py`, `state_machine.py` |
| User Visibility Layer | `ui/` | `visibility_mapper.py` |

Each major component has one primary implementation home.

## Core Interface Contracts
```text
route_interaction(raw_input, session_context, runtime_state) -> InteractionResult
parse_command(raw_input, session_context) -> Command
validate_command(command) -> ValidationResult
build_clarification(validation_issue_or_routing_issue, command_or_input) -> ClarificationRequest
apply_clarification(command_or_input, user_reply) -> Command | string
build_execution_plan(command) -> PlannedCommand
execute_step(step) -> ActionResult
request_confirmation(boundary) -> ConfirmationResult
answer_question(raw_input_or_question_request, session_context, runtime_snapshot, backend_config?) -> AnswerResult
transition_runtime(state, event) -> RuntimeState
handle_interaction(raw_input, session_context) -> InteractionResult
```

Interface responsibilities:
- `route_interaction`: produce the top-level interaction decision only.
- `parse_command`: produce preliminary `Command` only.
- `validate_command`: enforce command legality; return validated state or blocking issue.
- `build_clarification`: create one minimal clarification request from a routing or command issue.
- `apply_clarification`: patch only blocked fields or blocked routing choice from user reply.
- `build_execution_plan`: produce ordered `execution_steps` with confirmation boundaries.
- `execute_step`: run one step and return one `ActionResult`.
- `request_confirmation`: return `approved`, `denied`, or `pending`; never auto-approve.
- `answer_question`: return a grounded read-only `AnswerResult`.
- answer backend selection is an internal QA concern and must not leak into routing contracts.
- grounding bundle selection and provider-specific request building remain internal QA concerns and must not leak into routing contracts.
- shared grounding verification and source-attribution policy remain internal QA concerns and must not leak into routing contracts.
- `transition_runtime`: enforce legal command runtime state transitions only.
- `handle_interaction`: orchestrate top-level dual-mode handling.

## Shared Types
| Type | Represents | Consumed By |
| --- | --- | --- |
| `Command` | Parsed/validated command contract | `interaction`, `parser`, `validator`, `clarification`, `planner`, `runtime`, `ui` |
| `Target` | Resolved target entity for actions | `parser`, `validator`, `planner`, `executor`, `ui` |
| `Step` | One executable unit in plan | `planner`, `executor`, `runtime`, `ui` |
| `ActionResult` | Result of one executed step | `executor`, `runtime`, `ui` |
| `JarvisError` | Unified error contract | all runtime and QA modules |
| `RuntimeState` | Current command lifecycle state | `runtime`, `ui`, `confirmation`, `clarification` |
| `ClarificationRequest` | Minimal clarification prompt contract | `interaction`, `validator`, `clarification`, `runtime`, `ui` |
| `ConfirmationRequest` | Confirmation boundary contract | `planner`, `confirmation`, `runtime`, `ui` |
| `ValidationResult` | Validator output contract | `validator`, `runtime`, `clarification`, `planner` |
| `PlannedCommand` | Validated command plus execution plan | `planner`, `runtime`, `executor`, `ui` |
| `QuestionRequest` | Structured question-answer request | `interaction`, `qa` |
| `AnswerResult` | Grounded answer output | `qa`, `interaction`, `ui` |
| `InteractionResult` | Top-level result for either command or question mode | `interaction`, `ui`, `cli` |

All shared types must live in `types/` and remain free of UI-only logic.

## Dependency Rules
- Interaction router may call parser or answer engine only through explicit routing boundaries.
- Parser cannot call executor.
- Parser cannot absorb question-answer logic.
- Executor cannot mutate parser output shape.
- QA modules cannot call planner or executor.
- A future LLM backend may call an external model API only through the QA boundary.
- A future LLM backend must not own routing, source selection policy, or execution authority.
- UI cannot control execution directly.
- Runtime manager is the only source of truth for active command runtime state.
- Interaction manager is the only source of truth for top-level command-vs-question dispatch.
- Shared types must not contain UI-only logic.
- Dependencies must remain one-directional and minimal.

Allowed direction (high level):
- `input -> interaction -> (parser -> validator -> clarification/planner -> confirmation/executor -> runtime) -> ui`
- `input -> interaction -> qa -> ui`
- `types` is shared but passive and has no runtime dependencies.

## Constraints
- no plugin architecture
- no event bus
- no background worker system
- no multi-command scheduler
- no deep abstraction layers
- no hidden answer-triggered execution path
