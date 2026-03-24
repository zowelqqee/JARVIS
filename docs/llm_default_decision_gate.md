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
  - `python3 -m evals.run_qa_eval --compare-profile deterministic --compare-profile llm_env --gate-candidate-profile llm_env`
- Comparative gate with strict no-fallback env-backed LLM profile:
  - `python3 -m evals.run_qa_eval --compare-profile deterministic --compare-profile llm_env_strict --gate-candidate-profile llm_env_strict`

Notes:
- `llm_env` uses current QA env settings and leaves deterministic fallback enabled.
- `llm_env_strict` uses current QA env settings with fallback disabled, so provider and grounding failures stay visible.
- `llm_missing_key_fallback` is a harness/debug profile, not a candidate default profile.

## Metrics To Review
The gate compares at least these signals:
- routing safety regressions
- command-regression pass rate
- groundedness pass rate
- unsupported-question honesty
- source attribution quality
- fallback frequency
- average interaction latency
- usage/cost proxy availability

Interpretation:
- routing safety regressions must remain zero because the LLM backend must not influence routing
- command regressions must remain zero because command runtime semantics are not allowed to drift
- unsupported-question honesty must stay explicit and bounded
- source attribution quality must remain grounded and specific
- fallback frequency must stay low enough that the LLM path is actually carrying the product path
- latency and usage must be measured in the target environment before any default switch discussion

## Thresholds
Current default-switch thresholds:
- routing safety regressions: `0`
- command-regression pass rate: `100%`
- groundedness pass rate: `100%`
- unsupported-question honesty: `100%`
- source attribution quality: at least `95%`
- fallback frequency: at most `5%`
- latency: must be measured on the candidate profile
- usage/cost proxy: must be available on the candidate profile

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
