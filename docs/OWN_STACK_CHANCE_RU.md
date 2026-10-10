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
