"""Canonical immutable Author engine function contracts.

This module owns provider grammar, prompt-visible function metadata, wire/provenance
obligations, repair groups, normalized-only IR parameters, and typed lowerer edges.
Specialized compiler lowerers remain the gameplay value-transform owners. Result-kind
applicability remains solely in ``reports.py`` / runtime-family policy.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from types import MappingProxyType
from typing import Any

from infini_local.core.runtime_authoring.engine_param_boundaries import (
    ArmorSetBonusParamBoundary,
    BuffParamBoundary,
    EquipmentStatsParamBoundary,
    GeneratedBuffParamBoundary,
)
from infini_local.core.runtime_authoring.function_contract_types import (
    FUNCTION_SOURCE_PATH,
    EngineLowererContract,
    LoweredParamBinding,
    NormalizedParamContract,
    EngineFunctionContract,
    EngineParamContract,
    NestedWirePathContract,
    ParamValueKind,
    RepairGroupContract,
    WireObligation,
    validate_engine_function_contracts,
)
from infini_local.core.runtime_executor_vocabulary import EFFECT_CODE, ONHIT_CODE
from infini_local.core.sound_catalog import IMPACT_SOUND_IDS, USE_SOUND_IDS
from infini_local.core.runtime_sentry_policy import SENTRY_CHILD_ONHIT
from infini_local.core.vfx_composition_primitives import (
    VFX_CUE_CHANNEL_VALUES,
    VFX_CUE_EMISSION_MODE_VALUES,
    VFX_CUE_EVENT_VALUES,
    VFX_CUE_IMPORTANCE_VALUES,
    VFX_CUE_LANE_VALUES,
    VFX_CUE_PARTICLE_SYSTEM_ID_VALUES,
    VFX_CUE_RENDERER_VALUES,
    VFX_CUE_ROLE_VALUES,
)

_EXECUTOR_EFFECT_VALUES = tuple(EFFECT_CODE)
_EXECUTOR_ONHIT_VALUES = tuple(ONHIT_CODE)
_SENTRY_ONHIT_VALUES = tuple(
    value for value in _EXECUTOR_ONHIT_VALUES if value not in SENTRY_CHILD_ONHIT
)
_PARTICLE_EFFECT_VALUES = (
    "none",
    "dust",
    *(value for value in _EXECUTOR_EFFECT_VALUES if value != "none"),
)
_ARMOR_SLOT_VALUES = ("head", "body", "legs")

# Stable wire name of the sole terminal combat executor. Specialized Author
# functions lower into this function through typed registry edges.
NORMALIZED_ROOT_FUNCTION_NAME = "shoot_projectile"

def _param(**kwargs: Any) -> EngineParamContract:
    return EngineParamContract(**kwargs)


def _root_required_param(**kwargs: Any) -> EngineParamContract:
    """Declare one mandatory field of the terminal normalized root grammar."""

    return EngineParamContract(required_on_normalized_root=True, **kwargs)


def _internal(name: str, *compiled_fields: str) -> NormalizedParamContract:
    return NormalizedParamContract(name=name, compiled_fields=tuple(compiled_fields))


def _bind(source_path: str, *target_param_paths: str) -> LoweredParamBinding:
    return LoweredParamBinding(source_path=source_path, target_param_paths=tuple(target_param_paths))


def _direct_bindings(*names: str) -> tuple[LoweredParamBinding, ...]:
    return tuple(_bind(name, name) for name in names)


def _lowerer(*bindings: LoweredParamBinding) -> EngineLowererContract:
    return EngineLowererContract(target_function=NORMALIZED_ROOT_FUNCTION_NAME, bindings=tuple(bindings))


# One canonical owner for parameters accepted by every root executor.  The direct
# normalized executor owns compiled fields; typed source functions receive a derived
# lowerer-owned view with optional prompt-only visibility/description overrides.
_ROOT_EXECUTOR_SHARED_TARGET_PARAMS: tuple[EngineParamContract, ...] = (
    _param(
        name="effect",
        prompt_description="|".join(_EXECUTOR_EFFECT_VALUES),
        value_kind=ParamValueKind.ENUM,
        example_value="none",
        compiled_fields=("effect",),
        wire_obligation=WireObligation.FINAL_WIRE,
        enum_values=_EXECUTOR_EFFECT_VALUES,
        function_card_visible=False,
        prompt_group="root_executor",
    ),
    _param(
        name="secondaryDamageMultiplier",
        prompt_description="Shared secondary damage multiplier.",
        value_kind=ParamValueKind.NUMBER,
        example_value=1.0,
        compiled_fields=("secondaryDamageMultiplier",),
        wire_obligation=WireObligation.FINAL_WIRE,
        function_card_visible=False,
        prompt_group="root_executor",
    ),
    _param(
        name="secondaryLifetimeTicks",
        prompt_description="Shared secondary lifetime in ticks.",
        value_kind=ParamValueKind.INTEGER,
        example_value=1,
        compiled_fields=("secondaryLifetimeTicks",),
        wire_obligation=WireObligation.FINAL_WIRE,
        function_card_visible=False,
        prompt_group="root_executor",
    ),
    _param(
        name="soundImpactCatalogId",
        prompt_description="Exact impact sound catalog id.",
        value_kind=ParamValueKind.ENUM,
        example_value="impact_blade",
        compiled_fields=("soundImpactCatalogId",),
        wire_obligation=WireObligation.FINAL_WIRE,
        enum_values=tuple(sorted(IMPACT_SOUND_IDS)),
        function_card_visible=False,
        prompt_group="root_executor",
    ),
    _param(
        name="soundPitch",
        prompt_description="Authored sound pitch.",
        value_kind=ParamValueKind.NUMBER,
        example_value=1.0,
        compiled_fields=("soundPitch",),
        wire_obligation=WireObligation.FINAL_WIRE,
        function_card_visible=False,
        prompt_group="root_executor",
    ),
    _param(
        name="soundPitchVariance",
        prompt_description="Authored sound pitch variance.",
        value_kind=ParamValueKind.NUMBER,
        example_value=1.0,
        compiled_fields=("soundPitchVariance",),
        wire_obligation=WireObligation.FINAL_WIRE,
        function_card_visible=False,
        prompt_group="root_executor",
    ),
    _param(
        name="soundUseCatalogId",
        prompt_description="Exact use sound catalog id.",
        value_kind=ParamValueKind.ENUM,
        example_value="bow_release",
        compiled_fields=("soundUseCatalogId",),
        wire_obligation=WireObligation.FINAL_WIRE,
        enum_values=tuple(sorted(USE_SOUND_IDS)),
        function_card_visible=False,
        prompt_group="root_executor",
    ),
    _param(
        name="soundVolume",
        prompt_description="Authored sound volume.",
        value_kind=ParamValueKind.NUMBER,
        example_value=1.0,
        compiled_fields=("soundVolume",),
        wire_obligation=WireObligation.FINAL_WIRE,
        function_card_visible=False,
        prompt_group="root_executor",
    ),
    _param(
        name="useAnimationTicks",
        prompt_description="Shared root item animation time in ticks.",
        value_kind=ParamValueKind.INTEGER,
        example_value=1,
        compiled_fields=("useAnimationTicks",),
        wire_obligation=WireObligation.FINAL_WIRE,
        function_card_visible=False,
        prompt_group="root_executor",
    ),
    _param(
        name="useTimeTicks",
        prompt_description="Shared root item use time in ticks.",
        value_kind=ParamValueKind.INTEGER,
        example_value=1,
        compiled_fields=("useTimeTicks",),
        wire_obligation=WireObligation.FINAL_WIRE,
        function_card_visible=False,
        prompt_group="root_executor",
    ),
)


def _lowered_root_shared_params(
    *,
    visible: frozenset[str] = frozenset(),
    prompt_overrides: Mapping[str, str] | None = None,
) -> tuple[EngineParamContract, ...]:
    overrides = prompt_overrides or {}
    return tuple(
        replace(
            param,
            prompt_description=overrides.get(param.name, param.prompt_description),
            compiled_fields=(),
            provenance_via_lowerer=True,
            function_card_visible=param.name in visible,
        )
        for param in _ROOT_EXECUTOR_SHARED_TARGET_PARAMS
    )


_ROOT_SHARED_LOWERED_PARAMS = tuple(
    param.name for param in _ROOT_EXECUTOR_SHARED_TARGET_PARAMS
)
_ROOT_PROJECTILE_DIRECT_PARAMS = (
    "speed", "rangeTiles", "lifetimeTicks", "shotCount", "spreadRadians", "pierce",
    "projectileShape", "projectileMotion", "projectileTrail", "projectileImpact",
)


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
        _param(name='armorSlot', prompt_description='|'.join(_ARMOR_SLOT_VALUES) + ' for armor', value_kind=ParamValueKind.ENUM, example_value='head', compiled_fields=('slot',), wire_obligation=WireObligation.FINAL_WIRE, enum_values=_ARMOR_SLOT_VALUES),
        _param(name='defense', prompt_description='armor 0..80', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('defense',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='consumable', prompt_description='true stack-spent; false gear', value_kind=ParamValueKind.BOOLEAN, example_value=False, compiled_fields=('consumable',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='rarity', prompt_description='-1..12', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('rarity',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='value', prompt_description='>=0', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('value',), wire_obligation=WireObligation.FINAL_WIRE),
        ),
        root_executor=False,
        requires_root_executor=False,
        repair_groups=(),
    ),
    EngineFunctionContract(
        name=NORMALIZED_ROOT_FUNCTION_NAME,
        meaning='Low-level root executor; runtimeFamily required. Exactly one root executor owns a use, but delivery=swing with runtimeFamily=shoot keeps the item/tool body hitbox and also emits the projectile.',
        params=(
        _root_required_param(name='delivery', prompt_description='swing|thrust|flail|yoyo|whip|shoot|cast|throw|summon; pair with runtimeFamily', value_kind=ParamValueKind.ENUM, example_value='swing', compiled_fields=('delivery',), wire_obligation=WireObligation.FINAL_WIRE, enum_values=('swing', 'thrust', 'flail', 'yoyo', 'whip', 'shoot', 'cast', 'throw', 'summon')),
        _root_required_param(name='movement', prompt_description='straight|slow_homing|gravity_arc|drift|orbit|boomerang|bounce|sine_homing|phase|accelerate|spiral|vortex_orb|blackhole_pull|proximity_missile|returning_glaive|expanding_wave|flail_tether|yoyo_hover|whip_lash; phase passes tiles', value_kind=ParamValueKind.ENUM, example_value='straight', compiled_fields=('movement',), wire_obligation=WireObligation.FINAL_WIRE, enum_values=('straight', 'slow_homing', 'gravity_arc', 'drift', 'orbit', 'boomerang', 'bounce', 'sine_homing', 'phase', 'accelerate', 'spiral', 'vortex_orb', 'blackhole_pull', 'proximity_missile', 'returning_glaive', 'expanding_wave', 'flail_tether', 'yoyo_hover', 'whip_lash')),
        _root_required_param(name='speed', prompt_description='3..18', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('speed',), wire_obligation=WireObligation.FINAL_WIRE),
        _root_required_param(name='rangeTiles', prompt_description='4..120', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('range', 'rangeTiles'), wire_obligation=WireObligation.FINAL_WIRE),
        _root_required_param(name='lifetimeTicks', prompt_description='25..900', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('lifetime', 'lifetimeTicks'), wire_obligation=WireObligation.FINAL_WIRE),
        _root_required_param(name='shotCount', prompt_description='1..8 simultaneous', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('shotCount',), wire_obligation=WireObligation.FINAL_WIRE),
        _root_required_param(name='spreadRadians', prompt_description='0..0.75', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('spreadRadians',), wire_obligation=WireObligation.FINAL_WIRE),
        _root_required_param(name='pierce', prompt_description='-1=infinite hits; 0 or 1=one target total; 2..10=total NPC hits', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('pierce',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='extraUpdates', prompt_description='0..3', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('extraUpdates',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='homingStrength', prompt_description='0..1', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('homingStrength',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='beamWidthPx', prompt_description='2..96', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('beamWidthPx',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='beamChargeTicks', prompt_description='0..300', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('beamChargeTicks',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='chargeTicks', prompt_description='1..300', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('chargeTicks',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='chargePowerMultiplier', prompt_description='1..3', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('chargePowerMultiplier',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='delayTicks', prompt_description='0..300; overhead_barrage 0=immediate', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('delayTicks',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='immunityCooldown', prompt_description='4..60', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('immunityCooldown',), wire_obligation=WireObligation.FINAL_WIRE),
        _root_required_param(name='runtimeFamily', prompt_description='swing|thrust|returning|flail|yoyo|whip|shoot|cast|beam|charge_release|overhead_barrage|throw|summon; sentry uses deploy_sentry', value_kind=ParamValueKind.ENUM, example_value='swing', compiled_fields=('runtimeFamily',), wire_obligation=WireObligation.FINAL_WIRE, enum_values=('swing', 'thrust', 'returning', 'flail', 'yoyo', 'whip', 'shoot', 'cast', 'beam', 'charge_release', 'overhead_barrage', 'throw', 'summon')),
        _param(name='weaponFamily', prompt_description='exact optional', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=('weaponFamily',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='projectileFamily', prompt_description='visual form', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=('projectileFamily',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='projectileShape', prompt_description='visual body', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=('projectileShape',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='projectileMotion', prompt_description='visual motion', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=('projectileMotion',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='projectileTrail', prompt_description='visual trail', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=('projectileTrail',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='projectileImpact', prompt_description='visual impact', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=('projectileImpact',), wire_obligation=WireObligation.FINAL_WIRE),
        *_ROOT_EXECUTOR_SHARED_TARGET_PARAMS,
        ),
        root_executor=True,
        requires_root_executor=False,
        repair_groups=(
            RepairGroupContract(members=('delivery', 'movement', 'runtimeFamily'), policy_owner='infini_local.core.runtime_authoring.schema.repair_param_allowed_combinations'),
        ),
        normalized_only_params=(
            _internal('ammoFor', 'ammoFor'),
            _internal('channelUse', 'channelUse'),
            _internal('onHit', 'onHit'),
            _internal('secondaryProjectileShape', 'secondaryProjectileShape'),
            _internal('sentryAttackIntervalTicks', 'sentryAttackIntervalTicks'),
            _internal('sentryLifetimeTicks', 'sentryLifetimeTicks'),
            _internal('sentryPlacement', 'sentryPlacement'),
            _internal('sentryTargetRangeTiles', 'sentryTargetRangeTiles'),
        ),
    ),
    EngineFunctionContract(
        name='perform_melee_attack',
        meaning='Body-owned melee/tool swing or explicit projectile-owned melee-family executor.',
        params=(
        _param(name='family', prompt_description='broadsword|sword|pickaxe|axe|hammer|shortsword|rapier|dagger|spear|lance|pike|trident|halberd|naginata|jousting_lance|boomerang|chakram|flail|mace|anchor|yoyo|whip', value_kind=ParamValueKind.ENUM, example_value='broadsword', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, enum_values=('broadsword', 'sword', 'pickaxe', 'axe', 'hammer', 'shortsword', 'rapier', 'dagger', 'spear', 'lance', 'pike', 'trident', 'halberd', 'naginata', 'jousting_lance', 'boomerang', 'chakram', 'flail', 'mace', 'anchor', 'yoyo', 'whip')),
        _param(name='speed', prompt_description='3..18', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='rangeTiles', prompt_description='2..80', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='lifetimeTicks', prompt_description='10..900', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='pierce', prompt_description='-1 infinite; 0/1 one total; 2..10 total', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='shotCount', prompt_description='1..8 simultaneous emitted; not swing count', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='spreadRadians', prompt_description='0..0.75', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='projectileShape', prompt_description='body', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='projectileMotion', prompt_description='motion', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='projectileTrail', prompt_description='trail', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='projectileImpact', prompt_description='impact', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        *_lowered_root_shared_params(
            visible=frozenset({"useTimeTicks"}),
            prompt_overrides={"useTimeTicks": "10..150"},
        ),
        ),
        root_executor=True,
        requires_root_executor=False,
        repair_groups=(),
        lowerers=(
            _lowerer(
                _bind(
                    "family",
                    "runtimeFamily",
                    "delivery",
                    "movement",
                    "weaponFamily",
                    "projectileMotion",
                ),
                *_direct_bindings(
                    *_ROOT_PROJECTILE_DIRECT_PARAMS,
                    *_ROOT_SHARED_LOWERED_PARAMS,
                ),
            ),
        ),
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
        _param(name='projectileFamily', prompt_description='visual form; launcher+empty=custom rocket', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='chargeTicks', prompt_description='1..300 charge_release hold', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='chargePowerMultiplier', prompt_description='1..3 max power', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='projectileShape', prompt_description='body', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='projectileMotion', prompt_description='motion', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='projectileTrail', prompt_description='trail', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='projectileImpact', prompt_description='impact', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        *_lowered_root_shared_params(
            visible=frozenset({"secondaryDamageMultiplier", "secondaryLifetimeTicks"}),
            prompt_overrides={
                "secondaryDamageMultiplier": "0.01..1 barrage damage",
                "secondaryLifetimeTicks": "5..180 barrage life",
            },
        ),
        ),
        root_executor=True,
        requires_root_executor=False,
        repair_groups=(),
        lowerers=(
            _lowerer(
                _bind("$function", "delivery"),
                _bind(
                    "family",
                    "runtimeFamily",
                    "movement",
                    "weaponFamily",
                    "projectileFamily",
                ),
                _bind("projectileFamily", "projectileFamily"),
                *_direct_bindings(
                    "movement",
                    "ammoFor",
                    "chargeTicks",
                    "chargePowerMultiplier",
                    "delayTicks",
                    *_ROOT_PROJECTILE_DIRECT_PARAMS,
                    *_ROOT_SHARED_LOWERED_PARAMS,
                ),
            ),
        ),
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
        _param(name='immunityCooldown', prompt_description='4..60', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='projectileShape', prompt_description='body', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='projectileMotion', prompt_description='motion', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='projectileTrail', prompt_description='trail', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='projectileImpact', prompt_description='impact', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        *_lowered_root_shared_params(
            visible=frozenset({"secondaryDamageMultiplier", "secondaryLifetimeTicks"}),
            prompt_overrides={
                "secondaryDamageMultiplier": "0.01..1 barrage damage",
                "secondaryLifetimeTicks": "5..180 barrage life",
            },
        ),
        ),
        root_executor=True,
        requires_root_executor=False,
        repair_groups=(),
        lowerers=(
            _lowerer(
                _bind("$function", "delivery", "weaponFamily"),
                _bind(
                    "family",
                    "runtimeFamily",
                    "movement",
                    "projectileFamily",
                    "channelUse",
                ),
                _bind("projectileFamily", "projectileFamily"),
                *_direct_bindings(
                    "movement",
                    "homingStrength",
                    "beamWidthPx",
                    "beamChargeTicks",
                    "chargeTicks",
                    "chargePowerMultiplier",
                    "delayTicks",
                    "immunityCooldown",
                    *_ROOT_PROJECTILE_DIRECT_PARAMS,
                    *_ROOT_SHARED_LOWERED_PARAMS,
                ),
            ),
        ),
    ),
    EngineFunctionContract(
        name='deploy_sentry',
        meaning='Stationary sentry firing at NPCs; not a minion.',
        params=(
        _param(name='placement', prompt_description='grounded|floating', value_kind=ParamValueKind.ENUM, example_value='grounded', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, enum_values=('grounded', 'floating')),
        _param(name='attackIntervalTicks', prompt_description='12..180 ticks/volley', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='targetRangeTiles', prompt_description='8..60', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='helperLifetimeTicks', prompt_description='120..36000 root', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='shotCount', prompt_description='1..4/volley', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='speed', prompt_description='3..18', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='spreadRadians', prompt_description='0..0.75', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='pierce', prompt_description='-1 infinite; 0/1 one total; 2..10 total', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='movement', prompt_description='shot movement', value_kind=ParamValueKind.ENUM, example_value='accelerate', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, enum_values=('accelerate', 'blackhole_pull', 'boomerang', 'bounce', 'drift', 'expanding_wave', 'flail_tether', 'gravity_arc', 'orbit', 'phase', 'proximity_missile', 'returning_glaive', 'sine_homing', 'slow_homing', 'spiral', 'straight', 'vortex_orb', 'whip_lash', 'yoyo_hover')),
        _param(name='onHit', prompt_description='non-child effect only: ' + '|'.join(_SENTRY_ONHIT_VALUES), value_kind=ParamValueKind.ENUM, example_value='none', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, enum_values=_SENTRY_ONHIT_VALUES),
        _param(name='projectileShape', prompt_description='sentry body', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        _param(name='secondaryProjectileShape', prompt_description='shot body', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True),
        *_lowered_root_shared_params(
            visible=frozenset({"secondaryLifetimeTicks"}),
            prompt_overrides={
                "secondaryLifetimeTicks": "5..180 shot lifetime; not sentry lifetime",
            },
        ),
        ),
        root_executor=True,
        requires_root_executor=False,
        repair_groups=(),
        lowerers=(
            _lowerer(
                _bind(
                    "$function",
                    "runtimeFamily",
                    "delivery",
                    "weaponFamily",
                    "projectileFamily",
                ),
                _bind("placement", "sentryPlacement"),
                _bind("attackIntervalTicks", "sentryAttackIntervalTicks"),
                _bind("targetRangeTiles", "sentryTargetRangeTiles", "rangeTiles"),
                _bind("helperLifetimeTicks", "sentryLifetimeTicks", "lifetimeTicks"),
                *_direct_bindings(
                    "shotCount",
                    "speed",
                    "spreadRadians",
                    "pierce",
                    "movement",
                    "effect",
                    "onHit",
                    "projectileShape",
                    "secondaryProjectileShape",
                    "secondaryDamageMultiplier",
                    "secondaryLifetimeTicks",
                    "soundUseCatalogId",
                    "soundImpactCatalogId",
                    "soundVolume",
                    "soundPitch",
                    "soundPitchVariance",
                    "useAnimationTicks",
                    "useTimeTicks",
                ),
            ),
        ),
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
        *_lowered_root_shared_params(),
        ),
        root_executor=True,
        requires_root_executor=False,
        repair_groups=(),
        lowerers=(
            _lowerer(
                _bind("$function", "runtimeFamily", "delivery"),
                _bind("family", "movement", "weaponFamily", "projectileFamily"),
                *_direct_bindings(
                    "movement",
                    "speed",
                    "rangeTiles",
                    "lifetimeTicks",
                    "shotCount",
                    "spreadRadians",
                    "pierce",
                    "projectileShape",
                    *_ROOT_SHARED_LOWERED_PARAMS,
                ),
            ),
        ),
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
        repair_groups=(),
    ),
    EngineFunctionContract(
        name='apply_on_hit_effect',
        meaning='Real on-hit gameplay: debuffs, bursts, chained hits, child-producing effects, pull or lifesteal. Visual-only impact belongs in spawn_contact_particles.',
        params=(
        _param(name='onHit', prompt_description='|'.join(_EXECUTOR_ONHIT_VALUES), value_kind=ParamValueKind.ENUM, example_value='none', compiled_fields=('onHit',), wire_obligation=WireObligation.FINAL_WIRE, enum_values=_EXECUTOR_ONHIT_VALUES),
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
        repair_groups=(),
    ),
    EngineFunctionContract(
        name='spawn_contact_particles',
        meaning='Pure projectile contact VFX/dust; no damage. Requires one executable root executor.',
        params=(
        _param(name='effect', prompt_description='|'.join(_PARTICLE_EFFECT_VALUES), value_kind=ParamValueKind.ENUM, example_value='none', compiled_fields=('effect',), wire_obligation=WireObligation.FINAL_WIRE, enum_values=_PARTICLE_EFFECT_VALUES),
        _param(name='amount', prompt_description='0 off; 1..40', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('burstDustCap', 'dustSpawnDenom'), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='scale', prompt_description='0.15..2', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('vfxParticleScale',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='durationTicks', prompt_description='1..80', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('vfxParticleDurationTicks',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='material', prompt_description='none|wood|metal|stone|magic|fire|slime|frost|shadow; only with effect none/dust', value_kind=ParamValueKind.ENUM, example_value='none', compiled_fields=('vfxMaterial',), wire_obligation=WireObligation.FINAL_WIRE, enum_values=('none', 'wood', 'metal', 'stone', 'magic', 'fire', 'slime', 'frost', 'shadow')),
        ),
        root_executor=False,
        requires_root_executor=True,
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
        _param(name='visualOnly', prompt_description='true only', value_kind=ParamValueKind.BOOLEAN, example_value=False, compiled_fields=(), wire_obligation=WireObligation.CONTROL_DERIVED),
        ),
        root_executor=False,
        requires_root_executor=True,
        repair_groups=(),
    ),
    EngineFunctionContract(
        name='visual_effect_cue',
        meaning='Frozen VFX/audio slot; presentation only, no gameplay.',
        params=(
        _param(name='event', prompt_description='|'.join(VFX_CUE_EVENT_VALUES), value_kind=ParamValueKind.ENUM, example_value='travel', compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX, enum_values=VFX_CUE_EVENT_VALUES),
        _param(name='rendererKind', prompt_description='|'.join(VFX_CUE_RENDERER_VALUES), value_kind=ParamValueKind.ENUM, example_value='projectileAfterimage', compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX, enum_values=VFX_CUE_RENDERER_VALUES),
        _param(name='channel', prompt_description='|'.join(VFX_CUE_CHANNEL_VALUES), value_kind=ParamValueKind.ENUM, example_value='motionTrail', compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX, enum_values=VFX_CUE_CHANNEL_VALUES),
        _param(name='lane', prompt_description='|'.join(VFX_CUE_LANE_VALUES), value_kind=ParamValueKind.ENUM, example_value='primary', compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX, enum_values=VFX_CUE_LANE_VALUES),
        _param(name='textureRole', prompt_description='|'.join(VFX_CUE_ROLE_VALUES), value_kind=ParamValueKind.ENUM, example_value='projectile', compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX, enum_values=VFX_CUE_ROLE_VALUES),
        _param(name='particleRole', prompt_description='|'.join(VFX_CUE_ROLE_VALUES), value_kind=ParamValueKind.ENUM, example_value='projectile', compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX, enum_values=VFX_CUE_ROLE_VALUES),
        _param(name='emissionMode', prompt_description='|'.join(VFX_CUE_EMISSION_MODE_VALUES), value_kind=ParamValueKind.ENUM, example_value='wake', compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX, enum_values=VFX_CUE_EMISSION_MODE_VALUES),
        _param(name='particleSystemId', prompt_description='|'.join(VFX_CUE_PARTICLE_SYSTEM_ID_VALUES), value_kind=ParamValueKind.ENUM, example_value='pl:glow', compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX, enum_values=VFX_CUE_PARTICLE_SYSTEM_ID_VALUES),
        _param(name='scale', prompt_description='0.15..5', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX),
        _param(name='density', prompt_description='0..1', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX),
        _param(name='duration', prompt_description='3..120', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX),
        _param(name='alpha', prompt_description='0..1', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX),
        _param(name='spread', prompt_description='0..2', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX),
        _param(name='jitter', prompt_description='0..1.5', value_kind=ParamValueKind.NUMBER, example_value=1.0, compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX),
        _param(name='startTick', prompt_description='0..120', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX),
        _param(name='repeatEvery', prompt_description='0..120', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX),
        _param(name='importance', prompt_description='|'.join(VFX_CUE_IMPORTANCE_VALUES), value_kind=ParamValueKind.ENUM, example_value='core', compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX, enum_values=VFX_CUE_IMPORTANCE_VALUES),
        _param(name='note', prompt_description='short debug', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=('vfxCues',), wire_obligation=WireObligation.DEFERRED_VFX),
        ),
        root_executor=False,
        requires_root_executor=False,
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
        repair_groups=(),
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
        repair_groups=(),
    ),
    EngineFunctionContract(
        name='armor_effect',
        meaning='Armor: slot, defense, equip/set bonuses.',
        params=(
        _param(name='armorSlot', prompt_description='|'.join(_ARMOR_SLOT_VALUES), value_kind=ParamValueKind.ENUM, example_value='head', compiled_fields=('slot',), wire_obligation=WireObligation.FINAL_WIRE, enum_values=_ARMOR_SLOT_VALUES),
        _param(name='setKey', prompt_description='same id for set or empty', value_kind=ParamValueKind.STRING, example_value='value', compiled_fields=('setKey',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='archetype', prompt_description='melee|ranged|magic|summon|defense|mobility|utility|hybrid', value_kind=ParamValueKind.ENUM, example_value='melee', compiled_fields=('archetype',), wire_obligation=WireObligation.FINAL_WIRE, enum_values=('melee', 'ranged', 'magic', 'summon', 'defense', 'mobility', 'utility', 'hybrid')),
        _param(name='defense', prompt_description='0..80', value_kind=ParamValueKind.INTEGER, example_value=1, compiled_fields=('defense',), wire_obligation=WireObligation.FINAL_WIRE),
        _param(name='stats', prompt_description='life/mana/regen/move/jump/classDmg/crit/atkSpeed/kb/minions/light/immunities', value_kind=ParamValueKind.OBJECT, example_value=(), compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, object_model=EquipmentStatsParamBoundary, nested_wire_paths=(NestedWirePathContract(path='aggro', compiled_fields=('aggro',)), NestedWirePathContract(path='ammoSaveChance', compiled_fields=('ammoSaveChance',)), NestedWirePathContract(path='armorPenetration', compiled_fields=('armorPenetration',)), NestedWirePathContract(path='attackSpeed', compiled_fields=('attackSpeed',)), NestedWirePathContract(path='endurance', compiled_fields=('endurance',)), NestedWirePathContract(path='fallDamageImmune', compiled_fields=('fallDamageImmune',)), NestedWirePathContract(path='genericCrit', compiled_fields=('genericCrit',)), NestedWirePathContract(path='genericDamage', compiled_fields=('genericDamage',)), NestedWirePathContract(path='jumpSpeed', compiled_fields=('jumpSpeed',)), NestedWirePathContract(path='knockback', compiled_fields=('knockback',)), NestedWirePathContract(path='lavaImmune', compiled_fields=('lavaImmune',)), NestedWirePathContract(path='lifeRegen', compiled_fields=('lifeRegen',)), NestedWirePathContract(path='lightColorName', compiled_fields=('lightColorName',)), NestedWirePathContract(path='lightStrength', compiled_fields=('lightStrength',)), NestedWirePathContract(path='magicDamage', compiled_fields=('magicDamage',)), NestedWirePathContract(path='manaCostReduction', compiled_fields=('manaCostReduction',)), NestedWirePathContract(path='manaRegen', compiled_fields=('manaRegen',)), NestedWirePathContract(path='maxLife', compiled_fields=('maxLife',)), NestedWirePathContract(path='maxMana', compiled_fields=('maxMana',)), NestedWirePathContract(path='maxRunSpeed', compiled_fields=('maxRunSpeed',)), NestedWirePathContract(path='meleeDamage', compiled_fields=('meleeDamage',)), NestedWirePathContract(path='minionSlots', compiled_fields=('minionSlots',)), NestedWirePathContract(path='movementSpeed', compiled_fields=('movementSpeed',)), NestedWirePathContract(path='rangedDamage', compiled_fields=('rangedDamage',)), NestedWirePathContract(path='sentrySlots', compiled_fields=('sentrySlots',)), NestedWirePathContract(path='summonDamage', compiled_fields=('summonDamage',)), NestedWirePathContract(path='summonTagDamage', compiled_fields=('summonTagDamage',)), NestedWirePathContract(path='waterWalk', compiled_fields=('waterWalk',)), NestedWirePathContract(path='whipRange', compiled_fields=('whipRange',)),)),
        _param(name='setBonus', prompt_description='text,genericDamage,meleeDamage,rangedDamage,magicDamage,summonDamage,genericCrit,movementSpeed,lifeRegen,manaRegen,minionSlots,sentrySlots,manaCostReduction,ammoSaveChance,aggro,endurance,armorPenetration', value_kind=ParamValueKind.OBJECT, example_value=(), compiled_fields=(), wire_obligation=WireObligation.FINAL_WIRE, provenance_via_lowerer=True, object_model=ArmorSetBonusParamBoundary, nested_wire_paths=(NestedWirePathContract(path='aggro', compiled_fields=('setBonusAggro',)), NestedWirePathContract(path='ammoSaveChance', compiled_fields=('setBonusAmmoSaveChance',)), NestedWirePathContract(path='armorPenetration', compiled_fields=('setBonusArmorPenetration',)), NestedWirePathContract(path='endurance', compiled_fields=('setBonusEndurance',)), NestedWirePathContract(path='genericCrit', compiled_fields=('setBonusGenericCrit',)), NestedWirePathContract(path='genericDamage', compiled_fields=('setBonusGenericDamage',)), NestedWirePathContract(path='lifeRegen', compiled_fields=('setBonusLifeRegen',)), NestedWirePathContract(path='magicDamage', compiled_fields=('setBonusMagicDamage',)), NestedWirePathContract(path='manaCostReduction', compiled_fields=('setBonusManaCostReduction',)), NestedWirePathContract(path='manaRegen', compiled_fields=('setBonusManaRegen',)), NestedWirePathContract(path='meleeDamage', compiled_fields=('setBonusMeleeDamage',)), NestedWirePathContract(path='minionSlots', compiled_fields=('setBonusMinionSlots',)), NestedWirePathContract(path='movementSpeed', compiled_fields=('setBonusMovementSpeed',)), NestedWirePathContract(path='rangedDamage', compiled_fields=('setBonusRangedDamage',)), NestedWirePathContract(path='sentrySlots', compiled_fields=('setBonusSentrySlots',)), NestedWirePathContract(path='summonDamage', compiled_fields=('setBonusSummonDamage',)), NestedWirePathContract(path='text', compiled_fields=('setBonusText',)))),
        ),
        root_executor=False,
        requires_root_executor=False,
        repair_groups=(),
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
        repair_groups=(
            RepairGroupContract(members=('mobilityMode', 'mode'), policy_owner='infini_local.core.runtime_authoring.schema.repair_param_allowed_combinations'),
        ),
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
        repair_groups=(),
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
        repair_groups=(),
    ),
)

_CONTRACT_ERRORS = validate_engine_function_contracts(ENGINE_FUNCTION_CONTRACTS)
if _CONTRACT_ERRORS:
    raise RuntimeError("invalid engine function contracts: " + "; ".join(_CONTRACT_ERRORS))

ENGINE_FUNCTION_CONTRACT_BY_NAME = MappingProxyType({spec.name: spec for spec in ENGINE_FUNCTION_CONTRACTS})

# Derived from the terminal normalized root grammar. Adding/removing a mandatory
# root field is therefore one typed registry edit: prompt, repair, validation and
# lowerer parity all consume this projection.
NORMALIZED_ROOT_REQUIRED_PARAM_NAMES: tuple[str, ...] = tuple(
    param.name
    for param in ENGINE_FUNCTION_CONTRACT_BY_NAME[NORMALIZED_ROOT_FUNCTION_NAME].params
    if param.required_on_normalized_root
)
if not NORMALIZED_ROOT_REQUIRED_PARAM_NAMES:
    raise RuntimeError("normalized root contract declares no required parameters")


def _normalize_function_name(fn: object) -> str:
    return str(fn or "").strip().lower().replace("-", "_").replace(" ", "_")


def lowerer_contract(
    source_fn: str,
    target_fn: str | None = None,
) -> EngineLowererContract | None:
    """Return the canonical typed lowering edge, if one exists."""

    source = ENGINE_FUNCTION_CONTRACT_BY_NAME.get(_normalize_function_name(source_fn))
    if source is None:
        return None
    wanted = _normalize_function_name(target_fn) if target_fn is not None else ""
    matches = tuple(
        lowerer for lowerer in source.lowerers
        if not wanted or lowerer.target_function == wanted
    )
    if len(matches) > 1 and not wanted:
        raise RuntimeError(f"ambiguous lowerer for {source.name!r}; specify target_fn")
    return matches[0] if matches else None


def engine_function_impact_names(fn: str) -> frozenset[str]:
    """Return authored function plus every canonical lowerer target transitively."""

    normalized = _normalize_function_name(fn)
    if normalized not in ENGINE_FUNCTION_CONTRACT_BY_NAME:
        return frozenset()
    impacted: set[str] = set()
    pending = [normalized]
    while pending:
        current = pending.pop()
        if current in impacted:
            continue
        impacted.add(current)
        spec = ENGINE_FUNCTION_CONTRACT_BY_NAME[current]
        pending.extend(lowerer.target_function for lowerer in spec.lowerers)
    return frozenset(impacted)


def engine_function_form_impacts(fn: str, param_path: str) -> frozenset[tuple[str, str]]:
    """Map one Author function/param form to normalized replay forms.

    The mapping is projected from the same typed lowerer edge used by normalization.
    It lets affected replay select a narrow case set without maintaining a second
    function-family or alias table. ``$function`` means the function identity itself.
    """

    normalized = _normalize_function_name(fn)
    path = str(param_path or "").strip()
    spec = ENGINE_FUNCTION_CONTRACT_BY_NAME.get(normalized)
    if spec is None or not path:
        return frozenset()
    if path == "$function":
        return frozenset((name, "$function") for name in engine_function_impact_names(normalized))
    if spec.lowerers:
        impacts = {
            (lowerer.target_function, target_path)
            for lowerer in spec.lowerers
            for binding in lowerer.bindings
            if binding.source_path == path
            for target_path in binding.target_param_paths
        }
        return frozenset(impacts)

    declared = {param.name for param in spec.params}
    declared.update(
        f"{param.name}.{nested.path}"
        for param in spec.params
        for nested in param.nested_wire_paths
    )
    return frozenset({(normalized, path)}) if path in declared else frozenset()


def lowerer_passthrough_param_names(source_fn: str, target_fn: str) -> tuple[str, ...]:
    """Top-level source params copied unchanged to the same target param."""

    lowerer = lowerer_contract(source_fn, target_fn)
    if lowerer is None:
        return ()
    return tuple(
        binding.source_path
        for binding in lowerer.bindings
        if binding.source_path != "$function"
        and binding.target_param_paths == (binding.source_path,)
        and "." not in binding.source_path
    )


def lowerer_output_param_names(source_fn: str, target_fn: str) -> frozenset[str]:
    """Closed top-level output grammar emitted by one typed lowerer."""

    lowerer = lowerer_contract(source_fn, target_fn)
    if lowerer is None:
        return frozenset()
    return frozenset(
        str(path).split(".", 1)[0]
        for binding in lowerer.bindings
        for path in binding.target_param_paths
    )


def normalized_root_required_authored_param_names(fn: str) -> tuple[str, ...]:
    """Project authored source params needed by the normalized root grammar.

    Function-identity bindings (``$function``) represent finite lowerer decisions and
    therefore do not create an Author parameter requirement.  Nested source paths
    return their public top-level parameter owner.
    """

    normalized = _normalize_function_name(fn)
    spec = ENGINE_FUNCTION_CONTRACT_BY_NAME.get(normalized)
    if spec is None or not spec.root_executor:
        return ()
    required_targets = set(NORMALIZED_ROOT_REQUIRED_PARAM_NAMES)
    if normalized == NORMALIZED_ROOT_FUNCTION_NAME:
        required_sources = required_targets
    else:
        lowerer = lowerer_contract(normalized, NORMALIZED_ROOT_FUNCTION_NAME)
        if lowerer is None:
            return ()
        required_sources = {
            binding.source_path.split(".", 1)[0]
            for binding in lowerer.bindings
            if binding.source_path != FUNCTION_SOURCE_PATH
            and required_targets.intersection(binding.target_param_paths)
        }
    return tuple(param.name for param in spec.params if param.name in required_sources)


def _path_present(data: dict[str, Any], path: str) -> bool:
    current: Any = data
    for segment in str(path or "").split("."):
        if not segment or not isinstance(current, dict) or segment not in current:
            return False
        current = current[segment]
    return current not in (None, "", [], {})


def lowerer_target_source_map(
    source_fn: str,
    target_fn: str,
    authored_params: dict[str, Any],
    target_params: dict[str, Any],
) -> dict[str, str]:
    """Resolve the actual source owner for each emitted normalized target path.

    Direct same-name parameters win over broader family transforms.  Remaining
    authored bindings win in declaration order; ``$function`` is the final owner for
    invariant fields introduced by selecting the typed function itself.
    """

    lowerer = lowerer_contract(source_fn, target_fn)
    if lowerer is None:
        return {}
    candidates: dict[str, list[str]] = {}
    for binding in lowerer.bindings:
        source = binding.source_path
        if source != "$function" and not _path_present(authored_params, source):
            continue
        for target_path in binding.target_param_paths:
            if not _path_present(target_params, target_path):
                continue
            candidates.setdefault(target_path, []).append(source)

    owners: dict[str, str] = {}
    for target_path, sources in candidates.items():
        direct = next((source for source in sources if source == target_path), None)
        non_function = next((source for source in sources if source != "$function"), None)
        owner = direct or non_function or ("$function" if "$function" in sources else "")
        if owner:
            owners[target_path] = owner
    return owners


def validate_lowerer_output(
    source_fn: str,
    target_fn: str,
    params: dict[str, Any],
) -> tuple[str, ...]:
    """Fail closed when executable lowerer code emits outside its typed grammar."""

    allowed = lowerer_output_param_names(source_fn, target_fn)
    if not allowed:
        return (f"no typed lowerer contract for {source_fn!r}->{target_fn!r}",)
    return tuple(
        f"undeclared lowerer output param {name!r} for {source_fn!r}->{target_fn!r}"
        for name in sorted(str(key) for key in params if not str(key).startswith("_") and str(key) not in allowed)
    )


def _compiled_fields_for_normalized_path(fn: str, param_path: str) -> tuple[str, ...]:
    spec = ENGINE_FUNCTION_CONTRACT_BY_NAME.get(_normalize_function_name(fn))
    path = str(param_path or "").strip()
    if spec is None or not path:
        return ()
    top, dot, child = path.partition(".")
    for param in spec.params:
        if param.name != top:
            continue
        if not dot:
            return tuple(param.compiled_fields)
        return tuple(
            field
            for nested in param.nested_wire_paths
            if nested.path == child
            for field in nested.compiled_fields
        )
    if not dot:
        for param in spec.normalized_only_params:
            if param.name == top:
                return tuple(param.compiled_fields)
    return ()


def compiled_fields_for_authored_path(fn: str, param_path: str) -> frozenset[str]:
    """Resolve one public authored path through the canonical typed lowerer graph."""

    normalized = _normalize_function_name(fn)
    spec = ENGINE_FUNCTION_CONTRACT_BY_NAME.get(normalized)
    path = str(param_path or "").strip()
    if spec is None or not path:
        return frozenset()
    if not spec.lowerers:
        return frozenset(_compiled_fields_for_normalized_path(normalized, path))

    resolved: set[str] = set()
    for lowerer in spec.lowerers:
        for binding in lowerer.bindings:
            if binding.source_path != path:
                continue
            for target_path in binding.target_param_paths:
                resolved.update(_compiled_fields_for_normalized_path(lowerer.target_function, target_path))
    return frozenset(resolved)


def compiled_fields_for_function_identity(fn: str) -> frozenset[str]:
    """Fields selected by choosing a typed function, independent of its params."""

    spec = ENGINE_FUNCTION_CONTRACT_BY_NAME.get(_normalize_function_name(fn))
    if spec is None:
        return frozenset()
    resolved: set[str] = set()
    for lowerer in spec.lowerers:
        for binding in lowerer.bindings:
            if binding.source_path != "$function":
                continue
            for target_path in binding.target_param_paths:
                resolved.update(_compiled_fields_for_normalized_path(lowerer.target_function, target_path))
    return frozenset(resolved)


def compiled_fields_for_lowered_compatibility_path(
    target_fn: str,
    legacy_source_path: str,
    target_params: dict[str, Any],
) -> frozenset[str]:
    """Resolve provenance for legacy dumps that stored post-lowering aliases.

    Older committed replay rows predate ``_authoredFn``/``_authoredParams`` and may
    therefore contain a normalized target function together with both the canonical
    target fields and source aliases left by the old lowerer (for example
    ``shoot_projectile.attackIntervalTicks`` beside
    ``sentryAttackIntervalTicks``).  The compatibility mapping is *derived from the
    incoming typed lowerer graph*; it is not an Author/provider surface and does not
    create a second list of aliases.
    """

    normalized_target = _normalize_function_name(target_fn)
    source_path = str(legacy_source_path or "").strip()
    if not normalized_target or not source_path or source_path == "$function":
        return frozenset()

    # A real target-owned parameter always wins.  This helper is only a fallback for
    # legacy source aliases that are not part of the target contract.
    if _compiled_fields_for_normalized_path(normalized_target, source_path):
        return frozenset()

    resolved: set[str] = set()
    for source_spec in ENGINE_FUNCTION_CONTRACTS:
        for lowerer in source_spec.lowerers:
            if _normalize_function_name(lowerer.target_function) != normalized_target:
                continue
            for binding in lowerer.bindings:
                if binding.source_path != source_path:
                    continue
                for target_path in binding.target_param_paths:
                    if not _path_present(target_params, target_path):
                        continue
                    resolved.update(
                        _compiled_fields_for_normalized_path(normalized_target, target_path)
                    )
    return frozenset(resolved)


def _model_contract_name(model: type[Any] | None) -> str | None:
    if model is None:
        return None
    return f"{model.__module__}.{model.__qualname__}"


def _json_contract_value(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_json_contract_value(child) for child in value]
    if isinstance(value, (str, bool, int, float)) or value is None:
        return value
    return str(value)


def engine_function_contract_surface() -> dict[str, dict[str, Any]]:
    """Project the public Author contract plus the narrow typed lowering boundary."""

    out: dict[str, dict[str, Any]] = {}
    for spec in ENGINE_FUNCTION_CONTRACTS:
        params: dict[str, dict[str, Any]] = {}
        for param in spec.params:
            value_kind = param.value_kind.value if isinstance(param.value_kind, ParamValueKind) else str(param.value_kind)
            obligation = param.wire_obligation.value if isinstance(param.wire_obligation, WireObligation) else str(param.wire_obligation)
            param_row = {
                "promptDescription": param.prompt_description,
                "valueKind": value_kind,
                "exampleValue": _json_contract_value(param.example_value),
                "enumValues": list(param.enum_values),
                "stringPattern": param.string_pattern,
                "objectModel": _model_contract_name(param.object_model),
                "listItemModel": _model_contract_name(param.list_item_model),
                "compiledFields": list(param.compiled_fields),
                "wireObligation": obligation,
                "provenanceViaLowerer": param.provenance_via_lowerer,
                "functionCardVisible": param.function_card_visible,
                "promptGroup": param.prompt_group,
                "nestedWirePaths": [
                    {"path": nested.path, "compiledFields": list(nested.compiled_fields)}
                    for nested in param.nested_wire_paths
                ],
            }
            if param.required_on_normalized_root:
                param_row["requiredOnNormalizedRoot"] = True
            params[param.name] = param_row
        out[spec.name] = {
            "rootExecutor": spec.root_executor,
            "requiresRootExecutor": spec.requires_root_executor,
            "paramOrder": [param.name for param in spec.params],
            "params": params,
            "repairGroups": [
                {"members": list(group.members), "policyOwner": group.policy_owner}
                for group in spec.repair_groups
            ],
            "normalizedOnlyParams": {
                param.name: list(param.compiled_fields)
                for param in spec.normalized_only_params
            },
            "lowerers": [
                {
                    "targetFunction": lowerer.target_function,
                    "bindings": [
                        {
                            "sourcePath": binding.source_path,
                            "targetParamPaths": list(binding.target_param_paths),
                        }
                        for binding in lowerer.bindings
                    ],
                }
                for lowerer in spec.lowerers
            ],
        }
    return out


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
    spec = ENGINE_FUNCTION_CONTRACT_BY_NAME.get(_normalize_function_name(fn))
    return frozenset(param.name for param in spec.params) if spec is not None else frozenset()


def engine_param_wire_obligation(fn: str, param_path: str) -> WireObligation | None:
    """Return the canonical top-level provenance obligation for one authored leaf."""

    spec = ENGINE_FUNCTION_CONTRACT_BY_NAME.get(_normalize_function_name(fn))
    param_name = str(param_path or "").strip().split(".", 1)[0]
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


def _authored_paths(spec: EngineFunctionContract) -> tuple[str, ...]:
    return tuple(
        path
        for param in spec.params
        for path in (
            (param.name,)
            if not param.nested_wire_paths
            else (param.name, *(f"{param.name}.{nested.path}" for nested in param.nested_wire_paths))
        )
    )


def compiled_field_source_map() -> dict[str, dict[str, str | tuple[str, ...]]]:
    """Project public authored provenance; lowerer/internal aliases are derived."""

    out: dict[str, dict[str, str | tuple[str, ...]]] = {}
    for spec in ENGINE_FUNCTION_CONTRACTS:
        sources_by_field: dict[str, list[str]] = {}
        for source_path in _authored_paths(spec):
            for field in compiled_fields_for_authored_path(spec.name, source_path):
                sources_by_field.setdefault(field, []).append(source_path)
        if sources_by_field:
            out[spec.name] = {
                field: sources[0] if len(sources) == 1 else tuple(dict.fromkeys(sources))
                for field, sources in sorted(sources_by_field.items())
            }
    return out


ROOT_EXECUTOR_FUNCTION_NAMES = frozenset(spec.name for spec in ENGINE_FUNCTION_CONTRACTS if spec.root_executor)
ENGINE_FUNCTION_CATALOG = MappingProxyType(engine_function_catalog())
ACCEPTED_PARAM_EXTRAS_BY_FUNCTION = MappingProxyType(accepted_param_extras())
REPAIR_DEPENDENCY_GROUPS_BY_FUNCTION = MappingProxyType(repair_dependency_groups())
ROOT_EXECUTOR_SHARED_PARAM_NAMES = frozenset(
    param.name for param in _ROOT_EXECUTOR_SHARED_TARGET_PARAMS
)

__all__ = [
    "ENGINE_FUNCTION_CONTRACTS",
    "ENGINE_FUNCTION_CONTRACT_BY_NAME",
    "ENGINE_FUNCTION_CATALOG",
    "ACCEPTED_PARAM_EXTRAS_BY_FUNCTION",
    "REPAIR_DEPENDENCY_GROUPS_BY_FUNCTION",
    "ROOT_EXECUTOR_FUNCTION_NAMES",
    "ROOT_EXECUTOR_SHARED_PARAM_NAMES",
    "NORMALIZED_ROOT_FUNCTION_NAME",
    "NORMALIZED_ROOT_REQUIRED_PARAM_NAMES",
    "lowerer_contract",
    "lowerer_passthrough_param_names",
    "lowerer_output_param_names",
    "normalized_root_required_authored_param_names",
    "lowerer_target_source_map",
    "validate_lowerer_output",
    "engine_function_impact_names",
    "engine_function_form_impacts",
    "compiled_fields_for_authored_path",
    "compiled_fields_for_function_identity",
    "compiled_fields_for_lowered_compatibility_path",
    "engine_function_contract_surface",
    "engine_function_catalog",
    "accepted_engine_param_names",
    "engine_param_wire_obligation",
    "accepted_param_extras",
    "repair_dependency_groups",
    "compiled_field_source_map",
]
