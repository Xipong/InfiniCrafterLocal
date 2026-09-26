# Terraria/tModLoader standardization — InfiniCrafterLocal v0.4.241

## Цель

При возможности runtime использует точные понятия и значения stable tModLoader 1.4.4: `DamageClass`, `ItemUseStyleID`, `AmmoID`, обычные поля `Item`/`Projectile`, `Projectile.NewProjectileDirect`, стандартные immunity/collision semantics и ModProjectile hooks. Собственный bounded runtime сохраняется только там, где dynamic generated content нельзя выразить статической регистрацией `ModItem`/`ModProjectile` без потери функций.

Главное правило: стандартизация не имеет права превращаться в semantic router. Vanilla mapping переводит один authored token в одно точное tModLoader-значение; он не выбирает за Gameplay Author movement, delivery, attachment, lifecycle или weapon family.

Таблица конкретных `UpdateAccessory`/`UpdateEquip`/`UpdateArmorSet` additive процентов, percentage points, flat points, диапазонов, нейтральных значений и C# wire projection генерируется из одного registry в [`PRIMITIVE_PARITY_RU.md`](PRIMITIVE_PARITY_RU.md). Пять исполняемых классов `GetDamage` не являются пятью Author knobs: `add_equipment_damage_bonus` принимает explicit `damageClass`, `phase` и `bonusPercent`, а compiler one-to-one материализует сохранённые scalar DTO-поля. Generic-only crit/attack speed/knockback/armor penetration **не** подразумевают поддержку иных классов. Нормализация выборочных числовых DTO safety bounds генерируется в `GeneratedEquipmentBounds.g.cs` из registry, включая pre-IR clamps для сохранённых generic damage полей; lifecycle/authority выбирает runtime, не модель.

## Что приведено к tModLoader

### Канонический finite vocabulary

- `damageClass` имеет одну identity-форму: точный built-in token либо загруженный tModLoader `ModType.FullName` (`ModName/ClassName`). Псевдотокены `none`/`modded`, отдельное `damageClassFullName`, `rogue` и loose lookup удалены. Отсутствие урона выражается `damage=0`, а не выдуманным классом.
- `useStyle` соответствует конкретным `ItemUseStyleID`; свободные `drink`, `eat` и другие удобные spellings удалены.
- author input `passive` удалён как дубль; остаётся `equipped`.
- физически удалены мёртвые `effect_catalog.py`/`effect_archetypes.json` с whole-pattern aliases (`spear → spear_thrust`, `beam → laser_beam`, `slash → slash_holdout`), чтобы будущий агент не воскресил скрытый archetype router.
- loose lookup произвольного modded `DamageClass` удалён. Вместо него разрешён только точный registered `ModName/ClassName`; неизвестное/выгруженное содержимое отклоняется, а не превращается в `Generic`.

### Ammo semantics

`configure_vanilla_ammo_item` явно задаёт:

- `Item.ammo` через canonical `AmmoID` category;
- `Item.shoot` через authored vanilla `ProjectileID` в точном диапазоне stable `1..1021`;
- ammo-вклад `Item.shootSpeed` через отдельный `shootSpeedContributionPxPerUpdate`, не связанный со скоростью direct runtime entity;
- `Item.notAmmo` как отдельный authored флаг;
- обязательный `consumable=true`.

`Item.useAmmo` не выводится автоматически: это отдельная механика оружия и не должна возникать из факта, что предмет сам является боеприпасом. Один флаг здесь недостаточен: стандартный `PickAmmo` также меняет projectile type, скорость, урон и knockback, поэтому weapon-ammo support требует отдельного полного vertical slice. Каталог охватывает finite stable `AmmoID` категории, которые безопасно задаются per-item; Sand намеренно не exposed, потому что полная vanilla-семантика использует type-wide `ItemID.Sets.SandgunAmmoProjectileData`, а generated items разделяют один proxy `Item.type`.

### Healing/potion semantics

`healLife` и `healMana` больше не означают автоматически potion sickness. `restore_resources_on_use.usesPotionRules` напрямую задаёт `Item.potion`: healing food, аксессуарный эффект или другая нестандартная лечилка могут восстанавливать ресурсы без скрытого potion-флага.

### Projectile semantics

Primary executable ownership is authored explicitly per runtime row. For normal swords, pickaxes, axes and hammers the `item_body` is primary; a projectile on the same use is secondary unless the authored mechanic is explicitly projectile-owned (throw/flail/yoyo/whip/laser drill/held beam and similar). Final wire carries `primaryEntityId` and `primaryOwner`; C# gates `Item.noMelee`, contact hitbox and `Player.heldProj` writes from these fields. Entity/input/category names are never ownership classifiers.

- proxy projectile начинает с Terraria defaults: `ignoreWater=false`, `netImportant=false`;
- liquid collision, tile collision, penetrate, extra updates и NPC immunity задаются явно;
- поддерживаются owner immunity и per-projectile local immunity;
- ID-static immunity не exposed, потому что она разделялась бы всеми generated entities одного proxy type;
- spawn использует `Projectile.NewProjectileDirect`, чтобы не искать созданный instance повторно;
- held proxy type использует `ProjectileID.Sets.HeldProjDoesNotUsePlayerGfxOffY`;
- owner aim/vector sync отправляется только при значимом изменении и с bounded interval.

### Loaded content IDs

Rarity, buff, tile и wall IDs больше не clamp-ятся в произвольный диапазон. C# проверяет их против `RarityLoader.RarityCount`, `BuffLoader.BuffCount`, `TileLoader.TileCount` и `WallLoader.WallCount`. Author получает точные IDs/имена из parent facts и не должен угадывать. Special negative rarity flags не exposed как обычная rarity: expert/master/quest требуют отдельных Terraria flags, а не одного числа.

Parent packets дополнительно содержат canonical `useStyleName`, `ammoCategoryName`, `potion`, `notAmmo` и точный damage-class content ID, чтобы следующая LLM не переводила числовые Terraria поля по памяти.

### Неочевидные Terraria units

- `valueCopper` — точное поле `Item.value` в copper. Это base/shop value, а не гарантированная сумма обратной продажи игроком.
- Author `axePowerTooltipPercent` — точный tooltip percent (0..500, шаг 5); compiler делит на 5 до прежнего целого `gameplay.axePower`/`Item.axe` 0..100. Старый wire и C# не меняются; `axePower` как Author alias не принимается.
- Author generated buff `lifeRegenHpPerSecond` — 0..60 HP/s с шагом 0.5; compiler умножает на 2 до прежнего целого `gameplay.generatedBuff.lifeRegen` 0..120 (2 engine units = 1 HP/s до иных эффектов). Старый wire/C# не меняется; `lifeRegen` как имя Author-параметра этого capability не принимается.

### Range parity

Author ranges и C# clamps согласованы для spawn/collision/tool fields. Авторское допустимое значение не должно молча меняться на C#-границе. Расхождение является contract defect и проверяется `audit_terraria_standardization.py` вместе с общим capability audit.

## Где остаётся собственный движок

1. **Proxy types.** tModLoader регистрирует content types при загрузке, а UnlimitedCraft создаёт сущности во время игры. Поэтому используется общий `GeneratedItem`/`GeneratedProjectile` и локальный authored `entityId`.
2. **Dynamic component composition.** Movement/controller/event combinations собираются после загрузки. Их нельзя превратить в статические `ProjectileID`/`aiStyle` без потери authored topology.
3. **Per-instance assets.** Один proxy type не может иметь разные type-wide texture/static sets; visual assets адресуются generated item ID + entity ID.
4. **Bounded event graph.** Typed entity/event links остаются проектным runtime, но исполняются через обычные ModItem/ModProjectile hooks и Terraria fields.
5. **Dynamic hydration/network packet.** `entityId` выбирает authored spec; `Projectile.identity/whoAmI` по-прежнему идентифицируют конкретный Terraria instance.

## Canonical owners

- Python vocabulary: `LocalGenerator/infini_local/core/runtime_authoring/terraria_vocabulary.py`;
- gameplay registry: `LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py`;
- alias/lowering inventory: `lowery.md`;
- C# vocabulary: `ModSources/InfiniCrafterLocal/Common/Models/TerrariaRuntimeVocabulary.cs`;
- C# DTO validation: `Common/Models/RuntimeProgramSpec.cs` и `GeneratedItemData.Normalize.cs`;
- item projection: `GeneratedItemData.Apply.cs`;
- projectile defaults/spawn: `Content/Projectiles/GeneratedProjectile.cs`;
- machine gate: `tools/audit_terraria_standardization.py`.

Новая модель не должна создавать второй mapping рядом с этими owners. Изменение canonical token требует одновременно обновить Python/C# mapping, registry/schema, final wire, tests, `lowery.md` и standardization audit.

## Alias policy

Полный перечень сохранённых aliases находится в корневом `lowery.md`. Author-visible gameplay aliases отсутствуют. Сохраняются только конечные config/UI/VFX aliases, которые не выбирают механику. Любой новый alias должен быть либо внутренней migration-нормализацией вне gameplay, либо удалён в пользу одного canonical spelling.

## References

- stable release line: https://github.com/tModLoader/tModLoader/releases?q=stable
- `ItemUseStyleID`: https://docs.tmodloader.net/docs/stable/class_item_use_style_i_d.html
- `DamageClass`: https://docs.tmodloader.net/docs/stable/class_damage_class.html
- `Projectile`: https://docs.tmodloader.net/docs/stable/class_projectile.html
- official ExampleMod branch: https://github.com/tModLoader/tModLoader/tree/1.4.4/ExampleMod
