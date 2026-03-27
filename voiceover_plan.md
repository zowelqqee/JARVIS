# Подробный план разработки voice-слоя JARVIS

## 1. Цель документа

Этот документ описывает подробный план развития voice-слоя JARVIS от текущего one-shot voice input до полноценного голосового интерфейса, который:

- понимает русскую и английскую речь;
- корректно маршрутизирует voice input в существующее command/question ядро;
- умеет отвечать голосом, а не только печатать текст;
- сохраняет deterministic behavior для команд;
- не ломает safety, confirmation, clarification и QA guardrails;
- остаётся расширяемым без появления отдельного "voice brain".

Главная архитектурная идея:

- ядро JARVIS остаётся text-first;
- voice-слой строится как transport + normalization + audio UX поверх существующих parser/router/runtime/QA модулей.

## 2. Что уже есть

### 2.1 Текущие модули

- `input/macos_voice_capture.m`
  - low-level one-shot macOS helper для захвата и распознавания речи через `Speech.framework`.
- `input/voice_input.py`
  - Python-обёртка над helper;
  - отвечает за rebuild, codesign, retry, error normalization.
- `input/voice_normalization.py`
  - voice-specific normalization;
  - wake words, de-dup repeated phrases, ограниченная русская канонизация.
- `cli.py`
  - voice trigger через `voice` / `/voice`;
  - вызов voice capture;
  - отправка normalised text в основной interaction path;
  - speech output через `say`.
- `interaction/interaction_router.py`
  - роутинг между `command`, `question`, `clarification`.
- `parser/command_parser.py`
  - deterministic command parsing.
- `qa/answer_engine.py`
  - question classification;
  - grounded/open-domain answer path.
- `ui/interaction_presenter.py`
  - рендер top-level interaction result;
  - выбирает одну speech message для TTS.

### 2.2 Что уже улучшено

- helper теперь умеет locale chain через preferred locales;
- для CLI доступен дефолтный voice locale priority `ru-RU,en-US`;
- есть базовая русская wake-word нормализация;
- есть базовая русская канонизация для voice-команд и ключевых question prompts;
- минимальный русский question surface уже добавлен в router/answer engine.

### 2.3 Текущее ограничение

Сейчас voice работает как "one-shot transcript -> обычный текстовый input".

Это полезный MVP, но это ещё не полноценный voice layer, потому что:

- нет отдельного voice orchestration layer;
- нет speech-specific rendering policy;
- нет language-aware TTS selection;
- нет continuous conversation loop;
- нет явной state machine voice session;
- нет audio policy между listening и speaking;
- нет voice telemetry;
- нет полного русского deterministic command surface;
- нет отдельного voice manual verification guide.

## 3. Продуктовая цель

Итоговый voice-режим должен поддерживать четыре класса сценариев:

1. Голосовые deterministic команды.
2. Голосовые grounded вопросы о самом JARVIS и репозитории.
3. Голосовые open-domain вопросы.
4. Голосовые confirmation/clarification диалоги.

Итоговое UX-ожидание:

- пользователь говорит короткую фразу;
- JARVIS подтверждает, что услышал;
- JARVIS либо исполняет команду, либо отвечает на вопрос;
- если нужно подтверждение, JARVIS задаёт короткий голосовой follow-up;
- если ответ длинный, JARVIS произносит краткий summary и умеет продолжить диалог.

## 4. Нефункциональные требования

### 4.1 Надёжность

- voice не должен ломать существующий text path;
- английский path не должен деградировать после добавления русского;
- ошибки микрофона/permissions должны быть структурированными и воспроизводимыми;
- один и тот же transcript должен приводить к одному и тому же downstream result.

### 4.2 Архитектура

- voice logic не должна расползаться по `cli.py`;
- новый слой должен быть модульным;
- parser/router/runtime/QA нельзя дублировать в voice code;
- speech output и screen output должны быть связаны, но не идентичны.

### 4.3 UX

- JARVIS должен говорить кратко и полезно;
- команды не должны зачитываться как внутренние runtime traces;
- источники и длинные пути не должны читаться вслух целиком;
- clarification/confirmation вопросы должны быть voice-friendly.

### 4.4 Safety

- destructive действия требуют такого же подтверждения, как и в text path;
- speech output не должен озвучивать лишнюю внутреннюю диагностику;
- unsafe questions должны следовать тем же safety policy, что и text QA path.

## 5. Архитектурные принципы

### 5.1 Один core, один routing path

Voice не должен иметь отдельный parser или отдельный runtime.

Правильная схема:

- `voice capture`
- `voice normalization`
- `interaction_manager.handle_input(...)`
- `visibility / presenter`
- `speech presenter`
- `tts provider`

### 5.2 Speech-specific rendering обязателен

Screen output и spoken output не должны быть одинаковыми строками по умолчанию.

Пример:

- на экран можно показать `sources`, `paths`, `evidence`;
- голосом нужно говорить summary и, при необходимости, короткое предупреждение.

### 5.3 Voice should be stateful, core should stay deterministic

Voice session может быть stateful, но ядро должно продолжать жить в существующих `runtime_manager`, `session_context`, `interaction_manager`.

### 5.4 Расширение через слои, а не через хаки

Нельзя бесконечно расширять `cli.py` новыми regex и if-ветками.

Все будущие voice-specific вещи должны жить в отдельном слое:

- orchestration;
- normalization;
- speech rendering;
- TTS;
- audio policy.

## 6. Целевая архитектура

### 6.1 Предлагаемая структура модулей

Рекомендуемая структура:

- `voice/session.py`
- `voice/asr_service.py`
- `voice/voice_turn.py`
- `voice/normalization.py`
- `voice/dispatcher.py`
- `voice/speech_presenter.py`
- `voice/tts_provider.py`
- `voice/tts_macos.py`
- `voice/audio_policy.py`
- `voice/telemetry.py`
- `voice/errors.py`

Часть логики можно временно оставить в существующих модулях, но итоговая цель именно такая.

### 6.2 Роли модулей

#### `voice/asr_service.py`

Отвечает за:

- вызов low-level capture helper;
- preferred locales;
- retries;
- structured voice errors;
- future VAD/silence tuning.

#### `voice/normalization.py`

Отвечает за:

- wake words;
- dedup repeated ASR phrases;
- language-aware cleanup;
- canonical voice command surface;
- canonical fixed voice questions.

#### `voice/dispatcher.py`

Отвечает за:

- вызов `interaction_manager.handle_input(...)`;
- упаковку transcript, normalized text и metadata в единый voice turn result;
- отсутствие дублирования routing logic.

#### `voice/speech_presenter.py`

Отвечает за:

- speech-friendly summary;
- сокращение длинных ответов;
- confirmation phrasing;
- clarification phrasing;
- language-aware spoken rendering.

#### `voice/tts_provider.py`

Отвечает за:

- единый интерфейс TTS backend;
- выбор голоса;
- выбор языка;
- формат ошибок TTS.

#### `voice/audio_policy.py`

Отвечает за:

- stop speaking before listening;
- stop listening before speaking;
- future barge-in support;
- suppression of feedback loops.

## 7. Этапы разработки

Ниже описан рекомендуемый порядок работ. Каждый этап должен иметь собственные acceptance criteria и тестовое покрытие.

## 8. Phase 0. База и инвентаризация

Цель:

- формально зафиксировать текущее поведение voice path и не потерять его при рефакторинге.

### Подзадачи

- [ ] Создать `voiceover_plan.md` и зафиксировать целевую архитектуру.
- [ ] Зафиксировать текущий single-turn voice contract в tests.
- [ ] Составить список текущих voice fixtures на русском и английском.
- [ ] Добавить раздел в manual verification docs для текущего `voice` path.
- [ ] Зафиксировать, какие voice функции уже поддерживаются, а какие нет.

### Выходы этапа

- документация;
- baseline tests;
- список known gaps.

### Acceptance criteria

- существующий voice path покрыт контрактами;
- при последующих рефакторах можно быстро отличить intentional changes от regression.

## 9. Phase 1. Надёжный ASR слой

Цель:

- сделать speech recognition устойчивым и предсказуемым до передачи текста в ядро.

### Основные файлы

- `input/macos_voice_capture.m`
- `input/voice_input.py`
- будущий `voice/asr_service.py`

### Подзадачи

#### 9.1 Locale strategy

- [ ] Завершить preferred locale chain как стабильный API, а не как ad-hoc параметр.
- [ ] Поддержать выбор preferred locales из runtime config, а не только из env.
- [ ] Добавить explicit language preference policy для:
  - interactive local CLI;
  - future app mode;
  - future automation/tests.
- [ ] Зафиксировать fallback order:
  - preferred locales;
  - current locale;
  - system default recognizer.

#### 9.2 Error model

- [ ] Вынести voice error codes в отдельный документ или модуль.
- [ ] Разделить ошибки:
  - permission denied;
  - microphone unavailable;
  - empty recognition;
  - helper crash;
  - timeout;
  - speech framework unavailable.
- [ ] Добавить structured metadata для retryability.

#### 9.3 Retry policy

- [ ] Явно описать, когда helper rebuild/retry допустим.
- [ ] Не делать retry на permission errors.
- [ ] Добавить distinction между `retry in-place` и `retry via open bundle`.

#### 9.4 Observability

- [ ] Ввести latency measurement:
  - helper startup latency;
  - recognition latency;
  - total ASR latency.
- [ ] Зафиксировать structured debug payload для voice capture path.

### Acceptance criteria

- русский и английский reliably распознаются через preferred locale chain;
- ошибки voice capture всегда mapped в понятные user-facing messages;
- нет silent failure при распознавании.

## 10. Phase 2. Нормализация voice input

Цель:

- сделать transcript пригодным для существующего deterministic core.

### Основные файлы

- `input/voice_normalization.py`
- future `voice/normalization.py`
- `cli.py`

### Подзадачи

#### 10.1 Wake words

- [ ] Поддержать:
  - `Jarvis`
  - `Hey Jarvis`
  - `Ok Jarvis`
  - `Джарвис`
  - `Эй Джарвис`
  - вариации с пунктуацией и паузами.
- [ ] Добавить устойчивую нормализацию пробелов и punctuation noise.

#### 10.2 Repeated phrase collapse

- [ ] Поддержать частые ASR-дубли:
  - `open Safari open Safari`
  - `что ты умеешь что ты умеешь`
- [ ] Не ломать фразы, где повтор осмысленный.

#### 10.3 Canonical command surface

- [ ] Составить MVP-словарь русских voice-команд:
  - `открой`
  - `запусти`
  - `закрой`
  - `покажи`
  - `найди`
  - `подготовь`
  - `используй`
- [ ] Добавить aliases приложений:
  - `телеграм`
  - `сафари`
  - `код`
  - `хром`
  - `файндер`
- [ ] Добавить минимальную нормализацию voice follow-ups:
  - `да`
  - `нет`
  - `подтверждаю`
  - `отмена`
  - `стоп`

#### 10.4 Canonical question surface

- [ ] Составить список русских interrogatives:
  - `что`
  - `как`
  - `почему`
  - `зачем`
  - `где`
  - `когда`
  - `кто`
  - `сколько`
  - `какой`
  - `какая`
  - `какое`
  - `какие`
- [ ] Добавить fixed Russian prompts для grounded families:
  - capabilities;
  - blocked state;
  - docs clarification;
  - safety explanation.
- [ ] Не переводить все русские open-domain вопросы на английский;
  - общий вопрос должен идти дальше как есть.

#### 10.5 Mixed voice interaction

- [ ] Поддержать шаблоны:
  - `что ты умеешь и открой сафари`
  - `почему ты остановился и открой телеграм`
  - `а потом открой ...`
- [ ] Канонизировать только command tail, не уничтожая question head.

### Acceptance criteria

- voice normalization повторяема и детерминирована;
- ключевые русские команды и вопросы стабильно превращаются в downstream-friendly input;
- английский path не деградирует.

## 11. Phase 3. Routing и question classification для voice

Цель:

- гарантировать, что voice-вопросы не падают в command clarify path по умолчанию.

### Основные файлы

- `interaction/interaction_router.py`
- `qa/answer_engine.py`
- `interaction/interaction_manager.py`

### Подзадачи

#### 11.1 Router question detection

- [ ] Добавить полный минимальный русскоязычный question surface.
- [ ] Добавить detection для polite voice questions:
  - `можешь ли ты`
  - `можно ли`
  - `объясни`
  - `расскажи`
- [ ] Добавить mixed-input recognition для normalized mixed voice commands.

#### 11.2 Blocked-state question support

- [ ] Зафиксировать набор русских blocked-state prompts.
- [ ] Убедиться, что при `awaiting_confirmation` и `awaiting_clarification` вопрос уходит в question path, а не в parser.

#### 11.3 Question classification

- [ ] Расширить deterministic grounded families русскими паттернами.
- [ ] Для unknown Russian questions использовать open-domain general, если backend разрешён.
- [ ] Не допускать unsupported_question там, где честнее open-domain path.

### Acceptance criteria

- voice-вопросы типа `сколько`, `кто`, `почему`, `как`, `что` корректно уходят в question path;
- blocked-state Russian prompts отвечаются grounded answer path;
- open-domain questions не сваливаются в command clarify без причины.

## 12. Phase 4. Полноценный русский deterministic command surface

Цель:

- сделать русский voice usable не только для вопросов, но и для реально исполняемых команд.

### Основные файлы

- `parser/command_parser.py`
- `input/voice_normalization.py`
- `input/adapter.py`
- возможно `runtime/` modules depending on target handling

### Подзадачи

#### 12.1 Confirmation replies

- [ ] Добавить русские approve/deny варианты.
- [ ] Не путать `да` с новой командой.

#### 12.2 Command verbs

- [ ] Поддержать русские voice verbs через canonical English surface или узкий synonym layer.
- [ ] Зафиксировать, какие verbs официально поддерживаются в MVP.

#### 12.3 App aliases и target aliases

- [ ] Ввести русский alias catalog для приложений.
- [ ] Добавить search/file/workspace aliases только там, где есть высокая детерминированность.

#### 12.4 Close/focus/list/search

- [ ] Покрыть русские команды:
  - `закрой телеграм`
  - `покажи окна`
  - `найди файл ...`
  - `открой ... в коде`
- [ ] Проверить, что destructive flows всё ещё требуют confirmation.

### Acceptance criteria

- 80-90% MVP voice-команд работают end-to-end без ручного английского rephrase;
- parser остаётся deterministic;
- отсутствуют dangerous false positives.

## 13. Phase 5. TTS abstraction и spoken output

Цель:

- сделать JARVIS говорящим не через случайные строки, а через контролируемый speech layer.

### Основные файлы

- `cli.py`
- `ui/interaction_presenter.py`
- будущие:
  - `voice/speech_presenter.py`
  - `voice/tts_provider.py`
  - `voice/tts_macos.py`

### Подзадачи

#### 13.1 TTS provider abstraction

- [ ] Вынести вызов `say` из `cli.py` в provider layer.
- [ ] Поддержать structured TTS errors.
- [ ] Подготовить API для будущей замены `say` на другой backend.

#### 13.2 Speech rendering policy

- [ ] Разделить:
  - screen output;
  - spoken output.
- [ ] Добавить правила speech summarization для:
  - question answers;
  - command completions;
  - clarification prompts;
  - confirmation prompts;
  - warnings;
  - failures.

#### 13.3 Language-aware speaking

- [ ] Определять язык spoken response по:
  - language of user request;
  - language of answer;
  - explicit locale preference.
- [ ] Выбирать русскую voice для русских ответов и английскую для английских.

#### 13.4 Safety of spoken content

- [ ] Не озвучивать длинные пути, evidence blocks и внутренние debug traces.
- [ ] Сокращать open-domain answers до компактного summary, если ответ слишком длинный.
- [ ] Отдельно формировать spoken warnings.

### Acceptance criteria

- spoken output короткий, понятный и не похож на терминальный лог;
- JARVIS умеет говорить по-русски и по-английски;
- TTS failures не ломают основной interaction flow.

## 14. Phase 6. Voice session orchestration

Цель:

- перейти от single-turn voice input к управляемой voice session.

### Основные файлы

- будущие:
  - `voice/session.py`
  - `voice/dispatcher.py`
  - `voice/audio_policy.py`

### Подзадачи

#### 14.1 Voice state machine

- [ ] Ввести состояния:
  - `idle`
  - `listening`
  - `transcribing`
  - `routing`
  - `executing`
  - `answering`
  - `speaking`
  - `awaiting_follow_up`
  - `error`
- [ ] Зафиксировать valid transitions.

#### 14.2 Turn lifecycle

- [ ] Ввести `VoiceTurn` dataclass/model.
- [ ] Добавить поля:
  - raw transcript;
  - normalized transcript;
  - detected language;
  - recognition status;
  - interaction kind;
  - answer/command summary;
  - spoken response;
  - retryable flag.

#### 14.3 Audio policy

- [ ] Явно запретить simultaneous listening + speaking на первом этапе.
- [ ] При старте capture останавливать TTS.
- [ ] Перед TTS закрывать активную capture session.

#### 14.4 Follow-up window

- [ ] Добавить опциональный короткий период для follow-up voice replies.
- [ ] Разрешить это только после:
  - clarification;
  - confirmation;
  - short answer completion.

### Acceptance criteria

- voice turn имеет явный lifecycle;
- код не размазан по CLI loops;
- появляется основа для continuous conversation.

## 15. Phase 7. Continuous voice conversation

Цель:

- сделать JARVIS способным поддерживать короткий голосовой диалог без ручного возврата к клавиатуре.

### Подзадачи

#### 15.1 Auto re-listen policy

- [ ] После clarification question возвращаться в listening state автоматически.
- [ ] После confirmation prompt возвращаться в listening state автоматически.
- [ ] После обычного answer делать это только если включён conversation mode.

#### 15.2 Voice control commands

- [ ] Добавить голосовые команды управления сессией:
  - `повтори`
  - `скажи подробнее`
  - `стоп`
  - `замолчи`
  - `слушай снова`
  - `repeat`
  - `stop speaking`
  - `listen again`

#### 15.3 Context reuse

- [ ] Использовать существующий `session_context` для follow-up questions.
- [ ] Убедиться, что recent answer context работает одинаково для text и voice.

### Acceptance criteria

- пользователь может провести минимум 2-3 voice turns подряд;
- confirmation/clarification paths естественно продолжаются голосом;
- контекст не теряется между turns.

## 16. Phase 8. Voice UX polish

Цель:

- сделать voice UX качественным и приятным, а не просто функциональным.

### Подзадачи

#### 16.1 Earcons и audible feedback

- [ ] Добавить короткие звуки на:
  - start listening;
  - stop listening;
  - error;
  - speaking start.
- [ ] Сделать это отключаемым.

#### 16.2 Latency UX

- [ ] Если answer generation занимает дольше порога, давать короткий spoken filler:
  - `Секунду`
  - `Проверяю`
  - `Let me think`
- [ ] Не злоупотреблять filler phrases.

#### 16.3 Barge-in

- [ ] Добавить barge-in только после стабилизации half-duplex.
- [ ] Явно определить, как прерывать TTS пользовательской речью.

#### 16.4 Voice persona

- [ ] Зафиксировать spoken tone:
  - краткость;
  - ясность;
  - мягкость;
  - отсутствие сухого лог-стиля.
- [ ] Поддержать русские и английские response templates.

### Acceptance criteria

- voice UX выглядит как ассистент, а не как терминал с микрофоном;
- речь краткая и предсказуемая;
- длинные ответы не утомляют.

## 17. Phase 9. Safety и policy hardening

Цель:

- сделать voice path полностью совместимым с safety expectations text path.

### Подзадачи

#### 17.1 Spoken confirmation policy

- [ ] Определить краткие spoken confirmation prompts для destructive actions.
- [ ] Гарантировать, что destructive action не исполняется без explicit approval.

#### 17.2 Spoken refusal policy

- [ ] Для unsupported/unsafe questions формировать краткий spoken refusal или bounded answer.
- [ ] Не зачитывать policy-heavy текст целиком.

#### 17.3 Ambiguity handling

- [ ] Для ambiguous commands генерировать voice-friendly clarification.
- [ ] Делать её короткой и answerable голосом.

### Acceptance criteria

- voice safety не слабее text safety;
- clarification prompts короткие и usable;
- spoken output не раскрывает лишнюю внутреннюю информацию.

## 18. Phase 10. Telemetry, evals, rollout

Цель:

- сделать voice development измеримым и пригодным для постепенного rollout.

### Подзадачи

#### 18.1 Telemetry

- [ ] Добавить voice metrics:
  - recognition latency;
  - empty recognition rate;
  - clarification rate;
  - confirmation completion rate;
  - retry rate;
  - TTS failure rate;
  - average spoken response length.

#### 18.2 QA cases

- [ ] Расширить eval/fixture cases для русского и английского voice.
- [ ] Покрыть:
  - command;
  - grounded question;
  - open-domain question;
  - clarification;
  - confirmation;
  - mixed interaction;
  - permission failures.

#### 18.3 Manual verification

- [ ] Создать `docs/manual_voice_verification.md`.
- [ ] Описать:
  - setup;
  - permissions;
  - sample utterances;
  - expected output;
  - regression checklist.

#### 18.4 Rollout

- [ ] Ввести feature flag для continuous voice mode.
- [ ] Ввести отдельный rollout gate для voice readiness.
- [ ] Не включать advanced conversation mode по умолчанию до прохождения manual QA.

### Acceptance criteria

- voice path измерим;
- есть формализованный manual verification flow;
- rollout можно делать поэтапно и безопасно.

## 19. Рекомендуемый порядок реализации

Оптимальный порядок:

1. Завершить ASR стабильность и normalization.
2. Довести router/question classification.
3. Закрыть русский deterministic command MVP.
4. Вынести TTS abstraction и speech presenter.
5. Добавить voice session orchestration.
6. Добавить continuous conversation.
7. Сделать UX polish.
8. Закрыть safety hardening.
9. Добавить telemetry и rollout gate.

Причина такого порядка:

- без стабильного transcript нет смысла строить сложный session layer;
- без нормального speech presenter JARVIS будет "говорить логами";
- full-duplex и persona имеет смысл только после стабильного half-duplex base.

## 20. Детальный backlog по файлам

### `input/macos_voice_capture.m`

- [ ] formalize locale chain contract;
- [ ] future hook for VAD/silence control;
- [ ] richer structured diagnostics;
- [ ] latency instrumentation.

### `input/voice_input.py`

- [ ] выделить ASR service boundary;
- [ ] ввести structured retry metadata;
- [ ] подготовить integration with future `voice/asr_service.py`.

### `input/voice_normalization.py`

- [ ] расширить русский/английский normalization catalog;
- [ ] формализовать command aliases;
- [ ] формализовать fixed question phrases;
- [ ] вынести normalization fixtures.

### `cli.py`

- [ ] убрать orchestration details из CLI;
- [ ] заменить прямой `say` на TTS service;
- [ ] оставить CLI только как shell trigger layer.

### `interaction/interaction_router.py`

- [ ] расширить voice-friendly question surface;
- [ ] доработать mixed Russian/English patterns;
- [ ] минимизировать false command fallback.

### `parser/command_parser.py`

- [ ] покрыть русский confirmation surface;
- [ ] расширить deterministic command coverage для voice MVP;
- [ ] не превращать parser в полноценный multilingual NLP слой.

### `qa/answer_engine.py`

- [ ] расширить русские grounded patterns;
- [ ] улучшить fixed family detection;
- [ ] оставить open-domain questions на оригинальном языке.

### `ui/interaction_presenter.py`

- [ ] отделить screen-oriented formatting от speech-oriented formatting;
- [ ] использовать как источник visibility, но не как final spoken UX policy.

### `tests/`

- [ ] отдельные contract tests для voice normalization;
- [ ] ASR locale tests;
- [ ] routing tests;
- [ ] interaction manager voice end-to-end tests;
- [ ] speech presenter tests;
- [ ] TTS provider tests.

## 21. Матрица тестирования

### 21.1 Unit tests

- wake word stripping;
- phrase dedup;
- locale chain;
- language-aware speech selection;
- question marker recognition;
- confirmation/denial recognition.

### 21.2 Contract tests

- voice helper error normalization;
- speech presenter output contract;
- interaction speech summary contract;
- TTS provider error contract.

### 21.3 Integration tests

- voice transcript -> interaction manager -> answer result;
- voice transcript -> runtime -> confirmation;
- voice transcript -> clarification;
- voice transcript -> spoken summary.

### 21.4 Manual verification suites

- permissions suite;
- Russian voice suite;
- English voice suite;
- mixed-language suite;
- destructive action confirmation suite;
- open-domain answer suite;
- failure and retry suite.

## 22. Manual verification scenarios

Минимальный manual suite должен включать:

- [ ] `Джарвис, открой телеграм`
- [ ] `Эй Джарвис, открой сафари`
- [ ] `Что ты умеешь`
- [ ] `Как работает уточнение`
- [ ] `Что именно тебе нужно подтвердить`
- [ ] `Кто президент Франции`
- [ ] `Сколько планет во вселенной`
- [ ] `Что ты умеешь и открой сафари`
- [ ] `Закрой телеграм` -> `да`
- [ ] `Закрой телеграм` -> `нет`
- [ ] `Who is Ada Lovelace?`
- [ ] `Open Safari`
- [ ] `What can you do?`
- [ ] отключённый микрофон;
- [ ] denied speech recognition permission;
- [ ] empty recognition;
- [ ] unavailable `say`.

## 23. Метрики успеха

### Краткосрочные

- русские и английские короткие utterances идут в correct path;
- confirmation/clarification работают голосом;
- spoken summary звучит адекватно.

### Среднесрочные

- не менее 90% fixture voice inputs маршрутизируются корректно;
- destructive actions подтверждаются голосом без regressions;
- manual verification suite проходит стабильно.

### Долгосрочные

- JARVIS поддерживает короткий голосовой диалог;
- voice UX естественный и быстрый;
- TTS и ASR abstraction позволяют развивать voice без переписывания core.

## 24. Основные риски

### Риск 1. Сползание voice логики в CLI

Последствие:

- трудноподдерживаемый код;
- сложность тестирования;
- скрытые регрессии.

Снижение риска:

- early extraction в `voice/` modules;
- thin CLI shell.

### Риск 2. Переусложнение parser под русский

Последствие:

- parser превратится в brittle multilingual rule engine.

Снижение риска:

- больше канонизации до parser;
- narrow deterministic command surface.

### Риск 3. Spoken UX будет просто читать экранные строки

Последствие:

- JARVIS будет звучать плохо;
- длинные ответы станут непригодными для voice.

Снижение риска:

- отдельный `speech_presenter`;
- spoken summary policy.

### Риск 4. Full-duplex слишком рано

Последствие:

- flaky UX;
- race conditions;
- feedback loop между TTS и capture.

Снижение риска:

- сначала robust half-duplex;
- barge-in только после стабилизации базового voice loop.

### Риск 5. Отсутствие измеримости

Последствие:

- непонятно, что реально улучшилось, а что деградировало.

Снижение риска:

- telemetry;
- eval fixtures;
- manual verification suites.

## 25. Что не нужно делать слишком рано

- не строить полноценный multilingual semantic parser;
- не переводить все русские вопросы на английский;
- не внедрять full-duplex до стабилизации half-duplex;
- не смешивать speech rendering с screen formatting;
- не завязывать voice quality на один giant regex file в `cli.py`;
- не включать advanced voice mode по умолчанию без manual QA.

## 26. Definition of Done для "JARVIS умеет говорить"

Можно считать, что voice layer достиг хорошего уровня, когда одновременно выполнено следующее:

- JARVIS понимает базовые русские и английские voice commands;
- JARVIS понимает русские и английские voice questions;
- JARVIS озвучивает ответы кратко и корректно;
- confirmation/clarification возможны без клавиатуры;
- destructive safety не ослаблена;
- voice path покрыт unit/integration/manual tests;
- есть telemetry и rollout story;
- код voice-слоя модульный и не размазан по CLI.

## 27. Рекомендуемый ближайший практический next step

Если двигаться от текущего состояния репозитория, лучший следующий порядок такой:

1. Закрыть русский deterministic confirmation surface.
2. Вынести TTS abstraction из `cli.py`.
3. Ввести `voice/speech_presenter.py`.
4. Сделать `voice/session.py` для managed half-duplex voice loop.
5. После этого переходить к continuous conversation и UX polish.

Это даст максимальный продуктовый эффект с минимальным архитектурным риском.
