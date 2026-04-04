# Voice Remaining Plan

## Зачем этот документ

Этот файл не дублирует `voiceover_plan.md`, а фиксирует именно то, что ещё осталось сделать от текущего состояния репозитория до нужного практического результата:

- voice mode работает не только в тестах, но и вживую;
- bounded conversation mode ощущается как нормальный голосовой UX, а не как терминал с микрофоном;
- есть operator evidence, по которому можно принимать rollout-решения;
- остаётся сохранённым text-first core и минимально-инвазивная архитектура.

## Что считаем "нужным результатом"

Под "нужным результатом" в этом документе понимается не абстрактный идеал, а конкретная рабочая цель для текущей codebase:

- single-turn voice path стабилен;
- bounded multi-turn voice path под флагом реально проверен живым микрофоном;
- spoken output звучит коротко, понятно и без логового мусора;
- follow-up UX не раздражает и не ломает command/question routing;
- есть readiness/telemetry/gate evidence;
- advanced voice mode всё ещё может оставаться opt-in, но уже не висит в состоянии "теоретически собрано, practically не проверено".

## Текущая отправная точка

На момент создания этого документа уже есть:

- выделенный TTS слой;
- speech-specific presenter;
- locale-aware voice/TTS path для `ru/en`;
- bounded follow-up loop под `JARVIS_VOICE_CONTINUOUS_MODE=1`;
- follow-up controls (`listen again`, `stop speaking`, dismiss/relisten surface);
- answer-follow-up surface (`repeat`, `say more`, `which source`, `why`, русские эквиваленты);
- voice telemetry / readiness / gate / status / last / mode helpers;
- voice eval corpus для `ru/en` command/question/follow-up/failure cases;
- speech sanitization для markdown, путей, URL, debug tails и refusal surface;
- latency filler для медленного question-like voice path.

Это уже хороший фундамент. Основной незакрытый объём теперь лежит не в базовой архитектуре, а в live validation, UX-polish и audio control semantics.

## Главные незакрытые зоны

### 1. Live validation всё ещё не завершён

Сейчас unit/eval покрытие уже сильное, но нет подтверждённого живого voice smoke в текущем цикле.

Что это значит:

- мы не знаем, как текущий flow реально ощущается с микрофоном;
- не подтверждены реальные macOS permission и helper edge cases;
- bounded follow-up mode под флагом всё ещё не доказан как реальный UX, а не только как тестовый контракт.

### 2. Conversation UX ещё не полностью "естественный"

Уже есть bounded loop, retries, controls и filler, но ещё остаются UX-дыры:

- не до конца зафиксирована политика auto re-listen по всем типам follow-up;
- ещё нет earcons;
- нет live-validated решения, насколько хорошо работают follow-up timeout и closure;
- нет подтверждения, что 2-3 голосовых turn подряд ощущаются естественно именно вживую.

### 3. Audio excellence почти целиком впереди

Здесь самый тяжёлый оставшийся технический блок:

- controlled TTS interruption;
- barge-in contract;
- более зрелая `voice/audio_policy.py`;
- защита от self-feedback не только архитектурно, но и в реальном UX.

### 4. Spoken quality уже хорошая, но ещё не финальная

Осталось добить:

- умное spoken summarization длинных open-domain answers;
- более явную language policy для TTS voice selection;
- ещё несколько deterministic `ru` templates там, где возможен English fallback;
- короткие source references, полезные именно на слух.

### 5. Rollout story ещё не доведена до release-grade

Даже после live QA останется сделать:

- понятный default-on readiness criterion;
- регулярный voice eval / hygiene workflow;
- операторский rollback protocol;
- явные rollout уровни для single-turn, bounded mode и future advanced mode.

## План работ

Ниже порядок задач дан не "по красоте архитектуры", а по product impact и снижению риска.

## Phase 1. Закрыть live manual verification

### Цель

Подтвердить, что текущий bounded voice mode работает в реальном микрофонном сценарии, а не только в unit/eval.

### Что сделать

1. Пройти `docs/manual_voice_verification.md` вручную на macOS.
2. Прогнать сценарии:
   - русский command path;
   - английский command path;
   - русский question path;
   - mixed question+command clarification;
   - confirmation approve/deny;
   - short-answer follow-up;
   - `repeat` / `say more` / `source` follow-ups;
   - `listen again` / `stop speaking` / dismiss surface;
   - latency filler path при `speak on`.
3. Собрать evidence:
   - `voice telemetry write`;
   - `voice readiness write`;
   - `voice gate`.
4. Зафиксировать реальные проблемы, найденные вживую.

### Выход

- один живой список реальных regressions;
- readiness artifact;
- telemetry artifact;
- понятный статус: bounded mode ready или blocked.

### Acceptance

- checklist пройден без неясных мест;
- все blocker'ы перечислены явно;
- `voice gate` отражает реальное состояние, а не "бумажную готовность".

## Phase 2. Исправить только реальные live blockers

### Цель

Не делать абстрактный рефактор, а закрыть только то, что действительно болит в живом использовании.

### Типовые классы проблем, которые здесь ожидаем

- macOS permissions / helper failure surface;
- слишком длинные или навязчивые spoken ответы;
- follow-up окно открывается не там, где нужно;
- наоборот, follow-up не открывается там, где нужен;
- relisten/dismiss controls ощущаются неинтуитивно;
- latency filler звучит слишком часто или слишком поздно;
- spoken locale/voice mismatch.

### Правило фазы

Каждая правка должна привязываться к конкретному live observation и закрепляться тестом или runbook update.

### Acceptance

- после повторного ручного smoke те же blocker'ы не воспроизводятся;
- не добавлен большой нерелевантный рефактор вокруг voice path.

## Phase 3. Довести bounded conversation UX

### Цель

Сделать 2-3 голосовых turn подряд естественными и предсказуемыми.

### Подзадачи

1. Финализировать auto re-listen policy.
   Нужно чётко определить:
   - сколько раз и в каких состояниях re-listen допустим;
   - чем отличается empty capture от explicit `listen again`;
   - где loop должен закрываться сразу.

2. Earcons.
   Добавить и проверить:
   - listening start;
   - listening stop;
   - error;
   - optionally speaking start.

3. Уточнить follow-up close semantics.
   Нужно стабилизировать:
   - timeout close;
   - dismiss close;
   - no-speech close;
   - limit close.

4. Проверить short-answer policy.
   Надо подтвердить, что auto follow-up после короткого ответа:
   - не открывается слишком часто;
   - не мешает обычному answer flow;
   - не выглядит как навязчивый второй вопрос после каждого ответа.

5. Дошлифовать spoken prompts.
   Особенно:
   - confirmation prompts;
   - ambiguity prompts;
   - timeout / close / limit-reached prompts.

### Acceptance

- bounded mode ощущается как один разговор, а не как серия несвязанных shell calls;
- пользователю редко нужно возвращаться к клавиатуре;
- follow-up loop закрывается предсказуемо и не раздражает.

## Phase 4. Audio excellence

### Цель

Убрать самый заметный разрыв между "рабочим MVP" и "хорошим голосовым ассистентом".

### Подзадачи

1. Controlled TTS interruption.
   Нужен контракт:
   - как прервать длинный spoken answer;
   - что делать с уже идущим `say`;
   - как это отражается в CLI state.

2. Barge-in contract.
   Нужно зафиксировать:
   - что считается прерыванием;
   - когда capture можно открывать поверх/после TTS;
   - как избежать гонок между speaking и listening.

3. Усилить `voice/audio_policy.py`.
   Нужно довести до явной политики:
   - stop-speaking-before-listening;
   - pause/resume semantics;
   - self-feedback suppression.

4. Hook под future VAD/silence tuning.
   Не обязательно полноценно реализовать VAD сейчас, но нужен чистый extension point.

5. Noisy environment UX.
   Нужно описать и проверить:
   - repeated misses;
   - partial recognition;
   - noisy room behavior;
   - how fast system gives up vs keeps trying.

### Acceptance

- TTS не мешает следующему capture;
- длинный spoken answer можно прервать контролируемо;
- нет явных feedback loops;
- audio policy остаётся маленькой и понятной.

## Phase 5. Language and spoken content quality

### Цель

Довести spoken output до состояния, где он почти всегда звучит как ассистент, а не как адаптированный CLI output.

### Подзадачи

1. Spoken summarization для длинных open-domain answers.
   Нужно отдельно решить:
   - что говорить полностью;
   - что summarise;
   - когда предлагать `say more` вместо чтения длинного полотна.

2. TTS locale policy.
   Нужна явная иерархия:
   - explicit user locale;
   - locale hint от voice capture;
   - language of spoken message;
   - fallback.

3. Spoken source references.
   Довести до стабильного формата:
   - file labels;
   - host names;
   - no raw path dumps;
   - no evidence walls.

4. Финализировать refusal / warning templates.
   Уже много сделано, но нужен финальный consistency pass:
   - безопасные отказы;
   - medical/legal/financial warnings;
   - unsupported/insufficient-context failures.

5. Русский deterministic spoken surface.
   Добрать места, где ещё возможен English fallback в `ru` voice path.

### Acceptance

- spoken output короткий и полезный на слух;
- `ru/en` voice surface выглядит целостным;
- длинные ответы не утомляют;
- источники произносятся понятно.

## Phase 6. Release-grade rollout

### Цель

Сделать voice mode не просто приятным, а управляемым с точки зрения запуска и отката.

### Подзадачи

1. Регулярный voice eval workflow.
   Нужно решить:
   - какой набор voice eval cases обязательный;
   - как часто он гоняется;
   - что считается regression.

2. Stabilize operator workflow.
   Довести до стабильного режима:
   - `voice telemetry`;
   - `voice telemetry write`;
   - `voice readiness`;
   - `voice readiness write`;
   - `voice gate`.

3. Default-on criterion.
   Нужен явный список условий, при которых bounded mode можно расширять без флага.

4. Rollout levels.
   Зафиксировать уровни:
   - single-turn default;
   - bounded conversation opt-in;
   - future advanced conversation.

5. Rollback protocol.
   Должно быть ясно:
   - что выключать первым;
   - как быстро вернуться к safe mode;
   - какие симптомы считаются поводом для rollback.

### Acceptance

- rollout делается по уровням риска;
- оператор видит реальное качество voice mode;
- advanced mode не включается "на ощущениях".

## Что делать не надо

Чтобы не потерять темп и не развалить текущую архитектуру, в ближайших фазах не нужно:

- переписывать весь CLI вокруг voice mode;
- делать full continuous assistant loop по умолчанию;
- раздувать audio subsystem до сложного framework раньше live validation;
- переводить весь app в speech-first UX;
- ломать text-first core ради voice convenience.

## Рекомендуемый порядок выполнения

1. Live verification и artifacts.
2. Фикс только реальных live blockers.
3. Bounded conversation UX polish.
4. Audio excellence.
5. Language/content polish.
6. Release-grade rollout policy.

Именно этот порядок даёт лучший шанс быстро получить нужный результат без лишнего рефактора.

## Definition of Done

Можно считать, что нужный результат достигнут, когда одновременно выполняется следующее:

- `docs/manual_voice_verification.md` пройден вживую без blocker'ов;
- есть свежие telemetry/readiness artifacts;
- `voice gate` не блокирует текущий bounded mode;
- 2-3 turn voice conversation под флагом ощущается естественно;
- spoken output не читает логи, пути и debug noise;
- long-answer path имеет внятную стратегию: filler, interruptibility, follow-up;
- есть понятный rollout и rollback story;
- нет необходимости делать большой внеплановый рефактор, чтобы безопасно продолжать развитие voice mode.

## Самый короткий practical path

Если нужен максимально прагматичный путь без лишнего scope creep, то он такой:

1. Пройти live manual voice smoke.
2. Исправить только live blockers.
3. Добить earcons и remaining follow-up UX polish.
4. Сделать controlled TTS interruption.
5. Финализировать spoken summarization и TTS locale policy.
6. Зафиксировать rollout criteria и rollback strategy.

Это и есть самый прямой маршрут от текущего состояния к "достаточно хорошему и управляемому" voice mode.
