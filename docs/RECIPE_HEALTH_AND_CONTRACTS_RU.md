# v0.4.174 — Recipe Health + contract stamps

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

В `LocalGenerator/cache/world_recipes/world_<id>/` теперь есть:

- `index.json` — как раньше, но recipe entry содержит компактное `health`;
- `health.json` — отдельный health-index по всем рецептам мира.

## Debug endpoints

- `/debug/recipe_health` — последние health строки по мирам;
- `/debug/contracts` — последние contract stamps из сохранённых рецептов;
- `/debug/worlds` — теперь показывает `healthCounts`.

## tModLoader grey zones

В `/health` добавлены заметки по серым зонам tModLoader: held item, holdout offset, projectile rotation/net state. Они диагностические и не роутят gameplay.
