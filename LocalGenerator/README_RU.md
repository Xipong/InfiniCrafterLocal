# LocalGenerator v0.4.250

Python HTTP-сервис генерации и Tk GUI настроек. [Единый setup/runbook](../QUICK_START_RU.md) владеет установкой, providers, запуском и MP; [offline QA](QUICK_START_RU.md) — проверкой checkout. Парная поставка 0.4.250 включает явную placed-body capability и полную sanitized stage-request diagnostics, а также OpenRouter upstream pin, safe restart/effective-config diagnostics и Codex effective-wire cache/prefix refinements; старый опубликованный ZIP 0.4.246 их не содержит. Обновляй генератор вместе с модом, сохраняя `config.env`, cache, recipes/PNG и данные миров. Новая held-body/collision guidance относится к будущей генерации, а не к исправлению старых рисунков.

## Граница сервиса

`server.py` — launcher; `infini_local/web/server.py` — HTTP wiring, `settings_gui.py` — GUI launcher. Baseline: Gameplay Author → Visual Director → VFX Director, затем PNG/delivery. Repair условен для собственного отвергнутого domain; никакого classifier pass, whole-weapon macro или импорта legacy cache.

Author получает полный компактный каталог один раз. `runtimeProgram` v5 ограничен 12 entities, 8 bindings, 48 calls и child depth 3; текущая grammar/catalog принадлежит [generated inventory](../docs/LOW_LEVEL_CAPABILITY_INVENTORY_RU.md), авторские правила — [lowery](../lowery.md). Числа capabilities не являются настройкой сервера.

## Данные и настройки

- `config.env` — личный GUI/manual конфиг; [example](config.example.env) содержит примеры путей. Process environment имеет приоритет; настройки перечитываются при старте.
- `data/` — входные данные. `/infinidump` даёт реальные loaded Terraria rows; explicit overrides — `INFINI_ITEMS_RUNTIME_DUMP` и `INFINI_PROJECTILES_RUNTIME_DUMP`.
- `cache/` (`INFINI_CACHE_DIR`) — traces и PNG `sprites/`; `world_recipes/` (`INFINI_WORLD_RECIPES_DIR`) — world-scoped рецепты. Не коммить личный cache и не подменять world scope глобальным importer.
- OAuth принадлежит профилю пользователя Python, не `config.env`: [Codex auth](../docs/CODEX_IMAGE_OAUTH_RU.md).

[Транспорт/лимиты](../docs/LLM_TRANSPORT_REQUEST_SHAPE_RU.md) · [prompt cache/latency](../docs/LLM_PROMPT_CACHE_AND_LATENCY_RU.md) · [OpenRouter pin](../docs/OPENROUTER_ROUTING_RU.md) · [image lifecycle](../docs/IMAGE_ASSET_LIFECYCLE_RU.md).
