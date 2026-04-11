# JARVIS General QA Policy

## Purpose
Define the product boundaries for broader GPT-backed question answering beyond the current grounded-local QA scope.

This document is policy for the planned expansion described in `GPT_QA_PLAN.md`.
It does not mean that open-domain GPT answering is already the default shipped path.
Detailed boundary rules live in `docs/general_qa_safety_boundaries.md`.

Current shipped/default state:
- grounded local QA is the default product path
- broader GPT answering is a staged expansion, not yet the default

## Product Positioning
JARVIS remains a supervised desktop assistant.

Broader question answering changes only the read-only `question` surface:
- it does not turn JARVIS into an autonomous agent
- it does not change `command` ownership of execution
- it does not give model answers authority over runtime state

## Answer Classes
Question mode may eventually contain multiple answer classes:

1. `grounded_local`
- based on local docs, runtime state, session context, or capability metadata
- should expose local sources and support claims

2. `open_domain_model`
- based on model knowledge rather than local repository/runtime grounding
- must not expose fake local citations
- must be clearly labeled as model-backed / model-knowledge output

Later, a separate `tool_augmented` class may exist, but it is out of scope for the first general-QA rollout.

## Hard Boundaries
Broader GPT answering must not:
- execute actions
- create `Command` objects or `execution_steps`
- approve or deny confirmation
- resume blocked execution
- override routing precedence
- silently browse the internet
- fabricate local sources or pretend to quote docs/runtime state that were not provided
- create long-term user memory or hidden personalization

## Routing Policy
Top-level routing remains:
1. blocked confirmation reply
2. blocked clarification reply
3. explicit command
4. mixed question + action -> clarification
5. question

Broader GPT answering may widen what happens inside step 5 only.
It must not absorb explicit execution requests.

Examples:
- `Open Safari` -> command
- `What can you do and open Safari` -> clarification
- `Why are you waiting?` while blocked -> question grounded in blocked runtime state
- `Why is the sky blue?` -> candidate for broader GPT-backed question mode once enabled

## Provenance Policy
Every answer must be truthful about where it came from.

Rules:
- grounded local answers should show local sources
- broader model-backed answers should show model provenance instead of fake sources
- model answers must not imply access to current runtime state unless that state was explicitly supplied
- model answers must not imply access to current internet state unless a later explicit web-enabled path exists

## Safety Policy
Broader GPT answering must remain read-only and bounded.

It must refuse or tightly bound:
- self-harm facilitation
- illegal or dangerous wrongdoing assistance
- extreme medical/legal/financial overclaim
- instructions that would effectively bypass execution safety through question phrasing

For temporally unstable questions, such as current events or changing public facts:
- without web tools, answers must be explicitly bounded
- the system should acknowledge possible staleness or uncertainty

## Mixed Interaction Policy
Question mode must not silently answer and execute in one pass.

Examples:
- `Explain quantum mechanics and open Safari` -> clarification
- `Answer first` after that clarification -> answer path only
- `Execute the command` after that clarification -> command path only

## Rollout Policy
Recommended stages:

1. `alpha_opt_in`
- flag-gated
- explicit provenance required
- no default switch

2. `beta_question_default`
- broader GPT answering may become default for questions
- grounded local answering still preferred for system/runtime/repo questions

3. `stable`
- only after eval, manual verification, and operator readiness pass

## Evaluation Expectations
Before any wider rollout, review:
- command safety regressions
- mixed-input regressions
- refusal quality
- provenance correctness
- latency
- cost / usage visibility
- provider availability and fallback behavior

## Non-Goals
This policy does not authorize:
- web search by default
- arbitrary repo-agent behavior
- hidden memory
- answer-triggered execution
- weakening desktop supervision rules
