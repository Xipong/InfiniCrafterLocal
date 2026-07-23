# Добавление runtime capability coding-агентом

Цель процедуры — не запретить расширение проекта, а сделать неполное расширение красным.

## Новый engine call

1. Добавь функцию и параметры в immutable registry:
   `core/runtime_authoring/function_contract_registry.py` с primitives из
   `function_contract_types.py`. Одновременно задай provider type/enum,
   prompt-card visibility, wire/provenance obligation, repair group и
   `lowered_function_names`, если high-level call понижается в другой executor.
2. Проверь generated raw boundary:

```bash
PYTHONPATH=LocalGenerator python -c "from infini_local.core.runtime_authoring.engine_call_contracts import engine_contract_inventory; print(engine_contract_inventory())"
```

Однозначные конечные enum выводятся из registry автоматически. Произвольные
authored строки остаются открытыми только когда это намеренный contract
(например, modded identity), а не потому что finite vocabulary забыли закрыть.

3. Добавь semantic lowering/normalization в профильного Python-owner. Если call
   понижается, registry metadata и production lowerer должны указывать один и тот
   же canonical executor; frozen surface/replay tests обязаны это проверять.
4. Добавь compiler projection в final `AttackSpec`/`GameplaySpec` и явную
   provenance/final-wire обязанность. Applicability пока остаётся в
   `reports.py`/runtime-family policy: `allowed_result_kinds` в registry зарезервирован
   и не является действующей политикой.
5. Обнови frozen function surface, affected historical replay coverage и
   property/E2E golden case. Пустая replay-выборка для известной изменённой функции
   должна fail-closed, а не считаться зелёным результатом.

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
