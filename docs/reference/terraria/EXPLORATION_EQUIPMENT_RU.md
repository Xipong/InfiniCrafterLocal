# Исследовательская экипировка

Все параметры ниже — независимые optional-параметры `configure_accessory`.
Они исполняются только через `equipped → equip_passive`. Пропуск остаётся
пропуском в сохранённом wire; false/0 не выдаёт эффект. Имена предметов не
выбирают механики. Проекция — identity Alias Lowering с exact receipt на каждый лист.

## Рыбалка

`fishingPower` (0–100 целых очков) прибавляет `Player.fishingSkill` до
нативных множителей удочки, наживки, погоды и времени. `fishingLine`
включает нативную защиту от обрыва лески; `lavaFishing` — возможность
рыбалки в лаве, без иммунитета к лаве. `fishingSonar` включает предпросмотр
улова, `fishingCrates` — нативный модификатор шанса ящиков.
Ни один параметр не создаёт удочку, наживку, поплавок или добычу.

Проверки: `test_exploration_equipment.py` проверяет реальный Author-пакет,
schema, compiler, receipts, strict wire и frozen Repair; native check
`Exploration Fishing` проходит DTO/network roundtrip и UpdateAccessory,
проверяет GetFishingConditions, native reset и отказ неверных чисел.
Это CPU-проверки, не запуск игрового мира или multiplayer.

## Pickup

`lifePickup` → `Player.lifeMagnet`: увеличенный сбор сердец.
`manaPickup` → `Player.manaMagnet`: увеличенный сбор звёзд маны.
`coinPickup` → `Player.goldRing`: увеличенный сбор монет.
`treasurePickup` → `Player.treasureMagnet`: увеличенный сбор предметов.

Каждый флаг независим: выбор одного не включает остальные. Эффект выдаётся
на нативном проходе экипировки и снимается ResetEffects после снятия предмета.
Параметры отображаются в локализованных tooltip, проходят strict wire и exact receipts.

## Vision

`treasureVision` → `Player.findTreasure`: подсветка сокровищ.
`dangerVision` → `Player.dangerSense`: подсветка опасностей.
`creatureVision` → `Player.detectCreature`: подсветка существ.
`nightVision` → `Player.nightVision`: ночное зрение.

Каждый флаг независим: выбор одного не включает остальные. Эффект выдаётся
на нативном проходе экипировки и снимается ResetEffects после снятия предмета.
Параметры отображаются в локализованных tooltip, проходят strict wire и exact receipts.

## Instruments

`fishingInfo` → `Player.accFishFinder`: индикатор силы рыбалки.
`weatherInfo` → `Player.accWeatherRadio`: индикатор погоды.
`moonInfo` → `Player.accCalendar`: индикатор фазы луны.
`enemyInfo` → `Player.accThirdEye`: число врагов рядом.
`speedInfo` → `Player.accStopwatch`: индикатор скорости.
`oreInfo` → `Player.accOreFinder`: индикатор ценных ресурсов.
`rareCreatureInfo` → `Player.accCritterGuide`: индикатор редких существ.
`killCountInfo` → `Player.accDreamCatcher`: счётчик убийств.

Каждый флаг независим: выбор одного не включает остальные. Эффект выдаётся
на нативном проходе экипировки и снимается ResetEffects после снятия предмета.
Параметры отображаются в локализованных tooltip, проходят strict wire и exact receipts.

## Survival

`potionCooldown` → `Player.pStone`: нативное сокращение перезарядки лечения.
`autoManaPotion` → `Player.manaFlower`: автоматическое зелье маны.
`restingRecovery` → `Player.shinyStone`: нативное восстановление здоровья в покое.
`extendedInvulnerability` → `Player.longInvince`: продлённая нативная неуязвимость.

Каждый флаг независим: выбор одного не включает остальные. Эффект выдаётся
на нативном проходе экипировки и снимается ResetEffects после снятия предмета.
Параметры отображаются в локализованных tooltip, проходят strict wire и exact receipts.
