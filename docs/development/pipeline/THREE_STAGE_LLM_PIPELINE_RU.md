# Трёхстадийный LLM pipeline

[System authority](../architecture/ARCHITECTURE_RU.md#authority) · [Author](../../reference/authoring/LOW_LEVEL_RUNTIME_AUTHORING_RU.md) · [Repair](TARGETED_REPAIR_PROTOCOL_RU.md)

<a id="flow"></a>
## Happy path и handoffs

| Стадия fresh LLM craft | Baseline calls | Принятый output / следующий consumer |
|---|---:|---|
| Gameplay Author | 1 | Strict validation → technical compile → typed wire; entities/visual roles и raw parent facts → Visual |
| Visual Director | 1 | Entity-based visual kit; accepted gameplay + visual context → VFX |
| VFX Director | 1 | Finite slots над exact `entityId + event`; самостоятельные image ingredients → общий image pass |
| Repairs | 0 | Нет при валидных outputs |

После **трёх текстовых стадий**: asset runtime gates → image generation → visual delivery → parent summary → final normalize/runtime/VFX gates → stage accounting → world metadata/health → sanitize → final cached-payload check → atomic recipe commit. VFX asset ID, общий нескольким элементам, не требует отдельной image job на каждый элемент. Required PNG нельзя заменить placeholder. Visual/VFX не добавляют gameplay и не выбирают weapon family.

Stage-level Gameplay admission/compile/wire/conditional Repair находится в [gameplay_stage](../../../LocalGenerator/infini_local/pipelines/author/stage.py); VFX transport — в [vfx_generation_pipeline](../../../LocalGenerator/infini_local/pipelines/vfx/request.py). Их внутренние imports не являются compatibility API.

Parent context: `context/cards.py.raw_parent_card_for_llm` собирает Author/Visual packets из source facts и exact accepted generated runtime. `context/parents.py` извлекает current native numeric/projectile/ammo facts, generated parents сохраняют полный exact graph без single-projectile compatibility projection; identity primitives принадлежат `core.item_identity_tools`. Parent prose — advisory context, не authority или отдельная knowledge/category/power стадия. Provenance, zeros/false и Visual-only appearance сохраняются в соответствующем handoff.

Orchestration owner — [combine_pipeline.combine](../../../LocalGenerator/infini_local/pipelines/combine_pipeline.py); assets — [image lifecycle](IMAGE_ASSET_LIFECYCLE_RU.md) / [VFX materials](../../reference/presentation/VFX_MATERIAL_ELEMENTS_RU.md). Cache/dev path отдельно от fresh LLM craft.

<a id="resume"></a>
## Продолжение принятого дизайна

`combine` сохраняет отдельный checkpoint после принятого compiled Author wire, Visual kit и VFX manifest. Owner хранения — `storage/craft_progress.py`; файл `world_*/checkpoints/<recipeKey>.checkpoint` находится вне `recipes/` и не имеет расширения, разрешённого asset endpoint. Записи используют существующий `atomic_write_json`; ошибка записи останавливает следующую платную стадию, сохраняя предыдущий атомарный снимок.

Resume привязан к полным фактам обоих родителей, world, identity version, multi-dev lane, режиму авторства и явным stamps Author/wire/Visual/VFX. При перестановке A/B проверяется точное равенство полной пары и восстанавливается исходный порядок для оставшихся стадий. Ключи доступа, URL, transport budgets и случайно выбранный round-robin lease не входят в эту идентичность. Новый lease нужен только для оставшихся текстовых стадий; старый response chain не восстанавливается.

При чтении проверяются checksum принятого снимка, текущий runtime wire, Visual kit и его каноническая проекция, VFX wire и accounting уже принятых стадий. Compiler и Repair для них повторно не запускаются. Повреждение — явный отказ с сохранением файла; изменившиеся входы/контракты — новая генерация с записью причины в trace. Это сохранение и проверка уже принятого результата, без выбора или исправления authored дизайна.

Общий image request сохраняет receipt каждого успешно опубликованного PNG сразу из worker. Существующий `copy_context()` переносит текущий `CraftProgress`; его lock объединяет receipts и stage snapshots без потери соседних записей. Полный image request и влияющие на рисунок настройки задают identity; reuse требует актуальной технической проверки, SHA256, размера и соответствующего content-addressed имени. Отсутствующий/доказанно повреждённый PNG создаётся заново; ошибки доступа/чтения проходят наружу без нового image call. Snapshot дизайна остаётся **до** image hydration, поэтому suffix исходного prompt не добавляется повторно.

Полный committed cache имеет приоритет. Checkpoint удаляется только после успешного `cache_put`; ошибка уборки не превращает готовый крафт в ошибку. Delivery gates всегда выполняются перед commit. `llmStageAccounting` сохраняет происхождение принятых стадий; неудавшиеся попытки остаются в request/transport traces. Offline behavioral coverage: `test_generation_resume.py` и `test_image_checkpoint_reuse.py`, включая независимые процессы и параллельные image jobs.

<a id="repairs-accounting"></a>
## Conditional repairs и accounting

Executable Gameplay rejection открывает только Gameplay Repair; required Visual contract rejection — Visual Repair; VFX rejection — VFX Repair. Optional `concept`/`realization` и текстовый `selfEvaluation`, как и Visual `animationPlan`, advisory: их отсутствие/оформление не вызывает Repair и не блокирует валидный executable/art contract. Невалидный initial Author/Visual JSON может израсходовать тот же единственный Repair как format pass. Ошибка image generation/final delivery не разрешает новый бесконечный reauthor loop.

[Frozen-first protocol](TARGETED_REPAIR_PROTOCOL_RU.md#frozen-first) применяется во всех трёх доменах: exact invalid leaves/dependencies, read-only accepted context, audit проигнорированных лишних правок, полная повторная валидация. Repair предыдущий валидный stage не перезапускает; обязательного judge/critic нет.

`llmStageAccounting`: `gameplayAuthorCalls`, `gameplayRepairCalls`, `visualDirectorCalls`, `visualRepairCalls`, `vfxDirectorCalls`, `vfxRepairCalls`. Fresh happy path — `1/0/1/0/1/0`; каждый repair count не более одного. [Topology gate](../../../LocalGenerator/infini_local/pipelines/combine_pipeline.py) проверяет это перед commit. Это logical stage calls, не обещание ровно трёх HTTP attempts: transport compatibility retries считают отдельно.

## Статические инструкции и provider cache

Каждый production builder (Author/Visual/VFX, их scoped Repair и Gameplay Format Repair) создаёт complete JSON DEVELOPER с явно выбранными application-owned rules/catalog и complete JSON USER с оставшимися данными. `core/llm_prompt_cache.py:with_instruction_segments` не угадывает authority по повторяемости: только builder перечисляет instruction members. Parents/tooltips, accepted runtime, errors, invalid fragments, fieldPermissions/create-policy и item-specific output schema остаются USER. Состав объединённого dossier и frozen merge не меняются; trace сохраняет все сообщения.

Visual отдельно выделяет application-owned `spritePresentationReadOnly` (units/axis/formulas, registry descriptions и ownership rules) в DEVELOPER; выбранный runtime role roster `bakeFillByProcessingRole` и `acceptedPresentationMechanicsReadOnly` — USER. Scoped Repair выбирает нужные части guidance по exact editable paths: size-only сохраняет calibration, mechanics и parent visual references без повторного полного design dossier. Accepted visual source не обрезается. Entity-specific responseSchema и Repair permissions не повышаются до instruction authority.

Initial Visual/VFX и Repair с нужными invariant nodes включают явно выбранные application-owned canonical output grammar nodes в **тот же полный DEVELOPER** `schemaDefinitions={"$defs":…}` рядом с rules. VFX берёт `element/path/screenShake/particle/sound` непосредственно из schema владельцев `core/vfx/schema.py`/`core/vfx/materials.py`; Visual — `item` либо частичный `itemPatch` из `_visual_item_schema` и существующей provider projection. Остальная schema использует `#/$defs/…`; объединение definitions и case schema — та же JSON Schema grammar, не новый набор правил. Exact entity/event enums, item-body/texture/history clauses, configured limits, equipment branches и все Repair facts остаются case USER. Authority определяется владельцем grammar, не cacheability; runtime facts не повышаются до DEVELOPER.

Внутренний `_infini_prompt_cache={instructionMessageIndex:1}` объявляет конец полного DEVELOPER. Валидатор требует adjacent DEVELOPER/USER, disjoint nonempty objects, точные metadata keys и strict JSON: nested/escaped duplicates, NaN/Infinity/`1e999`, неверные roles/indices и overlaps отвергаются до send. Author/Gameplay Repair сохраняют прежний marker и wire/key bytes. Scoped Visual/VFX и Format Repair сохраняют протокол marker, но содержимое и identity отражают реально отправленную сокращённую grammar.

`response_format` содержит **полную inline provider schema текущего запроса**; у scoped Repair это permission-derived grammar, не весь initial design domain. Provider constraints не заменяются внешними refs. При json_object/off все поля остаются доступны через schemaDefinitions + case schema. Key включает весь declared static prefix и effective model/reasoning/format framing; для grammar framing case-specific full response schema исключена только из routing identity, не из запроса. Изменение definitions инвалидирует key, изменение runtime enums/parents/Repair tail — нет. Это не обещает, что provider сможет reuse prefix при смене structured schema.

`pipelines/transport/client.py` вычисляет content identity до dynamic USER. Native Codex сохраняет typed DEVELOPER/USER без demotion; Author JSON marker, key и `session-id` affinity byte-identical. Generic Responses сохраняет explicit developer, неизвестные roles отвергает вместо demotion. Только точный Nous Chat endpoint + OpenAI model получает измеренный `prompt_cache_key` и invariant final USER `JSON response.` (один раз); ни retention, ни Platform breakpoints, ни новые affinity headers ему не приписываются. Остальные optional controls остаются endpoint-allowlisted. Marker/key — не доказательство cache hit: это только raw provider cached-token counters на разных fresh tails.

Offline contract: `test_craft_instruction_segments.py` и `test_stable_schema_data.py` проходят все семь builders через реальные senders с остановкой до auth/network: Nous/OpenAI/OpenRouter Chat, native Codex и OpenAI Responses × json_object/json_schema/off. Проверяются roles, полный provider schema, static/key invariance, parent/runtime-enum tail controls, canonical owner revision invalidation, valid/invalid `$defs` validator parity и malformed declaration refusal. Semantic tests читают derived dossier через `prompt_packet_helpers.py`, не подменяя production packets. Live/game/GPU acceptance отдельно.

Transport retries и self-contained requests — [отдельная boundary](../architecture/ARCHITECTURE_RU.md#pipeline), не новые authoring stages. [Provider-aware admission и quota feedback](../providers/LLM_PROVIDER_ADMISSION_RU.md): известный Nous OpenAI route не получает выдуманный char/4 token window; unknown routes сохраняют conservative policy, FIFO/deadline/429 общие. Offline tests: `test_low_level_three_stage_pipeline.py`, `test_pipeline_repair_contract.py` из [test owners](../TESTING_RU.md); green не означает live/game/MP прогон.
