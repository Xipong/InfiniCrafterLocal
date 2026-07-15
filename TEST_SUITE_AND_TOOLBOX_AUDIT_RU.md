# Аудит test-suite/toolbox и проверка изменений Luna 5.6

## Итоговый вердикт

Изменения Luna нельзя было принимать в исходном виде.

Полезная часть была: ограничение subprocess-вызовов, общий timeout shard-runner и исключение `.hermes` из временной копии. Но поверх этого Luna:

1. подменила production-подобные defaults искусственно ослабленной test-конфигурацией;
2. не устранила process-wide pollution, хотя отчёт утверждал обратное;
3. сделала release-runner зависимым от конкретной структуры `agent-work-main/common/.venv`;
4. не нашла установленные `ruff`/`pyright` и оставила release gate красным;
5. не выполнила исходную задачу по semantic test removal/toolbox migration;
6. записала test-runner как ложного владельца продуктовых `INFINI_*` полей в generated registry.

Подтверждённые дефекты исправлены. Полный прямой pytest и release source/contract gates теперь зелёные.

### Уточнение: почему snapshot зависал в ChatGPT

После уточнения среды подтверждён отдельный корень: dependency-poor ChatGPT/web sandbox не имеет части `pytest`/Pydantic/Pillow/Hypothesis stack, но пытался запускать полный suite. Это давало collection/import cascade, после которого агент повторял или дробил проверки и фактически зависал.

Добавлен отдельный честный вход:

```bash
python tools/validate_sandbox.py
```

Он использует только стандартную библиотеку, не импортирует runtime package и запускает только bounded static gates. Результат явно разделяет `ok`, `coverage="portable-static"`, `fullSuiteAvailable` и всегда оставляет `releaseReady=false`.

Защищены также ошибочные входы:

- direct pytest останавливается до collection, если runtime test dependencies отсутствуют;
- `run_pytest_shards.py` возвращает `status=unavailable`, exit code 2 и portable command, не копируя и не собирая tests;
- Linux/Windows release runners делают тот же preflight до первого full gate;
- `AGENTS.md` и корневой `README_RU.md` требуют portable command первым в неизвестном sandbox.

## 1. Подтверждённые проблемы Luna

### P1 — тесты запускались с ослабленными продуктовым defaults

Исходный Luna `conftest.py` и `run_pytest_shards.py` принудительно задавали:

- `INFINI_ALLOW_DETERMINISTIC_DEV_FALLBACK=1`, хотя shipped default в `core/llm_config.py` равен `False`;
- `INFINI_VISUAL_DIRECTOR_LLM=0`, хотя shipped default равен `True`;
- несколько authoring/timeout flags, не нужных для отключения live side effects.

Это могло скрывать отказ fail-closed LLM path и проверяло не фактические defaults репозитория.

Исправление:

- live `config.env` по-прежнему игнорируется;
- `INFINI_USE_LLM=0` и sd.cpp autostart выключены;
- backend identity остаётся shipped `sdcpp`;
- deterministic dev fallback остаётся `0`;
- лишние runtime/visual/timeout overrides удалены.

### P1 — заявленная environment isolation не работала

До исправления `test_sprite_keyer_contract.py` во время collection глобально задавал:

- `INFINI_IMAGE_BACKEND=off`;
- общий `/tmp/infini_sprite_keyer_contract_cache`;
- background/profile flags.

Luna autouse-fixture снимал snapshot уже после collection, то есть сохранял и восстанавливал загрязнённое состояние.

Воспроизведение до исправления:

- `sprite_keyer` перед `test_243_runtime_quality_regressions` → `1 failed, 1 passed`;
- ожидался backend `sdcpp`, фактически получался `off`;
- обратный порядок → `2 passed`.

Это была реальная order dependence. Сам import-time mutation существовал до Luna, но её новый «общий изолятор» не исправлял его и создавал ложную гарантию.

Исправление:

- все module-level `os.environ` mutations удалены из sprite test;
- все временные изображения используют pytest `tmp_path`;
- direct `os.environ.pop` в replay contract заменён на `monkeypatch.delenv`;
- общий autouse env/cwd reset удалён как ненужная магия.

Проверка после исправления:

- оба порядка файлов дают `2 passed`;
- после полной collection: backend=`sdcpp`, fallback=`0`, LLM=`0`, autostart=`0`, cache находится в уникальном `infini-pytest-*` каталоге.

### P1 — release-runner неверно находил Python/toolchain

Luna добавила автоматический поиск:

`$ROOT/../../../common/.venv/bin/python`

Это workspace-specific layout, которого нет в обычном clone/CI. При этом выбранный venv не добавлялся в `PATH`, поэтому shell сообщал `ruff` и `pyright` как unavailable.

Фактическая проверка:

- `common/.venv` содержит `ruff 0.15.21`;
- `common/.venv` содержит `pyright 1.1.411`;
- ruff сразу проходил;
- pyright без interpreter binding не видел `pydantic` и показывал 9 import errors;
- pyright с `--pythonpath common/.venv/bin/python` даёт `0 errors`.

Исправление:

- Python dispatcher передаёт собственный `sys.executable` через `INFINI_PYTHON`;
- shell не знает о `agent-work-main/common/.venv` и использует explicit Python/активный venv/PATH;
- `ruff` и `pyright` сначала запускаются как modules выбранного Python;
- pyright всегда получает `--pythonpath "$PYTHON_BIN"`;
- Windows runner использует тот же selected Python;
- PowerShell source успешно прошёл parser-check.

### P2 — generated config registry был загрязнён

Luna добавила test-only env overrides в `tools/run_pytest_shards.py`. Registry scanner счёл runner владельцем продуктовых полей (`INFINI_IMAGE_BACKEND`, fallback, sd.cpp timeouts и т.д.).

Исправление:

- runner снова задаёт только исходный `INFINI_SKIP_CONFIG_FILE=1`;
- registry регенерирован;
- продуктовые owner lists совпадают с HEAD;
- добавлено только реальное tool-only поле `INFINI_PYTHON`, owner — `tools/validate_release.py`;
- `config_registry.py --check` проходит.

### P2 — отчёт Luna преувеличивал результат

Luna завершила задачу при красном release script и назвала `ruff`/`pyright` недоступными, хотя они были установлены. Кроме того, реальный tML build/self-test не выполнялся.

Текущий отчёт различает:

- `ok=true`: Python/source/contract gates действительно прошли;
- `releaseReady=false`: реальный tML build и runtime self-test не запускались.

## 2. Что было полезным и оставлено

Оставлены изменения с понятной failure semantics:

- 11 subprocess-вызовов в contract tests получили `timeout=30`;
- все 15 subprocess-вызовов test-suite теперь bounded;
- default timeout каждого shard/isolated pytest child равен 60 секундам и остаётся CLI-overridable;
- process-group cleanup в shard-runner сохранён;
- `.hermes` исключён из временной копии shard-worktree.

Replay tests удалены из `ISOLATED_TEST_FILES`: process-wide pollution для них не воспроизведён, а их env mutation теперь использует pytest monkeypatch. Они снова идут в обычном batch без дополнительных child-process startups.

## 3. Дополнительный старый дефект, найденный честным полным запуском

`test_240_python_runtime_bugfixes.py` запускал дочерний Python с `import infini_local`, но полагался на pytest `pythonpath` текущего процесса. Этот setting не передаётся child process.

Без вручную заданного `PYTHONPATH` полный suite стабильно падал:

`ModuleNotFoundError: No module named 'infini_local'`

Исправление локализовано в этом subprocess-тесте: его `env` теперь содержит абсолютный `LocalGenerator` в `PYTHONPATH`. Глобальный conftest ради одного child import не расширялся.

## 4. Можно ли удалить ещё тесты

Текущий набор:

- 90 файлов `test_*.py`;
- 102 pytest items;
- 55 файлов уже сведены в coarse contract: несколько helper-checks выполняются одним pytest item;
- `toolbox/test-consolidation-map.json` — отчёт об этом уже выполненном item-level consolidation, а не карта будущих `remove` actions.

Проверки дублирования:

- проанализировано 710 test/helper functions;
- единственный exact duplicate body между файлами — механическая wrapper-оболочка coarse runner;
- внутренние helper-checks у этих файлов разные;
- совпадающие отдельные assertions — generic seam assertions (`returncode`, `ok`, sentinel fields), а не дубли целых сценариев;
- `check_project_hygiene.py` проходит.

Вывод: безопасных file-level removals в текущей версии не подтверждено. Удаление файлов только ради меньшего числа файлов потеряет отдельные runtime/C#/MP/visual/replay/release owners. Проблема зависания решена ограничением side effects/process lifetime, а не удалением уникальных контрактов.

## 5. Toolbox

`toolbox/migration-map.json` содержит 8 old paths внутри этой версии проекта. Все 8 уже отсутствуют в source tree (`still-existing mapped sources = 0`): перенос/удаление было выполнено ранее.

Нового standalone tool для переноса не подтверждено.

`LocalGenerator/tools/generate_golden_runtime_proof.py` не является случайной миниутилитой:

- вызывается contract test;
- является canonical release/runtime proof generator;
- хранится рядом с versioned source, которое проверяет.

Переносить его в внешний toolbox нельзя без разрушения release ownership.

## 6. Изменённые/исправленные поверхности

- `LocalGenerator/tests/conftest.py`
- `LocalGenerator/tests/test_sprite_keyer_contract.py`
- `LocalGenerator/tests/test_replay_fixtures_contract.py`
- `LocalGenerator/tests/test_240_python_runtime_bugfixes.py`
- `LocalGenerator/tests/test_release_hygiene_tool_contract.py`
- `LocalGenerator/tests/FOLDER_DOCS_RU.md`
- `AGENTS.md`
- `README_RU.md`
- `tools/run_pytest_shards.py`
- `tools/validate_sandbox.py`
- `tools/FOLDER_DOCS_RU.md`
- `tools/validate_release.py`
- `tools/validate_release.sh`
- `tools/validate_release_windows.ps1`
- `contracts/config_registry.json`

Сохранены bounded-timeout изменения в:

- `test_239_golden_runtime_proof_contract.py`
- `test_csharp_compile_surface_contract.py`
- `test_planner_prompt_usability_contract.py`
- `test_v18_contract_safety_stack.py`

## 7. Фактические финальные проверки

### Order-independence regression

- sprite → runtime quality: `2 passed`;
- runtime quality → sprite: `2 passed`.

### Прямой pytest без ручного PYTHONPATH/config guard

- `102 passed in 24.30s`.

### Dependency-poor/no-site simulation

`python -S tools/validate_sandbox.py`:

- exit code 0;
- `ok=true`;
- `coverage="portable-static"`;
- `fullSuiteAvailable=false`;
- `releaseReady=false`;
- 249 Python files и 12 contract/agent JSON parsed;
- 15 bounded test subprocess calls, 0 unbounded;
- config registry, C# static contracts и project hygiene passed.

Ошибочные full entry points в той же no-site среде:

- direct pytest: exit code 2 за 0 секунд, collection не начат;
- shard runner: exit code 2 за 0 секунд, `shards=[]`;
- release shell: exit code 2 за 0 секунд, ни один full gate не запущен.

### Canonical release dispatcher

Запуск через `common/.venv/bin/python tools/validate_release.py --skip-build`:

- pytest shards: `102 passed`, all shards passed;
- compileall: passed;
- schema check: passed;
- config registry: passed;
- contract parity: passed;
- mutation gate: passed;
- semantic runtime diff: passed;
- runtime impact: passed;
- C# source contracts: passed;
- project hygiene: passed;
- planner prompt: passed;
- ruff: passed;
- pyright: `0 errors, 0 warnings, 0 informations`;
- overall report: `ok=true`, `failed=[]`, `unavailableRequired=[]`.

Дополнительно:

- `bash -n tools/validate_release.sh`: passed;
- Windows PowerShell parser: `POWERSHELL_PARSE_OK`;
- `git diff --check`: passed.

## 8. Что не проверено и не заявляется

- реальный tModLoader C# build был явно пропущен;
- runtime self-test report из запущенной Terraria/tML отсутствует;
- поэтому `releaseReady=false` — это честный остаточный статус, а не «полный релиз зелёный».
