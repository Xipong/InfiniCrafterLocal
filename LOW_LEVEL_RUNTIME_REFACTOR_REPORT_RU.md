# InfiniCrafterLocal 0.4.241 — отчёт тотального low-level runtime refactor

> Исторический отчёт о первоначальном переходе на v5, **не текущий verdict о полной capability parity**. Числа тестов, параметров и описание доступного SDK ниже относятся к тому snapshot. Актуальные источники: `PROJECT_ARCHITECTURE_RU.md`, generated `docs/PRIMITIVE_PARITY_RU.md` и `docs/LOW_LEVEL_CAPABILITY_INVENTORY_RU.md`; C# headless/build отдельно от игрового и сетевого acceptance.

## Итог

Активная архитектура переведена с whole-weapon Author IR на конечный `runtimeProgram`:

```text
parent facts + balance corridor + полный capability catalog
  -> Gameplay Author (1 baseline call)
  -> strict Author validator
  -> lossless technical compiler
  -> strict v5 wire
  -> Visual Director (1 baseline call)
  -> VFX Director (1 baseline call)
  -> C# typed DTO/executors
```

Успешный baseline содержит ровно **3 LLM-вызова**. Gameplay/Visual/VFX Repair остаются условными и запускаются только после отказа validator соответствующей стадии.

## Что удалено

- Author-visible `perform_melee_attack`, `fire_ranged_weapon`, `cast_magic_weapon`, whole-weapon `deploy_sentry` и universal root-macro.
- `root_lowering.py`, family/profile route tables, reducers/singletons старого normalized root.
- `AttackSpec`, `runtimeFamily`, `weaponFamily` как gameplay authority.
- C# family/child/sentry/charge/barrage partials и policies, которые склеивали независимые решения.
- старые schema/cache/replay/fingerprint/import paths; v5 не мигрирует прежние generated items.
- tests/docs/agent metadata, требовавшие historical weapon-IR parity.
- placeholder-пути для обязательного PNG.

Исторический тотальный рефактор сократил старое дерево за счёт удаления weapon-IR, replay/golden и compatibility surfaces. Текущая v0.4.241 поверх Repair-complete baseline добавляет Terraria vocabulary/gates/docs и физически удаляет последний мёртвый effect-archetype catalog; точная delta приведена в standardization verification.

## Что переиспользовано и разложено

Старые executors не заменены игрушечной VM. Из них извлечены и сохранены:

- item stats/use/contact/consumption/resources/tool/placeable/accessory/armor;
- explicit spawn, damage, lifetime, hitbox, tile collision, pierce/bounce/immunity;
- 20 movement controllers, включая straight/homing/gravity/orbit/boomerang/flail/yoyo/whip/forward-retract;
- channel beam, charge/release, stationary target-and-fire;
- typed child/event spawn, status, AoE, chain, pull, heal и owner movement;
- owner/server authority, child budgets и `SendExtraAI`/`ReceiveExtraAI` seam;
- entity-level Visual и exact `entityId + event` VFX hooks.

Предварительно склеенные композиции `spear`, `bow`, `staff`, `sentry` не сохранены.

## Новый capability contract

Live registry: `LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py`.

- **52 capabilities**;
- **7 entity kinds**;
- **4 inputs**;
- **5 binding actions**;
- **10 events**;
- **185 typed parameters**, из них **143/143 numeric bounded**;
- **2 typed cross-entity references**;
- **257 exact final-wire paths**;
- **100 exact outputs** трёх global technical lowerers;
- **52 Python→C# vertical witnesses**.

Registry определяет types/ranges/units/semantic types, target kinds, component slots, exclusivity, position ownership, dependencies, emitted/accepted events, authority, budgets, compiler callable, C# method symbols и exact wire delivery.

### Оценка машиночитаемости

- **Структура и проверяемость: 10/10.** Объявленный контракт полностью замкнут audit/parity/mutation gates.
- **Однозначность для LLM: 9/10.** Нет family router и semantic defaults; prompt содержит все 52 capabilities в одном запросе.
- **Выразительность текущего runtime: 8/10.** Multi-entity странные предметы работают, но допускается один movement slot и один controller slot на entity; arbitrary ECS/VM намеренно отсутствует.
- **Доказанность внутри Terraria: неполная.** В данном контейнере отсутствуют .NET/tModLoader и внешние DLL, поэтому статическая C# доставка доказана, а реальная сборка/игровой smoke не заявляются.

После аудита дополнительно добавлен technical marker `runtimeProgram.itemUse.configured`. Теперь C# может отличить реально authored `configure_item_use` от DTO-default. C# также fail-closed отклоняет `apply_item_effects`, `place_item` и `equip_passive`, если соответствующий compiled component отсутствует.

## Gameplay validation и Repair

Validator проверяет shape, capability IDs, types, ranges, entity/action refs, target kinds, exclusive inputs, component slots, position drivers, event producers, cycles/depth/spawn budgets и binding dependencies. Он не выбирает замену.

Conditional Gameplay Repair переведён на leaf-local frozen protocol:

- модели отправляются exact path-level errors, broken fragments, valid dependency context и compact immutable index, но не полный старый item/history;
- capability catalog сужается до direct blockers, обязательного support closure и уже существующих сломанных capabilities;
- все 33 semantic validator codes имеют явную `REPAIR_ERROR_POLICY`;
- существующие корректные значения frozen; из полного возвращённого узла применяются только exact broken/mandatory missing leaves;
- попытки изменить соседний damage/target/component либо добавить optional design fields игнорируются и аудируются вместо отмены полезного Repair;
- registry/runtime defects не скрываются LLM Repair;
- после tolerant merge выполняется полная валидация и обычные compile/wire gates.

Visual и VFX Repair используют ту же frozen-first семантику для exact invalid fields/rows. Подробности и ограничения: `docs/TARGETED_REPAIR_PROTOCOL_RU.md` и `TARGETED_REPAIR_AUDIT_RU.md`.

## Visual и VFX

Visual получает только accepted runtime entities/roles и parent facts. Каждый mandatory `baked_sprite` привязан к конкретной entity; missing PNG является failure.

VFX получает конечный event inventory и создаёт slots только для реально существующих `entityId + event`. Gameplay через VFX не меняется.

## C# runtime

- `RuntimeProgramSpec.cs`: strict v5 DTO, refs, events, graph, budgets, name/opcode parity, action/component dependencies.
- `GeneratedItemData*.cs`: точная projection authored item/equipment values.
- `GeneratedItem.cs`: binding dispatch без category/family routing.
- `GeneratedProjectile*.cs`: один bounded entity executor с explicit movement/controller/event data.
- `RuntimeProgramExecutor.cs`: finite event-action switch.
- неизвестные fields/opcodes fail closed; arbitrary code/reflection scripting отсутствуют.

## Non-archetypal acceptance

Восемь программ проходят author→validator→compiler→strict wire без единственной weapon family:

1. меч с буквально прикреплённым верстаком и дочерними гвоздями;
2. зонт + граната;
3. дверь на цепи;
4. возвращающееся зелье;
5. инструмент/удочка с поддержанной placeable-композицией;
6. held shield + независимый secondary disc;
7. primary held + alternate deployed entity;
8. equipment/tool + combat composition.

## Остаточные риски

1. Реальная C# компиляция не выполнена: в контейнере нет `dotnet`, tModLoader install, `ParticleLibrary.dll`, `Luminance.dll`.
2. Singleplayer/host-client/Calamity runtime smoke не выполнены по той же причине.
3. Provider credentials отсутствуют, поэтому реальные три LLM happy-path crafts не запускались; prompt/schema/stage-accounting проверены fixtures.
4. Ruff, Pyright и Hypothesis недоступны в установленном окружении и отсутствуют в доступном package index.
5. Точный patch release stable tModLoader нельзя определить без installed environment; source ограничен stable/1.4.4 API patterns и не использует 1.4.5-only API.

## Terraria/tModLoader standardization

v0.4.241 дополнительно сводит exact технические значения к canonical stable tModLoader vocabulary, удаляет gameplay aliases и последний мёртвый effect/weapon router. Полный one-to-one mapping и оставшиеся не-gameplay aliases находятся в `lowery.md`; граница собственного proxy runtime описана в `docs/TERRARIA_TMODLOADER_STANDARDIZATION_RU.md`.
