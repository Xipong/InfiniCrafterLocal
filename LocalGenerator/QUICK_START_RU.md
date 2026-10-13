# LocalGenerator 0.5.00 — offline QA

Для **пользовательского запуска** нужен [основной Windows-вход](../docs/user/START_RU.md). Здесь только source checkout без model/image/game/login. Dev-зависимости отличаются от runtime; установка не gate.

## Команды из корня репозитория

Используй уже подготовленное dev-окружение: [подготовка](../docs/development/README_RU.md#подготовь-dev-окружение).

```bash
python tools/validate_sandbox.py
PYTHONPATH=LocalGenerator python tools/audit_capability_library.py
PYTHONPATH=LocalGenerator python tools/check_delivery_contract.py
python tools/check_project_hygiene.py
python tools/check_csharp_contracts.py
```

Для regression выбери affected suite в [тестовом runbook](../docs/development/TESTING_RU.md); полный runner обоих test roots — `PYTHONPATH=LocalGenerator python tools/run_pytest_shards.py --shards 4`. Полный packaging набор — [AGENTS](../AGENTS.md#обязательный-vertical-slice).

[C# prerequisites](../docs/development/BUILD_RU.md#сборка) нужны отдельно. Portable validation не равна full pytest/build; offline/headless не доказывает художественное качество, world/GPU/MP. Неисполненное — `notRun`. Live campaigns требуют отдельного разрешения: [toolbox](../toolbox/README.md).
