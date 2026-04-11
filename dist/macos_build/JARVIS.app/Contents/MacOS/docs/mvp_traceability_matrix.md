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
| Blocked-state fresh-command restart | New full command in blocked states restarts flow deterministically and does not execute blocked boundary step. | `tests/test_runtime_smoke.py::test_clarification_state_allows_fresh_command_restart`, `tests/test_runtime_smoke.py::test_confirmation_block_allows_fresh_command_restart` |
| Short-lived search-context safety | Recent search results are overwritten by newer search and cleared after unrelated completed commands. | `tests/test_runtime_smoke.py::test_recent_search_context_clears_after_unrelated_completed_command`, `tests/test_runtime_smoke.py::test_recent_search_context_persists_for_indexed_open_chain` |

## Visibility Contract Mapping

| Visibility Contract | Deterministic Rule | Tests |
| --- | --- | --- |
| `next_step_hint` | One hint max, structured precedence, no message-text parsing. | `tests/test_runtime_smoke.py::test_failed_followup_reference_unclear_uses_structured_hint`, `tests/test_runtime_smoke.py::test_failed_fallback_uses_generic_hint_when_no_specific_rule` |
| `search_results` | Result list is capped, includes total count, never invents data. | `tests/test_runtime_smoke.py::test_search_visibility_shows_capped_results_and_count` |
| `window_results` | Window list is capped, includes totals/filter, honest failure if unavailable. | `tests/test_runtime_smoke.py::test_list_windows_visibility_caps_results`, `tests/test_runtime_smoke.py::test_list_windows_failure_message_is_honest` |
| Optional field presence | Optional visibility fields are omitted when empty; blocked/success/failure payloads stay non-conflicting. | `tests/test_visibility_contract.py::test_completed_payload_omits_failure_and_hint_fields`, `tests/test_visibility_contract.py::test_awaiting_confirmation_payload_contains_single_blocked_hint`, `tests/test_visibility_contract.py::test_awaiting_clarification_payload_contains_question_and_hint`, `tests/test_visibility_contract.py::test_failed_payload_prefers_specific_structured_hint` |

## Parser/Validator Determinism Fixtures

| Risk Area | Deterministic Rule | Tests |
| --- | --- | --- |
| Overlapping phrasing precedence | `list_windows` / `search_local` / `prepare_workspace` are routed in explicit parser order. | `tests/test_parser_validator_contract.py::test_list_windows_phrase_wins_over_open_family`, `tests/test_parser_validator_contract.py::test_open_latest_markdown_in_folder_maps_to_search_then_open_shape`, `tests/test_parser_validator_contract.py::test_open_project_in_code_maps_to_prepare_workspace` |
| Alias + follow-up consistency | Alias and indexed follow-up phrases map to stable intent/target shapes. | `tests/test_parser_validator_contract.py::test_run_alias_maps_to_open_app`, `tests/test_parser_validator_contract.py::test_search_result_index_followup_is_deterministic` |
| Ambiguity and unsupported routing | Ambiguous phrases block with `MULTIPLE_MATCHES`; explicit unsupported phrases fail with `UNSUPPORTED_ACTION`. | `tests/test_parser_validator_contract.py::test_ambiguous_open_maps_to_multiple_matches`, `tests/test_parser_validator_contract.py::test_explicit_unsupported_window_management_is_not_clarified`, `tests/test_parser_validator_contract.py::test_search_result_ambiguous_followup_routes_to_multiple_matches` |

## Executor Reliability Fixtures

| Reliability Area | Deterministic Rule | Tests |
| --- | --- | --- |
| Confirmation boundary at executor edge | Steps marked `requires_confirmation` fail with `CONFIRMATION_REQUIRED` if called directly. | `tests/test_executor_contract.py::test_requires_confirmation_step_is_blocked` |
| URL validation contract | Invalid website URLs fail with `INVALID_URL`. | `tests/test_executor_contract.py::test_open_website_invalid_url_fails_with_invalid_url` |
| App running-state contract | `focus_app`/`close_app` require running app and fail with `APP_NOT_RUNNING` otherwise. | `tests/test_executor_contract.py::test_focus_app_not_running_returns_app_not_running`, `tests/test_executor_contract.py::test_close_app_not_running_returns_app_not_running` |
| Permission-classification contract | OS-permission failures map to `PERMISSION_DENIED`. | `tests/test_executor_contract.py::test_open_app_permission_denied_maps_to_permission_denied` |
| Window inspection error normalization | `list_windows` preserves canonical error codes and normalizes unknown codes to `EXECUTION_FAILED`. | `tests/test_executor_contract.py::test_list_windows_permission_denied_propagates`, `tests/test_executor_contract.py::test_list_windows_unknown_error_code_normalizes_to_execution_failed` |
| Unsupported window actions remain explicit | `focus_window` remains explicit `UNSUPPORTED_ACTION`. | `tests/test_executor_contract.py::test_focus_window_remains_explicitly_unsupported` |
| App resolution fallback remains strict and deterministic | `open_*` keeps explicit `APP_UNAVAILABLE` on unresolved apps, and uses deterministic bundle-path fallback only when available. | `tests/test_executor_contract.py::test_open_app_uses_bundle_path_fallback_when_name_lookup_fails`, `tests/test_executor_contract.py::test_open_file_with_explicit_app_uses_bundle_path_fallback`, `tests/test_executor_contract.py::test_open_app_without_bundle_fallback_remains_app_unavailable`, `tests/test_executor_contract.py::test_open_app_bundle_not_launchable_returns_app_unavailable` |

## Voice Reliability Fixtures

| Reliability Area | Deterministic Rule | Tests |
| --- | --- | --- |
| Voice helper crash/error normalization | Voice helper failures map to stable structured categories with concise actionable messages/hints. | `tests/test_voice_input_contract.py::test_negative_exit_code_maps_to_voice_helper_crash`, `tests/test_voice_input_contract.py::test_permission_denied_keeps_structured_hint`, `tests/test_voice_input_contract.py::test_unknown_positive_exit_without_detail_reports_exit_code` |

## Release Gate Commands
- `python3 -m compileall parser/command_parser.py validator/command_validator.py runtime/runtime_manager.py ui/visibility_mapper.py executor/desktop_executor.py input/voice_input.py tests/test_runtime_smoke.py tests/test_cli_smoke.py tests/test_use_case_parity.py tests/test_parser_validator_contract.py tests/test_executor_contract.py tests/test_visibility_contract.py tests/test_voice_input_contract.py`
- `python3 -m unittest tests/test_runtime_smoke.py tests/test_cli_smoke.py tests/test_use_case_parity.py tests/test_parser_validator_contract.py tests/test_executor_contract.py tests/test_visibility_contract.py tests/test_voice_input_contract.py`
