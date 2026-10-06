# Terraria/tModLoader standardization — точная граница 0.4.248

[Generated vocabulary/lowerings](../lowery.md) · [Primitive parity/units](PRIMITIVE_PARITY_RU.md) · [External references](LOW_LEVEL_RUNTIME_EXTERNAL_REFERENCES_RU.md) · [Add capability](ADDING_RUNTIME_CAPABILITY_FOR_AGENTS_RU.md)

<a id="boundary"></a>
## Принцип и canonical owners

Используются точные stable tModLoader 1.4.4 понятия: DamageClass/ItemUseStyleID/AmmoID, Item/Projectile fields, NewProjectileDirect и обычные hooks. Mapping переводит **один authored token в одно engine value**, не выбирает movement/delivery/attachment/lifecycle/family. Точный установленный patch определяется build references, не названием stable.

Python vocabulary — `core/runtime_authoring/terraria_vocabulary.py`; mechanical facts — capability registry; C# mapping — `Common/Models/TerrariaRuntimeVocabulary.cs`; strict DTO — RuntimeProgramSpec/GeneratedItemData.Normalize; item projection — GeneratedItemData.Apply; projectile defaults/spawn — GeneratedProjectile. [Source map](../PROJECT_MAP_RU.md) и `tools/audit_terraria_standardization.py` связывают owners. Новое canonical spelling требует совместного Python/C#/registry/schema/wire/tests/generated-audit изменения, не второго mapping.

<a id="vocabulary"></a>
## Finite vocabulary и loaded IDs

- DamageClass: exact built-in token либо зарегистрированный `ModType.FullName=ModName/ClassName`, взятый именно из parent `damageClass`; `item.fullName`/`Terraria/<ItemName>` не класс урона. Unknown/unloaded reject, не Generic. `none/modded/rogue`, отдельный damageClassFullName и loose search не gameplay spellings; отсутствие damage — `damage=0`.
- UseStyle: точные ItemUseStyleID spellings; loose drink/eat, DrinkOld/None не exposed. Input `passive` не alias для equipped. Удалённые effect_catalog/effect_archetypes и whole-pattern aliases spear/beam/slash не восстанавливать.
- Rarity/buff/tile/wall IDs C# проверяет по текущим RarityLoader/BuffLoader/TileLoader/WallLoader counts, не произвольным clamps. Special negative rarity не заменяет expert/master/quest flags. Author получает exact parent IDs/names и не угадывает их.
- Parent packets содержат canonical useStyleName/ammoCategoryName/potion/notAmmo и damage-class content ID; это source facts, не semantic helper.

Author-visible gameplay aliases отсутствуют. Конечные technical/config/UI/VFX aliases перечислены в generated Lowery; internal migration normalization вне gameplay не означает разрешение legacy recipe importer.

<a id="ammo-healing"></a>
## Ammo и healing: независимые решения

`configure_vanilla_ammo_item`: Item.ammo через finite AmmoID, authored Item.shoot (stable ProjectileID 1..1021), отдельный `shootSpeedContributionPxPerUpdate`, Item.notAmmo и обязательный consumable=true. Это **ammo-item identity**, не weapon ammo consumption.

Item.useAmmo не выводится из ammo-item; PickAmmo меняет projectile type/speed/damage/knockback, поэтому weapon support требует полного отдельного slice. Sand не exposed: type-wide ItemID.Sets.SandgunAmmoProjectileData несовместим с независимой семантикой generated items, разделяющих proxy Item.type.

`restore_resources_on_use.usesPotionRules` напрямую задаёт Item.potion; healLife/healMana сами не включают potion sickness. Food/нестандартный heal не получает скрытые potion rules.

<a id="projectiles"></a>
## Projectile/lifecycle semantics

Primary/use ownership определяется [authored primary contract](LOW_LEVEL_RUNTIME_AUTHORING_RU.md#primary-use), не классом оружия. C# по exact primaryOwner ограничивает contact/noMelee/heldProj; secondary projectile не захватывает body ownership.

Proxy starts: ignoreWater=false, netImportant=false. Liquid/tile collision, penetrate, extraUpdates и immunity задаются явно. Owner и per-projectile local immunity поддерживаются; ID-static immunity скрыта, иначе делилась бы между всеми entities одного proxy type. NewProjectileDirect возвращает созданный instance для direct hydrate, не повторного поиска. Held proxy uses HeldProjDoesNotUsePlayerGfxOffY; owner aim sync bounded по изменению/интервалу, не arbitrary per-frame packet.

<a id="units"></a>
## Units и exact conversions

[Model-facing units](MODEL_FACING_UNITS_RU.md#gameplay) владеет current units/consumer traps; [conversion/null proof](MODEL_FACING_UNITS_RU.md#conversions) — percent/regen/zero/sentinel/float границей; [generated parity](PRIMITIVE_PARITY_RU.md) — full roster. Не копировать все ranges/cards сюда.

Terraria-specific display adapter: `axePowerTooltipPercent` — integer 0..500, шаг 5 → прежний integer `gameplay.axePower`/Item.axe 0..100 через /5. Старый DTO остаётся; Author `axePower` не alias. Generated buff `lifeRegenHpPerSecond` — 0..60, шаг .5 → прежний integer lifeRegen 0..120 через ×2; Author `lifeRegen` не alias. `valueCopper` остаётся exact Item.value в copper, не resale guarantee/Author value alias.

Проценты `15` и `0.15` — разные authored значения, не interchangeable spelling; движение/скорость — projectile updates, длительности — world ticks, raw local-immunity cooldown — engine units (`-1` one hit per NPC). Если биекция не доказана, units не переводятся в удобную prose единицу. Полное объяснение — canonical units owner выше.

`add_equipment_damage_bonus(phase,damageClass,bonusPercent)` — один explicit operation с пятью executable damage selectors; compiler пишет прежние scalar DTO без выбора класса/фазы. Generic-only crit/speed/knockback/penetration не произвольный DamageClass support. UpdateAccessory/UpdateEquip/UpdateArmorSet phase, neutral/ranges и additive units принадлежат registry/parity. GeneratedEquipmentBounds.g.cs сохраняет выборочные historical DTO clamps, включая generic/set damage; новые Author bounds всё равно обязательны. Authority/lifecycle — runtime ownership, не authored network switch.

Author-valid value не должно тихо меняться на C# boundary: несовпадение — contract defect и range-parity regression. Legacy safety envelope может быть шире Author, не уже; отсутствующая доказанная биекция не разрешает удобный approximate conversion. Event producer/timing units — [Author events](LOW_LEVEL_RUNTIME_AUTHORING_RU.md#validation-events).

<a id="custom"></a>
## Намеренно custom runtime

1. Proxy GeneratedItem/GeneratedProjectile types: tModLoader регистрирует types при load, а generated definitions появляются во время игры.
2. Dynamic movement/controller/event composition: статический ProjectileID/aiStyle не сохраняет authored topology.
3. Per-instance assets: generated item ID + entity ID, не type-wide texture/static sets.
4. Bounded event graph через обычные ModItem/ModProjectile hooks, не VM.
5. Hydration/network: authored entityId выбирает spec; Projectile.identity/whoAmI идентифицирует Terraria instance, не заменяет definition ID.

External stable/ExampleMod/Calamity links и patterns — [reference owner](LOW_LEVEL_RUNTIME_EXTERNAL_REFERENCES_RU.md); текущие behavior/trust и proof limits — [architecture](../PROJECT_ARCHITECTURE_RU.md#runtime-trust).
