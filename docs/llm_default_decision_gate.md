# JARVIS LLM Default Decision Gate

## Purpose
Define the explicit gate that must pass before question-answer mode may switch from deterministic to model-backed default behavior.

Current rule:
- keep the product default on deterministic
- keep the LLM path opt-in
- do not switch the default based on anecdotal local success

## Required Comparison
Compare profiles on the same centralized QA corpus.

Recommended commands:
- Deterministic baseline:
  - `python3 -m evals.run_qa_eval --default-profile deterministic`
- Comparative gate with env-backed LLM profile:
  - `scripts/run_openai_live_smoke.sh llm_env`
  - `scripts/run_qa_rollout_gate.sh llm_env`
- Comparative gate with strict no-fallback env-backed LLM profile:
  - `scripts/run_openai_live_smoke.sh llm_env_strict`
  - `scripts/run_qa_rollout_gate.sh llm_env_strict`

Notes:
- `llm_env` uses current QA env settings and leaves deterministic fallback enabled.
- `llm_env_strict` uses current QA env settings with fallback disabled, so provider and grounding failures stay visible.
- raw comparative gate commands resolve the candidate-specific live-smoke artifact path automatically when `JARVIS_QA_OPENAI_LIVE_ARTIFACT` is unset.
- `llm_missing_key_fallback` is a harness/debug profile, not a candidate default profile.
- `llm_open_domain_mock` is a harness/debug profile for deterministic open-domain answer, warning, refusal, and provenance checks without a live API dependency.
- env-backed gate reviews now also read the live smoke artifact from `JARVIS_QA_OPENAI_LIVE_ARTIFACT` or the default path `tmp/qa/openai_live_smoke.json`.
- run `scripts/run_openai_live_smoke.sh` in the target environment before the comparative gate so the artifact is fresh.
- the gate also validates that the artifact matches the current candidate provider/model/strict/fallback/open-domain config instead of trusting any older green smoke.

## Metrics To Review
The gate compares at least these signals:
- routing safety regressions
- command-regression pass rate
- groundedness pass rate
- unsupported-question honesty
- safety-boundary cases for refusal and bounded sensitive answers
- source attribution quality
- open-domain answer pass rate
- refusal pass rate
- provenance correctness
- fallback frequency
- average interaction latency
- usage/cost proxy availability
- live smoke artifact health

Interpretation:
- routing safety regressions must remain zero because the LLM backend must not influence routing
- command regressions must remain zero because command runtime semantics are not allowed to drift
- unsupported-question honesty must stay explicit and bounded
- safety-boundary cases must keep refusing or bounding the right classes of requests
- source attribution quality must remain grounded and specific
- open-domain answer cases must stay available when that path is enabled
- refusal cases must stay explicit and policy-bounded
- provenance correctness must stay truthful for grounded vs model-backed answers
- fallback frequency must stay low enough that the LLM path is actually carrying the product path
- latency and usage must be measured in the target environment before any default switch discussion
- env-backed candidate profiles must have a green live smoke artifact
- the live smoke artifact must be fresh enough for rollout review
- the live smoke artifact must match the current candidate provider/model/strict/fallback/open-domain config
- if open-domain answering is enabled, the live smoke artifact must explicitly verify the open-domain path rather than only grounded QA

## Thresholds
Current default-switch thresholds:
- routing safety regressions: `0`
- command-regression pass rate: `100%`
- groundedness pass rate: `100%`
- unsupported-question honesty: `100%`
- source attribution quality: at least `95%`
- open-domain answer pass rate: `100%` when open-domain cases are in scope
- refusal pass rate: `100%` when refusal cases are in scope
- provenance correctness: `100%` when provenance-labeled answer cases are in scope
- fallback frequency: at most `5%`
- latency: must be measured on the candidate profile
- usage/cost proxy: must be available on the candidate profile
- live smoke artifact: must exist and be green for env-backed candidate profiles
- live smoke artifact freshness: at most `24h`
- live smoke artifact profile match: provider/model/strict/fallback/open-domain flags must match the candidate profile
- open-domain live verification: must exist when `JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED=true`

If any threshold fails:
- keep deterministic as the default profile
- keep LLM as opt-in alpha only

## Decision Rule
The default switch is allowed only when:
1. deterministic remains fully green on the corpus
2. the candidate LLM profile shows no routing or command-safety regressions
3. groundedness and unsupported-question honesty stay at threshold
4. source attribution quality stays at threshold
5. fallback frequency stays at threshold
6. latency and usage/cost proxy are measured in the target environment

If the candidate is better in quality but still fails these default-switch thresholds:
- it may remain opt-in alpha
- it must not become the product default

## Current Recommendation
- default product path: deterministic
- model-backed path: opt-in only
- default switch: blocked until the comparative gate passes cleanly in the target environment
