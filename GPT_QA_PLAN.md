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
Я бы начал так:
1. зафиксировать новый product contract и provenance model
2. расширить `AnswerResult` под `grounded_local` vs `open_domain_model`
3. только потом врезать open-domain GPT path в `answer_engine`

Причина:
- иначе GPT path появится раньше, чем у него будет честный contract
- и UI начнёт показывать general answers как будто они grounded

**Что не рекомендую делать сейчас**
- не включать GPT сразу default для всех questions
- не убирать grounded deterministic path
- не давать GPT routing authority
- не добавлять web browsing в тот же PR, что и general GPT QA
- не смешивать “model knowledge” и “local sources” в одном answer without labeling
- не открывать memory/personalization scope в том же цикле
