# Зарядка, орбита и отскоки

Это независимые current primitives. Их композицию выбирает Author; код не восстанавливает weapon family. Формы параметров и точные диапазоны принадлежат registry и [generated inventory](../generated/LOW_LEVEL_CAPABILITY_INVENTORY_RU.md).

## Зарядка

`charge.duration` задаёт секунды до полного заряда; optional `autoReleaseAge` — active age автоматического release. Active use требует явно выбранного `item_use.channel=true`. `charge.releaseEffect` независимо выбирает усиления и обязательную `launchSpeed` в блоках/с.

`damageMultiplier` 1…4, `knockbackMultiplier` 0…4 и `speedMultiplier` 0.1…4 интерполируются от 1 к выбранному значению. Объявленный пропуск multiplier означает 1 с receipt. Присутствующий releaseEffect всё равно устанавливает launch velocity даже при единичных коэффициентах; отсутствие объекта не создаёт этот эффект. Пауза lifetime выбирается отдельным `pauseLifetimeWhileCharging`; без неё обычный countdown продолжается.

Damage/knockback масштабируются один раз по фактическим значениям projectile. Нулевая база остаётся нулевой, hydration/ExtraAI не усиливает повторно. Контактный урон и owner guards не выводятся из charge: для них есть `gate_contact` и `set_owner_control`.

Индикатор возле прицела читает текущий charge component физического снаряда. Полный заряд помечает готовность; повторное чтение/hydration не повторяет сигнал того же поколения. UI не меняет gameplay release и `channel_complete`; меню, карта и hidden UI не накапливают отложенный сигнал.

## Орбита

`orbit` явно задаёт anchor, `radius` в блоках, signed `radiansPerSecond`, `anglePhase` и `identityAnglePhase`. Positive rate вращает по часовой стрелке на экране; 0 сохраняет фазу. Lowering делит angular rate на `60 × updatesPerTick`. Это мировая скорость, не зависимость от launch velocity.

Anchor выбирается из owner center/mounted center/front hand. Орбита не включает terrain avoidance, arm pose, lifetime или owner cancellation. Tile collision задаётся отдельно и должна быть допустима для выбранной композиции.

## Отскоки

`projectile_collision.bounceSpeedRetention` — коэффициент 0…1 только столкнувшейся компоненты скорости. 1 отражает без потерь, 0 останавливает эту ось; касательная компонента не меняется. Пропуск — объявленная нейтраль 1. `bounceCount=N` разрешает N отражений; следующий контакт отдаёт native уничтожение. Возврат, friction, gravity и explosion не выводятся из bounce.

`OnTileCollide(oldVelocity)` получает скорость до столкновения; native velocity уже содержит collision result. Отражение сравнивает изменившиеся оси. Явный `return_when.onTileCollision` — отдельный latch, не сохранённый bundled early-return opcode.

## Проверка

Проверяй outgoing Author schema/cards, compiler receipts, strict DTO, frozen Repair и actual native hooks: charge release/hydration, signed orbit при разных N, collided-axis reflection. Native API: [ModProjectile.OnTileCollide](https://docs.tmodloader.net/docs/stable/class_mod_projectile.html), [Projectile.extraUpdates](https://docs.tmodloader.net/docs/stable/class_projectile.html). Build/CPU, GPU и host-client игра — разные результаты по [TESTING](../../development/TESTING_RU.md).
