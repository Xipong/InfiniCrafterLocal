# Strict world recipes, contract stamps и health

<a id="storage"></a>
## Хранилище и commit boundary

Owners: [world_recipe_runtime.py](../LocalGenerator/infini_local/storage/world_recipe_runtime.py) — cache identity/strict v5 validation; [world_storage.py](../LocalGenerator/infini_local/storage/world_storage.py) — atomic files, sanitize и derived health. Старые AttackSpec/family/runtimePlan payload не импортируются и не чинятся migration-путём.

В `LocalGenerator/cache/world_recipes/world_<id>/`:

| Path | Authority |
|---|---|
| `manifest.json` | Маленькая world metadata; rewrite только при изменении stable fields (имя/app/storage/runtime version), не каждый craft |
| `recipes/<recipe_key>.json` | Единственный authoritative recipe file с generated data, parents/world metadata и diagnostic stamps/health |
| `invalid/` | Quarantine unreadable/rejected recipes с причиной; не автоматическая migration |

Нет monolithic index.json/health.json; debug views сканируют recipe files по запросу. Per-file lock + temp/write/flush/fsync/replace обеспечивают atomic replacement; directory fsync — best effort. Cache hit также проходит current runtime/visual/VFX/delivery gates; invalid cache quarantined, не GREEN из-за наличия файла.

Fresh commit разрешён только после трёх accepted stages, image delivery, final runtime/VFX/stage gates, sanitize и повторного cached-payload check ([pipeline](THREE_STAGE_LLM_PIPELINE_RU.md#flow)). Recipe authority не равна station escrow/placed-item return ledger: их [world ownership](../PROJECT_ARCHITECTURE_RU.md#profiles-world) отдельна.

<a id="health"></a>
## Что health доказывает

`contractVersions` — версионные stamps от [contract_versions.py](../LocalGenerator/infini_local/core/contract_versions.py), не proof runtime execution. `recipeHealth` схемы `infini.recipe-health.runtime-program.v2` наблюдает accepted typed wire: runtime shape, required visual slots/assets, finite VFX, deliverability, stage accounting, bounded warnings/problems. Status `healthy|warning|blocked` — результат этих gates, не оценка gameplay/art quality.

Delivery projection удаляет internal `_llmHistory`, compile caches, `visualKit` и `runtimeContract`, ограничивает nested DTO keys и debug strings; это объявленная transport projection, не design repair. Internal receipts нужны в compile audit, но не обязательны в final C# DTO.

<a id="diagnostics"></a>
## Debug routes и grey zones

`/debug/recipe_health`, `/debug/contracts`, `/debug/worlds` (`healthCounts`) — derived views из сохранённых recipes; route owner — [server_utility_routes.py](../LocalGenerator/infini_local/web/server_utility_routes.py). `/health` может публиковать tModLoader grey-zone notes (held item/holdout/net state): они диагностические, не gameplay router. Ни health, ни stamps не доказывают render/world loop/MP delivery; для этого нужны отдельно выполненные checks.
