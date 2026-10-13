# LocalGenerator — 0.5.00

Python HTTP-сервис генерации и локальный браузерный **Infinicraft Studio**. Для обычного запуска открой **`OPEN_INFINICRAFT.bat` в корне проекта**: [пошаговая инструкция](../docs/user/START_RU.md). Мод и image/text servers устанавливаются отдельно; готовые модели не скачиваются автоматически.

## Граница сервиса

`server.py` и `settings_gui.py` — launcher entrypoints. HTTP wiring живёт в `infini_local/web/server.py`, GUI — в `infini_local/desktop/`. Baseline: Gameplay Author → Visual Director → VFX Director → обязательные PNG/delivery; Repair условен и frozen-first. Семантического classifier/family router/legacy cache importer нет.

## Владельцы

- [Настройки и эксплуатация](../docs/user/SETTINGS_RU.md), [точный runbook](../docs/user/OPERATIONS_RU.md): `config.env`, environment priority и restart.
- [Карта кода](../docs/development/CODE_MAP_RU.md#python), [архитектура](../docs/development/ARCHITECTURE_RU.md), [offline QA](QUICK_START_RU.md).
- [Generated grammar/catalog](../docs/reference/GENERATED_RU.md): bounds берутся из source, не ручного списка в README.
- `data/` — входные rows; `/infinidump` даёт реальные loaded Terraria данные. Overrides — `INFINI_ITEMS_RUNTIME_DUMP`/`INFINI_PROJECTILES_RUNTIME_DUMP`.
- `cache/` (`INFINI_CACHE_DIR`) — traces/PNG; world-scoped recipes — `INFINI_WORLD_RECIPES_DIR`. Не подменяй world scope глобальным importer.
- OAuth хранится в пользовательском Python profile, не `config.env`: [сессия и ограничения](../docs/user/CODEX_IMAGE_OAUTH_RU.md).

Обновляй мод/генератор вместе и сохраняй личные данные. Старые PNG не перерисовываются автоматически. [Лицензия](../LICENSE).

<a id="данные-и-настройки"></a>
- [Данные и настройки](../docs/user/SETTINGS_RU.md).
