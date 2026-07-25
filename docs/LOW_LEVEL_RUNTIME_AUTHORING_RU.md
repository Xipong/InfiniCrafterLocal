# Low-level Runtime Authoring

## Author response

Gameplay Author returns metadata, concept, claim-backed runtime contract and:

```json
{
  "runtimeProgram": {
    "apiVersion": "infini.runtime-program.v5",
    "schema": "infini.runtime-program.authoring.v1",
    "entities": [{"id": "item", "kind": "item_body"}],
    "bindings": [],
    "calls": []
  }
}
```

IDs are stable lowercase snake_case. Exactly one `item_body` exists. Every projectile entity explicitly receives spawn, lifetime, hitbox, collision and a position driver where its kind requires one.

## Composition

Bindings map a concrete input to a concrete action and entity. Calls attach one capability to one entity. Cross-entity behavior uses typed parameters such as `shotEntity`/`entity`; validator checks target kinds and graph depth.

Movement, controller, damage, targeting, child spawn, item effects and equipment are independent decisions. No single call means «make a spear» or «make a sentry».

## Validation

Validator checks strict shape, IDs, target kinds, one-per-slot components, dependencies, event producers, illegal cycles, child depth/count, periods, lifetime and authority. It reports exact paths. It never chooses what to keep or substitutes a weapon family.

## Compiler

Compiler writes only declared final-wire paths and emits receipts. Numeric opcodes are technical encodings of already selected names. The wire program remains entity/component/event-based.

## Repair

Gameplay Repair возвращает narrow upsert/delete patch. Deterministic code выводит exact mutable leaf paths, missing-dependency create policy и минимальный blocker capability subset. Модель может вернуть полный broken node для удобства, но frozen merge применяет только reported broken/mandatory missing fields. Изменения валидных старых значений и необязательные additions вне scope игнорируются и аудируются, не отменяя полезное исправление. Полный предыдущий item/history не отправляется. See `TARGETED_REPAIR_PROTOCOL_RU.md`.

## Visual/VFX

Visual roles are derived mechanically from accepted entity kinds. VFX slots must reference an accepted entity and one of its actual runtime events. Neither stage can add gameplay.
