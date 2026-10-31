# Проверки контрактов и их владельцы

Новый regression сначала относится к **наблюдаемому инварианту**, а не к номеру релиза. Вариант существующего контракта добавляется в named table/corpus, не в отдельный bug-specific файл. Владельцы production-кода — в [карте задач](CODE_MAP_RU.md); правила изменения runtime — в [AGENTS.md](../../AGENTS.md).

В Studio точные RGB, подписи и DOM-селекторы могут быть устаревшими снимками дизайна: меняй их тесты вместе с интерфейсом, сохраняя проверки поведения. Это оболочка генератора, а не игровой runtime.

## Где проверять

Пути семейств ниже относительны [LocalGenerator/tests](../../LocalGenerator/tests).

| Инвариант | Канонический вход / семейство |
|---|---|
| Registry → schema/card → validator → compiler → receipts/wire | [registry vertical](../../LocalGenerator/tests/test_registry_vertical_contract.py); [units и percent projection](../../LocalGenerator/tests/test_registry_author_units.py) — единый numeric owner; `test_registry_*` отдельно покрывают neutral provenance, receipt identity, wire/cache, Author packet и composition |
| Typed frozen merge, literal JSON members, captured Gameplay/Visual replay | [frozen Repair](../../LocalGenerator/tests/test_repair_frozen_contract.py) |
| Exact permissions → filter → apply → validator | [Gameplay Repair](../../LocalGenerator/tests/test_repair_gameplay_contract.py), [VFX Repair](../../LocalGenerator/tests/test_repair_vfx_contract.py) |
| Identity/binding/producer transactions и три реальные LLM-стадии | [pipeline Repair](../../LocalGenerator/tests/test_pipeline_repair_contract.py), [stage ordering/budgets](../../LocalGenerator/tests/test_low_level_three_stage_pipeline.py) |
| Visual metadata и serialized prompt/cache boundary | [presentation](../../LocalGenerator/tests/test_visual_presentation_metadata.py), [prompt prefix](../../LocalGenerator/tests/test_visual_vfx_prompt_prefix.py) |
| Explicit hand movement → frozen Repair → Visual grip → delivered DTO | `test_front_hand_movement.py`, `test_front_hand_visual_contract.py`, `test_front_hand_wire_integration.py`; native `EngineRuntimeChecks.FrontHand.cs` использует fresh compiler fixture `tools/fixtures/front-hand-compiled.json`, не исторический игровой предмет |
| VFX packet/material/frozen/selected PNG producer | `test_vfx_*`; [dependency/delivery](../../LocalGenerator/tests/test_vfx_dependency_delivery_contracts.py) |
| Image attempts, adapters, ingredients, pixels/UV | `test_image_*`, [ingredients](../../LocalGenerator/tests/test_vfx_ingredient_generation_contracts.py), [sprite render](../../LocalGenerator/tests/test_sprite_render_contracts.py) |
| Transfer byte authority и cache/quarantine | [asset transfer/cache](../../LocalGenerator/tests/test_asset_transfer_cache_contracts.py) |
| Complete builder-owned instruction/data segments, changed-tail identity и role-preserving provider wire | [craft instruction segments](../../LocalGenerator/tests/test_craft_instruction_segments.py); `prompt_packet_helpers.py` — только derived dossier observer в semantic tests |
| Profile pin, retry/failover, request semantics, HTTP и lifecycle | `test_provider_*`; [activity/real-route faults](../../LocalGenerator/tests/test_provider_activity_contract.py) — current stages, semaphore/rate waits, cache I/O recovery, actionable failures и sibling identity; [Codex subscription](../../LocalGenerator/tests/test_codex_subscription_contract.py) отдельно защищает auth/SSE/privacy/no-paid-fallback |
| Placement provenance, maxStack и use-policy | [placement](../../LocalGenerator/tests/test_item_placement_contracts.py), [dual-use transactions](../../LocalGenerator/tests/test_dual_use_placeable_contract.py) |
| Source-language policies и runner registration | Существующие [C# gate](../../tools/checks/check_csharp_contracts.py), [hygiene gate](../../tools/checks/check_project_hygiene.py); их synthetic positive/negative controls — [source audits](../../LocalGenerator/tests/test_source_audit_gates.py) |
| Studio HTTP/session и headless controller: все поля, сохранение и unknown keys | [bridge/controller](../../LocalGenerator/tests/test_web_studio.py) |
| Browser draft: поздняя LAN-правка и polling до подтверждения преобразования | [delayed-response integration](../../LocalGenerator/tests/test_web_studio_browser.py) — настоящий headless controller + Chromium, не mock API |
| Реальная C#/tML/FNA CPU-семантика | [EngineRuntimeChecks.csproj](../../tools/native/EngineRuntimeChecks.csproj) и зарегистрированные partial checks |

Самостоятельные UI, multiplayer, trace и tooling-контракты сохраняют своих владельцев. Сходство названий не доказывает дублирование.

## Практический бюджет

- Проверяй вход → результат через настоящего владельца: compiler/validator/Repair, serialized provider request, asset bytes или native C# entry point. Обычный и невалидный пример важнее десятков одинаковых комбинаций.
- Не фиксируй private method names, порядок строк, количество guards или точные куски реализации. При внутреннем refactor поведение должно остаться GREEN без восстановления старых wrappers.
- Source tests нужны лишь для настоящих source-language policies (warning suppression, запрещённые gameplay routers, authored-field ownership) и регистрации runner. `test_source_audit_gates.py` проверяет lint API на маленьких synthetic inputs; scanner не доказывает runtime correctness.
- Frozen Repair, authority/security, literal wire identity и material claims остаются поведенческими контрактами. Native suite проверяет крафт, отмену, возврат/capacity, world persistence, asset lifecycle и representative invalid inputs через actual consumers. Exhaustive DTO/shape products, частные UI/storage observers и creative pixel/curve микропроверки сознательно убраны; чтение `.cs` в Python не заменяет runtime behavior.
- Удаляй низкоценные повторные проверки, не прячь их за skip/xfail, общим циклом или переименованным helper. Не обещай сохранение всех прежних assertions: узкое честное покрытие лучше дублирующего scanner framework.
- Для tests-only cleanup достаточно одного affected Python run; неизменённые native результаты можно повторно использовать. Не запускай full suite и mutation campaign по кругу. Full CI принадлежит интегрированному commit.

## Один рабочий маршрут

`tools/agentctl.py` выбирает существующие семейства проверок по крупным областям владельцев. Это подсказка для итерации, не доказательство полного impact closure:

```bash
python tools/agentctl.py context --task "новая capability" --area runtime
python tools/agentctl.py context --task "настройка Studio" --area studio
python tools/agentctl.py context --task "projectile bug" --path ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Executors.cs
python tools/agentctl.py verify --path LocalGenerator/infini_local/core/runtime_authoring/validator.py
python tools/agentctl.py verify --area transport
python tools/agentctl.py verify --changed --base origin/main --plan
python tools/agentctl.py verify --changed --base origin/main
python tools/agentctl.py diff --base origin/main
```

- `verify --path` и `--area` запускают existing owner checks даже в чистом checkout/source archive; оба флага повторяемы и объединяют выбранные области. Выбор не сканирует Git diff и отражается в `paths`, а не в `changedFiles`. Не смешивай явный scope с `--changed`/`--base`; для branch diff есть отдельный запуск. `--plan` только показывает команды, без проверки.
- `--base` сравнивает committed branch diff от merge-base и добавляет staged/unstaged/untracked изменения. Для stacked PR используй его base branch. Без `--base` учитывается только рабочее дерево.
- Runtime, Studio, transport и storage выбирают готовые test families; C# — static contract gate и один полный быстрый linked-source CPU runner. Mutation и full pytest остаются финальной приёмкой.
- Неизвестные пути и общие test fixtures/conftest консервативно выбирают полный набор. Изменённый самостоятельный test module запускается сам. Пустая выборка — `not_selected`, недоступная среда — `unavailable`/`notRun`, не PASS.
- `context --area` выбирает область, `--path` — существующий файл; `--line` начинает его выдержку с нужной строки. Явный контекст не сканирует изменения ветки. `suggestedVerification` — один план выбранного scope, без запуска; его исполняют `verify --path`/`--area`, реальный diff проверяет `verify --changed`. `--task` — необязательное описание, не эвристический router. Стандартный бюджет — 5000 символов исходников; обрезка отмечается `truncated`, границы — `startLine`/`endLine`.
- `run_changed_pytests.py --base ...` — только удобный pytest subset из той же карты. Он не заменяет остальные gates.
- `agentctl diff` — только committed/worktree source diff и список changed paths, без semantic verdict или запуска валидаторов. `--semantic` и дублирующие parity/semantic report tools удалены.
- Budget scalar-таблицы проверяются через реальные request callers без полного subprocess для каждого значения; изолированные process smoke остаются для import-time настроек и representative Repair routes. Schema/cache reconstruction использует representative стадии и отдельные provider-wire controls вместо повторного product. Исторические inverse projections ради старого whole-document hash и private-name blacklist не являются обязательствами текущей версии; frozen fixture bytes и direct refusal сохраняются.
- Полный library audit выполняется один раз внутри generated-docs gate; `audit_capability_library.py` остаётся отдельной ручной командой для отчёта, не дублирующим шагом full validation.

Полная приёмка: `python tools/validate_release.py`. Bash/PowerShell wrappers и CI вызывают тот же Python owner и manifest. Группы `--group python`, `--group static`, `--group build` делят полный набор без повторов; `releaseReady` требует выполнения всего набора. Недоступные optional native/live проверки показываются отдельно даже при успешных offline gates.

Для native CPU: `dotnet` в PATH, `INFINI_TML_REFERENCE_DIR` указывает на `tModLoader/lib/net8.0`, `INFINI_TML_DEPS_SRC` — на корень ParticleLibrary/Luminance. Runner собирает harness один раз и запускает DLL только после успешной сборки. Это не GPU/world/MP проверка. `--require-build` и `--require-runtime-selftest` делают соответствующие environment gates обязательными для release command.

Обновление производных файлов: `python tools/validate_release.py --refresh runtime` либо `--refresh config`; оба вызывают существующих producers и в конце обновляют offline handbook. Для одной документации — `--refresh docs`. Refresh не запускает тестовую кампанию и не меняет runtime contracts сам.

## Запуск

Из корня с test dependencies:

```bash
PYTHONPATH=LocalGenerator python -m pytest -q LocalGenerator/tests/<affected_module>.py
python tools/checks/check_csharp_contracts.py
```

Studio controller проверяется без Tcl/Tk и дисплея. Для browser integration нужны `playwright` и установленный Chromium (`python -m playwright install chromium`). Без этих optional prerequisites соответствующая проверка явно пропускается; HTTP/security-контракт остаётся headless. Запуск:

```bash
PYTHONPATH=LocalGenerator python -m pytest -q LocalGenerator/tests/test_web_studio.py LocalGenerator/tests/test_web_studio_browser.py
```

Полная Python приёмка: `PYTHONPATH=LocalGenerator python tools/testing/run_pytest_shards.py --shards 4` (оба test roots). Native:

```bash
dotnet build tools/native/EngineRuntimeChecks.csproj -c Release \
  -p:InfiniTmlReferenceDir="<tModLoader lib/net8.0>" \
  -p:InfiniExternalDepsRoot="<ParticleLibrary/Luminance root>"
dotnet tools/native/bin/Release/net8.0/EngineRuntimeChecks.dll --check-filter "<named behavior>"
```

Новый `tools/native/EngineRuntimeChecks*.cs` входит в Compile автоматически; добавь явный вызов check в `RunChecks`. C# source gate проверяет развёрнутый compile roster и фактическую регистрацию.

Filter должен выбрать хотя бы одну проверку; compile и registration smoke не равны execution. Без .NET/tML/FNA/native DLL — `notRun`, не PASS. CPU/headless не доказывает GPU/game-loop или сетевой матч. Не меняй production, operator config, captured fixtures или generated artifacts ради tests-only GREEN.


## Advisory-контроль сложности Python

```bash
python tools/checks/check_code_health.py --base origin/main
python tools/checks/check_code_health.py --base origin/main --path LocalGenerator/infini_local/core/runtime_authoring/repair/scope.py
```

Команда сравнивает текущие Python implementation files с Git merge-base; без `--path` учитывает committed, staged, unstaged и untracked изменения. Без `--base` baseline — `HEAD`. Tests и декларации вне функций не входят в измерение; функции внутри большого registry проверяются как обычно. Старый показатель выше ориентира становится своим текущим пределом: сохранение или уменьшение не даёт предупреждения, рост показывает before/after/cap.

| Метрика | Начальный ориентир |
|---|---:|
| Физические строки функции | 300 |
| Точки ветвления AST внутри функции | 20 |
| Вложенные control-flow blocks | 6 |
| Строки функций файла, без двойного счёта вложенных функций | 2000 |

Точки ветвления включают if/циклы/except, условные выражения, булевы связи, comprehensions и match cases; это простая структурная метрика. Цепочка elif имеет один уровень вложенности. Перенос с единственным одинаковым AST в baseline и текущем scope сохраняет предел функции; копия или перенос с изменённой сигнатурой/телом считается новой функцией. Для распознавания переноса выбери оба владельца или весь diff.

Это отдельный advisory-отчёт, без CI/release gate и без baseline-файла, который нужно вручную обновлять. Предупреждения возвращают exit 0 и требуют человеческой оценки; недоступный Git baseline, неверный путь и ошибка разбора возвращают exit 2. Удобное выделение самостоятельного helper иногда увеличивает суммарные строки: такой сигнал сам по себе не требует дробить код дальше. Отчёт никогда не объявляет `releaseReady`.
