# LocalGenerator v0.4.249 — offline QA

Для установки/запуска парной поставки 0.4.249 используй [корневой runbook](../QUICK_START_RU.md): обновляй мод и генератор вместе, сохраняя личный конфиг, cache, recipes/PNG и данные миров. Здесь только проверка source checkout; runtime requirements и dev requirements различаются. Прежние offline/native результаты не заменяют проверку финальных release-байтов и не доказывают исправление старых визуальных результатов.

## Команды из корня репозитория

В уже подготовленном Python-окружении разработчика:

```bash
python -m pip install -r LocalGenerator/requirements-dev.txt
python tools/validate_sandbox.py
PYTHONPATH=LocalGenerator python -m pytest -q
PYTHONPATH=LocalGenerator python tools/audit_capability_library.py
PYTHONPATH=LocalGenerator python tools/check_delivery_contract.py
python tools/check_project_hygiene.py
python tools/check_csharp_contracts.py
python tools/check_planner_prompt_usability.py
```

Установка — подготовка окружения, а не gate; не переустанавливай зависимости, если оно уже готово. [AGENTS](../AGENTS.md#обязательный-vertical-slice) перечисляет полный release набор, [test owners](../docs/TEST_CONTRACT_OWNERS_RU.md) — тематические suites/shards. Portable validation не равна полному pytest и не доказывает C# build.

[C# prerequisites](../BUILD_QOL_RU.md#сборка) обязательны отдельно. Неисполненную проверку среды записывай `notRun`, не GREEN. LLM/image/game/login не нужны для перечисленных offline gates; [Live20](../toolbox/README.md) — отдельная разрешаемая кампания с реальным text provider.
