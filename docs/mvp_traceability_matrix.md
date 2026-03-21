# JARVIS MVP Traceability Matrix

## Purpose
- Lock deterministic MVP behavior against source-of-truth docs.
- Map each required behavior to runtime contracts and automated tests.
- Provide one release gate checklist for supervised local use.

## Contract Baseline
- Runtime entrypoint: `runtime/runtime_manager.py::RuntimeManager.handle_input`.
- Core deterministic contracts:
  - parser: `parser/command_parser.py::parse_command`
  - validator: `validator/command_validator.py::validate_command`
  - planner: `planner/execution_planner.py::build_execution_plan`
  - executor: `executor/desktop_executor.py::execute_step`
  - visibility: `ui/visibility_mapper.py::map_visibility`
- Stable visibility outputs:
  - `next_step_hint`
  - `search_results`
  - `window_results`

## Use-Case Parity Mapping

| Doc Use Case | Deterministic Runtime Behavior | Primary Tests |
| --- | --- | --- |
| Open Applications | Multi-target open parses to `open_app`, executes step-per-app, completes. | `tests/test_use_case_parity.py::test_use_case_open_applications` |
| Open File / Folder | Explicit folder/file target parses, validates, and completes as one open step. | `tests/test_use_case_parity.py::test_use_case_open_file_or_folder` |
| Workspace Setup | Workspace phrasing normalizes to short explicit `prepare_workspace` sequence. | `tests/test_use_case_parity.py::test_use_case_workspace_setup` |
| Window Management | Unsupported batch window-management phrases fail as structured `UNSUPPORTED_ACTION`. | `tests/test_use_case_parity.py::test_use_case_window_management_is_explicitly_unsupported` |
| Search and Open | `latest/newest` open phrasing executes deterministic `search_local -> open_file`. | `tests/test_use_case_parity.py::test_use_case_search_and_open` |
| Clarification Flow | Ambiguous commands block in `awaiting_clarification` with a single clarification request. | `tests/test_use_case_parity.py::test_use_case_clarification_flow_blocks_on_ambiguity` |
| Safe Failure | Missing/unavailable targets fail explicitly with structured failure and message. | `tests/test_use_case_parity.py::test_use_case_safe_failure_reports_missing_target` |
| Context Follow-up | Follow-up command after completion runs as a fresh supervised command using short-lived context. | `tests/test_use_case_parity.py::test_use_case_context_follow_up` |

## Runtime Invariant Mapping

| Invariant | Runtime Rule | Tests |
| --- | --- | --- |
| One active command | Runtime stores one `active_command`; blocked states resume against that command only. | `tests/test_runtime_smoke.py::test_clarification_block_and_resume_preserves_command_context` |
| No hidden continuation | Blocked states require explicit follow-up input (`awaiting_clarification` / `awaiting_confirmation`). | `tests/test_runtime_smoke.py::test_confirmation_approval_executes_only_after_approval` |
| Confirmation denial is terminal for current flow | Denial transitions to `cancelled` and executes no blocked step. | `tests/test_runtime_smoke.py::test_confirmation_denial_cancels_without_executing_blocked_step` |
| Terminal-state restart behavior | New input after terminal states starts a fresh supervised pass. | `tests/test_runtime_smoke.py::test_follow_up_after_completion_is_a_new_command` |

## Visibility Contract Mapping

| Visibility Contract | Deterministic Rule | Tests |
| --- | --- | --- |
| `next_step_hint` | One hint max, structured precedence, no message-text parsing. | `tests/test_runtime_smoke.py::test_failed_followup_reference_unclear_uses_structured_hint`, `tests/test_runtime_smoke.py::test_failed_fallback_uses_generic_hint_when_no_specific_rule` |
| `search_results` | Result list is capped, includes total count, never invents data. | `tests/test_runtime_smoke.py::test_search_visibility_shows_capped_results_and_count` |
| `window_results` | Window list is capped, includes totals/filter, honest failure if unavailable. | `tests/test_runtime_smoke.py::test_list_windows_visibility_caps_results`, `tests/test_runtime_smoke.py::test_list_windows_failure_message_is_honest` |

## Release Gate Commands
- `python3 -m compileall parser/command_parser.py validator/command_validator.py runtime/runtime_manager.py ui/visibility_mapper.py executor/desktop_executor.py tests/test_runtime_smoke.py tests/test_cli_smoke.py tests/test_use_case_parity.py`
- `python3 -m unittest tests/test_runtime_smoke.py tests/test_cli_smoke.py tests/test_use_case_parity.py`

