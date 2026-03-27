# GPT QA Expansion Plan

**Стартовая точка**
- `QA v1` уже работает как grounded read-only mode поверх `InteractionManager`.
- `Command` остаётся execution-only контрактом.
- routing уже разделяет `command`, `question`, `clarification`.
- deterministic grounded answers и opt-in OpenAI backend уже есть.
- текущий product scope специально ограничен локальными docs/runtime/session sources.

**Что меняется в этом цикле**
Цель нового цикла: расширить `question` mode от grounded QA к general-purpose GPT-backed answers.

Новая product-цель:
1. JARVIS умеет отвечать не только по системе, но и на произвольные пользовательские вопросы.
2. Command safety model при этом не ослабевает.
3. GPT answers не становятся скрытым execution/planning path.
4. grounded answers и open-domain GPT answers остаются различимыми и объяснимыми.
5. rollout идёт по staged launch, а не через одномоментный default switch.

**Главный принцип**
`Question` остаётся отдельной top-level interaction веткой.

Это значит:
- не превращать general QA в `Command` intent
- не пускать GPT в routing decision как source of truth
- не давать GPT менять runtime state
- не давать GPT инициировать hidden execution
- не смешивать grounded local answers и model-knowledge answers так, будто это одно и то же

## Предлагаемая целевая модель

В question mode появляются два answer класса:

1. `grounded_local`
- ответы по docs/runtime/session/repo, как сейчас
- со sources и support-attributions

2. `open_domain_model`
- ответы на произвольные вопросы через GPT
- без fake local sources
- с явной provenance-маркировкой: ответ дан model knowledge path, а не local grounding

Опционально позже:

3. `tool_augmented`
- model + retrieval/web/search/tooling
- не делать в первом цикле этого плана

## Product Invariants

Сохранить без изменений:
- `InteractionManager` остаётся top-level orchestrator
- `RuntimeManager` остаётся только командным
- blocked confirmation / blocked clarification precedence сохраняется
- mixed question + action остаётся clarification, а не hidden multi-action
- question mode остаётся read-only
- answer mode не может подтверждать, отменять или продолжать execution

Новые инварианты:
- любой answer должен иметь явный provenance class
- open-domain answer не должен притворяться grounded local answer
- uncertainty / no-answer / safety refusal должны быть честными
- general GPT answer не должен silently pull internet unless later explicitly enabled

**Рекомендуемый порядок**
1. Product Contract for General QA
2. Answer Taxonomy and Final Contracts
3. Open-Domain GPT Backend
4. Routing and Fallback Policy
5. UX / Visibility / Provenance
6. Eval Harness Expansion
7. Safety and Abuse Boundaries
8. Rollout Gate and Release Readiness

## Статус на 2026-03-25

Текущий уровень проекта:
- rollout stage: `alpha_opt_in`
- implementation stage: внутри `8. Rollout Gate and Release Readiness`
- default switch status: `beta_question_default` ещё не готов; deterministic path остаётся product default

Статус по шагам плана:
- `1. Product Contract for General QA` — `done`
  - product/docs слой уже зафиксирован в `docs/product_rules.md`, `docs/question_answer_mode.md`, `docs/general_qa_policy.md`
- `2. Answer Taxonomy and Final Contracts` — `done`
  - `answer_kind` / `provenance` уже есть в `types/answer_result.py`; visibility/presenter поддерживают grounded vs model-backed answers
- `3. Open-Domain GPT Backend` — `done (flag-gated)`
  - `open_domain_general` classification, отдельные prompt/schema/parser модули и provider seam уже есть
- `4. Routing and Fallback Policy` — `mostly_done`
  - blocked-state precedence, mixed question+action clarification и honest failure для unavailable open-domain backend уже реализованы
  - дополнительная hardening-логика может ещё приехать в рамках safety stage
- `5. UX / Visibility / Provenance` — `mostly_done`
  - CLI/presenter уже показывают `answer-kind`, `provenance`, `warning`
  - speech/history polish остаётся как доработка, а не как blocker для alpha
- `6. Eval Harness Expansion` — `mostly_done`
  - eval corpus и summary/gate metrics уже покрывают grounded path, open-domain answers, refusals, provenance correctness и fallback
  - остаётся расширение env-backed/live coverage, чтобы mock harness не был единственным general-QA signal
- `7. Safety and Abuse Boundaries` — `mostly_done`
  - policy doc, safety-tagging, prompt-level boundary hints и eval/test coverage для refusal, bounded sensitive answers и temporally unstable warnings уже есть
  - остаётся env-backed/live verification, чтобы safety readiness не опиралась только на mock harness
- `8. Rollout Gate and Release Readiness` — `in_progress`
  - rollout stages, thresholds, comparative gate, operator guide, manual verification checklist и live-smoke contracts уже оформлены
  - comparative gate теперь читает live-smoke artifact для env-backed/open-domain readiness, проверяет freshness и match с текущим provider/model/strict/fallback/open-domain config, а не опирается только на mock/manual contract coverage
  - `qa smoke` helper теперь показывает artifact path/status и наличие open-domain live verification для operator workflows
  - добавлены `qa gate` и `qa gate strict` helper-команды для offline precheck обоих candidate profiles до полного comparative gate
  - live-smoke artifact теперь различает `llm_env` vs `llm_env_strict` через config flags, а не только по model/open-domain
  - добавлены candidate-aware wrapper scripts для live smoke и comparative gate, чтобы `llm_env` / `llm_env_strict` прогонялись через разные artifact paths и готовые команды
  - `llm_env` compare profile теперь реально использует current env model/strict/retry/token settings, а не частичный default-only subset
  - raw compare flow и CLI precheck теперь тоже автоматически резолвят candidate-specific artifact paths, так что wrapper scripts нужны для удобства, а не для корректности
  - candidate-aware live smoke теперь наследует current QA env model/strict/open-domain/api-key-env defaults, так что следующий live step ближе к реальному env-backed profile
  - comparative gate report теперь показывает failing-case samples для non-green profiles, включая source counts и short answer previews, чтобы rollout triage не упирался только в агрегированные percentages
  - `2026-03-25`: выполнен реальный env-backed live smoke для `llm_env` и `llm_env_strict`; оба smoke-прогона дали green artifact в текущем окружении
  - `2026-03-25`: выполнен реальный env-backed comparative gate для `llm_env` и `llm_env_strict`; это уже не purely local readiness, а фактическая проверка candidate profiles против live provider path
  - после hardening grounded/general prompts, parser fallback for policy warnings, gate logic, и eval contracts open-domain live verification уже подтверждена не только локально, но и на реальном env-backed provider path
  - `2026-03-25`: повторный live smoke с `JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED=true` реально прогнан и остаётся green для обоих profiles: `llm_env` и `llm_env_strict`
  - `2026-03-25`: `llm_env_strict` дал полностью green env-backed comparative gate with `default switch allowed: yes`, `grounding pass rate: 12/12`, `open-domain answer pass rate: 5/5`, `refusal pass rate: 2/2`, `fallback frequency: 0/19`, `open-domain live verification: yes`
  - `2026-03-25`: `llm_env` остаётся non-green и нестабильным по reruns; после реального open-domain verification он всё ещё oscillates между semantic/open-domain mismatches и occasional grounded regressions, поэтому `recommended default profile` остаётся deterministic
  - added repeated rollout stability sweep (`scripts/run_qa_rollout_stability.sh`) so release readiness can measure blocker frequency across multiple env-backed gate runs instead of trusting one isolated green rerun
  - `2026-03-25`: targeted strict env-backed reruns для `route_runtime_status_with_folder_context`, `route_answer_follow_up_explain_more` и `route_answer_follow_up_sources` после prompt/eval hardening снова прошли green на live provider path
  - `2026-03-25`: повторный strict stability sweep в правильном env-backed режиме на current HEAD дал `2/2` gate passes; strict candidate сейчас выглядит repeatable green, а не one-off success
  - `2026-03-25`: повторный non-strict stability sweep на current HEAD всё ещё дал только `1/2` gate passes; блокирующий rerun снова упал по `grounding pass rate`, `open-domain answer pass rate` и `candidate grounding quality regressed versus deterministic baseline`
  - `2026-03-26`: свежий env-backed live smoke снова реально прогнан для `llm_env` и `llm_env_strict`; оба smoke-прогона остались green с open-domain verification на текущем окружении
  - `2026-03-26`: свежие env-backed comparative gates для `llm_env` и `llm_env_strict` оба дали `default switch allowed: yes` на current HEAD
  - `2026-03-26`: после hardening blocked-state prompt guidance и payload contract strict blocker `route_blocked_state_question` вернулся в green с `3` source_attributions и explicit read-only confirmation boundary
  - `2026-03-26`: repeated env-backed stability sweeps на свежих artifacts дали `2/2` gate passes и для `llm_env`, и для `llm_env_strict`
  - добавлен offline CLI helper `qa beta`, который сводит current stage/default hold, candidate live-smoke readiness и latest candidate-specific stability evidence по `llm_env` / `llm_env_strict`
  - `2026-03-26`: rollout stability теперь пишет machine-readable candidate artifacts (`tmp/qa/rollout_stability_llm_env.json`, `tmp/qa/rollout_stability_llm_env_strict.json`), а `qa beta` умеет их читать
  - `2026-03-26`: более поздние same-day repeated stability reruns снова сорвались и записали fresh red artifacts: `llm_env` дал `0/2` gate passes с blocker'ами по `open-domain answer pass rate` и `fallback frequency`, `llm_env_strict` дал `0/2` gate passes с blocker'ами по `open-domain answer pass rate` и occasional grounded regression
  - `2026-03-26`: fallback-case aggregation в stability artifacts была tightened так, чтобы она считалась по тем же candidate-scoped answer results, что и `fallback_total`; `qa beta` теперь показывает latest blocker/fallback summaries из artifacts без profile-override noise
  - `2026-03-26`: после этого fix и повторных same-day reruns latest stability artifacts снова вернулись в green и сейчас показывают `2/2` gate passes и для `llm_env`, и для `llm_env_strict`
  - `2026-03-26`: добавлен offline beta-readiness record builder `python3 -m qa.beta_readiness`, который собирает current technical evidence из latest smoke/stability artifacts, предпочитает `llm_env_strict` как cleaner no-fallback candidate, и умеет писать machine-readable decision artifact `tmp/qa/beta_readiness.json`
  - `2026-03-26`: `qa beta` теперь показывает не только latest technical evidence, но и recommended candidate plus recorded manual/product approval evidence из beta-readiness artifact, если он есть
  - `2026-03-26`: `qa beta` теперь также cross-check'ит recorded beta-readiness artifact against latest smoke/stability evidence и помечает recorded sign-off как stale, если chosen candidate больше не technical-ready или drift'нул относительно latest recommendation
  - `2026-03-26`: beta-readiness artifact теперь хранит per-candidate smoke/stability snapshot metadata (`created_at`), а `qa beta` валидирует recorded sign-off против exact latest evidence snapshot, а не только против candidate name/status
  - `2026-03-26`: beta-readiness artifact теперь хранит ещё и per-candidate smoke/stability sha256 fingerprints, так что `qa beta` ловит evidence drift даже если artifact был переписан без смены timestamp
  - `2026-03-26`: добавлен machine-readable manual beta checklist helper `python3 -m qa.manual_beta_checklist` c artifact `tmp/qa/manual_beta_checklist.json`; `qa beta` и `qa.beta_readiness` теперь учитывают его как отдельный release-decision input вместо голого manual boolean
  - `2026-03-26`: beta-readiness artifact теперь хранит ещё и exact manual checklist snapshot/fingerprint; `qa beta` помечает recorded beta sign-off как stale, если `manual_beta_checklist.json` drift'нул после sign-off
  - `2026-03-26`: добавлен machine-readable beta release-review helper `python3 -m qa.beta_release_review` c artifact `tmp/qa/beta_release_review.json`; он выносит `latency review`, `cost review`, `operator sign-off` и `product approval` из transient CLI booleans в отдельный offline evidence layer
  - `2026-03-26`: `qa.beta_readiness` теперь опирается на оба supporting artifacts, `tmp/qa/manual_beta_checklist.json` и `tmp/qa/beta_release_review.json`, а `qa beta` считает recorded beta sign-off stale, если drift'нул и release-review snapshot/fingerprint
  - `2026-03-26`: legacy shortcut flags в `python3 -m qa.beta_readiness` удалены; consolidated readiness record теперь собирается только из artifact-based evidence, а не из ручных boolean overrides
  - `2026-03-26`: `beta_release_review.json` теперь хранит exact manual-checklist snapshot/fingerprint; `qa beta` и `qa.beta_readiness` считают release review stale, если после review drift'нул `manual_beta_checklist.json`
  - `2026-03-26`: для `manual_beta_checklist.json` и `beta_release_review.json` добавлены freshness/age checks; `qa beta` теперь показывает `fresh=yes|no|n/a` по supporting artifacts, а `qa.beta_readiness` блокируется, если manual/release evidence старее rollout freshness window
  - `2026-03-26`: release-review consistency дополнительно tightened: `qa beta` и `qa.beta_readiness` теперь считают `beta_release_review.json` stale не только при manual-checklist fingerprint/snapshot drift, но и если latest `manual_beta_checklist.json` сам уже вышел за freshness window
  - `2026-03-26`: `qa beta` теперь печатает ещё и `manual checklist pending items` / `release review pending checks`, чтобы manual beta pass и release sign-off были actionable прямо из CLI, а не только через docs
  - `2026-03-26`: те же `pending manual items` / `pending release-review checks` теперь записываются и в `qa.beta_readiness` record, так что final offline decision artifact остаётся actionable even when supporting artifacts are still missing/incomplete
  - `2026-03-26`: consistency для уже записанного `beta_readiness.json` тоже tightened: `qa beta` теперь invalidates recorded beta sign-off, если latest `manual_beta_checklist.json` или `beta_release_review.json` просто состарились по freshness window, даже без fingerprint drift
  - `2026-03-26`: `qa beta` теперь ещё и строит incremental manual/release commands из pending work: для partial artifacts он предлагает добить только недостающие `--pass ...` / review flags, а для missing/stale artifacts остаётся на full rerun command
  - `2026-03-26`: это правило tightened для stale partial artifacts тоже: incremental commands теперь предлагаются только для свежих partial artifacts; если partial manual/release evidence уже stale, `qa beta` снова требует полный rerun, а не “добить хвост”
  - `2026-03-26`: `qa.beta_readiness` repaired and tightened too: helper снова собирает собственные manual/release command suggestions, пишет `next_step_reason`, и когда supporting evidence уже complete, ведёт прямо в финальный `python3 -m qa.beta_readiness --candidate-profile ... --write-artifact`, а не только в generic blockers
  - `2026-03-26`: финальный write path тоже tightened: `python3 -m qa.beta_readiness --write-artifact` теперь требует явный `--candidate-profile` и отказывается писать `tmp/qa/beta_readiness.json`, если record всё ещё blocked, так что final sign-off больше не может быть случайно записан как incomplete snapshot
  - `2026-03-26`: read path tightened symmetrically: `qa beta` теперь считает legacy `beta_readiness.json` без `candidate_selection_source=explicit` stale even if the rest of the artifact is green, и печатает recorded candidate selection source отдельно, чтобы final sign-off всегда был привязан к явному operator choice
  - `2026-03-26`: та же explicit-choice защита теперь протянута и в `beta_release_review`: write path требует явный `--candidate-profile`, artifact пишет `candidate_selection_source`, а `qa beta` / `qa.beta_readiness` теперь считают legacy release-review artifact без explicit candidate selection stale
  - `2026-03-26`: supporting release helpers тоже стали self-contained: `python3 -m qa.manual_beta_checklist` теперь печатает/пишет pending manual items и next-step command, а `python3 -m qa.beta_release_review` печатает/пишет manual/review pending work и next-step command; если manual evidence stale или missing, release-review helper честно ведёт обратно к full checklist rerun, а не к фиктивному добиванию review flags
  - `2026-03-26`: manual beta checklist helper теперь печатает ещё и pending scenario guide с sample prompt / env hint / expected outcome для каждого непрошедшего item id; тот же mapping явно зафиксирован в `docs/manual_verification_commands.md`, чтобы основной remaining blocker — реальный manual beta pass — можно было закрывать без implicit knowledge
  - `2026-03-26`: этот manual guide протянут и в higher-level release helpers: `qa beta` теперь явно печатает guide command `python3 -m qa.manual_beta_checklist`, а `python3 -m qa.beta_readiness` хранит/печатает guide command, verification doc и pending scenario guide в своём record, так что manual blocker виден не только в checklist helper, но и в stage-8 summary surfaces
  - `2026-03-26`: тот же scenario-aware manual guide теперь зеркалится и в `python3 -m qa.beta_release_review`; blocked release-review helper показывает guide command, verification doc и pending scenario guide, так что все три release-decision surfaces (`qa.manual_beta_checklist`, `qa.beta_release_review`, `qa.beta_readiness`) согласованно ведут к реальному manual pass
  - `2026-03-26`: те же release-decision helpers теперь доступны и в interactive shell: `python3 cli.py` перехватывает `qa checklist`, `qa release review`, `qa readiness` как read-only aliases для manual checklist / release review / beta readiness summaries, так что stage 8 можно инспектировать из одного CLI surface без отдельного `python3 -m ...`
  - `2026-03-26`: `qa beta` тоже стал self-contained по главному operational blocker: когда manual checklist pending, он теперь печатает не только item ids и module command, но и helper alias `qa checklist` плюс pending scenario guide, так что top-level beta summary сам ведёт к реальному manual pass
  - `2026-03-27`: real scripted manual beta pass завершён и записан в `tmp/qa/manual_beta_checklist.json`; artifact сейчас `complete(7/7)` и fresh
  - `2026-03-27`: fresh env-backed live smoke с open-domain verification снова реально прогнан для `llm_env` и `llm_env_strict`; оба smoke artifacts остались green на current HEAD
  - `2026-03-27`: fresh one-off comparative gates для `llm_env` и `llm_env_strict` снова реально дали `default switch allowed: yes`
  - `2026-03-27`: triage same-day stability drift показал два разных сигнала: `llm_env` остаётся нестабильным и latest artifact сейчас failed, а `llm_env_strict` после prompt hardening для `capabilities`, `answer_follow_up` и `repo_structure` снова вышел на fresh green repeated stability `3/3`
  - `2026-03-27`: `qa beta` снова рекомендует `llm_env_strict`; technical evidence и real manual checklist больше не главный blocker
  - remaining work внутри stage 8 теперь честно сведён к release decisioning: записать `beta_release_review.json` для `llm_env_strict`, затем `beta_readiness.json`, и только после реального sign-off обсуждать `beta_question_default`
  - default switch по-прежнему заблокирован; rollout stage остаётся `alpha_opt_in`, deterministic path остаётся product default

**1. Product Contract for General QA**
Цель: сначала зафиксировать, что именно означает “JARVIS отвечает на любой вопрос”.

Сделать:
- обновить product framing:
  - JARVIS остаётся desktop assistant
  - но question mode становится broader assistant surface
- явно разделить:
  - grounded local answers
  - general GPT answers
  - unsupported / refusal cases
- определить, что “любой вопрос” не означает:
  - hidden execution
  - legal/medical/financial overclaim
  - internet-backed truth by default
  - persistent memory
- решить default behavior для open-domain question:
  - если вопрос не routed as command и не требует blocked-state precedence, он может идти в GPT answer path

Файлы:
- `docs/product_rules.md`
- `docs/question_answer_mode.md`
- новый doc с policy-границами general QA

Definition of done:
- product docs больше не противоречат general GPT QA
- сохранены command/runtime safety boundaries
- зафиксировано различие между grounded и model-backed general answers

**2. Answer Taxonomy and Final Contracts**
Цель: не пытаться натянуть open-domain GPT answers на grounded-only contract.

Сделать:
- расширить answer contract новым полем, например:
  - `answer_kind`: `grounded_local | open_domain_model | refusal`
  - `provenance`: `local_sources | model_knowledge`
- определить, какие поля обязательны для каждого класса:
  - grounded answer:
    - `sources`
    - `source_attributions`
  - open-domain model answer:
    - `answer_text`
    - `answer_summary`
    - `warning`/`disclaimer` when needed
    - no fake `sources`
- определить unified visibility contract:
  - CLI должен понимать оба answer класса
  - presenter не должен ожидать `sources` у каждого ответа
- добавить schema version bump для answer contract, если shape меняется

Нельзя:
- использовать local source fields как “декорацию” для model answer
- смешивать citations и non-citations без маркировки

Файлы:
- `types/answer_result.py`
- `types/interaction_result.py`
- `ui/visibility_mapper.py`
- `ui/interaction_presenter.py`

Definition of done:
- contract различает grounded и open-domain ответы
- visibility корректно рендерит оба класса
- backward migration path ясен

**3. Open-Domain GPT Backend**
Цель: ввести отдельный backend path для general answers без поломки grounded path.

Сделать:
- не заменять существующий deterministic grounded backend
- добавить explicit classification:
  - grounded question family -> existing grounded pipeline
  - open-domain question family -> GPT general-answer backend
- использовать уже существующий provider seam, но вынести отдельный mode:
  - grounded LLM answering
  - open-domain LLM answering
- сделать отдельный prompt builder для open-domain answers:
  - no execution
  - no hidden commands
  - no claims about runtime state unless explicitly provided
  - answer concisely
  - be honest about uncertainty
- ввести separate response schema for open-domain answers
- оставить model configurable, но не жестко зашивать behavior в routing

Важно:
- GPT backend отвечает только текстом
- command objects, execution steps, confirmation state не создаются
- runtime snapshot даётся только как optional context, не как permission

Файлы:
- `qa/answer_engine.py`
- `qa/llm_backend.py`
- `qa/openai_responses_provider.py`
- новые prompt/schema modules для general QA

Definition of done:
- open-domain questions могут проходить через GPT path
- grounded local path остаётся отдельным и предсказуемым
- provider seam остаётся изолированным

**4. Routing and Fallback Policy**
Цель: решить, когда вопрос считать grounded, когда open-domain, а когда refusal.

Сделать:
- расширить `QuestionType`/classification:
  - `grounded_*` families как сейчас
  - `open_domain_general`
  - при необходимости later: `open_domain_sensitive`
- порядок routing:
  1. blocked confirmation reply
  2. blocked clarification reply
  3. explicit command
  4. mixed question+action -> clarification
  5. grounded system/runtime/repo question
  6. otherwise question -> `open_domain_general`
- определить fallback policy:
  - если GPT backend unavailable:
    - honest failure, а не fake grounded answer
  - если grounded question попал в GPT mode по config:
    - provenance всё равно должен остаться truthful
- ввести denylist для phrases, которые нельзя silently reroute в general QA, если они на самом деле execution-like

Тесты:
- routing regressions на command precedence
- unsupported old-world cases теперь могут стать `open_domain_general`
- mixed question/action по-прежнему clarification

Definition of done:
- routing остаётся deterministic and safe
- open-domain path не съедает command semantics
- fallback поведение честное

**5. UX / Visibility / Provenance**
Цель: чтобы пользователь видел, откуда пришёл ответ и насколько ему можно доверять.

Сделать:
- в CLI добавить явный признак answer class:
  - `mode: question`
  - `answer-kind: grounded_local` или `answer-kind: open_domain_model`
- для open-domain answers показывать compact provenance line, например:
  - `provenance: GPT model knowledge`
- при необходимости показывать warning:
  - no local sources
  - may be incomplete
  - not based on current internet state
- speech mode:
  - не озвучивать provenance слишком многословно
  - warning озвучивать только когда он важен
- history scanning:
  - grounded vs model answers должны визуально отличаться

Нельзя:
- скрывать, что ответ не grounded
- притворяться, что модель “знает” текущее runtime state без visible evidence

Definition of done:
- user может быстро отличить grounded answer от GPT answer
- UX не превращается в noisy chat transcript

**6. Eval Harness Expansion**
Цель: добавить quality gate уже для general GPT answers, а не только для grounded QA.

Сделать:
- расширить eval corpus новыми категориями:
  - open-domain factual questions
  - open-domain explanation questions
  - casual chat / small talk
  - unsupported harmful asks
  - command-vs-general-question ambiguities
  - stale-current-events questions
- для каждого кейса хранить:
  - expected_interaction_kind
  - expected_answer_kind
  - should_call_runtime
  - should_call_answer_engine
  - expected_warning_contains
  - expected_refusal / expected_boundary
- ввести separate metrics:
  - command safety regressions
  - grounded-local regressions
  - open-domain answer availability
  - open-domain refusal quality
  - provenance correctness
  - latency / cost

Важно:
- не пытаться формально “доказать truth” всех world-knowledge answers через unit tests
- вместо этого проверять:
  - correct path selection
  - correct provenance
  - refusal honesty
  - safety compliance
  - stable formatting/contracts

Definition of done:
- eval harness покрывает general QA path
- regressions между grounded и open-domain path видны отдельно

**7. Safety and Abuse Boundaries**
Цель: general GPT answering не должен сломать supervised product posture.

Сделать:
- определить explicit refusal / safe-completion policy для:
  - self-harm
  - illegal assistance
  - dangerous step-by-step wrongdoing
  - extreme medical/legal/financial overclaim
- определить policy для current-events / temporally unstable questions:
  - без web tools answer должен быть bounded
  - при uncertainty модель должна говорить, что может быть неактуально
- зафиксировать запрет на:
  - hidden browsing
  - hidden execution
  - fabricated citations
- определить, как JARVIS отвечает на:
  - “открой Safari и объясни квантовую механику”
  - “подтверди это и скажи, кто президент ...”
  - “ты можешь ответить как GPT, а потом выполнить команду?”

Definition of done:
- есть policy docs для general GPT QA
- safety boundaries тестируемы и не конфликтуют с command model

**8. Rollout Gate and Release Readiness**
Цель: включать broader GPT QA осознанно, а не “оно вроде отвечает”.

Этапы rollout:

1. `alpha_opt_in`
- env/config flag only
- visible provenance mandatory
- no default switch

2. `beta_question_default`
- open-domain GPT becomes default only for question mode
- command mode unchanged
- grounded local path still preferred for system/runtime/repo questions

3. `stable`
- only after eval + manual verification + operator readiness

Перед beta/stable:
- сравнить:
  - command regressions
  - mixed-input regressions
  - provenance correctness
  - refusal quality
  - latency
  - cost
  - live provider stability
- подготовить manual checklist:
  - arbitrary factual question
  - arbitrary explanation question
  - casual chat
  - blocked-state question
  - grounded docs question
  - mixed question+command
  - provider unavailable path

Definition of done:
- есть explicit rollout stages
- default-switch критерии формализованы
- release docs и operator guide обновлены

**Рекомендуемая разбивка на PR**
1. `PR11 general-qa product contract + docs`
2. `PR12 answer contract + provenance taxonomy`
3. `PR13 open-domain GPT backend`
4. `PR14 routing/fallback + safety boundaries`
5. `PR15 eval expansion + rollout gate`
6. `PR16 UX/presenter/CLI polish for mixed provenance`

**Что делать прямо сейчас**
Сейчас разумный следующий шаг такой:
1. прогнать реальный `scripts/run_openai_live_smoke.sh` в target environment и получить green artifact
2. после этого прогнать comparative gate для `llm_env` / `llm_env_strict` уже на живом env-backed signal
3. только потом обсуждать `beta_question_default`

Причина:
- product contract, taxonomy, backend split, safety layer и базовый eval/gate слой уже собраны
- следующий реальный риск теперь не в architecture, а в target-environment verification
- default switch без green live artifact останется формальным, а не доказанным

**Что не рекомендую делать сейчас**
- не включать GPT сразу default для всех questions
- не убирать grounded deterministic path
- не давать GPT routing authority
- не добавлять web browsing в тот же PR, что и general GPT QA
- не смешивать “model knowledge” и “local sources” в одном answer without labeling
- не открывать memory/personalization scope в том же цикле
