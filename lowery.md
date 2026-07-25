# lowery.md — canonical lowering и aliases

Версия проекта: **0.4.241**.

## Неподвижное правило

> Lowering разрешён только как семантически без потерь технический перевод. Он может скрывать неудобство API, но не сжимать пространство дизайна. По имени, категории, family, tooltip или prose нельзя выбирать movement, attachment, delivery, entity kind, input binding, lifecycle, targeting, hitbox topology или root executor.

Gameplay Author-visible semantic aliases: **нет**. У каждой механической операции и каждого enum-значения один канонический токен. Старые `passive`, `drink`, `eat`, plural ammo spellings и `rogue` не принимаются. Старый effect/weapon catalog с aliases `spear → spear_thrust`, `beam → laser_beam`, `slash → slash_holdout` физически удалён и не является reference. `throwing` сохранён только как точное каноническое отображение stable `DamageClass.Throwing`, а не как алиас. `damageClass` имеет одну identity-форму: built-in token либо точный tModLoader `ModName/ClassName`, скопированный из loaded parent facts; псевдотокены `none`/`modded` и параллельное `damageClassFullName` запрещены.

## Канонические технические отображения — это не semantic aliases

Эти таблицы являются one-to-one переводом JSON-токена в точное поле/константу stable tModLoader. Они не добавляют решений за Author.

### DamageClass

| runtime token | tModLoader |
|---|---|
| default | DamageClass.Default |
| generic | DamageClass.Generic |
| melee | DamageClass.Melee |
| melee_no_speed | DamageClass.MeleeNoSpeed |
| ranged | DamageClass.Ranged |
| magic | DamageClass.Magic |
| magic_summon_hybrid | DamageClass.MagicSummonHybrid |
| summon | DamageClass.Summon |
| summon_melee_speed | DamageClass.SummonMeleeSpeed |
| throwing | DamageClass.Throwing |

### ItemUseStyleID

| runtime token | tModLoader |
|---|---|
| swing | ItemUseStyleID.Swing |
| eat_food | ItemUseStyleID.EatFood |
| thrust | ItemUseStyleID.Thrust |
| hold_up | ItemUseStyleID.HoldUp |
| shoot | ItemUseStyleID.Shoot |
| drink_long | ItemUseStyleID.DrinkLong |
| drink_liquid | ItemUseStyleID.DrinkLiquid |
| golf_play | ItemUseStyleID.GolfPlay |
| hidden_animation | ItemUseStyleID.HiddenAnimation |
| mow_the_lawn | ItemUseStyleID.MowTheLawn |
| guitar | ItemUseStyleID.Guitar |
| rapier | ItemUseStyleID.Rapier |
| raise_lamp | ItemUseStyleID.RaiseLamp |

### Vanilla ammo item

| runtime token | tModLoader field |
|---|---|
| arrow | AmmoID.Arrow |
| bullet | AmmoID.Bullet |
| candy_corn | AmmoID.CandyCorn |
| coin | AmmoID.Coin |
| dart | AmmoID.Dart |
| fallen_star | AmmoID.FallenStar |
| flare | AmmoID.Flare |
| gel | AmmoID.Gel |
| jack_o_lantern | AmmoID.JackOLantern |
| nail_friendly | AmmoID.NailFriendly |
| rocket | AmmoID.Rocket |
| snowball | AmmoID.Snowball |
| solution | AmmoID.Solution |
| stake | AmmoID.Stake |
| stynger_bolt | AmmoID.StyngerBolt |

`configure_vanilla_ammo_item` отдельно принимает `projectileId` и `shootSpeedPxPerTick`, напрямую записывая `Item.shoot` и ammo-вклад `Item.shootSpeed`. Категория не выбирает projectile автоматически. `Item.ammo` означает «этот предмет является боеприпасом»; `Item.useAmmo` означал бы «это оружие расходует боеприпас» и данным adapter-ом не выставляется. Нельзя добавить `useAmmo` одним полем: стандартный `PickAmmo` также меняет projectile type, скорость, урон и knockback, поэтому нужен отдельный полный vertical slice.

### Loaded content IDs

`rarity`, `buffId`, `tileId` и `wallId` не имеют aliases и не угадываются по имени. Сейчас это точные IDs текущего loaded content set, прошедшие `RarityLoader`/`BuffLoader`/`TileLoader`/`WallLoader`; их можно только копировать из parent facts. Modded `DamageClass` является исключением: он хранится устойчивой exact content identity `ModName/ClassName` и разрешается через `ModContent.TryFind`.

### Поля с неочевидными Terraria units

- `valueCopper` напрямую пишет `Item.value`; это base/shop value в copper, а не обещание конкретной суммы resale игроком.
- `axePower` напрямую пишет внутренний `Item.axe`; Terraria показывает в tooltip `Item.axe × 5`. Допустимый Author range 0..100 совпадает с C# boundary.

### Runtime opcodes

Movement:

| capability | opcode |
|---|---|
| move_straight | 0 |
| move_slow_homing | 1 |
| move_gravity_arc | 2 |
| move_drift | 3 |
| move_orbit | 4 |
| move_boomerang | 5 |
| move_bounce | 6 |
| move_sine_homing | 7 |
| move_phase | 8 |
| move_accelerate | 9 |
| move_spiral | 10 |
| move_vortex_orb | 11 |
| move_blackhole_pull | 12 |
| move_proximity_missile | 13 |
| move_returning_glaive | 14 |
| move_expanding_wave | 15 |
| move_flail_tether | 16 |
| move_yoyo_hover | 17 |
| move_whip_lash | 18 |
| move_forward_then_retract | 19 |

Controllers:

| capability | opcode |
|---|---|
| none | 0 |
| channel_beam | 1 |
| charge_then_release | 2 |
| target_and_fire | 3 |

Event actions:

| capability | opcode |
|---|---|
| spawn_entity_on_event | 1 |
| apply_status_on_event | 2 |
| damage_area_on_event | 3 |
| chain_damage_on_event | 4 |
| pull_on_event | 5 |
| heal_owner_on_event | 6 |
| move_owner_on_event | 7 |

### Entity kind → visual role

| entity kind | visual role |
|---|---|
| item_body | inventory_item |
| owner_attached_projectile | held_body |
| free_projectile | projectile |
| stationary_projectile | deployed_entity |
| temporary_helper | helper |
| field | field |
| child_projectile | child_projectile |

Visual role — renderer handoff, а не gameplay-классификатор.

## Удалённые gameplay aliases и archetype routers

Физически удалены `effect_catalog.py` и `effect_archetypes.json`, включая `basic/projectile/bolt → thrown_simple`, `spear/lance/pike → spear_thrust`, `slash/held/swing → slash_holdout`, `beam/laser/ray → laser_beam` и другие whole-pattern aliases. Они не являются compatibility API и не должны восстанавливаться.

## Сохранившиеся aliases вне gameplay

Эти aliases не попадают в runtimeProgram и не могут выбирать механику предмета.

### LLM provider config

| accepted config spelling | canonical provider |
|---|---|
| openrouter, or | openrouter |
| openai, openai_compat, api, remote | openai_compat |
| local, lmstudio, lm_studio, ollama, empty | local |

### Image backend config

| accepted config spelling | canonical image backend |
|---|---|
| stablediffusioncpp, stable-diffusion.cpp, stable_diffusion_cpp | sdcpp |
| api_image, openai_image, openai_images, openai_compat_image | image_api |
| none, disabled | off |

Это только config migration для выбора уже существующего image backend; visual topology и gameplay от spelling не зависят.

### Result identity/UI category normalization

| incoming UI/category spelling | canonical UI category |
|---|---|
| placeable | furniture |
| station, crafting_station | placeable_station |
| device | technology |
| trinket, acc | accessory |
| consumable_item, stack_consumable, thrown_stack | consumable |

Эта нормализация используется только для identity/UI/parent summary. Она не выбирает runtime capability, movement или delivery.

### VFX fallback palette

| visual motif spellings | fallback color family |
|---|---|
| fire, heat | fire/orange |
| ice, water | ice/cyan |
| poison, nature | poison/green |
| shadow, void | shadow/purple |
| electric, lightning | electric/yellow |
| blood | blood/crimson |

Это только цветовой fallback VFX; gameplay и damage type от motif не зависят.

## Где намеренно остаётся наш runtime

1. **`GeneratedItem` и `GeneratedProjectile` — proxy-типы.** tModLoader регистрирует `ModItem`/`ModProjectile` и глобальные type IDs во время загрузки мода, а предметы UnlimitedCraft создаются уже во время игры. Поэтому каждый authored entity получает локальный `entityId`, а не новый глобальный `ProjectileID`.
2. **Per-entity capabilities и opcodes.** Movement/controller/event composition динамична и хранится в typed runtimeProgram. Она не переводится в `aiStyle` или weapon family, если это потеряло бы authored комбинацию.
3. **Per-instance visuals/assets.** Один proxy type не может иметь разные type-wide texture/static sets; PNG/VFX выбираются по generated item ID + entity ID.
4. **Type-wide Terraria sets не подделываются.** `ItemID.Sets`, `ProjectileID.Sets` и ID-static NPC immunity общие для proxy type. Их нельзя безопасно менять на один generated item/entity. Поэтому sand ammo не выставляется: полная sandgun-семантика требует type-wide `ItemID.Sets.SandgunAmmoProjectileData`.
5. **Local NPC immunity.** Поддерживаются явные режимы `owner` и `local`. ID-static immunity не exposed, потому что все generated projectiles имеют один global type и разделили бы cooldown между несвязанными предметами.
6. **Custom hydration/network identity.** `entityId` и generated item ID синхронизируют параметры proxy projectile. `Projectile.identity/whoAmI` остаются Terraria-идентификаторами конкретного экземпляра, но не заменяют authored subtype ID.
7. **Сложные held/beam/field controllers.** Используются обычные ModProjectile hooks и Terraria collision/network fields, но orchestration остаётся bounded custom runtime, потому что она составляется LLM после загрузки контента.

## Запрет на добавление alias

Новый gameplay alias допустим только если два входа обозначают одно и то же точное действие и один из них не показывается Author. Любое новое имя должно быть либо единственным canonical token, либо внутренней migration/config нормализацией вне gameplay. Добавление alias в Author schema требует обновить этот файл и пройти `tools/audit_terraria_standardization.py`.
