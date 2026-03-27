# План интеграции русского голосового ввода

## Цель

Сделать так, чтобы пользователь мог говорить по-русски в `voice`-режиме, а JARVIS:

- корректно распознавал русскую речь;
- маршрутизировал русский голосовой ввод в уже существующие question/command path;
- не ломал текущий английский voice path;
- не терял safety-гарантии для confirmation / clarification / command execution.

## Что есть сейчас

Текущий голосовой пайплайн уже существует, но он почти полностью англоязычный.

- `input/macos_voice_capture.m`
  - one-shot macOS helper на `Speech.framework`;
  - recognizer сейчас выбирается в порядке `en-US -> current locale -> default recognizer`.
- `input/voice_input.py`
  - обёртка над helper;
  - отвечает за rebuild / retry / codesign / structured errors.
- `cli.py`
  - вызывает `capture_voice_input(...)`;
  - после этого делает только простую детерминированную нормализацию;
  - wake-word и voice starters сейчас английские (`Jarvis`, `Hey Jarvis`, `open`, `what`, `how` и т.д.).
- `interaction/interaction_router.py`
  - роутинг command vs question vs clarification сейчас завязан на английские маркеры.
- `parser/command_parser.py`
  - confirmation, denial, command verbs и aliases сейчас англоязычные.
- `qa/answer_engine.py`
  - deterministic question classification тоже завязана на английские паттерны.

Вывод: одного переключения speech locale на `ru-RU` недостаточно. Если просто включить русское распознавание, downstream-роутер и parser всё равно не поймут большую часть русского текста.

## Рекомендуемый подход

Самый быстрый и качественный путь для MVP: не переписывать весь parser/router под русский с нуля, а добавить узкий слой русской нормализации и русские question markers в нужных местах.

Рекомендуемая архитектура:

1. Helper начинает уверенно распознавать русский.
2. CLI/voice normalization умеет:
   - удалить русские wake-слова;
   - привести самые важные русские команды и fixed questions к каноническим формам.
3. Router и answer engine получают минимальную русскую поверхность:
   - распознают, что русский ввод является вопросом;
   - умеют отнести fixed Russian prompts к существующим question families;
   - open-domain русский вопрос пропускают дальше как question, а не как fallback command.
4. Английский path остаётся рабочим и покрытым существующими тестами.

## Что именно делать

### Phase 1. Locale-aware speech capture

Цель: helper должен сначала пытаться распознавать `ru-RU`, но не ломать английский.

Файлы:

- `input/macos_voice_capture.m`
- `input/voice_input.py`

Изменения:

- Вынести выбор recognizer в locale chain, а не в жёсткий `en-US -> current -> default`.
- Поддержать явный список preferred locales, например:
  - `ru-RU,en-US`
  - `en-US,ru-RU`
- Передавать этот список в helper из Python-обёртки.
- Для локального CLI-использования по умолчанию рекомендовать приоритет:
  - `ru-RU,en-US`

Практическая форма:

- Добавить в `input/voice_input.py` новый конфиг входа, например:
  - параметр `preferred_locales: Sequence[str] | None`
  - и/или env `JARVIS_VOICE_LOCALES=ru-RU,en-US`
- В `input/macos_voice_capture.m` попробовать locale identifiers по порядку и взять первый доступный `SFSpeechRecognizer`.

Acceptance criteria:

- Русская речь больше не зависит от случайного `current locale`.
- Английская речь не теряется, потому что есть fallback на `en-US`.

### Phase 2. Русская voice normalization

Цель: распознанный русский текст должен превращаться в нормальный вход для текущей системы.

Файлы:

- `cli.py`
- новый модуль, лучше отдельный:
  - `input/voice_normalization.py`

Изменения:

- Добавить русские wake-слова:
  - `джарвис`
  - `эй джарвис`
  - при этом сохранить `Jarvis`, `Hey Jarvis`, `Ok Jarvis`
- Добавить русские starters для voice normalization:
  - commands: `открой`, `запусти`, `закрой`, `покажи`, `найди`, `подготовь`, `используй`
  - questions: `что`, `как`, `почему`, `зачем`, `где`, `когда`, `кто`, `какие`, `объясни`, `помоги`
- Не тащить всю русскую логику в `cli.py`; лучше вынести в отдельный helper.

Важно:

- Здесь не нужно делать «полный перевод русского в английский».
- Нужен узкий канонический слой только для тех фраз, которые должны надёжно попадать в существующий deterministic path.

Примеры для MVP:

- `джарвис открой телеграм` -> `open telegram`
- `джарвис открой сафари` -> `open safari`
- `что ты умеешь` -> `what can you do`
- `что именно тебе нужно подтвердить` -> `what exactly do you need me to confirm`

Acceptance criteria:

- Русский wake-word снимается корректно.
- Повтор одной и той же русской команды нормализуется так же стабильно, как и в английских voice fixtures.

### Phase 3. Русский routing для question vs command

Цель: русский голосовой ввод не должен падать в `fallback_command` только потому, что он не на английском.

Файлы:

- `interaction/interaction_router.py`
- `qa/answer_engine.py`

Изменения:

- Добавить русские question starters и markers в router:
  - `что`, `как`, `почему`, `зачем`, `где`, `когда`, `кто`, `объясни`
- Добавить русские mixed-input markers:
  - `и открой`
  - `а потом открой`
  - `и запусти`
- Добавить русские blocked-state question markers:
  - `что ты ждешь`
  - `что тебе нужно`
  - `что именно тебе нужно подтвердить`
- В `qa/answer_engine.py` добавить русские fixed question patterns для основных grounded families:
  - capabilities
  - blocked_state
  - safety explanation
  - docs clarification
- Для общего русского вопроса, который не попал в fixed grounded family, маршрут должен вести в `OPEN_DOMAIN_GENERAL`, а не в unsupported/fallback command.

Это важно: open-domain русский вопрос лучше сохранить в исходном виде и передать дальше как вопрос. Не нужно сначала переводить его на английский, если речь идёт о GPT path.

Acceptance criteria:

- `кто президент Франции` -> question path
- `почему небо голубое` -> open-domain question path
- `что именно тебе нужно подтвердить` в blocked state -> grounded blocked-state answer

### Phase 4. Русский deterministic command surface

Цель: базовые русские голосовые команды должны работать end-to-end, а не только распознаваться.

Файлы:

- `parser/command_parser.py`
- возможно `input/adapter.py`, если туда логичнее вынести канонизацию

Изменения:

- Добавить русские confirmation/deny варианты:
  - `да`, `ага`, `подтверждаю`
  - `нет`, `отмена`, `стоп`
- Добавить MVP-команды:
  - `открой`
  - `запусти`
  - `закрой`
  - `покажи окна`
  - `найди`
- Добавить русские app aliases:
  - `телеграм` -> `Telegram`
  - `сафари` -> `Safari`

Рекомендация:

- Для MVP лучше не строить полноценный русский parser.
- Лучше либо:
  - нормализовать ограниченный набор русских команд в канонический английский перед parser;
  - либо добавить узкий русский синонимический слой рядом с текущими английскими паттернами.

Первый вариант проще и безопаснее для текущей архитектуры.

Acceptance criteria:

- `открой телеграм` -> `open_app: Telegram`
- `закрой телеграм` -> `awaiting_confirmation`
- `да` / `нет` работают как confirmation reply

### Phase 5. Тесты и eval coverage

Цель: зафиксировать русский path контрактами, а не ручными обещаниями.

Файлы:

- `tests/test_voice_input_contract.py`
- `tests/test_cli_smoke.py`
- `tests/test_interaction_router.py`
- `tests/test_answer_engine.py`
- `tests/test_interaction_manager.py`
- `evals/qa_cases.json`
- `docs/manual_verification_commands.md`

Что добавить:

- Voice normalization tests:
  - `Джарвис, открой телеграм`
  - `Эй Джарвис, открой сафари`
  - `Что ты умеешь что ты умеешь`
- Routing tests:
  - `кто президент Франции`
  - `почему небо голубое`
  - `что ты умеешь и открой сафари`
- Confirmation tests:
  - `закрой телеграм` -> blocked
  - `что именно тебе нужно подтвердить`
  - `да` / `нет`
- Manual verification section:
  - русский voice happy path
  - русский blocked-state follow-up
  - русский open-domain question

Acceptance criteria:

- Английские voice tests продолжают проходить.
- Русские voice tests появляются как отдельный locked contract.

## Рекомендуемый MVP scope

Чтобы сделать быстро и качественно, рекомендую такой MVP scope:

- locale chain: `ru-RU -> en-US`
- русские wake-слова
- русские question markers
- канонизация 5-8 самых важных русских команд/фраз
- базовые русские confirmation replies
- open-domain русские вопросы как `question`, без попытки всё переводить

Этого уже достаточно, чтобы пользователь мог:

- спросить по-русски общий вопрос;
- спросить по-русски grounded/fixed вопрос;
- дать по-русски базовую голосовую команду;
- подтвердить или отменить действие по-русски.

## Что не нужно делать в первой версии

- Не нужно переписывать весь command parser целиком под русский.
- Не нужно добавлять «полный переводчик» всех русских фраз в английские.
- Не нужно сначала поддерживать все падежи, свободный порядок слов и разговорные варианты.
- Не нужно менять voice failure contracts и privacy path.

## Риски

- `Speech.framework` может по-разному вести себя на смешанной русско-английской речи, особенно для названий приложений.
- Русские вопросы без явного вопросительного маркера могут по-прежнему хуже маршрутизироваться.
- Слишком агрессивная канонизация может сломать английский voice path.
- Слишком широкая поддержка русского на первом шаге создаст много edge cases и замедлит поставку.

## Порядок реализации

Рекомендую идти в таком порядке:

1. Locale chain в helper + Python wrapper.
2. Русские wake-слова и русская voice normalization.
3. Русские question markers в router и answer engine.
4. Узкий русский command MVP.
5. Тесты и manual verification.

Именно в таком порядке мы быстрее получим реальный пользовательский эффект:

- сначала JARVIS хотя бы начнёт слышать русский;
- потом начнёт правильно понимать русские вопросы;
- потом уже стабильно исполнять базовые русские команды.

## Definition of Done для MVP

Считаем задачу закрытой, если на macOS проходят такие сценарии:

- `voice` -> `Джарвис, кто президент Франции?`
  - результат: `mode: question`
  - `answer-kind: open_domain_model`
- `voice` -> `Джарвис, что ты умеешь?`
  - результат: grounded capabilities answer
- `voice` -> `Джарвис, открой Телеграм`
  - результат: command path `open_app`
- `voice` -> `Джарвис, закрой Телеграм`
  - результат: `awaiting_confirmation`
- follow-up голосом: `Что именно тебе нужно подтвердить?`
  - результат: grounded blocked-state answer
- follow-up голосом: `Да` / `Нет`
  - результат: confirmation/cancel path
- английские voice fixtures остаются зелёными

## Итог

Если делать это «быстро, но качественно», то правильный путь такой:

- не переписывать всё под русский с нуля;
- сначала включить `ru-RU` в speech helper;
- затем добавить узкий русский normalization + routing слой;
- и только потом расширять русский command surface.

Это даст работающий русский voice MVP без поломки текущего английского и без лишнего архитектурного долга.
