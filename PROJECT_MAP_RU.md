# InfiniCrafterLocal v0.4.254 — карта owners

[Архитектура и trust boundaries](PROJECT_ARCHITECTURE_RU.md) · [Добавить capability](docs/ADDING_RUNTIME_CAPABILITY_FOR_AGENTS_RU.md) · [Generated contract](lowery.md) · [Placed PNG source/runtime owners](docs/PRESENT_PLACED_ITEM_SPRITE_RU.md)

<a id="python"></a>
## LocalGenerator: куда идти за изменением

Python base: [`LocalGenerator/infini_local/`](LocalGenerator/infini_local/FOLDER_DOCS_RU.md). Public imports: `infini_local.core.runtime_authoring`, не deleted legacy compiler/root lowerers. Имена без directory в первых шести строках — `core/runtime_authoring/`; далее соседние bare filenames имеют тот же directory, что предшествующий path.

| Изменение | Canonical owner относительно Python base |
|---|---|
| Grammar, units, events, authority | `core/runtime_authoring/capability_registry.py` |
| Author/Repair shape | `program_schema.py` в том же runtime_authoring |
| Dependencies/slots/producers/budgets | `validator.py`, `event_producer_validation.py`, `binding_use_policy.py` |
| Frozen scope/filter | `repair_scope.py`; shared leaf merge — `core/repair_merge.py` |
| Projection/receipts/final wire | `compiler.py`, `technical_lowering.py`, `wire_validator.py` |
| Terraria mappings | `terraria_vocabulary.py` |
| Model prose/packet | `pipelines/author_item_contract.py`, `llm_authoring_prompt.py` |
| Author/Repair/stage orchestration | `pipelines/llm_authoring_pipeline.py`, `combine_pipeline.py` |
| Numeric parent corridor | `pipelines/combine_balance.py` |
| Profile lease/provider/Responses | `pipelines/llm_transport.py`, `core/llm_config.py` |
| Visual + PNG delivery | `pipelines/visual_generation_pipeline.py`, `visual_delivery_gate.py`; [image owner](docs/IMAGE_ASSET_LIFECYCLE_RU.md) |
| VFX slots/PNG dependencies | `core/vfx_manifest.py`, `vfx_material_contract.py`; [точные sound samples/controls](docs/VFX_SOUND_PALETTE_RU.md) |
| World recipes/health/traces | `storage/world_recipe_runtime.py`, `world_storage.py`, `trace_runtime.py` |
| C# executable completeness | `qa/primitive_loss_audit.py`; [QA owners](LocalGenerator/infini_local/qa/FOLDER_DOCS_RU.md), [test owners](docs/TEST_CONTRACT_OWNERS_RU.md) |

<a id="csharp"></a>
## ModSources: consumers и persistent state

C# base: [`ModSources/InfiniCrafterLocal/`](ModSources/InfiniCrafterLocal/FOLDER_DOCS_RU.md); `GeneratedItem*`/`GeneratedProjectile*` включают partials.

| Surface | Canonical source относительно C# base |
|---|---|
| Strict DTO/vocabulary/safety | `Common/Models/RuntimeProgramSpec.cs`, `TerrariaRuntimeVocabulary.cs`, `GeneratedEquipmentBounds.g.cs` |
| Item projection/hooks | `Common/Models/GeneratedItemData.Apply.cs`, `Content/Items/GeneratedItem.cs` |
| Bindings/events/delays/hit receipt | `Common/Runtime/RuntimeProgramExecutor.cs`, `RuntimeDelayedActionScheduler.cs`, `RuntimeHitPullBridge.cs` |
| Entity lifecycle/net/visual | `Content/Projectiles/GeneratedProjectile.cs` |
| VFX DTO/rendering | `Common/Models/VfxManifestSpec.cs`; [VFX owners](ModSources/InfiniCrafterLocal/Common/VFX/FOLDER_DOCS_RU.md) |
| Station lanes/world journal | `Common/Players/InfiniCraftPlayer.MultiDev.cs`, `Common/Systems/GeneratedStationEscrowStateSystem.cs` |
| Placed-item world returns | `Common/Systems/GeneratedPlacementLedgerSystem.cs` |
| Shared limits/packet IDs | `Common/InfiniRuntimeLimits.cs`, `Common/InfiniNetPacketIds.cs` |

<a id="projections"></a>
## Generated поверхности и gates

`contracts/schemas/` — provider exports; [lowery.md](lowery.md), [inventory](docs/LOW_LEVEL_CAPABILITY_INVENTORY_RU.md), [lowering audit](TECHNICAL_LOWERING_AUDIT_RU.md), [primitive parity](docs/PRIMITIVE_PARITY_RU.md) — проверяемые проекции, не ручные registries. Генераторы `tools/generate_lowery.py`, `generate_low_level_runtime_docs.py`, `generate_equipment_bounds.py`, `generate_primitive_parity.py` обслуживают соответствующие outputs.

Канонический [data flow](docs/THREE_STAGE_LLM_PIPELINE_RU.md#flow) не имеет weapon IR fallback. Новая механика требует [полного vertical slice](docs/ADDING_RUNTIME_CAPABILITY_FOR_AGENTS_RU.md#vertical-slice), включая consumer и witness; изменение только prompt, schema или C# не завершает capability.
