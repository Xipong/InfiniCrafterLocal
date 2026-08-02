# Low-level Runtime Authoring — projection

> Не является владельцем контракта. Каноническая замороженная граница, owner routing и generated lowering manifest находятся в [`../lowery.md`](../lowery.md).
> Exact Author/Repair JSON shape владеет `LocalGenerator/infini_local/core/runtime_authoring/program_schema.py`; registry facts — `capability_registry.py`.

## Author response

Gameplay Author возвращает metadata, concept, claim-backed `runtimeContract` и `runtimeProgram` схемы `infini.runtime-program.authoring.v4`.

`runtimeProgram` содержит:

- `apiVersion` и `schema`;
- `primaryEntityId` — один точный существующий authored entity id, владелец lifecycle/held representation;
- `entities[]` — явные ids и low-level kinds;
- `bindings[]` — явные `input + usePolicy`, где атомарный `usePolicy` содержит `action`, `stackCost`, `contactDamage`;
- `calls[]` — явные `fn + target + params`.

Author bindings/calls **не содержат `role`**. Код не определяет primary entity по input, capability, kind, имени, tooltip, category, урону или факту spawn. По умолчанию held/lifecycle owner — единственный `item_body`; projectile выбирается только когда Author явно переносит в него lifecycle/held representation. После валидации compiler только материализует wire role из exact equality:

```text
binding.usePolicy.action.targetId == runtimeProgram.primaryEntityId -> primary
otherwise                                                           -> secondary
```

Это mandatory technical projection уже authored identity, а не выбор механики и не authoring compression.

## One root, независимые use lanes

Один exclusive input имеет один root binding, но это не означает «одну главную атаку». `usePolicy.contactDamage` — независимая item-body lane; `usePolicy.action` — независимый root effect. Поэтому canonical Starfury-like tuple выражается одной транзакцией:

```json
{
  "input": "primary_use",
  "usePolicy": {
    "action": {"kind": "spawn_entity", "targetId": "falling_star"},
    "stackCost": 0,
    "contactDamage": true
  }
}
```

При `primaryEntityId=item_body` этот use одновременно сохраняет Terraria item hitbox и создаёт projectile; projectile не получает `heldProj` и ownership из-за урона. Если же все active bindings спавнят одну и ту же entity, `contactDamage=false`, а `configure_item_use.hideUseGraphic=true`, item-body вообще не представляет use и exact spawn target обязан стать lifecycle/held owner. Projectile-owned flail/yoyo/whip/holdout также может быть выбран явно; `place_item`, `hold` и `equipped` не могут включать contact damage, потому что соответствующие consumers его не исполняют.

Это engine invariant, а не classifier: никаких решений по имени, tooltip, weapon/tool category или progression. Необычные vanilla/modded предметы используются как edge-case corpus; допустимость определяется только явным lifecycle/use tuple и реальными consumers.

Проверяемые источники поведения: [Starfury — Official Terraria Wiki](https://terraria.wiki.gg/wiki/Starfury), [Flails — Official Terraria Wiki](https://terraria.wiki.gg/wiki/Flails). API/runtime authority остаются за текущим tModLoader source и текущими Python/C# consumers; executable fixtures: `workbench_blade` (body + projectile) и `door_on_chain` (projectile-owned flail).

## Composition

Bindings связывают конкретный input с одним атомарным `usePolicy`. Calls прикрепляют одну capability к одной entity. Cross-entity behavior использует typed references. Movement, controller, damage, input, lifecycle, targeting, body contact и event actions остаются независимыми решениями модели; whole-weapon macro отсутствует.

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
