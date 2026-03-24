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
- `JARVIS_QA_DEBUG=1`

Notes:
- Do not enable LLM by default in product config.
- Keep deterministic fallback enabled for alpha experiments unless you are intentionally running a strict no-fallback diagnostic pass.

## Smoke Commands
Deterministic path:
- `python3 -m evals.run_qa_eval`

Interaction routing path:
- `python3 -m unittest tests.test_interaction_router tests.test_interaction_manager tests.test_cli_smoke`

Live OpenAI path:
- `scripts/run_openai_live_smoke.sh`

Comparative default-decision gate:
- `python3 -m evals.run_qa_eval --compare-profile deterministic --compare-profile llm_env --gate-candidate-profile llm_env`

## How To Diagnose Failures
`MODEL_BACKEND_UNAVAILABLE`
- Usually means `OPENAI_API_KEY` is missing, the LLM backend is disabled, or provider config is invalid.
- Check `qa backend`, `qa model`, and `qa smoke`.

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
