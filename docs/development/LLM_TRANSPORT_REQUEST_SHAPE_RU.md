# LLM transport: форма запроса и ошибки

[Transport owner](../../LocalGenerator/infini_local/pipelines/llm_transport.py), [GUI presets](../../LocalGenerator/infini_local/desktop/settings_schema.py), [setup/restart](../user/SETTINGS_RU.md). Локальный serializer и прежний live probe — не универсальные capabilities provider/model.

## Настройки

| Поле | Текущая семантика |
|---|---|
| `INFINI_LLM_RESPONSE_FORMAT=json_object` | JSON hint; shape в prompt, local validator/compiler/wire gate обязательны |
| `…=json_schema` | Provider schema; endpoint/model имеет собственный complexity budget |
| `…=auto` | **Remote → json_object, local → json_schema**, если stage не задал `auto_preference`; explicit choice сохраняется |
| `…=off` | Нет provider format, но local validation остаётся |
| `INFINI_LLM_API_MODE=chat_completions` | Stateless `/chat/completions` |
| `…=auto`/`responses` | Пробует `/responses`, допускает same-profile Chat compatibility downgrade |

Remote presets: `json_object` + `chat_completions`; local сохраняют schema. Это starting point, не availability guarantee. Codex — отдельный subscription Responses adapter: [auth/limits](../user/CODEX_IMAGE_OAUTH_RU.md#качество-размер-и-расход).

`json_object` не semantic fallback: `requiredJsonShape`, `runtimeProgramInvariants` и полный capability catalog остаются в prompt; optional advisory report не является validation verdict; invalid response → условный Repair/RED. Без constrained grammar синтаксического брака **может стать больше**, но provider schema не gameplay authority.

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

У logical call один абсолютный `time.monotonic()` deadline: rate wait, открытие/headers, body/error reads, negotiation, retry/backoff и разрешённый failover расходуют общий остаток, а не получают новый timeout. Непрерывная выдача малых порций не продлевает budget. Общий [HTTP I/O owner](../../LocalGenerator/infini_local/core/http_io.py) не выбирает provider, не делает retries и не заменяет отдельный Codex/SSE adapter. Отмена блокирующего системного DNS resolver не реализована.

[OpenRouter pin](../user/OPENROUTER_ROUTING_RU.md#что-именно-запрещает-этот-выбор) запрещает другой профиль/legacy fallback, но сохраняется при same-upstream envelope/API downgrade. Основной Codex не уходит на paid API. Unpinned pool/lease/cooldown и legacy резерв — отдельная явно настроенная policy; пустой `INFINI_LLM_FALLBACK_MODEL` выключает резерв.

## Диагностика

`request_shape_rejection_diagnosis`: только релевантный Chat schema rejection, без изменения payload/retry. До успешного recovery `knownWorkingResponseFormat/ApiMode` пусты; `candidateResponseFormat/ApiMode` — предложение, не доказательство работоспособности. Повтор делает caller; `LLM schema negotiation accepted` фиксирует состоявшийся usable recovery.

| Где | Что смотреть |
|---|---|
| `cache/events.ndjson` | `LLM provider rejected the configured request shape`: configured/sent format, API mode, schemaChars, `knownWorkingResponseFormat/ApiMode`, bounded providerBody |
| `pipeline_trace.ndjson`, craft error | Stage `requestShapeRejection` / hint |
| `LLM usage`/debug | Retry count/causes, [cache counters](LLM_PROMPT_CACHE_AND_LATENCY_RU.md#наблюдаемость) |

`knownWorking*` относится только к наблюдённому recovery, **не remote billing proof**. Generic 400 не доказывает, что модель не получила задание или что расход равен нулю. Проверяй status/body/model/baseUrl.

События `LLM physical attempt`, `LLM transport wait` и logical-call finish/failure связаны через `logicalCallId`, `stage`, `leaseId`. `physicalAttemptCount` считает generation POST network-open attempts, не accepted/billed requests; discovery GET и auth/control-plane в этот счёт не входят. Сохраняется до 16 attempt/wait events, с отдельным dropped count; диагностика не меняет retry policy. Несостоявшаяся из-за rate wait отправка имеет ноль attempts.

Requested и effective API/format/reasoning различаются: effective — последняя попытка wire, не подтверждение поддержки provider. `openMs` включает connect/TLS/status/headers, `readMs` — чтение; `connectMs=null`, отдельного измерителя connection нет. Supplement не содержит raw headers/body/prompts; legacy providerBody diagnostics — отдельное поле. При wrapped failure существующий [failure snapshot owner](../../LocalGenerator/infini_local/storage/failure_state.py) извлекает ближайший пригодный supplement из явной `__cause__` chain и сохраняет `transportDebug` в том же snapshot/summary. Обход ограничен и защищён от cycles; fixed field/type/size projection не копирует provider extras или неизвестные объекты. Если supplement отсутствует, прежняя форма snapshot сохраняется.

### Codex HTTP/SSE: evidence и формат артефактов

Text/image generation adapters подключают существующий trace writer к общему HTTP/SSE owner. В `pipeline_trace.ndjson` записи `kind=codex_transport` связаны через `transportCallId` и номер физической попытки; текстовый caller дополнительно передаёт `logicalCallId`, `stage`, `leaseId`. Image lifecycle передаёт реальные `assetId`, backend `attemptId`, semantic `attempt`, audit `role`; каждый variant добавляет свой номер, а success event сохраняет callback-observed `transportCallId`. Identical prompts и усечённые filenames не используются как identity. Direct backend без lifecycle не выдумывает отсутствующий logical asset/role. Сохраняются effective serialized request, фактический POST start после последней deadline admission, HTTP status, open/read/elapsed, ошибка, retry/terminal outcome. `physicalAttemptCount` считает наблюдённые generation network-open attempts, включая ноль до отправки. Если sender обойдён и native owner не наблюдался, остаются `null`/`codex_owner_unobserved`; auth/discovery не включаются.

Для SSE отдельно записываются исходные `data` payloads до parser projection (не буквальные HTTP/SSE framing bytes), arrival time, event/delta counters, first/last text delta и authentic terminal envelope с provider usage. `observedAt` — sender wall clock, `arrivalMs` — monotonic от начала попытки; `persistedAt`/legacy top-level `ts` — время фоновой записи. До attempt_end/call_end статус явно transient (`terminal=false,outcome=in_progress`), не предварительная ошибка. Parser-reconstructed output не выдаётся за исходный terminal; malformed events, EOF без completed, unframed tail и позднее чтение остаются отдельными наблюдениями. Это не токенизация и не измерение чистого model compute.

Полные полученные UTF-8 payload bytes сохраняются после redaction в content-addressed `cache/transport_artifacts/<sha256>.txt`; NDJSON хранит receipt либо явный refusal. Один safe SSE attempt публикует один immutable файл вместо файла/fsync на delta. Fresh receipt `infini.transport-ranges.v1`: path/sha256/bytes проверяют общий файл, offset/length/rangeSha256 — exact event. Разделитель payloads — LF, не reconstructed SSE framing. Reader `trace_tools.read_transport_artifact` проверяет обе границы и прежний whole-event формат без переписывания архивов. Количество NDJSON rows не сокращается, latency-ускорение этим не заявляется. Request-local FIFO snapshot передаётся фоновому writer: дисковые locks/fsync не выполняются внутри HTTP/SSE deadline. Clean process exit пытается дренировать очередь до 2 секунд; принудительное завершение процесса или постоянно недоступное хранилище может оставить queued diagnostics несохранёнными. Атомарная запись и sanitization не меняют чистый provider content/PNG/parser. Request headers, credentials, refresh/session store не сохраняются. Общий `INFINI_TRACE_PROMPTS=false` отключает эти записи; persistence failure не прерывает generation. Для HTTP error-body сохраняется прежняя bounded parser projection: oversized сообщение не становится новым caller error. Diagnostic worker отдельно дочитывает настоящий error stream только в исходном deadline; complete bytes либо полученный partial prefix записываются с явным `bodyComplete`/`bodyReadErrorType`, без задержки terminal/retry.

Raw SSE artifacts остаются в памяти фонового writer до `attempt_end` (общий предел pending batches: 8 MiB, 4096 events, 64 attempts; переполнение и `call_end` без attempt boundary дают явный refusal): перед публикацией проверяется собранный текст delta и terminal output parts, чтобы credential, разбитый между events/parts, нельзя было восстановить из файлов. При найденном credential или неразбираемых SSE данных весь raw SSE batch получает явный refusal; counters/timing/outcome сохраняются, clean events остаются byte-identical. `/trace_clear` инвалидирует queued/in-flight transport rows и pending SSE batches по epoch до очистки выбранных NDJSON, поэтому завершившийся старый вызов не восстанавливает очищенный журнал. Это очистка выбранных NDJSON, не удаление ранее сохранённых content-addressed artifacts. Generation не ждёт clear/commit lock.

Codex retry policy не меняется: 429 terminal; 503 и другие существующие transient statuses используют прежний bounded budget и общий deadline. Unterminated/escaped JSON literals и malformed escape fragments санитизируются без восстановления фиктивного JSON; clean complete bytes сохраняются. `IncompleteRead.partial` записывается отдельно как `reader_exception_partial_unclassified`, не достраивает entity-body и не даёт `bodyComplete=true`. Старые captures не дополняются новыми событиями: до подключения observer реальные physical attempts/waits неизвестны. Offline fixture-проверки находятся в [test_codex_transport_trace.py](../../LocalGenerator/tests/test_codex_transport_trace.py); они не доказывают новый live provider run.

Native Codex text request запрашивает `reasoning.summary="auto"` с прежним effort и `include=[]`. Это публичное summary, не расшифровка encrypted_content и не обещание полного CoT/объёма thinking. Authentic summary events сохраняются; attempt receipt сообщает reasoningSummaryEventCount/DeltaChars/Returned, включая final-only summary и честное отсутствие. В видимый authored JSON summary не подмешивается. Medium — effort, не минимальный reasoning-token budget; token IDs/logprobs этим не добавляются.

Pre-Author failure snapshot сохраняет полные безопасные itemA/itemB и вычисленный recipeKey через существующий generation_debug/redaction owner; candidate поздних стадий остаётся прежним. Ни provider headers, ни посторонний config туда не копируются.

## Provider complexity boundary

Один endpoint/model может отвергнуть составную schema, даже если отдельные constraints проходят. Нет универсального порога chars/числа variants и нельзя ослаблять local validation ради provider acceptance. [Google structured-output limitations](https://ai.google.dev/gemini-api/docs/structured-output) описывают provider constraints; offline serializer не доказывает current quota, availability или billing. Network/concurrency/rate errors не лечатся заменой gameplay contract.

## Проверка

[Request contracts](../../LocalGenerator/tests/test_provider_request_contract.py), [transport](../../LocalGenerator/tests/test_provider_transport_contract.py), [GUI](../../LocalGenerator/tests/test_settings_gui_contract.py): envelopes/diagnosis/one-time downgrade/profile memory/pin/failure boundaries. [Offline QA](../user/START_RU.md); [Live20](../../toolbox/README.md) — отдельно разрешаемый запуск, не fixture-based billing/availability proof.
