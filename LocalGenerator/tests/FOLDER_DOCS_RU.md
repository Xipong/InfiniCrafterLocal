# Python-тесты

[Канонические владельцы и приёмка](../../docs/TEST_CONTRACT_OWNERS_RU.md) — единая инструкция по тестам, gates и мутациям. `fixtures/` хранит неизменяемые regression inputs; общие VFX builders — `vfx_material_fixtures.py` и `vfx_image_fixtures.py`.

[conftest.py](conftest.py) до collection отключает операторский `config.env`, live LLM и autostart SD.cpp, создаёт изолированный cache. Изменения среды выполняются через `monkeypatch`. `INFINI_TEST_USE_PROJECT_CONFIG=1` допустим только для отдельно запрошенного эксперимента, не release gate.

[run_pytest_shards.py](../../tools/run_pytest_shards.py) выполняет оба test root конечными пакетами и сохраняет необходимую process isolation. [run_focused_pytests.py](../../tools/run_focused_pytests.py) выбирает узкие модули с `INFINI_FOCUSED_PYTEST=1`; это не полный PASS. При неполных зависимостях сначала запускай [validate_sandbox.py](../../tools/validate_sandbox.py), а не падающую полную collection.

Версионируемый [toolbox](../../toolbox/README.md) отделяет offline harness tests от явно разрешаемого live-запуска. Название теста или fixture prose не доказывает реализованную механику.
