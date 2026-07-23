# Добавление runtime capability coding-агентом

Цель процедуры — не запретить расширение проекта, а сделать неполное расширение красным.

## Новый engine call

1. Добавь функцию и параметры в immutable registry:
   `core/runtime_authoring/function_contract_registry.py` с primitives из
   `function_contract_types.py`. Одновременно задай provider type/enum,
   prompt-card visibility, wire/provenance obligation и repair group. Если
   high-level call понижается в другой executor, сразу опиши typed `lowerers`:
   target function, source paths и закрытый набор target paths.
2. Проверь generated raw boundary:

```bash
PYTHONPATH=LocalGenerator python -c "from infini_local.core.runtime_authoring.engine_call_contracts import engine_contract_inventory; print(engine_contract_inventory())"
```

Однозначные конечные enum выводятся из registry автоматически. Произвольные
authored строки остаются открытыми только когда это намеренный contract
(например, modded identity), а не потому что finite vocabulary забыли закрыть.

3. Добавь semantic lowering/normalization в профильного Python-owner. Production
   lowerer обязан пройти `validate_lowerer_output`: emitted target params не могут
   выходить за typed edge. Provenance берётся из того же binding graph, а не из
   отдельной ручной карты.
4. Добавь compiler projection в final `AttackSpec`/`GameplaySpec` и явную
   provenance/final-wire обязанность. Applicability имеет одного отдельного owner в
   `reports.py`/runtime-family policy; не заводи её зеркало в function registry.
5. Обнови affected historical replay coverage и один contract-invariant/E2E case.
   Не добавляй огромный frozen JSON snapshot реализации: parity gate должен
   проверять target closure, final-wire reachability и provider/prompt projection
   непосредственно из canonical registry. Пустая replay-выборка для известной
   изменённой функции должна fail-closed, а не считаться зелёным результатом.

Не нужно редактировать общий validator для каждой новой функции, если тип выразим
registry. Ручной код boundary нужен только для новой структурной формы параметра.

## Новое executable поле

Поле должно пройти только применимые стадии:

```text
Pydantic compiled boundary
Python compiler
Python final projection
C# DTO/default
C# normalize
network policy
executor read
child policy
```

В `contracts/field_lifecycle.json` указываются:

- `requiredStages`;
- owners;
- `zeroSemantics`;
- child policy (`inherit`, `reset`, `recompute`, `strip`, `not_applicable` по фактической реализации);
- network stage только если значение действительно требуется projectile instance.

Manifest не доказывает наличие поля — source extractor доказывает его сам.

## Рефакторинг существующей capability

Разрешено:

- переносить semantic code в профильного owner;
- выносить child transforms в чистые функции;
- менять внутренние canonical calls;
- заменять dict internals typed structures постепенно;
- разделять большие partial-файлы.

Обязательно:

- обновить owner path/method в lifecycle policy, если владелец реально вышел за объявленный `stageOwners` glob;
- сохранить ordered network protocol либо явно bump protocol version;
- не менять wire field/enum spelling скрытым alias;
- прогнать semantic baseline и mutation gate.

Тесты не должны требовать, чтобы присваивание физически оставалось в старом façade/partial-файле. Они проверяют canonical owner и результат. Normalize, net-sync и child-policy owners поддерживают узкие glob-пути: безопасное разбиение partial-файла не требует ослаблять проверку до глобального token search.

## Когда новое поле не нужно

Не добавляй DTO/runtime поле для:

- provenance/debug-only данных;
- `attack.genome`/`patternSource` и других compiler diagnostics;
- visual prose, которое не исполняется;
- future intent без executor.

Такие данные остаются debug/presentation-only либо explicit rejected/inert.

## Команды перед handoff

```bash
python tools/agentctl.py verify --changed
python tools/agentctl.py diff --semantic
PYTHONPATH=LocalGenerator python tools/mutation_contract_gate.py
PYTHONPATH=LocalGenerator python tools/runtime_impact_report.py
```

Если изменён C#, итог нельзя объявлять runtime-ready без настоящего tML build и зависимостей.
