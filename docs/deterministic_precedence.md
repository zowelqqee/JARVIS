# JARVIS MVP Deterministic Precedence Rules

## Parser Precedence
`parse_command` resolves command families in this exact order:
1. confirmation reply forms (`confirm` intent)
2. explicit clarification forms (`clarify` intent)
3. explicitly unsupported batch window-management forms (`switch_window` -> validator `UNSUPPORTED_ACTION`)
4. `list_windows` family (plain and filtered forms)
5. `search_local` family (including explicit open-after-search phrasing)
6. `prepare_workspace` family
7. close/focus/use follow-up families
8. open-family handling (targets, aliases, follow-ups)
9. fallback clarification with unknown target

## Validation Routing Precedence
`validate_command` applies this deterministic order:
1. unsupported/unknown intent check
2. confidence threshold check
3. intent-specific structural checks
4. explicit follow-up/reference error mapping

Validation output is always structured:
- `valid=True` + `validated_command`
- or `valid=False` + canonical `JarvisError`

## Runtime Block/Fail Routing
Runtime clarification block is allowed only for:
- `LOW_CONFIDENCE`
- `MISSING_PARAMETER`
- `TARGET_NOT_FOUND`
- `MULTIPLE_MATCHES`
- `FOLLOWUP_REFERENCE_UNCLEAR`

All other validation/execution failures route to terminal `failed` state.

## Visibility Hint Precedence
`next_step_hint` uses one deterministic priority:
1. specific structured failure reason
2. specific blocked-state hint
3. generic failure hint
4. no hint

Rules:
- one hint maximum
- no empty hint
- no hint on successful completion
- no text parsing of human-readable messages for hint selection

