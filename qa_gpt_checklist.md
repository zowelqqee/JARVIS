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
- final release evidence: есть

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
- real `beta_release_review.json` уже записан для `llm_env_strict`
- real `beta_readiness.json` уже записан для `llm_env_strict`
- `qa beta` уже видит recorded readiness как fresh/consistent и больше не ведёт в фиктивный повторный write
- для реального opt-in использования теперь есть явный launcher `scripts/run_qa_question_beta.sh llm_env_strict`, так что question-mode beta можно запускать без ручного набора env и без fake default switch
- для preview будущего `beta_question_default` теперь есть отдельный launcher `scripts/run_qa_question_stage_preview.sh beta_question_default`, который включает stage-aware question default без реального rollout switch
- оба launcher'а теперь пинят свой `JARVIS_QA_*` env, так что inherited shell overrides больше не могут тихо изменить intended beta/preview path
- direct hybrid question routing тоже работает: при `JARVIS_QA_LLM_ENABLED=true` и `JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED=true` open-domain вопросы уже идут в model path даже без явного `JARVIS_QA_BACKEND=llm`, а grounded questions остаются локальными
- после refusal/capabilities hardening `llm_env_strict` снова имеет fresh green smoke + gate + repeated stability `3/3`
- обычный `python3 cli.py` теперь bootstrap'ит hybrid question defaults сам, так что open-domain вопрос в interactive CLI больше не требует ручных LLM env exports

Главный остаток сейчас не инженерный и уже не внутри stage 8: это отдельное rollout/product decision по `beta_question_default`.

## Что Осталось

### 1. Подтвердить, что recorded evidence всё ещё актуален

Перед любым отдельным rollout/default discussion нужно проверить, что `qa beta` всё ещё показывает:
- `qa beta technical precheck: ready`
- `qa beta recommended candidate: llm_env_strict`
- `candidate llm_env_strict: ... stability=green(3/3) ...`
- `qa beta manual checklist artifact: ... complete(7/7) ...`
- `qa beta release review artifact: ... complete(4/4) ...`
- `qa beta decision artifact: ... ready`
- `qa beta decision artifact consistent with latest evidence: yes`
- `qa beta decision: recorded as ready for explicit beta_question_default review; default remains unchanged`

Команда:

```bash
JARVIS_QA_BACKEND=llm \
JARVIS_QA_LLM_ENABLED=true \
JARVIS_QA_LLM_OPEN_DOMAIN_ENABLED=true \
python3 -c "import cli; cli._print_qa_beta()"
```

Если supporting artifacts уже stale/missing/red, это не product-decision step, а возврат к rollout verification:
- rerun live smoke
- rerun gate
- rerun stability

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

Статус на `2026-03-27`: `done`.

Были реально подтверждены:
- latency review
- cost review
- operator sign-off
- product approval

Записанный artifact:

```text
tmp/qa/beta_release_review.json
```

Что это означает по факту:
- release-review сделан именно для `llm_env_strict`
- review привязан к текущему manual-checklist snapshot
- это уже не transient state, а recorded evidence
- helper `python3 -m qa.beta_release_review` теперь тоже показывает checklist guide command / verification doc / pending scenario guide, если релиз-review упирается в незакрытый manual checklist

### 4. Записать финальный beta readiness artifact

Статус на `2026-03-27`: `done`.

Записанный artifact:

```text
tmp/qa/beta_readiness.json
```

Что это означает:
- выбран beta candidate
- technical evidence, manual checklist и release review сведены в единый decision record
- `qa beta` уже видит этот record как fresh/consistent
- `python3 -m qa.beta_readiness` теперь тоже не предлагает лишний rewrite, если current readiness artifact уже записан и остаётся актуальным

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

- [x] `qa beta` показывает актуальный technical-ready signal
- [x] recommended candidate остаётся `llm_env_strict`
- [x] `tmp/qa/manual_beta_checklist.json` существует и fresh
- [x] `tmp/qa/beta_release_review.json` существует и fresh
- [x] `tmp/qa/beta_readiness.json` существует
- [x] `qa beta` не считает recorded artifacts stale/inconsistent
- [x] есть реальный operator sign-off
- [x] есть реальный product approval для `beta_question_default`

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

2. Убедиться, что recorded artifacts всё ещё fresh/consistent:
   - `tmp/qa/manual_beta_checklist.json`
   - `tmp/qa/beta_release_review.json`
   - `tmp/qa/beta_readiness.json`

3. Если один из artifacts уже stale/red, сначала освежить evidence, а не спорить про rollout.

4. После этого отдельно принять решение по `beta_question_default`.

## Итог В Одной Фразе

До полноценного `qa_gpt` осталось не дописывать систему и уже не добивать stage-8 artifacts, а отдельно решить rollout/stage/default conversation поверх уже записанного beta-ready evidence для `llm_env_strict`.
