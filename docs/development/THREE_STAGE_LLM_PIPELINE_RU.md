# Трёхстадийный LLM pipeline — 0.4.248

[System authority](ARCHITECTURE_RU.md#authority) · [Author](../reference/LOW_LEVEL_RUNTIME_AUTHORING_RU.md) · [Repair](TARGETED_REPAIR_PROTOCOL_RU.md)

<a id="flow"></a>
## Happy path и handoffs

| Стадия fresh LLM craft | Baseline calls | Принятый output / следующий consumer |
|---|---:|---|
| Gameplay Author | 1 | Strict validation → technical compile → typed wire; entities/visual roles и raw parent facts → Visual |
| Visual Director | 1 | Entity-based visual kit; accepted gameplay + visual context → VFX |
| VFX Director | 1 | Finite slots над exact `entityId + event`; самостоятельные image ingredients → общий image pass |
| Repairs | 0 | Нет при валидных outputs |

После **трёх текстовых стадий**: asset runtime gates → image generation → visual delivery → parent summary → final normalize/runtime/VFX gates → stage accounting → world metadata/health → sanitize → final cached-payload check → atomic recipe commit. VFX asset ID, общий нескольким элементам, не требует отдельной image job на каждый элемент. Required PNG нельзя заменить placeholder. Visual/VFX не добавляют gameplay и не выбирают weapon family.

Stage-level Gameplay admission/compile/wire/conditional Repair находится в [gameplay_stage](../../LocalGenerator/infini_local/pipelines/gameplay_stage.py); VFX transport — в [vfx_generation_pipeline](../../LocalGenerator/infini_local/pipelines/vfx_generation_pipeline.py). Их внутренние imports не являются compatibility API.

Parent context: `parent_context_cards.raw_parent_card_for_llm` — единственный assembler Author/Visual packets; `parent_context_pipeline` извлекает source facts и сохраняет активный parent-power profile для `item_power_knowledge`. Identity primitives импортируются прямо из `core.item_identity_tools`. Неиспользуемый alternative `llm_parent_card`, derived-semantics и behavior-policy builders удалены: они не участвовали в requests. Exact accepted runtime, provenance, zeros/false и Visual-only appearance сохраняют прежнюю проекцию.

Orchestration owner — [combine_pipeline.combine](../../LocalGenerator/infini_local/pipelines/combine_pipeline.py); assets — [image lifecycle](IMAGE_ASSET_LIFECYCLE_RU.md) / [VFX materials](../reference/VFX_MATERIAL_ELEMENTS_RU.md). Cache/dev path отдельно от fresh LLM craft.

<a id="repairs-accounting"></a>
## Conditional repairs и accounting

Gameplay rejection открывает только Gameplay Repair; Visual contract rejection — Visual Repair; VFX rejection — VFX Repair. Невалидный initial Author/Visual JSON может израсходовать тот же единственный Repair как format pass. Ошибка image generation/final delivery не разрешает новый бесконечный reauthor loop.

[Frozen-first protocol](TARGETED_REPAIR_PROTOCOL_RU.md#frozen-first) применяется во всех трёх доменах: exact invalid leaves/dependencies, read-only accepted context, audit проигнорированных лишних правок, полная повторная валидация. Repair предыдущий валидный stage не перезапускает; обязательного judge/critic нет.

`llmStageAccounting`: `gameplayAuthorCalls`, `gameplayRepairCalls`, `visualDirectorCalls`, `visualRepairCalls`, `vfxDirectorCalls`, `vfxRepairCalls`. Fresh happy path — `1/0/1/0/1/0`; каждый repair count не более одного. [Topology gate](../../LocalGenerator/infini_local/pipelines/combine_pipeline.py) проверяет это перед commit. Это logical stage calls, не обещание ровно трёх HTTP attempts: transport compatibility retries считают отдельно.

## Статические инструкции и provider cache

Каждый production builder (Author/Visual/VFX, их scoped Repair и Gameplay Format Repair) создаёт complete JSON DEVELOPER с явно выбранными application-owned rules/catalog и complete JSON USER с оставшимися данными. `core/llm_prompt_cache.py:with_instruction_segments` не угадывает authority по повторяемости: только builder перечисляет instruction members. Parents/tooltips, accepted runtime, errors, invalid fragments, fieldPermissions/create-policy и item-specific output schema остаются USER. Состав объединённого dossier и frozen merge не меняются; trace сохраняет все сообщения.

Visual отдельно выделяет неизменные `spritePresentationReadOnly` (units/axis/formulas, registry descriptions и ownership rules) в DEVELOPER; только выбранный runtime role roster `bakeFillByProcessingRole` вынесен в USER рядом с `acceptedPresentationMechanicsReadOnly`. Все исходные leaf values сохраняются; semantic test observer восстанавливает прежнюю вложенность role map. Entity-specific responseSchema и Repair permissions не повышаются до instruction authority.

Visual и VFX включают явно выбранные application-owned canonical output grammar nodes в **тот же полный DEVELOPER** `schemaDefinitions={"$defs":…}` рядом с rules. VFX берёт `element/path/screenShake/particle/sound` непосредственно из schema владельцев `vfx_manifest.py`/`vfx_material_contract.py`; Visual — `item` либо частичный `itemPatch` из `_visual_item_schema` и существующей provider projection. Остальная schema использует `#/$defs/…`; объединение definitions и case schema — та же JSON Schema grammar, не новый набор правил. Exact entity/event enums, item-body/texture/history clauses, configured limits, equipment branches и все Repair facts остаются case USER. Authority определяется владельцем grammar, не cacheability; runtime facts не повышаются до DEVELOPER.

Внутренний `_infini_prompt_cache={instructionMessageIndex:1}` объявляет конец полного DEVELOPER. Валидатор требует adjacent DEVELOPER/USER, disjoint nonempty objects, точные metadata keys и strict JSON: nested/escaped duplicates, NaN/Infinity/`1e999`, неверные roles/indices и overlaps отвергаются до send. Author/Gameplay Repair/Format Repair сохраняют прежний marker и wire/key bytes.

`response_format` по-прежнему содержит **полную inline provider schema**; provider constraints не заменяются внешними refs. При json_object/off все поля остаются доступны через schemaDefinitions + case schema. Key включает весь declared static prefix и effective model/reasoning/format framing; для grammar framing case-specific full response schema исключена только из routing identity, не из запроса. Изменение definitions инвалидирует key, изменение runtime enums/parents/Repair tail — нет. Это не обещает, что provider сможет reuse prefix при смене structured schema.

`llm_transport.py` вычисляет content identity до dynamic USER. Native Codex сохраняет typed DEVELOPER/USER без demotion; Author JSON marker, key и `session-id` affinity byte-identical. Generic Responses сохраняет explicit developer, неизвестные roles отвергает вместо demotion. Только точный Nous Chat endpoint + OpenAI model получает измеренный `prompt_cache_key` и invariant final USER `JSON response.` (один раз); ни retention, ни Platform breakpoints, ни новые affinity headers ему не приписываются. Остальные optional controls остаются endpoint-allowlisted. Marker/key — не доказательство cache hit: это только raw provider cached-token counters на разных fresh tails.

Offline contract: `test_craft_instruction_segments.py` и `test_stable_schema_data.py` проходят все семь builders через реальные senders с остановкой до auth/network: Nous/OpenAI/OpenRouter Chat, native Codex и OpenAI Responses × json_object/json_schema/off. Проверяются roles, полный provider schema, static/key invariance, parent/runtime-enum tail controls, canonical owner revision invalidation, valid/invalid `$defs` validator parity и malformed declaration refusal. Semantic tests читают derived dossier через `prompt_packet_helpers.py`, не подменяя production packets. Live/game/GPU acceptance отдельно.

Историческое offline сравнение static-USER варианта с `28621ad`: 42 real builder packets, 210 candidate wire packets; literal dossier inverse, system/options parity и Author/Gameplay Repair/Format Repair wire+key parity. Пример workbench fixture, json_object, точные chars (UTF-8 bytes static block здесь равны chars):

| Stage | Новый static USER schema block | Dynamic USER было → стало | Inline schema → case schema | Total text delta |
|---|---:|---:|---:|---:|
| Visual | 2877 | 14025 → 11212 | 7367 → 4554 | +281 |
| Visual Repair | 2732 | 15724 → 13066 | 7745 → 5087 | +291 |
| VFX | 19663 | 47972 → 28527 | 42863 → 23418 | +435 |
| VFX Repair | 19663 | 49605 → 30160 | 43226 → 23781 | +435 |

Это перенос уже существующих owner definitions, не удаление выразительных полей и не token/hit measurement. Overlapping payload и packaged definitions не складываются как независимая экономия. Full-schema HTTP constraints и все frozen permissions неизменны. Исторический static-USER прогон на Nous Luna дал changed-tail reuse только SYSTEM/DEVELOPER: Visual 3024 и VFX 4009 cached tokens; отдельные USER definitions не увеличили наблюдаемый cache. Текущий application-owned DEVELOPER grammar framing проверяется отдельно; bounded short-output cache diagnostics не доказывают качество полной генерации, latency speedup или игровые/GPU smoke. Source-bound receipts и итог — `artifacts/developer-grammar-cache/` (локальные, не packaged).

Transport retries/continuation — [отдельная boundary](ARCHITECTURE_RU.md#pipeline), не новые authoring stages. [Provider-aware admission и quota feedback](LLM_PROVIDER_ADMISSION_RU.md): известный Nous OpenAI route не получает выдуманный char/4 token window; unknown routes сохраняют conservative policy, FIFO/deadline/429 общие. Offline tests: `test_low_level_three_stage_pipeline.py`, `test_pipeline_repair_contract.py` из [test owners](TESTING_RU.md); green не означает live/game/MP прогон.
