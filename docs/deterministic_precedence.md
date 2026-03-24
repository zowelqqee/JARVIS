# JARVIS Dual-Mode Deterministic Precedence Rules

## Interaction Routing Precedence
`route_interaction` resolves user inputs in this exact order:
1. confirmation reply forms when command runtime is `awaiting_confirmation`
2. clarification reply forms when command runtime is `awaiting_clarification`
3. explicit blocked-state status questions about the active blocked command
4. explicit executable command families
5. explicit grounded question families
5. mixed command/question forms -> clarification
6. fallback clarification or bounded unsupported question outcome

Rules:
- blocked replies outrank fresh routing
- blocked-state status questions may route to question mode only when they ask what the active block needs; they must not auto-resume execution
- a polite action request remains a command if execution is requested
- a how/what/why question remains a question unless execution is explicitly requested
- mixed requests must not silently answer and execute in the same pass

## Command Parser Precedence
After routing chooses the command branch, `parse_command` resolves command families in this exact order:
1. confirmation reply forms (`confirm` intent)
2. explicit clarification forms (`clarify` intent)
3. explicitly unsupported batch window-management forms (`switch_window` -> validator `UNSUPPORTED_ACTION`)
4. `list_windows` family (plain and filtered forms)
5. `search_local` family (including explicit open-after-search phrasing)
6. `prepare_workspace` family
7. close/focus/use follow-up families
8. open-family handling (targets, aliases, follow-ups)
9. fallback clarification with unknown target

## Question Classification Precedence
After routing chooses the question branch, `answer_question` classifies question families in this exact order:
1. `blocked_state`
2. `recent_runtime`
3. `runtime_status`
4. `capabilities`
5. `docs_rules`
6. `repo_structure`
7. `safety_explanations`
8. unsupported question outcome

Rules:
- blocked-state questions win over generic runtime-status questions when both are plausible
- recent-runtime questions win over generic runtime-status questions when both are plausible
- runtime-status questions win over generic docs questions when both are plausible
- capabilities questions win over repo-structure questions when the user asks what JARVIS supports
- unsupported question routing must fail honestly, not guess

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
- explicit routing ambiguity between question and command intent

All other validation/execution failures route to terminal `failed` state.

## Answer Failure Routing
Question-answer failures route in this order:
1. unsupported question scope -> `UNSUPPORTED_QUESTION`
2. missing required source -> `SOURCE_NOT_AVAILABLE`
3. insufficient runtime/session context -> `INSUFFICIENT_CONTEXT`
4. configured model backend unavailable -> `MODEL_BACKEND_UNAVAILABLE`
5. candidate answer lacks support -> `ANSWER_NOT_GROUNDED`
6. answer build failure -> `ANSWER_GENERATION_FAILED`

Rules:
- answer failures are terminal for the current question
- answer failures must not invoke planner or executor
- answer failures must not silently fall back to command execution

## Visibility Hint Precedence
`next_step_hint` uses one deterministic priority:
1. specific structured failure reason
2. specific blocked-state hint
3. specific answer-boundary hint
4. generic failure hint
5. no hint

Rules:
- one hint maximum
- no empty hint
- no hint on successful completion or successful answer
- no text parsing of human-readable messages for hint selection
