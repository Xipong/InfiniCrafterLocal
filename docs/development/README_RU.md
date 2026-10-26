# Разработка InfiniCrafterLocal

Этот раздел — для изменения checkout. Установка и первый craft — в [руководстве игрока](../user/START_RU.md); вся документация — в [общем индексе](../README_RU.md).

## Короткий маршрут

После [AGENTS](../../AGENTS.md) открой известный исходник либо выбери одну строку [карты задач](CODE_MAP_RU.md#fast-start). Следуй прямым вызовам до consumer и его существующего regression. Уже прочитанные инструкции не нужно загружать заново.

[ARCHITECTURE](architecture/ARCHITECTURE_RU.md) нужна, когда меняется общий поток или authority; [MODULES](MODULES_RU.md) — при затронутой границе подсистемы; [TESTING](TESTING_RU.md) и [BUILD](BUILD_RU.md) — для выбора уровня проверки. Это справочники по необходимости, а не очередь обязательного чтения перед каждой задачей.

## Папки по назначению

- **`architecture/`** — общий поток, engine execution и политика lowering.
- **`pipeline/`** — три LLM-стадии, frozen-first Repair, компактные запросы и жизненный цикл изображений.
- **`providers/`** — transport envelope, admission/quota, prompt cache и latency.
- **`runtime/`** — native craft lifecycle и технические исправления текущего мира.

В корне раздела остаются этот вход, [CODE_MAP](CODE_MAP_RU.md#fast-start), [BUILD](BUILD_RU.md), [TESTING](TESTING_RU.md), [организация docs](DOCUMENTATION_RU.md) и [roadmap](ROADMAP_RU.md). Основные руководства [по границам модулей](MODULES_RU.md) и [добавлению capability](ADDING_RUNTIME_CAPABILITY_FOR_AGENTS_RU.md) также остаются здесь: на них напрямую ссылаются инструкции проекта. Это полные канонические главы, не копии и не перенаправления. Утилиты физически разделены в [tools](../../tools/README_RU.md); карта исходников остаётся одна.

## Углубление по задаче

| Задача | Один канонический маршрут |
|---|---|
| Новая механика | [Vertical slice](ADDING_RUNTIME_CAPABILITY_FOR_AGENTS_RU.md) → [Author contract](../reference/authoring/LOW_LEVEL_RUNTIME_AUTHORING_RU.md) → [generated inventory](../reference/generated/LOW_LEVEL_CAPABILITY_INVENTORY_RU.md) |
| LLM стадии и локальное исправление | [Pipeline](pipeline/THREE_STAGE_LLM_PIPELINE_RU.md), [frozen-first Repair](pipeline/TARGETED_REPAIR_PROTOCOL_RU.md); компактные запросы [Author](pipeline/AUTHOR_REQUEST_COMPACTION_RU.md) и [Repair](pipeline/REPAIR_REQUEST_COMPACTION_RU.md) |
| Проверяемые факты native-родителей и боеприпасов | [Источники, сертификаты и границы](pipeline/PARENT_NATIVE_FACTS_RU.md) |
| Lowering/fix/normalization | [Policy](architecture/TECHNICAL_LOWERING_POLICY_RU.md), [generated boundary](../reference/generated/LOWERY_RU.md) |
| Provider envelope/quota/cache | [Request shape](providers/LLM_TRANSPORT_REQUEST_SHAPE_RU.md), [admission](providers/LLM_PROVIDER_ADMISSION_RU.md), [cache/latency](providers/LLM_PROMPT_CACHE_AND_LATENCY_RU.md) |
| Image attempts/publication/delivery | [Image lifecycle](pipeline/IMAGE_ASSET_LIFECYCLE_RU.md) |
| Craft/cancel/refund/world-exit | [Native craft lifecycle](runtime/NATIVE_CRAFT_LIFECYCLE_QOL.md) |
| Технические исправления текущего мира | [Границы и владельцы](runtime/CURRENT_WORLD_TECHNICAL_FIXES_RU.md) |
| Engine execution/trust | [Runtime boundaries](architecture/ENGINE_RUNTIME_BOUNDARIES_RU.md) |
| Где хранить и обновлять docs | [Организация и sources](DOCUMENTATION_RU.md), [generated refresh](../reference/GENERATED_RU.md) |

## Dev-окружение

Из корня checkout, пример Linux/WSL с отдельным venv; Windows runtime `.venv` не переиспользуется в Linux:

```bash
python3 -m venv .venv-dev
. .venv-dev/bin/activate
python -m pip install -r LocalGenerator/requirements-dev.txt
```

Если окружение уже есть, используй его. Это установка dev-зависимостей, не acceptance. На Windows нужен отдельный venv/`Scripts/python.exe`; пользовательский Studio открывается основным BAT. .NET/tML/external DLL — отдельные prerequisites [BUILD](BUILD_RU.md).

<a id="быстрый-offline-проход"></a>
## Быстрый offline проход

```bash
PYTHONPATH=LocalGenerator python tools/generate/generate_lowery.py --check
PYTHONPATH=LocalGenerator python tools/generate/generate_low_level_runtime_docs.py --check
PYTHONPATH=LocalGenerator python tools/generate/generate_primitive_parity.py --check
python tools/checks/check_project_hygiene.py
```

Affected behavioral suite выбирай по [TESTING](TESTING_RU.md). Полный Python runner — `tools/testing/run_pytest_shards.py` (оба roots); полный packaging набор — [AGENTS](../../AGENTS.md#обязательный-vertical-slice). Для gameplay требуется registry → schema/prompt → validator/compiler receipts → strict wire → C# DTO/executor → tests/docs, не локальная запись только в prompt/schema/C#.

Обычный docs/offline проход не запускает live campaign, модель, OAuth/login, игру или paid API. Source/headless CPU/full build/GPU/world loop/art/MP — разные уровни; неисполненное — `notRun`, не PASS. [PR workflow и лицензия](../../CONTRIBUTING.md).
