# Вероятность расхода собственного стека

`usePolicy.stackConsumeChancePercent` — optional integer 0..100 только для активной
`primary_use`/`alternate_use` binding с `stackCost=1` и action, отличным от `place_item`.
Отсутствие оставляет прежний буквальный расход. Author задаёт эту игровую возможность явно;
переданное значение копируется в тот же wire binding без clamp, inference или выбора
механики. Класс преобразования — lossless identity projection. Receipt связывает
исходный binding ID, authored probability и итоговый индекс после сортировки bindings.

```json
{"id":"throw","input":"primary_use","usePolicy":{"action":{"kind":"spawn_entity","targetId":"projectile"},"stackCost":1,"stackConsumeChancePercent":35,"contactDamage":false}}
```

После завершённой native активации ConsumeItem выполняет один `Next(100) < 35`.
0 и 100 не двигают RNG. Exact player/item/data/binding/tick receipt расходуется один
раз; повторный ConsumeItem не бросает шанс заново. Ошибка pure mobility не расходует
предмет, даже при 100. Поздний отказ spawn сохраняет прежнюю семантику completed use
(не откатывает уже выполненные events/native costs), а не обещает общий rollback.

## Независимая композиция с именованными эффектами

`apply_item_effects.action.effectGroupId` выбирает exact named effects, а
`usePolicy.stackConsumeChancePercent` независимо задаёт стоимость завершённого use.
Выбор группы не меняет вероятность; вероятность не выбирает и не дополняет группу.
Например, primary healing с шансом 0 сохраняет предмет после лечения, а alternate
mana с шансом 100 расходует его после собственного завершённого use. Native healing
по-прежнему выполняет Terraria; RNG не является условием выполнения эффекта.
Pure mobility проверяется по выбранной группе: отказ movement не расходует стек
даже при 100; успешная другая binding не может предоставить ей outcome receipt.
Mixed effects сохраняют прежнюю completed-use семантику без общего rollback.

Оба optional поля имеют отдельные identity receipts внутри одного
`audit_compiler_receipts`. Они связываются с exact source binding ID и итоговым
индексом после сортировки; missing/duplicate/coherent forged claims остаются RED.
Receipt completed use (`_stackChanceUseOutcome`) и dedup held refresh
(`_heldEffectRefresh`) принадлежат разным native state lanes: удерживание группы
не заменяет доказательство завершённого active use. Frozen Repair invalid input,
probability или group selector сохраняет остальные lanes и все effect definitions.
Оба provider formats и raw malformed wire покрыты combined regressions в
`test_item_effect_groups.py`. Это Python/compiler и source-consumer доказательство;
combined native execution остаётся отдельной проверкой parent native runner.

[Точный контракт именованных эффектов](NAMED_ITEM_EFFECT_GROUPS_RU.md).

Placement полностью исключён: любой chance field, даже 100, отвергается. Native
changed-cell receipt и world placement escrow/возврат не участвуют в RNG. Reusable
placement hybrid с вероятностью меньше 100 по-прежнему требует `maxStack=1`.
`Item.ammo`, native PickAmmo saving и accessory ammoSaveChance независимы.

Полный Author schema выделяет cost=0 и cost=1 branches; optional probability есть
только во второй. Provider nullable projection восстанавливает omission; literal
Author/wire null отвергается. Repair меняет только invalid leaf, не дополняет
пропущенную вероятность и не редактирует frozen contact/action siblings.

Проверки: `test_binding_stack_chance.py`, существующие binding/receipt/Repair gates;
native seam `EngineRuntimeChecks.StackChance.cs` подключён к существующему runner.
В среде подготовки PR нет .NET/tModLoader, поэтому build и native execution —
`notRun`, а не пройденный игровой тест.
