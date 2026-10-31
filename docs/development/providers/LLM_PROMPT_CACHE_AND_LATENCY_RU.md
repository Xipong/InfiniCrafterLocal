# Prompt cache и задержка LLM

## Граница реализации

Cache — provider KV-prefix reuse, **не** рецепт/инструкции на диске. Author → Visual → VFX/условные scoped frozen Repairs и local validation не меняются.

Rules/catalog перед parents/IDs/visual kit/errors/exact schemas. Internal `_infini_prompt_cache` маркирует объявленную builder границу и не попадает в wire; сам marker **не** разрешает повышать роль данных. Initial Author сохраняет отдельную явно объявленную `staticInstructionPrefix=true` проекцию собственного каталога в developer JSON. Director/Repair builders формируют полные app-owned DEVELOPER instruction/schemaDefinitions и отдельный USER контекст. Parents, accepted mechanics, exact entity/event selectors и Repair permissions остаются USER; полный Author catalog не добавляется downstream ради hit. Обратная сборка Director/Repair dossier восстанавливает inline grammar и все исходные факты; provider `json_schema` остаётся полным. Framing — явный контракт builder/adapter, не побайтовая идентичность прежнего HTTP body и не доказательство fresh cache hit.

Identity: SHA-256 предшествующих/system messages + exact static prefix + model/response format/effective reasoning; без recipe suffix/UUID/time/credentials/account IDs. Codex использует фактическую adapter projection; новая developer-граница дополнительно отделена versioned framing identity. Одинаковые bytes дают стабильный key между процессами; catalog/instructions/model/exact schema меняют его. Exact entity IDs не скрываются ради hit.

Каждый stage request самодостаточен; сохранённая response-history chain не используется как источник контекста. Prompt cache — reuse объявленного prefix, не conversation history.

## Поддержка провайдеров

| Реализованный маршрут | Adapter wire |
|---|---|
| `openai_compat`: точный `https://api.openai.com/v1`; `openrouter`: точный `https://openrouter.ai/api/v1` с `openai/gpt-…` | Numeric GPT 5.6+ → `prompt_cache_breakpoint`, `prompt_cache_options.mode=explicit`, стабильный `prompt_cache_key`; прежние распознанные GPT → только key |
| Codex subscription | Whitelisted key + согласованный `session-id`, `store=false`; explicit app-owned Author static developer prefix; без Platform breakpoint/retention/resource API, прогрева и дополнительных запросов |
| Direct Gemini compatible | Stable prefix для возможного implicit reuse; без OpenAI options/платного `cachedContents`/TTL lifecycle |
| Другие compatible/local | Прежние messages; `cache_prompt`, slot save/restore, durable KV-file здесь не реализованы |

Split: Chat `text`, Responses `input_text`; concatenation byte-equivalent, variable suffix не cache-write marker. Это serializer behavior, **не live acceptance** всех моделей. Provider хранит KV; restart сохраняет key, не lifetime cache. Eviction/endpoint/account/model change дают miss. Код не покупает/продлевает TTL; прежний upstream OpenAI 5.6+ default 30 минут не локальная гарантия. Threshold/TTL/pricing проверяй у provider.

## Каноническая грамматика Visual/VFX

Production builders отделяют полный `system` + builder-owned `developer` contract от
case-specific `user` dossier. `schemaDefinitions.$defs` в DEVELOPER содержит только
явно выбранные owner paths из канонической схемы; USER schema ссылается на них через
`#/$defs/`. Раскрытие ссылок буквально восстанавливает исходную inline schema.
`response_format=json_schema` по-прежнему передаёт полную inline provider schema,
без cache refs и без ослабления constraints.

- Visual Director и scoped Visual Repair: item/itemPatch и точные
  повторяющиеся entity scale/prompt/silhouette/visualIdentity nodes. `animationPlan`
  optional advisory и не входит в mutable Repair surface. Ссылки на одну
  definition разрешены лишь при идентичных compact JSON bytes выбранных узлов.
- VFX Director и scoped VFX Repair: invariant slot properties, rendererRequirements
  clauses, material/sound payloads и asset schemas. Exact
  entity/event enums и все последующие runtime-dependent compatibility clauses
  остаются inline USER constraints; поля Repair scope/permissions не переносятся.
- Scoped Repair включает только разрешённые операции/листья и нужные зависимости;
  full inline provider schema относится к этому exact patch domain, не к initial
  design. Frozen case constants остаются USER, не общим cache vocabulary.
- Нет recursive common-field cache heuristic, demotion ролей или
  изменений Author. Static packet/affinity стабильность проверяется offline через
  настоящий native serializer на трёх разных runtime rosters; это не новый live
  cache hit или измерение ускорения.

Регрессии: `LocalGenerator/tests/test_director_schema_cache_extraction.py` — literal
reconstruction, native wire/affinity, changed-tail/static-revision и valid/invalid
parity; frozen merge проверяется существующими Repair contract tests.

## Наблюдаемость

`LLM usage`/debug: `cachedInputTokens` = сообщённый `cached_tokens`, иначе null; `cacheHit` = positive → true, explicit zero → false, missing → null; `cacheWriteTokens` = сообщённый `cache_write_tokens`, иначе null. Key/marker/readiness ≠ hit. Codex допускает nonnegative integer counters без metadata/credentials. Explicit write может быть платным. [Trace paths](../../user/OPERATIONS_RU.md#запустить-перед-игрой).

`inputTokens`/`outputTokens` читают соответственно Responses `input_tokens`/`output_tokens` либо Chat `prompt_tokens`/`completion_tokens`, если основной ключ отсутствует. Явный ноль сохраняется; отсутствующий, null, boolean, отрицательный и нецелочисленный счётчик даёт null, не фиктивный нулевой расход и не coercion. `reasoningTokens` читает `output_tokens_details.reasoning_tokens` либо Chat `completion_tokens_details.reasoning_tokens`, когда Responses details не объект. Исходный provider `usage`, запросы и cache-routing не меняются; это наблюдаемость ответа, не новое измерение billing/cache hit.

## Локальная производительность

`json_object`/off не строят discarded provider schema eagerly; `json_schema` factory/local strict checks сохранены. Model/reasoning/budgets/stages не урезаются. Remote prefill/decode/Repairs/quota доминируют; миллисекунды Python не делают craft мгновенным.

Cache key/стабильный prefix не доказывают hit, latency speedup или качество полной генерации. Нужны provider usage counters на реальных different-tail requests; fixture replay/короткий диагностический ответ не заменяет полный craft. Исторические измерения не являются текущими defaults или гарантией поддержки endpoint. Live/provider probes требуют отдельного разрешения.

## Владельцы и регрессии

[Prefix](../../../LocalGenerator/infini_local/core/llm_prompt_cache.py): `json_prefix_chars`/`with_prompt_cache_prefix`; [Author/Repair](../../../LocalGenerator/infini_local/pipelines/author/request.py), [VFX transport](../../../LocalGenerator/infini_local/pipelines/vfx/request.py), [Visual](../../../LocalGenerator/infini_local/pipelines/visual/request.py), [VFX packet](../../../LocalGenerator/infini_local/pipelines/vfx/prompt.py); [transport](../../../LocalGenerator/infini_local/pipelines/transport/client.py), [Codex whitelist](../../../LocalGenerator/infini_local/services/codex_text_backend.py).

[Request](../../../LocalGenerator/tests/test_provider_request_contract.py)/[transport](../../../LocalGenerator/tests/test_provider_transport_contract.py) regressions: identity/invalidation/processes/exact split/stripped marker/unknown endpoints/zero-vs-missing usage/self-contained requests. [Offline QA](../../user/START_RU.md); HTTP fixtures не GPU cache proof.

[OpenAI](https://developers.openai.com/api/docs/guides/prompt-caching) · [OpenRouter](https://openrouter.ai/docs/guides/best-practices/prompt-caching) · [Gemini](https://ai.google.dev/gemini-api/docs/generate-content/caching) · [Codex upstream key](https://github.com/openai/codex/blob/main/codex-rs/codex-api/src/common.rs).
