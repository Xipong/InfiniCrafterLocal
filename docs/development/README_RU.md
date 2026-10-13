# Центр разработки — 0.5.00

Это вход для изменения source checkout, не пользовательская установка. Для запуска приложения — [руководство игрока](../user/START_RU.md).

## Перед изменением

1. Прочитай [AGENTS](../../AGENTS.md), [архитектуру](ARCHITECTURE_RU.md) и [карту кода](CODE_MAP_RU.md).
2. Найди [canonical owner задачи](OWNERS_RU.md); не добавляй shadow registry/facade.
3. Выбери [тестовый контракт](TESTING_RU.md). Прямой regression через настоящего consumer важнее source snapshot.
4. Для gameplay изменения нужен [полный vertical slice](ADDING_RUNTIME_CAPABILITY_FOR_AGENTS_RU.md): registry → schema/prompt → validation/compiler → strict wire → C# DTO/executor → tests/docs.

## Основные владельцы

| Решение | Документ |
|---|---|
| Authority, trust и data flow | [Архитектура](ARCHITECTURE_RU.md), [границы runtime](ENGINE_RUNTIME_BOUNDARIES_RU.md) |
| Пути source и задача → owner | [Карта кода](CODE_MAP_RU.md), [owners](OWNERS_RU.md) |
| LLM стадии и exact-scope Repair | [Pipeline](THREE_STAGE_LLM_PIPELINE_RU.md), [Repair](TARGETED_REPAIR_PROTOCOL_RU.md) |
| Разрешённые преобразования | [Lowering policy](TECHNICAL_LOWERING_POLICY_RU.md), [generated boundary](../../lowery.md) |
| Image attempts, atomic publication и delivery | [Image lifecycle](IMAGE_ASSET_LIFECYCLE_RU.md) |
| Escrow/refund/cancellation/ready-result wait | [Native craft lifecycle](NATIVE_CRAFT_LIFECYCLE_QOL.md) |
| Provider envelope/admission/cache | [Transport](LLM_TRANSPORT_REQUEST_SHAPE_RU.md), [admission](LLM_PROVIDER_ADMISSION_RU.md), [cache/latency](LLM_PROMPT_CACHE_AND_LATENCY_RU.md) |
| Сборка с настоящими DLL | [Сборка](BUILD_RU.md) |
| Regression, full runner и пределы доказательства | [Тесты](TESTING_RU.md) |
| Структура документации и миграция | [Docs ownership](DOCUMENTATION_RU.md) |

## Подготовь dev-окружение

Из корня checkout, пример Linux/WSL с отдельным окружением; Windows runtime `.venv` не переиспользуй в Linux:

```bash
python3 -m venv .venv-dev
. .venv-dev/bin/activate
python -m pip install -r LocalGenerator/requirements-dev.txt
```

Это установка dev-зависимостей, не gate. Если окружение уже подготовлено, используй его. На Windows можно использовать отдельный venv и его `Scripts/python.exe`; production GUI открывается через основной BAT. C# требует [.NET/tML/внешних DLL](BUILD_RU.md), отдельно от Python.

## Быстрый offline проход

```bash
PYTHONPATH=LocalGenerator python tools/generate_lowery.py --check
PYTHONPATH=LocalGenerator python tools/generate_low_level_runtime_docs.py --check
PYTHONPATH=LocalGenerator python tools/generate_primitive_parity.py --check
python tools/check_project_hygiene.py
```

Affected behavioral suite выбирай из [TESTING](TESTING_RU.md); оба Python test roots запускаются `tools/run_pytest_shards.py`. Полный packaging набор — [AGENTS](../../AGENTS.md#обязательный-vertical-slice). Не запускай live campaign, модель, OAuth/login, игру или платный API как часть обычного docs/offline прохода.

Headless CPU, source audit, full build, GPU/world loop, art quality и реальный MP — **разные** уровни. Неисполненный уровень — `notRun`, не PASS. [Generated refresh](../reference/GENERATED_RU.md) не имеет права менять canonical JSON/schema без отдельного owner action. [PR workflow и лицензия](../../CONTRIBUTING.md).
