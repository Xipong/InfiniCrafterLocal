# Тесты

| Каталог | Что проверяет |
|---|---|
| `generator/<область>/` | Python: Author/Repair, runtime contracts, изображения, VFX, storage, transport и Studio |
| `generator/fixtures/` | Входные данные Python; общие helpers лежат рядом с `suite_paths.py` |
| `native/<область>/` | Поведение C# на настоящих Terraria/FNA API; общий entrypoint — `native/EngineRuntimeChecks.cs` |
| `fixtures/` | Общие Python → C# данные и зафиксированные исторические входы |
| `toolbox/` | CLI, campaign и craft-audit |

Workbench проверяется отдельно: `python tools/workbench/workbench.py test`.

Из корня можно запустить конкретный Python-файл:

```bash
python -m pytest -q tests/generator/storage/test_environment_access_contract.py
```

Полная приёмка и окружение описаны в [TESTING_RU.md](../docs/development/TESTING_RU.md).
История прежних аудитов перенесена в [архив](../docs/archive/TEST_AUDITS.md).
