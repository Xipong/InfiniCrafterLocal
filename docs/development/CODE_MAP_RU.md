# Карта исходников

[Архитектура](ARCHITECTURE_RU.md) объясняет поток, [MODULES](MODULES_RU.md) — рабочие ограничения, [OWNERS](OWNERS_RU.md) — выбор файла по задаче. Ниже реальное дерево, не список предполагаемых слоёв. `GeneratedItemData`, `GeneratedItem`, `GeneratedProjectile` и ledger остаются partial types; перемещение исходника не создаёт API.

<a id="tree"></a>
## Репозиторий

```text
LocalGenerator/                 Python приложение, bootstrap, data, tests
  infini_local/
    core/runtime_authoring/     canonical gameplay contract
    pipelines/                  LLM стадии и транспорт
    services/ + web/            HTTP, assets, backend boundaries
    storage/                    world recipes, health, traces
    desktop/ + desktop/webui/   Studio и native controller
    qa/                         offline witnesses/audits
ModSources/InfiniCrafterLocal/   tModLoader executor
  Common/Models/                Contracts / Runtime / Presentation
  Common/Runtime/               bindings, events, delays, budgets
  Common/Services/              Generation / Assets / Networking
  Common/Players/               station и per-player state
  Common/Systems/               Craft / Placement / Combat / Presentation / Utility
  Common/VFX/                   finite renderer/lifecycle/peer stream
  Common/UI/                    station drawing/input
  Content/Items/ + Projectiles/ shared per-instance proxies
  Assets/ + Localization/       bundled resources и EN/RU HJSON
contracts/                      schemas, config registry, saved reports
tools/                          development gates/build/replay; windows/ BAT helpers
toolbox/                        отдельно разрешаемый live harness + offline tests
docs/                           user / development / reference / archive
.agent/ + .github/               impact metadata и CI, не игровой runtime
```

`OPEN_INFINICRAFT.bat` — пользовательский launcher. `LocalGenerator/scripts/bootstrap.py` владеет setup/gui/server/doctor; `LocalGenerator/server.py` и `settings_gui.py` не используются как import barrels. Cache, `.venv`, `bin`/`obj`, build logs и workspace indexes не являются canonical source.

<a id="python"></a>
## Python

**Все пути таблицы — относительно `LocalGenerator/infini_local/`.** Когда owner относится к нескольким файлам, directory указан для каждого; не нужно угадывать контекст соседней строки.

| Решение | Файлы |
|---|---|
| Capability facts, grammar, params/units, events/producers | `core/runtime_authoring/capability_registry.py` |
| Strict Author/Repair shape | `core/runtime_authoring/program_schema.py` |
| Exact Repair mutable IDs/indices/create policy | `core/runtime_authoring/repair_scope.py`; shared merge `core/repair_merge.py` |
| Composition/slots/budgets/binding admission | `core/runtime_authoring/validator.py`, `core/runtime_authoring/event_producer_validation.py`, `core/runtime_authoring/binding_use_policy.py` |
| Component/opcode projection, receipts, final wire | `core/runtime_authoring/compiler.py`, `core/runtime_authoring/technical_lowering.py`, `core/runtime_authoring/wire_validator.py` |
| Finite Terraria/tML mappings | `core/runtime_authoring/terraria_vocabulary.py` |
| Model-facing cards/prompt и Author calls | `pipelines/author_item_contract.py`, `pipelines/llm_authoring_prompt.py`, `pipelines/llm_authoring_pipeline.py` |
| Whole craft/stage orchestration | `pipelines/combine_pipeline.py`; numeric advice `pipelines/combine_balance.py` |
| Request-local HTTP admission/response | `services/combine_endpoint.py`, `web/server_handler.py`, `web/http_response_helpers.py` |
| Provider profile lease, quota, retry, Responses | `pipelines/llm_transport.py`, `core/llm_config.py`, `services/codex_auth.py`, `services/codex_text_backend.py` |
| Explicit stage/cache packet framing | `core/llm_prompt_cache.py`, `core/llm_stage_messages.py`, соответствующий stage request builder |
| Visual, image attempts, delivery gate | `pipelines/visual_generation_pipeline.py`, `pipelines/visual_sprite_generation.py`, `pipelines/visual_delivery_gate.py`, `services/visual_asset_pipeline.py` |
| VFX entity/event contract + materials | `core/vfx_manifest.py`, `core/vfx_material_contract.py` |
| Asset serving и optional sd.cpp lifecycle | `services/asset_sync_service.py`, `services/sdcpp_service.py`, `services/sdcpp_backend.py`, `web/server_utility_routes.py` |
| World recipe API/storage, failure/trace evidence | `storage/world_recipe_runtime.py`, `storage/world_storage.py`, `storage/failure_state.py`, `storage/trace_runtime.py`, `storage/trace_tools.py` |
| Studio shell/browser/native state | `desktop/web_studio.py`, `desktop/webui/index.html`, `desktop/webui/studio.css`, `desktop/webui/studio.js`; [native split](MODULES_RU.md#studio) |
| Canonical settings/persistence/lifecycle | `desktop/settings_schema.py`, `desktop/settings_env.py`, `desktop/settings_gui_trace_state.py`, `desktop/settings_gui_server_controls.py` |
| Offline fixtures/witnesses/library and consumer proof | `qa/runtime_program_fixtures.py`, `qa/capability_witnesses.py`, `qa/capability_library_audit.py`, `qa/runtime_program_proof.py`, `qa/primitive_loss_audit.py` |

Fresh Author принимает только `authoring.v5`: flat `action`/`stackCost`/`contactDamage`, registry-fixed branches и unique item-body identity. Nested source `usePolicy`, v4 и compact API не являются fresh admission. **Persisted wire** сохраняет `usePolicy` и отдельную provenance: retirement Author grammar не удаляет recipes. Public runtime imports — `infini_local.core.runtime_authoring`, не deleted legacy compiler/root lowerers.

<a id="csharp"></a>
## C#

**Все пути таблицы — относительно `ModSources/InfiniCrafterLocal/`.**

| Решение | Файлы |
|---|---|
| Strict DTO/JSON/domain/vocabulary | `Common/Models/Contracts/RuntimeProgramSpec.cs`, `Common/Models/Contracts/GeneratedItemData.cs`, `Common/Models/Contracts/GeneratedItemData.Model.cs`, `Common/Models/Contracts/GeneratedItemData.Normalize.cs`, `Common/Models/Contracts/RawJsonNumericDomain.cs`, `Common/Models/Contracts/TerrariaRuntimeVocabulary.cs` |
| Item projection/debug/generated bounds | `Common/Models/Runtime/GeneratedItemData.Apply.cs`, `Common/Models/Runtime/GeneratedItemData.Debug.cs`, `Common/Models/Runtime/GeneratedEquipmentBounds.g.cs` |
| Bindings/events/delays | `Common/Runtime/RuntimeProgramExecutor.cs`, `Common/Runtime/RuntimeDelayedActionScheduler.cs` |
| Child/root spawn, distributions, target geometry | `Common/Runtime/RuntimeSpawnBudget.cs`, `Common/Runtime/RuntimeSpawnVelocity.cs`, `Common/Runtime/RuntimeSpawnTransform.cs`, `Common/Runtime/RuntimeHitTargetSpawn.cs` |
| Owner-hit/generation fencing | `Common/Runtime/RuntimeHitNpcGeneration.cs`, `Common/Runtime/RuntimeHitPullBridge.cs` |
| Item use/save/net/equipment + native prefix/root/tooltip | `Content/Items/GeneratedItem.cs`, `Content/Items/GeneratedItem.UseStyle.cs`, `Content/Items/GeneratedItem.PrefixLifecycle.cs`, `Content/Items/GeneratedItem.RootCombat.cs`, `Content/Items/GeneratedItem.Tooltips.cs` |
| Exact named effect groups / native ammo DTO | `Common/Models/Contracts/RuntimeItemEffectGroupSpec.cs`, `Common/Models/Contracts/RuntimeWeaponAmmoSpec.cs` |
| Entity bootstrap/controller/events/net/visual | `Content/Projectiles/GeneratedProjectile.cs`, `Content/Projectiles/GeneratedProjectile.Executors.cs`, `Content/Projectiles/GeneratedProjectile.RuntimeEvents.cs`, `Content/Projectiles/GeneratedProjectile.NetSync.cs`, `Content/Projectiles/GeneratedProjectile.Visuals.cs` |
| Station input/jobs/MP/readiness | `Common/Players/InfiniCraftPlayer.Station.cs`, `Common/Players/InfiniCraftPlayer.CraftState.cs`, `Common/Players/InfiniCraftPlayer.MultiDev.cs`, `Common/Players/InfiniCraftPlayer.Multiplayer.cs` |
| Durable station escrow и world exit | `Common/Systems/Craft/GeneratedStationEscrowStateSystem.cs`, `Common/Systems/Craft/InfiniCraftWorldExitSystem.cs` |
| Placement/material claim + native admission | `Common/Systems/Placement/GeneratedPlacementLedgerSystem.cs` и его partials; `Common/Systems/Placement/GeneratedPlacedBodyNativeAdapter.cs`, `Common/Systems/Placement/GeneratedPlacedBodyNativeAdapter.Contracts.cs` |
| Native combat / quick utility | `Common/Systems/Combat/GeneratedRootCombatSystem.cs`, `Common/Systems/Utility/GeneratedQuickUseSystem.cs`, `Common/Runtime/GeneratedQuickUtilityActivation.cs` |
| Cursor/placed/held draw | `Common/Systems/Presentation/GeneratedCursorItemPresentationSystem.cs`, `Common/Systems/Presentation/GeneratedPlacedBodyDrawSystem.cs`, `Common/Players/GeneratedHeldItemDrawLayer.cs` |
| Definitions и generator HTTP | `Common/Services/Generation/GeneratedItemRegistryService.cs`, `Common/Services/Generation/GeneratorClient.cs` |
| PNG validation/chunks/queue/cache | `Common/Services/Assets/GeneratedAssetSyncService.cs`, `Common/Services/Assets/GeneratedTransferSystem.cs`, `Common/Services/Assets/RuntimeSpriteCache.cs` |
| Authority predicates / HTTP cooldown | `Common/Services/Networking/InfiniRuntimeAuthority.cs`, `Common/Services/Networking/LocalHttpQuietFailure.cs` |
| Sprite geometry / typed VFX | `Common/Models/Presentation/SpritePresentation.cs`, `Common/Models/Presentation/VfxManifestSpec.cs`; [VFX split](MODULES_RU.md#vfx) |
| Limits, packet IDs, Terraria sentinels | `Common/InfiniRuntimeLimits.cs`, `Common/InfiniNetPacketIds.cs`, `Common/InfiniTerrariaSentinels.cs` |
| Station UI и localization | `Common/UI/InfiniCraftStationUISystem.cs`, `Localization/en-US_Mods.InfiniCrafterLocal.hjson`, `Localization/ru-RU_Mods.InfiniCrafterLocal.hjson` |
| Heart/proxies/config/diagnostics | `Content/Items/InfiniCore.cs`, `Content/Items/GeneratedArmorItems.cs`, `Common/Config/InfiniGameplayQolConfig.cs`, `Common/Config/InfiniVfxClientConfig.cs`, `Common/Commands/`, `Common/Systems/Diagnostics/InfiniAgentContractSelfTestSystem.cs` |

<a id="projections"></a>
## Generated outputs и проверки

[GENERATED](../reference/GENERATED_RU.md) связывает outputs с producer/refresh. Главные пары:

| Producer в `tools/` | Output |
|---|---|
| `generate_lowery.py` | Только [LOWERY](../reference/generated/LOWERY_RU.md) |
| `generate_low_level_runtime_docs.py` | [capability inventory](../reference/generated/LOW_LEVEL_CAPABILITY_INVENTORY_RU.md), [machine-readability audit](../reference/generated/CAPABILITY_LIBRARY_MACHINE_READABILITY_AUDIT_RU.md), [technical audit](../reference/generated/TECHNICAL_LOWERING_AUDIT_RU.md) |
| `audit_capability_library.py` | JSON verdict в stdout; optional `--out` записывает выбранный report, не generated Markdown |
| `generate_primitive_parity.py` | [primitive parity](../reference/generated/PRIMITIVE_PARITY_RU.md) |
| `generate_equipment_bounds.py` | `Common/Models/Runtime/GeneratedEquipmentBounds.g.cs` относительно C# base |
| `export_contract_schemas.py` | strict Author/Repair/Visual/VFX schema exports и inventory manifests в `contracts/schemas/` |
| `config_registry.py` | `contracts/config_registry.json` |

Behavioral owners — [TESTING](TESTING_RU.md); native roster — `tools/EngineRuntimeChecks.cs` + `.csproj`; saved replay — `tools/replay_generation_case.py`; impact/tooling — `tools/agentctl.py`, `.agent/manifest.json`, `.agent/impact_rules.json`. Source path существующего файла не является доказательством native/world/GPU приёмки.
