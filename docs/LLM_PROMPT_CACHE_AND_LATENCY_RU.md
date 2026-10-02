# Prompt cache и задержка LLM

## Граница реализации

Cache — provider KV-prefix reuse, **не** рецепт/инструкции на диске. Author → Visual → VFX/условные scoped frozen Repairs и local validation не меняются.

Rules/catalog перед parents/IDs/visual kit/errors/exact schemas. Internal `_infini_prompt_cache={messageIndex,prefixChars}` маркирует static user boundary, не попадает в wire. JSON values/два messages сохраняются; full Author catalog не добавляется в Repair/следующие стадии ради hit.

Identity: SHA-256 предшествующих/system messages + exact static prefix + model/response format/effective reasoning; без recipe suffix/UUID/time/credentials/account IDs. Одинаковые bytes дают стабильный key между процессами; catalog/instructions/model/exact schema меняют его. Exact entity IDs не скрываются ради hit.

Marked Responses dossiers не используют/не сохраняют `previous_response_id`; unmarked generic calls сохраняют прежний continuation contract. Conversation history ≠ prompt cache.

## Поддержка провайдеров

| Реализованный маршрут | Adapter wire |
|---|---|
| `openai_compat`: точный `https://api.openai.com/v1`; `openrouter`: точный `https://openrouter.ai/api/v1` с `openai/gpt-…` | Numeric GPT 5.6+ → `prompt_cache_breakpoint`, `prompt_cache_options.mode=explicit`, стабильный `prompt_cache_key`; прежние распознанные GPT → только key |
| Codex subscription | Whitelisted key, `store=false`; без Platform breakpoint/retention/resource API |
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

## Owners и проверка

[Prefix](../LocalGenerator/infini_local/core/llm_prompt_cache.py): `json_prefix_chars`/`with_prompt_cache_prefix`; [Author/Repair/VFX](../LocalGenerator/infini_local/pipelines/llm_authoring_pipeline.py), [Visual](../LocalGenerator/infini_local/pipelines/visual_generation_pipeline.py), [VFX ordering](../LocalGenerator/infini_local/core/vfx_manifest.py); [transport](../LocalGenerator/infini_local/pipelines/llm_transport.py), [Codex whitelist](../LocalGenerator/infini_local/services/codex_text_backend.py).

[Request](../LocalGenerator/tests/test_provider_request_contract.py)/[transport](../LocalGenerator/tests/test_provider_transport_contract.py) regressions: identity/invalidation/processes/exact split/stripped marker/unknown endpoints/zero-vs-missing usage/continuation. [Offline QA](../LocalGenerator/QUICK_START_RU.md); HTTP fixtures не GPU cache proof.

[OpenAI](https://developers.openai.com/api/docs/guides/prompt-caching) · [OpenRouter](https://openrouter.ai/docs/guides/best-practices/prompt-caching) · [Gemini](https://ai.google.dev/gemini-api/docs/generate-content/caching) · [Codex upstream key](https://github.com/openai/codex/blob/main/codex-rs/codex-api/src/common.rs).
