# План внедрения протоколов в JARVIS

## 1. Зачем это нужно

Протоколы нужны, чтобы JARVIS умел выполнять не только отдельные команды вроде `open Telegram`, но и короткие именованные сценарии, запускаемые одной фразой.

Примеры:
- `протокол чистый лист`
- `JARVIS, я дома`
- `протокол фокус`
- `протокол созвон`

Цель этой инициативы:
- дать пользователю быстрый способ запускать повторяющиеся сценарии одной фразой;
- сохранить текущую архитектуру supervised desktop assistant;
- не ломать safety-модель;
- сделать систему расширяемой, чтобы новые протоколы можно было добавлять без переписывания ядра.

## 2. Что считается протоколом

Протокол в JARVIS это:
- именованный сценарий;
- с одним или несколькими голосовыми/текстовыми триггерами;
- с явным набором шагов;
- с понятной политикой безопасности;
- с предсказуемым результатом;
- с возможностью расширения через конфиг и/или реестр.

Протокол не должен быть:
- скрытым автономным агентом;
- бесконечным workflow;
- неограниченной макросистемой со свободным выполнением произвольного кода;
- способом обойти подтверждение для чувствительных действий.

## 3. Продуктовые принципы

Протоколы должны подчиняться уже существующим правилам из текущего MVP:
- остаются внутри `command mode`;
- выполняются только после явной команды пользователя;
- идут через видимый plan и runtime;
- не создают фоновых задач;
- не обходят confirmation boundary;
- не смешиваются с question-answer mode.

Дополнительно для протоколов:
- каждый протокол должен быть детерминированно разрешен в структурированную команду или последовательность шагов;
- каждый протокол должен иметь явный `id`;
- каждый протокол должен иметь декларативное описание;
- каждый протокол должен иметь policy о том, требует ли он confirmation;
- протоколы должны быть расширяемыми без изменения базового роутера под каждый новый кейс.

## 4. Ограничения текущей системы

На момент планирования в репозитории уже есть сильный фундамент:
- голосовая нормализация в `input/voice_normalization.py`;
- top-level routing в `interaction/interaction_router.py`;
- command parsing в `parser/command_parser.py`;
- validation в `validator/command_validator.py`;
- planning в `planner/execution_planner.py`;
- supervised runtime в `runtime/runtime_manager.py`;
- desktop execution в `executor/desktop_executor.py`;
- spoken output в `voice/speech_presenter.py`.

Но сейчас отсутствует:
- отдельная сущность `protocol`;
- реестр протоколов;
- persisted state между сессиями для вещей вроде `последний workspace`;
- расширяемая схема пользовательских протоколов;
- capability для воспроизведения музыки;
- безопасный batch-close как отдельная поддержанная возможность.

Особенно важно:
- текущий `SessionContext` по контракту краткоживущий и не подходит для long-lived памяти между сессиями;
- часть желаемых сценариев требует новых executor-capabilities, а не только новых parser-rules.

## 5. Целевая архитектурная идея

Нужно внедрить протоколы как новый command-family, но не как третью top-level ветку рядом с `command` и `question`.

Правильная модель:

```text
user phrase
  -> input normalization
  -> interaction routing
  -> command parsing
  -> protocol resolution
  -> validation
  -> plan expansion
  -> runtime execution
  -> visible status + spoken output
```

То есть протокол:
- распознается как команда;
- превращается в структурированный `Command`;
- дальше проходит через обычный supervised pipeline.

Это важно, потому что тогда протоколы автоматически наследуют:
- clarification;
- confirmation;
- visibility;
- completion reporting;
- speech rendering;
- тестовую инфраструктуру.

## 6. Предлагаемая модель данных

### 6.1 Новый intent

Добавить новый intent:
- `run_protocol`

Он должен означать:
- пользователь запросил запуск именованного протокола;
- протокол еще не является произвольным кодом;
- протокол должен быть разрешен в безопасный набор поддержанных шагов.

### 6.2 Новый доменный модуль `protocols/`

Добавить новый пакет:
- `protocols/`

Предлагаемая структура:
- `protocols/models.py`
- `protocols/registry.py`
- `protocols/resolver.py`
- `protocols/planner.py`
- `protocols/state_store.py`
- `protocols/builtin_protocols.py`
- `protocols/user_protocol_loader.py`

### 6.3 Базовые сущности

#### `ProtocolDefinition`

Поля:
- `id: str`
- `version: str`
- `title: str`
- `description: str`
- `triggers: list[ProtocolTrigger]`
- `parameters_schema: dict | None`
- `steps: list[ProtocolActionDefinition]`
- `confirmation_policy: ProtocolConfirmationPolicy`
- `visibility_policy: ProtocolVisibilityPolicy`
- `enabled: bool`
- `tags: list[str]`

#### `ProtocolTrigger`

Поля:
- `type: literal["exact", "alias", "pattern"]`
- `phrase: str`
- `locale: str | None`
- `wake_word_optional: bool`

Назначение:
- сопоставление пользовательской фразы с `protocol_id`;
- возможность держать несколько разговорных вариантов одной команды.

#### `ProtocolActionDefinition`

Поля:
- `action_type: str`
- `inputs: dict`
- `requires_confirmation: bool | None`
- `on_failure: literal["stop", "continue_if_safe"]`
- `speak_before: str | None`
- `speak_after: str | None`

Это именно декларация шага протокола, а не конечный `Step`.

#### `ResolvedProtocol`

Поля:
- `definition: ProtocolDefinition`
- `resolved_parameters: dict`
- `resolved_actions: list[ProtocolActionDefinition]`
- `summary: str`

Это переходный объект между parser и planner.

## 7. Где протоколы встраиваются в текущий pipeline

### 7.1 Input normalization

В `input/voice_normalization.py` нужно добавить только поверхностную поддержку:
- нормализацию форм вроде `джарвис, я дома`;
- канонизацию `протокол X`;
- при необходимости простые русские/английские aliases.

Но нельзя переносить сюда бизнес-логику протоколов.

Правило:
- `input/` чистит surface form;
- `protocols/registry.py` знает, какие протоколы вообще существуют.

### 7.2 Command parsing

В `parser/command_parser.py` нужно:
- добавить ветку распознавания `run_protocol`;
- вызывать `protocols.resolver.match_protocol_trigger(...)`;
- если триггер найден, возвращать `Command(intent=run_protocol, ...)`.

В `Command.parameters` для такого intent желательно класть:
- `protocol_id`
- `protocol_trigger`
- `protocol_display_name`
- `protocol_parameters`

Важно:
- не захардкодить каждый отдельный протокол прямо в parser;
- parser должен знать только про общий механизм поиска совпадения.

### 7.3 Validation

В `validator/command_validator.py` нужно:
- добавить `run_protocol` в список поддержанных intent;
- валидировать, что `protocol_id` существует в registry;
- валидировать, что протокол включен;
- валидировать, что обязательные параметры разрешены;
- валидировать, что протокол ссылается только на допустимые action types.

Если протокол не найден:
- не падать молча;
- возвращать структурированную ошибку или clarification.

### 7.4 Planning

В `planner/execution_planner.py` протокол не должен исполняться как opaque black box.

Нужна схема:
- planner видит `run_protocol`;
- вызывает `protocols.planner.expand_protocol_to_steps(...)`;
- получает обычный список `Step`.

Это ключевая идея всей интеграции.

Плюсы:
- runtime остается почти неизменным;
- executor остается пошаговым;
- ui/visibility продолжает работать;
- confirmation boundary может навешиваться на конкретные шаги.

### 7.5 Runtime

В `runtime/runtime_manager.py` желательно оставить старую модель:
- одна команда;
- один план;
- один шаг за раз.

Но нужно добавить:
- запись успешных protocol-runs в persisted store;
- обогащение completion summary для `run_protocol`;
- запись полезного recent context после выполнения.

### 7.6 Spoken output

В `voice/speech_presenter.py` нужно добавить:
- spoken template для `run_protocol`;
- возможность красиво озвучивать completion типа:
  - `Запустил протокол чистый лист.`
  - `Протокол "я дома" выполнен.`

Позже можно расширить это до промежуточных речевых шагов, но это уже второй этап.

## 8. Расширяемость: как добавлять новые протоколы

Это важнейшее требование.

Система должна поддерживать два уровня протоколов:
- встроенные протоколы репозитория;
- пользовательские протоколы, добавляемые без изменения Python-кода.

### 8.1 Встроенные протоколы

Хранятся в коде или в встроенных YAML/JSON-файлах внутри репозитория.

Подходят для:
- `clean_slate`
- `i_am_home`
- `focus_mode`
- `work_session_start`

Плюсы:
- легко тестировать;
- легко версионировать;
- удобно внедрять сложные политики.

### 8.2 Пользовательские протоколы

Хранить отдельно от кода, например:
- `~/.jarvis/protocols/*.yaml`
или
- `config/protocols/*.yaml` внутри workspace

Предпочтительный стартовый вариант:
- `~/.jarvis/protocols/`

Причина:
- это не repo-specific knowledge;
- это ближе к пользовательским сценариям;
- не будет смешиваться с исходниками JARVIS.

### 8.3 Формат протокола

Рекомендуемый формат для начала:
- YAML

Пример:

```yaml
id: i_am_home
version: "1"
title: "Я дома"
description: "Включает домашний контекст после возвращения."
enabled: true
triggers:
  - type: exact
    phrase: "я дома"
    locale: "ru-RU"
  - type: exact
    phrase: "jarvis i'm home"
    locale: "en-US"
confirmation_policy:
  mode: never
steps:
  - action_type: open_website
    inputs:
      browser_name: "Safari"
      url: "https://www.youtube.com/watch?v=IyR25B-IGyg"
```

### 8.4 Loader

`protocols/user_protocol_loader.py` должен:
- читать директорию с пользовательскими файлами;
- валидировать schema;
- отклонять неизвестные action types;
- не выполнять произвольный Python;
- не принимать shell snippets;
- отдавать безопасные декларативные объекты.

## 9. Принцип безопасности для extensibility

Расширяемость допустима только на уровне декларативных действий.

Нельзя разрешать в user-defined protocol:
- произвольный shell command;
- произвольный AppleScript;
- Python callbacks из файла конфигурации;
- сетевые действия вне явно поддержанных capabilities;
- обход confirmation.

Разрешать нужно только whitelist action types, например:
- `open_app`
- `open_folder`
- `open_file`
- `open_website`
- `close_app`
- `prepare_workspace`
- `play_music`
- `open_last_workspace`
- `speak_text`

И даже внутри whitelist:
- чувствительные действия должны идти через confirmation policy.

## 10. Persistence: что нужно хранить между сессиями

Для сценария `JARVIS, я дома` текущего `SessionContext` недостаточно.

Нужен отдельный persisted state store.

### 10.1 Новый модуль

Добавить:
- `protocols/state_store.py`

### 10.2 Что хранить

Минимальный persisted state:
- `last_workspace_path`
- `last_workspace_label`
- `last_workspace_opened_at`
- `last_command_summary`
- `last_protocol_id`
- `last_protocol_run_at`
- `last_primary_app`
- `last_git_branch`
- `last_work_summary`

### 10.3 Откуда заполнять

Обновлять persisted state после успешных команд:
- `prepare_workspace`
- `open_folder`
- `open_file` в code/editor
- `run_protocol`

Дополнительно можно обогащать:
- из git status веткой текущего repo;
- из recent runtime summary;
- из explicit protocol metadata.

### 10.4 Где хранить

Простой и надежный старт:
- JSON-файл в пользовательской директории, например `~/.jarvis/state/protocol_state.json`

Почему не SessionContext:
- тот живет только внутри активной supervised session;
- в docs уже закреплено, что cross-session persistence там быть не должно.

## 11. Capability model для протоколов

Протоколы должны собираться из capabilities, а не быть особыми исключениями.

Предлагаемая градация:

### 11.1 Уже существующие capabilities

- open app
- open folder
- open file
- open website
- close app
- search local
- prepare workspace

### 11.2 Новые capabilities первого класса

Нужно ввести как отдельные действия:
- `play_music`
- `open_last_workspace`
- `speak_text`
- возможно `close_apps_batch`

Рекомендуемый порядок:
- сначала `open_last_workspace` и `speak_text`;
- потом `play_music`;
- потом уже batch-close.

## 12. Протокол `clean_slate`

### 12.1 Цель

По фразе:
- `протокол чистый лист`

JARVIS должен:
- подготовить чистое рабочее состояние;
- безопасно закрыть лишние приложения;
- не закрыть критически важные или защищенные процессы;
- не уничтожить данные без подтверждения.

### 12.2 MVP-версия

На первом этапе `clean_slate` должен:
- показать список приложений к закрытию;
- попросить confirmation;
- закрыть только allowlist приложений;
- оставить защищенные приложения нетронутыми.

Пример allowlist:
- Telegram
- Notes
- Safari
- Chrome
- Music

Пример protected-list:
- Finder
- Terminal / iTerm
- Visual Studio Code
- сам JARVIS / Codex shell
- системные процессы

### 12.3 Почему не “закрыть вообще всё”

Потому что это:
- нарушает текущую safety-модель;
- может привести к потере несохраненной работы;
- потребует значительно более сложной window/app introspection.

Поэтому MVP должен быть честным:
- `clean_slate` не “убивает всё”;
- он выполняет безопасный управляемый cleanup.

### 12.4 Вторая версия

После появления более зрелой capability можно расширить до:
- list running apps;
- вычисление кандидатов на закрытие;
- protected policies;
- per-app confirmation;
- skip app if unsaved-state is suspected.

## 13. Протокол `i_am_home`

### 13.1 Цель

По фразе:
- `я дома`
- `джарвис, я дома`

JARVIS должен:
- включить домашний контекст;
- открыть домашний музыкальный URL;
- произнести короткую сводку.

### 13.2 MVP-версия

На первом этапе:
- открыть конкретный YouTube URL с домашней музыкой;
- произнести шаблонную фразу.

Пример spoken text:
- `Сэр, вы закончили работать над {last_workspace_label}, ветка {last_git_branch}.`

### 13.3 Важная деталь

`last_work_summary` лучше не генерировать свободно на лету без опоры.

Безопасный MVP:
- брать только то, что было явно сохранено из предыдущего runtime;
- не выдумывать summary.

## 14. Нужно ли вводить новый executor action для музыки

Да, если мы хотим, чтобы это было честной capability, а не скрытым ad-hoc костылем.

Предлагаемый action:
- `play_music`

Варианты реализации на macOS:
- открыть `Music.app`;
- запустить playlist URL;
- позднее добавить AppleScript integration для play/resume конкретного playlist.

MVP-версия action может быть очень узкой:
- только открыть `Music.app` или `Spotify.app`;
- или открыть заранее заданный playlist URL.

Не нужно на первом этапе:
- управление медиатекой;
- сложные play/pause/next flows;
- универсальная интеграция со всеми музыкальными приложениями.

## 15. Нужно ли вводить `speak_text` как action

Да, но аккуратно.

Есть два варианта:

### Вариант A. Не делать action, а говорить только completion-summary

Плюсы:
- меньше изменений;
- хорошо ложится на текущий `speech_presenter`.

Минусы:
- нельзя делать специальные голосовые реплики внутри протокола.

### Вариант B. Ввести `speak_text`

Плюсы:
- можно делать кастомные реплики в сценариях;
- удобно для протокола `я дома`.

Минусы:
- executor начинает выполнять не только desktop actions, но и explicit speech actions.

Рекомендация:
- в MVP ограничиться completion speech;
- `speak_text` добавить сразу после первого рабочего протокольного каркаса.

## 16. Как должен выглядеть flow запуска протокола

### 16.1 Happy path

```text
Пользователь говорит: "Джарвис, я дома"
-> voice normalization
-> parser распознает trigger
-> command intent = run_protocol
-> validator проверяет protocol_id и inputs
-> protocol planner разворачивает protocol в Steps
-> runtime показывает plan
-> выполняются шаги
-> runtime пишет persisted state
-> speech presenter озвучивает completion
```

### 16.2 Unknown protocol

Если пользователь говорит:
- `протокол солнечный шторм`

а такого протокола нет, система должна:
- не делать fallback в случайную generic команду;
- честно сказать, что такой протокол не найден;
- предложить один или несколько похожих вариантов, если они есть.

### 16.3 Ambiguous trigger

Если один trigger конфликтует с другим:
- registry должен возвращать ambiguity;
- parser/validator должны блокировать выполнение;
- JARVIS должен уточнить, какой протокол запускать.

## 17. Confirmation policy

Каждый протокол должен явно описывать confirmation policy.

Возможные режимы:
- `never`
- `always`
- `if_sensitive_steps_present`
- `per_step`

Рекомендации:
- `clean_slate` -> `always` или `if_sensitive_steps_present`
- `i_am_home` -> `never`, если это только открытие домашнего URL и голосовая сводка
- любые batch-close сценарии -> confirmation обязателен

## 18. Visibility и UX

Протоколы должны быть видимы пользователю как first-class команды.

В visibility payload полезно добавить:
- `protocol_id`
- `protocol_title`
- `protocol_trigger`
- `protocol_step_index`

В CLI/UI это должно выглядеть понятно:
- `command: run_protocol: clean_slate`
- `current: step_2 close_app Telegram`
- `result: Completed protocol clean_slate with 4 step(s).`

В speech:
- `Запустил протокол чистый лист.`
- `Протокол "я дома" выполнен.`

## 19. Где хранить built-in протоколы

Есть два хороших варианта:

### Вариант A. Python-реестр

Например:
- `protocols/builtin_protocols.py`

Плюсы:
- быстрее старт;
- меньше I/O;
- проще рефакторить вместе с кодом.

Минусы:
- хуже масштабируется для non-code editing.

### Вариант B. YAML-файлы внутри repo

Например:
- `protocols/builtin/*.yaml`

Плюсы:
- ближе к user-defined модели;
- удобнее расширять.

Минусы:
- нужен loader уже на старте.

Рекомендация:
- built-in протоколы сначала держать в Python;
- user-defined протоколы читать из YAML;
- когда модель стабилизируется, можно перевести built-ins тоже в YAML.

## 20. Предлагаемый порядок внедрения

### Этап 1. Архитектурный каркас

Сделать:
- новый intent `run_protocol`;
- пакет `protocols/`;
- built-in registry;
- trigger matching;
- validator support;
- planner expansion в обычные `Step`;
- completion summary и speech support.

Результат этапа:
- протоколы существуют как доменная сущность;
- новые протоколы можно добавлять как built-ins.

### Этап 2. Persistence

Сделать:
- `state_store.py`;
- запись/чтение persisted state;
- сохранение `last_workspace_*`;
- сохранение `last_protocol_*`;
- безопасное чтение state для protocol inputs.

Результат этапа:
- можно делать сценарии уровня `я дома`, использующие данные прошлой сессии.

### Этап 3. Первые built-in протоколы

Сделать:
- `clean_slate`
- `i_am_home`

Результат этапа:
- два живых демонстрационных протокола на реальной архитектуре.

### Этап 4. Новые protocol capabilities

Сделать:
- `open_last_workspace`
- затем `play_music`
- затем, возможно, `speak_text`

Результат этапа:
- протоколы перестают быть только thin-wrapper над existing actions.

### Этап 5. User-defined protocols

Сделать:
- YAML loader;
- schema validation;
- безопасный whitelist action types;
- merge built-in + user registries;
- conflict resolution policy.

Результат этапа:
- пользователь может добавлять свои протоколы без правки Python-кода.

## 21. Технический план по файлам

### Новые файлы

- `protocols/__init__.py`
- `protocols/models.py`
- `protocols/registry.py`
- `protocols/resolver.py`
- `protocols/planner.py`
- `protocols/state_store.py`
- `protocols/builtin_protocols.py`
- `protocols/user_protocol_loader.py`
- `tests/test_protocol_registry.py`
- `tests/test_protocol_parser.py`
- `tests/test_protocol_planner.py`
- `tests/test_protocol_state_store.py`
- `tests/test_protocol_runtime.py`

### Изменяемые файлы

- `types/command.py`
- `parser/command_parser.py`
- `validator/command_validator.py`
- `planner/execution_planner.py`
- `runtime/runtime_manager.py`
- `executor/desktop_actions.py`
- `executor/desktop_executor.py`
- `voice/speech_presenter.py`
- `docs/command_model.md`
- `docs/product_rules.md`
- `docs/session_context.md`
- `docs/use_cases.md`
- `docs/desktop_actions.md`

## 22. Тестовая стратегия

### 22.1 Unit tests

Покрыть:
- trigger matching;
- protocol registry loading;
- built-in protocol resolution;
- unknown protocol handling;
- ambiguity handling;
- planner expansion;
- confirmation policy behavior;
- persisted state serialization.

### 22.2 Contract tests

Проверить:
- `run_protocol` не ломает existing precedence;
- протоколы не перехватывают обычные команды вроде `open code`;
- unknown protocol не уходит в ложный `open_app`.

### 22.3 Runtime smoke

Нужны smoke-сценарии:
- `протокол чистый лист`
- `я дома`
- `unknown protocol`
- `ambiguous protocol`

### 22.4 Voice tests

Проверить:
- `джарвис, я дома` нормализуется корректно;
- spoken completion для `run_protocol` звучит естественно;
- follow-up windows и confirmation не ломаются.

## 23. Риски

### 23.1 Главный архитектурный риск

Если начать хардкодить каждый протокол прямо в parser/runtime, система быстро станет нерасширяемой.

Поэтому обязательно:
- один реестр;
- одна модель протокола;
- одно место для expansion в шаги.

### 23.2 Главный продуктовый риск

`clean_slate` легко превратить в слишком опасную функцию.

Нужно сохранить строгие границы:
- protected apps;
- confirmation;
- честная коммуникация;
- отсутствие force-quit в MVP.

### 23.3 Риск ложной памяти

Если `i_am_home` начнет “вспоминать”, над чем пользователь работал, без явного persisted state, ответы будут ненадежными.

Поэтому:
- только явно сохраненные поля;
- никаких свободных догадок.

### 23.4 Риск слишком мощной extensibility

Если позволить YAML-протоколам исполнять shell или AppleScript, это разрушит safety и предсказуемость.

Расширяемость должна быть:
- declarative;
- schema-validated;
- capability-bounded.

## 24. Рекомендуемое MVP-решение

Если выбирать самый здоровый путь, MVP должен быть таким:

1. Ввести `run_protocol` и `protocols/registry.py`.
2. Сделать built-in протоколы как кодовый реестр.
3. Добавить persisted state store отдельно от `SessionContext`.
4. Реализовать `i_am_home` через:
   - open конкретный домашний YouTube URL;
   - spoken completion summary с названием последнего проекта.
5. Реализовать `clean_slate` только как safe batch-close с обязательным confirmation.
6. Только после этого открывать user-defined YAML protocols.

## 25. Definition of done для первой полноценной версии

Фича протоколов считается внедренной, когда:
- пользователь может сказать `протокол чистый лист` и получить видимый подтверждаемый сценарий cleanup;
- пользователь может сказать `я дома` и получить открытие домашнего музыкального URL плюс реплику с названием последнего проекта;
- новый built-in протокол добавляется через реестр без изменений в core runtime;
- user-defined protocol может быть добавлен декларативно;
- протоколы проходят через тот же supervised runtime, что и обычные команды;
- все чувствительные действия остаются под confirmation;
- есть unit, contract и smoke coverage.

## 26. Следующий практический шаг

Следующим шагом после этого документа лучше всего делать не `clean_slate`, а каркас:
- `run_protocol`
- `protocols/registry.py`
- built-in protocol support

Причина:
- это создаст правильную архитектурную основу;
- и `clean_slate`, и `i_am_home` потом лягут в нее как обычные протоколы, а не как два специальных хака.
