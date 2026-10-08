# Документация InfiniCrafterLocal

**Начни с задачи, а не с исторического отчёта.** Сведения о релизе и локальных обновлениях — в [README](../README_RU.md). Контракт задают текущие source/registry/schema; документы объясняют их, но не создают альтернативный runtime.

## Запуск и эксплуатация

| Задача | Руководство |
|---|---|
| Установить и запустить | [Быстрый старт](../QUICK_START_RU.md), [LocalGenerator](../LocalGenerator/README_RU.md) |
| Собрать мод, подобрать reference paths | [Сборка](../BUILD_QOL_RU.md) |
| Найти команду оператора | [Команды](../command.md) |
| Выбрать конкретного upstream-провайдера | [Строгий OpenRouter pin](OPENROUTER_ROUTING_RU.md) |
| Подключить подписочный Codex image route | [OAuth и ограничения маршрута](CODEX_IMAGE_OAUTH_RU.md) |
| Разобраться с формой запросов и задержкой | [Transport/request contract](LLM_TRANSPORT_REQUEST_SHAPE_RU.md), [cache/latency](LLM_PROMPT_CACHE_AND_LATENCY_RU.md) |
| Проверить конкретный результат | [Recipe health](RECIPE_HEALTH_AND_CONTRACTS_RU.md) |

## Архитектура и изменение контрактов

| Решение | Канонический документ |
|---|---|
| Кто чем владеет и как идут данные | [Архитектура](../PROJECT_ARCHITECTURE_RU.md), [карта дерева](../PROJECT_MAP_RU.md), [задача → owner](../AGENT_INDEX_RU.md) |
| Какие правила нельзя ослаблять | [AGENTS.md](../AGENTS.md), [классы lowering](TECHNICAL_LOWERING_POLICY_RU.md) |
| Как Author составляет программу | [Low-level authoring](LOW_LEVEL_RUNTIME_AUTHORING_RU.md), [direct construction](AUTHOR_DIRECT_CONSTRUCTION_RU.md) |
| Где заканчиваются стадии и начинается Repair | [Author → Visual → VFX](THREE_STAGE_LLM_PIPELINE_RU.md), [exact-scope Repair](TARGETED_REPAIR_PROTOCOL_RU.md) |
| Когда omission эквивалентен нейтрали | [Declared neutral omissions](DECLARED_NEUTRAL_OMISSIONS_RU.md) |
| Какие единицы и числовые границы видит модель | [Model-facing units](MODEL_FACING_UNITS_RU.md), [баланс и progression](BALANCE_REFERENCE_VANILLA_PROGRESS_LIMITS_RU.md) |
| Как добавить возможность без shadow contract | [Полный vertical slice](ADDING_RUNTIME_CAPABILITY_FOR_AGENTS_RU.md) |
| Где находятся lifecycle, authority и persistence | [Engine runtime boundaries](ENGINE_RUNTIME_BOUNDARIES_RU.md), [tModLoader standardization](TERRARIA_TMODLOADER_STANDARDIZATION_RU.md) |

## Visual, VFX и ассеты

- [Качество контекста и source physics](ITEM_QUALITY_CONTEXT_RU.md) — exact parents, literal tooltips, motion reference и display pixel budget.
- [Presentation consistency](PRESENTATION_CONSISTENCY_RU.md) — согласованность gameplay, видимого тела и стадий.
- [Visual metadata](VISUAL_PRESENTATION_METADATA.md) — принятые поля и их ownership.
- [VFX materials](VFX_MATERIAL_ELEMENTS_RU.md) — материал, selector, geometry и bounded execution.
- [Image asset lifecycle](IMAGE_ASSET_LIFECYCLE_RU.md) — attempt ownership, публикация bytes, доставка и cache.

## Проверка и generated references

- [Исправления 0.4.251](BUGFIX_0_4_251_RU.md) — Repair, cache admission и native support/MP lifecycle; пары runtime/generator и пределы проверки.

[Владельцы тестовых контрактов](TEST_CONTRACT_OWNERS_RU.md) — единый runbook для regression/mutation/gates и границ доказательства. [Toolbox](../toolbox/README.md) отделяет offline checks от отдельно разрешаемых live-кампаний. CPU/headless, native GPU, игра/MP и художественная приёмка — разные уровни, не взаимозаменяемые отметки PASS.

| Generated документ | Producer |
|---|---|
| [lowery](../lowery.md) | [generate_lowery.py](../tools/generate_lowery.py) |
| [Capability inventory](LOW_LEVEL_CAPABILITY_INVENTORY_RU.md), [machine-readability audit](CAPABILITY_LIBRARY_MACHINE_READABILITY_AUDIT_RU.md), [lowering audit](../TECHNICAL_LOWERING_AUDIT_RU.md) | [generate_low_level_runtime_docs.py](../tools/generate_low_level_runtime_docs.py) |
| [Primitive parity](PRIMITIVE_PARITY_RU.md) | [generate_primitive_parity.py](../tools/generate_primitive_parity.py) |

У каждого generated документа есть команды обновления/`--check`. Его полный каталог не сокращают вручную и не копируют в соседние руководства. Эти три producer пишут только Markdown; отдельный [export_contract_schemas.py](../tools/export_contract_schemas.py) владеет JSON/schema exports.

## Справка и история

- [Внешние runtime references](LOW_LEVEL_RUNTIME_EXTERNAL_REFERENCES_RU.md) и [Terraria weapons/progression guide](TERRARIA_WEAPONS_AND_PROGRESSION_FULL_GUIDE_RU.md) — reference material, не дополнительная игровая схема.
- [История архитектурных аудитов](HISTORY_RU.md) и [история Visual/VFX](VISUAL_AUDIT_HISTORY_RU.md) — датированные решения, provenance и ограничения прошлых проверок, не текущий GREEN.
- [Отложенные идеи](../TODO_ROADMAP_VERY_LATER_RU.md) — backlog, не обещание реализованных возможностей.

`FOLDER_DOCS_RU.md` объясняют локальное назначение каталогов и ведут к этим владельцам. Новая документация должна закрывать новое решение читателя; дублирующий runbook или список вручную скопированных registry-фактов не нужен.
