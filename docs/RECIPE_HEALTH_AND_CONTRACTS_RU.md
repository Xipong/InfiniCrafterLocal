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

Нет monolithic index.json/health.json; debug views читают recipe files по запросу. Per-file lock + temp/write/flush/fsync/replace обеспечивают atomic replacement; directory fsync — best effort. Для cache hit чтение, полная runtime/visual/VFX/delivery assessment и возможный quarantine находятся под **одной per-file блокировкой**: устаревшая проверка не может убрать новый commit. Наличие файла само по себе не означает GREEN.

Fresh commit разрешён только после трёх accepted stages, image delivery, final runtime/VFX/stage gates, sanitize и повторного cached-payload check ([pipeline](THREE_STAGE_LLM_PIPELINE_RU.md#flow)). Recipe authority не равна station escrow/placed-item return ledger: их [world ownership](../PROJECT_ARCHITECTURE_RU.md#profiles-world) отдельна.

<a id="health"></a>
## Что health доказывает

`contractVersions` — версионные stamps от [contract_versions.py](../LocalGenerator/infini_local/core/contract_versions.py), не proof runtime execution. `recipeHealth` схемы `infini.recipe-health.runtime-program.v2` наблюдает accepted typed wire: runtime shape, required visual slots/assets, finite VFX, deliverability, stage accounting, bounded warnings/problems. Status `healthy|warning|blocked` — результат этих gates, не оценка gameplay/art quality.

Delivery projection удаляет internal `_llmHistory`, compile caches, `visualKit` и `runtimeContract`, ограничивает nested DTO keys и debug strings; это объявленная transport projection, не design repair. Internal receipts нужны в compile audit, но не обязательны в final C# DTO.

<a id="diagnostics"></a>
## Debug routes и grey zones

Отдельный inspector UI сейчас не нужен: это не компонент runtime и не дополнительный LLM-проверяющий. Для разбора сохранённого результата остаются [dump/debug-команды](../command.md), trace стадий, contract/health views и offline replay. Панель имеет смысл добавлять только под конкретный неудобный сценарий диагностики; она должна читать этих же владельцев данных, а не вводить второе состояние, собственные правила gameplay или новый обязательный model pass.

`/debug/recipes` (50 записей), `/debug/recipe_health` (100), `/debug/latest_recipe` и `/debug/contracts` сначала сортируют file metadata, затем читают необходимые JSON bodies. Обычная выборка не декодирует весь архив; unreadable recipes пропускаются, а отсутствие health/stamps может потребовать дополнительных чтений. Обход metadata остаётся O(N), это не постоянный индекс и не O(1) поиск. `/debug/worlds` (`healthCounts`) по-прежнему сканирует все recipes для точных агрегатов. Route owner — [server_utility_routes.py](../LocalGenerator/infini_local/web/server_utility_routes.py). `/health` может публиковать tModLoader grey-zone notes (held item/holdout/net state): они диагностические, не gameplay router. Ни health, ни stamps не доказывают render/world loop/MP delivery; для этого нужны отдельно выполненные checks.
