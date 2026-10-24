# Low-level authoring и Lowery — канонический контракт

> Generated: [`tools/generate/generate_lowery.py`](../../../tools/generate/generate_lowery.py). Не редактировать вручную; менять canonical owner и [обновлять projection](#refresh).
> Sources: [registry](../../../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py), [Author shape](../../../LocalGenerator/infini_local/core/runtime_authoring/program_schema.py), [lowering](../../../LocalGenerator/infini_local/core/runtime_authoring/technical_lowering.py), [tModLoader vocabulary](../../../LocalGenerator/infini_local/core/runtime_authoring/terraria_vocabulary.py), [Author/Repair prose](../../../LocalGenerator/infini_local/pipelines/author_item_contract.py), [unit guide](../../../LocalGenerator/infini_local/pipelines/llm_authoring_prompt.py).

Schemas: `infini.runtime-program.v5` / `infini.runtime-program.authoring.v6` / `infini.runtime-program.wire.v3`.

**Навигация:** [граница](#boundary) · [owners](#owners) · [Author → wire](#wire) · [manifest](#lowering) · [технические отображения](#mappings) · [текст и единицы игрока](#player-text) · [config/UI aliases](#config-aliases) · [proxy runtime](#runtime) · [обновление и проверка](#refresh).

<a id="boundary"></a>

## READ THIS FIRST — замороженная граница

1. Gameplay Author сам выбирает механику, entities, bindings, calls, params, events, references, metadata и optional advisory realization/selfEvaluation. Ни имя, tooltip, category, family, parent tag или capability prose не разрешают коду дописать дизайн.
2. Deterministic Python имеет право только проверить exact authored graph, ограничить его, отфильтровать exact Repair scope и выполнить lossless technical lowering.
3. Lowery не является вторым Author. Он не выбирает movement, attachment, delivery, lifecycle, input, target, entity kind, event, damage, visual topology, hitbox topology, root executor или fallback mechanic. Он может скрывать неудобство API, но не сжимать пространство дизайна.
4. Authoring compression допустима только для буквально одинакового low-level значения, повторённого минимум **5** раз. Она обязана сохранять literal equality и не может добавлять design choice.
5. Обязательная wire projection из уже authored identity (например, exact entity kind → renderer role или exact primary id/target equality → binding role) не считается authoring compression: она сериализует одно решение, а не заменяет несколько решений модели.
6. Repair получает конечные registry-derived alternatives и exact permissions. Модель выбирает и явно пишет полный вариант; patch не заполняет пропуски и после frozen-first merge повторно запускается canonical validator.
7. Только optional params с явно объявленным registry default=neutral допускают пропуск в полном Author как точный выбор этой нейтрали. При omission_condition должна выполняться точная объявленная неисполняемая ветвь; вне её поле обязательно. Compiler материализует нейтраль после validation с отдельным receipt declared_neutral_omission. Это явное изменение контракта, не fallback невалидного значения и не правило для всех нулей. Связанные эффекты/обязательные группы проверяются совместно; omission в Repair означает не менять. Если разрешённый Repair меняет ветвь на исполняемую, он должен явно добавить ставший обязательным leaf.

<a id="owners"></a>

## Единственные owners

| что меняется | единственный owner | derived consumers |
|---|---|---|
| Author JSON shape, primaryEntity fields, repair patch shape | runtime_authoring/program_schema.py | prompt schema, validator, Repair filter |
| capabilities, entity/input/action/event facts and event producers | runtime_authoring/capability_registry.py | Author catalog, validator, Repair alternatives, docs |
| lossless projections, exact outputs, receipts, repetition policy | runtime_authoring/technical_lowering.py | compiler, audits, this document |
| Author/Repair model-facing prose and unit explanation | pipelines/author_item_contract.py + pipelines/llm_authoring_prompt.py | serialized Author/Repair messages, this document |
| validation truth | runtime_authoring/validator.py | Repair requirements and final acceptance |
| Repair permissions/filter | runtime_authoring/repair_scope.py | conditional Repair dossier and merge report |
| wire materialization | runtime_authoring/compiler.py | RuntimeProgram wire + finalWireReceipts |
| runtime execution | ModSources/.../RuntimeProgramSpec.cs + executors | tModLoader behavior |

Правило меняется у owner-а. Нельзя создавать facade, shadow constant, prose-router или второй event/primary contract рядом. Generated projections обновляются командами в [«Обновление и проверка»](#refresh).

<a id="wire"></a>

## Authoring → wire boundary

- `runtimeProgram.primaryEntityId` — ровно один model-authored существующий entity id.
- Author bindings/calls не содержат `role`. Compiler сравнивает exact `binding.action.targetId` (либо exact unique item-body identity на registry-fixed ветви) с exact `primaryEntityId`: equality → wire `primary`, иначе wire `secondary`. Wire сохраняет `binding.usePolicy`; эта one-to-one projection не выбирает entity, input, action, attachment, delivery или gameplay importance.
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
| on_hurt | — | equipped | — | — |
| on_enemy_kill | — | equipped | — | — |

<a id="lowering"></a>

## Lossless lowering manifest

Exact-repetition policy: `{'kind': 'exact_repetition', 'minimumRepeatedPlacements': 5, 'requiresLiteralEquality': True, 'mayAddDesignChoice': False}`.

| lowerer | authored inputs | wire outputs | adds design |
|---|---|---|---|
| author_binding_lanes | runtimeProgram.bindings[].id, runtimeProgram.bindings[].input, runtimeProgram.bindings[].action.kind, runtimeProgram.bindings[].action.targetId, runtimeProgram.bindings[].stackCost, runtimeProgram.bindings[].contactDamage, runtimeProgram.bindings[].action.effectGroupId, runtimeProgram.entities[].id, runtimeProgram.entities[].kind, runtimeProgram.primaryEntityId | runtimeProgram.bindings[].id, runtimeProgram.bindings[].input, runtimeProgram.bindings[].usePolicy.action.kind, runtimeProgram.bindings[].usePolicy.action.targetId, runtimeProgram.bindings[].usePolicy.action.effectGroupId, runtimeProgram.bindings[].usePolicy.stackCost, runtimeProgram.bindings[].usePolicy.contactDamage, runtimeProgram.entities[].id, runtimeProgram.entities[].kind, runtimeProgram.primaryEntityId, runtimeProgram.itemEntityId | false |
| binding_stack_chance_identity | runtimeProgram.bindings[].id, runtimeProgram.bindings[].stackConsumeChancePercent | runtimeProgram.bindings[].usePolicy.stackConsumeChancePercent | false |
| binding_effect_group_identity | runtimeProgram.bindings[].id, runtimeProgram.bindings[].action.effectGroupId | runtimeProgram.bindings[].usePolicy.action.effectGroupId | false |
| entity_kind_to_visual_role | runtimeProgram.entities[].kind | runtimeProgram.entities[].visualRole, runtimeProgram.entities[].visual.role | false |
| primary_entity_to_binding_role | runtimeProgram.primaryEntityId, runtimeProgram.bindings[].action.targetId, runtimeProgram.bindings[].id, runtimeProgram.bindings[].input, runtimeProgram.bindings[].action.kind, runtimeProgram.entities[].id, runtimeProgram.entities[].kind | runtimeProgram.bindings[].role | false |
| primary_entity_kind_to_owner | runtimeProgram.primaryEntityId, runtimeProgram.entities[].id, runtimeProgram.entities[].kind | runtimeProgram.primaryOwner | false |
| capability_name_to_opcode | runtimeProgram.calls[].fn | runtimeProgram.entities[].movement.code, runtimeProgram.entities[].controller.code, runtimeProgram.entities[].events[].actionCode | false |
| item_fields_to_tml_projection | item_body capability params | gameplay.damageClass, gameplay.damage, gameplay.knockback, gameplay.useTime, gameplay.useAnimation, gameplay.manaCost, gameplay.manaCostInput, gameplay.rarity, gameplay.value, gameplay.maxStack, gameplay.craftYield, gameplay.width, gameplay.height, gameplay.itemScale, gameplay.useStyleName, gameplay.autoReuse, gameplay.useTurn, gameplay.holdoutOffsetX, gameplay.holdoutOffsetY, gameplay.handPose, gameplay.releaseTiming, runtimeProgram.itemUse.configured, runtimeProgram.itemUse.useStyle, runtimeProgram.itemUse.hideUseGraphic, runtimeProgram.itemUse.disableMeleeHitbox, runtimeProgram.itemUse.channel, runtimeProgram.itemUse.handPose, runtimeProgram.itemUse.releaseTiming, runtimeProgram.itemUse.holdoutOffsetX, runtimeProgram.itemUse.holdoutOffsetY, gameplay.collectSeedsFromGrass, runtimeProgram.itemContact.hitboxScale, runtimeProgram.itemContact.contactForgivenessPx, gameplay.ammoCategory, gameplay.ammoProjectileId, gameplay.ammoShootSpeedPxPerTick, gameplay.notAmmo, gameplay.healLife, gameplay.healMana, gameplay.potion, gameplay.extraBuffs[].buffCode, gameplay.extraBuffs[].buffTime, gameplay.generatedBuff.durationTicks, gameplay.generatedBuff.exhaustionTicks, gameplay.generatedBuff.miningSpeedMultiplier, gameplay.generatedBuff.emitLightStrength, gameplay.generatedBuff.lightColorName, gameplay.generatedBuff.oreSenseRadiusTiles, gameplay.generatedBuff.movementSpeed, gameplay.generatedBuff.jumpBoost, gameplay.generatedBuff.manaRegen, gameplay.generatedBuff.lifeRegen, gameplay.generatedBuff.combat.defensePoints, gameplay.generatedBuff.combat.attackSpeedPercent, gameplay.generatedBuff.combat.critChancePoints, gameplay.generatedBuff.combat.damagePercent, gameplay.generatedBuff.combat.damageClass, gameplay.pickPower, gameplay.axePower, gameplay.hammerPower, gameplay.miningSpeedScale, gameplay.useConditions[].input, gameplay.useConditions[].useConditionMode, gameplay.useConditions[].useConditionMinLife, gameplay.useConditions[].useConditionMinMana, gameplay.holdLightStrength, gameplay.holdLightColorName, gameplay.mobilityMode, gameplay.mobilityRangeTiles, gameplay.mobilityCooldownTicks, gameplay.mobilitySafeTileOnly, accessory.enabled, accessory.defense, accessory.maxLife, accessory.maxMana, accessory.lifeRegen, accessory.manaRegen, accessory.movementSpeed, accessory.maxRunSpeed, accessory.jumpSpeed, accessory.genericCrit, accessory.attackSpeed, accessory.knockback, accessory.minionSlots, accessory.sentrySlots, accessory.manaCostReduction, accessory.ammoSaveChance, accessory.aggro, accessory.endurance, accessory.armorPenetration, accessory.whipRange, accessory.summonTagDamage, accessory.lightStrength, accessory.lightColorName, accessory.fallDamageImmune, accessory.lavaImmune, accessory.waterWalk, accessory.iceSkate, accessory.noKnockback, accessory.fireWalk, accessory.accRunSpeed, accessory.rocketBoots, accessory.wireVision, armor.enabled, armor.slot, armor.setKey, armor.defense, armor.maxLife, armor.maxMana, armor.lifeRegen, armor.manaRegen, armor.movementSpeed, armor.maxRunSpeed, armor.jumpSpeed, armor.genericCrit, armor.attackSpeed, armor.knockback, armor.minionSlots, armor.sentrySlots, armor.manaCostReduction, armor.ammoSaveChance, armor.aggro, armor.endurance, armor.armorPenetration, armor.whipRange, armor.summonTagDamage, armor.lightStrength, armor.lightColorName, armor.fallDamageImmune, armor.lavaImmune, armor.waterWalk, armor.setBonusGenericCrit, armor.setBonusMovementSpeed, armor.setBonusLifeRegen, armor.setBonusManaRegen, armor.setBonusMinionSlots, armor.setBonusSentrySlots, armor.setBonusManaCostReduction, armor.setBonusAmmoSaveChance, armor.setBonusAggro, armor.setBonusEndurance, armor.setBonusArmorPenetration, accessory.genericDamage, accessory.meleeDamage, accessory.rangedDamage, accessory.magicDamage, accessory.summonDamage, armor.genericDamage, armor.meleeDamage, armor.rangedDamage, armor.magicDamage, armor.summonDamage, armor.setBonusGenericDamage, armor.setBonusMeleeDamage, armor.setBonusRangedDamage, armor.setBonusMagicDamage, armor.setBonusSummonDamage | false |

## Каноническая vocabulary

Gameplay Author-visible semantic aliases: **нет**. У каждой механической операции и каждого enum-значения один канонический токен. Старые `passive`, `drink`, `eat`, plural ammo spellings и `rogue` не принимаются. `throwing` сохранён только как точное каноническое отображение stable `DamageClass.Throwing`, а не как алиас. `damageClass` имеет одну identity-форму: built-in token либо точный tModLoader `ModName/ClassName`, скопированный из loaded parent facts; псевдотокены `none`/`modded` и параллельное `damageClassFullName` запрещены.

<a id="mappings"></a>

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

`configure_vanilla_ammo_item` отдельно принимает `projectileId` и `shootSpeedContributionBlocksPerSecond`, переводя базовый ammo-вклад в native `Item.shootSpeed`; `projectileId` задаёт `Item.shoot`. Категория не выбирает projectile автоматически. `Item.ammo` означает «этот предмет является боеприпасом». Отдельная capability `configure_weapon_ammo` задаёт `Item.useAmmo` для active spawn_entity shots: native selection/conservation и damage/knockback сохраняются, поведение projectile принадлежит authored entity. Author явно выбирает `speedBasis=authored_spawn|native_shot`. Другие use lanes и passive hold не расходуют ammo. Одновременная роль ammo stack и ammo consumer у одного generated item отклоняется.

### Loaded content IDs

`rarity`, `buffId`, `tileId` и `wallId` не имеют aliases и не угадываются по имени. Сейчас это точные IDs текущего loaded content set, прошедшие `RarityLoader`/`BuffLoader`/`TileLoader`/`WallLoader`; их можно только копировать из parent facts. Modded `DamageClass` является исключением: он хранится устойчивой exact content identity `ModName/ClassName` и разрешается через `ModContent.TryFind`.

### Поля с неочевидными Terraria units

- `valueCopper` напрямую пишет `Item.value`; это base/shop value в copper, а не обещание конкретной суммы resale игроком.
- Author `configure_tool.axePowerTooltipPercent` задаёт целое 0..500 с шагом 5 в видимых процентах tooltip; compiler точно пишет старое целое `gameplay.axePower = value / 5` в `Item.axe` 0..100. Старое имя `axePower` не принимается как Author alias.
- Author `apply_generated_buff_on_use.lifeRegenHpPerSecond` задаёт вклад в HP/с (0..60, шаг 0.5); compiler точно пишет старое целое `gameplay.generatedBuff.lifeRegen = value × 2`. Это вклад в engine stat до остальных эффектов, не обещание итогового лечения.

<a id="player-text"></a>

### Описание игроку и engine units — разные представления

Lowery — технический lowering, не lore и не автор дополнительной механики. Author задаёт игровые расстояния в блоках, длительности в секундах, скорости в блоках/с. Меняется schema авторинга; сохранённый engine wire остаётся в прежних единицах. Canonical lowering выполняет объявленные проекции с учётом updatesPerTick именно затронутой сущности. Секунды разрешаются до ближайшего целого world tick, половина тика округляется вверх; неположенное обнуление ненулевого эффекта отклоняется, а не скрыто меняет механику. Pixel-labelled collision/sprite geometry и texture/UV units сохраняют своё объявленное пространство. Описание остаётся optional advisory: оно не требует нового отчёта и не запускает validator/Repair. Механическая истина — явно emitted runtimeProgram, а не красивое обещание в тексте.

Ниже — тот же model-facing текст из существующих prompt owners, а не отдельный prose-контракт. Author получает его в `requiredJsonShape.realization` и `runtimeCapabilityContract.technicalNotes`; Repair — в `requiredJsonShape.realizationReplacement` и `runtimeExecutionTruth.units.playerFacingUnits`. Он передаётся в JSON messages при json_schema и json_object; schema annotations для этого не требуются. Если Repair добровольно возвращает описание, оно относится к post-merge программе; read-only context не даёт права менять frozen механику.

| optional prose | shared guidance |
|---|---|
| realization.description | optional advisory interpretation of the emitted runtimeProgram, not an observed execution. Write a concise item description in clear player language: explain the actual controls (use, alternate use, while selected or while equipped), effects, costs, conditions and limits that matter in play. Describe only supported behavior of the emitted bindings, calls and events; distinguish base values or conditional effects from guaranteed outcomes. Do not invent abilities, charges, safety, cooldowns or measured results from names, appearance or intent. Use Terraria blocks, blocks/s and seconds for player-facing distance, speed and time; gameplay params use their Author cards' human units and lowering produces engine units. Pixel-labelled geometry retains its declared engine units. Prefer readable actions over internal ids, capability names or a parameter dump. No extra lore or report is required; string minLength=0, maxLength=4000 Unicode code points |
| realization.playerExperience | optional advisory notes on practical use and trade-offs of the same emitted mechanics, not additional mechanics or promises; avoid repeating the description; string minLength=0, maxLength=3000 Unicode code points |

| единицы / scope | shared model-facing guide |
|---|---|
| time | Write world durations/intervals in decimal seconds. The engine has 60 world ticks = 1 second; lowering resolves seconds to the nearest world tick, half-tick ties upward. Explicit zero stays zero; a positive effect may not round to disabled zero. Raw immunity.localCooldown and explicitly named projectile-update counters are counts, not seconds. |
| distance | Write gameplay world distances in blocks. 1 Terraria block (tile) = 16 world pixels. rangeTiles/radiusTiles already mean blocks, including blink rangeTiles: do not divide again. Read whether each card means radius, diameter, origin offset or distance to a target center. |
| speed | Write gameplay speeds in blocks/s, physical accelerations in blocks/s^2 and declared angular rates in radians/s. The canonical lowering accounts for the affected target's updatesPerTick; do not manually rescale Author values. Initial speed, flat bonuses, sprint floors and event impulses are distinct, not guaranteed final movement or jump height. Ammo speed is a base native launch contribution; the eventual projectile can have its own update rate. Dimensionless retention/lerp/multiplier controls retain their declared per-update meaning. |
| scope | Use each Author card's declared units; the compiled wire and raw parent facts keep engine units. Pixel-labelled collision and local sprite geometry remain pixels; 16 world pixels = 1 block. Texture texels/canvas dimensions remain texture pixels; normalized UV/grip coordinates remain normalized: do not divide by 16. Texture resolution alone is not rendered world size, collision size or reach. |
| vanillaScaleReference | Vanilla scale reference, not a balance ceiling: an ordinary standing unmounted player's collision box is 20x42 world pixels (1.25x2.625 blocks). Without gear/buffs or special terrain, nominal base run speed is 11.25 blocks/s; a normal jump assigns about 18.79 blocks/s upward velocity. The 15-update held-jump counter is not a distance. Jump height/range depend on hold, gravity and horizontal motion; these are not a measured height/range or a limit on authored mechanics. |
| spread | radians; total span |

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
| move_front_hand | 20 |
| move_traveling_wave | 23 |
| move_elliptic_orbit | 22 |
| move_spring_tether | 21 |

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
| select_targets_and_emit_on_event | 8 |
| apply_generated_buff_on_event | 9 |

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

Whole-pattern aliases и archetype routers не входят в текущий контракт. Name/category/prose не выбирают композицию; compatibility importer и старые spelling не являются вторым API.

<a id="config-aliases"></a>

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

Это только выбор существующего image backend в конфигурации; visual topology и gameplay от spelling не зависят.

### Явные presentation choices

Категория результата проходит strict Author enum без UI/category alias routing. VFX цвет задаётся local RGB objects в slots/profile knots/library endpoints; Visual palette остаётся art context. Технические config aliases выше не выбирают механику, renderer или цвет.

<a id="runtime"></a>

## Где намеренно остаётся наш runtime

1. **`GeneratedItem` и `GeneratedProjectile` — proxy-типы.** tModLoader регистрирует `ModItem`/`ModProjectile` и глобальные type IDs во время загрузки мода, а предметы UnlimitedCraft создаются уже во время игры. Поэтому каждый authored entity получает локальный `entityId`, а не новый глобальный `ProjectileID`.
2. **Per-entity capabilities и opcodes.** Movement/controller/event composition динамична и хранится в typed runtimeProgram. Она не переводится в `aiStyle` или weapon family, если это потеряло бы authored комбинацию.
3. **Per-instance visuals/assets.** Один proxy type не может иметь разные type-wide texture/static sets; PNG/VFX выбираются по generated item ID + entity ID.
4. **Type-wide Terraria sets не подделываются.** `ItemID.Sets`, `ProjectileID.Sets` и ID-static NPC immunity общие для proxy type. Их нельзя безопасно менять на один generated item/entity. Поэтому sand ammo не выставляется: полная sandgun-семантика требует type-wide `ItemID.Sets.SandgunAmmoProjectileData`.
5. **Local NPC immunity.** Поддерживаются явные режимы `owner` и `local`. ID-static immunity не exposed, потому что все generated projectiles имеют один global type и разделили бы cooldown между несвязанными предметами.
6. **Custom hydration/network identity.** `entityId` и generated item ID синхронизируют параметры proxy projectile. `Projectile.identity/whoAmI` остаются Terraria-идентификаторами конкретного экземпляра, но не заменяют authored subtype ID.
7. **Сложные held/beam/field controllers.** Используются обычные ModProjectile hooks и Terraria collision/network fields, но orchestration остаётся bounded custom runtime, потому что она составляется LLM после загрузки контента.

<a id="refresh"></a>

## Обновление и проверка

Из корня репозитория, с Python окружения проекта. Без `--check` этот generator записывает **только `docs/reference/generated/LOWERY_RU.md`**. [Inventory и audit](LOW_LEVEL_CAPABILITY_INVENTORY_RU.md#refresh) и [primitive parity](PRIMITIVE_PARITY_RU.md#refresh) обновляются своими generators.

```bash
PYTHONPATH=LocalGenerator python tools/generate/generate_lowery.py
PYTHONPATH=LocalGenerator python tools/generate/generate_lowery.py --check
PYTHONPATH=LocalGenerator python tools/generate/generate_low_level_runtime_docs.py --check
PYTHONPATH=LocalGenerator python tools/generate/generate_primitive_parity.py --check
PYTHONPATH=LocalGenerator python -m pytest -q LocalGenerator/tests/test_registry_*.py LocalGenerator/tests/test_low_level_three_stage_pipeline.py LocalGenerator/tests/test_pipeline_repair_contract.py
```

Type check: `python tools/testing/run_pyright.py --pythonpath "$(python -c 'import sys; print(sys.executable)')"`. Полные delivery gates: [AGENTS.md](../../../AGENTS.md).

Change-locality acceptance: изменить один canonical owner, обновить generated projections, пройти affected replay; не редактировать параллельные prose contracts и не запускать Live как замену локальному доказательству.

## Запрет на добавление alias

Новый gameplay alias допустим только если два входа обозначают одно и то же точное действие и один из них не показывается Author. Любое новое имя должно быть либо единственным canonical token, либо внутренней migration/config нормализацией вне gameplay. Добавление alias в Author schema требует изменить canonical vocabulary owner, перегенерировать этот файл и пройти `tools/checks/audit_terraria_standardization.py`.
