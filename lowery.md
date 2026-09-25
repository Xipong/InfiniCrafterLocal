# Low-level authoring и Lowery — канонический контракт

> Этот файл генерируется `python tools/generate_lowery.py`. Не редактировать вручную. Source of truth — перечисленные ниже Python owners; inventory/audit docs являются projections.

Schemas: `infini.runtime-program.v5` / `infini.runtime-program.authoring.v4` / `infini.runtime-program.wire.v3`.

## READ THIS FIRST — замороженная граница

1. Gameplay Author сам выбирает механику, entities, bindings, calls, params, events, references, metadata и финальный realization/selfEvaluation. Ни имя, tooltip, category, family, parent tag или capability prose не разрешают коду дописать дизайн.
2. Deterministic Python имеет право только проверить exact authored graph, ограничить его, отфильтровать exact Repair scope и выполнить lossless technical lowering.
3. Lowery не является вторым Author. Он не выбирает movement, attachment, delivery, lifecycle, input, target, entity kind, event, damage, visual topology или fallback mechanic.
4. Authoring compression допустима только для буквально одинакового low-level значения, повторённого минимум **5** раз. Она обязана сохранять literal equality и не может добавлять design choice.
5. Обязательная wire projection из уже authored identity (например, exact entity kind → renderer role или exact primary id/target equality → binding role) не считается authoring compression: она сериализует одно решение, а не заменяет несколько решений модели.
6. Repair получает конечные registry-derived alternatives и exact permissions. Модель выбирает и явно пишет полный вариант; код ничего не вставляет и после merge повторно запускает canonical validator.

## Единственные owners

| что меняется | единственный owner | derived consumers |
|---|---|---|
| Author JSON shape, primaryEntity fields, repair patch shape | runtime_authoring/program_schema.py | prompt schema, validator, Repair filter |
| capabilities, entity/input/action/event facts and event producers | runtime_authoring/capability_registry.py | Author catalog, validator, Repair alternatives, docs |
| lossless projections, exact outputs, receipts, repetition policy | runtime_authoring/technical_lowering.py | compiler, audits, this document |
| Author/Repair model-facing prose | pipelines/author_item_contract.py | Author and Repair system prompts |
| validation truth | runtime_authoring/validator.py | Repair requirements and final acceptance |
| Repair permissions/filter | runtime_authoring/repair_scope.py | conditional Repair dossier and merge report |
| wire materialization | runtime_authoring/compiler.py | RuntimeProgram wire + finalWireReceipts |
| runtime execution | ModSources/.../RuntimeProgramSpec.cs + executors | tModLoader behavior |

Правило меняется у owner-а. Нельзя создавать facade, shadow constant, prose-router или второй event/primary contract рядом. Generated projections обновляются командами в разделе «Проверка».

## Authoring → wire boundary

- `runtimeProgram.primaryEntityId` — ровно один model-authored существующий entity id.
- Author bindings/calls не содержат `role`. Compiler сравнивает exact `binding.target` с exact `primaryEntityId`: equality → wire `primary`, иначе wire `secondary`.
- `primaryOwner` выводится только из exact kind выбранной entity через `ENTITY_KIND_REGISTRY.projectile`; неизвестный kind fail-closed валидатором, а не становится projectile default.
- Каждая такая projection имеет manifest row и compiler receipt с authored paths, exact final path и value.
- Repair может менять primary identity только через `primaryEntitySelection` и только выбирая один id из transaction candidates.

### Event producer contract

`EventKindSpec` владеет producer calls, producer binding inputs и exact producer params; `EntityKindSpec.base_events` владеет producer-free availability для конкретного kind. Validator и Repair вызывают одну generic registry projection. Event-name `if/elif` вне registry запрещён.

| event | producer calls | producer binding inputs | producer-free kinds | exact params |
|---|---|---|---|---|
| on_use | — | primary_use, alternate_use | — | — |
| on_spawn | — | — | owner_attached_projectile, free_projectile, stationary_projectile, temporary_helper, field, child_projectile | — |
| on_hit | set_projectile_damage | primary_use, alternate_use | — | — |
| on_crit | set_projectile_damage | primary_use, alternate_use | — | — |
| on_tile_collision | set_projectile_collision | — | — | set_projectile_collision(tileCollide=True) |
| on_expire | set_projectile_lifetime | — | owner_attached_projectile, free_projectile, stationary_projectile, temporary_helper, field, child_projectile | — |
| on_kill | — | — | owner_attached_projectile, free_projectile, stationary_projectile, temporary_helper, field, child_projectile | — |
| periodic | — | — | item_body, owner_attached_projectile, free_projectile, stationary_projectile, temporary_helper, field, child_projectile | — |
| on_release | charge_then_release | — | — | — |
| channel_complete | charge_then_release | — | — | — |

## Lossless lowering manifest

Exact-repetition policy: `{'kind': 'exact_repetition', 'minimumRepeatedPlacements': 5, 'requiresLiteralEquality': True, 'mayAddDesignChoice': False}`.

| lowerer | authored inputs | wire outputs | adds design |
|---|---|---|---|
| entity_kind_to_visual_role | runtimeProgram.entities[].kind | runtimeProgram.entities[].visualRole, runtimeProgram.entities[].visual.role | false |
| primary_entity_to_binding_role | runtimeProgram.primaryEntityId, runtimeProgram.bindings[].usePolicy.action.targetId | runtimeProgram.bindings[].role | false |
| primary_entity_kind_to_owner | runtimeProgram.primaryEntityId, runtimeProgram.entities[].id, runtimeProgram.entities[].kind | runtimeProgram.primaryOwner | false |
| capability_name_to_opcode | runtimeProgram.calls[].fn | runtimeProgram.entities[].movement.code, runtimeProgram.entities[].controller.code, runtimeProgram.entities[].events[].actionCode | false |
| item_fields_to_tml_projection | item_body capability params | gameplay.damageClass, gameplay.damage, gameplay.knockback, gameplay.useTime, gameplay.useAnimation, gameplay.manaCost, gameplay.rarity, gameplay.value, gameplay.maxStack, gameplay.craftYield, gameplay.width, gameplay.height, gameplay.itemScale, gameplay.useStyleName, gameplay.autoReuse, gameplay.useTurn, gameplay.holdoutOffsetX, gameplay.holdoutOffsetY, gameplay.handPose, gameplay.releaseTiming, runtimeProgram.itemUse.configured, runtimeProgram.itemUse.useStyle, runtimeProgram.itemUse.hideUseGraphic, runtimeProgram.itemUse.disableMeleeHitbox, runtimeProgram.itemUse.channel, runtimeProgram.itemUse.handPose, runtimeProgram.itemUse.releaseTiming, runtimeProgram.itemUse.holdoutOffsetX, runtimeProgram.itemUse.holdoutOffsetY, runtimeProgram.itemContact.hitboxScale, runtimeProgram.itemContact.contactForgivenessPx, gameplay.ammoCategory, gameplay.ammoProjectileId, gameplay.ammoShootSpeedPxPerTick, gameplay.notAmmo, gameplay.healLife, gameplay.healMana, gameplay.potion, gameplay.extraBuffs[].buffCode, gameplay.extraBuffs[].buffTime, gameplay.generatedBuff.durationTicks, gameplay.generatedBuff.miningSpeedMultiplier, gameplay.generatedBuff.emitLightStrength, gameplay.generatedBuff.lightColorName, gameplay.generatedBuff.oreSenseRadiusTiles, gameplay.generatedBuff.movementSpeed, gameplay.generatedBuff.jumpBoost, gameplay.generatedBuff.manaRegen, gameplay.generatedBuff.lifeRegen, gameplay.pickPower, gameplay.axePower, gameplay.hammerPower, gameplay.miningSpeedScale, gameplay.useConditionMode, gameplay.useConditionMinLife, gameplay.useConditionMinMana, gameplay.holdLightStrength, gameplay.holdLightColorName, gameplay.mobilityMode, gameplay.mobilityRangeTiles, gameplay.mobilityCooldownTicks, gameplay.mobilitySafeTileOnly, accessory.enabled, accessory.defense, accessory.maxLife, accessory.maxMana, accessory.lifeRegen, accessory.manaRegen, accessory.movementSpeed, accessory.maxRunSpeed, accessory.jumpSpeed, accessory.genericCrit, accessory.attackSpeed, accessory.knockback, accessory.minionSlots, accessory.sentrySlots, accessory.manaCostReduction, accessory.ammoSaveChance, accessory.aggro, accessory.endurance, accessory.armorPenetration, accessory.whipRange, accessory.summonTagDamage, accessory.lightStrength, accessory.lightColorName, accessory.fallDamageImmune, accessory.lavaImmune, accessory.waterWalk, armor.enabled, armor.slot, armor.setKey, armor.defense, armor.maxLife, armor.maxMana, armor.lifeRegen, armor.manaRegen, armor.movementSpeed, armor.maxRunSpeed, armor.jumpSpeed, armor.genericCrit, armor.attackSpeed, armor.knockback, armor.minionSlots, armor.sentrySlots, armor.manaCostReduction, armor.ammoSaveChance, armor.aggro, armor.endurance, armor.armorPenetration, armor.whipRange, armor.summonTagDamage, armor.lightStrength, armor.lightColorName, armor.fallDamageImmune, armor.lavaImmune, armor.waterWalk, armor.setBonusGenericCrit, armor.setBonusMovementSpeed, armor.setBonusLifeRegen, armor.setBonusManaRegen, armor.setBonusMinionSlots, armor.setBonusSentrySlots, armor.setBonusManaCostReduction, armor.setBonusAmmoSaveChance, armor.setBonusAggro, armor.setBonusEndurance, armor.setBonusArmorPenetration, accessory.genericDamage, accessory.meleeDamage, accessory.rangedDamage, accessory.magicDamage, accessory.summonDamage, armor.genericDamage, armor.meleeDamage, armor.rangedDamage, armor.magicDamage, armor.summonDamage, armor.setBonusGenericDamage, armor.setBonusMeleeDamage, armor.setBonusRangedDamage, armor.setBonusMagicDamage, armor.setBonusSummonDamage | false |

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

### Primary entity → binding role

`runtimeProgram.primaryEntityId` выбирается Author как точный существующий `entityId`. Lowery сравнивает его только с точным `binding.target`: равный target materializes wire `role=primary`, остальные — `role=secondary`. Это one-to-one техническая проекция authored identity; она не выбирает entity, input, action, attachment, delivery или gameplay importance.

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

## Проверка

```bash
python tools/generate_lowery.py --check
python tools/generate_low_level_runtime_docs.py --check
python tools/run_pyright.py --pythonpath /path/to/venv/bin/python
python -m pytest -q LocalGenerator/tests/test_runtime_authoring_change_locality.py LocalGenerator/tests/test_low_level_runtime_contract_v5.py LocalGenerator/tests/test_low_level_three_stage_pipeline.py
```

Change-locality acceptance: изменить один canonical owner, обновить generated projections, пройти affected replay; не редактировать параллельные prose contracts и не запускать Live как замену локальному доказательству.

## Запрет на добавление alias

Новый gameplay alias допустим только если два входа обозначают одно и то же точное действие и один из них не показывается Author. Любое новое имя должно быть либо единственным canonical token, либо внутренней migration/config нормализацией вне gameplay. Добавление alias в Author schema требует изменить canonical vocabulary owner, перегенерировать этот файл и пройти `tools/audit_terraria_standardization.py`.
