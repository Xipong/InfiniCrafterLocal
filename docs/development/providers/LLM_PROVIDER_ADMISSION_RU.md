# Provider-aware admission для LLM HTTP

Canonical owners: FIFO quota/rate admission — `LocalGenerator/infini_local/pipelines/llm_admission.py`; profile/lease/cooldown — `llm_profiles.py`; logical deadline, physical attempts и HTTP — `llm_transport.py` в той же папке. Admission получает attempt diagnostics от executor явно.
Это transport policy, не gameplay normalization и не изменение Author/parent packets.

## Что известно о quota contract

Nous plan sharing покрывает только eligible inference; сохраняются ChatGPT plan/app
limits, unlimited allowance не обещается. Ошибка после выбора sharing не вызывает
автоматический retry за Nous credits.[1] Canonical Nous URL сам по себе **не доказывает**
включённый sharing конкретного аккаунта: этот patch не читает auth/config, не выбирает
billing route и не проверяет подписку. Политика относится к известному transport route
независимо от того, какой разрешённый billing mode выбрал сервер.

В публичном Codex contract allowance зависит от model, task complexity, context,
reasoning и caching; prompt length не является надёжной оценкой. Для local/cloud
messages объявлены five-hour windows и возможные weekly limits, не универсальные
16k input TPM.[4] Native `openai_codex` уже использует отдельный
`codex_text_backend.generate_chat -> codex_auth.post_sse` owner: он **не проходит**
через generic `http_json` limiter. Его bounded retries/deadline и terminal 429
остаются без изменений; generic metadata не приписывается native SSE.

OpenAI Platform rate limits относятся к organization/project и model; некоторые
model families делят budget. Документированы response headers `x-ratelimit-*`
для requests, tokens и project-tokens, включая remaining и относительный reset.[2]
Эти сведения не устанавливают значения лимитов для Nous gateway.

Platform caching не уменьшает TPM: cached prompts продолжают учитываться в
rate limits.[3] Codex credit accounting различает input, cached input и output
по model-specific rates.[4] Ни credit discount, ни положительный `cached_tokens`
не дают универсального права вычесть cache hits из локальной rate reservation.
Этот patch **не списывает и не возвращает** токены по usage/cache counters: нет
подтверждённого Nous contract, связывающего эти counters с minute quota.

## Production policy

| Route | Admission |
|---|---|
| Точные HTTPS `inference-api.nousresearch.com/v1/chat/completions` и `/v1/responses`, model начинается с literal `openai/`; без port/userinfo/query/fragment | `nous_openai_feedback`: прежний local 5.1s pacing, FIFO, provider feedback; **без** char/4 token window |
| Остальные remote routes, включая похожие hostnames, другие model families, OpenAI Platform и generic попытку вызвать native Codex URL | `unknown_conservative`: прежние capped char/4, 16k/60s и model pacing; это **локальная предосторожность**, не заявленный provider limit |
| localhost / 127.0.0.1 / ::1 | `local_exempt`: без remote admission state |
| Native Codex subscription | Отдельный существующий SSE owner; generic policy не применяется |

State сохраняет прежний scope endpoint authority + model и общий process-wide lock.
Это не точная модель account-wide/shared-model quotas и не межпроцессный limiter.
Request shape, parent cards, max_tokens, reasoning, API negotiation, profile lease
и configured provider pin не меняются. 5.1s сохранено как local safety pacing,
не как выдуманные 12 RPM провайдера.

На каждом response, в том числе HTTP error, из реальных headers выбираются только:

- `x-ratelimit-{limit,remaining,reset}-{requests,tokens,project-tokens}`;
- `retry-after`.

Diagnostic `rateLimitHeaders` содержит только проверенные числовые значения;
reset/Retry-After представлены секундами, **не** raw strings. Counter: nonnegative
integer до 12 цифр. Reset: numeric seconds или duration с `ms/s/m/h/d`, до года.
Malformed, NaN/Infinity, negative, oversized и duplicate values не принимаются.
Cookies, account IDs, Authorization, request IDs и прочие headers не копируются.
`Retry-After` поддерживает delay и timezone-qualified HTTP-date, который переводится
в относительный delay; HTTP standard допускает обе формы.[5]

Explicit `remaining == 0` + valid reset устанавливает monotonic `quotaUntil`;
следующий oldest waiter не отправляется раньше reset (`provider_quota`). Positive
remaining сохраняется как evidence, но не считается точной стоимостью следующего
запроса, не отменяет уже наблюдавшийся cooldown и не снимает unknown local policy.
Одни `limit`, `reset`, `Retry-After` на успешном response без exhaustion не задают
новую квоту. 429 сохраняет `blockedUntil = max(existing, now + max(60s,
Retry-After, legacy model pacing))` (`provider_cooldown`). Default 60s — existing
safe recovery policy, не доказанный window подписки. Feedback берётся сразу после
headers, до body read: malformed/timeout body не теряет уже полученный quota signal.

FIFO position, cancellation cleanup, независимость keys и logical deadline сохранены:
ожидание расходует тот же бюджет; при exhaustion deadline нет reservation/send.
Diagnostics добавляют `rateAdmissionPolicy` к physical attempt / transport wait.
Selected safe headers появляются на physical attempts, включая failures.

## Live диагностика craft и отказов

`/health.generationActivity` сохраняет `active`, `waiting`, `accepting` и добавляет
bounded `requests` (до 32 наблюдаемых admitted requests) и `requestsOmitted`.
Owner — `services/combine_endpoint.py`: тот же admission/finally, не новый job/queue.
Каждая detached строка содержит только `requestId` (random UUID hex, не recipe/world/hash),
`profileId` (`llm_1..3` или null), `active`, `stage`, `startedMonotonicSeconds`,
`elapsedSeconds`, `stageElapsedSeconds`, `waitReason`, `networkStarted`.
Elapsed — monotonic, не wall-clock и не прогноз remaining time. `stage` меняется на
реальном `combine_pipeline.step` enter и очищается на leave; между стадиями — null,
до первой стадии — `00_prepare`. Процент завершения отсутствует: скорость/ETA неизвестны.

`waitReason`: `none`, `generation_slot`, `profile_slot`, `rate_queue`,
`provider_cooldown`, `provider_quota`, `token_window`, `pacing`, `retry_backoff`.
Transport обновляет его непосредственно у admission wait/network-start owner.
`networkStarted=false` означает unsent текущую HTTP попытку; true — entered physical
network owner; null — текущая transport boundary не наблюдается (включая native Codex
SSE). Это не cumulative send count и не доказательство ответа provider.
Logging OFF не отключает live snapshot. В нём нет parents/world/prompt/body/URL/auth.
При exit/refusal/error удаляется request row, releases acquired permits и resets context.
Cache-only/cache-hit не получают generation admission и не запускают inference.

Existing `lastFailure.transportDebug` переносит finite `failureCategory`, bounded
`httpStatus`, allowlisted `providerErrorCode`/`providerErrorParam`, `networkStarted`.
Unknown provider strings не копируются. Supplement проходит existing bounded explicit
cause traversal и persisted summary projection; отдельного failure store нет.
HTTP 404 без model-specific code не означает неизвестную модель. Model/auth/profile/
endpoint/quota failures возвращают non-retryable 424 с конкретным действием; provider
rate limit — retryable 424 с советом ждать. Logical-call deadline — 504 `llm_timeout`,
unsent local admission exhaustion — 504 `llm_admission_timeout`; это не свидетельство
provider outage. Outgoing request rejection остаётся non-retryable 424, authored JSON/
validation rejection — retryable 422. HTTP request responses используют только
exception-owned snapshot, никогда process-wide latest failure чужой concurrent lane.

World recipe I/O denial возвращает 500 `cache_lookup_failed` для cache-only и fresh
request; active bytes остаются на месте и повторное чтение может восстановиться.
Missing file — обычный miss; quarantine допустим только после observed invalid JSON/
metadata/domain checks под существующим canonical path lock. Debug readers сохраняют
best-effort режим. Regression owner: `test_provider_activity_contract.py` — real
`/combine`, source-built Author transport, loopback providers, stage/thread gates,
semaphore/rate queues, persisted supplements, privacy, cleanup и sibling isolation.

## Наблюдённая причина задержек — не новый speed benchmark

Existing artifact: `pr-review-worktrees/craft-stage-prefix-cache/artifacts/`
`craft-stage-cache-20261012/live/logical_llm.ndjson` в родительском project workspace.
10 response rows, 10 physical POSTs, все HTTP 200; 8 attempts имеют
`rateWaitReason=token_window`. Их сумма admission waits — **300.086344s** из
**573.544s** logical-call time (**52.321%**). Старый transport не сохранял quota
headers, поэтому этот artifact не доказывает Nous TPM/RPM/reset. Он доказывает
задержку в нашем локальном token window.

Expected causal change: большой full Author/VFX wire больше не резервирует целиком
выдуманное 16k окно на известном Nous route. Если предыдущий POST был более 5.1s
назад и server feedback не требует cooldown, следующий POST не ждёт 60s из-за
размера wire. При настоящем exhaustion/reset/429 он продолжает ждать или заканчивает
logical deadline без отправки. Это **не измеренное ускорение**: network/model latency,
cache hit и stage repairs не обещаются прежними, новый live benchmark не запускался.

## Offline verification

`LocalGenerator/tests/test_provider_transport_contract.py` проходит real
`http_json` seam с управляемым monotonic clock, threaded Event gates и recording
sender; отдельно настоящий loopback urllib проверяет HTTP 200/429 headers через
`llm_chat_json` и logical diagnostics. Покрыты:

- known route large-wire admission за 5.1s вместо synthetic token window;
- неизменные wire и абсолютный deadline;
- success/429 exhausted requests/tokens/project-tokens, reset, no-send timeout;
- safe numeric header allowlist и malformed/duplicate inputs;
- HTTP-date Retry-After и monotonic cooldown extension;
- FIFO при quota/429 reset, existing cancellation и independent/local routes;
- unknown routes + cached usage сохраняют прежний conservative budget;
- native Codex boundary сохраняет собственный transport owner.

Verified scoped command: `PYTHONPATH=LocalGenerator python -m pytest`
для `test_provider_transport_contract.py`, `test_provider_request_contract.py`,
`test_transport_retry_redaction.py`, `test_codex_subscription_contract.py`,
`test_visual_vfx_prompt_prefix.py`, `test_stage_request_artifacts.py` и
`test_craft_instruction_segments.py`: **618 passed**. Отдельно ruff для двух
изменённых Python owners, `git diff --check`, project hygiene, delivery contract
и citation verification — PASS.

Полный suite и live acceptance выполняет parent после интеграции с отдельным schema
patch. Здесь никаких paid/inference/auth requests и никаких изменений пользовательских
настроек.

## Sources

[1] https://portal.nousresearch.com/help/chatgpt-plan-sharing
[2] https://platform.openai.com/docs/guides/rate-limits
[3] https://platform.openai.com/docs/guides/prompt-caching
[4] https://developers.openai.com/codex/pricing
[5] https://www.rfc-editor.org/rfc/rfc9110.html
