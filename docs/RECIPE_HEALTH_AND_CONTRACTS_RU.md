# Recipe Health + contract stamps

Этот патч не чинит старые рецепты и не меняет авторство ЛЛМ. Он добавляет диагностический слой вокруг новых рецептов, чтобы быстро отличать:

- recipe committed, но визуал частично слабый;
- runtimePlan валиден, но child/projectile/impact роли не совпали с ожиданием;
- ассеты доехали/не доехали;
- каким prompt/runtime/visual contract был создан предмет.

## Что пишется в рецепт

Новые рецепты получают:

- `contractVersions` — app/runtime/recipe/visual/planner stamps;
- `recipeHealth` — компактный статус по runtime, visual slots, VFX и asset sync.

## Что пишется в мир

В `LocalGenerator/cache/world_recipes/world_<id>/` используются:

- `manifest.json` — маленькая мета мира; переписывается только при изменении имени мира, версии приложения или формата хранения;
- `recipes/<recipe_key>.json` — единственный authoritative-файл предмета, внутри которого уже лежат `contractVersions`, `recipeHealth`, родители и world metadata;
- `invalid/` — карантин нечитаемых или отвергнутых recipe-файлов с отдельной причиной.

Монолитные `index.json` и `health.json` больше не создаются. Debug-представления строятся по `recipes/*.json` только при запросе debug endpoint, поэтому обычный крафт после создания manifest атомарно заменяет только файл самого изменённого рецепта.

## Debug endpoints

- `/debug/recipe_health` — последние health строки, производные от authoritative recipe-файлов;
- `/debug/contracts` — последние contract stamps, найденные сканированием сохранённых рецептов;
- `/debug/worlds` — теперь показывает `healthCounts`.

## tModLoader grey zones

В `/health` добавлены заметки по серым зонам tModLoader: held item, holdout offset, projectile rotation/net state. Они диагностические и не роутят gameplay.
