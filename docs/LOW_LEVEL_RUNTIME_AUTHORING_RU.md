# Low-level Runtime Authoring — projection

> Не является владельцем контракта. Каноническая замороженная граница, owner routing и generated lowering manifest находятся в [`../lowery.md`](../lowery.md).
> Exact Author/Repair JSON shape владеет `LocalGenerator/infini_local/core/runtime_authoring/program_schema.py`; registry facts — `capability_registry.py`.

## Author response

Gameplay Author возвращает metadata, concept, claim-backed `runtimeContract` и `runtimeProgram` схемы `infini.runtime-program.authoring.v1`.

`runtimeProgram` содержит:

- `apiVersion` и `schema`;
- `primaryEntityId` — один точный существующий authored entity id;
- `entities[]` — явные ids и low-level kinds;
- `bindings[]` — явные `input + action + target`;
- `calls[]` — явные `fn + target + params`.

Author bindings/calls **не содержат `role`**. Код не определяет primary entity по input, capability, kind, имени, tooltip или category. После валидации compiler только материализует wire role из exact equality:

```text
binding.target == runtimeProgram.primaryEntityId -> primary
otherwise                                      -> secondary
```

Это mandatory technical projection уже authored identity, а не выбор механики и не authoring compression.

## Composition

Bindings связывают конкретный input с конкретным action/target. Calls прикрепляют одну capability к одной entity. Cross-entity behavior использует typed references. Movement, controller, damage, input, lifecycle, targeting и event actions остаются независимыми решениями модели; whole-weapon macro отсутствует.

Event producer alternatives выводятся только из `EVENT_KIND_REGISTRY` и `ENTITY_KIND_REGISTRY.base_events`. Author или Repair выбирает один полный вариант и явно пишет необходимые call/binding; код не вставляет producer автоматически.

Полный generated registry inventory: [`LOW_LEVEL_CAPABILITY_INVENTORY_RU.md`](LOW_LEVEL_CAPABILITY_INVENTORY_RU.md).

## Validation и compilation

Validator проверяет strict shape, references, target kinds, slots, dependencies, event producers, cycles и budgets. Он сообщает exact paths и не выбирает замену.

Compiler пишет только declared final-wire paths и создаёт receipts. Global receipts доказывают authored inputs и exact output; capability receipts доказывают exact call delivery. Numeric opcode — кодирование уже выбранного capability name.

## Repair

Gameplay Repair получает frozen accepted state, exact errors, finite registry-derived alternatives и exact create/retarget/delete permissions. Filter принимает только разрешённые leaves/nodes; затем canonical validator обязан подтвердить исчезновение исходных требований. Полный protocol: [`TARGETED_REPAIR_PROTOCOL_RU.md`](TARGETED_REPAIR_PROTOCOL_RU.md).

## Visual/VFX

Visual roles losslessly выводятся из accepted entity kinds. Visual и VFX могут ссылаться только на accepted runtime entities/events и не могут добавлять gameplay.

## Проверка projection

```bash
python tools/generate_lowery.py --check
python tools/generate_low_level_runtime_docs.py --check
python -m pytest -q LocalGenerator/tests/test_runtime_authoring_change_locality.py LocalGenerator/tests/test_low_level_runtime_contract_v5.py LocalGenerator/tests/test_low_level_three_stage_pipeline.py
```
