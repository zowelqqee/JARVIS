# Архитектура JARVIS

## 1. Главная мысль

Архитектура этого проекта построена вокруг одной простой идеи:

- на вход приходит одна фраза пользователя;
- система сначала решает, это **команда** или **вопрос**;
- дальше она идет либо в ветку выполнения, либо в ветку ответа;
- обе ветки пользуются общим коротким контекстом сессии и общим слоем показа результата.

То есть здесь не одна огромная "магическая" функция.
Здесь набор небольших слоев, у каждого свой кусок работы.

## 2. Самая общая схема

```text
Пользователь
   |
   v
`cli.py`
   |
   v
`interaction/interaction_manager.py`
   |
   v
`interaction/interaction_router.py`
   |
   +---------------------------+
   |                           |
   |                           |
   v                           v
ветка команд                   ветка вопросов
`runtime/runtime_manager.py`   `qa/answer_engine.py`
   |                           |
   v                           v
разбор -> проверка ->          классификация вопроса ->
уточнение -> план ->           выбор источников ->
подтверждение ->               выбор движка ответа ->
выполнение                     проверка ответа
   |                           |
   +-------------+-------------+
                 |
                 v
      `ui/visibility_mapper.py`
                 |
                 v
   `ui/interaction_presenter.py`
                 |
                 v
        консоль и голосовой вывод
```

## 3. Где лежат основные слои

```text
1. Вход
   `cli.py`
   `input/`
   `voice/`

2. Выбор пути
   `interaction/`

3. Ветка команд
   `runtime/`
   `parser/`
   `validator/`
   `clarification/`
   `confirmation/`
   `planner/`
   `executor/`

4. Ветка вопросов
   `qa/`

5. Общие структуры
   `types/`
   `context/`

6. Показ результата
   `ui/`
   `voice/speech_presenter.py`

7. Проверки качества и раскатка
   `tests/`
   `evals/`
   `scripts/`
   часть файлов в `qa/`
```

## 4. Командная ветка по шагам

### Схема

```text
`cli.py`
   |
   v
`InteractionManager.handle_input()`
   |
   v
`route_interaction()`
   |
   v
`RuntimeManager.handle_input()`
   |
   v
`normalize_input()`
   |
   v
`parse_command()`
   |
   v
`validate_command()`
   |
   +------------------------+
   |                        |
   | ошибка, неясность      | все хорошо
   v                        v
`build_clarification()`     `build_execution_plan()`
   |                        |
   v                        v
ожидание ответа             шаги `Step`
   |                        |
   v                        v
`apply_clarification()`     `request_confirmation()` если нужно
   |                        |
   +------------+-----------+
                |
                v
         `execute_step()`
                |
                v
      `map_visibility()` 

                |
                v
   `interaction_output_lines()`
```

### Кто с кем связан в командной ветке

| Файл | Что делает | Кто вызывает | Кого вызывает дальше |
|---|---|---|---|
| `cli.py` | Принимает ввод пользователя | Пользователь | `InteractionManager` |
| `interaction/interaction_manager.py` | Выбирает верхний путь | `cli.py` | `interaction_router.py`, `runtime/runtime_manager.py` |
| `interaction/interaction_router.py` | Решает, это команда, вопрос или уточнение | `InteractionManager` | Возвращает решение наверх |
| `runtime/runtime_manager.py` | Ведет всю жизнь команды | `InteractionManager` | `input/adapter.py`, `parser/command_parser.py`, `validator/command_validator.py`, `clarification/clarification_handler.py`, `planner/execution_planner.py`, `confirmation/confirmation_gate.py`, `executor/desktop_executor.py`, `ui/visibility_mapper.py` |
| `parser/command_parser.py` | Делает `Command` из текста | `RuntimeManager` | Возвращает `Command` |
| `validator/command_validator.py` | Проверяет структуру команды | `RuntimeManager` | Возвращает `ValidationResult` |
| `clarification/clarification_handler.py` | Строит вопрос и применяет ответ пользователя | `RuntimeManager` | Возвращает `ClarificationRequest` или обновленный `Command` |
| `planner/execution_planner.py` | Делает шаги `Step` | `RuntimeManager` | Возвращает `PlannedCommand` |
| `confirmation/confirmation_gate.py` | Строит запрос подтверждения | `RuntimeManager` | Возвращает `ConfirmationRequest` |
| `executor/desktop_executor.py` | Выполняет один шаг на macOS | `RuntimeManager` | Возвращает `ActionResult` |
| `ui/visibility_mapper.py` | Переводит внутреннее состояние в понятный вид | `RuntimeManager` | Возвращает словарь видимости |
| `ui/interaction_presenter.py` | Делает строки для консоли | `cli.py` | Печать результата |

## 5. Ветка вопросов по шагам

### Схема

```text
`cli.py`
   |
   v
`InteractionManager.handle_input()`
   |
   v
`route_interaction()`
   |
   v
`answer_question()`
   |
   v
`classify_question()`
   |
   v
`build_grounding_bundle()`
   |
   +------------------------------+
   |                              |
   v                              v
`select_sources()`                runtime/session facts
   |                              |
   v                              |
`source_registry.py`              |
   |                              |
   +--------------+---------------+
                  |
                  v
     выбор движка ответа
     `deterministic_backend`
        или
     `llm_backend`
                  |
                  v
 `ensure_source_attributions()`
                  |
                  v
 `map_interaction_visibility()`
                  |
                  v
 `interaction_output_lines()`
```

### Кто с кем связан в ветке вопросов

| Файл | Что делает | Кто вызывает | Кого вызывает дальше |
|---|---|---|---|
| `interaction/interaction_manager.py` | Отправляет вопрос в ветку ответов | `cli.py` | `qa/answer_engine.py` |
| `qa/answer_engine.py` | Главный вход в ответ | `InteractionManager` | `classify_question()`, `qa/grounding.py`, выбранный движок ответа, `qa/grounding_verifier.py` |
| `qa/source_selector.py` | Выбирает допустимые источники под вопрос | `qa/grounding.py` | `qa/source_registry.py` |
| `qa/source_registry.py` | Хранит карту "тип вопроса -> разрешенные источники" | `qa/source_selector.py` | Возвращает `GroundingSource` |
| `qa/grounding.py` | Собирает пакет источников и фактов | `qa/answer_engine.py` | `qa/source_selector.py` |
| `qa/deterministic_backend.py` | Отвечает по локальным правилам и шаблонам | `qa/answer_engine.py` или `qa/llm_backend.py` как запасной путь | Возвращает `AnswerResult` |
| `qa/llm_backend.py` | Ведет путь через модель и умеет откатиться на простой ответ | `qa/answer_engine.py` | `qa/openai_responses_provider.py`, иногда `qa/deterministic_backend.py` |
| `qa/openai_responses_provider.py` | Готовит запрос в OpenAI и разбирает ответ | `qa/llm_backend.py` | `qa/openai_responses_prompt.py`, `qa/openai_responses_transport.py`, `qa/openai_responses_parser.py` или `qa/openai_responses_general_parser.py` |
| `qa/grounding_verifier.py` | Проверяет, что ответ честный и опирается на разрешенные источники | `qa/answer_engine.py`, `qa/openai_responses_parser.py` | Возвращает проверенный результат или ошибку |
| `ui/visibility_mapper.py` | Делает видимый словарь для ответа | `InteractionManager` | `ui/interaction_presenter.py` |

## 6. Путь через OpenAI внутри ветки вопросов

Это уже не весь проект, а только внутренность модельного пути.

```text
`qa/llm_backend.py`
   |
   v
`qa/openai_responses_provider.py`
   |
   +---------------------------------------------+
   |                                             |
   v                                             v
локально обоснованный режим                      широкий режим
`openai_responses_prompt.py`                     `openai_responses_general_prompt.py`
`openai_responses_schema.py`                     `openai_responses_general_schema.py`
`openai_responses_parser.py`                     `openai_responses_general_parser.py`
   |                                             |
   +-------------------+-------------------------+
                       |
                       v
      `openai_responses_transport.py`
                       |
                       v
              OpenAI Responses API
```

Что важно понимать:

- путь через модель не должен сам решать, это команда или вопрос;
- путь через модель не должен сам подбирать произвольные локальные источники;
- сначала всегда выбирается верхний режим;
- потом выбираются допустимые источники;
- и только потом модель получает узко ограниченный запрос.

## 7. Голосовой путь

### Схема

```text
Пользователь говорит
   |
   v
`cli.py` команда `voice`
   |
   v
`voice/session.py`
   |
   v
`voice/asr_service.py`
   |
   v
`input/voice_input.py`
   |
   v
`input/macos_voice_capture.m`
   |
   v
распознанный текст
   |
   v
`input/voice_normalization.py`
   |
   v
обычный текстовый ввод в `InteractionManager`
```

### Озвучка ответа

```text
результат работы
   |
   v
`voice/speech_presenter.py`
   |
   v
`voice/tts_provider.py`
   |
   v
`voice/tts_macos.py`
   |
   v
macOS `say`
```

## 8. Где находится короткая память сессии

Файл: `context/session_context.py`

Связи:

- `cli.py` создает один объект `SessionContext`;
- `InteractionManager` передает его вниз;
- `RuntimeManager` обновляет его после шагов, ошибок, подтверждений и поиска;
- ветка ответов читает его, когда нужен недавний контекст;
- голосовая часть напрямую в него не пишет, она только поставляет нормализованный текст.

Упрощенная схема:

```text
              `SessionContext`
              /      |       \
             /       |        \
            v        v         v
`RuntimeManager`  `InteractionManager`  `qa/answer_engine.py`
   пишет             пишет               читает
```

Что там хранится по смыслу:

- активная команда;
- шаг выполнения;
- последние понятные цели;
- недавняя папка проекта;
- недавние результаты поиска;
- недавний ответ и его источники;
- временные данные для продолжения после уточнения.

## 9. Где проект держит общие структуры

Папка `types/` - это фундамент, на который смотрят почти все слои.

Связи можно представить так:

```text
`types/command.py` <----- parser / validator / planner / runtime
`types/target.py`  <----- parser / planner / executor / context
`types/step.py`    <----- planner / runtime / executor / ui
`types/question_request.py` <----- qa/answer_engine.py / qa/*
`types/answer_result.py`    <----- qa/* / ui/*
`types/jarvis_error.py`     <----- почти все слои
`types/interaction_result.py` <--- InteractionManager / cli
```

Почему это важно:

- по этим файлам быстро видно форму данных;
- если данные меняются, почти всегда придется пройтись по нескольким слоям;
- это помогает не делать скрытых несовместимых изменений.

## 10. Порядок связей в `RuntimeManager`

Если нужно понять один файл глубже, то `runtime/runtime_manager.py` полезно читать как главный сценарий.

Он связан почти со всем командным слоем:

```text
`RuntimeManager`
   |
   +-> `normalize_input()`
   +-> `parse_command()`
   +-> `validate_command()`
   +-> `build_clarification()`
   +-> `apply_clarification()`
   +-> `build_execution_plan()`
   +-> `request_confirmation()`
   +-> `execute_step()`
   +-> `map_visibility()`
   +-> `SessionContext`
```

То есть этот файл - не "исполнитель".
Он именно **ведущий команды**.
Он решает, на каком этапе команда находится и что делать дальше.

## 11. Порядок связей в `InteractionManager`

`interaction/interaction_manager.py` - это верхняя развилка всего проекта.

Его роль:

- посмотреть на текущий ввод;
- учесть, нет ли уже незавершенного уточнения;
- вызвать `route_interaction()`;
- если это команда, отправить в `RuntimeManager`;
- если это вопрос, отправить в `answer_question()`;
- сохранить контекст недавнего ответа;
- вернуть единый `InteractionResult`.

Схема:

```text
`InteractionManager`
   |
   +-> `route_interaction()`
   |
   +-> если `command`
   |      -> `RuntimeManager.handle_input()`
   |
   +-> если `question`
   |      -> `answer_question()`
   |
   +-> `map_interaction_visibility()`
```

Это один из самых полезных файлов, если нужно быстро понять весь репозиторий.

## 12. Где проект показывает пользователю правду о состоянии

Есть два важных файла:

- `ui/visibility_mapper.py`
- `ui/interaction_presenter.py`

Разница между ними такая:

- `visibility_mapper.py` решает, **что именно надо показать**;
- `interaction_presenter.py` решает, **как это написать строками**.

То есть первый файл ближе к смыслу, а второй ближе к тексту.

Пример связей:

```text
внутреннее состояние
   |
   v
`map_visibility()` или `map_interaction_visibility()`
   |
   v
словарь видимого состояния
   |
   v
`interaction_output_lines()`
   |
   v
печать в CLI
```

## 13. Где лежит спецификация, а где реализация

Очень полезно не путать эти два уровня.

### Спецификация

Это в основном:

- `docs/`
- `tests/`
- `evals/`

Они отвечают на вопрос:

- как проект **должен** вести себя;
- какие сценарии считаются правильными;
- что нужно проверить перед включением модели по умолчанию.

### Реализация

Это в основном:

- `cli.py`
- `interaction/`
- `runtime/`
- `parser/`
- `validator/`
- `clarification/`
- `planner/`
- `executor/`
- `qa/`
- `ui/`
- `voice/`

Они отвечают на вопрос:

- как проект **фактически** это делает.

## 14. Слой проверок качества и раскатки

Этот слой живет немного сбоку от основного продукта.

Схема:

```text
`evals/qa_cases.json`
   |
   v
`evals/run_qa_eval.py`
   |
   +-> сравнение профилей
   +-> подсчет метрик
   +-> gate для переключения пути по умолчанию
   |
   v
артефакты в `tmp/qa/`
   |
   v
`qa/rollout_stability.py`
`qa/manual_beta_checklist.py`
`qa/beta_release_review.py`
`qa/beta_readiness.py`
```

Что это значит по-простому:

- автор проекта не просто добавил путь через модель;
- он добавил еще слой, который должен доказать, что этот путь не портит поведение;
- это одна из причин, почему в проекте так много файлов вокруг QA.

## 15. Самые важные связи между файлами

Если нужен короткий список "какие связи помнить всегда", то вот он:

- `cli.py` -> `interaction/interaction_manager.py`
- `interaction/interaction_manager.py` -> `interaction/interaction_router.py`
- `interaction/interaction_manager.py` -> `runtime/runtime_manager.py`
- `interaction/interaction_manager.py` -> `qa/answer_engine.py`
- `runtime/runtime_manager.py` -> `parser/command_parser.py`
- `runtime/runtime_manager.py` -> `validator/command_validator.py`
- `runtime/runtime_manager.py` -> `clarification/clarification_handler.py`
- `runtime/runtime_manager.py` -> `planner/execution_planner.py`
- `runtime/runtime_manager.py` -> `confirmation/confirmation_gate.py`
- `runtime/runtime_manager.py` -> `executor/desktop_executor.py`
- `runtime/runtime_manager.py` -> `ui/visibility_mapper.py`
- `qa/answer_engine.py` -> `qa/source_selector.py`
- `qa/source_selector.py` -> `qa/source_registry.py`
- `qa/answer_engine.py` -> `qa/deterministic_backend.py`
- `qa/answer_engine.py` -> `qa/llm_backend.py`
- `qa/llm_backend.py` -> `qa/openai_responses_provider.py`
- `qa/openai_responses_provider.py` -> `qa/openai_responses_transport.py`
- `qa/openai_responses_provider.py` -> `qa/openai_responses_parser.py`
- `qa/openai_responses_provider.py` -> `qa/openai_responses_general_parser.py`
- `ui/interaction_presenter.py` -> `voice/speech_presenter.py`

## 16. Куда смотреть, если хочешь менять конкретную часть

### Хочу менять разбор фраз

Смотри:

- `interaction/interaction_router.py`
- `parser/command_parser.py`
- `input/voice_normalization.py`

### Хочу менять правила безопасности и блокировки

Смотри:

- `validator/command_validator.py`
- `clarification/clarification_handler.py`
- `confirmation/confirmation_gate.py`
- `runtime/runtime_manager.py`
- `qa/general_qa_safety.py`

### Хочу менять реальные действия на рабочем столе

Смотри:

- `executor/desktop_actions.py`
- `executor/desktop_executor.py`
- `planner/execution_planner.py`

### Хочу менять ответы на вопросы

Смотри:

- `qa/answer_engine.py`
- `qa/deterministic_backend.py`
- `qa/source_selector.py`
- `qa/source_registry.py`
- `qa/grounding.py`
- `qa/grounding_verifier.py`

### Хочу менять путь через OpenAI

Смотри:

- `qa/answer_config.py`
- `qa/llm_backend.py`
- `qa/openai_responses_provider.py`
- `qa/openai_responses_prompt.py`
- `qa/openai_responses_schema.py`
- `qa/openai_responses_parser.py`
- `qa/openai_responses_transport.py`
- широкие аналоги с `general_`

### Хочу менять то, что видит пользователь

Смотри:

- `ui/visibility_mapper.py`
- `ui/interaction_presenter.py`
- `voice/speech_presenter.py`

## 17. Важные архитектурные выводы

Если сжать всю архитектуру в несколько честных выводов, получится так:

1. Проект построен не вокруг модели, а вокруг маршрута обработки ввода.
2. Главная развилка находится в `interaction/`.
3. Командная ветка и ветка ответов специально разделены.
4. `RuntimeManager` - это сердце командной ветки.
5. `answer_engine.py` - это сердце ветки ответов.
6. `SessionContext` - короткая память между шагами и соседними вопросами.
7. `ui/` показывает состояние, но не принимает решения за систему.
8. Голосовой слой подает и озвучивает текст, но не меняет смысл работы продукта.
9. Вокруг модельного пути есть отдельный слой проверок, артефактов и правил раскатки.

Если держать в голове именно эти девять пунктов, архитектура проекта становится очень ясной.
