# Native equipment: самостоятельные возможности аксессуаров

`configure_accessory` расширен независимыми bounded листьями; provider shape/cards,
validator, compiler и receipts выводятся из registry. Нет preset для исходного предмета
и нет routing по имени/категории. `equip_passive` / `equipped` остаётся явным binding.

| Author | Wire / native consumer | Граница |
|---|---|---|
| `wireVision` | accessory.wireVision → Player.InfoAccMechShowWires | Native builder toggles управляют цветами проводов/actuators и hide-all; secret-world pre-Skeletron gate сохранён. Не ruler и не размещение. Работает только equipped, а не inventory как vanilla Mechanical Lens. |
| `iceSkate` | accessory.iceSkate → Player.iceSkate | Native ice acceleration/sliding и запрет CheckIceBreak. Не общий speed bonus. |
| `noKnockback` | accessory.noKnockback → Player.noKnockback | Native HurtModifiers.ToHurtInfo(..., noKnockback); не защита от урона и не knockback врагов. Native special-hit modifiers могут уменьшить KnockbackImmunityEffectiveness; это не абсолютный override всех типов удара. |
| `fireWalk` | accessory.fireWalk → Player.fireWalk | Collision.CanTileHurt исключает только TileID.Sets.TouchDamageHot. Не lavaImmune, не fire-debuff immunity, не spikes/suffocation. |
| `rocketBoots` | accessory.rocketBoots → Player.rocketBoots, integer 0..5 | 0 не выдаёт flight; 1 имеет rocketDelay2=30, 2..5=15. Max с native mode после всех equipped accessories в existing `InfiniCraftPlayer.PostUpdateEquips`. Не выбирает vanityRocketBoots. |
| `accRunSpeedPxPerTick` | accessory.accRunSpeed → max(Player.accRunSpeed, value), 0..20 px/world tick | Sprint-speed floor в `PostUpdateEquips` после всех native accessory assignments, до movement consumers. Native terrain/mount/wing/chilled rules после него сохранены. Не дубликат maxRunSpeed bonus или moveSpeed percent. |

Пропуск не материализует новые поля в Python wire; C# DTO читает старое отсутствие как 0/false и при повторной сериализации пишет свои нейтральные поля. 0/false не отменяют effects других
предметов. Присутствующее невалидное значение — RED, не clamp/default. Float speed
проверяется по raw JSON decimal token до float32 narrowing; обычное допустимое
округление остаётся, nonzero→zero collapse запрещён. Никакой новой armor/set/inventory
версии этих primitives здесь нет.

## Жизненный цикл rocket boots

Vanilla ResetEffects сбрасывает rocketBoots/vanityRocketBoots, но не spent rocketTime.
UpdateAccessory накапливает mode/floor через existing per-player equipment lifecycle; ResetEffects очищает grants каждый tick, PostUpdateEquips применяет max с native fields независимо от slot order. Не пишет rocketTime, rocketTimeMax, rocketDelay,
canRocket или rocketRelease. Native Player.Update владеет release/extra-jump/wing gates,
charge decrement и thrust. Базовый rocketTimeMax=7 — charges, **не семь world ticks**:
каждый расход запускает rocketDelay=10; rocketDelay2 задаёт частоту presentation.
Landing/sliding и RefreshMovementAbilities обновляют budget. Wings могут перевести
remaining charges в wingTime; mounts подавляют rocket flags. Произвольные flight
seconds, wings, infinite midair refill и отдельный rocket presentation здесь не exposed.

## Уже существующие поля и source facts

Installed tML ItemID: MechanicalLens=3619, FrostsparkBoots=1862, ObsidianShield=397.
В native equip code Frostspark boots задают accRunSpeed=6.75, rocketBoots=3,
moveSpeed+=0.08, iceSkate=true. Obsidian shield задаёт noKnockback/fireWalk; Item.defense
остаётся существующим `defensePoints`. Это read-only source trace, **не recipe/default**.
Существующие `moveSpeedBonusPercent`, `maxRunSpeedBonusPxPerTick`, `fallDamageImmune`,
`lavaImmune`, `waterWalk` сохранены без дублей. Их выбор остаётся у Author;
сами эти исходные предметы не получают все перечисленные effects.

## Проверено и не проверено

### Identity generated-аксессуаров

`GeneratedAccessoryIdentitySystem` исправляет техническую границу общего proxy
`Item.type`/`netID`: два разрешённых generated-аксессуара сравниваются по точному
`GeneratedItemData.Id` (ordinal), независимо от prefix. Разные ID можно надеть
вместе; повтор одного ID остаётся duplicate. Имя, recipe metadata и параметры
эффектов не создают новую identity. Непустой разрешённый accessory definition нужен
с обеих сторон; пустые предметы, пустой ID, reference-only hydration, обычные
предметы и чужие ModItem сохраняют исходный native comparator.

Это узкий **Fix** с audit reason `fix:generated_accessory_definition_identity`:
при установке он записывается в mod log. Изменяются только четыре callsite
`Item.IsTheSameAs` в `ItemSlot.AccCheck_ForPlayer` и `ItemSlot.AccessorySwap`.
Первый владеет ручной установкой в обычные/vanity/modded slots, второй — выбором
слота при right-click/quick equip. Глобальная identity, stacking, type registry,
save/network format и authored gameplay не меняются. Native wing exclusions,
`CanAccessoryBeEquippedWith`, `CanEquipAccessory`, slot acceptance и unlock rules
остаются на исходном пути. В каждом методе оба callsite проверяются до изменения; несовместимая
форма IL даёт явную ошибку и снимает уже установленный соседний hook. Unload
восстанавливает оба метода.

`EngineRuntimeChecks.AccessoryIdentity.cs` исполняет реальные native entrypoints:
разные/одинаковые ID и prefixes; normal/vanity/modded collections; замена занятого
слота при duplicate в другом; vanilla/foreign controls, pair/equip/slot vetoes,
wings, Demon Heart unlock; quick equip/replacement и reload/unload/failure rollback.
Это CPU/headless проверка на официальном tML `2026.08.3.0`, source commit
[`c9545cf`](https://github.com/tModLoader/tModLoader/blob/c9545cf27d56c456321e1896274c02adf67d0140/patches/tModLoader/Terraria/UI/ItemSlot.TML.cs).
Реальный UI/game loop и multiplayer match этим не подтверждены.

### Equipment effects

Headless checks используют real installed tModLoader/FNA DLL и canonical mod sources:
FromJson → ApplyToItem → network DTO roundtrip → real ApplyEquipFunctional/ItemLoader.UpdateAccessory → PlayerLoader.PostUpdateEquips → native ResetEffects dispatch,
реальные WiresUI.Settings.DrawWires (eligibility, не GPU), HorizontalMovement, RefreshMovementAbilities, HurtModifiers.ToHurtInfo и Collision.CanTileHurt.
Slot-order regression использует exact reviewer pairs (generated mode 5 + native Rocket Boots/Frostspark; generated sprint 20 + Frostspark) в обоих порядках, native CanAccessoryBeEquippedWith, once/reset controls и pure/mixed fields. Это headless native-hook proof, не полный Player.Update.
Python проверяет оба сериализованных Author/Repair formats, nullable-provider roundtrip,
exact leaf-only Repair с hostile frozen siblings, receipts и strict delivery без receipts.

Native source trace дополнительно устанавливает DrawWires/builder toggles, ice update,
Hurt/knockback и весь rocket consumer cycle. Headless seams **не** доказывают полный
Player.Update/world collision loop, GPU wires/flames/shoe visuals, multiplayer match,
inventory/void-bag activation, полный slot UI/content registration или измеренную
продолжительность полёта. Game/network/model/install не запускались.

## Jumps: независимая авторская композиция

- `jumpCloud`: Дополнительный прыжок облака.
- `jumpBlizzard`: Дополнительный прыжок метели.
- `jumpSandstorm`: Дополнительный прыжок песчаной бури.
- `jumpFart`: Дополнительный прыжок газа.
- `jumpTsunami`: Дополнительный прыжок цунами.


Поля optional: отсутствие сохраняется через DTO/network, явный null запрещён. Каждый выбор получает собственный receipt; названия предметов не включают соседние эффекты. Исполнение — native Player/ExtraJump в UpdateAccessory, сброс — native ResetEffects. Нативные ограничения движения и строительные переключатели сохраняются.

## Aquatic: независимая авторская композиция

- `swimFlipper`: Плавательные прыжки в воде.
- `divingHelm`: Замедленный расход воздуха.
- `underwaterBreathing`: Жабры: дыхание в воде и на суше; getGoodWorld требует воду.
- `waterFloat`: Всплытие в воде, спуск кнопкой вниз.


Поля optional: отсутствие сохраняется через DTO/network, явный null запрещён. Каждый выбор получает собственный receipt; названия предметов не включают соседние эффекты. Исполнение — native Player/ExtraJump в UpdateAccessory, сброс — native ResetEffects. Нативные ограничения движения и строительные переключатели сохраняются.

## Climbing: независимая авторская композиция

- `autoJump`: Автопрыжок при удержании кнопки.
- `frogJump`: Высота прыжка и безопасное падение лягушки.
- `wallGrip`: Уровень сцепления со стеной, целое 0..2.

Поля optional: отсутствие сохраняется через DTO/network, явный null запрещён. Каждый выбор получает собственный receipt; названия предметов не включают соседние эффекты. Исполнение — native Player/ExtraJump в UpdateAccessory, сброс — native ResetEffects. Нативные ограничения движения и строительные переключатели сохраняются.

## Building: независимая авторская композиция

- `autoPaint`: Автопокраска расходует краску при строительстве.
- `rulerGrid`: Сетка линейки с переключателем строителя.
- `buildRangeTiles`: Дальность строительства в клетках, целое 0..20.
- `tileSpeedBonusPercent`: Бонус скорости установки блоков (%), целое 0..100.
- `wallSpeedBonusPercent`: Бонус скорости установки стен (%), целое 0..100.

Поля optional: отсутствие сохраняется через DTO/network, явный null запрещён. Каждый выбор получает собственный receipt; названия предметов не включают соседние эффекты. Исполнение — native Player/ExtraJump в UpdateAccessory, сброс — native ResetEffects. Нативные ограничения движения и строительные переключатели сохраняются.

## Gravity: независимая авторская композиция

- `gravityControl`: Управление гравитацией кнопкой вверх.
- `featherFall`: Плавное падение с управлением вверх/вниз.
- `extraFallTiles`: Дополнительная безопасная высота падения, целое 0..100.

Поля optional: отсутствие сохраняется через DTO/network, явный null запрещён. Каждый выбор получает собственный receipt; названия предметов не включают соседние эффекты. Исполнение — native Player/ExtraJump в UpdateAccessory, сброс — native ResetEffects. Нативные ограничения движения и строительные переключатели сохраняются.
