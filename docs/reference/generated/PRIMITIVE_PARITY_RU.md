# Parity примитивов Author ↔ Terraria/tModLoader

> Generated: [`tools/generate/generate_primitive_parity.py`](../../../tools/generate/generate_primitive_parity.py). Не редактировать вручную; [refresh/check](#refresh).
> Sources: [capability_registry.py](../../../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py) — имена, единицы, диапазоны, wire и фазы; [primitive_loss_audit.py](../../../LocalGenerator/infini_local/qa/primitive_loss_audit.py) — C# executable-поля из AST. [Lowery](LOWERY_RU.md) — boundary/owners; [inventory](LOW_LEVEL_CAPABILITY_INVENTORY_RU.md) — полный каталог.

**Навигация:** [источник](#history) · [machine audit](#audit) · [equipment](#equipment) · [events/runtime](#events) · [граница расширения](#unsupported) · [extraUpdates units](#units) · [границы проверки](#limits) · [обновление](#refresh).

<a id="history"></a>

## Текущий источник истины

Один registry выдаёт Author JSON schema, компактные карточки, validator-параметры, exact wire paths, технические receipts, C# safety bounds и таблицы ниже. DTO — цель проекции, не второе описание механики. Semantic aliases/weapon-family routers и compatibility importer не входят в текущий контракт.

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

`additive_percent` — авторский процент прибавки к additive компоненте StatModifier (15 → +0.15), не итоговый множитель урона. `percentage_points` — сдвиг шанса в п.п.; `probability_percent` — вероятность/100. `defense_points`, `life_points` и `slots` не масштабируются. Author-скорости в блоках/с переводятся в native pixels/world tick через ×16/60, регенерация HP/s — в lifeRegen через ×2. Отрицательные значения разрешены только там, где указан отрицательный минимум. Ноль/false/пустая строка — нейтральны, если не оговорено иначе. Item.defense проектируется в `ApplyToItem`: Terraria сама применяет защиту, equip-hook не удваивает её.

Author schema ограничивает значения всех примитивов; C# Normalize применяет только объявленные **runtime safety clamps** из `runtime_minimum`/`runtime_maximum` registry и `GeneratedEquipmentBounds.g.cs`. В таблицах они обозначены `runtime clamp`; отсутствие пометки не разрешает подставлять новые ограничения. Это не разрешение Author выбирать значения вне своей схемы и не повод удалять действующие caps как устаревшие metadata.

### `configure_accessory`

| Author | Действие / engine semantics | Единица | Neutral | Author range | Wire DTO | Фаза |
|---|---|---|---|---|---|---|
| defensePoints | Add to Item.defense; Terraria applies it, not an extra equip-hook adjustment | defense_points | 0 | -50…200<br>runtime clamp: -100…500 | accessory.defense | ModItem.UpdateAccessory |
| maxLifePoints | Add maximum life | life_points | 0 | -200…1000<br>runtime clamp: -500…5000 | accessory.maxLife | ModItem.UpdateAccessory |
| maxManaPoints | Add maximum mana | mana_points | 0 | -200…1000<br>runtime clamp: -500…5000 | accessory.maxMana | ModItem.UpdateAccessory |
| lifeRegenHpPerSecond | Add signed HP/s regeneration contribution before other Terraria effects; +1 HP/s writes +2 Player.lifeRegen engine units, -1 HP/s writes -2; 0 adds nothing | HP/s | 0 | -50…100<br>runtime clamp: -120…200 | accessory.lifeRegen = Author ×2 | ModItem.UpdateAccessory |
| manaRegenBonusPoints | Add raw Player.manaRegenBonus points; 0 adds nothing, not mana/s | engine units: manaRegenBonus points | 0 | -100…200<br>runtime clamp: -120…200 | accessory.manaRegen | ModItem.UpdateAccessory |
| moveSpeedBonusPercent | Add percent/100 to Player.moveSpeed | additive_percent | 0 | -90…300<br>runtime clamp: -0.9…3 | accessory.movementSpeed = Author /100 | ModItem.UpdateAccessory |
| maxRunSpeedBonusBlocksPerSecond | Author units: blocks/s. Native consumer: Add to Player.maxRunSpeed, subject to other Terraria movement limits | blocks/s | 0.0 | -18.75…75.0 | accessory.maxRunSpeed = Author ×16 /60 | ModItem.UpdateAccessory |
| jumpSpeedBonusBlocksPerSecond | Author units: blocks/s. Native consumer: Add to Player.jumpSpeedBoost (positive raises jump speed) | blocks/s | 0.0 | -18.75…75.0 | accessory.jumpSpeed = Author ×16 /60 | ModItem.UpdateAccessory |
| genericCritChancePercentagePoints | Add percentage points to generic critical chance | percentage_points | 0 | -100…100<br>runtime clamp: -100…100 | accessory.genericCrit | ModItem.UpdateAccessory |
| genericAttackSpeedBonusPercent | Add percent/100 to generic attack speed | additive_percent | 0 | -90…300 | accessory.attackSpeed = Author /100 | ModItem.UpdateAccessory |
| genericKnockbackBonusPercent | Add percent/100 to generic StatModifier knockback; not flat points | additive_percent | 0 | -90…300 | accessory.knockback = Author /100 | ModItem.UpdateAccessory |
| minionSlotsBonus | Add minion slots | slots | 0 | 0…20<br>runtime clamp: 0…20 | accessory.minionSlots | ModItem.UpdateAccessory |
| sentrySlotsBonus | Add sentry slots | slots | 0 | 0…20<br>runtime clamp: 0…20 | accessory.sentrySlots | ModItem.UpdateAccessory |
| manaCostReductionPercentagePoints | Subtract percent/100 from Player.manaCost factor, floored at 0.1 | percentage_points | 0 | 0…90 | accessory.manaCostReduction = Author /100 | ModItem.UpdateAccessory |
| ammoSaveChancePercent | Equipped owner's ammo saving chance via Player.CanConsumeAmmo for any weapon; equipped item chances combine as 1−product(1−p) | probability_percent | 0 | 0…99 | accessory.ammoSaveChance = Author /100 | ModItem.UpdateAccessory |
| aggroPoints | Add raw Player.aggro engine points (negative reduces targeting); not a probability or radius | engine units: aggro points | 0 | -1000…1000 | accessory.aggro | ModItem.UpdateAccessory |
| damageReductionPercentagePoints | Add percent/100 to Player.endurance damage reduction | percentage_points | 0 | 0…75<br>runtime clamp: 0…0.75 | accessory.endurance = Author /100 | ModItem.UpdateAccessory |
| genericArmorPenetrationPoints | Add flat armor penetration points to DamageClass.Generic; not damage percent | armor_points | 0 | 0…100 | accessory.armorPenetration | ModItem.UpdateAccessory |
| whipRangeBonusPercent | Add percent/100 to Player.whipRangeMultiplier | additive_percent | 0 | -90…300 | accessory.whipRange = Author /100 | ModItem.UpdateAccessory |
| taggedSummonSourceDamageBonusPercent | Multiply summon projectile source damage by 1+percent/100 only against an NPC tagged by this owner's generated whip | source_damage_percent | 0 | 0…300 | accessory.summonTagDamage = Author /100 | ModItem.UpdateAccessory |
| lightStrength | Client-only RGB light coefficient multiplying lightColor; not tile radius; requires lightColor when positive | engine units: RGB coefficient | 0 | 0…1.5<br>runtime clamp: 0…1.5 | accessory.lightStrength | ModItem.UpdateAccessory |
| lightColor | Explicit equipped light color | runtime_color |  | white/red/orange/yellow/green/cyan/blue/purple/pink/gray/black | accessory.lightColorName | ModItem.UpdateAccessory |
| fallDamageImmune | Prevent fall damage while equipped | bounded_text | False | boolean | accessory.fallDamageImmune | ModItem.UpdateAccessory |
| lavaImmune | Grant lava immunity while equipped | bounded_text | False | boolean | accessory.lavaImmune | ModItem.UpdateAccessory |
| waterWalk | Walk on water while equipped | bounded_text | False | boolean | accessory.waterWalk | ModItem.UpdateAccessory |
| swimFlipper | Native flipper swimming jump while wet. Independently authored; false grants nothing. Native ResetEffects/extra-jump reset removes on unequip; no automatic sibling grants. | bounded_text | False | boolean | accessory.swimFlipper | ModItem.UpdateAccessory |
| divingHelm | Native diving helmet breath conservation. Independently authored; false grants nothing. Native ResetEffects/extra-jump reset removes on unequip; no automatic sibling grants. | bounded_text | False | boolean | accessory.divingHelm | ModItem.UpdateAccessory |
| underwaterBreathing | Native gills: breathe air and water; getGoodWorld reverses drowning and requires water. Independently authored; false grants nothing. Native ResetEffects/extra-jump reset removes on unequip; no automatic sibling grants. | bounded_text | False | boolean | accessory.underwaterBreathing | ModItem.UpdateAccessory |
| waterFloat | Native water flotation, descend with down control. Independently authored; false grants nothing. Native ResetEffects/extra-jump reset removes on unequip; no automatic sibling grants. | bounded_text | False | boolean | accessory.waterFloat | ModItem.UpdateAccessory |
| jumpCloud | Cloud bottle extra jump. Independently authored; false grants nothing. Native ResetEffects/extra-jump reset removes on unequip; no automatic sibling grants. Only enables this native jump; native order, movement restrictions and landing recharge apply; equip never refreshes spent jumps. | bounded_text | False | boolean | accessory.jumpCloud | ModItem.UpdateAccessory |
| jumpBlizzard | Blizzard bottle extra jump. Independently authored; false grants nothing. Native ResetEffects/extra-jump reset removes on unequip; no automatic sibling grants. Only enables this native jump; native order, movement restrictions and landing recharge apply; equip never refreshes spent jumps. | bounded_text | False | boolean | accessory.jumpBlizzard | ModItem.UpdateAccessory |
| jumpSandstorm | Sandstorm bottle extra jump. Independently authored; false grants nothing. Native ResetEffects/extra-jump reset removes on unequip; no automatic sibling grants. Only enables this native jump; native order, movement restrictions and landing recharge apply; equip never refreshes spent jumps. | bounded_text | False | boolean | accessory.jumpSandstorm | ModItem.UpdateAccessory |
| jumpFart | Fart jar extra jump. Independently authored; false grants nothing. Native ResetEffects/extra-jump reset removes on unequip; no automatic sibling grants. Only enables this native jump; native order, movement restrictions and landing recharge apply; equip never refreshes spent jumps. | bounded_text | False | boolean | accessory.jumpFart | ModItem.UpdateAccessory |
| jumpTsunami | Tsunami bottle extra jump. Independently authored; false grants nothing. Native ResetEffects/extra-jump reset removes on unequip; no automatic sibling grants. Only enables this native jump; native order, movement restrictions and landing recharge apply; equip never refreshes spent jumps. | bounded_text | False | boolean | accessory.jumpTsunami | ModItem.UpdateAccessory |
| iceSkate | Enable Player.iceSkate: native ice acceleration/sliding behavior and no thin-ice break; not general movement speed | bounded_text | False | boolean | accessory.iceSkate | ModItem.UpdateAccessory |
| noKnockback | Enable Player.noKnockback for native hurt knockback immunity; damage, defense and enemy-knockback modifiers remain separate | bounded_text | False | boolean | accessory.noKnockback | ModItem.UpdateAccessory |
| fireWalk | Enable Player.fireWalk: immunity to TileID.Sets.TouchDamageHot blocks only; NOT lava immunity, fire debuffs or all harmful tiles | bounded_text | False | boolean | accessory.fireWalk | ModItem.UpdateAccessory |
| accRunSpeedBlocksPerSecond | Author units: blocks/s. Native consumer: Native sprint-speed floor: max(Player.accRunSpeed, lowered value) in equip phase; 0 grants nothing. Later native terrain/mount/wing/chilled rules still apply; distinct from moveSpeed percent and the post-vanilla maxRunSpeed flat bonus | blocks/s | 0.0 | 0.0…75.0 | accessory.accRunSpeed = Author ×16 /60 | ModItem.UpdateAccessory |
| rocketBoots | Native Player.rocketBoots mode: 0 grants nothing, 1 uses 30-tick rocketDelay2, 2..5 use 15-tick rocketDelay2. Any nonzero mode enables native charge/thrust flight, not wings. Modes combine by max; does not choose vanityRocketBoots, ice skating, sprint speed or refresh rocketTime. Native rocketTimeMax=7 charges with 10-tick thrust windows; landing/sliding/RefreshMovementAbilities refill, wings may convert charges to wingTime; mounts suppress flight | native rocket flight mode | 0 | 0…5 | accessory.rocketBoots | ModItem.UpdateAccessory |
| wireVision | Enable Player.InfoAccMechShowWires while equipped; native builder toggles choose wire colors and actuators; not ruler, placement or inventory activation | bounded_text | False | boolean | accessory.wireVision | ModItem.UpdateAccessory |

Authority: `owner_execute_sync`; техническая фаза/сетевая роль выбираются runtime, не LLM.

### `configure_armor`

| Author | Действие / engine semantics | Единица | Neutral | Author range | Wire DTO | Фаза |
|---|---|---|---|---|---|---|
| slot | Armor equip slot | bounded_text | None | head/body/legs | armor.slot | C# normalized item projection |
| setKey | Exact authored set key (empty when no matching set is intended) | bounded_text |  | ^[a-z0-9_]{0,48}$ | armor.setKey | C# normalized item projection |
| defensePoints | Add to Item.defense; Terraria applies it, not an extra equip-hook adjustment | defense_points | 0 | 0…200<br>runtime clamp: 0…500 | armor.defense | ModItem.UpdateEquip |
| maxLifePoints | Add maximum life | life_points | 0 | -200…1000<br>runtime clamp: -500…5000 | armor.maxLife | ModItem.UpdateEquip |
| maxManaPoints | Add maximum mana | mana_points | 0 | -200…1000<br>runtime clamp: -500…5000 | armor.maxMana | ModItem.UpdateEquip |
| lifeRegenHpPerSecond | Add signed HP/s regeneration contribution before other Terraria effects; +1 HP/s writes +2 Player.lifeRegen engine units, -1 HP/s writes -2; 0 adds nothing | HP/s | 0 | -50…100 | armor.lifeRegen = Author ×2 | ModItem.UpdateEquip |
| manaRegenBonusPoints | Add raw Player.manaRegenBonus points; 0 adds nothing, not mana/s | engine units: manaRegenBonus points | 0 | -100…200 | armor.manaRegen | ModItem.UpdateEquip |
| moveSpeedBonusPercent | Add percent/100 to Player.moveSpeed | additive_percent | 0 | -90…300<br>runtime clamp: -0.9…3 | armor.movementSpeed = Author /100 | ModItem.UpdateEquip |
| maxRunSpeedBonusBlocksPerSecond | Author units: blocks/s. Native consumer: Add to Player.maxRunSpeed, subject to other Terraria movement limits | blocks/s | 0.0 | -18.75…75.0 | armor.maxRunSpeed = Author ×16 /60 | ModItem.UpdateEquip |
| jumpSpeedBonusBlocksPerSecond | Author units: blocks/s. Native consumer: Add to Player.jumpSpeedBoost (positive raises jump speed) | blocks/s | 0.0 | -18.75…75.0 | armor.jumpSpeed = Author ×16 /60 | ModItem.UpdateEquip |
| genericCritChancePercentagePoints | Add percentage points to generic critical chance | percentage_points | 0 | -100…100<br>runtime clamp: -100…100 | armor.genericCrit | ModItem.UpdateEquip |
| genericAttackSpeedBonusPercent | Add percent/100 to generic attack speed | additive_percent | 0 | -90…300 | armor.attackSpeed = Author /100 | ModItem.UpdateEquip |
| genericKnockbackBonusPercent | Add percent/100 to generic StatModifier knockback; not flat points | additive_percent | 0 | -90…300 | armor.knockback = Author /100 | ModItem.UpdateEquip |
| minionSlotsBonus | Add minion slots | slots | 0 | 0…20 | armor.minionSlots | ModItem.UpdateEquip |
| sentrySlotsBonus | Add sentry slots | slots | 0 | 0…20 | armor.sentrySlots | ModItem.UpdateEquip |
| manaCostReductionPercentagePoints | Subtract percent/100 from Player.manaCost factor, floored at 0.1 | percentage_points | 0 | 0…90 | armor.manaCostReduction = Author /100 | ModItem.UpdateEquip |
| ammoSaveChancePercent | Equipped owner's ammo saving chance via Player.CanConsumeAmmo for any weapon; equipped item chances combine as 1−product(1−p) | probability_percent | 0 | 0…99 | armor.ammoSaveChance = Author /100 | ModItem.UpdateEquip |
| aggroPoints | Add raw Player.aggro engine points (negative reduces targeting); not a probability or radius | engine units: aggro points | 0 | -1000…1000 | armor.aggro | ModItem.UpdateEquip |
| damageReductionPercentagePoints | Add percent/100 to Player.endurance damage reduction | percentage_points | 0 | 0…75 | armor.endurance = Author /100 | ModItem.UpdateEquip |
| genericArmorPenetrationPoints | Add flat armor penetration points to DamageClass.Generic; not damage percent | armor_points | 0 | 0…100 | armor.armorPenetration | ModItem.UpdateEquip |
| whipRangeBonusPercent | Add percent/100 to Player.whipRangeMultiplier | additive_percent | 0 | -90…300 | armor.whipRange = Author /100 | ModItem.UpdateEquip |
| taggedSummonSourceDamageBonusPercent | Multiply summon projectile source damage by 1+percent/100 only against an NPC tagged by this owner's generated whip | source_damage_percent | 0 | 0…300 | armor.summonTagDamage = Author /100 | ModItem.UpdateEquip |
| lightStrength | Client-only RGB light coefficient multiplying lightColor; not tile radius; requires lightColor when positive | engine units: RGB coefficient | 0 | 0…1.5 | armor.lightStrength | ModItem.UpdateEquip |
| lightColor | Explicit equipped light color | runtime_color |  | white/red/orange/yellow/green/cyan/blue/purple/pink/gray/black | armor.lightColorName | ModItem.UpdateEquip |
| fallDamageImmune | Prevent fall damage while equipped | bounded_text | False | boolean | armor.fallDamageImmune | ModItem.UpdateEquip |
| lavaImmune | Grant lava immunity while equipped | bounded_text | False | boolean | armor.lavaImmune | ModItem.UpdateEquip |
| waterWalk | Walk on water while equipped | bounded_text | False | boolean | armor.waterWalk | ModItem.UpdateEquip |
| setBonuses | Matching three-piece armor set bonuses, executed once by its head piece; exact setKey required for non-neutral effects | bounded_text | None | object | armor.setBonuses | C# normalized item projection |

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

C# DTO и runtime safety bounds проецируются из текущих typed primitives; Author выбирает phase/damageClass в одной параметризованной capability. Runtime wire загружается без повторной компиляции Author.

<a id="events"></a>

## Event/runtime и намеренно скрытое

- Все `RuntimeEventActionSpec` поля, включая `DelayTicks`, сверяются с exact wire paths. Каждый event action допускает `delayTicks=0…600`; C# scheduler проверяет spawn budget/authority и переносит действие, не создавая новый дизайн.
- `move_owner_on_event` телепортирует только к **сохранённой позиции события** (ограничение `rangeTiles`, проверка safe tile, общий cooldown с `move_player_on_use`). Wire `Mode=blink_to_event_position` — фиксированный технический discriminator; старое `blink_to_entity` исполнялось той же веткой и больше не предлагается модели.
- `oreSenseEnabled` — булево включение Terraria `Player.findTreasure`; `GeneratedBuffSpec.OreSenseRadiusTiles` хранит только 0/1, **не радиус**. В prompt нет ложных тайлов.
- `target_and_fire` использует только typed `Targeting.ShotEntityId`/`IntervalTicks`/`SameTargetBias`; typed interval обязателен и положителен, executor сохраняет floor 6 world ticks и перевод при extraUpdates. Старые `RuntimeParamsSpec.ShotEntity`/`IntervalTicks`/`SameTargetBias` удалены; старые Params-поля в saved wire отвергаются, fallback cadence отсутствует.
- `refresh_generated_effect_group_while_held` явно выбирает `runtimeProgram.heldEffectGroupId`: только named generated-buff group. `GeneratedItem.HoldItem -> RefreshHeldEffectGroup -> ApplyGeneratedUtilityBuff` пытается refresh раз за world tick для exact held item; duration управляет lingering после release, exhaustion остаётся отдельной политикой. Healing, mobility и native buffs не выводятся из held light/mining-speed или prose.
- Single-slot `GameplaySpec.BuffCode`/`BuffTime` удалены; старые gameplay-поля отвергаются. Default и named effect groups используют явный многобафовый `ExtraBuffs[]` с `BuffEntrySpec.BuffCode`/`BuffTime`; `GeneratedItem.ApplyItemEffects` вызывает native `Player.AddBuff` для каждой записи. `ApplyUseEffectFields` очищает `Item.buffType`/`buffTime` до0, не восстанавливает single slot.
- `Enabled`, opcodes, роли, `UseStyle` и DTO IDs выводятся из явно авторских calls. Display/advisory prose не выбирает механические поля.

<a id="unsupported"></a>

## Граница расширения executable surface

Текущий AST audit проверяет текущих consumers, не историческую полноту или native/game acceptance. Новая поддержка требует explicit bounded primitive и полного vertical slice без whole-weapon macros. Исторический snapshot отдельно: [архивный аудит](../../archive/HISTORICAL_RUNTIME_AUDIT_2026_10_RU.md), не текущий capability catalog.

<a id="units"></a>

## Единицы при extraUpdates > 0

Author явно задаёт `set_projectile_collision.updatesPerTick=N` — число AI/physics-обновлений снаряда за мировой тик; wire хранит `extraUpdates=N−1`. Игровые расстояния Author задаёт в блоках, длительности — в секундах, скорости — в блоках/с, физические ускорения — в блоках/с² и объявленные угловые скорости — в радианах/с. Registry-lowering учитывает N именно затронутой сущности: дочерний снаряд использует собственный clock. Длительности округляются до ближайшего world tick, половина тика вверх; C# сохраняет прежний перевод через `AuthoredTicksToProjectileUpdates`. Dimensionless retention/lerp/multiplier и технические update-счётчики сохраняют явно объявленный per-update смысл. Engine wire и сохранённые рецепты не пересчитываются; параметры не обещают конечную скорость нелинейного движения.

<a id="limits"></a>

## Границы проверки

AST audit анализирует нынешние DTO и названные C# executor seams. Удалённое вместе с consumer поле исчезает из этого множества: текущий PASS не доказывает исторический паритет. Audit не заменяет полноценный compiler/semantic analysis всех tML API. Headless C# тесты покрывают projection/equip и cooldown, но не Terraria world loop, GPU или multiplayer. Live20 проверяет Author pipeline на внешней модели, а не выполнение в игре.

<a id="refresh"></a>

## Обновление и проверка

Из корня репозитория, с Python окружения проекта. Без `--check` generator записывает **только этот Markdown**, не JSON, DTO или bounds:

```bash
PYTHONPATH=LocalGenerator python tools/generate/generate_primitive_parity.py
PYTHONPATH=LocalGenerator python tools/generate/generate_primitive_parity.py --check
```

Generation/check исполняют все пять surface audits выше и завершаются ошибкой при loss; freshness доказывает совпадение projection с owners, а не игровой smoke. Affected regressions: [test_registry_vertical_contract.py](../../../LocalGenerator/tests/test_registry_vertical_contract.py), [test_registry_author_packet.py](../../../LocalGenerator/tests/test_registry_author_packet.py).
