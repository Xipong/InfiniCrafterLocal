# Трёхстадийный LLM pipeline — 0.4.248

[System authority](../PROJECT_ARCHITECTURE_RU.md#authority) · [Author](LOW_LEVEL_RUNTIME_AUTHORING_RU.md) · [Repair](TARGETED_REPAIR_PROTOCOL_RU.md)

<a id="flow"></a>
## Happy path и handoffs

| Стадия fresh LLM craft | Baseline calls | Принятый output / следующий consumer |
|---|---:|---|
| Gameplay Author | 1 | Strict validation → technical compile → typed wire; entities/visual roles и raw parent facts → Visual |
| Visual Director | 1 | Entity-based visual kit; accepted gameplay + visual context → VFX |
| VFX Director | 1 | Finite slots над exact `entityId + event`; самостоятельные image ingredients → общий image pass |
| Repairs | 0 | Нет при валидных outputs |

После **трёх текстовых стадий**: asset runtime gates → image generation → visual delivery → parent summary → final normalize/runtime/VFX gates → stage accounting → world metadata/health → sanitize → final cached-payload check → atomic recipe commit. VFX asset ID, общий нескольким элементам, не требует отдельной image job на каждый элемент. Required PNG нельзя заменить placeholder. Visual/VFX не добавляют gameplay и не выбирают weapon family.

Owner — [combine_pipeline.combine](../LocalGenerator/infini_local/pipelines/combine_pipeline.py#L265); assets — [image lifecycle](IMAGE_ASSET_LIFECYCLE_RU.md) / [VFX materials](VFX_MATERIAL_ELEMENTS_RU.md). Cache/dev path отдельно от fresh LLM craft.

<a id="repairs-accounting"></a>
## Conditional repairs и accounting

Gameplay rejection открывает только Gameplay Repair; Visual contract rejection — Visual Repair; VFX rejection — VFX Repair. Невалидный initial Author/Visual JSON может израсходовать тот же единственный Repair как format pass. Ошибка image generation/final delivery не разрешает новый бесконечный reauthor loop.

[Frozen-first protocol](TARGETED_REPAIR_PROTOCOL_RU.md#frozen-first) применяется во всех трёх доменах: exact invalid leaves/dependencies, read-only accepted context, audit проигнорированных лишних правок, полная повторная валидация. Repair предыдущий валидный stage не перезапускает; обязательного judge/critic нет.

`llmStageAccounting`: `gameplayAuthorCalls`, `gameplayRepairCalls`, `visualDirectorCalls`, `visualRepairCalls`, `vfxDirectorCalls`, `vfxRepairCalls`. Fresh happy path — `1/0/1/0/1/0`; каждый repair count не более одного. [Topology gate](../LocalGenerator/infini_local/pipelines/combine_pipeline.py#L66) проверяет это перед commit. Это logical stage calls, не обещание ровно трёх HTTP attempts: transport compatibility retries считают отдельно.

## Статические инструкции и provider cache

Каждый production builder (Author/Visual/VFX, их scoped Repair и Gameplay Format Repair) создаёт complete JSON DEVELOPER с явно выбранными application-owned rules/catalog и complete JSON USER с оставшимися данными. `core/llm_prompt_cache.py:with_instruction_segments` не угадывает authority по повторяемости: только builder перечисляет instruction members. Parents/tooltips, accepted runtime, errors, invalid fragments, fieldPermissions/create-policy и item-specific output schema остаются USER. Состав объединённого dossier и frozen merge не меняются; trace сохраняет все сообщения.

Visual отдельно выделяет неизменные `spritePresentationReadOnly` (units/axis/formulas, registry descriptions и ownership rules) в DEVELOPER; только выбранный runtime role roster `bakeFillByProcessingRole` вынесен в USER рядом с `acceptedPresentationMechanicsReadOnly`. Все исходные leaf values сохраняются; semantic test observer восстанавливает прежнюю вложенность role map. Entity-specific responseSchema и Repair permissions не повышаются до instruction authority.

`llm_transport.py` вычисляет content identity до dynamic USER. Native Codex сохраняет прежние effective typed DEVELOPER/USER, JSON marker, key и `session-id` affinity. Generic Responses сохраняет explicit developer, неизвестные roles отвергает вместо demotion. Только точный Nous Chat endpoint + OpenAI model получает измеренный `prompt_cache_key` и invariant final USER `JSON response.` (один раз); ни retention, ни Platform breakpoints, ни новые affinity headers ему не приписываются. Остальные optional controls остаются endpoint-allowlisted. Marker/key — не доказательство cache hit: это только raw provider cached-token counters на разных fresh tails.

Offline contract: `test_craft_instruction_segments.py` проходит все семь builders через реальные senders с остановкой до auth/network, проверяет roles, static/key invariance, parent-representation negative controls, static invalidation и malformed declaration refusal. Semantic tests читают derived dossier через `prompt_packet_helpers.py`, не подменяя production packets. Live/game/GPU acceptance отдельно.

Transport retries/continuation — [отдельная boundary](../PROJECT_ARCHITECTURE_RU.md#pipeline), не новые authoring stages. [Provider-aware admission и quota feedback](LLM_PROVIDER_ADMISSION_RU.md): известный Nous OpenAI route не получает выдуманный char/4 token window; unknown routes сохраняют conservative policy, FIFO/deadline/429 общие. Offline tests: `test_low_level_three_stage_pipeline.py`, `test_pipeline_repair_contract.py` из [test owners](TEST_CONTRACT_OWNERS_RU.md); green не означает live/game/MP прогон.
