**Стартовая точка**
- `QA v1` работает.
- `Command` не перегружен вопросами.
- `InteractionManager` и `Interaction Router` уже есть.
- deterministic path покрыт тестами.
- OpenAI backend уже есть как opt-in seam, не как product default.
- Мы уже вышли за рамки исходного MVP-плана и находимся в фазе hardening + phase 2 planning.

**Главная цель следующего цикла**
Сделать систему не просто “работающей”, а:
1. архитектурно замороженной,
2. измеримой через evals,
3. расширяемой по question scope,
4. безопасной для model-backed answers,
5. готовой к phase 2 без переделки базовых инвариантов.

**Рекомендуемый порядок**
1. Cleanup and Freeze
2. Evaluation Harness
3. QA Phase 2 Scope
4. Grounding and Retrieval Hardening
5. LLM Alpha Hardening
6. UX and CLI Polish
7. Release Readiness

**1. Cleanup and Freeze**
Цель: добить мелкие архитектурные хвосты, чтобы дальше не строить на полузавершённом каркасе.

Сделать:
- Добавить отдельный shared type `InteractionKind`.
- Привести к одному словарю значений: `command`, `question`, `clarification`.
- Проверить, что `InteractionResult`, visibility payload и presenter используют один и тот же vocabulary.
- Зафиксировать schema version для model-backed answer contract.
- Проверить, что все answer-specific error codes реально используются и не дублируются.
- Проверить, что docs и код совпадают по:
  - default backend,
  - default model,
  - source attribution rules,
  - live smoke flow.
- Вычистить временные helper-решения, которые остались только ради ранней интеграции.

Файлы:
- `types/interaction.py`
- `types/interaction_result.py`
- `interaction/interaction_router.py`
- `interaction/interaction_manager.py`
- `ui/visibility_mapper.py`
- `ui/interaction_presenter.py`
- docs вокруг contracts

Тесты:
- contract test на `InteractionKind`
- regression на visibility vocabulary
- snapshot-like tests на presenter output

Definition of done:
- нет разъезда между docs и runtime contract
- нет скрытых string literals interaction-mode по всему коду
- type surface стабилен

**2. Evaluation Harness**
Цель: перестать проверять качество только через unit tests и добавить системную оценку поведения.

Сделать:
- Ввести отдельный eval corpus для routing и answer behavior.
- Собрать набор кейсов в одном формате, например `evals/qa_cases.json` или `tests/fixtures/qa_cases.json`.
- Разбить кейсы по категориям:
  - command vs question routing
  - mixed input routing
  - blocked-state precedence
  - deterministic grounded answers
  - unsupported question failures
  - LLM fallback behavior
  - live smoke gating
  - voice normalization cases
- Для каждого кейса хранить:
  - raw_input
  - expected_interaction_kind
  - expected_question_type или expected_command_intent
  - should_call_runtime
  - should_call_answer_engine
  - expected_sources_count_min
  - expected_warning / expected_error_code
- Добавить eval runner, который можно запускать отдельно от unit suite.
- Ввести отчёт вида:
  - total cases
  - routing accuracy
  - grounding pass rate
  - command-regression pass rate

Особенно важно:
- зафиксировать negative cases
- ввести dataset на polite commands vs real questions
- ввести dataset на blocked confirmation/clarification replies

Definition of done:
- есть централизованный eval corpus
- есть воспроизводимый отчёт
- можно сравнивать deterministic и llm backend на одном наборе кейсов

**3. QA Phase 2 Scope**
Цель: расширить полезность question mode, не ломая read-only модель.

Рекомендую взять только такие новые question families:

1. blocked_state_questions
- “что ты ждёшь?”
- “почему ты остановился?”
- “что тебе нужно от меня?”
- “что именно надо подтвердить?”

2. recent_runtime_questions
- “что ты только что сделал?”
- “какую команду ты выполнил последней?”
- “с каким target ты работал?”
- “какой app/file был последним?”

3. richer_docs_questions
- “объясни confirmation flow”
- “в чём разница между clarification и confirmation?”
- “как работает planner step-by-step?”
- “почему mixed input идёт в clarification?”

4. richer_repo_questions
- “где лежит routing логика?”
- “какой файл отвечает за visibility?”
- “где проверяется grounding?”

Не делать пока:
- open-ended arbitrary repo QA
- произвольные why-questions без grounding
- answer chaining по нескольким незаданным follow-up
- интернет и внешние знания

Нужные изменения:
- расширить `QuestionType`
- добавить новые source maps
- расширить runtime snapshot для read-only introspection
- обновить docs/use_cases и tests

Definition of done:
- phase 2 вопросы читают только runtime/docs/session data
- не вызывают executor/planner
- не ломают blocked-state semantics

**4. Grounding and Retrieval Hardening**
Цель: сделать grounding более точным, чем просто “список файлов”.

Сделать:
- Вынести source selection в отдельный модуль, если он ещё размазан между answer engine и backend-ами.
- Добавить doc/topic registry:
  - topic
  - source file
  - section hint
  - answer family
  - priority
- Перейти от file-level grounding к section-aware grounding там, где это возможно.
- Для docs answers добавлять не только `source`, но и `support` по section claim.
- Для runtime answers различать:
  - runtime visibility source
  - session context source
  - docs source
- Добавить explicit insufficient-context reasons:
  - no_active_command
  - no_recent_target
  - topic_not_supported
  - source_not_mapped

Хороший следующий шов:
- `qa/source_registry.py`
- `qa/source_selector.py`

Definition of done:
- answer engine объяснимо выбирает источники
- source attribution становится стабильнее
- меньше ручной логики в отдельных backend-ах

**5. LLM Alpha Hardening**
Цель: довести model-backed backend до состояния controlled alpha, но не делать его default.

Сделать:
- Вынести prompt/instructions builder в отдельный модуль.
- Вынести schema builder в отдельный модуль.
- Вынести response parser interface в отдельный слой, если появятся другие provider-ы.
- Добавить provider settings:
  - model
  - timeout
  - max output tokens
  - retry policy
  - strict mode
  - fallback mode
- Добавить retries только для transient cases:
  - 429
  - 500
  - 502
  - 503
  - network timeout
- Не ретраить:
  - malformed response
  - grounding failure
  - schema mismatch
  - out-of-bundle source attribution
- Добавить response schema version.
- Добавить request id / correlation id в debug details.
- Добавить bounded logging without leaking secrets.

Критично:
- LLM не должен решать routing
- LLM не должен решать confirmation
- LLM не должен менять runtime state
- LLM не должен сам выбирать “скрытые” источники вне bundle

Definition of done:
- provider path хорошо изолирован
- transient failures handled
- non-transient failures fail honestly
- alpha можно включать флагом в контролируемой среде

**6. UX and CLI Polish**
Цель: довести интерфейс до более удобного supervised experience.

Сделать:
- Добавить более короткое форматирование answer sources в CLI.
- Разделить human-readable source labels и raw absolute paths.
- Для voice mode решить, что именно озвучивать:
  - полный answer
  - только answer summary
  - warning отдельно
- Добавить shell helper commands, если нужно:
  - `qa backend`
  - `qa model`
  - `qa smoke`
- Улучшить mixed-input clarification wording.
- Добавить answer-mode summary line для CLI history scanning.
- Если нужно, добавить compact/non-compact output mode.

Важно:
- не превращать CLI в chat UI
- не прятать sources/warnings
- не смешивать command-state и answer-state визуально

Definition of done:
- answer output читается быстрее
- voice mode не звучит многословно
- CLI остаётся детерминированным

**7. Session Context Phase 2**
Цель: аккуратно добавить answer-follow-up continuity без появления “памяти”.

Сделать:
- Добавить short-lived:
  - `recent_answer_topic`
  - `recent_answer_sources`
  - `recent_answer_scope`
- Ограничить TTL логически рамками текущей сессии.
- Разрешить только безопасные follow-ups:
  - “объясни подробнее”
  - “какой источник?”
  - “почему?”
  - “где это написано?”
- Не разрешать follow-up, который внезапно становится execution without routing.

Не делать:
- long-term memory
- cross-session carry-over
- implicit preferences memory
- hidden personalization

Definition of done:
- follow-up answers работают
- command runtime от этого не мутирует
- session context остаётся short-lived

**8. Observability and Debuggability**
Цель: чтобы поломки объяснялись быстро, без ручного раскопа.

Сделать:
- Добавить structured debug payload для:
  - routing decision
  - question classification
  - source selection
  - provider response parse
  - grounding verification
- Добавить debug mode flag.
- В live smoke выводить:
  - chosen model
  - provider
  - source count
  - whether deterministic fallback happened
- В error details включать только безопасные поля.
- Не логировать API key.
- Не логировать полный answer bundle без явной нужды.

Definition of done:
- любую provider failure можно быстро локализовать
- debug output не нарушает security hygiene

**9. Product Gate for LLM Default Decision**
Цель: не включить model-backed QA по умолчанию раньше времени.

Решение принимать только после eval.

Перед включением default llm backend:
- сравнить deterministic vs llm на общем eval corpus
- измерить:
  - routing safety regressions
  - groundedness pass rate
  - unsupported-question honesty
  - source attribution quality
  - fallback frequency
  - latency
  - cost
- определить threshold:
  - если LLM даёт лучшее качество без потери safety, можно делать opt-in alpha
  - default switch только после стабильного eval

Пока рекомендация:
- default product path оставить deterministic
- llm path держать opt-in

**10. Release Readiness**
Цель: подготовить merge/release без архитектурного долга.

Сделать:
- Обновить docs по phase 2 scope.
- Подготовить manual verification checklist.
- Подготовить smoke commands:
  - deterministic path
  - interaction routing path
  - live OpenAI path
- Подготовить short operator guide:
  - как включить llm backend
  - как запустить live smoke
  - как диагностировать transport/provider/grounding errors
- Зафиксировать release criteria:
  - no command regressions
  - all contract suites green
  - deterministic mode green
  - live smoke green in target env
  - docs match reality

**Рекомендуемая разбивка на следующие PR**
1. `PR5 cleanup + InteractionKind + contract freeze`
2. `PR6 eval harness + qa case corpus`
3. `PR7 QA phase 2 question families`
4. `PR8 source registry + retrieval hardening`
5. `PR9 llm alpha hardening`
6. `PR10 UX + release docs`

**Что делать прямо сейчас**
Я бы пошёл так:
1. `InteractionKind` + final contract cleanup
2. eval harness
3. phase 2 blocked-state and recent-runtime questions

**Что не рекомендую делать сейчас**
- не включать LLM backend по умолчанию
- не добавлять интернет
- не расширять QA до arbitrary repo assistant
- не давать мета-вопросам влиять на blocked command flow
- не добавлять long-term memory
