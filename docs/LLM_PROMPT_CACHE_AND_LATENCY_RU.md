# Prompt cache и задержка LLM

## Граница реализации

Cache — provider KV-prefix reuse, **не** рецепт/инструкции на диске. Author → Visual → VFX/условные scoped frozen Repairs и local validation не меняются.

Rules/catalog перед parents/IDs/visual kit/errors/exact schemas. Internal `_infini_prompt_cache={messageIndex,prefixChars}` маркирует static user boundary, не попадает в wire. Сам cache marker **не** разрешает повышать роль данных. Только initial Author builder дополнительно объявляет `staticInstructionPrefix=true`: его шесть статических полей — собственные инструкции/каталог приложения. Codex adapter передаёт их отдельным developer JSON, а `recipeKey/parents/balanceCorridor` — отдельным user JSON. Исходные logical messages сохранены; точные срезы текста меняют только разделительные скобки/запятую, обратная сборка восстанавливает исходный user text. Это намеренное изменение wire framing/роли статического контракта, не побайтовая идентичность прежнего HTTP body. Для прочих providers и необъявленных prefix границ прежний формат сохранён; full Author catalog не добавляется в Repair/следующие стадии ради hit.

Identity: SHA-256 предшествующих/system messages + exact static prefix + model/response format/effective reasoning; без recipe suffix/UUID/time/credentials/account IDs. Codex использует фактическую adapter projection; новая developer-граница дополнительно отделена versioned framing identity. Одинаковые bytes дают стабильный key между процессами; catalog/instructions/model/exact schema меняют его. Exact entity IDs не скрываются ради hit.

Marked Responses dossiers не используют/не сохраняют `previous_response_id`; unmarked generic calls сохраняют прежний continuation contract. Conversation history ≠ prompt cache.

## Поддержка провайдеров

| Реализованный маршрут | Adapter wire |
|---|---|
| `openai_compat`: точный `https://api.openai.com/v1`; `openrouter`: точный `https://openrouter.ai/api/v1` с `openai/gpt-…` | Numeric GPT 5.6+ → `prompt_cache_breakpoint`, `prompt_cache_options.mode=explicit`, стабильный `prompt_cache_key`; прежние распознанные GPT → только key |
| Codex subscription | Whitelisted key + согласованный `session-id`, `store=false`; explicit app-owned Author static developer prefix; без Platform breakpoint/retention/resource API, прогрева и дополнительных запросов |
| Direct Gemini compatible | Stable prefix для возможного implicit reuse; без OpenAI options/платного `cachedContents`/TTL lifecycle |
| Другие compatible/local | Прежние messages; `cache_prompt`, slot save/restore, durable KV-file здесь не реализованы |

Split: Chat `text`, Responses `input_text`; concatenation byte-equivalent, variable suffix не cache-write marker. Это serializer behavior, **не live acceptance** всех моделей. Provider хранит KV; restart сохраняет key, не lifetime cache. Eviction/endpoint/account/model change дают miss. Код не покупает/продлевает TTL; прежний upstream OpenAI 5.6+ default 30 минут не локальная гарантия. Threshold/TTL/pricing проверяй у provider.

## Наблюдаемость

`LLM usage`/debug: `cachedInputTokens` = сообщённый `cached_tokens`, иначе null; `cacheHit` = positive → true, explicit zero → false, missing → null; `cacheWriteTokens` = сообщённый `cache_write_tokens`, иначе null. Key/marker/readiness ≠ hit. Codex допускает nonnegative integer counters без metadata/credentials. Explicit write может быть платным. [Trace paths](../QUICK_START_RU.md#запуск-и-проверка).

## Локальная производительность

`json_object`/off не строят discarded provider schema eagerly; `json_schema` factory/local strict checks сохранены. Model/reasoning/budgets/stages не урезаются. Remote prefill/decode/Repairs/quota доминируют; миллисекунды Python не делают craft мгновенным.

### Исторические измерения

Сохранённые прежние данные, **не новый cold/warm test**:

| Fixture / метод | Результат |
|---|---|
| Workbench/Sword serializer | System 3457, user 88744, static user 87712 chars; кандидат 91169/92201, не cached tokens/hit. Короткие Visual/VFX могут не достичь threshold |
| `591f439` → lazy schema/marker; 5 warmups, 101 samples | Median builder json_object 4.921 → 2.236 мс, json_schema 5.010 → 6.100; wire без marker имеет прежний SHA-256, не network/game latency |
| `be5b1a9`, `workbench_blade`; 5 warmups/101 samples, отдельно 100 cProfile | Builder 2.20 мс, validator 14.77 мс. Hotspots JSON/catalog/prefix vs recursive strict_schema/type checks; cProfile overhead не latency, validator не урезался |

Live20 `typed-final-3834acd-flashlite31-all18k-medium-live20`: `logical_llm.ndjson`/`http_llm.ndjson`/`results.ndjson`/`harness_events.ndjson`; usage layers сверены как мультимножества, raw config/payload не опубликованы.

- 94 requests, 91 responses, 3 transport errors. Logical medians: Author 85.83 с (22), Repair 66.47 (19), Visual 60.54 (21), VFX 27.09 (20), VFX Repair 17.48 (9); не складываются в median craft, включают прерванные attempts.
- Full-case retries/waits median 263.10 с, range 188.23–583.07; terminal-attempt results.ms median 248.64 исключает прежние попытки. parallel=3: сумма durations не panel wall time.
- До patch 11/22 Author hits, 179331 cached tokens; 80/91 missing counters = unknown, не misses. Hit median 85.45 с; other stages unknown, не paired proof.
- 17 no-retry cases: results.ms − logical durations median 142 мс, max 219, median share 0.0604%; не pure CPU. Retry cases исключены.
- **Rejected**: 20 результатов, first-Author 2 < minimum 10, Repair нужен 18. Нельзя ускорять отключением validator/Repair.

End-to-end вывод требует разрешённого paired cold/warm run с usage; старые числа не текущий acceptance.

## Наблюдённая сессия 0.4.252, world1647275982

Frozen usage: 33 логических вызова, 1 positive hit / 32 explicit zero / 0 unknown; input474701/output41856/cached22016, reused fraction4.637867%. Author10:1/9, Repair5:0/5, Visual9:0/9, VFX9:0/9. Три world-recipe-cache hit отдельно обходили генерацию.

Единственный hit — точный повтор Author с input22250/cached22016 (98.948315% данного входа), не reuse между разными рецептами. Static prefix/system/reconstructed affinity identity стабильны внутри каждой стадии; recipe-key churn не обнаружен. Codex держит static+dynamic в одном input_text без explicit breakpoint. Конкретная backend причина misses неизвестна: сохранённые messages/offline projection не являются live body/headers. Запрошена gpt-6.1-sol; served identity, physical POST count/скрытые retries, reasoning/usage attribution неизвестны. Prompt→response40с→38с у повтора — не controlled prefill speedup; заметная remote latency осталась. Кэш не объявляется эффективно работающим для общего catalog по этим данным.

Receipt и повторяемый extractor лежат в task artifacts `current-world-contract-cache-followup/cache-lane`; audit использовал frozen0.4.252 ZIP/messages, не переписывал source/saves и не запускал provider.

## Проверка Codex cache controls и отвергнутые кандидаты

На текущем subscription route `gpt-6.1-sol` отдельно проверены root `prompt_cache_options` и content-level `prompt_cache_breakpoint`: оба получили HTTP400 «is not supported on this model». Platform guide описывает другое capability domain; добавлять эти флаги в Codex production нельзя. Прямые диагностические вызовы не создавали сохранённых игровых предметов.

Первый раунд: static catalog97901 chars + переменные recipe-shaped tails; исходная одна user message, два text blocks и два same-role user messages не показали улучшения hit в проверенных парах. Эти хвосты были **синтетическими**: короткие `{name,damage}` parents и повторённый 1300-символьный диагностический хвост, не полные игровые snapshots. На почти одинаковом коротком tail reuse21632 tokens наблюдался и у исходного adapter, поэтому positive split-hit не является доказательством исправления. Message framing менял объём ответа; тот split-кандидат откатан. Его отрицательный результат не исключает иной механизм записи cache boundary.

Исправлен только подтверждённый metadata loss: typed whitelist `usage.attribution.request_fields.instructions` сохраняет input/cached/write/output counters, `_usage_fields` выдаёт `instructionsInputTokens`, `instructionsCachedInputTokens`, `instructionsCacheWriteTokens`, `reasoningTokens`. Missing остаётся null, malformed/bool/negative не приводятся к числам. Opaque item IDs и произвольная provider metadata не сохраняются; они не доказывают binding к authored messages. Эти counters проходят существующий sanitized `LLM usage` event sink. Это улучшение наблюдаемости, не объявление KV cache исправленным.

## Углублённый раунд: отдельно проверить запись и поиск границы

С полными source-bound parent cards, одинаковым коротким ответом, одной моделью `gpt-6.1-sol` и стабильным affinity проведён отдельный контроль: full A — 0 cached, full B — 0, точный full A repeat — 23296; static-only seed — 0, затем static-message + реальные B/C — по **21632**. Это поддерживает объяснение, что общий текст существовал, но пригодная для поиска короткая граница ранее не записывалась. Внутренний backend алгоритм не наблюдался. `cache_write_tokens=0` встречался даже перед доказанным reuse: этот счётчик здесь нельзя читать как доказательство отсутствия физической записи.

Независимый no-prewarm контроль с новым key: полный валидный static JSON в initial developer block, полный dynamic JSON в user; A — 0, B/C — по **21632** cached из 22760/23103 входных токенов. Доля reuse изменённых хвостов — **94,33%**. Все три ответа — один контрольный JSON, по 12 output tokens; latency 3,737/4,190/3,678 с. Это доказательство reuse в диагностике, не ускорения полного craft. Production candidate включён только для initial Author; ни один parent/tooltip/recipe field не переносится в developer. Model/reasoning/schema не переключаются. Нативный рабочий путь Author проверен отдельно без диагностической подмены задания: три разных source-bound рецепта, три HTTP200, Author и compiled wire **3/3 valid без Repair**. Cached tokens: **0 → 21888 → 21888**, input23607/22941/23284; reuse двух изменённых рецептов **94,70%**. Это реальные новые предметные программы, но не сохранённые игровые предметы и не Visual/VFX/gameplay campaign. Запросы заняли **78,047 / 63,524 / 92,360 с**: cache hit не убрал генерацию ответа/reasoning и не доказывает общего ускорения craft. Exact packets/wire/statuses/usage/outputs — `cache-and-prompt-deep-followup/native-author-final`.

Первичные источники: [OpenAI caching](https://developers.openai.com/api/docs/guides/prompt-caching) различает write и lookup; правила Platform не считаются гарантией subscription. [Codex #51353](https://github.com/openai/codex/issues/51353) описывает сходный отказ explicit breakpoint на той же модели (пользовательское сообщение, не официальный диагноз). [Codex #51156](https://github.com/openai/codex/pull/51156) переносит native instructions в developer input; сам PR не доказывает рост cache hits. [Native affinity](https://github.com/openai/codex/pull/44862) подтверждает роль `session-id`. Исследование с pinned source URLs — task artifact `cache-research/REPORT_RU.md`.

## Владельцы и регрессии

[Prefix](../LocalGenerator/infini_local/core/llm_prompt_cache.py): `json_prefix_chars`/`with_prompt_cache_prefix`; [Author/Repair/VFX](../LocalGenerator/infini_local/pipelines/llm_authoring_pipeline.py), [Visual](../LocalGenerator/infini_local/pipelines/visual_generation_pipeline.py), [VFX ordering](../LocalGenerator/infini_local/core/vfx_manifest.py); [transport](../LocalGenerator/infini_local/pipelines/llm_transport.py), [Codex whitelist](../LocalGenerator/infini_local/services/codex_text_backend.py).

[Request](../LocalGenerator/tests/test_provider_request_contract.py)/[transport](../LocalGenerator/tests/test_provider_transport_contract.py) regressions: identity/invalidation/processes/exact split/stripped marker/unknown endpoints/zero-vs-missing usage/continuation. [Offline QA](../LocalGenerator/QUICK_START_RU.md); HTTP fixtures не GPU cache proof.

[OpenAI](https://developers.openai.com/api/docs/guides/prompt-caching) · [OpenRouter](https://openrouter.ai/docs/guides/best-practices/prompt-caching) · [Gemini](https://ai.google.dev/gemini-api/docs/generate-content/caching) · [Codex upstream key](https://github.com/openai/codex/blob/main/codex-rs/codex-api/src/common.rs).
