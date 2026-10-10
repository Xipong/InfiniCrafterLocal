# InfiniCrafterLocal v0.4.254 — карта owners

[Архитектура и trust boundaries](PROJECT_ARCHITECTURE_RU.md) · [Добавить capability](docs/ADDING_RUNTIME_CAPABILITY_FOR_AGENTS_RU.md) · [Generated contract](lowery.md) · [Placed PNG source/runtime owners](docs/PRESENT_PLACED_ITEM_SPRITE_RU.md)

<a id="python"></a>
## LocalGenerator: куда идти за изменением

Fresh source — только `authoring.v5`: flat independent `action`/`stackCost`/`contactDamage`, exact registry-fixed branches и unique item-body identity. Nested source `usePolicy`, v4 и compact API не являются admission paths. Persisted wire сохраняет `usePolicy` и имеет отдельные readers/retained provenance; retirement Author grammar не удаляет recipes.

Python base: [`LocalGenerator/infini_local/`](LocalGenerator/infini_local/FOLDER_DOCS_RU.md). Public imports: `infini_local.core.runtime_authoring`, не deleted legacy compiler/root lowerers. Имена без directory в первых шести строках — `core/runtime_authoring/`; далее соседние bare filenames имеют тот же directory, что предшествующий path.

| Изменение | Canonical owner относительно Python base |
|---|---|
| Grammar, units, events, authority | `core/runtime_authoring/capability_registry.py` |
| Author/Repair shape и scope-derived examples | `program_schema.py` в том же runtime_authoring; `pipelines/author_item_contract.py` строит cards из canonical shapes, real Repair требует non-null realizationReplacement |
| Dependencies/slots/producers/budgets и advisory report leaves | `validator.py`, `event_producer_validation.py`, `binding_use_policy.py`; diagnosed planVsProgram не блокирует craft, но чужие siblings/gameplay/resource guards остаются strict |
| Frozen scope/filter | `repair_scope.py`; shared leaf merge — `core/repair_merge.py` |
| Projection/receipts/final wire | `compiler.py`, `technical_lowering.py`, `wire_validator.py`; scalar fresh names и buff percent units задаёт ParamSpec, retained source names не fresh grammar; exact typed/signed-zero omission и consumer float32 domain проверяются у тех же owners |
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
| Sampled launch / hit-target geometry / physical emission | `Common/Models/RuntimeProgramSpec.cs`, `Common/Runtime/RuntimeSpawnVelocity.cs`, `RuntimeProgramExecutor.cs`, `RuntimeHitNpcGeneration.cs`; exact target geometry и authority/refund имеют собственных владельцев |
| Strict DTO/vocabulary/safety | `Common/Models/RuntimeProgramSpec.cs`, `TerrariaRuntimeVocabulary.cs`, `GeneratedEquipmentBounds.g.cs` |
| Item projection/hooks | `Common/Models/GeneratedItemData.Apply.cs`, `Content/Items/GeneratedItem.cs` |
| Bindings/events/delays/hit receipt | `Common/Runtime/RuntimeProgramExecutor.cs`, `RuntimeDelayedActionScheduler.cs`, `RuntimeHitPullBridge.cs` |
| Entity lifecycle/net/visual | `Content/Projectiles/GeneratedProjectile.cs` |
| Named item effects / exact use selectors | `Common/Models/RuntimeItemEffectGroupSpec.cs`, `Content/Items/GeneratedItem.cs` (`EffectsForBinding`); [контракт](docs/NAMED_ITEM_EFFECT_GROUPS_RU.md) |
| Weapon ammo / spawn reservation ledger | `Common/Models/RuntimeWeaponAmmoSpec.cs`, `Common/Runtime/RuntimeSpawnBudget.cs`; native shot и event child — разные lanes |
| Hitbox curve / raw JSON numeric admission | `Common/Models/RuntimeProgramSpec.cs`, `RawJsonNumericDomain.cs` в том же directory, `Content/Projectiles/GeneratedProjectile.Executors.cs` |
| VFX DTO/rendering | `Common/Models/VfxManifestSpec.cs`; [VFX owners](ModSources/InfiniCrafterLocal/Common/VFX/FOLDER_DOCS_RU.md) |
| Station lanes/world journal | `Common/Players/InfiniCraftPlayer.MultiDev.cs`, `Common/Systems/GeneratedStationEscrowStateSystem.cs` |
| Placed-item world returns | `Common/Systems/GeneratedPlacementLedgerSystem.cs` |
| Shared limits/packet IDs | `Common/InfiniRuntimeLimits.cs`, `Common/InfiniNetPacketIds.cs` |

<a id="projections"></a>
## Generated поверхности и gates

`contracts/schemas/` — provider exports; [lowery.md](lowery.md), [inventory](docs/LOW_LEVEL_CAPABILITY_INVENTORY_RU.md), [lowering audit](TECHNICAL_LOWERING_AUDIT_RU.md), [primitive parity](docs/PRIMITIVE_PARITY_RU.md) — проверяемые проекции, не ручные registries. Генераторы `tools/generate_lowery.py`, `generate_low_level_runtime_docs.py`, `generate_equipment_bounds.py`, `generate_primitive_parity.py` обслуживают соответствующие outputs.

Канонический [data flow](docs/THREE_STAGE_LLM_PIPELINE_RU.md#flow) не имеет weapon IR fallback. Новая механика требует [полного vertical slice](docs/ADDING_RUNTIME_CAPABILITY_FOR_AGENTS_RU.md#vertical-slice), включая consumer и witness; изменение только prompt, schema или C# не завершает capability.
