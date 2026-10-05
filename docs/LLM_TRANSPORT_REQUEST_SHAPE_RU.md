# LLM transport: форма запроса и ошибки

[Transport owner](../LocalGenerator/infini_local/pipelines/llm_transport.py), [GUI presets](../LocalGenerator/infini_local/desktop/settings_schema.py), [setup/restart](../QUICK_START_RU.md#настройки). Локальный serializer и прежний live probe — не универсальные capabilities provider/model.

## Настройки

| Поле | Текущая семантика |
|---|---|
| `INFINI_LLM_RESPONSE_FORMAT=json_object` | JSON hint; shape в prompt, local validator/compiler/wire gate обязательны |
| `…=json_schema` | Provider schema; endpoint/model имеет собственный complexity budget |
| `…=auto` | **Remote → json_object, local → json_schema**, если stage не задал `auto_preference`; explicit choice сохраняется |
| `…=off` | Нет provider format, но local validation остаётся |
| `INFINI_LLM_API_MODE=chat_completions` | Stateless `/chat/completions` |
| `…=auto`/`responses` | Пробует `/responses`, допускает same-profile Chat compatibility downgrade |

Remote presets: `json_object` + `chat_completions`; local сохраняют schema. Это starting point, не availability guarantee. Codex — отдельный subscription Responses adapter: [auth/limits](CODEX_IMAGE_OAUTH_RU.md#модели-качество-и-расход).

`json_object` не semantic fallback: `requiredJsonShape`, `runtimeProgramInvariants`, `selfCheck` остаются в prompt; invalid response → условный Repair/RED. Без constrained grammar синтаксического брака **может стать больше**, но provider schema не gameplay authority.

## Retries и границы ошибок

| Событие | Policy |
|---|---|
| Chat 400 + sent `json_schema` + явное schema/format rejection | Один same-stage повтор с `json_object`; только envelope меняется, messages/model/sampling/reasoning сохранены |
| Повторный 400 с `json_object` | Второго schema downgrade нет; ошибка идёт higher-level policy |
| Responses 400/404/405/415/422/501 | Same-profile stateless Chat при распознанной API incompatibility; content/context/model errors не дают downgrade. Для 400/422 нужны явные признаки неподдержанного API/параметра; не network/timeout downgrade |
| 401/402/403/429 | Auth/billing/quota/rate-limit, не schema cure; 429 также transport-class с provider cooldown |
| 408/409/425/429/500/502/503/504, network/timeout | Bounded transport retry и/или настроенный pool/fallback только в оставшемся logical deadline |
| HTTP redirect 301/302/303/307/308 | Отказ с исходным 3xx; нет follow даже на тот же origin. Headers/body не пересылаются на новый адрес |

Один 400 или generic `INVALID_ARGUMENT` **не доказывает schema rejection**. Отрицательная capability запоминается только после релевантного отказа и успешного same-request recovery с пригодным JSON; неудачный/malformed recovery cache не отравляет. Scope: provider/base URL, фактически выбранная model, API и exact case-sensitive OpenRouter pin; complexity/invalid-schema evidence дополнительно привязана к digest конкретной schema envelope. Responses learning также требует успешного Chat recovery. Cache действует на процесс, не меняет `config.env`.

Debug: `strictSchemaDowngraded=true`, cause `json_schema_to_json_object_fallback`; API downgrade cause `responses_to_chat_fallback`. Применение уже известного cache evidence не выдумывает новый retry. Content/length retry и profile failover отдельно учитываются в `transportRetryCount/Causes`: один envelope retry ≠ один суммарный HTTP.

У logical call один абсолютный `time.monotonic()` deadline: rate wait, открытие/headers, body/error reads, negotiation, retry/backoff и разрешённый failover расходуют общий остаток, а не получают новый timeout. Непрерывная выдача малых порций не продлевает budget. Общий [HTTP I/O owner](../LocalGenerator/infini_local/core/http_io.py) не выбирает provider, не делает retries и не заменяет отдельный Codex/SSE adapter. Отмена блокирующего системного DNS resolver не реализована.

[OpenRouter pin](OPENROUTER_ROUTING_RU.md#строгая-семантика) запрещает другой профиль/legacy fallback, но сохраняется при same-upstream envelope/API downgrade. Основной Codex не уходит на paid API. Unpinned pool/lease/cooldown и legacy резерв — отдельная явно настроенная policy; пустой `INFINI_LLM_FALLBACK_MODEL` выключает резерв.

## Диагностика

`request_shape_rejection_diagnosis`: только релевантный Chat schema rejection, без изменения payload/retry. До успешного recovery `knownWorkingResponseFormat/ApiMode` пусты; `candidateResponseFormat/ApiMode` — предложение, не доказательство работоспособности. Повтор делает caller; `LLM schema negotiation accepted` фиксирует состоявшийся usable recovery.

| Где | Что смотреть |
|---|---|
| `cache/events.ndjson` | `LLM provider rejected the configured request shape`: configured/sent format, API mode, schemaChars, `knownWorkingResponseFormat/ApiMode`, bounded providerBody |
| `pipeline_trace.ndjson`, craft error | Stage `requestShapeRejection` / hint |
| `LLM usage`/debug | Retry count/causes, [cache counters](LLM_PROMPT_CACHE_AND_LATENCY_RU.md#наблюдаемость) |

`knownWorking*` относится только к наблюдённому recovery, **не remote billing proof**. Generic 400 не доказывает, что модель не получила задание или что расход равен нулю. Проверяй status/body/model/baseUrl.

События `LLM physical attempt`, `LLM transport wait` и logical-call finish/failure связаны через `logicalCallId`, `stage`, `leaseId`. `physicalAttemptCount` считает generation POST network-open attempts, не accepted/billed requests; discovery GET и auth/control-plane в этот счёт не входят. Сохраняется до 16 attempt/wait events, с отдельным dropped count; диагностика не меняет retry policy. Несостоявшаяся из-за rate wait отправка имеет ноль attempts.

Requested и effective API/format/reasoning различаются: effective — последняя попытка wire, не подтверждение поддержки provider. `openMs` включает connect/TLS/status/headers, `readMs` — чтение; `connectMs=null`, отдельного измерителя connection нет. Supplement не содержит raw headers/body/prompts; legacy providerBody diagnostics — отдельное поле. При wrapped failure существующий [failure snapshot owner](../LocalGenerator/infini_local/storage/failure_state.py) извлекает ближайший пригодный supplement из явной `__cause__` chain и сохраняет `transportDebug` в том же snapshot/summary. Обход ограничен и защищён от cycles; fixed field/type/size projection не копирует provider extras или неизвестные объекты. Если supplement отсутствует, прежняя форма snapshot сохраняется. Для native Codex `physicalAttemptCount=null` и scope=`codex_owner_unobserved`, а не выдуманные generic POST. Эти изменения включены в поставку 0.4.247; в старом опубликованном архиве 0.4.246 их нет.

## Исторический Gemini reproducer

Прежний конкретный Gemini Chat endpoint отклонял полную Author schema (400), Responses дал 404: **не запрет strict output всех нынешних Gemini**. Schema тогда: 85579 chars, 4043 nodes, depth 16, 519 constraints; calls `oneOf` 51 вариантов, maxItems 48.

| Изоляция | Прежний ответ |
|---|---|
| name/category/concept; entities; одиночный capability; oneOf 2 real / 32 synthetic objects | 200 |
| Полный runtimeProgram; calls 51 вариантов | 400 |
| Real variant maxItems 8 / 48 | 200 / 400 |
| String items maxItems 48 | 200 |

`pattern`, `const`, array bounds, `oneOf`, `$schema`, `x-infini-*` отдельно проходили; снятие pattern/min/max/всех constraints полную форму не исправляло. Complexity комбинации, не правило «до N chars»: [Google limitations](https://ai.google.dev/gemini-api/docs/structured-output).

Другой старый Live20 (json_object/Chat/parallel=3): три ~94k-char 400 при activeHttp=3 рядом с Connection refused/RemoteDisconnected. Concurrency — гипотеза, не доказанная причина; format не лечит network/rate-limit. Прежние free-tier 15 RPM — та конфигурация, не общий лимит новых моделей/аккаунтов.

## Проверка

[Request contracts](../LocalGenerator/tests/test_provider_request_contract.py), [transport](../LocalGenerator/tests/test_provider_transport_contract.py), [GUI](../LocalGenerator/tests/test_settings_gui_contract.py): envelopes/diagnosis/one-time downgrade/profile memory/pin/failure boundaries. [Offline QA](../LocalGenerator/QUICK_START_RU.md); [Live20](../toolbox/README.md) — отдельно разрешаемый запуск, не fixture-based billing/availability proof.
