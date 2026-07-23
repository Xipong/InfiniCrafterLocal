"""Canonical immutable Author engine function contracts.

This module owns provider grammar and prompt-visible function metadata. Specialized
compiler lowerers remain the only gameplay semantics owners.
"""
from __future__ import annotations

from types import MappingProxyType
from typing import Any

from infini_local.core.runtime_authoring.engine_param_boundaries import (
    ArmorSetBonusParamBoundary,
    BuffParamBoundary,
    EquipmentStatsParamBoundary,
    GeneratedBuffParamBoundary,
)
from infini_local.core.runtime_authoring.function_contract_types import (
    CompiledFieldSourceOverride,
    EngineFunctionContract,
    EngineParamContract,
    NestedWirePathContract,
    ParamValueKind,
    RepairGroupContract,
    WireObligation,
    validate_engine_function_contracts,
)

def _param(**kwargs: Any) -> EngineParamContract:
    return EngineParamContract(**kwargs)


ENGINE_FUNCTION_CONTRACTS: tuple[EngineFunctionContract, ...] = (
    EngineFunctionContract(
        name='set_item_stats',
        meaning='Base item stats and result type. Combat root executor also needs explicit shotCount and spreadRadians on its attack call. Reusable weapon/tool/armor/accessory must use consumable=false, maxStack=1, craftYield=1 and no consumption_behavior. Stack-spent weapons must use resultKind=consumable_weapon with consumable=true, maxStack>1, craftYield>0.',
        params=(
        _param(name='resultKind', prompt_description='weapon|ammo|consumable_weapon|tool|accessory|armor|potion|material|furniture|generic', value_kind=ParamValueKind.ENUM, example_value='weapon', compiled_fields=('resultKind',), wire_obligation=WireObligation.FINAL_WIRE, enum_values=('weapon', 'ammo', 'consumable_weapon', 'tool', 'accessory', 'armor', 'potion', 'material', 'furniture', 'generic')),
        _param(name='damageClass', prompt_description='generic|melee|melee_no_speed|ranged|magic|summon|summon_melee_speed|exact ModName/DamageClassName', value_kind=ParamValueKind.STRING, example_value='generic', compiled_fields=('damageClass',), wire_obligation=WireObligation.FINAL_WIRE, string_pattern='^(?:generic|melee|melee_no_speed|ranged|magic|summon|summon_melee_speed|[A-Za-z][A-Za-z0-9_]*/[A-Za-z][A-Za-z0-9_]*)$'),
        _param(name='damage', prompt_description='0..cap', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('damage',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='useTimeTicks', prompt_description='10..150', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('useTimeTicks',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='useAnimationTicks', prompt_description='6..150; =useTime one action/click; >useTime may repeat', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('useAnimationTicks',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='knockback', prompt_description='0..12', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('knockback',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='manaCost', prompt_description='0..80', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('manaCost',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='autoReuse', prompt_description='bool', value_kind=ParamValueKind.BOOLEAN, example_value=False, compiled_fields=('autoReuse',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='maxStack', prompt_description='1 gear; 25+ stacks', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('maxStack',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='craftYield', prompt_description='output count', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('craftYield',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='healLife', prompt_description='potion only', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('healLife',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='healMana', prompt_description='potion only', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('healMana',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='buffType', prompt_description='non-negative integer Terraria buff type ID; omit when generatedBuff owns the effect', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('buffType',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='buffTime', prompt_description='ticks paired with buffType', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('buffTime',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='pickPower', prompt_description='tool only', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('pickPower',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='axePower', prompt_description='tool only', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('axePower',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='hammerPower', prompt_description='tool only', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('hammerPower',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='ammoFor', prompt_description='empty custom; arrow|bullet vanilla ammo identity', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=('ammoFor',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='armorSlot', prompt_description='head|body|legs for armor', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=('slot',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='defense', prompt_description='armor 0..80', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('defense',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='consumable', prompt_description='true stack-spent; false gear', value_kind=ParamValueKind.BOOLEAN, example_value=False, compiled_fields=('consumable',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='rarity', prompt_description='-1..12', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('rarity',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='value', prompt_description='>=0', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('value',), wire_obligation=WireObligation.FINAL_WIRE),
        ),
        root_executor=False,
        requires_root_executor=False,
        allowed_result_kinds=(),
        repair_groups=(),
    ),
    EngineFunctionContract(
        name='shoot_projectile',
        meaning='Low-level root executor; runtimeFamily required. Exactly one root executor owns a use, but delivery=swing with runtimeFamily=shoot keeps the item/tool body hitbox and also emits the projectile.',
        params=(
        _param(name='delivery', prompt_description='swing|thrust|flail|yoyo|whip|shoot|cast|throw|summon; pair with runtimeFamily', value_kind=ParamValueKind.ENUM, example_value='swing', compiled_fields=('delivery',), wire_obligation=WireObligation.FINAL_WIRE, enum_values=('swing', 'thrust', 'flail', 'yoyo', 'whip', 'shoot', 'cast', 'throw', 'summon')),
        _param(name='movement', prompt_description='straight|slow_homing|gravity_arc|drift|orbit|boomerang|bounce|sine_homing|phase|accelerate|spiral|vortex_orb|blackhole_pull|proximity_missile|returning_glaive|expanding_wave|flail_tether|yoyo_hover|whip_lash; phase passes tiles', value_kind=ParamValueKind.ENUM, example_value='straight', compiled_fields=('movement',), wire_obligation=WireObligation.FINAL_WIRE, enum_values=('straight', 'slow_homing', 'gravity_arc', 'drift', 'orbit', 'boomerang', 'bounce', 'sine_homing', 'phase', 'accelerate', 'spiral', 'vortex_orb', 'blackhole_pull', 'proximity_missile', 'returning_glaive', 'expanding_wave', 'flail_tether', 'yoyo_hover', 'whip_lash')),
        _param(name='speed', prompt_description='3..18', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('speed',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='rangeTiles', prompt_description='4..120', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('range', 'rangeTiles'), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='lifetimeTicks', prompt_description='25..900', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('lifetime', 'lifetimeTicks'), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='shotCount', prompt_description='1..8 simultaneous', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('shotCount',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='spreadRadians', prompt_description='0..0.75', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('spreadRadians',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='pierce', prompt_description='-1=infinite hits; 0 or 1=one target total; 2..10=total NPC hits', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('pierce',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='extraUpdates', prompt_description='0..3', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('extraUpdates',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='homingStrength', prompt_description='0..1', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('homingStrength',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='beamWidthPx', prompt_description='2..96', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('beamWidthPx',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='beamChargeTicks', prompt_description='0..300', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('beamChargeTicks',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='chargeTicks', prompt_description='1..300', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('chargeTicks',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='chargePowerMultiplier', prompt_description='1..3', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('chargePowerMultiplier',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='delayTicks', prompt_description='0..300; overhead_barrage 0=immediate', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('delayTicks',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='immunityCooldown', prompt_description='4..60', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('immunityCooldown',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='runtimeFamily', prompt_description='swing|thrust|returning|flail|yoyo|whip|shoot|cast|beam|charge_release|overhead_barrage|throw|summon; sentry uses deploy_sentry', value_kind=ParamValueKind.ENUM, example_value='swing', compiled_fields=('runtimeFamily',), wire_obligation=WireObligation.FINAL_WIRE, enum_values=('swing', 'thrust', 'returning', 'flail', 'yoyo', 'whip', 'shoot', 'cast', 'beam', 'charge_release', 'overhead_barrage', 'throw', 'summon')),
        _param(name='weaponFamily', prompt_description='exact optional', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=('weaponFamily',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='projectileFamily', prompt_description='visual form', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=('projectileFamily',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='projectileShape', prompt_description='visual body', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=('projectileShape',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='projectileMotion', prompt_description='visual motion', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=('projectileMotion',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='projectileTrail', prompt_description='visual trail', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=('projectileTrail',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='projectileImpact', prompt_description='visual impact', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=('projectileImpact',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='effect', prompt_description='Shared exact executor effect token.', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=('effect',), wire_obligation=WireObligation.FINAL_WIRE, function_card_visible=False, prompt_group='root_executor'),
        _param(name='secondaryDamageMultiplier', prompt_description='Shared secondary damage multiplier.', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('secondaryDamageMultiplier',), wire_obligation=WireObligation.FINAL_WIRE, function_card_visible=False, prompt_group='root_executor'),
        _param(name='secondaryLifetimeTicks', prompt_description='Shared secondary lifetime in ticks.', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('secondaryLifetimeTicks',), wire_obligation=WireObligation.FINAL_WIRE, function_card_visible=False, prompt_group='root_executor'),
        _param(name='soundImpactCatalogId', prompt_description='Exact impact sound catalog id.', value_kind=ParamValueKind.ENUM, example_value='impact_blade', compiled_fields=('soundImpactCatalogId',), wire_obligation=WireObligation.FINAL_WIRE, enum_values=('impact_blade', 'impact_bubble', 'impact_construct', 'impact_creature_meow', 'impact_crystal', 'impact_earth', 'impact_electric', 'impact_explosion', 'impact_fire', 'impact_frost', 'impact_harpoon', 'impact_heal', 'impact_heavy', 'impact_inferno', 'impact_insect', 'impact_laser', 'impact_magic', 'impact_meteor', 'impact_nail', 'impact_nature', 'impact_portal', 'impact_rocket', 'impact_shadow', 'impact_slime', 'impact_soft', 'impact_spectral', 'impact_star', 'impact_summon', 'impact_toxic', 'impact_void', 'impact_water', 'impact_wind_vortex'), function_card_visible=False, prompt_group='root_executor'),
        _param(name='soundPitch', prompt_description='Authored sound pitch.', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('soundPitch',), wire_obligation=WireObligation.FINAL_WIRE, function_card_visible=False, prompt_group='root_executor'),
        _param(name='soundPitchVariance', prompt_description='Authored sound pitch variance.', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('soundPitchVariance',), wire_obligation=WireObligation.FINAL_WIRE, function_card_visible=False, prompt_group='root_executor'),
        _param(name='soundUseCatalogId', prompt_description='Exact use sound catalog id.', value_kind=ParamValueKind.ENUM, example_value='bow_release', compiled_fields=('soundUseCatalogId',), wire_obligation=WireObligation.FINAL_WIRE, enum_values=('bow_release', 'bow_volley', 'creature_meow', 'dart_pistol', 'dart_rifle', 'firearm_burst', 'firearm_clockwork', 'firearm_light', 'flail_chain', 'flame_stream', 'insect_swarm', 'laser_heavy', 'laser_machine', 'laser_short', 'laser_space', 'laser_zap', 'launcher_grenade', 'launcher_rocket', 'magic_bolt', 'magic_bubble', 'magic_cosmic', 'magic_crystal_burst', 'magic_earth', 'magic_electric', 'magic_frost', 'magic_gem', 'magic_harp', 'magic_inferno', 'magic_meteor', 'magic_phase', 'magic_shadow', 'magic_spectral', 'magic_star', 'magic_stream', 'magic_toxic', 'magic_void', 'magic_water', 'magic_wind_vortex', 'melee_energy_slash', 'melee_heavy', 'melee_prismatic_shred', 'melee_swing', 'melee_thrust', 'nailgun', 'potion_use', 'returning_boomerang', 'shotgun_heavy', 'shotgun_tactical', 'sniper_heavy', 'summon_fiery', 'summon_general', 'summon_insect', 'summon_lightning', 'summon_mechanical', 'summon_portal', 'summon_sentry', 'summon_skittering', 'throw_light', 'whip_lash', 'yoyo_launch'), function_card_visible=False, prompt_group='root_executor'),
        _param(name='soundVolume', prompt_description='Authored sound volume.', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('soundVolume',), wire_obligation=WireObligation.FINAL_WIRE, function_card_visible=False, prompt_group='root_executor'),
        _param(name='useAnimationTicks', prompt_description='Shared root item animation time in ticks.', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('useAnimationTicks',), wire_obligation=WireObligation.FINAL_WIRE, function_card_visible=False, prompt_group='root_executor'),
        _param(name='useTimeTicks', prompt_description='Shared root item use time in ticks.', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('useTimeTicks',), wire_obligation=WireObligation.FINAL_WIRE, function_card_visible=False, prompt_group='root_executor'),
        ),
        root_executor=True,
        requires_root_executor=False,
        allowed_result_kinds=(),
        repair_groups=(
            RepairGroupContract(members=('delivery', 'movement', 'runtimeFamily'), policy_owner='infini_local.core.runtime_authoring.schema.repair_param_allowed_combinations'),
        ),
        compiled_source_overrides=(CompiledFieldSourceOverride(compiled_field='ammoFor', source_paths=('ammoFor',)), CompiledFieldSourceOverride(compiled_field='channelUse', source_paths=('channelUse',)), CompiledFieldSourceOverride(compiled_field='disableItemMeleeHitbox', source_paths=('disableItemMeleeHitbox',)), CompiledFieldSourceOverride(compiled_field='hideUseGraphic', source_paths=('hideUseGraphic',)), CompiledFieldSourceOverride(compiled_field='onHit', source_paths=('onHit',)), CompiledFieldSourceOverride(compiled_field='ownerHitCheck', source_paths=('ownerHitCheck',)), CompiledFieldSourceOverride(compiled_field='secondaryProjectileShape', source_paths=('secondaryProjectileShape',)), CompiledFieldSourceOverride(compiled_field='sentryAttackIntervalTicks', source_paths=('sentryAttackIntervalTicks', 'attackIntervalTicks')), CompiledFieldSourceOverride(compiled_field='sentryLifetimeTicks', source_paths=('sentryLifetimeTicks', 'helperLifetimeTicks')), CompiledFieldSourceOverride(compiled_field='sentryPlacement', source_paths=('sentryPlacement', 'placement')), CompiledFieldSourceOverride(compiled_field='sentryTargetRangeTiles', source_paths=('sentryTargetRangeTiles', 'targetRangeTiles')), CompiledFieldSourceOverride(compiled_field='useStyleCode', source_paths=('useStyleCode',)),),
    ),
    EngineFunctionContract(
        name='perform_melee_attack',
        meaning='Body-owned melee/tool swing or explicit projectile-owned melee-family executor.',
        params=(
        _param(name='family', prompt_description='broadsword|sword|pickaxe|axe|hammer|shortsword|rapier|dagger|spear|lance|pike|trident|halberd|naginata|jousting_lance|boomerang|chakram|flail|mace|anchor|yoyo|whip', value_kind=ParamValueKind.ENUM, example_value='broadsword', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, enum_values=('broadsword', 'sword', 'pickaxe', 'axe', 'hammer', 'shortsword', 'rapier', 'dagger', 'spear', 'lance', 'pike', 'trident', 'halberd', 'naginata', 'jousting_lance', 'boomerang', 'chakram', 'flail', 'mace', 'anchor', 'yoyo', 'whip')),
        _param(name='runtimeFamily', prompt_description='omit; derived', value_kind=ParamValueKind.ENUM, example_value='swing', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, enum_values=('swing', 'thrust', 'returning', 'flail', 'yoyo', 'whip', 'shoot', 'cast', 'beam', 'charge_release', 'overhead_barrage', 'throw', 'summon')),
        _param(name='speed', prompt_description='3..18', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='rangeTiles', prompt_description='2..80', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='lifetimeTicks', prompt_description='10..900', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='pierce', prompt_description='-1 infinite; 0/1 one total; 2..10 total', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='useTimeTicks', prompt_description='10..150', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, prompt_group='root_executor'),
        _param(name='shotCount', prompt_description='1..8 simultaneous emitted; not swing count', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='spreadRadians', prompt_description='0..0.75', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='projectileShape', prompt_description='body', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='projectileMotion', prompt_description='motion', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='projectileTrail', prompt_description='trail', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='projectileImpact', prompt_description='impact', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='effect', prompt_description='Shared exact executor effect token.', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, function_card_visible=False, prompt_group='root_executor'),
        _param(name='secondaryDamageMultiplier', prompt_description='Shared secondary damage multiplier.', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, function_card_visible=False, prompt_group='root_executor'),
        _param(name='secondaryLifetimeTicks', prompt_description='Shared secondary lifetime in ticks.', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, function_card_visible=False, prompt_group='root_executor'),
        _param(name='soundImpactCatalogId', prompt_description='Exact impact sound catalog id.', value_kind=ParamValueKind.ENUM, example_value='impact_blade', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, enum_values=('impact_blade', 'impact_bubble', 'impact_construct', 'impact_creature_meow', 'impact_crystal', 'impact_earth', 'impact_electric', 'impact_explosion', 'impact_fire', 'impact_frost', 'impact_harpoon', 'impact_heal', 'impact_heavy', 'impact_inferno', 'impact_insect', 'impact_laser', 'impact_magic', 'impact_meteor', 'impact_nail', 'impact_nature', 'impact_portal', 'impact_rocket', 'impact_shadow', 'impact_slime', 'impact_soft', 'impact_spectral', 'impact_star', 'impact_summon', 'impact_toxic', 'impact_void', 'impact_water', 'impact_wind_vortex'), function_card_visible=False, prompt_group='root_executor'),
        _param(name='soundPitch', prompt_description='Authored sound pitch.', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, function_card_visible=False, prompt_group='root_executor'),
        _param(name='soundPitchVariance', prompt_description='Authored sound pitch variance.', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, function_card_visible=False, prompt_group='root_executor'),
        _param(name='soundUseCatalogId', prompt_description='Exact use sound catalog id.', value_kind=ParamValueKind.ENUM, example_value='bow_release', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, enum_values=('bow_release', 'bow_volley', 'creature_meow', 'dart_pistol', 'dart_rifle', 'firearm_burst', 'firearm_clockwork', 'firearm_light', 'flail_chain', 'flame_stream', 'insect_swarm', 'laser_heavy', 'laser_machine', 'laser_short', 'laser_space', 'laser_zap', 'launcher_grenade', 'launcher_rocket', 'magic_bolt', 'magic_bubble', 'magic_cosmic', 'magic_crystal_burst', 'magic_earth', 'magic_electric', 'magic_frost', 'magic_gem', 'magic_harp', 'magic_inferno', 'magic_meteor', 'magic_phase', 'magic_shadow', 'magic_spectral', 'magic_star', 'magic_stream', 'magic_toxic', 'magic_void', 'magic_water', 'magic_wind_vortex', 'melee_energy_slash', 'melee_heavy', 'melee_prismatic_shred', 'melee_swing', 'melee_thrust', 'nailgun', 'potion_use', 'returning_boomerang', 'shotgun_heavy', 'shotgun_tactical', 'sniper_heavy', 'summon_fiery', 'summon_general', 'summon_insect', 'summon_lightning', 'summon_mechanical', 'summon_portal', 'summon_sentry', 'summon_skittering', 'throw_light', 'whip_lash', 'yoyo_launch'), function_card_visible=False, prompt_group='root_executor'),
        _param(name='soundVolume', prompt_description='Authored sound volume.', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, function_card_visible=False, prompt_group='root_executor'),
        _param(name='useAnimationTicks', prompt_description='Shared root item animation time in ticks.', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, function_card_visible=False, prompt_group='root_executor'),
        ),
        root_executor=True,
        requires_root_executor=False,
        allowed_result_kinds=(),
        repair_groups=(),
    ),
    EngineFunctionContract(
        name='fire_ranged_weapon',
        meaning='Ranged executor; charge_release holds, overhead_barrage spawns above target.',
        params=(
        _param(name='family', prompt_description='bow|repeater|gun|shotgun|launcher|rocket_launcher|dart|blowgun|harpoon|charge_release|overhead_barrage', value_kind=ParamValueKind.ENUM, example_value='bow', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, enum_values=('bow', 'repeater', 'gun', 'shotgun', 'launcher', 'rocket_launcher', 'dart', 'blowgun', 'harpoon', 'charge_release', 'overhead_barrage')),
        _param(name='ammoFor', prompt_description='empty custom; arrow|bullet consume vanilla ammo', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='movement', prompt_description='straight|gravity_arc|slow_homing|phase|proximity_missile|boomerang; phase passes tiles', value_kind=ParamValueKind.ENUM, example_value='straight', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, enum_values=('straight', 'gravity_arc', 'slow_homing', 'phase', 'proximity_missile', 'boomerang')),
        _param(name='speed', prompt_description='3..18', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='rangeTiles', prompt_description='10..120', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='lifetimeTicks', prompt_description='25..900', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='shotCount', prompt_description='1..8 simultaneous', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='spreadRadians', prompt_description='0..0.75', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='pierce', prompt_description='-1 infinite; 0/1 one total; 2..10 total', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='delayTicks', prompt_description='0..300; barrage 0=immediate', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='secondaryDamageMultiplier', prompt_description='0.01..1 barrage damage', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, prompt_group='root_executor'),
        _param(name='secondaryLifetimeTicks', prompt_description='5..180 barrage life', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, prompt_group='root_executor'),
        _param(name='projectileFamily', prompt_description='visual form; launcher+empty=custom rocket', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='chargeTicks', prompt_description='1..300 charge_release hold', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='chargePowerMultiplier', prompt_description='1..3 max power', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='projectileShape', prompt_description='body', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='projectileMotion', prompt_description='motion', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='projectileTrail', prompt_description='trail', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='projectileImpact', prompt_description='impact', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='effect', prompt_description='Shared exact executor effect token.', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, function_card_visible=False, prompt_group='root_executor'),
        _param(name='soundImpactCatalogId', prompt_description='Exact impact sound catalog id.', value_kind=ParamValueKind.ENUM, example_value='impact_blade', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, enum_values=('impact_blade', 'impact_bubble', 'impact_construct', 'impact_creature_meow', 'impact_crystal', 'impact_earth', 'impact_electric', 'impact_explosion', 'impact_fire', 'impact_frost', 'impact_harpoon', 'impact_heal', 'impact_heavy', 'impact_inferno', 'impact_insect', 'impact_laser', 'impact_magic', 'impact_meteor', 'impact_nail', 'impact_nature', 'impact_portal', 'impact_rocket', 'impact_shadow', 'impact_slime', 'impact_soft', 'impact_spectral', 'impact_star', 'impact_summon', 'impact_toxic', 'impact_void', 'impact_water', 'impact_wind_vortex'), function_card_visible=False, prompt_group='root_executor'),
        _param(name='soundPitch', prompt_description='Authored sound pitch.', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, function_card_visible=False, prompt_group='root_executor'),
        _param(name='soundPitchVariance', prompt_description='Authored sound pitch variance.', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, function_card_visible=False, prompt_group='root_executor'),
        _param(name='soundUseCatalogId', prompt_description='Exact use sound catalog id.', value_kind=ParamValueKind.ENUM, example_value='bow_release', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, enum_values=('bow_release', 'bow_volley', 'creature_meow', 'dart_pistol', 'dart_rifle', 'firearm_burst', 'firearm_clockwork', 'firearm_light', 'flail_chain', 'flame_stream', 'insect_swarm', 'laser_heavy', 'laser_machine', 'laser_short', 'laser_space', 'laser_zap', 'launcher_grenade', 'launcher_rocket', 'magic_bolt', 'magic_bubble', 'magic_cosmic', 'magic_crystal_burst', 'magic_earth', 'magic_electric', 'magic_frost', 'magic_gem', 'magic_harp', 'magic_inferno', 'magic_meteor', 'magic_phase', 'magic_shadow', 'magic_spectral', 'magic_star', 'magic_stream', 'magic_toxic', 'magic_void', 'magic_water', 'magic_wind_vortex', 'melee_energy_slash', 'melee_heavy', 'melee_prismatic_shred', 'melee_swing', 'melee_thrust', 'nailgun', 'potion_use', 'returning_boomerang', 'shotgun_heavy', 'shotgun_tactical', 'sniper_heavy', 'summon_fiery', 'summon_general', 'summon_insect', 'summon_lightning', 'summon_mechanical', 'summon_portal', 'summon_sentry', 'summon_skittering', 'throw_light', 'whip_lash', 'yoyo_launch'), function_card_visible=False, prompt_group='root_executor'),
        _param(name='soundVolume', prompt_description='Authored sound volume.', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, function_card_visible=False, prompt_group='root_executor'),
        _param(name='useAnimationTicks', prompt_description='Shared root item animation time in ticks.', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, function_card_visible=False, prompt_group='root_executor'),
        _param(name='useTimeTicks', prompt_description='Shared root item use time in ticks.', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, function_card_visible=False, prompt_group='root_executor'),
        ),
        root_executor=True,
        requires_root_executor=False,
        allowed_result_kinds=(),
        repair_groups=(),
    ),
    EngineFunctionContract(
        name='cast_magic_weapon',
        meaning='Magic executor; beam channels, charge_release holds, overhead_barrage spawns above target.',
        params=(
        _param(name='family', prompt_description='staff|wand|rod|book|magic_gun|channelled_beam|charge_release|overhead_barrage|other exact family', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='projectileFamily', prompt_description='spear|bolt|beam|orb|etc', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='movement', prompt_description='straight|slow_homing|gravity_arc|phase|accelerate|vortex_orb|blackhole_pull|expanding_wave', value_kind=ParamValueKind.ENUM, example_value='straight', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, enum_values=('straight', 'slow_homing', 'gravity_arc', 'phase', 'accelerate', 'vortex_orb', 'blackhole_pull', 'expanding_wave')),
        _param(name='speed', prompt_description='3..18', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='rangeTiles', prompt_description='8..120', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='chargePowerMultiplier', prompt_description='1..3 charge_release', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='lifetimeTicks', prompt_description='25..900', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='shotCount', prompt_description='1..8 simultaneous', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='spreadRadians', prompt_description='0..0.75', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='pierce', prompt_description='-1 infinite; 0/1 one total; 2..10 total', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='homingStrength', prompt_description='0..1', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='beamWidthPx', prompt_description='2..96', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='beamChargeTicks', prompt_description='0..300; 0=full immediately', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='chargeTicks', prompt_description='1..300 charge_release', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='delayTicks', prompt_description='0..300; barrage 0=immediate', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='secondaryDamageMultiplier', prompt_description='0.01..1 barrage damage', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, prompt_group='root_executor'),
        _param(name='secondaryLifetimeTicks', prompt_description='5..180 barrage life', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, prompt_group='root_executor'),
        _param(name='immunityCooldown', prompt_description='4..60', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='projectileShape', prompt_description='body', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='projectileMotion', prompt_description='motion', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='projectileTrail', prompt_description='trail', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='projectileImpact', prompt_description='impact', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='effect', prompt_description='Shared exact executor effect token.', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, function_card_visible=False, prompt_group='root_executor'),
        _param(name='soundImpactCatalogId', prompt_description='Exact impact sound catalog id.', value_kind=ParamValueKind.ENUM, example_value='impact_blade', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, enum_values=('impact_blade', 'impact_bubble', 'impact_construct', 'impact_creature_meow', 'impact_crystal', 'impact_earth', 'impact_electric', 'impact_explosion', 'impact_fire', 'impact_frost', 'impact_harpoon', 'impact_heal', 'impact_heavy', 'impact_inferno', 'impact_insect', 'impact_laser', 'impact_magic', 'impact_meteor', 'impact_nail', 'impact_nature', 'impact_portal', 'impact_rocket', 'impact_shadow', 'impact_slime', 'impact_soft', 'impact_spectral', 'impact_star', 'impact_summon', 'impact_toxic', 'impact_void', 'impact_water', 'impact_wind_vortex'), function_card_visible=False, prompt_group='root_executor'),
        _param(name='soundPitch', prompt_description='Authored sound pitch.', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, function_card_visible=False, prompt_group='root_executor'),
        _param(name='soundPitchVariance', prompt_description='Authored sound pitch variance.', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, function_card_visible=False, prompt_group='root_executor'),
        _param(name='soundUseCatalogId', prompt_description='Exact use sound catalog id.', value_kind=ParamValueKind.ENUM, example_value='bow_release', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, enum_values=('bow_release', 'bow_volley', 'creature_meow', 'dart_pistol', 'dart_rifle', 'firearm_burst', 'firearm_clockwork', 'firearm_light', 'flail_chain', 'flame_stream', 'insect_swarm', 'laser_heavy', 'laser_machine', 'laser_short', 'laser_space', 'laser_zap', 'launcher_grenade', 'launcher_rocket', 'magic_bolt', 'magic_bubble', 'magic_cosmic', 'magic_crystal_burst', 'magic_earth', 'magic_electric', 'magic_frost', 'magic_gem', 'magic_harp', 'magic_inferno', 'magic_meteor', 'magic_phase', 'magic_shadow', 'magic_spectral', 'magic_star', 'magic_stream', 'magic_toxic', 'magic_void', 'magic_water', 'magic_wind_vortex', 'melee_energy_slash', 'melee_heavy', 'melee_prismatic_shred', 'melee_swing', 'melee_thrust', 'nailgun', 'potion_use', 'returning_boomerang', 'shotgun_heavy', 'shotgun_tactical', 'sniper_heavy', 'summon_fiery', 'summon_general', 'summon_insect', 'summon_lightning', 'summon_mechanical', 'summon_portal', 'summon_sentry', 'summon_skittering', 'throw_light', 'whip_lash', 'yoyo_launch'), function_card_visible=False, prompt_group='root_executor'),
        _param(name='soundVolume', prompt_description='Authored sound volume.', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, function_card_visible=False, prompt_group='root_executor'),
        _param(name='useAnimationTicks', prompt_description='Shared root item animation time in ticks.', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, function_card_visible=False, prompt_group='root_executor'),
        _param(name='useTimeTicks', prompt_description='Shared root item use time in ticks.', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, function_card_visible=False, prompt_group='root_executor'),
        ),
        root_executor=True,
        requires_root_executor=False,
        allowed_result_kinds=(),
        repair_groups=(),
    ),
    EngineFunctionContract(
        name='deploy_sentry',
        meaning='Bounded Terraria sentry at cursor; stationary, targets NPCs, fires generated shots; not a minion.',
        params=(
        _param(name='placement', prompt_description='grounded|floating', value_kind=ParamValueKind.ENUM, example_value='grounded', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, enum_values=('grounded', 'floating')),
        _param(name='attackIntervalTicks', prompt_description='12..180 ticks/volley', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='targetRangeTiles', prompt_description='8..60', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='helperLifetimeTicks', prompt_description='120..36000 root', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='shotCount', prompt_description='1..4 simultaneous/volley', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='speed', prompt_description='3..18', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='spreadRadians', prompt_description='0..0.75', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='pierce', prompt_description='-1 infinite; 0/1 one total; 2..10 total', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='movement', prompt_description='shot movement', value_kind=ParamValueKind.ENUM, example_value='accelerate', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, enum_values=('accelerate', 'blackhole_pull', 'boomerang', 'bounce', 'drift', 'expanding_wave', 'flail_tether', 'gravity_arc', 'orbit', 'phase', 'proximity_missile', 'returning_glaive', 'sine_homing', 'slow_homing', 'spiral', 'straight', 'vortex_orb', 'whip_lash', 'yoyo_hover')),
        _param(name='effect', prompt_description='shot effect', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, prompt_group='root_executor'),
        _param(name='onHit', prompt_description='none|non-child effect only', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='projectileShape', prompt_description='sentry body', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='secondaryProjectileShape', prompt_description='shot body', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='secondaryLifetimeTicks', prompt_description='5..180 shot lifetime; not sentry lifetime', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, prompt_group='root_executor'),
        _param(name='secondaryDamageMultiplier', prompt_description='Shared secondary damage multiplier.', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, function_card_visible=False, prompt_group='root_executor'),
        _param(name='soundImpactCatalogId', prompt_description='Exact impact sound catalog id.', value_kind=ParamValueKind.ENUM, example_value='impact_blade', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, enum_values=('impact_blade', 'impact_bubble', 'impact_construct', 'impact_creature_meow', 'impact_crystal', 'impact_earth', 'impact_electric', 'impact_explosion', 'impact_fire', 'impact_frost', 'impact_harpoon', 'impact_heal', 'impact_heavy', 'impact_inferno', 'impact_insect', 'impact_laser', 'impact_magic', 'impact_meteor', 'impact_nail', 'impact_nature', 'impact_portal', 'impact_rocket', 'impact_shadow', 'impact_slime', 'impact_soft', 'impact_spectral', 'impact_star', 'impact_summon', 'impact_toxic', 'impact_void', 'impact_water', 'impact_wind_vortex'), function_card_visible=False, prompt_group='root_executor'),
        _param(name='soundPitch', prompt_description='Authored sound pitch.', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, function_card_visible=False, prompt_group='root_executor'),
        _param(name='soundPitchVariance', prompt_description='Authored sound pitch variance.', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, function_card_visible=False, prompt_group='root_executor'),
        _param(name='soundUseCatalogId', prompt_description='Exact use sound catalog id.', value_kind=ParamValueKind.ENUM, example_value='bow_release', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, enum_values=('bow_release', 'bow_volley', 'creature_meow', 'dart_pistol', 'dart_rifle', 'firearm_burst', 'firearm_clockwork', 'firearm_light', 'flail_chain', 'flame_stream', 'insect_swarm', 'laser_heavy', 'laser_machine', 'laser_short', 'laser_space', 'laser_zap', 'launcher_grenade', 'launcher_rocket', 'magic_bolt', 'magic_bubble', 'magic_cosmic', 'magic_crystal_burst', 'magic_earth', 'magic_electric', 'magic_frost', 'magic_gem', 'magic_harp', 'magic_inferno', 'magic_meteor', 'magic_phase', 'magic_shadow', 'magic_spectral', 'magic_star', 'magic_stream', 'magic_toxic', 'magic_void', 'magic_water', 'magic_wind_vortex', 'melee_energy_slash', 'melee_heavy', 'melee_prismatic_shred', 'melee_swing', 'melee_thrust', 'nailgun', 'potion_use', 'returning_boomerang', 'shotgun_heavy', 'shotgun_tactical', 'sniper_heavy', 'summon_fiery', 'summon_general', 'summon_insect', 'summon_lightning', 'summon_mechanical', 'summon_portal', 'summon_sentry', 'summon_skittering', 'throw_light', 'whip_lash', 'yoyo_launch'), function_card_visible=False, prompt_group='root_executor'),
        _param(name='soundVolume', prompt_description='Authored sound volume.', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, function_card_visible=False, prompt_group='root_executor'),
        _param(name='useAnimationTicks', prompt_description='Shared root item animation time in ticks.', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, function_card_visible=False, prompt_group='root_executor'),
        _param(name='useTimeTicks', prompt_description='Shared root item use time in ticks.', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, function_card_visible=False, prompt_group='root_executor'),
        ),
        root_executor=True,
        requires_root_executor=False,
        allowed_result_kinds=(),
        repair_groups=(),
    ),
    EngineFunctionContract(
        name='spawn_temporary_helper_projectile',
        meaning='Not a persistent Terraria minion or sentry; short orbit/drift only.',
        params=(
        _param(name='family', prompt_description='drone|orbiter|pet_attack|temporary_turret|wisp', value_kind=ParamValueKind.ENUM, example_value='drone', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, enum_values=('drone', 'orbiter', 'pet_attack', 'temporary_turret', 'wisp')),
        _param(name='movement', prompt_description='orbit|slow_homing|drift|straight', value_kind=ParamValueKind.ENUM, example_value='orbit', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, enum_values=('orbit', 'slow_homing', 'drift', 'straight')),
        _param(name='speed', prompt_description='3..18', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='rangeTiles', prompt_description='8..120 target/orbit radius', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='lifetimeTicks', prompt_description='25..900 ticks; 60=1s', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='shotCount', prompt_description='1..4 simultaneous helpers', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='spreadRadians', prompt_description='0..0.75 total helper spread', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='pierce', prompt_description='0/1 one hit; 2..10 total hits', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='projectileShape', prompt_description='temporary helper body', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        ),
        root_executor=False,
        requires_root_executor=False,
        allowed_result_kinds=(),
        repair_groups=(),
    ),
    EngineFunctionContract(
        name='spawn_secondary_projectiles',
        meaning='Real secondary damaging projectiles, not VFX motes. Use only for actual child hits.',
        params=(
        _param(name='trigger', prompt_description='on_expire|on_hit', value_kind=ParamValueKind.ENUM, example_value='on_expire', compiled_fields=('secondaryTrigger',), wire_obligation=WireObligation.FINAL_WIRE, enum_values=('on_expire', 'on_hit')),
        _param(name='count', prompt_description='0 off; 1..8 children', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('maxChildProjectiles', 'splitCount'), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='damageMultiplier', prompt_description='0..1 parent damage', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('secondaryDamageMultiplier',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='spreadRadians', prompt_description='0..1.2 total spread', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('secondarySpreadRadians',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='lifetimeTicks', prompt_description='5..180 child ticks', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('secondaryLifetimeTicks',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='sameTargetBias', prompt_description='0..1 chance aim at hit target', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('sameTargetBias',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='projectileShape', prompt_description='optional child visual', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=('secondaryProjectileShape',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='material', prompt_description='optional child visual', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=('secondaryMaterial',), wire_obligation=WireObligation.FINAL_WIRE),
        ),
        root_executor=False,
        requires_root_executor=False,
        allowed_result_kinds=(),
        repair_groups=(),
        compiled_source_overrides=(CompiledFieldSourceOverride(compiled_field='maxChildProjectiles', source_paths=('maxChildProjectiles', 'count')), CompiledFieldSourceOverride(compiled_field='primaryColorName', source_paths=('primaryColorName',)), CompiledFieldSourceOverride(compiled_field='secondaryDamageMultiplier', source_paths=('secondaryDamageMultiplier', 'damageMultiplier')), CompiledFieldSourceOverride(compiled_field='secondaryLifetimeTicks', source_paths=('secondaryLifetimeTicks', 'lifetimeTicks')), CompiledFieldSourceOverride(compiled_field='secondaryMaterial', source_paths=('secondaryMaterial', 'material')), CompiledFieldSourceOverride(compiled_field='secondaryProjectileShape', source_paths=('secondaryProjectileShape', 'projectileShape')), CompiledFieldSourceOverride(compiled_field='secondarySpreadRadians', source_paths=('secondarySpreadRadians', 'spreadRadians')), CompiledFieldSourceOverride(compiled_field='splitCount', source_paths=('splitCount', 'count')),),
    ),
    EngineFunctionContract(
        name='apply_on_hit_effect',
        meaning='Real on-hit gameplay: debuffs, bursts, chained hits, child-producing effects, pull/heal/lifesteal. Visual-only impact belongs in spawn_contact_particles.',
        params=(
        _param(name='onHit', prompt_description='none|burst|split|chain|burn|frostburn|poison|shadowflame|bleed|starburst|overhead_barrage|aura_pulse|spore_cloud|mini_missiles|vortex_spawn|blackhole|radial_beams|lightning_arc|heal|lifesteal', value_kind=ParamValueKind.ENUM, example_value='none', compiled_fields=('onHit',), wire_obligation=WireObligation.FINAL_WIRE, enum_values=('none', 'burst', 'split', 'chain', 'burn', 'frostburn', 'poison', 'shadowflame', 'bleed', 'starburst', 'overhead_barrage', 'aura_pulse', 'spore_cloud', 'mini_missiles', 'vortex_spawn', 'blackhole', 'radial_beams', 'lightning_arc', 'heal', 'lifesteal')),
        _param(name='aoeRadiusTiles', prompt_description='0..10', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('aoeDamageRadiusPx', 'aoeRadiusTiles'), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='count', prompt_description='0..8 for child-producing onHit; overhead_barrage = bounded authored child projectiles descending from above the hit', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('maxChildProjectiles', 'splitCount'), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='chainCount', prompt_description='0..6 for chain-like effects', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('chainCount',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='secondaryDamageMultiplier', prompt_description='>0..1 required for damaging child-producing onHit; authored damage*secondaryDamageMultiplier must round to at least 1', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('secondaryDamageMultiplier',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='secondaryLifetimeTicks', prompt_description='5..180 required for overhead_barrage children', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('secondaryLifetimeTicks',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='pullStrength', prompt_description='0..1; values above 0 require explicit pullMode', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('pullStrength',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='pullMode', prompt_description='none|target_to_owner|owner_to_target|target_to_projectile', value_kind=ParamValueKind.ENUM, example_value='none', compiled_fields=('pullMode',), wire_obligation=WireObligation.FINAL_WIRE, enum_values=('none', 'target_to_owner', 'owner_to_target', 'target_to_projectile')),
        _param(name='debuffHint', prompt_description='short text or empty', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=('debuffHint',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='debuffTime', prompt_description='30..600 required for buff-applying onHit', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('debuffTime',), wire_obligation=WireObligation.FINAL_WIRE, prompt_group='apply_on_hit_effect'),
        ),
        root_executor=False,
        requires_root_executor=False,
        allowed_result_kinds=(),
        repair_groups=(),
        compiled_source_overrides=(CompiledFieldSourceOverride(compiled_field='immunityCooldown', source_paths=('immunityCooldown',)),),
    ),
    EngineFunctionContract(
        name='spawn_contact_particles',
        meaning='Pure projectile contact VFX/dust; no damage. Requires one executable root executor.',
        params=(
        _param(name='effect', prompt_description='none|dust|electric|slime|star|flame|frost|leaf|shadow|poison|blood|honey|sand|lunar|heal|holy|smoke', value_kind=ParamValueKind.ENUM, example_value='none', compiled_fields=('effect',), wire_obligation=WireObligation.FINAL_WIRE, enum_values=('none', 'dust', 'electric', 'slime', 'star', 'flame', 'frost', 'leaf', 'shadow', 'poison', 'blood', 'honey', 'sand', 'lunar', 'heal', 'holy', 'smoke')),
        _param(name='amount', prompt_description='0 off; 1..40', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('burstDustCap', 'dustSpawnDenom'), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='scale', prompt_description='0.15..2', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('vfxParticleScale',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='durationTicks', prompt_description='1..80', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('vfxParticleDurationTicks',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='material', prompt_description='none|wood|metal|stone|magic|fire|slime|frost|shadow; only with effect none/dust', value_kind=ParamValueKind.ENUM, example_value='none', compiled_fields=('vfxMaterial',), wire_obligation=WireObligation.FINAL_WIRE, enum_values=('none', 'wood', 'metal', 'stone', 'magic', 'fire', 'slime', 'frost', 'shadow')),
        ),
        root_executor=False,
        requires_root_executor=True,
        allowed_result_kinds=(),
        repair_groups=(
            RepairGroupContract(members=('effect', 'material'), policy_owner='infini_local.core.runtime_authoring.schema.repair_param_allowed_combinations'),
        ),
    ),
    EngineFunctionContract(
        name='leave_trail_or_field',
        meaning='Visual-only projectile trail or bounded dust field; no gameplay. Requires one executable root executor.',
        params=(
        _param(name='trailLength', prompt_description='0..24', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('trailLength',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='fieldLifetimeTicks', prompt_description='0..240', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('vfxFieldLifetimeTicks',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='fieldRadiusTiles', prompt_description='0..6', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('fieldRadius', 'vfxFieldRadiusTiles'), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='tickRate', prompt_description='1..60', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('vfxFieldTickRate',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='visualOnly', prompt_description='true only', value_kind=ParamValueKind.BOOLEAN, example_value=False, compiled_fields=(), wire_obligation=WireObligation.CONTROL_DERIVED, provenance_via_lowerer=True),
        ),
        root_executor=False,
        requires_root_executor=True,
        allowed_result_kinds=(),
        repair_groups=(),
        compiled_source_overrides=(CompiledFieldSourceOverride(compiled_field='fieldRadius', source_paths=('fieldRadiusTiles', 'fieldRadius')), CompiledFieldSourceOverride(compiled_field='vfxFieldRadiusTiles', source_paths=('fieldRadiusTiles', 'fieldRadius')),),
    ),
    EngineFunctionContract(
        name='visual_effect_cue',
        meaning='Frozen VFX/audio slot; presentation only, no gameplay.',
        params=(
        _param(name='event', prompt_description='travel|active|tick|hit|kill|expire|while_held|while_equipped|on_use|on_alt_use', value_kind=ParamValueKind.ENUM, example_value='travel', compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX, enum_values=('travel', 'active', 'tick', 'hit', 'kill', 'expire', 'while_held', 'while_equipped', 'on_use', 'on_alt_use')),
        _param(name='rendererKind', prompt_description='projectileAfterimage|spriteStampTrail|historyRibbon|tipTrail|ghostArc|wavyStrip|beamLine|fieldPulse|orbitingMotes|actorAfterimage|impactRing|impactSprite|childMotes|lightCue|soundCue', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX),
        _param(name='channel', prompt_description='motionTrail|coreGlow|ambientParticles|impactShape|impactParticles|decaySmoke|light|sound', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX),
        _param(name='lane', prompt_description='primary|support|accent|ornament|cue', value_kind=ParamValueKind.ENUM, example_value='primary', compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX, enum_values=('primary', 'support', 'accent', 'ornament', 'cue')),
        _param(name='textureRole', prompt_description='projectile|impact|child|field', value_kind=ParamValueKind.ENUM, example_value='projectile', compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX, enum_values=('projectile', 'impact', 'child', 'field')),
        _param(name='particleRole', prompt_description='projectile|impact|child|field', value_kind=ParamValueKind.ENUM, example_value='projectile', compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX, enum_values=('projectile', 'impact', 'child', 'field')),
        _param(name='emissionMode', prompt_description='wake|orbit|residue|burst|cone|ring|spiral|point', value_kind=ParamValueKind.ENUM, example_value='wake', compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX, enum_values=('wake', 'orbit', 'residue', 'burst', 'cone', 'ring', 'spiral', 'point')),
        _param(name='particleSystemId', prompt_description='pl:glow|pl:shard|pl:smoke|pl:spark|dust', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX),
        _param(name='scale', prompt_description='0.15..5', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX),
        _param(name='density', prompt_description='0..1', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX),
        _param(name='duration', prompt_description='3..120', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX),
        _param(name='alpha', prompt_description='0..1', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX),
        _param(name='spread', prompt_description='0..2', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX),
        _param(name='jitter', prompt_description='0..1.5', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX),
        _param(name='startTick', prompt_description='0..120', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX),
        _param(name='repeatEvery', prompt_description='0..120', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX),
        _param(name='importance', prompt_description='core|secondary|accent|luxury', value_kind=ParamValueKind.ENUM, example_value='core', compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX, enum_values=('core', 'secondary', 'accent', 'luxury')),
        _param(name='note', prompt_description='short debug', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX),
        ),
        root_executor=False,
        requires_root_executor=False,
        allowed_result_kinds=(),
        repair_groups=(
            RepairGroupContract(members=('channel', 'event', 'rendererKind'), policy_owner='infini_local.core.runtime_authoring.schema.repair_param_allowed_combinations'),
        ),
    ),
    EngineFunctionContract(
        name='apply_player_effect_on_use',
        meaning='Executable non-combat use effects: healing, vanilla buffs, and bounded generated utility buffs.',
        params=(
        _param(name='healLife', prompt_description='0..500', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('healLife',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='healMana', prompt_description='0..500', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('healMana',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='buffType', prompt_description='non-negative integer Terraria buff type ID; omit when generatedBuff owns the effect', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('buffType',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='buffTime', prompt_description='ticks', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('buffTime',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='buffs', prompt_description='array of {buffType: integer Terraria ID, buffTime: ticks}; max 4', value_kind=ParamValueKind.LIST, example_value=(), compiled_fields=('extraBuffs',), wire_obligation=WireObligation.FINAL_WIRE, list_item_model=BuffParamBoundary),
        _param(name='generatedBuff', prompt_description='object with durationTicks, miningSpeedMultiplier, emitLightStrength, lightColorName, oreSenseRadiusTiles, movementSpeed, jumpBoost, manaRegen, lifeRegen; oreSense>0=findTreasure; radius debug-only', value_kind=ParamValueKind.OBJECT, example_value=(), compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, object_model=GeneratedBuffParamBoundary, nested_wire_paths=(NestedWirePathContract(path='durationTicks', compiled_fields=('generatedBuff.durationTicks',)), NestedWirePathContract(path='emitLightStrength', compiled_fields=('generatedBuff.emitLightStrength',)), NestedWirePathContract(path='jumpBoost', compiled_fields=('generatedBuff.jumpBoost',)), NestedWirePathContract(path='lifeRegen', compiled_fields=('generatedBuff.lifeRegen',)), NestedWirePathContract(path='lightColorName', compiled_fields=('generatedBuff.lightColorName',)), NestedWirePathContract(path='manaRegen', compiled_fields=('generatedBuff.manaRegen',)), NestedWirePathContract(path='miningSpeedMultiplier', compiled_fields=('generatedBuff.miningSpeedMultiplier',)), NestedWirePathContract(path='movementSpeed', compiled_fields=('generatedBuff.movementSpeed',)), NestedWirePathContract(path='oreSenseRadiusTiles', compiled_fields=('generatedBuff.oreSenseRadiusTiles',)))),
        _param(name='note', prompt_description='short identity/debug only', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.NON_WIRE),
        ),
        root_executor=False,
        requires_root_executor=False,
        allowed_result_kinds=(),
        repair_groups=(),
    ),
    EngineFunctionContract(
        name='tool_capability',
        meaning='Executable Terraria tool stats for real tools only.',
        params=(
        _param(name='pickPower', prompt_description='0..1000', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('pickPower',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='axePower', prompt_description='0..200 internal Item.axe units', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('axePower',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='hammerPower', prompt_description='0..1000', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('hammerPower',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='miningSpeedScale', prompt_description='0.25..2 executable held-tool mining speed multiplier', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('miningSpeedScale',), wire_obligation=WireObligation.FINAL_WIRE),
        ),
        root_executor=False,
        requires_root_executor=False,
        allowed_result_kinds=(),
        repair_groups=(),
    ),
    EngineFunctionContract(
        name='placeable_behavior',
        meaning='Place exact raw parent tile/wall; requires furniture.',
        params=(
        _param(name='createTile', prompt_description='-1 off|exact raw id', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('createTile',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='createWall', prompt_description='-1 off|exact raw id', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('createWall',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='placeStyle', prompt_description='exact raw style', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('placeStyle',), wire_obligation=WireObligation.FINAL_WIRE),
        ),
        root_executor=False,
        requires_root_executor=False,
        allowed_result_kinds=(),
        repair_groups=(),
    ),
    EngineFunctionContract(
        name='emit_light',
        meaning='Executable held/projectile/effect light.',
        params=(
        _param(name='strength', prompt_description='0..1', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('runtimeLightStrength',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='color', prompt_description='named color', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=('primaryColorName', 'runtimeLightColorName'), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='durationTicks', prompt_description='1..240; held=continuous', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('runtimeLightDurationTicks',), wire_obligation=WireObligation.CONTROL_DERIVED),
        ),
        root_executor=False,
        requires_root_executor=False,
        allowed_result_kinds=(),
        repair_groups=(),
        compiled_source_overrides=(CompiledFieldSourceOverride(compiled_field='primaryColorName', source_paths=('lightColorName', 'color')), CompiledFieldSourceOverride(compiled_field='runtimeLightColorName', source_paths=('lightColorName', 'color')),),
    ),
    EngineFunctionContract(
        name='mobility_effect',
        meaning='Bounded movement: recall, blink to cursor, or blink to projectile impact; needs safe tile/cooldown.',
        params=(
        _param(name='mode', prompt_description='recall_home|blink_to_cursor|blink_to_projectile_impact', value_kind=ParamValueKind.ENUM, example_value='recall_home', compiled_fields=('mobilityMode',), wire_obligation=WireObligation.FINAL_WIRE, enum_values=('recall_home', 'blink_to_cursor', 'blink_to_projectile_impact')),
        _param(name='rangeTiles', prompt_description='0..80', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('mobilityRangeTiles',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='cooldownTicks', prompt_description='0..3600', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('mobilityCooldownTicks',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='safeTileOnly', prompt_description='true', value_kind=ParamValueKind.BOOLEAN, example_value=False, compiled_fields=('mobilitySafeTileOnly',), wire_obligation=WireObligation.FINAL_WIRE),
        ),
        root_executor=False,
        requires_root_executor=False,
        allowed_result_kinds=(),
        repair_groups=(),
    ),
    EngineFunctionContract(
        name='accessory_effect',
        meaning='Equippable accessory stats, not temporary use effects.',
        params=(
        _param(name='archetype', prompt_description='mobility|defense|damage|utility|hybrid', value_kind=ParamValueKind.ENUM, example_value='mobility', compiled_fields=('archetype',), wire_obligation=WireObligation.FINAL_WIRE, enum_values=('mobility', 'defense', 'damage', 'utility', 'hybrid')),
        _param(name='defense', prompt_description='0..20', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('defense',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='stats', prompt_description='object, not string; keys include maxLife,maxMana,lifeRegen,manaRegen,movementSpeed,maxRunSpeed,jumpSpeed,genericDamage,genericCrit,attackSpeed,lightStrength', value_kind=ParamValueKind.OBJECT, example_value=(), compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, object_model=EquipmentStatsParamBoundary, nested_wire_paths=(NestedWirePathContract(path='aggro', compiled_fields=('aggro',)), NestedWirePathContract(path='ammoSaveChance', compiled_fields=('ammoSaveChance',)), NestedWirePathContract(path='armorPenetration', compiled_fields=('armorPenetration',)), NestedWirePathContract(path='attackSpeed', compiled_fields=('attackSpeed',)), NestedWirePathContract(path='endurance', compiled_fields=('endurance',)), NestedWirePathContract(path='fallDamageImmune', compiled_fields=('fallDamageImmune',)), NestedWirePathContract(path='genericCrit', compiled_fields=('genericCrit',)), NestedWirePathContract(path='genericDamage', compiled_fields=('genericDamage',)), NestedWirePathContract(path='jumpSpeed', compiled_fields=('jumpSpeed',)), NestedWirePathContract(path='knockback', compiled_fields=('knockback',)), NestedWirePathContract(path='lavaImmune', compiled_fields=('lavaImmune',)), NestedWirePathContract(path='lifeRegen', compiled_fields=('lifeRegen',)), NestedWirePathContract(path='lightColorName', compiled_fields=('lightColorName',)), NestedWirePathContract(path='lightStrength', compiled_fields=('lightStrength',)), NestedWirePathContract(path='magicDamage', compiled_fields=('magicDamage',)), NestedWirePathContract(path='manaCostReduction', compiled_fields=('manaCostReduction',)), NestedWirePathContract(path='manaRegen', compiled_fields=('manaRegen',)), NestedWirePathContract(path='maxLife', compiled_fields=('maxLife',)), NestedWirePathContract(path='maxMana', compiled_fields=('maxMana',)), NestedWirePathContract(path='maxRunSpeed', compiled_fields=('maxRunSpeed',)), NestedWirePathContract(path='meleeDamage', compiled_fields=('meleeDamage',)), NestedWirePathContract(path='minionSlots', compiled_fields=('minionSlots',)), NestedWirePathContract(path='movementSpeed', compiled_fields=('movementSpeed',)), NestedWirePathContract(path='rangedDamage', compiled_fields=('rangedDamage',)), NestedWirePathContract(path='sentrySlots', compiled_fields=('sentrySlots',)), NestedWirePathContract(path='summonDamage', compiled_fields=('summonDamage',)), NestedWirePathContract(path='summonTagDamage', compiled_fields=('summonTagDamage',)), NestedWirePathContract(path='waterWalk', compiled_fields=('waterWalk',)), NestedWirePathContract(path='whipRange', compiled_fields=('whipRange',)),)),
        ),
        root_executor=False,
        requires_root_executor=False,
        allowed_result_kinds=(),
        repair_groups=(),
    ),
    EngineFunctionContract(
        name='armor_effect',
        meaning='Armor: slot, defense, equip/set bonuses.',
        params=(
        _param(name='armorSlot', prompt_description='head|body|legs', value_kind=ParamValueKind.ENUM, example_value='head', compiled_fields=('slot',), wire_obligation=WireObligation.FINAL_WIRE, enum_values=('head', 'body', 'legs')),
        _param(name='setKey', prompt_description='same id for set or empty', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=('setKey',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='archetype', prompt_description='melee|ranged|magic|summon|defense|mobility|utility|hybrid', value_kind=ParamValueKind.ENUM, example_value='melee', compiled_fields=('archetype',), wire_obligation=WireObligation.FINAL_WIRE, enum_values=('melee', 'ranged', 'magic', 'summon', 'defense', 'mobility', 'utility', 'hybrid')),
        _param(name='defense', prompt_description='0..80', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('defense',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='stats', prompt_description='life/mana/regen/move/jump/classDmg/crit/atkSpeed/kb/minions/light/immunities', value_kind=ParamValueKind.OBJECT, example_value=(), compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, object_model=EquipmentStatsParamBoundary, nested_wire_paths=(NestedWirePathContract(path='aggro', compiled_fields=('aggro',)), NestedWirePathContract(path='ammoSaveChance', compiled_fields=('ammoSaveChance',)), NestedWirePathContract(path='armorPenetration', compiled_fields=('armorPenetration',)), NestedWirePathContract(path='attackSpeed', compiled_fields=('attackSpeed',)), NestedWirePathContract(path='endurance', compiled_fields=('endurance',)), NestedWirePathContract(path='fallDamageImmune', compiled_fields=('fallDamageImmune',)), NestedWirePathContract(path='genericCrit', compiled_fields=('genericCrit',)), NestedWirePathContract(path='genericDamage', compiled_fields=('genericDamage',)), NestedWirePathContract(path='jumpSpeed', compiled_fields=('jumpSpeed',)), NestedWirePathContract(path='knockback', compiled_fields=('knockback',)), NestedWirePathContract(path='lavaImmune', compiled_fields=('lavaImmune',)), NestedWirePathContract(path='lifeRegen', compiled_fields=('lifeRegen',)), NestedWirePathContract(path='lightColorName', compiled_fields=('lightColorName',)), NestedWirePathContract(path='lightStrength', compiled_fields=('lightStrength',)), NestedWirePathContract(path='magicDamage', compiled_fields=('magicDamage',)), NestedWirePathContract(path='manaCostReduction', compiled_fields=('manaCostReduction',)), NestedWirePathContract(path='manaRegen', compiled_fields=('manaRegen',)), NestedWirePathContract(path='maxLife', compiled_fields=('maxLife',)), NestedWirePathContract(path='maxMana', compiled_fields=('maxMana',)), NestedWirePathContract(path='maxRunSpeed', compiled_fields=('maxRunSpeed',)), NestedWirePathContract(path='meleeDamage', compiled_fields=('meleeDamage',)), NestedWirePathContract(path='minionSlots', compiled_fields=('minionSlots',)), NestedWirePathContract(path='movementSpeed', compiled_fields=('movementSpeed',)), NestedWirePathContract(path='rangedDamage', compiled_fields=('rangedDamage',)), NestedWirePathContract(path='sentrySlots', compiled_fields=('sentrySlots',)), NestedWirePathContract(path='summonDamage', compiled_fields=('summonDamage',)), NestedWirePathContract(path='summonTagDamage', compiled_fields=('summonTagDamage',)), NestedWirePathContract(path='waterWalk', compiled_fields=('waterWalk',)), NestedWirePathContract(path='whipRange', compiled_fields=('whipRange',)),)),
        _param(name='setBonus', prompt_description='text,genericDamage,meleeDamage,rangedDamage,magicDamage,summonDamage,genericCrit,movementSpeed,lifeRegen,manaRegen,minionSlots,sentrySlots,manaCostReduction,ammoSaveChance,aggro,endurance,armorPenetration', value_kind=ParamValueKind.OBJECT, example_value=(), compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, object_model=ArmorSetBonusParamBoundary, nested_wire_paths=(NestedWirePathContract(path='aggro', compiled_fields=('setBonusAggro',)), NestedWirePathContract(path='ammoSaveChance', compiled_fields=('setBonusAmmoSaveChance',)), NestedWirePathContract(path='armorPenetration', compiled_fields=('setBonusArmorPenetration',)), NestedWirePathContract(path='endurance', compiled_fields=('setBonusEndurance',)), NestedWirePathContract(path='genericCrit', compiled_fields=('setBonusGenericCrit',)), NestedWirePathContract(path='genericDamage', compiled_fields=('setBonusGenericDamage',)), NestedWirePathContract(path='lifeRegen', compiled_fields=('setBonusLifeRegen',)), NestedWirePathContract(path='magicDamage', compiled_fields=('setBonusMagicDamage',)), NestedWirePathContract(path='manaCostReduction', compiled_fields=('setBonusManaCostReduction',)), NestedWirePathContract(path='manaRegen', compiled_fields=('setBonusManaRegen',)), NestedWirePathContract(path='meleeDamage', compiled_fields=('setBonusMeleeDamage',)), NestedWirePathContract(path='minionSlots', compiled_fields=('setBonusMinionSlots',)), NestedWirePathContract(path='movementSpeed', compiled_fields=('setBonusMovementSpeed',)), NestedWirePathContract(path='rangedDamage', compiled_fields=('setBonusRangedDamage',)), NestedWirePathContract(path='sentrySlots', compiled_fields=('setBonusSentrySlots',)), NestedWirePathContract(path='summonDamage', compiled_fields=('setBonusSummonDamage',)), NestedWirePathContract(path='text', compiled_fields=('setBonusText',)))),
        ),
        root_executor=False,
        requires_root_executor=False,
        allowed_result_kinds=(),
        repair_groups=(),
        compiled_source_overrides=(CompiledFieldSourceOverride(compiled_field='slot', source_paths=('armorSlot', 'slot')),),
    ),
    EngineFunctionContract(
        name='set_alt_use_mode',
        meaning='Right-click/alternate-use utility; normal use unchanged unless authored.',
        params=(
        _param(name='mode', prompt_description='mobility|generated_buff|light', value_kind=ParamValueKind.ENUM, example_value='mobility', compiled_fields=('altMobilityMode', 'altUseMode'), wire_obligation=WireObligation.FINAL_WIRE, enum_values=('mobility', 'generated_buff', 'light')),
        _param(name='mobilityMode', prompt_description='recall_home|blink_to_cursor', value_kind=ParamValueKind.ENUM, example_value='recall_home', compiled_fields=('altMobilityMode',), wire_obligation=WireObligation.FINAL_WIRE, enum_values=('recall_home', 'blink_to_cursor')),
        _param(name='rangeTiles', prompt_description='0..80', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('altMobilityRangeTiles',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='cooldownTicks', prompt_description='0..3600', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('altUseCooldownTicks',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='safeTileOnly', prompt_description='true', value_kind=ParamValueKind.BOOLEAN, example_value=False, compiled_fields=('altMobilitySafeTileOnly',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='generatedBuff', prompt_description='same shape as apply_player_effect_on_use.generatedBuff', value_kind=ParamValueKind.OBJECT, example_value=(), compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, object_model=GeneratedBuffParamBoundary, nested_wire_paths=(NestedWirePathContract(path='durationTicks', compiled_fields=('altGeneratedBuff.durationTicks',)), NestedWirePathContract(path='emitLightStrength', compiled_fields=('altGeneratedBuff.emitLightStrength',)), NestedWirePathContract(path='jumpBoost', compiled_fields=('altGeneratedBuff.jumpBoost',)), NestedWirePathContract(path='lifeRegen', compiled_fields=('altGeneratedBuff.lifeRegen',)), NestedWirePathContract(path='lightColorName', compiled_fields=('altGeneratedBuff.lightColorName',)), NestedWirePathContract(path='manaRegen', compiled_fields=('altGeneratedBuff.manaRegen',)), NestedWirePathContract(path='miningSpeedMultiplier', compiled_fields=('altGeneratedBuff.miningSpeedMultiplier',)), NestedWirePathContract(path='movementSpeed', compiled_fields=('altGeneratedBuff.movementSpeed',)), NestedWirePathContract(path='oreSenseRadiusTiles', compiled_fields=('altGeneratedBuff.oreSenseRadiusTiles',)))),
        _param(name='durationTicks', prompt_description='1..21600', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('altGeneratedBuff.durationTicks',), wire_obligation=WireObligation.FINAL_WIRE),
        ),
        root_executor=False,
        requires_root_executor=False,
        allowed_result_kinds=(),
        repair_groups=(
            RepairGroupContract(members=('mobilityMode', 'mode'), policy_owner='infini_local.core.runtime_authoring.schema.repair_param_allowed_combinations'),
        ),
        compiled_source_overrides=(CompiledFieldSourceOverride(compiled_field='altMobilityMode', source_paths=('mobilityMode', 'mode')),),
    ),
    EngineFunctionContract(
        name='hold_item_effect',
        meaning='Held-item utility: light or generated buff refreshed while held; generatedBuff.durationTicks must be at least 2.',
        params=(
        _param(name='lightStrength', prompt_description='0..1.5', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('holdLightStrength',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='lightColorName', prompt_description='white|gray|brown|tan|red|orange|yellow|gold|green|cyan|blue|purple|pink', value_kind=ParamValueKind.ENUM, example_value='white', compiled_fields=('holdLightColorName',), wire_obligation=WireObligation.FINAL_WIRE, enum_values=('white', 'gray', 'brown', 'tan', 'red', 'orange', 'yellow', 'gold', 'green', 'cyan', 'blue', 'purple', 'pink')),
        _param(name='generatedBuff', prompt_description='generated buff object', value_kind=ParamValueKind.OBJECT, example_value=(), compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, object_model=GeneratedBuffParamBoundary, nested_wire_paths=(NestedWirePathContract(path='durationTicks', compiled_fields=('holdGeneratedBuff.durationTicks',)), NestedWirePathContract(path='emitLightStrength', compiled_fields=('holdGeneratedBuff.emitLightStrength',)), NestedWirePathContract(path='jumpBoost', compiled_fields=('holdGeneratedBuff.jumpBoost',)), NestedWirePathContract(path='lifeRegen', compiled_fields=('holdGeneratedBuff.lifeRegen',)), NestedWirePathContract(path='lightColorName', compiled_fields=('holdGeneratedBuff.lightColorName',)), NestedWirePathContract(path='manaRegen', compiled_fields=('holdGeneratedBuff.manaRegen',)), NestedWirePathContract(path='miningSpeedMultiplier', compiled_fields=('holdGeneratedBuff.miningSpeedMultiplier',)), NestedWirePathContract(path='movementSpeed', compiled_fields=('holdGeneratedBuff.movementSpeed',)), NestedWirePathContract(path='oreSenseRadiusTiles', compiled_fields=('holdGeneratedBuff.oreSenseRadiusTiles',)))),
        ),
        root_executor=False,
        requires_root_executor=False,
        allowed_result_kinds=(),
        repair_groups=(),
        compiled_source_overrides=(CompiledFieldSourceOverride(compiled_field='holdLightColorName', source_paths=('lightColorName', 'color')),),
    ),
    EngineFunctionContract(
        name='use_affordance',
        meaning='Executable item-use and held-draw affordance only.',

        params=(
        _param(name='autoReuse', prompt_description='bool', value_kind=ParamValueKind.BOOLEAN, example_value=False, compiled_fields=('autoReuse',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='useTurn', prompt_description='bool', value_kind=ParamValueKind.BOOLEAN, example_value=False, compiled_fields=('useTurn',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='channelUse', prompt_description='bool', value_kind=ParamValueKind.BOOLEAN, example_value=False, compiled_fields=('channelUse',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='itemScale', prompt_description='0.55..1.55', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('itemScale',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='holdoutOffsetX', prompt_description='-80..80', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('holdoutOffsetX',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='holdoutOffsetY', prompt_description='-80..80', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('holdoutOffsetY',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='heldVisibility', prompt_description='show_item|hide_item|show_projectile|show_both', value_kind=ParamValueKind.ENUM, example_value='show_item', compiled_fields=('heldVisibility',), wire_obligation=WireObligation.FINAL_WIRE, enum_values=('show_item', 'hide_item', 'show_projectile', 'show_both')),
        _param(name='releaseTiming', prompt_description='instant|early|mid_swing|on_contact|on_release', value_kind=ParamValueKind.ENUM, example_value='instant', compiled_fields=('releaseTiming',), wire_obligation=WireObligation.FINAL_WIRE, enum_values=('instant', 'early', 'mid_swing', 'on_contact', 'on_release')),
        _param(name='handPose', prompt_description='short_weapon|two_hand|overhead|throwing|staff|held_out|none', value_kind=ParamValueKind.ENUM, example_value='short_weapon', compiled_fields=('handPose',), wire_obligation=WireObligation.FINAL_WIRE, enum_values=('short_weapon', 'two_hand', 'overhead', 'throwing', 'staff', 'held_out', 'none')),
        _param(name='initialOffsetPx', prompt_description='-64..64', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('initialOffsetPx',), wire_obligation=WireObligation.FINAL_WIRE),
        ),
        root_executor=False,
        requires_root_executor=False,
        allowed_result_kinds=(),
        repair_groups=(),
    ),
    EngineFunctionContract(
        name='consumption_behavior',
        meaning='Consumable-use behavior; consumeChancePercent controls stack spend; no loot/spawn.',
        params=(
        _param(name='consumeChancePercent', prompt_description='0..100; 100 normal consume; 0 never consume', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('consumeChancePercent',), wire_obligation=WireObligation.FINAL_WIRE),
        ),
        root_executor=False,
        requires_root_executor=False,
        allowed_result_kinds=(),
        repair_groups=(),
    ),
    EngineFunctionContract(
        name='ammo_behavior',
        meaning='Vanilla ammo identity for generated ammo stacks; projectile behavior belongs to weapon/projectile calls.',
        params=(
        _param(name='ammoFor', prompt_description='arrow|bullet|empty', value_kind=ParamValueKind.ENUM, example_value='arrow', compiled_fields=('ammoFor',), wire_obligation=WireObligation.FINAL_WIRE, enum_values=('arrow', 'bullet', 'empty')),
        ),
        root_executor=False,
        requires_root_executor=False,
        allowed_result_kinds=(),
        repair_groups=(),
    ),
    EngineFunctionContract(
        name='use_condition',
        meaning='Side-effect-free CanUseItem condition; blocks use only.',
        params=(
        _param(name='mode', prompt_description='grounded|not_wet|life_above|mana_above', value_kind=ParamValueKind.ENUM, example_value='grounded', compiled_fields=('useConditionMode',), wire_obligation=WireObligation.FINAL_WIRE, enum_values=('grounded', 'not_wet', 'life_above', 'mana_above')),
        _param(name='minLife', prompt_description='0..5000', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('useConditionMinLife',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='minMana', prompt_description='0..5000', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('useConditionMinMana',), wire_obligation=WireObligation.FINAL_WIRE),
        ),
        root_executor=False,
        requires_root_executor=False,
        allowed_result_kinds=(),
        repair_groups=(),
    ),
)

_CONTRACT_ERRORS = validate_engine_function_contracts(ENGINE_FUNCTION_CONTRACTS)
if _CONTRACT_ERRORS:
    raise RuntimeError("invalid engine function contracts: " + "; ".join(_CONTRACT_ERRORS))

ENGINE_FUNCTION_CONTRACT_BY_NAME = MappingProxyType({spec.name: spec for spec in ENGINE_FUNCTION_CONTRACTS})

def engine_function_catalog() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for spec in ENGINE_FUNCTION_CONTRACTS:
        card: dict[str, Any] = {
            "meaning": spec.meaning,
            "params": {param.name: param.prompt_description for param in spec.params if param.function_card_visible},
        }
        if spec.requires_root_executor:
            card["requiresRootExecutor"] = True
        out[spec.name] = card
    return out

def accepted_engine_param_names(fn: str) -> frozenset[str]:
    spec = ENGINE_FUNCTION_CONTRACT_BY_NAME.get(str(fn or ""))
    return frozenset(param.name for param in spec.params) if spec is not None else frozenset()


def engine_param_wire_obligation(fn: str, param_path: str) -> WireObligation | None:
    """Return the canonical top-level provenance obligation for one authored leaf."""

    normalized_fn = str(fn or "").strip().lower().replace("-", "_").replace(" ", "_")
    param_name = str(param_path or "").strip().split(".", 1)[0]
    spec = ENGINE_FUNCTION_CONTRACT_BY_NAME.get(normalized_fn)
    if spec is None or not param_name:
        return None
    return next((param.wire_obligation for param in spec.params if param.name == param_name), None)

def accepted_param_extras() -> dict[str, frozenset[str]]:
    return {
        spec.name: frozenset(param.name for param in spec.params if param.prompt_group)
        for spec in ENGINE_FUNCTION_CONTRACTS
        if any(param.prompt_group for param in spec.params)
    }

def repair_dependency_groups() -> dict[str, tuple[frozenset[str], ...]]:
    return {
        spec.name: tuple(frozenset(group.members) for group in spec.repair_groups)
        for spec in ENGINE_FUNCTION_CONTRACTS
        if spec.repair_groups
    }


def compiled_field_source_map() -> dict[str, dict[str, str | tuple[str, ...]]]:
    """Project exact static provenance from immutable parameter contracts."""

    out: dict[str, dict[str, str | tuple[str, ...]]] = {}
    for spec in ENGINE_FUNCTION_CONTRACTS:
        sources_by_field: dict[str, list[str]] = {}
        for param in spec.params:
            for field in param.compiled_fields:
                sources_by_field.setdefault(field, []).append(param.name)
            for nested in param.nested_wire_paths:
                source_path = f"{param.name}.{nested.path}"
                for field in nested.compiled_fields:
                    sources_by_field.setdefault(field, []).append(source_path)
        for override in spec.compiled_source_overrides:
            sources_by_field[override.compiled_field] = list(override.source_paths)
        if sources_by_field:
            out[spec.name] = {
                field: sources[0] if len(sources) == 1 else tuple(sources)
                for field, sources in sources_by_field.items()
            }
    return out


ROOT_EXECUTOR_FUNCTION_NAMES = frozenset(spec.name for spec in ENGINE_FUNCTION_CONTRACTS if spec.root_executor)
ENGINE_FUNCTION_CATALOG = MappingProxyType(engine_function_catalog())
ACCEPTED_PARAM_EXTRAS_BY_FUNCTION = MappingProxyType(accepted_param_extras())
REPAIR_DEPENDENCY_GROUPS_BY_FUNCTION = MappingProxyType(repair_dependency_groups())
ROOT_EXECUTOR_SHARED_PARAM_NAMES = frozenset(
    param.name
    for spec in ENGINE_FUNCTION_CONTRACTS
    if spec.root_executor
    for param in spec.params
    if param.prompt_group == "root_executor"
)

__all__ = [
    "ENGINE_FUNCTION_CONTRACTS",
    "ENGINE_FUNCTION_CONTRACT_BY_NAME",
    "ENGINE_FUNCTION_CATALOG",
    "ACCEPTED_PARAM_EXTRAS_BY_FUNCTION",
    "REPAIR_DEPENDENCY_GROUPS_BY_FUNCTION",
    "ROOT_EXECUTOR_FUNCTION_NAMES",
    "ROOT_EXECUTOR_SHARED_PARAM_NAMES",
    "engine_function_catalog",
    "accepted_engine_param_names",
    "engine_param_wire_obligation",
    "accepted_param_extras",
    "repair_dependency_groups",
    "compiled_field_source_map",
]
