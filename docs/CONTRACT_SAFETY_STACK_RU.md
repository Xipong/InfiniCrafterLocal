# Contract Safety Stack v18

Этот слой нужен coding-агентам, чтобы новое поле или engine call нельзя было добавить «наполовину». Он наблюдает и валидирует существующий runtime contract; не проектирует предметы, не генерирует C# и не подменяет gameplay compiler.

## Канонические владельцы

- `core/runtime_authoring/function_contract_registry.py` — канонический список engine calls, public параметров, normalized-only IR, wire/provenance obligations, repair groups и typed lowerer edges.
- `core/runtime_authoring/schema.py` — family/affordance/numeric и cross-param policy; не дублирует каталог.
- `core/runtime_authoring/engine_call_contracts.py` — строгие raw-LLM модели, динамически построенные из registry.
- `core/boundary_models.py` — strict compiled/wire boundaries.
- `contracts/field_lifecycle.json` — только политика обязательных стадий, child/network/zero semantics.
- `GeneratedItemData.Model.cs` — C# DTO.
- `GeneratedItemData.Normalize.cs` — C# normalization.
- `GeneratedProjectile.NetSync.cs` — ordered projectile protocol.
- `GeneratedChildSpecPolicy.cs` — чистые sentry/charge/generic-child transformations.
- `qa/csharp_delivery_contract.py` — source-derived recursive JSON shape/kind boundary для уже очищенного `GeneratedItemData` delivery payload.

`contracts/schemas/*.schema.json` и `contracts/config_registry.json` — generated evidence. Они не являются writable source-of-truth.

`stageOwners` в lifecycle manifest задаёт **узкие glob-границы доказательства** для normalize, projectile network и child policy. Поэтому partial-класс можно разделить на несколько файлов или переименовать внутри объявленной области без переписывания checker-а. При этом checker не ищет совпадение по всей репе и не принимает случайный DTO/serializer token за executor.

## Что проверяет parity v2

Для critical поля отчёт строит цепочку:

```text
Python boundary
Python compiler write
Python final projection
C# DTO type/default
C# normalization
ordered network write/read + primitive type
real executor owner read
child policy (inherit/reset/recompute/strip), если применимо
```

Проверяется фактический source, а manifest задаёт только требуемые стадии и семантику. Добавление строки в manifest не может скрыть отсутствующий DTO/executor.

```bash
PYTHONPATH=LocalGenerator python tools/contract_parity.py --json
PYTHONPATH=LocalGenerator python tools/check_delivery_contract.py
PYTHONPATH=LocalGenerator python tools/mutation_contract_gate.py
```

Mutation gate обязан поймать как минимум:

- потерю `chargeTicks` в Python projection;
- отсутствие `chargeTicks` в C# DTO;
- drift Python/C# default;
- замену C# normalize на константу;
- прекращение чтения поля реальным executor-владельцем;
- перестановку network read;
- разрушение `dustSpawnDenom=0`;
- превращение sentry shot обратно в sentry root.
- scalar вместо nested DTO, unknown nested field и wrong JSON kind в delivered payload.

## Raw и compiled strict boundaries

Сырые вызовы LLM валидируются **до repair/normalization**. Неизвестные функции, параметры, enum и неверные типы не могут исчезнуть и превратиться в зелёный canonical plan.

После semantic lowering повторно не применяется raw-LLM provider schema. Вместо этого normalized output обязан уложиться в закрытый typed lowerer edge из registry; provenance использует тот же binding graph. Внутренние canonical calls могут рефакториться, если сохраняют этот IR и compiled contract.

Финальный boundary:

- запрещает неизвестные executable поля;
- требует compiler-owned поля, а не молча подставляет DTO defaults;
- строго валидирует вложенные buffs/runtime state/VFX DTO;
- не мутирует вход и не авторит значения.

C# запрещает неизвестные nested JSON fields. Top-level `GeneratedItemData.ExtensionData` остаётся только для разрешённой local/debug metadata; network payload очищается.

## Property-based проверки

Hypothesis проверяет общие свойства, а не curated библиотеку оружия:

- `normalize(normalize(x)) == normalize(x)`;
- unknown enum/trigger не становится executable;
- explicit zero переживает compiler/projection;
- compiler-owned charge/sentry fields доходят до финального `AttackSpec`;
- child budget bounded;
- опасные комбинации вроде `overhead + on_expire` отвергаются;
- infinite pierce + long lifetime + split остаётся bounded;
- sentry root с child-producing onHit/secondary triggers и charge_release с vanilla ammo отвергаются для всех сгенерированных комбинаций.

C#-специфичное свойство «sentry shot не становится sentry root / released shot не остаётся holdout» не дублируется Python-моделью. Его проверяют mutation gate, чистый `GeneratedChildSpecPolicy` и opt-in self-test внутри реально скомпилированного tModLoader runtime.

Минимальный контрпример Hypothesis становится regression fixture/test.

## Locality-aware test routing

`agentctl verify --changed` не запускает весь test universe после каждого leaf diff.
Глобально обязательны только `compileall` и project hygiene; runtime-authoring diff
получает компактный invariant-набор + parity/mutation/semantic/replay gates, а
Visual/VFX diff — свой focused contract-набор. C# diff проверяется прямыми
parity/delivery/mutation/static-C# gates и обязательным настоящим build, а не полным
Python suite: source-string тесты не заменяют компилятор и не должны тормозить каждую
правку executor-а. Изменённые test modules запускаются отдельно через
`tools/run_changed_pytests.py`; shared fixture/helper change честно переходит на полный
suite. Полный sharded pytest остаётся release/final-acceptance gate, а не обязательным
inner-loop после каждого патча.

## Replay и semantic baseline

```bash
PYTHONPATH=LocalGenerator python tools/check_runtime_contract_replay.py
PYTHONPATH=LocalGenerator python tools/check_runtime_contract_replay.py --function deploy_sentry
PYTHONPATH=LocalGenerator python tools/check_runtime_contract_replay.py --form deploy_sentry:placement
python tools/replay_generation_case.py replay <case> --strict
python tools/replay_generation_case.py replay <case> --strict --rerun --replay-raw <fixture>
```

Committed historical gate всегда прогоняет весь зафиксированный corpus, если affected function/form не задан явно. Выбор по `function:param.path` выводится из typed lowerer graph и fail-closed завершает работу, если для изменённой формы нет corpus coverage. Это короткий gate production compiler/final projection, а не frozen snapshot implementation details.

Strict replay:

1. прогоняет final wire boundary;
2. повторно компилирует runtime;
3. сравнивает deterministic compiler semantics с `compiled_runtime.json`;
4. возвращает non-zero при drift;
5. при `--rerun` запускает реальный `combine()` в изолированном cache с сохранённым raw LLM fixture и не обращается тихо к внешней модели.

`tools/semantic_runtime_diff.py` сравнивает десять golden vertical slices с замороженным v20 authorship baseline. Он фиксирует семантику после удаления скрытых defaults; damage/timing/family/child-budget не игнорируются.

## Влияние на runtime

```bash
PYTHONPATH=LocalGenerator python tools/runtime_impact_report.py
```

Gate доказывает:

- agent/tools/contracts infrastructure не импортируется игровым runtime;
- safety schemas не генерируют C#;
- validators не авторят gameplay;
- golden gameplay semantics не изменились;
- единственные intentional runtime corrections v18: сохранение `dustSpawnDenom=0`, маршрутизация tool light в уже существующие `holdLight*`, вынос child resets в чистого владельца.

## Конфигурация

`tools/config_registry.py` извлекает реальные `INFINI_*` обращения, GUI-поля, example-env и C# references. Registry содержит type/default/bounds/owners/visibility и маскирует secrets.

```bash
PYTHONPATH=LocalGenerator python tools/config_registry.py --check
```

Новый env-параметр добавляется в его реальном owner. Отдельно редактировать generated registry нельзя.

## Agent control plane

```bash
python tools/agentctl.py doctor
python tools/agentctl.py context --task "..." --budget 14000
python tools/agentctl.py verify --changed
python tools/agentctl.py diff --semantic
python tools/agentctl.py task-check --task-file task.json
python tools/agentctl.py handoff
```

`.agent/impact_rules.json` выбирает проверки по diff. C#-чувствительная задача без настоящего tML build получает `blocked`, а не ложный PASS. `task-check` проверяет baseline, allowed/forbidden path globs и обязательный build flag для параллельных worktree-агентов.

## Полный release gate

Windows:

```bat
05_VALIDATE_RELEASE_STACK.bat
```

Linux/CI:

```bash
./tools/validate_release.sh --require-build
```

Без `dotnet`/tML/external assemblies Python/semantic часть может иметь `ok=true`, но `releaseReady` обязано оставаться `false`. После build tModLoader запускается один раз с `INFINI_AGENT_SELFTEST=1`; отчёт проверяется `tools/check_tml_selftest_report.py`. По умолчанию этот ModSystem возвращается сразу и не трогает мир, игроков или projectiles.


## Compact projectile hydration

`ProjectileSyncVersion = 20` передаёт только world-scoped generated id, конечный runtime-variant и точную упорядоченную последовательность bounded instance scalars. `ReceiveExtraAI` не присваивает ни одного поля `AttackSpec` из packet: immutable parent spec берётся из `GeneratedItemRegistryService`, а child/release spec детерминированно восстанавливает `GeneratedChildSpecPolicy`. `contract_parity` проверяет packet order/types, отсутствие `_spec` writes/reads, registry hydration, harmless missing-data defer и числовые bounds; `field_lifecycle.json` отмечает этот общий `registryHydrate` stage вместо ложного per-field `netWrite/netRead`.
