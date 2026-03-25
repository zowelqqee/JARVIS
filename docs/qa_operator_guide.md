# JARVIS QA Operator Guide

## Purpose
Provide one short operator-facing guide for running, debugging, and gating question-answer mode in supervised local environments.

Current product default:
- QA backend default: deterministic
- LLM backend: opt-in alpha only
- default LLM switch: blocked until `docs/llm_default_decision_gate.md` passes in the target environment

## Deterministic Path
Run the normal dual-mode CLI:
- `python3 cli.py`

Useful read-only helper commands:
- `qa backend`
- `qa model`
- `qa smoke`
- `qa gate`
- `qa gate strict`
- `qa smoke` now prints the live-smoke artifact path/status and whether open-domain live verification is already present
- `qa gate` now prints an offline rollout-gate precheck for the current `llm_env` candidate config
- `qa gate strict` does the same for `llm_env_strict` and prints the exact comparative gate command to run next

Deterministic sanity checks:
- `python3 -m evals.run_qa_eval`
- `python3 -m unittest tests.test_answer_engine tests.test_interaction_manager tests.test_cli_smoke`

## LLM Alpha Enablement
Opt in explicitly through environment variables.

Minimum env:
- `JARVIS_QA_BACKEND=llm`
- `JARVIS_QA_LLM_ENABLED=true`
- `JARVIS_QA_LLM_PROVIDER=openai_responses`
- `OPENAI_API_KEY=...`

Optional env:
- `JARVIS_QA_LLM_MODEL=gpt-5-nano`
- `JARVIS_QA_LLM_TIMEOUT_SECONDS=30`
- `JARVIS_QA_LLM_MAX_OUTPUT_TOKENS=800`
- `JARVIS_QA_LLM_REASONING_EFFORT=minimal`
- `JARVIS_QA_LLM_STRICT_MODE=true`
- `JARVIS_QA_LLM_MAX_RETRIES=1`
- `JARVIS_QA_LLM_FALLBACK_ENABLED=true`
- `JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED=true`
- `JARVIS_QA_DEBUG=1`

Notes:
- Do not enable LLM by default in product config.
- `JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED=true` is required before broader open-domain GPT answers are allowed; otherwise unsupported world-knowledge questions should still fail honestly.
- Keep deterministic fallback enabled for alpha experiments unless you are intentionally running a strict no-fallback diagnostic pass.

## Smoke Commands
Deterministic path:
- `python3 -m evals.run_qa_eval`

Interaction routing path:
- `python3 -m unittest tests.test_interaction_router tests.test_interaction_manager tests.test_cli_smoke`

Live OpenAI path:
- `scripts/run_openai_live_smoke.sh`
- `scripts/run_openai_live_smoke.sh llm_env`
- `scripts/run_openai_live_smoke.sh llm_env_strict`
- For open-domain live verification also set `JARVIS_QA_OPENAI_LIVE_OPEN_DOMAIN_ENABLED=1`
- For `llm_env` candidate matching also set `JARVIS_QA_OPENAI_LIVE_FALLBACK_ENABLED=1`
- For `llm_env_strict` keep the default no-fallback live smoke config, or set `JARVIS_QA_OPENAI_LIVE_FALLBACK_ENABLED=0` explicitly
- The script writes a rollout artifact to `JARVIS_QA_OPENAI_LIVE_ARTIFACT` or, by default, `tmp/qa/openai_live_smoke.json`
- Candidate-aware smoke runs now default to:
  - `tmp/qa/openai_live_smoke_llm_env.json`
  - `tmp/qa/openai_live_smoke_llm_env_strict.json`
- `qa gate`, `qa gate strict`, and raw comparative gate commands now resolve those candidate-specific artifact paths automatically when `JARVIS_QA_OPENAI_LIVE_ARTIFACT` is not set.
- Re-run the smoke immediately before the comparative gate so the artifact is fresh and matches the current model/profile config.

Comparative default-decision gate:
- `scripts/run_qa_rollout_gate.sh llm_env`
- `scripts/run_qa_rollout_gate.sh llm_env_strict`
- Raw form remains available:
  - `python3 -m evals.run_qa_eval --compare-profile deterministic --compare-profile llm_env --gate-candidate-profile llm_env`
- The gate now blocks env-backed candidates when the live smoke artifact is missing, unreadable, failed, or does not verify open-domain answering.
- The gate also blocks stale artifacts and artifacts captured under a different provider/model/strict/fallback/open-domain config.

Open-domain mock harness:
- `python3 -m evals.run_qa_eval --default-profile llm_open_domain_mock`

Relevant policy docs:
- `docs/general_qa_policy.md`
- `docs/general_qa_safety_boundaries.md`

## How To Diagnose Failures
`MODEL_BACKEND_UNAVAILABLE`
- Usually means `OPENAI_API_KEY` is missing, the LLM backend is disabled, or provider config is invalid.
- Check `qa backend`, `qa model`, `qa smoke`, and `qa gate`.

`ANSWER_GENERATION_FAILED`
- Usually means transport failure, provider status failure, malformed structured output, or schema mismatch.
- Re-run with `JARVIS_QA_DEBUG=1` and inspect the safe debug payload for `provider_response_parse`.

TLS / certificate failures
- Use `JARVIS_QA_OPENAI_CA_BUNDLE`, `SSL_CERT_FILE`, or `REQUESTS_CA_BUNDLE`.
- The live smoke wrapper already tries to populate a certifi bundle when available.

`ANSWER_NOT_GROUNDED`
- Usually means out-of-bundle sources, weak support text, or an answer that implied execution.
- Inspect `grounding_verification` and `source_selection` in QA debug output.

`INSUFFICIENT_CONTEXT`
- Usually means no active blocked command, no recent target, or no recent answer context for a safe follow-up.
- This is an honest product boundary, not something to bypass with fallback execution.

High fallback frequency
- Use the comparative gate report.
- If `llm_env` falls back too often, keep deterministic as the default and treat LLM as opt-in alpha only.

Gate precheck blocked
- Run `qa gate` or `qa gate strict` first.
- Fix missing API key, disabled open-domain config, stale/mismatched artifact, or missing open-domain live verification before spending time on the full comparative gate.

## Safe Debug Mode
Enable:
- `JARVIS_QA_DEBUG=1`

Current safe debug sections:
- `routing_decision`
- `question_classification`
- `source_selection`
- `provider_response_parse`
- `grounding_verification`
- `fallback`

Debug hygiene:
- no API keys
- no full answer bundle dumps by default
- only safe request ids, correlation ids, counts, statuses, and bounded diagnostics
