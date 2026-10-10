# Parity примитивов Author ↔ Terraria/tModLoader

> Generated: [`tools/generate_primitive_parity.py`](../tools/generate_primitive_parity.py). Не редактировать вручную; [refresh/check](#refresh).
> Sources: [capability_registry.py](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py) — имена, единицы, диапазоны, wire и фазы; [primitive_loss_audit.py](../LocalGenerator/infini_local/qa/primitive_loss_audit.py) — C# executable-поля из AST. [Lowery](../lowery.md) — boundary/owners; [inventory](LOW_LEVEL_CAPABILITY_INVENTORY_RU.md) — полный каталог.

**Навигация:** [история](#history) · [machine audit](#audit) · [equipment](#equipment) · [events/runtime](#events) · [невосстановленное](#unsupported) · [extraUpdates units](#units) · [границы проверки](#limits) · [обновление](#refresh).

<a id="history"></a>

## Историческое сопоставление

- `019ff01` (до low-level v5): `LocalGenerator/infini_local/core/runtime_authoring.py`, `effect_catalog.py`. `accessory_effect` и `armor_effect` допускали raw DTO-названия и смешивали десятичные доли (например `meleeDamage=0.15`), points и bool; существовали текстовые `archetype`/`setBonusText` и whole-weapon pattern cards. Это не целевой Author API.
- `25caddf` (импорт v5): явные item/entity/binding/event calls вместо оружейных macros. Часть executable-полей `AccessorySpec`/`ArmorSpec` осталась в C#, но была потеряна из model-visible каталога.
- Сейчас один registry выдаёт Author JSON schema, компактные карточки, validator-параметры, exact wire paths, технические receipts, C# safety bounds и таблицы ниже. Legacy C# DTO — цель проекции, а не второе описание механики.

<a id="audit"></a>

## Результат machine loss audit

Для каждой поверхности ниже C# DTO/исполняемые поля классифицированы. Исключения с причинами поддерживаются в `primitive_loss_audit.py`, не в LLM prompt.

- `equipment`: **PASS**.
- `events`: **PASS**.
- `runtime components`: **PASS**.
- `item gameplay`: **PASS**.
- `structural runtime/visual`: **PASS**.

<a id="equipment"></a>

## Equipment — значения, phase и authority

`additive_percent` — авторский процент прибавки к additive компоненте StatModifier (15 → +0.15), не итоговый множитель урона. `percentage_points` — сдвиг шанса в п.п.; `probability_percent` — вероятность/100. `defense_points`, `life_points`, `slots` и `pixels_per_tick` не масштабируются. Отрицательные значения разрешены только там, где указан отрицательный минимум. Ноль/false/пустая строка — нейтральны, если не оговорено иначе. Item.defense проектируется в `ApplyToItem`: Terraria сама применяет защиту, equip-hook не удваивает её.

Author schema ограничивает новые значения всех примитивов; C# Normalize сохраняет **только исторические DTO clamps**, перечисленные в `runtime_minimum`/`runtime_maximum` registry и `GeneratedEquipmentBounds.g.cs`. В таблицах они обозначены `legacy clamp`; отсутствие этой пометки означает отсутствие такого исторического clamp. Поля без него не сужаются для уже сохранённых legacy recipes. Это не разрешение Author выбирать значения вне своей схемы.

### `configure_accessory`

| Author | Действие / engine semantics | Единица | Neutral | Author range | Wire DTO | Фаза |
|---|---|---|---|---|---|---|
| defensePoints | Add to Item.defense; Terraria applies it, not an extra equip-hook adjustment | defense_points | 0 | -50…200<br>legacy clamp: -100…500 | accessory.defense | ModItem.UpdateAccessory |
| maxLifePoints | Add maximum life | life_points | 0 | -200…1000<br>legacy clamp: -500…5000 | accessory.maxLife | ModItem.UpdateAccessory |
| maxManaPoints | Add maximum mana | mana_points | 0 | -200…1000<br>legacy clamp: -500…5000 | accessory.maxMana | ModItem.UpdateAccessory |
| lifeRegenHpPerSecond | Add signed HP/s regeneration contribution before other Terraria effects; +1 HP/s writes +2 Player.lifeRegen engine units, -1 HP/s writes -2; 0 adds nothing | HP/s | 0 | -50…100<br>legacy clamp: -120…200 | accessory.lifeRegen | ModItem.UpdateAccessory |
| manaRegenBonusPoints | Add raw Player.manaRegenBonus points; 0 adds nothing, not mana/s | engine units: manaRegenBonus points | 0 | -100…200<br>legacy clamp: -120…200 | accessory.manaRegen | ModItem.UpdateAccessory |
| moveSpeedBonusPercent | Add percent/100 to Player.moveSpeed | additive_percent | 0 | -90…300<br>legacy clamp: -0.9…3 | accessory.movementSpeed /100 | ModItem.UpdateAccessory |
| maxRunSpeedBonusPxPerTick | Add to Player.maxRunSpeed, subject to other Terraria movement limits | pixels_per_tick | 0 | -5…20 | accessory.maxRunSpeed | ModItem.UpdateAccessory |
| jumpSpeedBonusPxPerTick | Add to Player.jumpSpeedBoost (positive raises jump speed) | pixels_per_tick | 0 | -5…20 | accessory.jumpSpeed | ModItem.UpdateAccessory |
| genericCritChancePercentagePoints | Add percentage points to generic critical chance | percentage_points | 0 | -100…100<br>legacy clamp: -100…100 | accessory.genericCrit | ModItem.UpdateAccessory |
| genericAttackSpeedBonusPercent | Add percent/100 to generic attack speed | additive_percent | 0 | -90…300 | accessory.attackSpeed /100 | ModItem.UpdateAccessory |
| genericKnockbackBonusPercent | Add percent/100 to generic StatModifier knockback; not flat points | additive_percent | 0 | -90…300 | accessory.knockback /100 | ModItem.UpdateAccessory |
| minionSlotsBonus | Add minion slots | slots | 0 | 0…20<br>legacy clamp: 0…20 | accessory.minionSlots | ModItem.UpdateAccessory |
| sentrySlotsBonus | Add sentry slots | slots | 0 | 0…20<br>legacy clamp: 0…20 | accessory.sentrySlots | ModItem.UpdateAccessory |
| manaCostReductionPercentagePoints | Subtract percent/100 from Player.manaCost factor, floored at 0.1 | percentage_points | 0 | 0…90 | accessory.manaCostReduction /100 | ModItem.UpdateAccessory |
| ammoSaveChancePercent | Equipped owner's ammo saving chance via Player.CanConsumeAmmo for any weapon; equipped item chances combine as 1−product(1−p) | probability_percent | 0 | 0…99 | accessory.ammoSaveChance /100 | ModItem.UpdateAccessory |
| aggroPoints | Add raw Player.aggro engine points (negative reduces targeting); not a probability or radius | engine units: aggro points | 0 | -1000…1000 | accessory.aggro | ModItem.UpdateAccessory |
| damageReductionPercentagePoints | Add percent/100 to Player.endurance damage reduction | percentage_points | 0 | 0…75<br>legacy clamp: 0…0.75 | accessory.endurance /100 | ModItem.UpdateAccessory |
| genericArmorPenetrationPoints | Add flat armor penetration points to DamageClass.Generic; not damage percent | armor_points | 0 | 0…100 | accessory.armorPenetration | ModItem.UpdateAccessory |
| whipRangeBonusPercent | Add percent/100 to Player.whipRangeMultiplier | additive_percent | 0 | -90…300 | accessory.whipRange /100 | ModItem.UpdateAccessory |
| taggedSummonSourceDamageBonusPercent | Multiply summon projectile source damage by 1+percent/100 only against an NPC tagged by this owner's generated whip | source_damage_percent | 0 | 0…300 | accessory.summonTagDamage /100 | ModItem.UpdateAccessory |
| lightStrength | Client-only RGB light coefficient multiplying lightColor; not tile radius; requires lightColor when positive | engine units: RGB coefficient | 0 | 0…1.5<br>legacy clamp: 0…1.5 | accessory.lightStrength | ModItem.UpdateAccessory |
| lightColor | Explicit equipped light color | runtime_color |  | white/red/orange/yellow/green/cyan/blue/purple/pink/gray/black | accessory.lightColorName | ModItem.UpdateAccessory |
| fallDamageImmune | Prevent fall damage while equipped | bounded_text | False | boolean | accessory.fallDamageImmune | ModItem.UpdateAccessory |
| lavaImmune | Grant lava immunity while equipped | bounded_text | False | boolean | accessory.lavaImmune | ModItem.UpdateAccessory |
| waterWalk | Walk on water while equipped | bounded_text | False | boolean | accessory.waterWalk | ModItem.UpdateAccessory |

Authority: `owner_execute_sync`; техническая фаза/сетевая роль выбираются runtime, не LLM.

### `configure_armor`

| Author | Действие / engine semantics | Единица | Neutral | Author range | Wire DTO | Фаза |
|---|---|---|---|---|---|---|
| slot | Armor equip slot | bounded_text | None | head/body/legs | armor.slot | C# normalized item projection |
| setKey | Exact authored set key (empty when no matching set is intended) | bounded_text |  | ^[a-z0-9_]{0,48}$ | armor.setKey | C# normalized item projection |
| defensePoints | Add to Item.defense; Terraria applies it, not an extra equip-hook adjustment | defense_points | 0 | 0…200<br>legacy clamp: 0…500 | armor.defense | ModItem.UpdateEquip |
| maxLifePoints | Add maximum life | life_points | 0 | -200…1000<br>legacy clamp: -500…5000 | armor.maxLife | ModItem.UpdateEquip |
| maxManaPoints | Add maximum mana | mana_points | 0 | -200…1000<br>legacy clamp: -500…5000 | armor.maxMana | ModItem.UpdateEquip |
| lifeRegenHpPerSecond | Add signed HP/s regeneration contribution before other Terraria effects; +1 HP/s writes +2 Player.lifeRegen engine units, -1 HP/s writes -2; 0 adds nothing | HP/s | 0 | -50…100 | armor.lifeRegen | ModItem.UpdateEquip |
| manaRegenBonusPoints | Add raw Player.manaRegenBonus points; 0 adds nothing, not mana/s | engine units: manaRegenBonus points | 0 | -100…200 | armor.manaRegen | ModItem.UpdateEquip |
| moveSpeedBonusPercent | Add percent/100 to Player.moveSpeed | additive_percent | 0 | -90…300<br>legacy clamp: -0.9…3 | armor.movementSpeed /100 | ModItem.UpdateEquip |
| maxRunSpeedBonusPxPerTick | Add to Player.maxRunSpeed, subject to other Terraria movement limits | pixels_per_tick | 0 | -5…20 | armor.maxRunSpeed | ModItem.UpdateEquip |
| jumpSpeedBonusPxPerTick | Add to Player.jumpSpeedBoost (positive raises jump speed) | pixels_per_tick | 0 | -5…20 | armor.jumpSpeed | ModItem.UpdateEquip |
| genericCritChancePercentagePoints | Add percentage points to generic critical chance | percentage_points | 0 | -100…100<br>legacy clamp: -100…100 | armor.genericCrit | ModItem.UpdateEquip |
| genericAttackSpeedBonusPercent | Add percent/100 to generic attack speed | additive_percent | 0 | -90…300 | armor.attackSpeed /100 | ModItem.UpdateEquip |
| genericKnockbackBonusPercent | Add percent/100 to generic StatModifier knockback; not flat points | additive_percent | 0 | -90…300 | armor.knockback /100 | ModItem.UpdateEquip |
| minionSlotsBonus | Add minion slots | slots | 0 | 0…20 | armor.minionSlots | ModItem.UpdateEquip |
| sentrySlotsBonus | Add sentry slots | slots | 0 | 0…20 | armor.sentrySlots | ModItem.UpdateEquip |
| manaCostReductionPercentagePoints | Subtract percent/100 from Player.manaCost factor, floored at 0.1 | percentage_points | 0 | 0…90 | armor.manaCostReduction /100 | ModItem.UpdateEquip |
| ammoSaveChancePercent | Equipped owner's ammo saving chance via Player.CanConsumeAmmo for any weapon; equipped item chances combine as 1−product(1−p) | probability_percent | 0 | 0…99 | armor.ammoSaveChance /100 | ModItem.UpdateEquip |
| aggroPoints | Add raw Player.aggro engine points (negative reduces targeting); not a probability or radius | engine units: aggro points | 0 | -1000…1000 | armor.aggro | ModItem.UpdateEquip |
| damageReductionPercentagePoints | Add percent/100 to Player.endurance damage reduction | percentage_points | 0 | 0…75 | armor.endurance /100 | ModItem.UpdateEquip |
| genericArmorPenetrationPoints | Add flat armor penetration points to DamageClass.Generic; not damage percent | armor_points | 0 | 0…100 | armor.armorPenetration | ModItem.UpdateEquip |
| whipRangeBonusPercent | Add percent/100 to Player.whipRangeMultiplier | additive_percent | 0 | -90…300 | armor.whipRange /100 | ModItem.UpdateEquip |
| taggedSummonSourceDamageBonusPercent | Multiply summon projectile source damage by 1+percent/100 only against an NPC tagged by this owner's generated whip | source_damage_percent | 0 | 0…300 | armor.summonTagDamage /100 | ModItem.UpdateEquip |
| lightStrength | Client-only RGB light coefficient multiplying lightColor; not tile radius; requires lightColor when positive | engine units: RGB coefficient | 0 | 0…1.5 | armor.lightStrength | ModItem.UpdateEquip |
| lightColor | Explicit equipped light color | runtime_color |  | white/red/orange/yellow/green/cyan/blue/purple/pink/gray/black | armor.lightColorName | ModItem.UpdateEquip |
| fallDamageImmune | Prevent fall damage while equipped | bounded_text | False | boolean | armor.fallDamageImmune | ModItem.UpdateEquip |
| lavaImmune | Grant lava immunity while equipped | bounded_text | False | boolean | armor.lavaImmune | ModItem.UpdateEquip |
| waterWalk | Walk on water while equipped | bounded_text | False | boolean | armor.waterWalk | ModItem.UpdateEquip |
| setBonusGenericCritChancePercentagePoints | Matching armor set (head piece only; matching head, body and legs must actually be equipped): Add percentage points to generic critical chance | percentage_points | 0 | -100…100 | armor.setBonusGenericCrit | ModItem.UpdateArmorSet; exact setKey on head, body and legs |
| setBonusMoveSpeedBonusPercent | Matching armor set (head piece only; matching head, body and legs must actually be equipped): Add percent/100 to Player.moveSpeed | additive_percent | 0 | -90…300<br>legacy clamp: -0.9…3 | armor.setBonusMovementSpeed /100 | ModItem.UpdateArmorSet; exact setKey on head, body and legs |
| setBonusLifeRegenHpPerSecond | Matching armor set (head piece only; matching head, body and legs must actually be equipped): Add signed HP/s regeneration contribution before other Terraria effects; +1 HP/s writes +2 Player.lifeRegen engine units, -1 HP/s writes -2; 0 adds nothing | HP/s | 0 | -50…100<br>legacy clamp: -120…200 | armor.setBonusLifeRegen | ModItem.UpdateArmorSet; exact setKey on head, body and legs |
| setBonusManaRegenBonusPoints | Matching armor set (head piece only; matching head, body and legs must actually be equipped): Add raw Player.manaRegenBonus points; 0 adds nothing, not mana/s | engine units: manaRegenBonus points | 0 | -100…200 | armor.setBonusManaRegen | ModItem.UpdateArmorSet; exact setKey on head, body and legs |
| setBonusMinionSlotsBonus | Matching armor set (head piece only; matching head, body and legs must actually be equipped): Add minion slots | slots | 0 | 0…20 | armor.setBonusMinionSlots | ModItem.UpdateArmorSet; exact setKey on head, body and legs |
| setBonusSentrySlotsBonus | Matching armor set (head piece only; matching head, body and legs must actually be equipped): Add sentry slots | slots | 0 | 0…20 | armor.setBonusSentrySlots | ModItem.UpdateArmorSet; exact setKey on head, body and legs |
| setBonusManaCostReductionPercentagePoints | Matching armor set (head piece only; matching head, body and legs must actually be equipped): Subtract percent/100 from Player.manaCost factor, floored at 0.1 | percentage_points | 0 | 0…90 | armor.setBonusManaCostReduction /100 | ModItem.UpdateArmorSet; exact setKey on head, body and legs |
| setBonusAmmoSaveChancePercent | Matching armor set (head piece only; matching head, body and legs must actually be equipped): Equipped owner's ammo saving chance via Player.CanConsumeAmmo for any weapon; equipped item chances combine as 1−product(1−p) | probability_percent | 0 | 0…99 | armor.setBonusAmmoSaveChance /100 | ModItem.UpdateArmorSet; exact setKey on head, body and legs |
| setBonusAggroPoints | Matching armor set (head piece only; matching head, body and legs must actually be equipped): Add raw Player.aggro engine points (negative reduces targeting); not a probability or radius | engine units: aggro points | 0 | -1000…1000 | armor.setBonusAggro | ModItem.UpdateArmorSet; exact setKey on head, body and legs |
| setBonusDamageReductionPercentagePoints | Matching armor set (head piece only; matching head, body and legs must actually be equipped): Add percent/100 to Player.endurance damage reduction | percentage_points | 0 | 0…75 | armor.setBonusEndurance /100 | ModItem.UpdateArmorSet; exact setKey on head, body and legs |
| setBonusGenericArmorPenetrationPoints | Matching armor set (head piece only; matching head, body and legs must actually be equipped): Add flat armor penetration points to DamageClass.Generic; not damage percent | armor_points | 0 | 0…100 | armor.setBonusArmorPenetration | ModItem.UpdateArmorSet; exact setKey on head, body and legs |

Authority: `owner_execute_sync`; техническая фаза/сетевая роль выбираются runtime, не LLM.

### `add_equipment_damage_bonus` — параметризованная операция

Один call выбирает `phase`, `damageClass` и `bonusPercent`. Shared type `equipment_damage_class` содержит ровно классы, для которых текущий C# вызывает `GetDamage(DamageClass)`: `generic`, `melee`, `ranged`, `magic`, `summon`. Другие item/projectile DamageClass здесь не исполняются и отклоняются; crit, attack speed, knockback и armor penetration пока исполняются только для `generic` и не маскируются выдуманной поддержкой других классов.
`bonusPercent`: `-90…300` additive_percent, neutral `0`; wire = percent / 100. Указанные в `phase` `equipped` и `matching_armor_set` — выбор модели. Последняя фаза требует `configure_armor(slot=head, setKey=<непустой exact ключ>)`; C# применяет её только при совпадении head/body/legs. Повтор пары `(phase, damageClass)` отклоняется, а не неявно складывается.

| Phase | DamageClass | Wire DTO | tModLoader hook |
|---|---|---|---|
| equipped (accessory) | generic | `accessory.genericDamage` | `UpdateAccessory` |
| equipped (accessory) | melee | `accessory.meleeDamage` | `UpdateAccessory` |
| equipped (accessory) | ranged | `accessory.rangedDamage` | `UpdateAccessory` |
| equipped (accessory) | magic | `accessory.magicDamage` | `UpdateAccessory` |
| equipped (accessory) | summon | `accessory.summonDamage` | `UpdateAccessory` |
| equipped (armor) | generic | `armor.genericDamage` | `UpdateEquip` |
| equipped (armor) | melee | `armor.meleeDamage` | `UpdateEquip` |
| equipped (armor) | ranged | `armor.rangedDamage` | `UpdateEquip` |
| equipped (armor) | magic | `armor.magicDamage` | `UpdateEquip` |
| equipped (armor) | summon | `armor.summonDamage` | `UpdateEquip` |
| matching_armor_set (armor) | generic | `armor.setBonusGenericDamage` | `UpdateArmorSet` |
| matching_armor_set (armor) | melee | `armor.setBonusMeleeDamage` | `UpdateArmorSet` |
| matching_armor_set (armor) | ranged | `armor.setBonusRangedDamage` | `UpdateArmorSet` |
| matching_armor_set (armor) | magic | `armor.setBonusMagicDamage` | `UpdateArmorSet` |
| matching_armor_set (armor) | summon | `armor.setBonusSummonDamage` | `UpdateArmorSet` |

Legacy C# DTO/Normalize-поля и выборочные исторические clamps сохранены; Author больше не видит пять class-specific полей как независимые primitives. Сохранённый wire v5 загружается без повторной компиляции Author.

<a id="events"></a>

## Event/runtime и намеренно скрытое

- Все `RuntimeEventActionSpec` поля, включая `DelayTicks`, сверяются с exact wire paths. Каждый event action допускает `delayTicks=0…600`; C# scheduler проверяет spawn budget/authority и переносит действие, не создавая новый дизайн.
- `move_owner_on_event` телепортирует только к **сохранённой позиции события** (ограничение `rangeTiles`, проверка safe tile, общий cooldown с `move_player_on_use`). Wire `Mode=blink_to_event_position` — фиксированный технический discriminator; старое `blink_to_entity` исполнялось той же веткой и больше не предлагается модели.
- `oreSenseEnabled` — булево включение Terraria `Player.findTreasure`; legacy `GeneratedBuffSpec.OreSenseRadiusTiles` хранит только 0/1, **не радиус**. В prompt нет ложных тайлов.
- `RuntimeParamsSpec.IntervalTicks` — только legacy fallback при нулевом typed `Targeting.IntervalTicks`; текущий Author требует положительный typed interval. `ShotEntity` и `SameTargetBias` в старом Params не потребляются: Author пишет typed `Targeting`.
- `held generatedBuff`: snapshot ещё не имеет refresh generated utility buff при удержании; текущие held light/mining-speed поля не заменяют произвольный buff. Исторический consumer и его удаление описаны в A2 snapshot-аудита; возможное восстановление требует явного отдельного capability, не скрытого выбора по предмету.
- Legacy `GameplaySpec.BuffCode`/`BuffTime` (`Item.buffType`/`buffTime`) сохраняются для старого wire. Новый Author использует явный многобафовый `ExtraBuffs` и не смешивает эти два пути; различие vanilla Item hook и пользовательского AddBuff не доказано эквивалентным.
- `Archetype`, `Kind`, `Stage`, `PowerBudget` — исторические display/plan поля, не семантические маршрутизаторы. `Enabled`, opcodes, роли, `UseStyle` и DTO IDs выводятся из явно авторских calls.

<a id="unsupported"></a>

## Исторические возможности вне нынешнего executable surface

Историческая проверка должна учитывать удалённые consumers отдельно от нынешнего AST. В pre-v5 `f04ee02` реальный `GeneratedProjectile.Sentry.cs:42–53` исполняет shotCount/spread за залп: этот механизм доказан. Вероятность собственного расхода сохранялась при импорте v5 и исчезла 2 августа (`3831d93`/`7f4e86a`). Ammo-side PickAmmo существует и не заменяет weapon Item.useAmmo. Старый Extractinator proxy хранил output в instance Data, но ExtractinatorUse неинстансный; intended per-instance output не доказан рабочим, а удаление произошло 15 июля (`5adb9fa`). Полная классификация с ранними архивами, source paths и ограничениями — [исторический snapshot-аудит](HISTORICAL_RUNTIME_AUDIT_2026_10_RU.md). Последующие restoration PR оцениваются отдельно: snapshot не является реестром текущих возможностей. Новая поддержка требует explicit bounded primitives и полного vertical slice, без whole-weapon macros.

<a id="units"></a>

## Единицы при extraUpdates > 0

`set_projectile_collision.extraUpdates=n` даёт `n+1` AI/physics-обновлений снаряда за мировой тик. В Author-карточках исходная `Projectile.velocity`, гравитация, поворот, ускорение и скорость возврата обозначены **за projectile update**, а не как гарантированные пиксели за мировой тик. Длительности и event-периоды остаются в мировых тиках; C# переводит их через `AuthoredTicksToProjectileUpdates`. Это точное описание существующего wire/v5 поведения без смены старых рецептов и без приблизительного пересчёта нелинейного движения в px/сек.

<a id="limits"></a>

## Границы проверки

AST audit анализирует нынешние DTO и названные C# executor seams. Удалённое вместе с consumer поле исчезает из этого множества: текущий PASS не доказывает исторический паритет. Audit не заменяет полноценный compiler/semantic analysis всех tML API. Headless C# тесты покрывают projection/equip и cooldown, но не Terraria world loop, GPU или multiplayer. Live20 проверяет Author pipeline на внешней модели, а не выполнение в игре.

<a id="refresh"></a>

## Обновление и проверка

Из корня репозитория, с Python окружения проекта. Без `--check` generator записывает **только этот Markdown**, не JSON, DTO или bounds:

```bash
PYTHONPATH=LocalGenerator python tools/generate_primitive_parity.py
PYTHONPATH=LocalGenerator python tools/generate_primitive_parity.py --check
```

Generation/check исполняют все пять surface audits выше и завершаются ошибкой при loss; freshness доказывает совпадение projection с owners, а не игровой smoke. Affected regressions: [test_registry_vertical_contract.py](../LocalGenerator/tests/test_registry_vertical_contract.py), [test_registry_author_packet.py](../LocalGenerator/tests/test_registry_author_packet.py).
