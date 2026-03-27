# QA GPT Checklist

Статус на `2026-03-27`.

## Цель

Этот документ фиксирует, что осталось сделать до состояния, которое можно честно назвать `qa_gpt` release-ready.

Под `qa_gpt` здесь имеется в виду:
- GPT-backed `question` mode технически подтверждён
- есть machine-readable release evidence
- выбран beta candidate
- можно обсуждать `beta_question_default` без фиктивных sign-off

Этот документ не означает, что GPT уже можно переключать в product default.

## Текущий статус

- rollout stage: `alpha_opt_in`
- product default: `deterministic`
- recommended beta candidate: `llm_env_strict`
- technical env-backed evidence: есть и снова fresh для `llm_env_strict`
- manual beta checklist evidence: есть
- final release evidence: ещё нет

Что уже закрыто:
- open-domain / grounded / safety / eval / rollout gate слой реализован
- live smoke, comparative gate и repeated stability уже были реально прогнаны; на `2026-03-27` `llm_env_strict` снова имеет fresh green smoke + stability `3/3`
- offline release-decision helpers уже есть:
  - `python3 -m qa.manual_beta_checklist`
  - `python3 -m qa.beta_release_review`
  - `python3 -m qa.beta_readiness`
  - те же read-only summaries теперь доступны и внутри `python3 cli.py` через `qa checklist`, `qa release review`, `qa readiness`
- helpers уже зажаты от фейковых sign-off:
  - final artifacts требуют explicit candidate choice
  - stale / drifted artifacts честно блокируются
- real scripted manual beta pass уже записан в `tmp/qa/manual_beta_checklist.json` (`7/7`, fresh)

Главный остаток сейчас не инженерный, а операционный.

## Что Осталось

### 1. Подтвердить, что technical evidence всё ещё актуален

Перед release sign-off нужно проверить, что `qa beta` всё ещё показывает:
- `qa beta technical precheck: ready`
- `qa beta recommended candidate: llm_env_strict`
- `candidate llm_env_strict: ... stability=green(3/3) ...`
- `qa beta manual checklist artifact: ... complete(7/7) ...`
- `qa beta release review artifact: ... missing`

Команда:

```bash
JARVIS_QA_BACKEND=llm \
JARVIS_QA_LLM_ENABLED=true \
JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED=true \
python3 -c "import cli; cli._print_qa_beta()"
```

Если technical artifacts уже stale/missing/red, это не release-review step, а возврат к rollout verification:
- rerun live smoke
- rerun gate
- rerun stability

До этого manual/release sign-off записывать нельзя.

### 2. Реально пройти manual beta checklist

Статус на `2026-03-27`: `done`.

Scripted manual scenarios для question mode уже реально пройдены и записаны.

Записанный artifact:

```text
tmp/qa/manual_beta_checklist.json
```

Команда, которой это уже было честно сделано:

```bash
python3 -m qa.manual_beta_checklist --all-passed --write-artifact
```

Что это означает по факту:
- manual scenarios реально проверены
- checklist не записывается “на доверии”
- helper `python3 -m qa.manual_beta_checklist` теперь сам печатает pending scenario guide с sample prompts / env hints / expected outcomes, так что scripted pass можно собрать из CLI без догадок

### 3. Реально записать beta release review

Нужно реально подтвердить:
- latency review
- cost review
- operator sign-off
- product approval

После реального подтверждения записать artifact:

```bash
python3 -m qa.beta_release_review \
  --candidate-profile llm_env_strict \
  --latency-reviewed \
  --cost-reviewed \
  --operator-signoff \
  --product-approval \
  --write-artifact
```

Что это означает по факту:
- release-review сделан именно для `llm_env_strict`
- review привязан к текущему manual-checklist snapshot
- это уже не transient state, а recorded evidence
- helper `python3 -m qa.beta_release_review` теперь тоже показывает checklist guide command / verification doc / pending scenario guide, если релиз-review упирается в незакрытый manual checklist

Ожидаемый artifact:

```text
tmp/qa/beta_release_review.json
```

### 4. Записать финальный beta readiness artifact

Только после двух предыдущих шагов:

```bash
python3 -m qa.beta_readiness --candidate-profile llm_env_strict --write-artifact
```

Что это означает:
- выбран beta candidate
- technical evidence, manual checklist и release review сведены в единый decision record

Ожидаемый artifact:

```text
tmp/qa/beta_readiness.json
```

### 5. Принять решение по `beta_question_default`

После появления корректного `beta_readiness.json` нужно отдельно принять продуктовое решение:
- готов ли `beta_question_default`
- меняется ли rollout stage
- когда и на каких условиях обсуждается default switch

Важно:
- наличие `beta_readiness.json` само по себе не переключает default
- deterministic path остаётся default, пока это решение не принято явно

## Definition Of Done

`qa_gpt` можно считать release-ready только если одновременно выполнено всё ниже:

- [ ] `qa beta` показывает актуальный technical-ready signal
- [x] recommended candidate остаётся `llm_env_strict`
- [x] `tmp/qa/manual_beta_checklist.json` существует и fresh
- [ ] `tmp/qa/beta_release_review.json` существует и fresh
- [ ] `tmp/qa/beta_readiness.json` существует
- [ ] `qa beta` не считает recorded artifacts stale/inconsistent
- [ ] есть реальный operator sign-off
- [ ] есть реальный product approval для `beta_question_default`

## Что Не Делать

- Не записывать `manual_beta_checklist.json`, если manual pass реально не делался.
- Не записывать `beta_release_review.json`, если latency/cost/sign-off/product approval реально не подтверждены.
- Не записывать `beta_readiness.json`, если supporting artifacts missing/stale.
- Не считать наличие старого green artifact достаточным без проверки через `qa beta`.
- Не переключать product default только потому, что GPT path технически зелёный.

## Быстрый Порядок Действий

1. Проверить текущее состояние:

```bash
JARVIS_QA_BACKEND=llm \
JARVIS_QA_LLM_ENABLED=true \
JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED=true \
python3 -c "import cli; cli._print_qa_beta()"
```

2. Если technical evidence всё ещё green, пройти manual checklist:

```bash
python3 -m qa.manual_beta_checklist --all-passed --write-artifact
```

Статус: уже сделано на `2026-03-27`, повторять не нужно, пока artifact остаётся fresh.

3. После реального review записать release review:

```bash
python3 -m qa.beta_release_review \
  --candidate-profile llm_env_strict \
  --latency-reviewed \
  --cost-reviewed \
  --operator-signoff \
  --product-approval \
  --write-artifact
```

4. Затем записать финальный readiness artifact:

```bash
python3 -m qa.beta_readiness --candidate-profile llm_env_strict --write-artifact
```

5. После этого отдельно принять решение по `beta_question_default`.

## Итог В Одной Фразе

До полноценного `qa_gpt` осталось не дописывать систему, а честно закрыть recorded release review / beta readiness evidence и явное beta approval для `llm_env_strict`.
