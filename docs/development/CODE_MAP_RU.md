# Карта исходников

[Архитектура](ARCHITECTURE_RU.md) объясняет поток, [MODULES](MODULES_RU.md) — рабочие ограничения, [OWNERS](OWNERS_RU.md) — выбор файла по задаче. Ниже реальное дерево, не список предполагаемых слоёв. `GeneratedItemData`, `GeneratedItem`, `GeneratedProjectile` и ledger остаются partial types; перемещение исходника не создаёт API.

<a id="fast-start"></a>
## Быстрый вход: симптом → цепочка → проверка

Не начинай с обхода всего репозитория. Выбери строку ниже, открой названный **entrypoint**, затем следуй его реальным вызовам. Python-пути здесь относительно `LocalGenerator/infini_local/`, C# — относительно `ModSources/InfiniCrafterLocal/`. Названия symbols удобнее номеров строк: строки меняются при обычных правках. Сохранённый рецепт/trace ищи в **фактически запущенном генераторе**, не среди WSL campaign artifacts.

| Симптом / вопрос | Начало и ближайшая цепочка | Минимальная проверка |
|---|---|---|
| «Где Author отклонён, когда разрешён Repair и что проверяется после него?» | `pipelines/gameplay_stage.py::compile_and_validate_authored_runtime` содержит stage-level validation/compile/wire/retry lifecycle. Для exact diagnostic следуй прямому import в `core/runtime_authoring/`; request самого Repair — `pipelines/llm_authoring_pipeline.py::repair_author_item_after_failure` | `test_low_level_three_stage_pipeline.py`, `test_repair_frozen_contract.py`, `test_generation_budgets.py`; labels, failure cutoff, одна Repair попытка |
| «Родительские native facts различаются в нескольких местах request» | `Common/Services/Generation/GeneratorClient.cs::ToWireItem` → `CaptureParentNativeFacts` → root / `FingerprintFromItem` / nested runtimeFacts; shared native field записывается один раз | `tools/EngineRuntimeChecks.ParentFacts.cs`; exact envelope keys/types/null/zero, prefix, generated placement, player/reference ammo |
| «Не хватает полного запроса / ответа / HTTP / SSE» | `storage/trace_runtime.py::trace_stage_request/trace_codex_transport/flush_codex_transport` → `storage/trace_tools.py::persist_stage_request/persist_transport_artifact/trace_event`; native wire: `services/codex_text_backend.py::generate_chat` → `services/codex_auth.py::post_sse/_generation_request/_read_sse_response` → `core/http_io.py::urlopen_no_redirect`; image joins: `pipelines/visual_sprite_generation.py::_execute_image_request` → `pipelines/image_backend_pipeline.py::generate_openai_codex` → `services/codex_image_backend.py::generate_image` | `LocalGenerator/tests/test_codex_transport_trace.py`, `test_image_transport_join.py`, `test_full_logging_contract.py`; actual artifacts/identity/toggle/flush, не только UI tail |
| «Кэш промпта не работает / craft долго» | Author: `pipelines/llm_authoring_pipeline.py::build_initial_author_request`; Visual: `pipelines/visual_generation_pipeline.py::_request_visual_kit`; VFX: `core/vfx_manifest.py::_request` → `pipelines/vfx_generation_pipeline.py::call_llm_vfx_director` → `core/llm_prompt_cache.py::with_instruction_segments` → `pipelines/llm_transport.py` → provider adapter | `test_craft_instruction_segments.py`, `test_codex_static_instruction_prefix.py`, `test_visual_vfx_prompt_prefix.py`; отдельно cached/input counters, logical/physical calls и image time |
| «Repair трогает правильный соседний узел / зависимость» | `core/runtime_authoring/validator.py` даёт exact error → `repair_scope.py::build_runtime_repair_scope/filter_repair_patch_scope` → `core/repair_merge.py`; реальные callers: `pipelines/llm_authoring_pipeline.py`, Visual `_request_visual_kit`, VFX `_request` | `test_repair_gameplay_contract.py`, `test_repair_frozen_contract.py`; sole/shared child: `test_referenced_entity_requirements.py`, `test_hit_target_spawn.py` |
| «Эффект предмета не срабатывает / альт даёт бесконечный баф» | **Будущая генерация:** `pipelines/author_item_contract.py::author_item_prompt_shape_card` (concept.coreMechanic uptime/cost) → `capability_registry.py` (`apply_generated_buff_on_use` refresh/duration/Spelunker scope) → `llm_authoring_pipeline.py::build_initial_author_request`. **Исполнение:** `Content/Items/GeneratedItem.cs::ActiveUseBinding/CanUseItem/UseItem/ApplyItemEffects` → `Common/Players/InfiniCraftPlayer.Mobility.cs::ApplyGeneratedUtilityBuff/ApplyGeneratedUtilityBuffEffects`; native quick use отдельно: `Common/Systems/Utility/GeneratedQuickUseSystem.cs` | `test_author_prompt_clarity.py`, `test_item_effect_groups.py`; native `tools/EngineRuntimeChecks.NamedItemEffects.cs`, `.QuickUse.cs`, `.QuickUtilityActivation.cs`; сначала exact binding/effectGroup/stackCost, не имя предмета; duration ≠ activation КД |
| «Предметная усталость / копией обходится баф / не хватает отдельных иконок» | Author `apply_generated_buff_on_use.params.exhaustionTicks` → `compiler.py`/`technical_lowering.py` → nullable `GeneratedBuffSpec.ExhaustionTicks`. Consumer: `InfiniCraftPlayer.Mobility.cs::ApplyGeneratedUtilityBuff` → `.Exhaustion.cs::CanApplyGeneratedBuff/CaptureGeneratedItemExhaustion`; callers: `GeneratedItem.cs::ApplyItemEffects/RefreshHeldEffectGroup`, `GeneratedQuickUtilityActivation.cs` Commit. Снимок v5: `.Multiplayer.cs`; UI: `GeneratedItemExhaustionStatusView`, `GeneratedUtilityBuffUISystem` | `test_generated_buff_exhaustion.py`; native `.Exhaustion.cs`, `.ExhaustionPresentation.cs`; только generated-баф, player + ID + definition hash, omission/0 без таймера, не общий attack КД |
| «Кирка медленно начинает добычу» | `Common/Models/Runtime/GeneratedItemData.Apply.cs::ApplyToItem` → `GeneratedItem.cs::CanUseItem/UseItem/HoldItem`; сравнить `useTime/useAnimation/reuseDelay/pickSpeed` с actual `Item.SetDefaults` и `items_runtime_dump.jsonl`; native граница — `Player.ItemCheck_UseMiningTools` | `tools/EngineRuntimeChecks.GeneratedItemPrefix.cs`, `.Player.cs`; интервал взмаха не равен задержке первого попадания, `noMelee` не выключает mining |
| «Оружие не в руке / кривой thrust / pivot» | **Item-body PNG:** `Common/Players/GeneratedHeldItemDrawLayer.cs::Draw/HeldSpriteOrigin` + `Content/Items/GeneratedItem.UseStyle.cs::UseStyle`. **Explicit hand body:** `Content/Projectiles/GeneratedProjectile.FrontHand.cs::MoveFrontHand/TryProjectFrontHandUseStyle` → `.Visuals.cs::PreDraw` → `Common/Models/Presentation/SpritePresentation.cs::Entity/ProjectileOrigin`. **Legacy code19:** `.Executors.cs::ForwardRetract`, не hand attachment | `tools/EngineRuntimeChecks.FrontHand.cs`, `.HeldProxy.cs`, `.BodyGeometry.cs`; Author/Visual join — `test_front_hand_wire_integration.py`; exact selected grip/axis, native H и collision C проверяются отдельно |
| «PNG здоров у генератора, но неверный в игре» | Python `services/asset_sync_service.py::runtime_asset_files/find_asset_file` + `pipelines/visual_delivery_gate.py::visual_delivery_report`; C# `Common/Services/Assets/GeneratedAssetSyncService.cs` → `RuntimeSpriteCache.cs` | `test_asset_transfer_cache_contracts.py`, `tools/EngineRuntimeChecks.AssetIdentity.cs`, `.AssetLifecycle.cs`; declared bytes/hash и выбранный cache source отдельно |
| «Где read-only статус бафа / tooltip?» | `Content/Items/GeneratedItem.Tooltips.cs`; active generated HUD: `Common/UI/GeneratedUtilityBuffUISystem.cs` + `GeneratedUtilityBuffStatusView.cs`; source snapshot: `Common/Players/InfiniCraftPlayer` | `tools/EngineRuntimeChecks.Tooltips.cs`; статус не должен добавлять vanilla buff или повторять effect execution |

### Короткий рабочий цикл агента

1. Открой [OWNERS](OWNERS_RU.md) для границы задачи и строку выше для entrypoint; [MODULES](MODULES_RU.md) нужен только для затронутого owner. Перед runtime-правкой выполни prerequisites из [AGENTS](../../AGENTS.md#перед-изменением-runtime).
2. Найди **symbol в указанном файле**, его caller и точный saved input. Расширяй поиск лишь если этот seam уходит в другой owner. Не читай целиком generated catalogs и все `artifacts/` ради одного метода.
3. Найди существующее behavioral test family в [TESTING](TESTING_RU.md). Native Compile roster — `tools/EngineRuntimeChecks.csproj`; invocation/filter roster — `tools/EngineRuntimeChecks.cs`. Новый файл без обеих регистраций не исполняется.
4. Для headless native запуска нужны actual tML/FNA и external DLL paths, private SavePath и **source-root cwd** для locale/fixture readers. Запускай точную свежесобранную DLL; успешный `dotnet build` не доказывает, что `dotnet run` выбрал её.
5. Для historical audit не называй builder messages exact HTTP wire; пустой physical-attempt list с unobserved owner — unknown, не «0 retries». Debug/manifest previews отдельно от полного сохранённого trace.

### Почему маршрут короче

Сравнение с baseline `6e4c901` относится к поиску владельца, а не к новому gameplay контракту:

| Задача | Раньше | Сейчас |
|---|---|---|
| Проследить stage-level Author admission, compile, wire gate и retry cutoff | `combine_pipeline` + `combine_validation` + `combine_gameplay` + `llm_authoring_pipeline` | Всё это в `gameplay_stage`; model request/Repair packet открывается отдельно только при необходимости |
| Изменить общий native parent fact | Три независимых поля в root, fingerprint и runtimeFacts | Одно поле в `CaptureParentNativeFacts`; envelopes явно добавляют/исключают только свои поля |
| Найти VFX provider request | Перейти из VFX в Gameplay Author helper | `vfx_generation_pipeline.call_llm_vfx_director` |
| Прочитать события/visual roles сохранённого wire | Импорт compiler через eager package barrel | Прямой `wire_views` без compiler и Repair |

Canonical registry → schema → validator → compiler → C# vertical slice намеренно сохраняется: эти owners отвечают на разные вопросы. Удалены именно случайные переходы, повторные field maps и пустые wrappers. Проверка import isolation/order — `test_runtime_import_boundaries.py`; она не заменяет behavior tests.

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
| Craft stage lifecycle / commit | `pipelines/gameplay_stage.py` / `pipelines/combine_pipeline.py` |
| Read-only event/visual views accepted wire | `core/runtime_authoring/wire_views.py` |
| Model-facing cards/prompt и Author calls | `pipelines/author_item_contract.py`, `pipelines/llm_authoring_prompt.py`, `pipelines/llm_authoring_pipeline.py` |
| Selected sprite size/axis/grip dependencies | `core/visual_contract_schema.py::grip_schema/front_hand_sprite_errors`; Visual projection — `pipelines/visual_generation_pipeline.py`; strict optional-present DTO — `core/runtime_authoring/wire_validator.py::_validate_sprite_presentation` |
| Whole craft/stage orchestration | `pipelines/combine_pipeline.py`; numeric advice `pipelines/combine_balance.py` |
| Request-local HTTP admission/response | `services/combine_endpoint.py`, `web/server_handler.py`, `web/http_response_helpers.py` |
| Provider profile lease, quota, retry, Responses | `pipelines/llm_transport.py`, `core/llm_config.py`, `services/codex_auth.py`, `services/codex_text_backend.py` |
| Explicit stage/cache packet framing | `core/llm_prompt_cache.py`, `core/llm_stage_messages.py`, соответствующий stage request builder |
| Visual, image attempts, delivery gate | `pipelines/visual_generation_pipeline.py`, `pipelines/visual_sprite_generation.py`, `pipelines/visual_delivery_gate.py`, `services/visual_asset_pipeline.py` |
| VFX entity/event contract + materials | `core/vfx_manifest.py`, `core/vfx_material_contract.py` |
| Asset serving и optional sd.cpp lifecycle | `services/asset_sync_service.py`, `services/sdcpp_service.py`, `services/sdcpp_backend.py`, `web/server_utility_routes.py` |
| World recipe API/storage, failure/trace evidence | `storage/world_recipe_runtime.py`, `storage/world_storage.py`, `storage/failure_state.py`, `storage/trace_runtime.py`, `storage/trace_tools.py` |
| Studio shell/browser/native state | `desktop/web_studio.py`, `desktop/webui/index.html`, `desktop/webui/studio.css`, `desktop/webui/studio.js`; [native split](MODULES_RU.md#studio) |
| Canonical generation recommendations / selective consent | `core/generation_defaults.py`, `core/llm_config.py`, `core/vfx_manifest_config.py`; `desktop/settings_defaults.py` → `web_studio.py`/`webui/studio.js` |
| Canonical settings/persistence/lifecycle | `desktop/settings_schema.py`, `desktop/settings_env.py`, `desktop/settings_controller.py`, `desktop/studio_operations.py` |
| Offline fixtures/witnesses/library and consumer proof | `qa/runtime_program_fixtures.py`, `qa/capability_witnesses.py`, `qa/capability_library_audit.py`, `qa/primitive_loss_audit.py` |

Fresh Author принимает только `authoring.v5`: flat `action`/`stackCost`/`contactDamage`, registry-fixed branches и unique item-body identity. Nested source `usePolicy`, v4 и compact API не являются fresh admission. **Persisted wire** сохраняет `usePolicy` и отдельную provenance: retirement Author grammar не удаляет recipes. Runtime imports указывают на defining module (`...capability_registry`, `...compiler`, `...repair_scope` и т. д.). Package `runtime_authoring/__init__.py` пуст по зависимостям: import registry не импортирует compiler/Repair; Visual/VFX читают `wire_views.py` без Gameplay Author. Общий provider response-format helper находится в `core/llm_json_tools.py`, а не в чужой LLM-стадии.

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
| Explicit native front-hand body pose | `Content/Projectiles/GeneratedProjectile.FrontHand.cs::MoveFrontHand/TryProjectFrontHandUseStyle`; selected PNG origin — `Common/Models/Presentation/SpritePresentation.cs::ProjectileOrigin` |
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

### Projectile state: проверяй update и rehydration вместе

Native `AI` находится в `GeneratedProjectile.Executors.cs`; общие поля, `Configure` и повторная загрузка definition — в `GeneratedProjectile.cs`; `ReceiveExtraAI` — в `.NetSync.cs`; producer dispatch и hit/kill hooks — в `.RuntimeEvents.cs`. При изменении activation delay, age или once-only event flag проследи обе ветви: fresh spawn → `Configure` → `AI` и `ReceiveExtraAI` → rehydrate с `preserveSyncedState` → `AI`. Поля одного partial type принадлежат общей lifecycle; чтение только controller не показывает reset/preserve семантику. Delayed actions дополнительно проходят source-incarnation guards и общий spawn budget в `Common/Runtime/`.

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
