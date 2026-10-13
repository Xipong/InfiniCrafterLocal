# Документация Infinicraft — 0.4.254

**Рабочее дерево подготовки к альфе, не опубликованный релиз.** Начни с задачи. Source/registry/schema задают контракт; документация объясняет его, не создаёт второй runtime.

| Тебе нужно | Главный документ-владелец |
|---|---|
| Установить, настроить и сделать первый предмет | [Быстрый старт](user/START_RU.md) |
| Выбрать модели и обработку PNG | [Настройки](user/SETTINGS_RU.md) |
| Проверить запуск, найти ошибку и логи | [Диагностика](user/DIAGNOSTICS_RU.md) |
| Играть с друзьями | [Мультиплеер](user/MULTIPLAYER_RU.md) |
| Обновиться без потери личных данных | [Обновление](user/UPDATING_RU.md) |
| Найти игровую команду | [Команды](user/COMMANDS_RU.md) |
| Менять код, собирать и проверять | [Центр разработки](development/README_RU.md) |
| Найти точный authored/wire/runtime контракт | [Справка](reference/README_RU.md), [generated projections](reference/GENERATED_RU.md) |
| Проверить старое решение или замер | [Архив](archive/README_RU.md) |
| Найти замену старому пути | [Миграция и владельцы](development/DOCUMENTATION_RU.md) |

## Структура и ответственность

- `docs/user/` — путь игрока/оператора: один установочный сценарий, эксплуатация, настройки, MP и диагностика.
- `docs/development/` — архитектура, canonical code owners, изменение контрактов, сборка и границы тестов.
- `docs/reference/` — тематические технические ограничения и внешние справочники; не руководство по установке.
- `docs/archive/` — датированные аудиты, эксперименты и прежние release notes. Старый PASS/count не текущая приёмка.

Стабильные generated файлы остаются на прежних путях: [lowery](../lowery.md), [capability inventory](LOW_LEVEL_CAPABILITY_INVENTORY_RU.md), [machine-readability audit](CAPABILITY_LIBRARY_MACHINE_READABILITY_AUDIT_RU.md), [lowering audit](../TECHNICAL_LOWERING_AUDIT_RU.md), [primitive parity](PRIMITIVE_PARITY_RU.md). Полный каталог не редактируется вручную.

Корневые и LocalGenerator `PROJECT_*.md`/`QUICK_START_RU.md`, а также точечные legacy входы в `docs/` служат короткими маршрутами. `FOLDER_DOCS_RU.md` объясняют локальные каталоги. Лицензионные тексты остаются на месте: [LICENSE](../LICENSE), [перевод](../LICENSE_RU.md).
