# Утилиты репозитория

Игроку эти команды не нужны: установка и первый крафт — в [руководстве игрока](../docs/user/START_RU.md), основной запуск Windows — `OPEN_INFINICRAFT.bat` в корне. Здесь — инструменты для работы с исходниками. Команды ниже выполняются **из корня checkout**, в уже настроенном Python-окружении проекта.

## Выбери задачу

| Где | Для чего | Основные входы |
|---|---|---|
| Корень `tools/` | Стабильные публичные команды | [agentctl.py](agentctl.py) — контекст и affected checks; [validate_release.py](validate_release.py) — единый release/CI owner; [build_documentation.py](build_documentation.py) — офлайн-книга. |
| [build/](build) | Сборка, упаковка и разбор ошибок | `build_tml_windows.bat` / `.ps1`, `try_tml_build_check.py`, `parse_tml_build_log.py`, `package_tmod.ps1`, `verify_tmod_package.py`; release wrappers — `validate_release.sh` / `validate_release_windows.ps1`. `install_to_tmodloader_modsources.py` **заменяет** установленную папку исходников. |
| [checks/](checks) | Offline gates и аудиты | `check_project_hygiene.py`, `check_csharp_contracts.py`, `check_delivery_contract.py`, `audit_targeted_repair.py`; advisory-сложность — `check_code_health.py`. |
| [testing/](testing) | Запуск и проверка тестовой инфраструктуры | `run_focused_pytests.py`, `run_changed_pytests.py`, `run_pytest_shards.py`, `run_pyright.py`, `validate_sandbox.py`; `test_tml_ci.py` проверяет реальную CI-обёртку с синтетическим compiler boundary. |
| [native/](native) | Linked-source C# CPU harnesses | `EngineRuntimeChecks.csproj` + `EngineRuntimeChecks*.cs`; отдельный `AssetTransportChecks/`. Компилируют канонические исходники, не копии алгоритмов. |
| [generate/](generate) | Producers проверяемых проекций | `config_registry.py`, `export_contract_schemas.py`, `generate_lowery.py`, `generate_low_level_runtime_docs.py`, `generate_primitive_parity.py`, `generate_equipment_bounds.py`, `generate_equipment_carriers.py`. Без `--check` генераторы записывают свои outputs. |
| [diagnostics/](diagnostics) | Replay, измерения, визуальные отчёты | `replay_generation_case.py`, `measure_llm_request_sizes.py`, `render_validation_report.py`, `render_vfx_preview.py`, `repro_placed_vfx_fixture.py`. Проверяй аргументы и output path: replay/fixture-команды могут записывать файлы. |
| [fixtures/](fixtures) | Сохранённые входы native-проверок | JSON и PNG — тестовые данные; не пользовательский cache и не outputs нового запуска. |
| [windows/](windows) | Дополнительные Windows BAT-входы | Установка исходников/генератора, сбор журналов и release validation. Основной пользовательский launcher остаётся в корне проекта. |

## Короткие offline-команды

```bash
# Только справка: не запускает проверку, игру или модель.
python tools/agentctl.py --help
python tools/validate_release.py --help
python tools/build_documentation.py --help

# Выбор области и выполнение существующих проверок.
python tools/agentctl.py context --area studio
python tools/agentctl.py verify --area docs
python tools/testing/run_focused_pytests.py LocalGenerator/tests/test_documentation_layout.py

# Проверка свежести без записи.
python tools/build_documentation.py --check
python tools/generate/generate_lowery.py --check
python tools/checks/check_project_hygiene.py
```

`--plan` у `agentctl verify` только показывает выбор, не подтверждает результат. Полная приёмка — `python tools/validate_release.py`; группы CI и команды принадлежат [.agent/manifest.json](../.agent/manifest.json), affected selection — [.agent/impact_rules.json](../.agent/impact_rules.json). Native build требует существующих .NET/tML/external DLL; недоступное окружение — `notRun`, не PASS. Ни offline gate, ни CPU harness не подтверждают игру, GPU или сетевой матч.

[Тесты и уровни доказательства](../docs/development/TESTING_RU.md) · [Сборка и зависимости](../docs/development/BUILD_RU.md) · [Источники и обновление generated docs](../docs/reference/GENERATED_RU.md) · [Единая карта исходников](../docs/development/CODE_MAP_RU.md#fast-start)
