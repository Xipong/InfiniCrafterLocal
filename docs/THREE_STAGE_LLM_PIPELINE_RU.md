# Трёхстадийный LLM pipeline — 0.4.246

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

Transport retries/continuation — [отдельная boundary](../PROJECT_ARCHITECTURE_RU.md#pipeline), не новые authoring stages. Offline tests: `test_low_level_three_stage_pipeline.py`, `test_pipeline_repair_contract.py` из [test owners](TEST_CONTRACT_OWNERS_RU.md); green не означает live/game/MP прогон.
