# JARVIS MVP Release Gate

## Hard Release Criteria
- No command regressions in parser, validator, planner, executor, runtime, or CLI shell interception.
- Deterministic QA remains the default product path.
- Question mode stays grounded, read-only, and separate from command runtime semantics.
- Supervised blocked-state behavior (`awaiting_clarification`, `awaiting_confirmation`) remains intact.
- All contract suites and centralized evals are green.
- Live OpenAI smoke is green in the target environment before making model-backed readiness claims.
- Comparative LLM default-decision gate still recommends deterministic unless `docs/llm_default_decision_gate.md` passes.
- Visibility payload remains stable and additive-only.
- Docs match the actual runtime, QA, and operator workflow.

## Mandatory Automated Checks
- `python3 -m evals.run_qa_eval`
- `python3 -m unittest discover -s tests`

If validating model-backed alpha readiness:
- `scripts/run_openai_live_smoke.sh llm_env`
- `scripts/run_openai_live_smoke.sh llm_env_strict`
- `scripts/run_qa_rollout_gate.sh llm_env`
- `scripts/run_qa_rollout_gate.sh llm_env_strict`

## Manual Verification Checklist (Scripted Local Pass)
- Open apps flow (`open Telegram and Safari`) completes predictably.
- Open folder/file flow completes or fails explicitly.
- Workspace flow stays short and deterministic.
- Search-only flow shows capped structured results.
- Search-then-open flow shows both search and open step outcomes.
- Clarification block requires explicit reply and resumes deterministically.
- Confirmation block requires explicit approval/denial and preserves boundaries.
- Fresh command while blocked restarts cleanly and does not execute previously blocked step.
- Capability question returns grounded read-only output with sources.
- Docs question follow-ups (`Explain more`, `Which source?`) reuse recent grounded answer context.
- Blocked-state question explains the boundary without approving or resuming execution.
- Recent-runtime question answers only from current session/runtime context.
- Mixed question + action input asks for routing clarification instead of answering and executing together.
- Unsupported window operations remain explicit failures with no fake success.
- CLI shell commands (`help`, `voice`, `speak on/off`, `reset`, `quit`, `qa backend`, `qa model`, `qa smoke`, `qa gate`, `qa gate strict`) stay intercepted and deterministic.
- Voice failure diagnostics stay explicit and actionable (no generic `Voice capture failed` path).
- Use `docs/manual_verification_commands.md` for the dual-mode scripted pass.
- Use `docs/qa_operator_guide.md` for LLM alpha enablement, live smoke, and failure diagnosis.
