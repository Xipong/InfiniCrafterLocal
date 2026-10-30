# Low-level authoring и Lowery — канонический контракт

> Generated: [`tools/generate/generate_lowery.py`](../../../tools/generate/generate_lowery.py). Не редактировать вручную; менять canonical owner и [обновлять projection](#refresh).
> Sources: [registry](../../../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py), [Author shape](../../../LocalGenerator/infini_local/core/runtime_authoring/program_schema.py), [lowering](../../../LocalGenerator/infini_local/core/runtime_authoring/technical_lowering.py), [tModLoader vocabulary](../../../LocalGenerator/infini_local/core/runtime_authoring/terraria_vocabulary.py), [Author/Repair prose](../../../LocalGenerator/infini_local/pipelines/author_item_contract.py), [unit guide](../../../LocalGenerator/infini_local/pipelines/llm_authoring_prompt.py).

Schemas: `infini.runtime-program.v5` / `infini.runtime-program.authoring.v6` / `infini.runtime-program.wire.v3`.

**Навигация:** [граница](#boundary) · [owners](#owners) · [Author → wire](#wire) · [manifest](#lowering) · [технические отображения](#mappings) · [текст и единицы игрока](#player-text) · [config/UI aliases](#config-aliases) · [proxy runtime](#runtime) · [обновление и проверка](#refresh).

<a id="boundary"></a>

## READ THIS FIRST — замороженная граница

1. Gameplay Author сам выбирает механику, entities, bindings, calls, params, events, references и metadata. Ни имя, tooltip, category, family, parent tag или capability prose не разрешают коду дописать дизайн.
2. Deterministic Python имеет право только проверить exact authored graph, ограничить его, отфильтровать exact Repair scope и выполнить lossless technical lowering.
3. Lowery не является вторым Author. Он не выбирает movement, attachment, delivery, lifecycle, input, target, entity kind, event, damage, visual topology, hitbox topology, root executor или fallback mechanic. Он может скрывать неудобство API, но не сжимать пространство дизайна.
4. Сжатие буквально повторённых low-level параметров допускается от **5** одинаковых placements и сохраняет literal equality. Этот threshold не запрещает точный выбранный alias или one-to-one technical projection; ни один из них не добавляет design choice.
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

`EventKindSpec` владеет producer calls, producer binding inputs, exact producer params и playerEffect predicate; `EntityKindSpec.base_events` владеет producer-free availability для конкретного kind. Validator и Repair вызывают одну generic registry projection. Event-name `if/elif` вне registry запрещён.

| event | producer calls | producer binding inputs | producer-free kinds | exact params | playerEffect predicate |
|---|---|---|---|---|---|
| on_use | — | primary_use, alternate_use | — | — | — |
| on_spawn | — | — | owner_attached_projectile, free_projectile, stationary_projectile, temporary_helper, field, child_projectile | — | — |
| on_hit | set_projectile_damage | primary_use, alternate_use | — | — | — |
| on_crit | set_projectile_damage | primary_use, alternate_use | — | — | — |
| on_tile_collision | set_projectile_collision | — | — | set_projectile_collision(tileCollide=True) | — |
| on_expire | set_projectile_lifetime | — | owner_attached_projectile, free_projectile, stationary_projectile, temporary_helper, field, child_projectile | — | — |
| on_kill | — | — | owner_attached_projectile, free_projectile, stationary_projectile, temporary_helper, field, child_projectile | — | — |
| periodic | — | — | item_body, owner_attached_projectile, free_projectile, stationary_projectile, temporary_helper, field, child_projectile | — | — |
| on_release | charge_then_release, accumulate_projectile_charge | — | — | — | — |
| channel_complete | charge_then_release, accumulate_projectile_charge | — | — | — | — |
| on_hurt | — | equipped | — | — | — |
| on_enemy_kill | — | equipped | — | — | — |

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
| item_fields_to_tml_projection | item_body capability params | gameplay.damageClass, gameplay.damage, gameplay.knockback, gameplay.useTime, gameplay.useAnimation, gameplay.manaCost, gameplay.manaCostInput, gameplay.rarity, gameplay.value, gameplay.maxStack, gameplay.craftYield, gameplay.width, gameplay.height, gameplay.itemScale, gameplay.useStyleName, gameplay.autoReuse, gameplay.useTurn, gameplay.holdoutOffsetX, gameplay.holdoutOffsetY, gameplay.handPose, gameplay.releaseTiming, runtimeProgram.itemUse.configured, runtimeProgram.itemUse.useStyle, runtimeProgram.itemUse.hideUseGraphic, runtimeProgram.itemUse.disableMeleeHitbox, runtimeProgram.itemUse.channel, runtimeProgram.itemUse.handPose, runtimeProgram.itemUse.releaseTiming, runtimeProgram.itemUse.holdoutOffsetX, runtimeProgram.itemUse.holdoutOffsetY, gameplay.collectSeedsFromGrass, runtimeProgram.itemContact.hitboxScale, runtimeProgram.itemContact.contactForgivenessPx, gameplay.ammoCategory, gameplay.ammoProjectileId, gameplay.ammoShootSpeedPxPerTick, gameplay.notAmmo, gameplay.healLife, gameplay.healMana, gameplay.potion, gameplay.extraBuffs[].buffCode, gameplay.extraBuffs[].buffTime, gameplay.generatedBuff.playerEffect.condition, gameplay.generatedBuff.playerEffect.fishingPowerPoints, gameplay.generatedBuff.playerEffect.preventLineBreak, gameplay.generatedBuff.playerEffect.allowLavaFishing, gameplay.generatedBuff.playerEffect.revealHookedCatch, gameplay.generatedBuff.playerEffect.extraCrateChancePercent, gameplay.generatedBuff.playerEffect.itemPickupRangePx, gameplay.generatedBuff.playerEffect.heartPickupRangePx, gameplay.generatedBuff.playerEffect.manaPickupRangePx, gameplay.generatedBuff.playerEffect.coinPickupRangePx, gameplay.generatedBuff.playerEffect.highlightDanger, gameplay.generatedBuff.playerEffect.highlightCreatures, gameplay.generatedBuff.playerEffect.nightVision, gameplay.generatedBuff.playerEffect.healingPotionCooldownReductionPercent, gameplay.generatedBuff.playerEffect.healingPotionCooldownReductionTicks, gameplay.generatedBuff.playerEffect.autoManaPotionBelowPercent, gameplay.generatedBuff.playerEffect.healingPotionCooldownOnHitReductionTicks, gameplay.generatedBuff.playerEffect.hurtInvulnerabilityBonusTicks, gameplay.generatedBuff.durationTicks, gameplay.generatedBuff.exhaustionTicks, gameplay.generatedBuff.miningSpeedMultiplier, gameplay.generatedBuff.emitLightStrength, gameplay.generatedBuff.lightColorName, gameplay.generatedBuff.oreSenseRadiusTiles, gameplay.generatedBuff.movementSpeed, gameplay.generatedBuff.jumpBoost, gameplay.generatedBuff.manaRegen, gameplay.generatedBuff.lifeRegen, gameplay.generatedBuff.lifeRegenCondition, gameplay.generatedBuff.treasureSenseCondition, gameplay.generatedBuff.combat.defensePoints, gameplay.generatedBuff.combat.attackSpeedPercent, gameplay.generatedBuff.combat.critChancePoints, gameplay.generatedBuff.combat.damagePercent, gameplay.generatedBuff.combat.damageClass, gameplay.pickPower, gameplay.axePower, gameplay.hammerPower, gameplay.miningSpeedScale, gameplay.useConditions[].input, gameplay.useConditions[].useConditionMode, gameplay.useConditions[].useConditionMinLife, gameplay.useConditions[].useConditionMinMana, gameplay.holdLightStrength, gameplay.holdLightColorName, gameplay.mobilityMode, gameplay.mobilityRangeTiles, gameplay.mobilityCooldownTicks, gameplay.mobilitySafeTileOnly, accessory.enabled, accessory.playerEffect.condition, accessory.playerEffect.fishingPowerPoints, accessory.playerEffect.preventLineBreak, accessory.playerEffect.allowLavaFishing, accessory.playerEffect.revealHookedCatch, accessory.playerEffect.extraCrateChancePercent, accessory.playerEffect.itemPickupRangePx, accessory.playerEffect.heartPickupRangePx, accessory.playerEffect.manaPickupRangePx, accessory.playerEffect.coinPickupRangePx, accessory.playerEffect.highlightDanger, accessory.playerEffect.highlightCreatures, accessory.playerEffect.nightVision, accessory.playerEffect.healingPotionCooldownReductionPercent, accessory.playerEffect.healingPotionCooldownReductionTicks, accessory.playerEffect.autoManaPotionBelowPercent, accessory.playerEffect.healingPotionCooldownOnHitReductionTicks, accessory.playerEffect.hurtInvulnerabilityBonusTicks, accessory.lifeRegenCondition, accessory.treasureSense, accessory.treasureSenseCondition, accessory.defense, accessory.maxLife, accessory.maxMana, accessory.lifeRegen, accessory.manaRegen, accessory.movementSpeed, accessory.maxRunSpeed, accessory.jumpSpeed, accessory.genericCrit, accessory.attackSpeed, accessory.knockback, accessory.minionSlots, accessory.sentrySlots, accessory.manaCostReduction, accessory.ammoSaveChance, accessory.aggro, accessory.endurance, accessory.armorPenetration, accessory.whipRange, accessory.summonTagDamage, accessory.lightStrength, accessory.lightColorName, accessory.fallDamageImmune, accessory.lavaImmune, accessory.waterWalk, accessory.iceSkate, accessory.noKnockback, accessory.fireWalk, accessory.accRunSpeed, accessory.rocketBoots, accessory.wireVision, armor.enabled, armor.slot, armor.setKey, armor.playerEffect.condition, armor.playerEffect.fishingPowerPoints, armor.playerEffect.preventLineBreak, armor.playerEffect.allowLavaFishing, armor.playerEffect.revealHookedCatch, armor.playerEffect.extraCrateChancePercent, armor.playerEffect.itemPickupRangePx, armor.playerEffect.heartPickupRangePx, armor.playerEffect.manaPickupRangePx, armor.playerEffect.coinPickupRangePx, armor.playerEffect.highlightDanger, armor.playerEffect.highlightCreatures, armor.playerEffect.nightVision, armor.playerEffect.healingPotionCooldownReductionPercent, armor.playerEffect.healingPotionCooldownReductionTicks, armor.playerEffect.autoManaPotionBelowPercent, armor.playerEffect.healingPotionCooldownOnHitReductionTicks, armor.playerEffect.hurtInvulnerabilityBonusTicks, armor.lifeRegenCondition, armor.treasureSense, armor.treasureSenseCondition, armor.defense, armor.maxLife, armor.maxMana, armor.lifeRegen, armor.manaRegen, armor.movementSpeed, armor.maxRunSpeed, armor.jumpSpeed, armor.genericCrit, armor.attackSpeed, armor.knockback, armor.minionSlots, armor.sentrySlots, armor.manaCostReduction, armor.ammoSaveChance, armor.aggro, armor.endurance, armor.armorPenetration, armor.whipRange, armor.summonTagDamage, armor.lightStrength, armor.lightColorName, armor.fallDamageImmune, armor.lavaImmune, armor.waterWalk, armor.setBonusGenericCrit, armor.setBonusMovementSpeed, armor.setBonusLifeRegen, armor.setBonusManaRegen, armor.setBonusMinionSlots, armor.setBonusSentrySlots, armor.setBonusManaCostReduction, armor.setBonusAmmoSaveChance, armor.setBonusAggro, armor.setBonusEndurance, armor.setBonusArmorPenetration, accessory.genericDamage, accessory.meleeDamage, accessory.rangedDamage, accessory.magicDamage, accessory.summonDamage, armor.genericDamage, armor.meleeDamage, armor.rangedDamage, armor.magicDamage, armor.summonDamage, armor.setBonusGenericDamage, armor.setBonusMeleeDamage, armor.setBonusRangedDamage, armor.setBonusMagicDamage, armor.setBonusSummonDamage | false |

### Точные выбранные проекции capabilities

Это не второй список политик: значения ниже получены из registry fixed_wire_literals, MOVEMENT_OPCODE/CONTROLLER_OPCODE/EVENT_ACTION_OPCODE и cap.wire_action через canonical lowerer. Каждый fn-selected выход требует ровно один technical_projection receipt с exact source .fn, callId, finalPath и типизированным значением. Source-aware audit связывает его с реально выбранным executor и authored target; согласованно изменить wire и receipt недостаточно. Без Author `authoredSourceChecked=false`: это только проверка согласованности сохранённых утверждений, не восстановление неизвестного намерения. Старые wire/opcodes/отсутствия не переписываются на чтении. `fresh Author` означает доступный модели самостоятельный fn; `retained runtime` сохраняется для принятого runtime wire, но не предлагается как самостоятельный fn в новом Author.

| capability | availability | fn-selected wire output | exact value |
|---|---|---|---|
| sustain_projectile_mana | fresh Author | runtimeProgram.entities[].manaSustain.cadence | 'held_item_use_time' |
| set_projectile_arrival | fresh Author | runtimeProgram.entities[].arrival.action | 'kill' |
| configure_item_use | fresh Author | runtimeProgram.itemUse.configured | True |
| collect_seeds_from_grass | fresh Author | gameplay.collectSeedsFromGrass | True |
| configure_tile_placement | fresh Author | runtimeProgram.bindings[].usePolicy.action.placement.wallId | -1 |
| configure_wall_placement | fresh Author | runtimeProgram.bindings[].usePolicy.action.placement.tileId | -1 |
| recall_home_on_use | fresh Author | gameplay.mobilityMode | 'recall_home' |
| recall_home_on_use | fresh Author | runtimeProgram.effectGroups[].mobilityMode | 'recall_home' |
| recall_home_on_use | fresh Author | gameplay.mobilityRangeTiles | 0 |
| recall_home_on_use | fresh Author | runtimeProgram.effectGroups[].mobilityRangeTiles | 0 |
| recall_home_on_use | fresh Author | gameplay.mobilitySafeTileOnly | False |
| recall_home_on_use | fresh Author | runtimeProgram.effectGroups[].mobilitySafeTileOnly | False |
| configure_accessory | fresh Author | accessory.enabled | True |
| configure_armor | fresh Author | armor.enabled | True |
| configure_spawn | fresh Author | runtimeProgram.entities[].spawn.enabled | True |
| set_projectile_damage | fresh Author | runtimeProgram.entities[].damage.enabled | True |
| orient_whip_to_owner_gravity | retained runtime | runtimeProgram.entities[].whipUsesOwnerGravity | True |
| move_straight | fresh Author | runtimeProgram.entities[].movement.name | 'move_straight' |
| move_straight | fresh Author | runtimeProgram.entities[].movement.code | 0 |
| move_slow_homing | retained runtime | runtimeProgram.entities[].movement.name | 'move_slow_homing' |
| move_slow_homing | retained runtime | runtimeProgram.entities[].movement.code | 1 |
| move_gravity_arc | retained runtime | runtimeProgram.entities[].movement.name | 'move_gravity_arc' |
| move_gravity_arc | retained runtime | runtimeProgram.entities[].movement.code | 2 |
| move_drift | retained runtime | runtimeProgram.entities[].movement.name | 'move_drift' |
| move_drift | retained runtime | runtimeProgram.entities[].movement.code | 3 |
| move_orbit | retained runtime | runtimeProgram.entities[].movement.name | 'move_orbit' |
| move_orbit | retained runtime | runtimeProgram.entities[].movement.code | 4 |
| move_boomerang | retained runtime | runtimeProgram.entities[].movement.name | 'move_boomerang' |
| move_boomerang | retained runtime | runtimeProgram.entities[].movement.code | 5 |
| move_sine_homing | retained runtime | runtimeProgram.entities[].movement.name | 'move_sine_homing' |
| move_sine_homing | retained runtime | runtimeProgram.entities[].movement.code | 7 |
| move_phase | retained runtime | runtimeProgram.entities[].movement.name | 'move_phase' |
| move_phase | retained runtime | runtimeProgram.entities[].movement.code | 8 |
| move_accelerate | retained runtime | runtimeProgram.entities[].movement.name | 'move_accelerate' |
| move_accelerate | retained runtime | runtimeProgram.entities[].movement.code | 9 |
| move_spiral | retained runtime | runtimeProgram.entities[].movement.name | 'move_spiral' |
| move_spiral | retained runtime | runtimeProgram.entities[].movement.code | 10 |
| move_vortex_orb | retained runtime | runtimeProgram.entities[].movement.name | 'move_vortex_orb' |
| move_vortex_orb | retained runtime | runtimeProgram.entities[].movement.code | 11 |
| move_blackhole_pull | retained runtime | runtimeProgram.entities[].movement.name | 'move_blackhole_pull' |
| move_blackhole_pull | retained runtime | runtimeProgram.entities[].movement.code | 12 |
| move_proximity_missile | retained runtime | runtimeProgram.entities[].movement.name | 'move_proximity_missile' |
| move_proximity_missile | retained runtime | runtimeProgram.entities[].movement.code | 13 |
| move_returning_glaive | retained runtime | runtimeProgram.entities[].movement.name | 'move_returning_glaive' |
| move_returning_glaive | retained runtime | runtimeProgram.entities[].movement.code | 14 |
| move_expanding_wave | retained runtime | runtimeProgram.entities[].movement.name | 'move_expanding_wave' |
| move_expanding_wave | retained runtime | runtimeProgram.entities[].movement.code | 15 |
| move_flail_tether | retained runtime | runtimeProgram.entities[].movement.name | 'move_flail_tether' |
| move_flail_tether | retained runtime | runtimeProgram.entities[].movement.code | 16 |
| move_yoyo_hover | retained runtime | runtimeProgram.entities[].movement.name | 'move_yoyo_hover' |
| move_yoyo_hover | retained runtime | runtimeProgram.entities[].movement.code | 17 |
| move_whip_lash | retained runtime | runtimeProgram.entities[].movement.name | 'move_whip_lash' |
| move_whip_lash | retained runtime | runtimeProgram.entities[].movement.code | 18 |
| move_forward_then_retract | retained runtime | runtimeProgram.entities[].movement.name | 'move_forward_then_retract' |
| move_forward_then_retract | retained runtime | runtimeProgram.entities[].movement.code | 19 |
| move_front_hand | retained runtime | runtimeProgram.entities[].movement.name | 'move_front_hand' |
| move_front_hand | retained runtime | runtimeProgram.entities[].movement.code | 20 |
| channel_beam | retained runtime | runtimeProgram.entities[].controller.name | 'channel_beam' |
| channel_beam | retained runtime | runtimeProgram.entities[].controller.code | 1 |
| charge_then_release | retained runtime | runtimeProgram.entities[].controller.name | 'charge_then_release' |
| charge_then_release | retained runtime | runtimeProgram.entities[].controller.code | 2 |
| target_and_fire | fresh Author | runtimeProgram.entities[].controller.name | 'target_and_fire' |
| target_and_fire | fresh Author | runtimeProgram.entities[].controller.code | 3 |
| spawn_entity_on_event | fresh Author | runtimeProgram.entities[].events[].action | 'spawn_entity_on_event' |
| spawn_entity_on_event | fresh Author | runtimeProgram.entities[].events[].actionCode | 1 |
| spawn_entity_from_hit_target | fresh Author | runtimeProgram.entities[].events[].action | 'spawn_entity_on_event' |
| spawn_entity_from_hit_target | fresh Author | runtimeProgram.entities[].events[].actionCode | 1 |
| select_targets_and_emit_on_event | fresh Author | runtimeProgram.entities[].events[].action | 'select_targets_and_emit_on_event' |
| select_targets_and_emit_on_event | fresh Author | runtimeProgram.entities[].events[].actionCode | 8 |
| apply_generated_buff_on_event | fresh Author | runtimeProgram.entities[].events[].action | 'apply_generated_buff_on_event' |
| apply_generated_buff_on_event | fresh Author | runtimeProgram.entities[].events[].actionCode | 9 |
| apply_npc_effect_on_event | fresh Author | runtimeProgram.entities[].events[].action | 'apply_npc_effect_on_event' |
| apply_npc_effect_on_event | fresh Author | runtimeProgram.entities[].events[].actionCode | 11 |
| apply_status_on_event | fresh Author | runtimeProgram.entities[].events[].action | 'apply_status_on_event' |
| apply_status_on_event | fresh Author | runtimeProgram.entities[].events[].actionCode | 2 |
| damage_nearby_on_event | fresh Author | runtimeProgram.entities[].events[].action | 'damage_nearby_on_event' |
| damage_nearby_on_event | fresh Author | runtimeProgram.entities[].events[].actionCode | 10 |
| damage_area_on_event | retained runtime | runtimeProgram.entities[].events[].action | 'damage_area_on_event' |
| damage_area_on_event | retained runtime | runtimeProgram.entities[].events[].actionCode | 3 |
| damage_nearest_on_event | retained runtime | runtimeProgram.entities[].events[].action | 'chain_damage_on_event' |
| damage_nearest_on_event | retained runtime | runtimeProgram.entities[].events[].actionCode | 4 |
| pull_on_event | fresh Author | runtimeProgram.entities[].events[].action | 'pull_on_event' |
| pull_on_event | fresh Author | runtimeProgram.entities[].events[].actionCode | 5 |
| pull_owner_to_event_target | retained runtime | runtimeProgram.entities[].events[].mode | 'owner_to_target' |
| pull_owner_to_event_target | retained runtime | runtimeProgram.entities[].events[].radiusTiles | 1 |
| pull_owner_to_event_target | retained runtime | runtimeProgram.entities[].events[].action | 'pull_on_event' |
| pull_owner_to_event_target | retained runtime | runtimeProgram.entities[].events[].actionCode | 5 |
| reduce_heal_cooldown_on_event | fresh Author | runtimeProgram.entities[].events[].action | 'reduce_healing_potion_cooldown_on_event' |
| reduce_heal_cooldown_on_event | fresh Author | runtimeProgram.entities[].events[].actionCode | 12 |
| heal_owner_on_event | fresh Author | runtimeProgram.entities[].events[].action | 'heal_owner_on_event' |
| heal_owner_on_event | fresh Author | runtimeProgram.entities[].events[].actionCode | 6 |
| move_owner_on_event | fresh Author | runtimeProgram.entities[].events[].mode | 'blink_to_event_position' |
| move_owner_on_event | fresh Author | runtimeProgram.entities[].events[].action | 'move_owner_on_event' |
| move_owner_on_event | fresh Author | runtimeProgram.entities[].events[].actionCode | 7 |

### Явные event-проекции

Разное authored имя может выбирать точную зарегистрированную проекцию существующего event executor. Это полезный отдельный выбор, не разрешение угадывать действие из prose и не whole-weapon macro.

| capability | availability | wire action | fixed outputs |
|---|---|---|---|
| spawn_entity_from_hit_target | fresh Author | spawn_entity_on_event | {'action': 'spawn_entity_on_event', 'actionCode': 1} |
| damage_nearest_on_event | retained runtime | chain_damage_on_event | {'action': 'chain_damage_on_event', 'actionCode': 4} |
| pull_owner_to_event_target | retained runtime | pull_on_event | {'mode': 'owner_to_target', 'radiusTiles': 1, 'action': 'pull_on_event', 'actionCode': 5} |
| reduce_heal_cooldown_on_event | fresh Author | reduce_healing_potion_cooldown_on_event | {'action': 'reduce_healing_potion_cooldown_on_event', 'actionCode': 12} |

### Structured и enum projections

Typed structured choices и конечные enum-отображения также принадлежат ParamSpec; они сохраняют явно выбранную ветвь и полезные независимые параметры.

| capability.param | declared projection |
|---|---|
| accumulate_projectile_charge.releaseEffect | (('releaseEffect.damageMultiplier', 'damageMultiplier', False), ('releaseEffect.knockbackMultiplier', 'knockbackMultiplier', False), ('releaseEffect.speedMultiplier', 'speedMultiplier', False), ('releaseEffect.launchSpeedBlocksPerSecond', 'launchSpeed', False), ('releaseEffect.pauseLifetimeWhileCharging', 'pauseLifetimeWhileCharging', False)) |
| gate_projectile_contact.window | (('window.phase', 'window.phase', False), ('window.clock', 'window.clock', False), ('window.startDelaySeconds', 'window.startDelayTicks', False), ('window.durationSeconds', 'window.durationTicks', False)) |
| set_projectile_beam_geometry.ramp | (('ramp.warmupSeconds', 'warmupTicks', False), ('ramp.initialWidthMultiplier', 'initialWidthMultiplier', False), ('ramp.initialDamageMultiplier', 'initialDamageMultiplier', False), ('ramp.damageStartProgress', 'damageStartProgress', False)) |
| attach_projectile.window | (('window.phase', 'window.phase', False), ('window.clock', 'window.clock', False), ('window.startDelaySeconds', 'window.startDelayTicks', False), ('window.durationSeconds', 'window.durationTicks', False)) |
| attach_projectile.reachCurve | (('reachCurve.durationSeconds', 'durationTicks', False), ('reachCurve.startOffsetBlocks', 'startOffsetPx', False), ('reachCurve.peakOffsetBlocks', 'peakOffsetPx', False), ('reachCurve.endOffsetBlocks', 'endOffsetPx', False), ('reachCurve.peakProgress', 'peakProgress', False), ('reachCurve.window.phase', 'window.phase', False), ('reachCurve.window.clock', 'window.clock', False), ('reachCurve.window.startDelaySeconds', 'window.startDelayTicks', False), ('reachCurve.window.durationSeconds', 'window.durationTicks', False)) |
| set_front_arm_pose.window | (('window.phase', 'window.phase', False), ('window.clock', 'window.clock', False), ('window.startDelaySeconds', 'window.startDelayTicks', False), ('window.durationSeconds', 'window.durationTicks', False)) |
| set_projectile_reach_curve.window | (('window.phase', 'window.phase', False), ('window.clock', 'window.clock', False), ('window.startDelaySeconds', 'window.startDelayTicks', False), ('window.durationSeconds', 'window.durationTicks', False)) |
| orbit_projectile.window | (('window.phase', 'window.phase', False), ('window.clock', 'window.clock', False), ('window.startDelaySeconds', 'window.startDelayTicks', False), ('window.durationSeconds', 'window.durationTicks', False)) |
| seek_projectile.window | (('window.phase', 'window.phase', False), ('window.clock', 'window.clock', False), ('window.startDelaySeconds', 'window.startDelayTicks', False), ('window.durationSeconds', 'window.durationTicks', False)) |
| set_projectile_arrival.window | (('window.phase', 'window.phase', False), ('window.clock', 'window.clock', False), ('window.startDelaySeconds', 'window.startDelayTicks', False), ('window.durationSeconds', 'window.durationTicks', False)) |
| set_projectile_proximity_action.window | (('window.phase', 'window.phase', False), ('window.clock', 'window.clock', False), ('window.startDelaySeconds', 'window.startDelayTicks', False), ('window.durationSeconds', 'window.durationTicks', False)) |
| accelerate_projectile_vertical.window | (('window.phase', 'window.phase', False), ('window.clock', 'window.clock', False), ('window.startDelaySeconds', 'window.startDelayTicks', False), ('window.durationSeconds', 'window.durationTicks', False)) |
| multiply_projectile_velocity.window | (('window.phase', 'window.phase', False), ('window.clock', 'window.clock', False), ('window.startDelaySeconds', 'window.startDelayTicks', False), ('window.durationSeconds', 'window.durationTicks', False)) |
| scale_projectile_velocity.window | (('window.phase', 'window.phase', False), ('window.clock', 'window.clock', False), ('window.startDelaySeconds', 'window.startDelayTicks', False), ('window.durationSeconds', 'window.durationTicks', False)) |
| set_projectile_rotation.window | (('window.phase', 'window.phase', False), ('window.clock', 'window.clock', False), ('window.startDelaySeconds', 'window.startDelayTicks', False), ('window.durationSeconds', 'window.durationTicks', False)) |
| oscillate_projectile_velocity.law | (('law', 'law', True), ('law.angular_sine.amplitudeRadiansPerSecond', 'amplitude', False), ('law.lateral_velocity_sine.amplitudeBlocksPerSecond', 'amplitude', False)) |
| oscillate_projectile_velocity.window | (('window.phase', 'window.phase', False), ('window.clock', 'window.clock', False), ('window.startDelaySeconds', 'window.startDelayTicks', False), ('window.durationSeconds', 'window.durationTicks', False)) |
| add_projectile_visual_scale.window | (('window.phase', 'window.phase', False), ('window.clock', 'window.clock', False), ('window.startDelaySeconds', 'window.startDelayTicks', False), ('window.durationSeconds', 'window.durationTicks', False)) |
| set_projectile_opacity.window | (('window.phase', 'window.phase', False), ('window.clock', 'window.clock', False), ('window.startDelaySeconds', 'window.startDelayTicks', False), ('window.durationSeconds', 'window.durationTicks', False)) |
| configure_item_use.customHeldSprite | {'hidden': 'immediate', 'visible': 'on_release', 'inherit': ''} |
| apply_generated_buff_on_use.playerEffect | (('playerEffect.condition', 'playerEffect.condition', False), ('playerEffect.fishingPowerPoints', 'playerEffect.fishingPowerPoints', False), ('playerEffect.preventLineBreak', 'playerEffect.preventLineBreak', False), ('playerEffect.allowLavaFishing', 'playerEffect.allowLavaFishing', False), ('playerEffect.revealHookedCatch', 'playerEffect.revealHookedCatch', False), ('playerEffect.extraCrateChancePercent', 'playerEffect.extraCrateChancePercent', False), ('playerEffect.itemPickupRangeBlocks', 'playerEffect.itemPickupRangePx', False), ('playerEffect.heartPickupRangeBlocks', 'playerEffect.heartPickupRangePx', False), ('playerEffect.manaPickupRangeBlocks', 'playerEffect.manaPickupRangePx', False), ('playerEffect.coinPickupRangeBlocks', 'playerEffect.coinPickupRangePx', False), ('playerEffect.highlightDanger', 'playerEffect.highlightDanger', False), ('playerEffect.highlightCreatures', 'playerEffect.highlightCreatures', False), ('playerEffect.nightVision', 'playerEffect.nightVision', False), ('playerEffect.healCooldownReductionPercent', 'playerEffect.healingPotionCooldownReductionPercent', False), ('playerEffect.healCooldownReduction', 'playerEffect.healingPotionCooldownReductionTicks', False), ('playerEffect.manaPotionBelowPercent', 'playerEffect.autoManaPotionBelowPercent', False), ('playerEffect.healCooldownOnHit', 'playerEffect.healingPotionCooldownOnHitReductionTicks', False), ('playerEffect.hurtImmunityBonus', 'playerEffect.hurtInvulnerabilityBonusTicks', False)) |
| apply_generated_buff_on_use.combat | (('combat.defensePoints', 'combat.defensePoints', False), ('combat.attackSpeedPercent', 'combat.attackSpeedPercent', False), ('combat.critChancePoints', 'combat.critChancePoints', False), ('combat.damagePercent', 'combat.damagePercent', False), ('combat.damageClass', 'combat.damageClass', False)) |
| require_use_condition.condition | (('condition', 'useConditionMode', True), ('condition.lifeAtLeast', 'useConditionMinLife', False), ('condition.manaAtLeast', 'useConditionMinMana', False)) |
| configure_accessory.playerEffect | (('playerEffect.condition', 'playerEffect.condition', False), ('playerEffect.fishingPowerPoints', 'playerEffect.fishingPowerPoints', False), ('playerEffect.preventLineBreak', 'playerEffect.preventLineBreak', False), ('playerEffect.allowLavaFishing', 'playerEffect.allowLavaFishing', False), ('playerEffect.revealHookedCatch', 'playerEffect.revealHookedCatch', False), ('playerEffect.extraCrateChancePercent', 'playerEffect.extraCrateChancePercent', False), ('playerEffect.itemPickupRangeBlocks', 'playerEffect.itemPickupRangePx', False), ('playerEffect.heartPickupRangeBlocks', 'playerEffect.heartPickupRangePx', False), ('playerEffect.manaPickupRangeBlocks', 'playerEffect.manaPickupRangePx', False), ('playerEffect.coinPickupRangeBlocks', 'playerEffect.coinPickupRangePx', False), ('playerEffect.highlightDanger', 'playerEffect.highlightDanger', False), ('playerEffect.highlightCreatures', 'playerEffect.highlightCreatures', False), ('playerEffect.nightVision', 'playerEffect.nightVision', False), ('playerEffect.healCooldownReductionPercent', 'playerEffect.healingPotionCooldownReductionPercent', False), ('playerEffect.healCooldownReduction', 'playerEffect.healingPotionCooldownReductionTicks', False), ('playerEffect.manaPotionBelowPercent', 'playerEffect.autoManaPotionBelowPercent', False), ('playerEffect.healCooldownOnHit', 'playerEffect.healingPotionCooldownOnHitReductionTicks', False), ('playerEffect.hurtImmunityBonus', 'playerEffect.hurtInvulnerabilityBonusTicks', False)) |
| configure_armor.playerEffect | (('playerEffect.condition', 'playerEffect.condition', False), ('playerEffect.fishingPowerPoints', 'playerEffect.fishingPowerPoints', False), ('playerEffect.preventLineBreak', 'playerEffect.preventLineBreak', False), ('playerEffect.allowLavaFishing', 'playerEffect.allowLavaFishing', False), ('playerEffect.revealHookedCatch', 'playerEffect.revealHookedCatch', False), ('playerEffect.extraCrateChancePercent', 'playerEffect.extraCrateChancePercent', False), ('playerEffect.itemPickupRangeBlocks', 'playerEffect.itemPickupRangePx', False), ('playerEffect.heartPickupRangeBlocks', 'playerEffect.heartPickupRangePx', False), ('playerEffect.manaPickupRangeBlocks', 'playerEffect.manaPickupRangePx', False), ('playerEffect.coinPickupRangeBlocks', 'playerEffect.coinPickupRangePx', False), ('playerEffect.highlightDanger', 'playerEffect.highlightDanger', False), ('playerEffect.highlightCreatures', 'playerEffect.highlightCreatures', False), ('playerEffect.nightVision', 'playerEffect.nightVision', False), ('playerEffect.healCooldownReductionPercent', 'playerEffect.healingPotionCooldownReductionPercent', False), ('playerEffect.healCooldownReduction', 'playerEffect.healingPotionCooldownReductionTicks', False), ('playerEffect.manaPotionBelowPercent', 'playerEffect.autoManaPotionBelowPercent', False), ('playerEffect.healCooldownOnHit', 'playerEffect.healingPotionCooldownOnHitReductionTicks', False), ('playerEffect.hurtImmunityBonus', 'playerEffect.hurtInvulnerabilityBonusTicks', False)) |
| configure_armor.setBonuses | (('setBonuses.genericCritChancePercentagePoints', 'setBonusGenericCrit', False), ('setBonuses.moveSpeedBonusPercent', 'setBonusMovementSpeed', False), ('setBonuses.lifeRegen', 'setBonusLifeRegen', False), ('setBonuses.manaRegenBonusPoints', 'setBonusManaRegen', False), ('setBonuses.minionSlotsBonus', 'setBonusMinionSlots', False), ('setBonuses.sentrySlotsBonus', 'setBonusSentrySlots', False), ('setBonuses.manaCostReductionPercentagePoints', 'setBonusManaCostReduction', False), ('setBonuses.ammoSaveChancePercent', 'setBonusAmmoSaveChance', False), ('setBonuses.aggroPoints', 'setBonusAggro', False), ('setBonuses.damageReductionPercentagePoints', 'setBonusEndurance', False), ('setBonuses.genericArmorPenetrationPoints', 'setBonusArmorPenetration', False)) |
| configure_spawn.velocity | (('velocity.constantSpeedBlocksPerSecond', 'speedPxPerTick', False), ('velocity.fanSpeed', 'velocityDistribution.kind', True), ('velocity.fanSpeed', 'speedPxPerTick', True), ('velocity.fanSpeed.minSpeedBlocksPerSecond', 'velocityDistribution.minSpeedPxPerUpdate', False), ('velocity.fanSpeed.maxSpeedBlocksPerSecond', 'velocityDistribution.maxSpeedPxPerUpdate', False), ('velocity.radial', 'velocityDistribution.kind', True), ('velocity.radial', 'speedPxPerTick', True), ('velocity.radial.minSpeedBlocksPerSecond', 'velocityDistribution.minSpeedPxPerUpdate', False), ('velocity.radial.maxSpeedBlocksPerSecond', 'velocityDistribution.maxSpeedPxPerUpdate', False), ('velocity.disk', 'velocityDistribution.kind', True), ('velocity.disk', 'speedPxPerTick', True), ('velocity.disk.maxSpeedBlocksPerSecond', 'velocityDistribution.maxSpeedPxPerUpdate', False), ('velocity.cone', 'velocityDistribution.kind', True), ('velocity.cone', 'speedPxPerTick', True), ('velocity.cone.minSpeedBlocksPerSecond', 'velocityDistribution.minSpeedPxPerUpdate', False), ('velocity.cone.maxSpeedBlocksPerSecond', 'velocityDistribution.maxSpeedPxPerUpdate', False), ('velocity.cone.halfAngleRadians', 'velocityDistribution.halfAngleRadians', False)) |
| configure_spawn.position | (('position', 'overTarget.heightTiles', True), ('position', 'overTarget.delayTicks', True), ('position.at', 'placement', False), ('position.above', 'placement', False), ('position.heightTiles', 'overTarget.heightTiles', False), ('position.activationDelaySeconds', 'overTarget.delayTicks', False)) |
| set_projectile_turn_modifier.window | (('window.phase', 'window.phase', False), ('window.clock', 'window.clock', False), ('window.startDelaySeconds', 'window.startDelayTicks', False), ('window.durationSeconds', 'window.durationTicks', False)) |
| set_projectile_speed_modifier.window | (('window.phase', 'window.phase', False), ('window.clock', 'window.clock', False), ('window.startDelaySeconds', 'window.startDelayTicks', False), ('window.durationSeconds', 'window.durationTicks', False)) |
| set_projectile_homing_modifier.window | (('window.phase', 'window.phase', False), ('window.clock', 'window.clock', False), ('window.startDelaySeconds', 'window.startDelayTicks', False), ('window.durationSeconds', 'window.durationTicks', False)) |
| attract_npcs_while_active.window | (('window.phase', 'window.phase', False), ('window.clock', 'window.clock', False), ('window.startDelaySeconds', 'window.startDelayTicks', False), ('window.durationSeconds', 'window.durationTicks', False)) |
| set_projectile_visual_scale_curve.window | (('window.phase', 'window.phase', False), ('window.clock', 'window.clock', False), ('window.startDelaySeconds', 'window.startDelayTicks', False), ('window.durationSeconds', 'window.durationTicks', False)) |
| set_projectile_collision.immunity | (('immunity', 'npcImmunityMode', True), ('immunity', 'localNpcHitCooldownTicks', True), ('immunity.localCooldown', 'localNpcHitCooldownTicks', False)) |
| spawn_entity_on_event.when | (('when', 'event', False), ('when.on', 'event', False), ('when.useInput', 'useInput', False), ('when', 'event', True), ('when.everySeconds', 'periodTicks', False), ('when.cooldownSeconds', 'reactionCooldownTicks', False)) |
| spawn_entity_from_hit_target.geometry | (('geometry', 'spreadRadians', True), ('geometry.beforeProbability', 'hitTargetSpawn.beforeProbability', False), ('geometry.hitboxMaxSideFactor', 'hitTargetSpawn.hitboxMaxSideFactor', False), ('geometry.clearanceBlocks', 'hitTargetSpawn.clearancePx', False), ('geometry.beforePositionJitterRadiusBlocks', 'hitTargetSpawn.beforePositionJitterRadiusPx', False), ('geometry.beforeDirectionJitterRadians', 'hitTargetSpawn.beforeDirectionJitterRadians', False), ('geometry.afterFanSpreadRadians', 'hitTargetSpawn.afterFanSpreadRadians', False), ('geometry.initialIgnoreCountdownUpdates', 'hitTargetSpawn.initialIgnoreCountdownUpdates', False)) |
| apply_generated_buff_on_event.when | (('when.on', 'event', False), ('when.cooldownSeconds', 'reactionCooldownTicks', False)) |
| damage_nearby_on_event.when | (('when', 'event', False), ('when.on', 'event', False), ('when.cooldownSeconds', 'reactionCooldownTicks', False)) |
| damage_area_on_event.when | (('when', 'event', False), ('when.on', 'event', False), ('when.cooldownSeconds', 'reactionCooldownTicks', False)) |
| pull_on_event.when | (('when', 'event', False), ('when', 'event', True), ('when.everySeconds', 'periodTicks', False)) |
| pull_owner_to_event_target.when | (('when', 'event', False), ('when', 'event', True), ('when.everySeconds', 'periodTicks', False)) |

### Разрешённые neutral omissions

Это только объявленные default=neutral, не универсальное правило для нуля. При условии вне указанной ветви leaf остаётся обязательным; contradictory-present не исправляется. Compiler выдаёт declared_neutral_omission receipt, а Repair отсутствие сохраняет.

| capability.param | exact neutral | omission condition |
|---|---|---|
| set_projectile_owner_control.requireHeldItem | False | unconditional declared neutral |
| set_projectile_owner_control.requireChannel | False | unconditional declared neutral |
| set_projectile_owner_control.requireItemAnimation | False | unconditional declared neutral |
| set_projectile_owner_control.claimHeldProjectile | False | unconditional declared neutral |
| set_projectile_owner_control.animation | 'none' | unconditional declared neutral |
| set_projectile_owner_control.lifetime | 'authored' | unconditional declared neutral |
| apply_projectile_charge_release.damageMultiplier | 1 | unconditional declared neutral |
| apply_projectile_charge_release.knockbackMultiplier | 1 | unconditional declared neutral |
| apply_projectile_charge_release.speedMultiplier | 1 | unconditional declared neutral |
| apply_projectile_charge_release.pauseLifetimeWhileCharging | False | unconditional declared neutral |
| set_projectile_beam_ramp.initialWidthMultiplier | 1 | unconditional declared neutral |
| set_projectile_beam_ramp.initialDamageMultiplier | 1 | unconditional declared neutral |
| set_projectile_beam_ramp.damageStartProgress | 0 | unconditional declared neutral |
| set_projectile_aim.turnOwner | False | unconditional declared neutral |
| attach_projectile.axisOffsetBlocks | 0 | unconditional declared neutral |
| attach_projectile.normalOffsetBlocks | 0 | unconditional declared neutral |
| set_projectile_return_trigger.onOwnerRelease | False | unconditional declared neutral |
| set_projectile_return_trigger.onTileCollision | False | unconditional declared neutral |
| set_projectile_return_trigger.disableTileCollisionOnReturn | False | unconditional declared neutral |
| set_projectile_rotation.offsetRadians | 0 | unconditional declared neutral |
| set_projectile_rotation.radiansPerSecond | 0 | {'targetKinds': (), 'paramEquals': (('mode', 'axis'), ('mode', 'velocity')), 'targetCapabilities': ()} |
| configure_item_stats.manaCost | 0 | unconditional declared neutral |
| configure_item_stats.manaCostInput | 'both' | unconditional declared neutral |
| configure_item_use.holdoutOffsetX | 0 | unconditional declared neutral |
| configure_item_use.holdoutOffsetY | 0 | unconditional declared neutral |
| apply_generated_buff_on_use.regenWhen | 'always' | unconditional declared neutral |
| apply_generated_buff_on_use.treasureWhen | 'always' | unconditional declared neutral |
| apply_generated_buff_on_use.miningSpeedMultiplier | 1 | unconditional declared neutral |
| apply_generated_buff_on_use.treasureSense | False | unconditional declared neutral |
| apply_generated_buff_on_use.moveSpeedBonusPercent | 0 | unconditional declared neutral |
| apply_generated_buff_on_use.jumpSpeedBonusBlocksPerSecond | 0.0 | unconditional declared neutral |
| apply_generated_buff_on_use.manaRegenBonusPoints | 0 | unconditional declared neutral |
| apply_generated_buff_on_use.lifeRegen | 0 | unconditional declared neutral |
| present_placed_item_sprite.pivotSpace | 'frame' | unconditional declared neutral |
| configure_accessory.regenWhen | 'always' | unconditional declared neutral |
| configure_accessory.treasureWhen | 'always' | unconditional declared neutral |
| configure_armor.regenWhen | 'always' | unconditional declared neutral |
| configure_armor.treasureWhen | 'always' | unconditional declared neutral |
| configure_spawn.count | 1 | {'targetKinds': ('child_projectile',), 'paramEquals': (), 'targetCapabilities': ()} |
| configure_spawn.spreadRadians | 0 | {'targetKinds': ('child_projectile',), 'paramEquals': (('count', 1),), 'targetCapabilities': ()} |
| set_projectile_turn_modifier.window.phase | 'always' | all timing absent: startDelaySeconds, durationSeconds, window |
| set_projectile_speed_modifier.window.phase | 'always' | all timing absent: startDelaySeconds, durationSeconds, window |
| set_projectile_homing_modifier.window.phase | 'always' | all timing absent: startDelaySeconds, durationSeconds, window |
| attract_npcs_while_active.window.phase | 'always' | all timing absent: startDelaySeconds, durationSeconds, window |
| set_projectile_collision.bounceCount | 0 | {'targetKinds': (), 'paramEquals': (('tileCollide', False),), 'targetCapabilities': ('move_boomerang', 'move_returning_glaive', 'move_flail_tether')} |
| set_projectile_collision.bounceSpeedRetention | 1 | unconditional declared neutral |
| channel_beam.manaPayment | 'initial_use_only' | unconditional declared neutral |
| channel_beam.initialDamageMultiplier | 1.0 | unconditional declared neutral |
| channel_beam.initialWidthMultiplier | 1.0 | unconditional declared neutral |
| channel_beam.damageStartProgress | 1.0 | unconditional declared neutral |
| channel_beam.raycastTiles | False | unconditional declared neutral |
| target_and_fire.count | 1 | unconditional declared neutral |
| target_and_fire.spreadRadians | 0.0 | unconditional declared neutral |
| target_and_fire.targetPolicy | 'distance_score' | unconditional declared neutral |
| target_and_fire.requireLineOfSight | False | unconditional declared neutral |
| target_and_fire.hardRange | False | unconditional declared neutral |
| spawn_entity_on_event.spreadRadians | 0 | {'targetKinds': (), 'paramEquals': (('count', 1),), 'targetCapabilities': ()} |
| apply_npc_effect_on_event.damagePerSecond | 0 | unconditional declared neutral |
| apply_npc_effect_on_event.defenseDelta | 0 | unconditional declared neutral |
| apply_npc_effect_on_event.contactDamageMultiplier | 1 | unconditional declared neutral |
| apply_npc_effect_on_event.velocityRetentionPerTick | 1 | unconditional declared neutral |
| apply_npc_effect_on_event.chancePercent | 100 | unconditional declared neutral |
| damage_nearby_on_event.maxTargets | 16 | unconditional declared neutral |

## Каноническая vocabulary

Точные event/structured/enum projections перечислены выше; технический alias сам по себе не запрещён. Синонимы spelling, напротив, не образуют дополнительный Author API. Старые `passive`, `drink`, `eat`, plural ammo spellings и `rogue` не принимаются. `throwing` сохранён только как точное каноническое отображение stable `DamageClass.Throwing`. `damageClass` имеет одну identity-форму: built-in token либо точный tModLoader `ModName/ClassName`, скопированный из loaded parent facts; псевдотокены `none`/`modded` и параллельное `damageClassFullName` запрещены.

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
- Author `apply_generated_buff_on_use.lifeRegen` задаёт вклад в HP/с (-50..60, шаг 0.5); compiler точно пишет старое целое `gameplay.generatedBuff.lifeRegen = value × 2`. Это вклад в engine stat до остальных эффектов, не обещание итогового лечения.
- `lifeRegen`/`regenWhen` и `treasureSense`/`treasureWhen` — единственные Author-входы для этих эффектов. Условия переводятся в typed native condition fields, не создают вторую stat-величину и сами по себе не являются эффектом. Nested `playerEffect.lifeRegen…`/`highlightTreasure` отвергаются.

<a id="player-text"></a>

### Описание игроку и engine units — разные представления

Lowery — технический lowering, не lore и не автор дополнительной механики. Author задаёт игровые расстояния в блоках, длительности в секундах, скорости в блоках/с. Меняется schema авторинга; сохранённый engine wire остаётся в прежних единицах. Canonical lowering выполняет объявленные проекции с учётом updatesPerTick именно затронутой сущности. Секунды разрешаются до ближайшего целого world tick, половина тика округляется вверх; неположенное обнуление ненулевого эффекта отклоняется, а не скрыто меняет механику. Pixel-labelled collision/sprite geometry и texture/UV units сохраняют своё объявленное пространство. Описание остаётся optional advisory: оно не требует нового отчёта и не запускает validator/Repair. Механическая истина — явно emitted runtimeProgram, а не красивое обещание в тексте.

Ниже — тот же model-facing текст из существующих prompt owners, а не отдельный prose-контракт. Initial Author получает единицы в `runtimeCapabilityContract.technicalNotes` и generation-only provider schema с кратким concept и разделёнными realization.description (применение) / selfEvaluation (отладка). Legacy acceptance и Repair сохраняют эти optional advisory поля; Repair — в `requiredJsonShape.realizationReplacement` и `runtimeExecutionTruth.units.playerFacingUnits`. Он передаётся в JSON messages при json_schema и json_object; schema annotations для этого не требуются. Если Repair добровольно возвращает описание, оно относится к post-merge программе; read-only context не даёт права менять frozen механику.

| optional prose | shared guidance |
|---|---|
| realization.description | Brief player-facing description of actual use, effects and conditions. String minLength=0, maxLength=4000 Unicode characters. |
| realization.playerExperience | Optional practical-use notes for the player. String minLength=0, maxLength=3000 Unicode characters. |

| единицы / scope | shared model-facing guide |
|---|---|
| nativeSourceReferences | Read-only native source values may be shared as {sourceSameAs:N}: read the complete value at nativeSourceFacts[N] in this same dossier, expanding recursively. These are exact repetitions, not inferred mechanics or Author values. Literal tooltips and accepted generatedParent packets stay inline. |
| time | Seconds resolve to the nearest world tick (60/s), half-tick ties upward. Positive effects that round to zero are rejected. immunity.localCooldown and projectile-update counters remain counts. |
| distance | World distances use blocks; Tiles also means blocks. 1 block = 16 world pixels. |
| speed | Physical speed/acceleration use blocks/s and blocks/s^2; angular rates use radians/s. The engine applies the target's updatesPerTick conversion. Retention/lerp/multiplier controls keep their declared per-update meaning. |
| scope | Author cards use player-facing units; raw parent facts and compiled wire retain engine units. Pixel geometry and normalized UV/grip coordinates retain their own units. Texture resolution is independent of rendered size and collision geometry. |
| vanillaScaleReference | Ordinary unmounted player: 20x42-pixel collision box; base run speed 11.25 blocks/s; normal jump initial upward velocity about 18.79 blocks/s. |
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
| damage_nearby_on_event | 10 |
| apply_npc_effect_on_event | 11 |
| reduce_healing_potion_cooldown_on_event | 12 |

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

## Добавление точной projection

Новая projection объявляется у существующего registry/ParamSpec owner и исполняется canonical lowerer/compiler. Нужны полный явный selector и единственный результат, receipt, source→wire identity, negative для contradictory-present и frozen Repair отсутствие. Полезные независимые параметры остаются у Author; старое ограничение compound controller не становится универсальным engine invariant новых primitives. Alias не даёт права добавлять meaningful defaults, выбирать channel/target/collision из имени или переписывать исторические saved items. После изменения owner обновить generated projections и пройти affected acceptance.
