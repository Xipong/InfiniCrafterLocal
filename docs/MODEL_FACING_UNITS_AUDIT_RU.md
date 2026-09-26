# Аудит единиц model-facing контрактов — Gameplay Author / Visual / VFX

## Итог и границы доказательства

Источник состояния: `LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py` (текущий реестр); контроль исходных ключей — read-only snapshot `icl-units-before.json` (229 строк); трассы потребителей — read-only отчёты `icl-unit-item-audit.md`, `icl-unit-movement-audit.md`, `icl-unit-events-audit.md`, `icl-unit-visual-vfx-audit.md`. Снимок и отчёты — входные материалы аудита, **не** часть исполняемого контракта; постоянный источник — registry → provider schema/prompt → validator → compiler receipts → wire → C# DTO/executor. Инвентарь и consumer traces — статический анализ; отдельные результаты исполняемых проверок приведены в конце. Model-run и игровой smoke не проводились.

Текущий реестр: **52 capabilities, 229 параметров (180 числовых)**; из них 51 capability имеет параметры, `move_straight` имеет **0**. Итог по 229 строкам ниже: **keep 164, identity-rename 14, declared-convert 27, engine-units 24**. Классы относятся к *текущему* model-facing состоянию, а не к числу предлагаемых правок. Сопоставление старого снимка с новым состоянием по `(capability, spec.wire_name)` при смене имени, иначе по `(capability, param)`: **229↔229, без пропусков и дублей**; 14 переименований с тождественным числом/значением и 3 уже принятых преобразования `lifeRegenHalfHpPerSecond → lifeRegenHpPerSecond` (accessory, armor, armor set). Последние сохраняют integer engine wire **[-100,200]** через `wire = 2 × HP/s`, допустимое авторское множество **[-50,100] с шагом 0.5**, обратное `HP/s = wire/2`; ноль, знак и концы сохранены. Остальные 24 existing `declared-convert` — уже существующие адаптеры; *новых* процентов/секунд/градусов не вводить. `declared-convert` здесь означает объявленный адаптер авторского представления на его образе, а **не** доказательство побитного JSON↔binary32 round-trip для каждого вещественного значения и **не** обратимость любого старого DTO значения. В частности `oreSenseEnabled` кодирует только `false→0`, `true→1`; произвольные исторические `oreSenseRadiusTiles=2..60` этим bool не восстановить. Для процентов `/100` нельзя без отдельного сквозного теста обещать бинарно-точное восстановление произвольной десятичной дроби.

**Отклонённая конверсия:** `apply_generated_buff_on_use.moveSpeedBonusFactor` — identity к старому `movementSpeed`, сырой additive `Player.moveSpeed` factor **[-0.5,2]**, не `moveSpeedBonusPercent`. Контрпример `x=1.770282212988338`: `x*100/100=1.7702822129883378`; соседние percent-float представления дают `1.7702822129883375`, `1.7702822129883378`, `1.7702822129883382`. Универсальный точный inverse старого wire из процентов не доказан; в отличие от уже существующего equipment `moveSpeedBonusPercent`, у buff процентного адаптера нет. `*Ticks`, углы в радианах и вещественные тайловые радиусы не переводить в секунды/градусы/пиксели без доказательства биекции полного JSON/C# домена, включая ноль, отрицательные значения и sentinels. C# wire поля остаются прежними, никакого legacy Author alias или удаления capabilities; внешний ключ модели меняется только там, где его уже переименовал текущий registry.

**Маршрут проверки:** `capability_registry.py:278-342,376-502` определяет `ParamSpec`, schema, prompt и lowering чисел; `core/runtime_authoring/compiler.py:46-55,92-105,160-190,225-241,264-353,392-421` строит проекции/receipts; `program_schema.py:45-162,237-363` держит Author/Repair структуру. При будущей правке проверять реальные prompt/schema, validator/Repair, receipt, старый strict wire, DTO/executor, regression и игровой результат **отдельно**. Инвентарная сверка и статическая привязка отделены от результатов тестов в конце документа. `craftYield` 1..9999 остаётся authored величиной, но фактическая выдача ограничивается `maxStack` (`InfiniCraftPlayer.Multiplayer.cs:1313-14`). Item rarity 0..65535 — принятый authored ID; утверждение о «vanilla 0..11» не следует считать исчерпывающим (установленный tML XML описывает -1..13). `safeTileOnly` для blink проверяет границы/solid/lava, не универсальную безопасность; `releaseTiming` теперь честно назван `heldSpriteVisibilityHint` и не реализует distinct release schedule.

## Полный параметрический инвентарь Gameplay Author

Для каждой строки: **старый ключ → текущий ключ**, классификация, текущий тип/домен, authored единица, точное текущее описание (из registry; английский текст сохранён для сверки без домысла), имя старого wire-листа. `wire_name` — leaf; полный путь задаётся `CapabilitySpec.final_wire_paths`, compiler и указанным потребителем. `—` у units означает селектор/флаг либо отсутствие отдельной физической единицы; не приписывать величине секунды или пиксели без описания. Параметры optional отмечены `опц.`; selector `phase/damageClass` выбирает явно указанный equipment путь, не эвристический router. У каждого блока указан исходный реестр и конечный C# owner; номера строк потребителей для сложных групп дополнительно даны после таблиц. Исторический ключ **не является** принимаемым Author alias.

### `configure_item_stats` (13) — [`registry:760`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L760); C# `Common/Models/GeneratedItemData.Apply.cs::ApplyToItem`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `damageClass` | keep | string ^(?:default\|generic\|melee\|melee_no_speed\|ranged\|magic\|magic_summon_hybrid\|summon\|summon_melee_speed\|throwing\|(?!Terraria/)[A-Za-z][A-Za-z0-9_]{0,63}/[A-Za-z][A-Za-z0-9_]{0,63})$; идентификатор/селектор | Exact built-in token or loaded tModLoader DamageClass.FullName copied only from parent damageClass facts (not item FullName) | `damageClass` |
| `damage` | keep | integer [0,2000]; без отдельной единицы | Base item damage | `damage` |
| `knockback` | engine-units | number [0,20]; engine units: Item.knockBack | Item.knockBack engine strength, not pixels or damage | `knockback` |
| `useTimeTicks` | keep | integer [1,600]; ticks | Terraria use/reuse interval (60 ticks/s), not the animation length | `useTime` |
| `useAnimationTicks` | keep | integer [1,600]; ticks | Duration of one use animation, independent of useTimeTicks; differing values can allow multiple uses during one animation, not necessarily one projectile per click | `useAnimation` |
| `manaCost` | keep | integer [0,500]; без отдельной единицы | Base Item.mana points before player mana-cost modifiers, not guaranteed final mana spent | `manaCost` |
| `rarity` | keep | integer [0,65535]; без отдельной единицы | Exact loaded Item.rare ID; copy modded IDs from parent facts, do not guess | `rarity` |
| `valueCopper` | keep | integer [0,100000000]; copper | Exact Terraria Item.value field in copper; NPC shop price/base value, not an inferred player resale amount | `value` |
| `maxStack` | keep | integer [1,9999]; без отдельной единицы | Maximum stack | `maxStack` |
| `craftYield` | keep | integer [1,9999]; без отдельной единицы | Requested items per craft; actual granted stack is capped by maxStack | `craftYield` |
| `widthPx` | keep | integer [8,256]; pixels | Inventory/world hitbox width | `width` |
| `heightPx` | keep | integer [8,256]; pixels | Inventory/world hitbox height | `height` |
| `scale` | keep | number [0.25,4]; без отдельной единицы | Item display scale multiplier (1 unchanged) | `itemScale` |

### `configure_item_use` (10) — [`registry:787`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L787); C# `Content/Items/GeneratedItem.cs::CanUseItem|Content/Items/GeneratedItem.UseStyle.cs::UseStyle`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `useStyle` | keep | string {swing, eat_food, thrust, hold_up, shoot, drink_long, drink_liquid, golf_play, hidden_animation, mow_the_lawn, guitar, rapier, raise_lamp}; идентификатор/селектор | Named Terraria ItemUseStyleID | `useStyleName` |
| `autoReuse` | keep | boolean true / false; флаг | Allow repeated use while input is held | `autoReuse` |
| `useTurn` | keep | boolean true / false; флаг | Allow facing turn during use | `useTurn` |
| `hideUseGraphic` | keep | boolean true / false; флаг | Hide inventory sprite during use | `hideUseGraphic` |
| `disableMeleeHitbox` | keep | boolean true / false; флаг | Disable vanilla item melee hitbox | `disableMeleeHitbox` |
| `channel` | keep | boolean true / false; флаг | Keep use active while input is held | `channel` |
| `holdoutOffsetX` | keep | integer [-96,96]; pixels | Held draw offset X | `holdoutOffsetX` |
| `holdoutOffsetY` | keep | integer [-96,96]; pixels | Held draw offset Y | `holdoutOffsetY` |
| `handPose` | keep | опц.; string {, one_handed, two_handed, overhead, forward}; идентификатор/селектор | Exact renderer hint | `handPose` |
| `releaseTiming` → `heldSpriteVisibilityHint` | identity-rename | опц.; string {, immediate, on_release, after_charge}; идентификатор/селектор | Held-sprite visibility only, not gameplay release timing; immediate hides it, empty/on_release/after_charge keep it while use is active; latter tokens do not schedule different releases | `releaseTiming` |

### `configure_item_contact_hitbox` (2) — [`registry:811`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L811); C# `Content/Items/GeneratedItem.cs::UseItemHitbox/OnHitNPC`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `hitboxScale` | keep | number [0.5,2]; без отдельной единицы | Contact hitbox scale; 1 unchanged | `hitboxScale` |
| `contactForgivenessPx` | keep | integer [0,64]; pixels | Extend scaled contact hitbox by this many pixels on each side | `contactForgivenessPx` |

### `configure_vanilla_ammo_item` (4) — [`registry:826`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L826); C# `Common/Models/TerrariaRuntimeVocabulary.cs::ResolveAmmoCategory|Common/Models/GeneratedItemData.Apply.cs::ApplyToItem`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `ammoCategory` | keep | string {arrow, bullet, candy_corn, coin, dart, fallen_star, flare, gel, jack_o_lantern, nail_friendly, rocket, snowball, solution, stake, stynger_bolt}; идентификатор/селектор | Exact stable Terraria AmmoID category | `ammoCategory` |
| `projectileId` | keep | integer [1,1021]; без отдельной единицы | Exact vanilla ProjectileID fired when this ammo is consumed; do not guess | `ammoProjectileId` |
| `shootSpeedPxPerTick` → `shootSpeedContributionPxPerUpdate` | identity-rename | number [-20,80]; pixels/projectile update contribution | Exact Item.shootSpeed contribution of this ammo to vanilla PickAmmo | `ammoShootSpeedPxPerTick` |
| `notAmmo` | keep | boolean true / false; флаг | Exact Item.notAmmo flag for special ammo-slot/tooltip behaviour | `notAmmo` |

### `restore_resources_on_use` (3) — [`registry:844`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L844); C# `Common/Models/GeneratedItemData.Apply.cs::ApplyToItem`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `healLife` | keep | integer [0,500]; без отдельной единицы | Life restored | `healLife` |
| `healMana` | keep | integer [0,500]; без отдельной единицы | Mana restored | `healMana` |
| `potionSickness` → `usesPotionRules` | identity-rename | boolean true / false; флаг | Set Terraria Item.potion rules including Quick Heal eligibility and potion-sickness use gating; not a duration; false allows non-potion healing | `potion` |

### `apply_vanilla_buff_on_use` (2) — [`registry:861`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L861); C# `Content/Items/GeneratedItem.cs::ApplyItemEffects`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `buffId` | keep | integer [1,65535]; без отдельной единицы | Exact loaded BuffID/ModContent.BuffType; copy from parent facts, do not guess | `buffCode` |
| `durationTicks` | keep | integer [1,21600]; ticks | Buff duration | `buffTime` |

### `apply_generated_buff_on_use` (9) — [`registry:878`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L878); C# `Content/Items/GeneratedItem.cs::ApplyItemEffects`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `durationTicks` | keep | integer [1,21600]; ticks | Duration | `durationTicks` |
| `miningSpeedMultiplier` | engine-units | number [0.25,4]; engine units: pickSpeed divisor | Divides Player.pickSpeed (mining-time factor); >1 mines faster | `miningSpeedMultiplier` |
| `lightStrength` | engine-units | number [0,1.5]; engine units: RGB coefficient | Client light RGB coefficient multiplying selected light color; not tile radius | `emitLightStrength` |
| `lightColor` | keep | string {white, red, orange, yellow, green, cyan, blue, purple, pink, gray, black}; идентификатор/селектор | Canonical light color | `lightColorName` |
| `oreSenseEnabled` | declared-convert | boolean true / false; флаг; true→1, false→0 | Enable Terraria spelunker-style ore highlighting; not a radius | `oreSenseRadiusTiles` |
| `movementSpeed` → `moveSpeedBonusFactor` | identity-rename | number [-0.5,2]; engine units: additive moveSpeed factor | Additive Player.moveSpeed factor; 0.2 adds 20% before other modifiers | `movementSpeed` |
| `jumpBoost` → `jumpSpeedBonusPxPerTick` | identity-rename | number [0,8]; pixels/world tick | Add to Player.jumpSpeedBoost in pixels/tick | `jumpBoost` |
| `manaRegen` → `manaRegenBonusPoints` | identity-rename | integer [0,120]; engine units: manaRegenBonus points | Add Player.manaRegenBonus engine points; not directly mana/second | `manaRegen` |
| `lifeRegenHpPerSecond` | declared-convert | number [0,60] / шаг 0.5; HP/s; wire=author×2 | Generated buff: HP restored per second before other effects; exact half-HP steps map to Terraria Player.lifeRegen units (2 units = 1 HP/s) | `lifeRegen` |

### `configure_tool` (4) — [`registry:901`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L901); C# `Common/Models/GeneratedItemData.Apply.cs::ApplyToItem`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `pickPower` | keep | integer [0,1000]; без отдельной единицы | Terraria Item.pick tooltip power percent | `pickPower` |
| `axePowerTooltipPercent` | declared-convert | integer [0,500] / шаг 5; tooltip percent; wire=author/5 | Axe power as displayed in Terraria's tooltip; exact Item.axe internal value = this / 5 | `axePower` |
| `hammerPower` | keep | integer [0,1000]; без отдельной единицы | Terraria Item.hammer tooltip power percent | `hammerPower` |
| `miningSpeedScale` | engine-units | number [0.1,4]; engine units: pickSpeed divisor | Divides Player.pickSpeed (mining-time factor); >1 mines faster | `miningSpeedScale` |

### `configure_placeable` (3) — [`registry:919`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L919); C# `Common/Models/GeneratedItemData.Apply.cs::ApplyToItem`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `tileId` | keep | integer [-1,65535]; без отдельной единицы | Exact loaded TileID/ModContent.TileType; -1 disables | `tileId` |
| `wallId` | keep | integer [-1,65535]; без отдельной единицы | Exact loaded WallID/ModContent.WallType; -1 disables | `wallId` |
| `placeStyle` | keep | integer [0,255]; без отдельной единицы | Exact Item.placeStyle style index for the loaded tile/wall, not a universal visual style | `placeStyle` |

### `require_use_condition` (3) — [`registry:936`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L936); C# `Content/Items/GeneratedItem.cs::UseBlockedReason`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `mode` | keep | string {grounded, not_wet, life_above, mana_above}; идентификатор/селектор | Use condition | `useConditionMode` |
| `minLife` | keep | опц.; integer [0,1000]; без отдельной единицы | Current HP (Player.statLife >= minLife) required for life_above; equality allowed | `useConditionMinLife` |
| `minMana` | keep | опц.; integer [0,1000]; без отдельной единицы | Current mana points (Player.statMana >= minMana) required for mana_above; equality allowed | `useConditionMinMana` |

### `add_hold_light` (2) — [`registry:953`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L953); C# `Content/Items/GeneratedItem.cs::HoldItem`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `strength` | engine-units | number [0.01,1.5]; engine units: RGB coefficient | Client light RGB coefficient multiplying selected color (not a tile radius) | `holdLightStrength` |
| `color` | keep | string {white, red, orange, yellow, green, cyan, blue, purple, pink, gray, black}; идентификатор/селектор | Canonical light color | `holdLightColorName` |

### `move_player_on_use` (4) — [`registry:969`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L969); C# `Content/Items/GeneratedItem.cs::ApplyItemEffects`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `mode` | keep | string {recall_home, blink_to_cursor}; идентификатор/селектор | Mobility executor | `mobilityMode` |
| `rangeTiles` | keep | integer [0,120]; tiles | Maximum blink range | `mobilityRangeTiles` |
| `cooldownTicks` | keep | integer [0,3600]; ticks | Cooldown | `mobilityCooldownTicks` |
| `safeTileOnly` | keep | boolean true / false; флаг | Blink bounds, solid-tile overlap and nearby lava checks; false skips them; ignored for recall_home; not a general hazard check | `mobilitySafeTileOnly` |

### `configure_accessory` (25) — [`registry:987`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L987); C# `Content/Items/GeneratedItem.cs::UpdateAccessory`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `defensePoints` | keep | опц.; integer [-50,200]; defense_points | Add to Item.defense; Terraria applies it, not an extra equip-hook adjustment | `defense` |
| `maxLifePoints` | keep | опц.; integer [-200,1000]; life_points | Add maximum life | `maxLife` |
| `maxManaPoints` | keep | опц.; integer [-200,1000]; mana_points | Add maximum mana | `maxMana` |
| `lifeRegenHalfHpPerSecond` → `lifeRegenHpPerSecond` | declared-convert | опц.; number [-50,100] / шаг 0.5; HP/s; wire=author×2 | Add signed HP/s regeneration contribution before other Terraria effects; +1 HP/s writes +2 Player.lifeRegen engine units, -1 HP/s writes -2; 0 adds nothing | `lifeRegen` |
| `manaRegenBonusPoints` | engine-units | опц.; integer [-100,200]; engine units: manaRegenBonus points | Add raw Player.manaRegenBonus points; 0 adds nothing, not mana/s | `manaRegen` |
| `moveSpeedBonusPercent` | declared-convert | опц.; number [-90,300]; additive_percent; wire=author/100 | Add percent/100 to Player.moveSpeed | `movementSpeed` |
| `maxRunSpeedBonusPxPerTick` | keep | опц.; number [-5,20]; pixels_per_tick | Add to Player.maxRunSpeed, subject to other Terraria movement limits | `maxRunSpeed` |
| `jumpSpeedBonusPxPerTick` | keep | опц.; number [-5,20]; pixels_per_tick | Add to Player.jumpSpeedBoost (positive raises jump speed) | `jumpSpeed` |
| `genericCritChancePercentagePoints` | keep | опц.; number [-100,100]; percentage_points | Add percentage points to generic critical chance | `genericCrit` |
| `genericAttackSpeedBonusPercent` | declared-convert | опц.; number [-90,300]; additive_percent; wire=author/100 | Add percent/100 to generic attack speed | `attackSpeed` |
| `genericKnockbackBonusPercent` | declared-convert | опц.; number [-90,300]; additive_percent; wire=author/100 | Add percent/100 to generic StatModifier knockback; not flat points | `knockback` |
| `minionSlotsBonus` | keep | опц.; integer [0,20]; slots | Add minion slots | `minionSlots` |
| `sentrySlotsBonus` | keep | опц.; integer [0,20]; slots | Add sentry slots | `sentrySlots` |
| `manaCostReductionPercentagePoints` | declared-convert | опц.; number [0,90]; percentage_points; wire=author/100 | Subtract percent/100 from Player.manaCost factor, floored at 0.1 | `manaCostReduction` |
| `ammoSaveChancePercent` | declared-convert | опц.; number [0,99]; probability_percent; wire=author/100 | Equipped owner's ammo saving chance via Player.CanConsumeAmmo for any weapon; equipped item chances combine as 1−product(1−p) | `ammoSaveChance` |
| `aggroPoints` | engine-units | опц.; integer [-1000,1000]; engine units: aggro points | Add raw Player.aggro engine points (negative reduces targeting); not a probability or radius | `aggro` |
| `damageReductionPercentagePoints` | declared-convert | опц.; number [0,75]; percentage_points; wire=author/100 | Add percent/100 to Player.endurance damage reduction | `endurance` |
| `genericArmorPenetrationPoints` | keep | опц.; number [0,100]; armor_points | Add flat armor penetration points to DamageClass.Generic; not damage percent | `armorPenetration` |
| `whipRangeBonusPercent` | declared-convert | опц.; number [-90,300]; additive_percent; wire=author/100 | Add percent/100 to Player.whipRangeMultiplier | `whipRange` |
| `taggedSummonSourceDamageBonusPercent` | declared-convert | опц.; number [0,300]; source_damage_percent; wire=author/100 | Multiply summon projectile source damage by 1+percent/100 only against an NPC tagged by this owner's generated whip | `summonTagDamage` |
| `lightStrength` | engine-units | опц.; number [0,1.5]; engine units: RGB coefficient | Client-only RGB light coefficient multiplying lightColor; not tile radius; requires lightColor when positive | `lightStrength` |
| `lightColor` | keep | опц.; string {white, red, orange, yellow, green, cyan, blue, purple, pink, gray, black}; идентификатор/селектор | Explicit equipped light color | `lightColorName` |
| `fallDamageImmune` | keep | опц.; boolean true / false; флаг | Prevent fall damage while equipped | `fallDamageImmune` |
| `lavaImmune` | keep | опц.; boolean true / false; флаг | Grant lava immunity while equipped | `lavaImmune` |
| `waterWalk` | keep | опц.; boolean true / false; флаг | Walk on water while equipped | `waterWalk` |

### `configure_armor` (38) — [`registry:1000`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1000); C# `Content/Items/GeneratedItem.cs::UpdateEquip`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `slot` | keep | string {head, body, legs}; идентификатор/селектор | Armor equip slot | `slot` |
| `setKey` | keep | string ^[a-z0-9_]{0,48}$; идентификатор/селектор | Exact authored set key (empty when no matching set is intended) | `setKey` |
| `defensePoints` | keep | опц.; integer [0,200]; defense_points | Add to Item.defense; Terraria applies it, not an extra equip-hook adjustment | `defense` |
| `maxLifePoints` | keep | опц.; integer [-200,1000]; life_points | Add maximum life | `maxLife` |
| `maxManaPoints` | keep | опц.; integer [-200,1000]; mana_points | Add maximum mana | `maxMana` |
| `lifeRegenHalfHpPerSecond` → `lifeRegenHpPerSecond` | declared-convert | опц.; number [-50,100] / шаг 0.5; HP/s; wire=author×2 | Add signed HP/s regeneration contribution before other Terraria effects; +1 HP/s writes +2 Player.lifeRegen engine units, -1 HP/s writes -2; 0 adds nothing | `lifeRegen` |
| `manaRegenBonusPoints` | engine-units | опц.; integer [-100,200]; engine units: manaRegenBonus points | Add raw Player.manaRegenBonus points; 0 adds nothing, not mana/s | `manaRegen` |
| `moveSpeedBonusPercent` | declared-convert | опц.; number [-90,300]; additive_percent; wire=author/100 | Add percent/100 to Player.moveSpeed | `movementSpeed` |
| `maxRunSpeedBonusPxPerTick` | keep | опц.; number [-5,20]; pixels_per_tick | Add to Player.maxRunSpeed, subject to other Terraria movement limits | `maxRunSpeed` |
| `jumpSpeedBonusPxPerTick` | keep | опц.; number [-5,20]; pixels_per_tick | Add to Player.jumpSpeedBoost (positive raises jump speed) | `jumpSpeed` |
| `genericCritChancePercentagePoints` | keep | опц.; number [-100,100]; percentage_points | Add percentage points to generic critical chance | `genericCrit` |
| `genericAttackSpeedBonusPercent` | declared-convert | опц.; number [-90,300]; additive_percent; wire=author/100 | Add percent/100 to generic attack speed | `attackSpeed` |
| `genericKnockbackBonusPercent` | declared-convert | опц.; number [-90,300]; additive_percent; wire=author/100 | Add percent/100 to generic StatModifier knockback; not flat points | `knockback` |
| `minionSlotsBonus` | keep | опц.; integer [0,20]; slots | Add minion slots | `minionSlots` |
| `sentrySlotsBonus` | keep | опц.; integer [0,20]; slots | Add sentry slots | `sentrySlots` |
| `manaCostReductionPercentagePoints` | declared-convert | опц.; number [0,90]; percentage_points; wire=author/100 | Subtract percent/100 from Player.manaCost factor, floored at 0.1 | `manaCostReduction` |
| `ammoSaveChancePercent` | declared-convert | опц.; number [0,99]; probability_percent; wire=author/100 | Equipped owner's ammo saving chance via Player.CanConsumeAmmo for any weapon; equipped item chances combine as 1−product(1−p) | `ammoSaveChance` |
| `aggroPoints` | engine-units | опц.; integer [-1000,1000]; engine units: aggro points | Add raw Player.aggro engine points (negative reduces targeting); not a probability or radius | `aggro` |
| `damageReductionPercentagePoints` | declared-convert | опц.; number [0,75]; percentage_points; wire=author/100 | Add percent/100 to Player.endurance damage reduction | `endurance` |
| `genericArmorPenetrationPoints` | keep | опц.; number [0,100]; armor_points | Add flat armor penetration points to DamageClass.Generic; not damage percent | `armorPenetration` |
| `whipRangeBonusPercent` | declared-convert | опц.; number [-90,300]; additive_percent; wire=author/100 | Add percent/100 to Player.whipRangeMultiplier | `whipRange` |
| `taggedSummonSourceDamageBonusPercent` | declared-convert | опц.; number [0,300]; source_damage_percent; wire=author/100 | Multiply summon projectile source damage by 1+percent/100 only against an NPC tagged by this owner's generated whip | `summonTagDamage` |
| `lightStrength` | engine-units | опц.; number [0,1.5]; engine units: RGB coefficient | Client-only RGB light coefficient multiplying lightColor; not tile radius; requires lightColor when positive | `lightStrength` |
| `lightColor` | keep | опц.; string {white, red, orange, yellow, green, cyan, blue, purple, pink, gray, black}; идентификатор/селектор | Explicit equipped light color | `lightColorName` |
| `fallDamageImmune` | keep | опц.; boolean true / false; флаг | Prevent fall damage while equipped | `fallDamageImmune` |
| `lavaImmune` | keep | опц.; boolean true / false; флаг | Grant lava immunity while equipped | `lavaImmune` |
| `waterWalk` | keep | опц.; boolean true / false; флаг | Walk on water while equipped | `waterWalk` |
| `setBonusGenericCritChancePercentagePoints` | keep | опц.; number [-100,100]; percentage_points | Matching armor set (head piece only; matching head, body and legs must actually be equipped): Add percentage points to generic critical chance | `setBonusGenericCrit` |
| `setBonusMoveSpeedBonusPercent` | declared-convert | опц.; number [-90,300]; additive_percent; wire=author/100 | Matching armor set (head piece only; matching head, body and legs must actually be equipped): Add percent/100 to Player.moveSpeed | `setBonusMovementSpeed` |
| `setBonusLifeRegenHalfHpPerSecond` → `setBonusLifeRegenHpPerSecond` | declared-convert | опц.; number [-50,100] / шаг 0.5; HP/s; wire=author×2 | Matching armor set (head piece only; matching head, body and legs must actually be equipped): Add signed HP/s regeneration contribution before other Terraria effects; +1 HP/s writes +2 Player.lifeRegen engine units, -1 HP/s writes -2; 0 adds nothing | `setBonusLifeRegen` |
| `setBonusManaRegenBonusPoints` | engine-units | опц.; integer [-100,200]; engine units: manaRegenBonus points | Matching armor set (head piece only; matching head, body and legs must actually be equipped): Add raw Player.manaRegenBonus points; 0 adds nothing, not mana/s | `setBonusManaRegen` |
| `setBonusMinionSlotsBonus` | keep | опц.; integer [0,20]; slots | Matching armor set (head piece only; matching head, body and legs must actually be equipped): Add minion slots | `setBonusMinionSlots` |
| `setBonusSentrySlotsBonus` | keep | опц.; integer [0,20]; slots | Matching armor set (head piece only; matching head, body and legs must actually be equipped): Add sentry slots | `setBonusSentrySlots` |
| `setBonusManaCostReductionPercentagePoints` | declared-convert | опц.; number [0,90]; percentage_points; wire=author/100 | Matching armor set (head piece only; matching head, body and legs must actually be equipped): Subtract percent/100 from Player.manaCost factor, floored at 0.1 | `setBonusManaCostReduction` |
| `setBonusAmmoSaveChancePercent` | declared-convert | опц.; number [0,99]; probability_percent; wire=author/100 | Matching armor set (head piece only; matching head, body and legs must actually be equipped): Equipped owner's ammo saving chance via Player.CanConsumeAmmo for any weapon; equipped item chances combine as 1−product(1−p) | `setBonusAmmoSaveChance` |
| `setBonusAggroPoints` | engine-units | опц.; integer [-1000,1000]; engine units: aggro points | Matching armor set (head piece only; matching head, body and legs must actually be equipped): Add raw Player.aggro engine points (negative reduces targeting); not a probability or radius | `setBonusAggro` |
| `setBonusDamageReductionPercentagePoints` | declared-convert | опц.; number [0,75]; percentage_points; wire=author/100 | Matching armor set (head piece only; matching head, body and legs must actually be equipped): Add percent/100 to Player.endurance damage reduction | `setBonusEndurance` |
| `setBonusGenericArmorPenetrationPoints` | keep | опц.; number [0,100]; armor_points | Matching armor set (head piece only; matching head, body and legs must actually be equipped): Add flat armor penetration points to DamageClass.Generic; not damage percent | `setBonusArmorPenetration` |

### `add_equipment_damage_bonus` (3) — [`registry:1017`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1017); C# `Content/Items/GeneratedItem.cs::UpdateAccessory/UpdateEquip/UpdateArmorSet`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `phase` | keep | string {equipped, matching_armor_set}; идентификатор/селектор | equipped applies while wearing this accessory/armor; matching_armor_set applies only on the head of a complete matching set | `phase` |
| `damageClass` | keep | string {generic, melee, ranged, magic, summon}; идентификатор/селектор | Equipped damage class; this equipment operation supports only these five classes | `damageClass` |
| `bonusPercent` | declared-convert | number [-90,300]; additive_percent; wire=author/100 | Add this percent to the selected class damage additive modifier; 15 means +15% | `bonusPercent` |

### `configure_spawn` (6) — [`registry:1034`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1034); C# `Content/Projectiles/GeneratedProjectile.cs::SpawnRuntimeEntity/Configure`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `speedPxPerTick` → `speedPxPerUpdate` | identity-rename | number [0,80]; pixels/projectile update | Initial Projectile.velocity pixels per projectile update; without steering/collisions, speed 10 with extraUpdates=1 moves ~20 px/world tick | `speedPxPerTick` |
| `count` | keep | integer [1,12]; без отдельной единицы | Default root binding spawn count per activation; event actions and target_and_fire select their own counts | `count` |
| `spreadRadians` | keep | number [0,6.283185307179586]; radians | Total angular spread | `spreadRadians` |
| `offsetPx` | keep | integer [-128,256]; pixels | Forward spawn offset | `offsetPx` |
| `aim` | keep | string {cursor, facing, velocity, none}; идентификатор/селектор | Initial aim source: cursor=spawn-to-cursor, facing=owner direction, velocity=incoming activation direction, none=zero velocity | `aim` |
| `placement` | keep | string {item_use_origin, owner_center, cursor, ground_at_cursor, above_cursor}; идентификатор/селектор | Spawn position | `placement` |

### `set_projectile_damage` (4) — [`registry:1053`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1053); C# `Content/Projectiles/GeneratedProjectile.cs::Configure`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `damageClass` | keep | string ^(?:default\|generic\|melee\|melee_no_speed\|ranged\|magic\|magic_summon_hybrid\|summon\|summon_melee_speed\|throwing\|(?!Terraria/)[A-Za-z][A-Za-z0-9_]{0,63}/[A-Za-z][A-Za-z0-9_]{0,63})$; идентификатор/селектор | Exact built-in token or loaded tModLoader DamageClass.FullName copied only from parent damageClass facts (not item FullName) | `damageClass` |
| `damage` | keep | integer [0,2000]; без отдельной единицы | Projectile base damage | `damage` |
| `knockback` | engine-units | number [0,20]; engine units: Projectile.knockBack | Projectile.knockBack engine strength, not pixels or damage | `knockback` |
| `ownerHitCheck` | keep | boolean true / false; флаг | Require owner line/held hit check | `ownerHitCheck` |

### `set_projectile_lifetime` (1) — [`registry:1070`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1070); C# `Content/Projectiles/GeneratedProjectile.cs::Configure`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `lifetimeTicks` | keep | integer [1,21600]; ticks | Lifetime | `lifetimeTicks` |

### `set_projectile_hitbox` (4) — [`registry:1082`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1082); C# `Content/Projectiles/GeneratedProjectile.cs::Configure`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `widthPx` | keep | integer [4,192]; pixels | Hitbox width | `widthPx` |
| `heightPx` | keep | integer [4,192]; pixels | Hitbox height | `heightPx` |
| `drawScale` | keep | number [0.25,4]; без отдельной единицы | Projectile sprite draw multiplier before entity visual scale; 1 unchanged, not damage hitbox size | `drawScale` |
| `hitboxScale` | keep | number [0.25,3]; без отдельной единицы | Runtime damage hitbox multiplier; 1 unchanged (beam/whip use special line collisions) | `hitboxScale` |

### `set_projectile_collision` (7) — [`registry:1099`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1099); C# `Content/Projectiles/GeneratedProjectile.cs::Configure`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `tileCollide` | keep | boolean true / false; флаг | Collide with solid tiles | `tileCollide` |
| `ignoreWater` | keep | boolean true / false; флаг | Ignore Terraria liquid drag; false keeps vanilla water interaction | `ignoreWater` |
| `bounceCount` | keep | integer [0,32]; без отдельной единицы | Maximum custom tile bounces | `bounceCount` |
| `pierce` | keep | integer [-1,100]; без отдельной единицы | Terraria Projectile.penetrate count; -1 means infinite | `pierce` |
| `extraUpdates` | keep | integer [0,5]; без отдельной единицы | Terraria Projectile.extraUpdates: adds this many AI/movement updates per world tick (1 + extraUpdates total) | `extraUpdates` |
| `npcImmunityMode` | keep | string {owner, local}; идентификатор/селектор | owner uses Terraria shared owner immunity; local gives this projectile its own NPC timers | `npcImmunityMode` |
| `localNpcHitCooldownTicks` → `localNpcHitCooldownEngineUnits` | identity-rename | integer [-1,600]; engine units: local NPC cooldown counts | Only npcImmunityMode=local: direct unscaled Projectile.localNPCHitCooldown, not a world-tick duration. -1 lets this projectile hit each NPC only once; 0..600 are engine local cooldown counts. owner mode uses shared owner immunity instead; with extraUpdates>0 do not infer elapsed seconds | `localNpcHitCooldownTicks` |

### `move_straight` (0) — [`registry:1147`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1147); C# `Content/Projectiles/GeneratedProjectile.Executors.cs::RunMovement/RunController`

Параметров нет; `move_straight` оставляет скорость без изменения (`GeneratedProjectile.Executors.cs:197-200`).

### `move_slow_homing` (2) — [`registry:1148`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1148); C# `Content/Projectiles/GeneratedProjectile.Executors.cs::RunMovement/RunController`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `rangeTiles` | keep | number [1,120]; tiles | Target search radius | `rangeTiles` |
| `homingStrength` | engine-units | number [0.001,1]; engine units: velocity lerp fraction | Per movement-update linear interpolation fraction toward target velocity | `homingStrength` |

### `move_gravity_arc` (1) — [`registry:1152`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1152); C# `Content/Projectiles/GeneratedProjectile.Executors.cs::RunMovement/RunController`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `gravityPerTick` → `gravityVelocityPerUpdate` | identity-rename | number [0.001,2]; engine units: vertical velocity increment per update | Add to vertical velocity (pixels/update) per projectile update | `gravityPerTick` |

### `move_drift` (1) — [`registry:1155`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1155); C# `Content/Projectiles/GeneratedProjectile.Executors.cs::RunMovement/RunController`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `velocityRetention` | engine-units | number [0.8,1.05]; engine units: velocity multiplier per update | Multiply velocity each projectile update (1 + extraUpdates per world tick); 1 preserves speed, below 1 slows, above 1 accelerates; not necessarily retention per 1/60 s | `velocityRetention` |

### `move_orbit` (1) — [`registry:1158`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1158); C# `Content/Projectiles/GeneratedProjectile.Executors.cs::RunMovement/RunController`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `rangeTiles` | keep | number [1,80]; tiles | Orbit leash | `rangeTiles` |

### `move_boomerang` (2) — [`registry:1161`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1161); C# `Content/Projectiles/GeneratedProjectile.Executors.cs::RunMovement/RunController`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `returnAfterTicks` | keep | integer [1,600]; ticks | Outbound duration | `returnAfterTicks` |
| `returnSpeed` | keep | number [1,80]; pixels/projectile update | Return speed | `returnSpeed` |

### `move_bounce` (1) — [`registry:1165`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1165); C# `Content/Projectiles/GeneratedProjectile.Executors.cs::RunMovement/RunController`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `gravityPerTick` → `gravityVelocityPerUpdate` | identity-rename | number [0.001,2]; engine units: vertical velocity increment per update | Add to vertical velocity (pixels/update) per projectile update | `gravityPerTick` |

### `move_sine_homing` (3) — [`registry:1168`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1168); C# `Content/Projectiles/GeneratedProjectile.Executors.cs::RunMovement/RunController`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `rangeTiles` | keep | number [1,120]; tiles | Target search radius | `rangeTiles` |
| `homingStrength` | engine-units | number [0.001,1]; engine units: velocity lerp fraction | Per movement-update linear interpolation fraction toward target velocity | `homingStrength` |
| `waveAmplitude` → `waveVelocityCoefficient` | identity-rename | number [0,64]; engine units: lateral velocity coefficient | Raw lateral velocity coefficient: sin(age×0.18) × waveVelocityCoefficient × 0.03 before velocity direction normalization; not displacement pixels | `waveAmplitude` |

### `move_phase` (1) — [`registry:1173`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1173); C# `Content/Projectiles/GeneratedProjectile.Executors.cs::RunMovement/RunController`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `phaseStrength` | engine-units | number [0,1]; engine units: coupled rotation/alpha coefficient | Per-update velocity rotation = sin(age×0.1) × strength × 0.01 radians AND alpha = int(80×strength); not collision phasing | `phaseStrength` |

### `move_accelerate` (2) — [`registry:1176`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1176); C# `Content/Projectiles/GeneratedProjectile.Executors.cs::RunMovement/RunController`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `acceleration` → `speedMultiplierPerUpdate` | identity-rename | number [1.0,1.2]; engine units: velocity multiplier per update | Velocity multiplier per projectile update until maxSpeed cap; 1 unchanged | `acceleration` |
| `maxSpeed` | keep | number [1,80]; pixels/projectile update | Speed cap | `maxSpeed` |

### `move_spiral` (1) — [`registry:1180`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1180); C# `Content/Projectiles/GeneratedProjectile.Executors.cs::RunMovement/RunController`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `turnRadiansPerTick` → `turnRadiansPerUpdate` | identity-rename | number [-0.5,0.5]; radians/update | Angular velocity turn per projectile update | `turnRadiansPerTick` |

### `move_vortex_orb` (2) — [`registry:1183`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1183); C# `Content/Projectiles/GeneratedProjectile.Executors.cs::RunMovement/RunController`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `pullStrength` | engine-units | number [0,4]; engine units: NPC velocity impulse coefficient | Add NPC velocity impulse of strength × clamped knockBackResist toward center per projectile update | `pullStrength` |
| `rangeTiles` | keep | number [1,80]; tiles | Pull radius | `rangeTiles` |

### `move_blackhole_pull` (2) — [`registry:1187`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1187); C# `Content/Projectiles/GeneratedProjectile.Executors.cs::RunMovement/RunController`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `pullStrength` | engine-units | number [0,4]; engine units: NPC velocity impulse coefficient | Add NPC velocity impulse of strength × clamped knockBackResist toward center per projectile update | `pullStrength` |
| `rangeTiles` | keep | number [1,80]; tiles | Pull radius | `rangeTiles` |

### `move_proximity_missile` (3) — [`registry:1191`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1191); C# `Content/Projectiles/GeneratedProjectile.Executors.cs::RunMovement/RunController`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `rangeTiles` | keep | number [1,120]; tiles | Detection/search radius | `rangeTiles` |
| `homingStrength` | engine-units | number [0.001,1]; engine units: velocity lerp fraction | Per movement-update linear interpolation fraction toward target velocity | `homingStrength` |
| `proximityRadiusPx` | keep | integer [4,512]; pixels | Trigger radius | `proximityRadiusPx` |

### `move_returning_glaive` (2) — [`registry:1196`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1196); C# `Content/Projectiles/GeneratedProjectile.Executors.cs::RunMovement/RunController`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `returnAfterTicks` | keep | integer [1,600]; ticks | Outbound duration | `returnAfterTicks` |
| `returnSpeed` | keep | number [1,80]; pixels/projectile update | Return speed | `returnSpeed` |

### `move_expanding_wave` (2) — [`registry:1200`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1200); C# `Content/Projectiles/GeneratedProjectile.Executors.cs::RunMovement/RunController`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `scalePerTick` → `scaleGrowthPerUpdate` | identity-rename | number [0.001,0.5]; engine units: scale increment per update | Additive Projectile.scale delta per projectile update, capped by maxScale | `scalePerTick` |
| `maxScale` | keep | number [0.25,4]; без отдельной единицы | Projectile.scale cap (not a pixel radius) | `maxScale` |

### `move_flail_tether` (2) — [`registry:1204`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1204); C# `Content/Projectiles/GeneratedProjectile.Executors.cs::RunMovement/RunController`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `rangeTiles` | keep | number [2,60]; tiles | Maximum tether length | `rangeTiles` |
| `returnSpeed` | keep | number [1,80]; pixels/projectile update | Return speed | `returnSpeed` |

### `move_yoyo_hover` (2) — [`registry:1208`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1208); C# `Content/Projectiles/GeneratedProjectile.Executors.cs::RunMovement/RunController`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `rangeTiles` | keep | number [2,60]; tiles | Cursor leash | `rangeTiles` |
| `returnSpeed` | keep | number [1,80]; pixels/projectile update | Return speed | `returnSpeed` |

### `move_whip_lash` (2) — [`registry:1212`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1212); C# `Content/Projectiles/GeneratedProjectile.Executors.cs::RunMovement/RunController`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `rangeTiles` | keep | number [2,60]; tiles | Lash reach | `rangeTiles` |
| `segments` | keep | integer [3,48]; без отдельной единицы | Collision curve segments | `segments` |

### `move_forward_then_retract` (2) — [`registry:1216`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1216); C# `Content/Projectiles/GeneratedProjectile.Executors.cs::RunMovement/RunController`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `rangeTiles` | keep | number [1,20]; tiles | Maximum reach | `rangeTiles` |
| `durationTicks` | keep | integer [2,240]; ticks | Full forward/retract cycle | `durationTicks` |

### `channel_beam` (3) — [`registry:1224`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1224); C# `Content/Projectiles/GeneratedProjectile.Executors.cs::RunMovement/RunController`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `rangeTiles` | keep | number [1,120]; tiles | Beam length | `rangeTiles` |
| `widthPx` | keep | number [2,128]; pixels | Beam collision width | `widthPx` |
| `warmupTicks` | keep | integer [0,600]; ticks | Warmup before full damage | `warmupTicks` |

### `charge_then_release` (2) — [`registry:1240`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1240); C# `Content/Projectiles/GeneratedProjectile.Executors.cs::RunMovement/RunController`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `chargeTicks` | keep | integer [1,600]; ticks | Full charge duration | `chargeTicks` |
| `powerMultiplier` | keep | number [1,4]; без отдельной единицы | Full-charge damage/knockback and release velocity multiplier; partial charge interpolates from 1; 1 unchanged | `powerMultiplier` |

### `target_and_fire` (4) — [`registry:1255`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1255); C# `Content/Projectiles/GeneratedProjectile.Executors.cs::RunMovement/RunController`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `shotEntity` | keep | string ^[a-z][a-z0-9_]{0,47}$; идентификатор/селектор | Referenced projectile entity id | `shotEntityId` |
| `intervalTicks` | keep | integer [6,3600]; ticks | Firing interval | `intervalTicks` |
| `rangeTiles` | keep | number [1,120]; tiles | Soft target range: previous target may be chosen outside it after distance discount | `rangeTiles` |
| `sameTargetBias` | engine-units | number [0,1]; engine units: distance-score discount | Previous target distance multiplied by (1 − min(bias, 0.9)); 0.9..1 saturates at 0.9 | `sameTargetBias` |

### `spawn_over_target` (2) — [`registry:1272`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1272); C# `Content/Projectiles/GeneratedProjectile.cs::SpawnRuntimeEntity/Configure`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `heightTiles` | keep | number [1,80]; tiles | Vertical spawn height | `heightTiles` |
| `delayTicks` | keep | integer [0,600]; ticks | Telegraph delay | `delayTicks` |

### `spawn_entity_on_event` (7) — [`registry:1287`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1287); C# `Common/Runtime/RuntimeProgramExecutor.cs::ExecuteAction`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `event` | keep | string {on_use, on_spawn, on_hit, on_crit, on_tile_collision, on_expire, on_kill, periodic, on_release, channel_complete}; идентификатор/селектор | Source event | `event` |
| `entity` | keep | string ^[a-z][a-z0-9_]{0,47}$; идентификатор/селектор | Referenced entity id | `entityId` |
| `count` | keep | integer [1,12]; без отдельной единицы | Spawn count | `count` |
| `spreadRadians` | keep | number [0,6.283185307179586]; radians | Total angular spread | `spreadRadians` |
| `damageMultiplier` | keep | number [0,4]; без отдельной единицы | Multiplier applied to the referenced child entity's authored base damage | `damageMultiplier` |
| `delayTicks` | keep | integer [0,600]; ticks | Delay after event | `delayTicks` |
| `periodTicks` | keep | опц.; integer [6,3600]; ticks | Required for periodic event | `periodTicks` |

### `apply_status_on_event` (4) — [`registry:1310`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1310); C# `Common/Runtime/RuntimeProgramExecutor.cs::ExecuteAction`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `event` | keep | string {on_hit, on_crit}; идентификатор/селектор | Source event | `event` |
| `buffId` | keep | integer [1,65535]; без отдельной единицы | Exact loaded BuffID/ModContent.BuffType; copy from parent facts, do not guess | `buffId` |
| `durationTicks` | keep | integer [1,21600]; ticks | Status duration | `durationTicks` |
| `delayTicks` | keep | опц.; integer [0,600]; ticks | Delay this exact action after the chosen event; 0 executes immediately | `delayTicks` |

### `damage_area_on_event` (4) — [`registry:1328`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1328); C# `Common/Runtime/RuntimeProgramExecutor.cs::ExecuteAction`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `event` | keep | string {on_hit, on_crit, on_tile_collision, on_expire, on_kill}; идентификатор/селектор | Source event | `event` |
| `radiusPx` | keep | integer [8,768]; pixels | Damage radius | `radiusPx` |
| `damageMultiplier` | keep | number [0.05,4]; без отдельной единицы | Multiply event-owning entity's authored base damage: item_body uses configure_item_stats.damage, projectile uses set_projectile_damage.damage; rounded, at least 1 before target defense. 1 is base damage, 0.05 is 5% of base, not +5% or damageDone | `damageMultiplier` |
| `delayTicks` | keep | опц.; integer [0,600]; ticks | Delay this exact action after the chosen event; 0 executes immediately | `delayTicks` |

### `chain_damage_on_event` (5) — [`registry:1346`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1346); C# `Common/Runtime/RuntimeProgramExecutor.cs::ExecuteAction`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `event` | keep | string {on_hit, on_crit}; идентификатор/селектор | Source event | `event` |
| `count` | keep | integer [1,12]; без отдельной единицы | Maximum chained targets | `count` |
| `rangeTiles` | keep | number [1,60]; tiles | Search radius | `rangeTiles` |
| `damageMultiplier` | keep | number [0.05,2]; без отдельной единицы | Multiply event-owning entity's authored base damage: item_body uses configure_item_stats.damage, projectile uses set_projectile_damage.damage; rounded, at least 1 before target defense. 1 is base damage, 0.05 is 5% of base, not +5% or damageDone | `damageMultiplier` |
| `delayTicks` | keep | опц.; integer [0,600]; ticks | Delay this exact action after the chosen event; 0 executes immediately | `delayTicks` |

### `pull_on_event` (6) — [`registry:1365`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1365); C# `Common/Runtime/RuntimeProgramExecutor.cs::ExecuteAction`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `event` | keep | string {on_hit, periodic, on_expire}; идентификатор/селектор | Source event | `event` |
| `mode` | keep | string {target_to_owner, target_to_entity, owner_to_target}; идентификатор/селектор | Pull direction | `mode` |
| `strength` | engine-units | number [0.01,4]; engine units: velocity impulse coefficient per event | Add velocity impulse toward selected endpoint on each event (NPC impulse also multiplies knockBackResist); not displacement | `strength` |
| `radiusTiles` | keep | number [1,60]; tiles | NPC search radius only with no directTarget; ignored for owner_to_target | `radiusTiles` |
| `periodTicks` | keep | опц.; integer [6,3600]; ticks | Required for periodic event | `periodTicks` |
| `delayTicks` | keep | опц.; integer [0,600]; ticks | Delay this exact action after the chosen event; 0 executes immediately | `delayTicks` |

### `heal_owner_on_event` (4) — [`registry:1385`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1385); C# `Common/Runtime/RuntimeProgramExecutor.cs::ExecuteAction`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `event` | keep | string {on_hit, on_crit}; идентификатор/селектор | Source event | `event` |
| `damageFraction` | keep | number [0.001,1]; без отдельной единицы | Fraction of damageDone healed (0.15 = 15%), capped by maxHeal; not a whole-number percent | `damageFraction` |
| `maxHeal` | keep | integer [1,200]; HP | Per-event heal cap | `maxHeal` |
| `delayTicks` | keep | опц.; integer [0,600]; ticks | Delay this exact action after the chosen event; 0 executes immediately | `delayTicks` |

### `move_owner_on_event` (5) — [`registry:1403`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1403); C# `Common/Runtime/RuntimeProgramExecutor.cs::ExecuteAction`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `event` | keep | string {on_hit, on_tile_collision, on_expire}; идентификатор/селектор | Source event | `event` |
| `rangeTiles` | keep | integer [1,120]; tiles | Maximum movement range | `rangeTiles` |
| `cooldownTicks` | keep | integer [0,3600]; ticks | Shared owner mobility cooldown | `cooldownTicks` |
| `safeTileOnly` | keep | boolean true / false; флаг | Check destination bounds, solid-tile overlap and nearby lava; false skips these checks; not a general hazard check | `safeTileOnly` |
| `delayTicks` | keep | опц.; integer [0,600]; ticks | Delay this exact action after the chosen event; 0 executes immediately | `delayTicks` |

### `emit_light_while_active` (2) — [`registry:1422`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py#L1422); C# `Content/Projectiles/GeneratedProjectile.Executors.cs::AI`

| Снимок → текущий param | Класс | Домен; authored единица | Смысл (registry) | Wire leaf |
|---|---|---|---|---|
| `strength` | engine-units | number [0.01,1.5]; engine units: RGB coefficient | Client light RGB coefficient multiplying selected color (not a tile radius) | `strength` |
| `color` | keep | string {white, red, orange, yellow, green, cyan, blue, purple, pink, gray, black}; идентификатор/селектор | Canonical light color | `color` |


## Привязка к terminal consumers и ограничения интерпретации

- **Item/use/tool/equipment (15 capabilities, 125 строк snapshot):** `GeneratedItemData.Apply.cs:34-149`, `GeneratedItem.cs:178-590`, `InfiniCraftPlayer.Mobility.cs:150-374`, `GeneratedHeldItemDrawLayer.cs:109-113,353-408`; selected class damage — `compiler.py:225-241`; placement — `compiler.py:392-418`. `manaCost` — базовая `Item.mana`, итоговый расход меняется модификаторами. Ammo `shootSpeedContributionPxPerUpdate` — подписанный вклад в `Item.shootSpeed`, не финальная скорость снаряда. `miningSpeedMultiplier/miningSpeedScale` — делитель `Player.pickSpeed` (меньше быстрее), `manaRegenBonusPoints` — сырые `Player.manaRegenBonus`, `aggroPoints` — `Player.aggro`, `lightStrength` — коэффициенты `Lighting.AddLight`, не радиус. Equipment speed/attack/knockback/mana/ammo/endurance/whip/tag bonuses уже имели `/100`, но результат зависит от других модификаторов/ограничений; armor set действует лишь для подходящего комплекта. `oreSenseEnabled` включает `Player.findTreasure`, не радиус. Тики item use и buff — счётчики движка, не обещание постоянной real-time длительности.
- **Projectile spawn/collision/movement/controller (с `configure_spawn` до `spawn_over_target`):** `GeneratedProjectile.cs:53-54,165-190,220-267`, `GeneratedProjectile.Executors.cs:20-58,197-467`, `GeneratedProjectile.RuntimeEvents.cs:55-80,92-125,148-164`; `compiler.py:264-317`. `extraUpdates=N` даёт `N+1` AI/движений на world tick, поэтому speed/gravity/rotation/scale и `localNPCHitCooldown` не являются секундными величинами; `returnSpeed` — target скорости после lerp. `lifetimeTicks`, `chargeTicks`, `warmupTicks`, `returnAfterTicks` задаются в world ticks и преобразуются к updates. `pierce=-1` означает бесконечное пробивание, `localNpcHitCooldownEngineUnits=-1` — one-hit-per-NPC в local immunity, `delayTicks=0` — немедленно; сохранить sentinels. `phaseStrength` одновременно меняет rotation и alpha, `sameTargetBias` насыщается на 0.9, `waveVelocityCoefficient` нормализуется при вычислении направления; их нельзя обратимо заменить на физические углы/скорости/проценты. `charge_then_release.powerMultiplier` воздействует также на release velocity (`GeneratedProjectile.Executors.cs:151`), не только damage/knockback. `target_and_fire.rangeTiles` — мягкий score range, а не строгая геометрическая граница.
- **Events (7 capabilities):** `compiler.py:321-353`; `RuntimeProgramSpec.cs:829-891`, `RuntimeProgramExecutor.cs:77-270`, `RuntimeDelayedActionScheduler.cs:153-170`, `GeneratedProjectile.RuntimeEvents.cs:55-80`, `GeneratedItem.cs:378-454`. `spawn_entity_on_event.count` — число детей, `chain_damage_on_event.count` — максимум дополнительных NPC. `damageMultiplier` опирается на base damage источника, `heal_owner_on_event.damageFraction` — доля фактически нанесённого `damageDone`; `maxHeal` — HP/cобытие, имя пока не переименовано. `pull_on_event.strength` — per-event velocity impulse с `knockBackResist`, не сила/секунду. `periodTicks` для item/projectile следует разным clock-путям; `delayTicks` — scheduler world ticks. `move_owner_on_event.safeTileOnly` не равен общей гарантии безопасности.
- **Отдельно `emit_light_while_active` (2 строки), а не предположение из roster движения:** `GeneratedProjectile.Executors.cs::AI` → `runtimeProgram.entities[].light.strength/color`, RGB коэффициент `Lighting.AddLight`, цветовой токен; этот cap входит в итог 52/229/180.

## Author/Repair: структурные входы вне `calls[].params`

`program_schema.py:45-162,165-363,595-667`, `author_item_contract.py:62-108`, `binding_use_policy.py:10-17,122-147`: Author `name`, `category`, `concept.literalSynthesis/coreMechanic/parentAContribution/parentBContribution/playerExperience`, `concept.plannedPlayerActions[].input/intent`, `realization.description/playerExperience/selfEvaluation.*.verdict/summary/actionChecks[]/behaviorChecks[]` и их текст/intentionality/reason — текст, перечисления и ссылки, не физические единицы. `category` не gameplay-router. `runtimeProgram.apiVersion/schema`, `primaryEntityId`, `entities[].id/kind`, `bindings[].id/input/usePolicy.action.kind/targetId/placementCallId`, `calls[].id/fn/target` — явные ID и discriminators; `runtimeRefs` и self-evaluation checks — ссылки/транспортные лимиты, не игровые счётчики. `bindings[].usePolicy.stackCost` — ровно 0 либо 1 экземпляр **generated item** на принятый use; `contactDamage` — независимый флаг contact-hitbox, не число damage. В Repair `entitiesUpsert/entityIdsDelete/entityIndicesDelete`, `bindingsUpsert/bindingIdsDelete/bindingIndicesDelete`, `callsUpsert/callIdsDelete/callIndicesDelete`, `callParamKeysDelete/callPropertyKeysDelete` (`callId/key`), `primaryEntitySelection`, `exclusiveInputSelections` (`input/keepBindingId`), `metadataPatch`, `realizationReplacement`, `note` — операции над явными ID/ключами/текстом. `*IndicesDelete` — **нулевая индексация массива**, соответственно 0..11 / 0..7 / 0..47, не игровые тики/расстояние. Nullable selection — контрольный sentinel, не новый выбранный объект. Лимиты массивов Author `entities 1..12`, `bindings 0..8`, `calls 1..48` и Repair maxima — transport/schema bounds. `runtimeProgram.limits.maxEntityCount/maxChildDepth/maxEventSpawnsPerActivation` задаёт compiler (`compiler.py:449-462`), **не** модель; глубина — рёбра графа, бюджет событий — bounded runtime ledger (`RuntimeProgramExecutor.cs:19-31,123-153`). Эти structural поля не прибавлены к 229 параметрам capabilities.

## Visual Director и условный Visual Repair — все authored поля

Источник: `LocalGenerator/infini_local/pipelines/visual_generation_pipeline.py:113-237,713-745,771-947`. Ordinary JSON: `schema` (версия), `item` (обязателен), `entities` (одна запись на runtime entity), `animationPlan` (текст до 1200 символов), `equipOverlay` (только когда требуется equipment overlay). `item.prompt` (1..1400 символов), `negativePrompt` (0..700), `silhouette` (1..700), `visualIdentity` (1..700), `palette` (1..8 непустых цветовых текстов по ≤48 символов) — описание внешности; длины строк не визуальные единицы. `equipOverlay.prompt/silhouette/visualIdentity` — отдельные описания и canvas. Схема entity зависит от `assetMode`: **`baked_sprite`** требует `entityId`, `assetMode`, `visualProjectRef` (`item`/`entity`), `prompt`, `silhouette`, `visualIdentity`, `scale`; **`reuse_item_icon`** требует `entityId`, `assetMode`, `visualProjectRef=item`, `scale` без отдельного prompt; **`runtime_geometry`/`no_asset`** требуют `entityId`, `assetMode`, `visualProjectRef=none`, `scale` без sprite prompt. `entityId` ссылается на готовый runtime entity; эти discriminators — не габариты и не inferred asset. Visual Repair: `schema`, **частичный** `itemPatch` или null, условно **целый** `equipOverlayPatch` или null, полные `entitiesUpsert`, `entityIdsDelete`, `entityIndicesDelete` (нулевые индексы прежнего списка, 0..2×entity_count), `animationPlan` либо null, `note`; frozen-first permission-aware merge, не повторное авторство валидных полей.

| Authored Visual число | Класс и смысл | Источник → consumer |
|---|---|---|
| `item.preferredCanvasSize` ∈ {24,32,48,64,96,128} | keep/identity: запрошенная сторона square canvas в PNG-пикселях, **не** размер предмета в мире/фактический занятый силуэт | `visual_generation_pipeline.py:123,906` → `visual_sprite_generation.py:142,157-195`, `sprite_postprocess.py:827-885` |
| `equipOverlay.preferredCanvasSize` ∈ {32,48,64,96} | keep/identity: сторона целевого overlay PNG, **не** экранный размер на игроке | `visual_generation_pipeline.py:139` → `visual_asset_plan.py:201-225`; `GeneratedEquipOverlayDrawLayer.cs:89-125` подгоняет фактический draw |
| `item.inventoryScale` [.25,4] | engine-units/identity: multiplicative inventory draw factor после texture/frame fit, нейтраль 1 | `visual_generation_pipeline.py:124,907` → `GeneratedItem.cs:593-603` |
| `item.worldScale` [.25,4] | engine-units/identity: отдельный world-item draw factor, нейтраль 1 | `visual_generation_pipeline.py:125,908` → `GeneratedItem.cs:606-617` |
| `entities[].scale` [.25,4] **для всех assetMode**, включая `no_asset` | engine-units/identity: visual multiplier `Hitbox.DrawScale × Visual.Scale`, не collision hitbox; `no_asset` может ничего не отрисовать | `visual_generation_pipeline.py:147-185,939` → `GeneratedProjectile.cs:168` |

`runtimeEntities.hitbox` в prompt — read-only gameplay context, не инструкция считать Visual `scale` размерами hitbox. Обычный и Repair schema сейчас включают описания числовых Visual полей (`visual_generation_pipeline.py:123-147`); это **метаданные**, не изменение числового wire. Image generation/postprocessing может не дать точный pixel footprint, поэтому canvas не гарантирует размер изображения на экране.

## VFX Director и условный VFX Repair — все authored поля

Источник: `LocalGenerator/infini_local/core/vfx_manifest.py:44-82,116-219,232-301,361-406,521-829`; C# DTO `Common/Models/VfxManifestSpec.cs:124-255`; terminal `Common/VFX/InfiniVfxRuntime.cs`, `InfiniItemVfxRuntime.cs`, `InfiniDetachedVfxSystem.cs`. Ordinary JSON: `schema`, `effectMagnitude`, `visualBudgetClass` (tiny/small/normal/large/signature), `motif` (`element`, `shapeLanguage`, `motionLanguage`, `paletteRole`, `rhythm`, `chaos`), `slots` длиной 0..`min(12,VFX_LLM_DIRECTOR_MAX_SLOTS)`. Каждый slot обязательно задаёт **все**: `id`, `entityId`, `event`, `rendererKind`, `backend`, `textureRole`, `particleRole`, `anchor`, `channel`, `lane`, `emissionMode`, `blend`, `layer`, `particleSystemId`, `scale`, `density`, `duration`, `alpha`, `spread`, `jitter`, `fadeIn`, `fadeOut`, `budgetWeight`, `signatureWeight`, `visualCost`, `startTick`, `repeatEvery`, `spritePrompt`, `spriteNegativePrompt`. `entityId+event` — конкретная разрешённая пара из read-only `runtimePairs`, presentation не Gameplay; перечисления renderer/backend/texture/particle/anchor/channel/lane/emission/blend/layer/system — категориальные, не числовые единицы. `spritePrompt` до 1400 и `spriteNegativePrompt` до 700 символов meaningful только для `impactSprite`; переносятся на impact entity, а не в slot runtime DTO. `motif.element` используется для named color; остальные текстовые motif поля — художественные описания, не скрытые физические параметры.

| Authored VFX число; домен | Класс; действительное использование / отсутствие потребителя |
|---|---|
| `effectMagnitude` [0,1] | engine-units/identity, **не реализовано в renderer**: сохраняемая presentation metadata; не intensity multiplier (`vfx_manifest.py:757,782-793`, DTO `VfxManifestSpec.cs:92,164`). |
| `motif.rhythm` [.2,3], `motif.chaos` [0,1] | engine-units/identity, **не реализовано в renderer**: retained motif metadata, не BPM/вероятность (`vfx_manifest.py:784`, DTO `:124-140`). |
| `slots[].scale` [.15,5] | engine-units/identity, renderer-specific: sprite trail × projectile.scale, primitive thickness `max(1,2×scale)`, beam length `max(20,48×scale)`, cross radius `max(4,9×scale)`; light coefficients/ dust/impact draw имеют другие clamps. Нет единого sizePx (`InfiniVfxRuntime.cs:124-139,207-249,287-306`; `InfiniItemVfxRuntime.cs:98-114`; `InfiniDetachedVfxSystem.cs:72-102`). |
| `slots[].density` [0,1] | engine-units/identity: coefficient счётчика и cadence, не particles/tick; projectile auto period `clamp(14−round(8×density),4,18)`, impact count `clamp(2+round(8×density),2,10)`, item dust count `clamp(1+round(7×density),1,8)` до client budgets (`InfiniVfxRuntime.cs:197-200,236-239`; `InfiniItemVfxRuntime.cs:108`). |
| `slots[].duration` integer [3,120] | keep/identity: lifetime **только impactSprite** в world ticks, detached linear fade/remove; у прочих renderer этот slot field не применяется (`InfiniVfxRuntime.cs:219-233`; `InfiniDetachedVfxSystem.cs:161-174,199-203`). |
| `slots[].alpha` [0,1] | engine-units/identity: sprite/primitive opacity, impact fade, sound volume с clamp [.05,1]; dust paths не используют slot alpha (`InfiniVfxRuntime.cs:115,203-250`; `InfiniItemVfxRuntime.cs:98-114`). |
| `slots[].spread` [0,2] | engine-units/identity: коэффициент скорости частиц, **не angular spread**; projectile dust `clamp(.35+1.7×spread,.2,4)`, item circular radii `1+spread` (`InfiniVfxRuntime.cs:246-249`; `InfiniItemVfxRuntime.cs:111`). |
| `slots[].jitter` [0,1.5], `fadeIn/fadeOut` [0,.8] | engine-units/identity, **не реализовано в renderer**; DTO хранит/clamp, не px/rad/ticks/seconds/lifetime fraction; impactSprite использует собственный fade (`VfxManifestSpec.cs:194-204,243-247`; `InfiniDetachedVfxSystem.cs:161-173`). |
| `slots[].budgetWeight` [.1,4], `signatureWeight` [0,1], `visualCost` [0,1] | engine-units/identity, **не реализовано в renderer**; сохранённые metadata, не бюджет/реальные draw calls; бюджет вычисляется из числа слотов и применяется отдельно (`vfx_manifest.py:785-793`; `InfiniVfxRuntime.cs:275-284`). |
| `slots[].startTick` integer [0,120] | keep/identity: start gate только для projectile periodic на per-projectile tick (`GameUpdateCount`), 0 без задержки; item periodic и event path игнорируют (`InfiniVfxRuntime.cs:79-87,197-200`; `InfiniItemVfxRuntime.cs:90-115`). |
| `slots[].repeatEvery` integer [0,120] | keep/identity: periodic cadence, **0=automatic** (projectile density-derived, item=10 global updates), не интервал нулевой длины; event path обходит этот gate (`InfiniVfxRuntime.cs:63-75,170-200`; `InfiniItemVfxRuntime.cs:96-97`). |

VFX Repair `schema`, `slotsUpsert` (полная ordinary slot schema), `slotIdsDelete`, `slotIndicesDelete` (нулевые индексы прежнего списка [0,2×maxSlots]), `motif` (целая структура либо null), `effectMagnitude`, `visualBudgetClass`, `note` — сверять **точные имена/nullable форму** с `_vfx_repair_schema` и `_vfx_repair_schema_from_packet` при использовании; возможности правки ограничены fieldPermissions/frozen-first, runtimeSurfaceReadOnly не authored. `phaseOffset`, baked-command `rotation/lifespan/scaleX`, generated `slotSeed/seed/spawnRateMultiplier=1` и budget caps — **не поля** ordinary или Repair model responses (`vfx_manifest.py:145-219,419-435,766-793`; `VfxManifestSpec.cs:205,278-306`). Текущие `_VFX_NUMERIC_DESCRIPTIONS` (`vfx_manifest.py:64-82,213-219`) показываются и в ordinary, и в reused Repair slot/motif schema; это честная документация ранее unit-less полей, **не runtime fix** и не свидетельство, что инертные поля уже заработали.

## Статус проверки

Сверены актуальные реестр, схемы Visual/VFX и старый параметрический snapshot; таблица сгенерирована обходом **реальных** `CAPABILITY_REGISTRY` и однозначным старым `wireName`, а не ручным предположением о roster. Результат: 52 capabilities / 229 строк / 180 numeric; matched 229/229; old-only без пары 0; new-only без пары 0; 14 identity-rename + 3 regen conversions среди 17 сменённых имён; 0 удалённых executable capabilities. Это **инвентарная/исходниковая** проверка.

Отдельная проверка итогового изменения:

- Полный Python/toolbox suite: **868 passed** (21.90 s), после уточнения `safeTileOnly` и исправления opt-in dev-fixture. Найденные ревьюером старые Author ключи заменены без изменения значений; прежний тест импорта усилен Author validation → compile → wire validation и проверкой исходных скоростей/gravity/sentinel, RED → GREEN.
- C# headless harness: **65/65**, real installed tML references; не игровой цикл/MP.
- DLL-only сборка: **0 errors, 0 warnings**. SDK packaging явно отключён `TmlBuildPackageMod=false`; `.tmod` не упаковывался.
- Ruff, Pyright, generated docs/schema checks, capability/standardization/delivery parity, mutation gate и sandbox/hygiene: passed.
- Gitleaks по staged diff: no leaks.
- Новые тесты проверяют полный integer lattice регенерации, identity wire/receipts всех 14 переименований, отказ старых Author ключей, неизменность исторических seed-wire hashes и реальные ordinary/Repair пакеты Visual/VFX. Исторический captured Live20 response-файл побайтно не изменён; адаптация имён только в test-local replay.

Не проводились новые LLM-вызовы, игровой/двухклиентный smoke и exhaustive binary32 parity произвольных коэффициентов. Эти границы не заменяются зелёными офлайн-тестами.
