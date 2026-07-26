from __future__ import annotations

from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any, Final, Iterable, Mapping

from infini_local.core.runtime_authoring.terraria_vocabulary import (
    DAMAGE_CLASS_TOKEN_PATTERN,
    DAMAGE_CLASS_TOKENS,
    ITEM_USE_STYLE_TOKENS,
    VANILLA_AMMO_CATEGORY_TOKENS,
    VANILLA_PROJECTILE_TYPE_ID_MAX,
)


RUNTIME_PROGRAM_API_VERSION: Final[str] = "infini.runtime-program.v5"
RUNTIME_PROGRAM_SCHEMA: Final[str] = "infini.runtime-program.authoring.v2"
RUNTIME_WIRE_SCHEMA: Final[str] = "infini.runtime-program.wire.v1"

ENTITY_KINDS: Final[tuple[str, ...]] = (
    "item_body",
    "owner_attached_projectile",
    "free_projectile",
    "stationary_projectile",
    "temporary_helper",
    "field",
    "child_projectile",
)
PROJECTILE_ENTITY_KIND_ORDER: Final[tuple[str, ...]] = ENTITY_KINDS[1:]
PROJECTILE_ENTITY_KINDS: Final[frozenset[str]] = frozenset(PROJECTILE_ENTITY_KIND_ORDER)
VISUAL_ROLE_BY_ENTITY_KIND: Final[Mapping[str, str]] = MappingProxyType({
    "item_body": "inventory_item",
    "owner_attached_projectile": "held_body",
    "free_projectile": "projectile",
    "stationary_projectile": "deployed_entity",
    "temporary_helper": "helper",
    "field": "field",
    "child_projectile": "child_projectile",
})

INPUT_KINDS: Final[tuple[str, ...]] = (
    "primary_use",
    "alternate_use",
    "hold",
    "equipped",
)
BINDING_ACTIONS: Final[tuple[str, ...]] = (
    "spawn_entity",
    "use_item_body",
    "apply_item_effects",
    "place_item",
    "equip_passive",
)
EVENT_KINDS: Final[tuple[str, ...]] = (
    "on_use",
    "on_spawn",
    "on_hit",
    "on_crit",
    "on_tile_collision",
    "on_expire",
    "on_kill",
    "periodic",
    "on_release",
    "channel_complete",
)
NETWORK_AUTHORITIES: Final[tuple[str, ...]] = (
    "owner_request_server_execute",
    "server_execute",
    "owner_execute_sync",
    "client_visual_only",
)


@dataclass(frozen=True, slots=True)
class ReferenceSpec:
    namespace: str
    target_kinds: tuple[str, ...] = ()
    allow_self: bool = False
    graph_edge: bool = False

    def card(self) -> dict[str, Any]:
        return {
            "namespace": self.namespace,
            "targetKinds": list(self.target_kinds),
            "allowSelf": self.allow_self,
            "graphEdge": self.graph_edge,
        }


@dataclass(frozen=True, slots=True)
class RequirementSpec:
    kind: str
    capability: str = ""
    target: str = "same_target"
    param: str = ""
    equals: Any = None
    any_of: tuple[str, ...] = ()
    message: str = ""

    def card(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": self.kind, "target": self.target}
        if self.capability:
            out["capability"] = self.capability
        if self.param:
            out["param"] = self.param
            out["equals"] = self.equals
        if self.any_of:
            out["anyOf"] = list(self.any_of)
        if self.message:
            out["message"] = self.message
        return out


@dataclass(frozen=True, slots=True)
class EntityKindSpec:
    name: str
    summary: str
    visual_role: str
    projectile: bool
    spawnable_by_binding: bool
    position_requirement: str
    required_components: tuple[str, ...]
    base_events: tuple[str, ...]
    requires_position_driver: bool = False

    def prompt_card(self) -> dict[str, Any]:
        return {
            "kind": self.name,
            "does": self.summary,
            "visualRole": self.visual_role,
            "projectile": self.projectile,
            "spawnableByBinding": self.spawnable_by_binding,
            "positionRequirement": self.position_requirement,
            "requiredComponents": list(self.required_components),
            "baseEvents": list(self.base_events),
            "requiresPositionDriver": self.requires_position_driver,
        }


@dataclass(frozen=True, slots=True)
class InputKindSpec:
    name: str
    exclusive: bool
    allowed_actions: tuple[str, ...]
    summary: str
    required_item_capabilities_any_of: tuple[str, ...] = ()

    def prompt_card(self) -> dict[str, Any]:
        return {
            "input": self.name,
            "exclusive": self.exclusive,
            "actions": list(self.allowed_actions),
            "does": self.summary,
            "requiresItemAnyOf": list(self.required_item_capabilities_any_of),
        }


@dataclass(frozen=True, slots=True)
class BindingActionSpec:
    name: str
    target_kinds: tuple[str, ...]
    allowed_inputs: tuple[str, ...]
    summary: str
    required_item_capabilities_any_of: tuple[str, ...] = ()

    def prompt_card(self) -> dict[str, Any]:
        return {
            "action": self.name,
            "targets": list(self.target_kinds),
            "inputs": list(self.allowed_inputs),
            "does": self.summary,
            "requiresItemAnyOf": list(self.required_item_capabilities_any_of),
        }


@dataclass(frozen=True, slots=True)
class EventKindSpec:
    name: str
    source_kinds: tuple[str, ...]
    producer_capabilities: tuple[str, ...]
    always_available_on_projectile: bool
    summary: str

    def prompt_card(self) -> dict[str, Any]:
        return {
            "event": self.name,
            "sources": list(self.source_kinds),
            "producedBy": list(self.producer_capabilities),
            "projectileBaseEvent": self.always_available_on_projectile,
            "does": self.summary,
        }


@dataclass(frozen=True, slots=True)
class ParamSpec:
    kind: str
    description: str
    required: bool = True
    minimum: float | int | None = None
    maximum: float | int | None = None
    enum: tuple[Any, ...] = ()
    pattern: str | None = None
    units: str = ""
    semantic_type: str = ""
    reference: ReferenceSpec | None = None
    default: Any = field(default=None, compare=False)

    def schema(self) -> dict[str, Any]:
        out: dict[str, Any] = {"type": self.kind}
        if self.minimum is not None:
            out["minimum"] = self.minimum
        if self.maximum is not None:
            out["maximum"] = self.maximum
        if self.enum:
            out["enum"] = list(self.enum)
        if self.pattern:
            out["pattern"] = self.pattern
        if self.description:
            out["description"] = self.description
        if self.units:
            out["x-infini-units"] = self.units
        if self.semantic_type:
            out["x-infini-semanticType"] = self.semantic_type
        if self.reference is not None:
            out["x-infini-reference"] = self.reference.card()
        if self.default is not None:
            out["default"] = self.default
        return out


@dataclass(frozen=True, slots=True)
class CapabilitySpec:
    name: str
    summary: str
    category: str
    target_kinds: tuple[str, ...]
    params: Mapping[str, ParamSpec]
    multiplicity: str
    network_authority: str
    performance_budget: str
    compiler_owner: str
    csharp_owner: str
    final_wire_paths: tuple[str, ...]
    provenance: str
    repair_group: str
    allowed_events: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    prompt_visible: bool = True
    implementation_status: str = "refactored"
    decision: str = "expose"
    technical_lowering_outputs: tuple[str, ...] = ()
    component_slot: str = ""
    exclusive_group: str = ""
    position_ownership: str = "none"
    emitted_events: tuple[str, ...] = ()
    requirements: tuple[RequirementSpec, ...] = ()
    authority_by_effect: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}), compare=False)
    activation_spawn_count_param: str = ""
    meaningful_for_stationary: bool = False

    def provider_variant_schema(self) -> dict[str, Any]:
        properties = {name: spec.schema() for name, spec in self.params.items()}
        required = [name for name, spec in self.params.items() if spec.required]
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "id": {
                    "type": "string",
                    "pattern": r"^[a-z][a-z0-9_]{0,47}$",
                    "description": "Stable call id used by claims and repair.",
                },
                "fn": {"const": self.name},
                "target": {
                    "type": "string",
                    "pattern": r"^[a-z][a-z0-9_]{0,47}$",
                    "description": "Authored entity id. Target kind is checked locally.",
                    "x-infini-reference": {
                        "namespace": "entity",
                        "targetKinds": list(self.target_kinds),
                        "allowSelf": True,
                        "graphEdge": False,
                    },
                },
                "params": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": properties,
                    "required": required,
                },
            },
            "required": ["id", "fn", "target", "params"],
        }

    def prompt_card(self) -> dict[str, Any]:
        params: dict[str, dict[str, Any]] = {}
        for name, spec in self.params.items():
            row: dict[str, Any] = {
                "type": spec.kind,
                "required": spec.required,
                "meaning": spec.description,
            }
            if spec.minimum is not None:
                row["min"] = spec.minimum
            if spec.maximum is not None:
                row["max"] = spec.maximum
            if spec.enum:
                row["enum"] = list(spec.enum)
            if spec.units:
                row["units"] = spec.units
            if spec.semantic_type:
                row["semanticType"] = spec.semantic_type
            if spec.reference is not None:
                row["reference"] = spec.reference.card()
            if spec.default is not None:
                row["default"] = spec.default
            params[name] = row
        authority: Any = self.network_authority
        if self.authority_by_effect:
            authority = {"primary": self.network_authority, "byEffect": dict(self.authority_by_effect)}
        return {
            "fn": self.name,
            "does": self.summary,
            "slot": self.component_slot,
            "exclusiveGroup": self.exclusive_group or None,
            "positionOwnership": self.position_ownership,
            "targets": list(self.target_kinds),
            "params": params,
            "acceptedEvents": list(self.allowed_events),
            "emitsEvents": list(self.emitted_events),
            "requires": [row.card() for row in self.requirements],
            "multiplicity": self.multiplicity,
            "authority": authority,
            "budget": self.performance_budget,
            "activationSpawnCountParam": self.activation_spawn_count_param or None,
            "meaningfulForStationary": self.meaningful_for_stationary,
        }



def _p(
    kind: str,
    description: str,
    *,
    required: bool = True,
    minimum: float | int | None = None,
    maximum: float | int | None = None,
    enum: Iterable[Any] = (),
    pattern: str | None = None,
    units: str = "",
    semantic_type: str = "",
    reference: ReferenceSpec | None = None,
    default: Any = None,
) -> ParamSpec:
    return ParamSpec(
        kind=kind,
        description=description,
        required=required,
        minimum=minimum,
        maximum=maximum,
        enum=tuple(enum),
        pattern=pattern,
        units=units,
        semantic_type=semantic_type,
        reference=reference,
        default=default,
    )


def _cap(
    name: str,
    summary: str,
    category: str,
    targets: Iterable[str],
    params: Mapping[str, ParamSpec],
    *,
    multiplicity: str = "single_per_target",
    authority: str = "server_execute",
    budget: str = "bounded by runtime program limits",
    py: str,
    cs: str,
    wire: Iterable[str],
    provenance: str,
    repair_group: str,
    events: Iterable[str] = (),
    dependencies: Iterable[str] = (),
    conflicts: Iterable[str] = (),
    lowering: Iterable[str] = (),
    status: str = "refactored",
    decision: str = "expose",
    component_slot: str = "",
    exclusive_group: str = "",
    position_ownership: str = "none",
    emitted_events: Iterable[str] = (),
    requirements: Iterable[RequirementSpec] = (),
    authority_by_effect: Mapping[str, str] | None = None,
    activation_spawn_count_param: str = "",
    meaningful_for_stationary: bool = False,
) -> CapabilitySpec:
    target_values = tuple(targets)
    target_set = set(target_values)
    ordered_targets = tuple(kind for kind in ENTITY_KINDS if kind in target_set) if target_set.issubset(set(ENTITY_KINDS)) else target_values
    return CapabilitySpec(
        name=name,
        summary=summary,
        category=category,
        target_kinds=ordered_targets,
        params=MappingProxyType(dict(params)),
        multiplicity=multiplicity,
        network_authority=authority,
        performance_budget=budget,
        compiler_owner=py,
        csharp_owner=cs,
        final_wire_paths=tuple(wire),
        provenance=provenance,
        repair_group=repair_group,
        allowed_events=tuple(events),
        dependencies=tuple(dependencies),
        conflicts=tuple(conflicts),
        technical_lowering_outputs=tuple(lowering),
        implementation_status=status,
        decision=decision,
        component_slot=component_slot,
        exclusive_group=exclusive_group,
        position_ownership=position_ownership,
        emitted_events=tuple(emitted_events),
        requirements=tuple(requirements),
        authority_by_effect=MappingProxyType(dict(authority_by_effect or {})),
        activation_spawn_count_param=activation_spawn_count_param,
        meaningful_for_stationary=meaningful_for_stationary,
    )


_DAMAGE_CLASS = DAMAGE_CLASS_TOKENS
_DAMAGE_CLASS_PATTERN = DAMAGE_CLASS_TOKEN_PATTERN
_COLOR = ("white", "red", "orange", "yellow", "green", "cyan", "blue", "purple", "pink", "gray", "black")
_USE_STYLE = ITEM_USE_STYLE_TOKENS
_MOVEMENT_OWNER = "InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile.Executors.cs"
_MODEL_OWNER = "InfiniCrafterLocal.Common.Models.RuntimeProgramSpec.cs"
_COMPILER_OWNER = "infini_local.core.runtime_authoring.compiler::compile_runtime_program"


_CAPS: list[CapabilitySpec] = [
    _cap(
        "configure_item_stats",
        "Set exact item stats; no weapon class or behaviour is inferred.",
        "item",
        ("item_body",),
        {
            "damageClass": _p("string", "Exact built-in token or loaded tModLoader ModName/ClassName copied from parent facts", pattern=_DAMAGE_CLASS_PATTERN, semantic_type="terraria_damage_class"),
            "damage": _p("integer", "Base item damage", minimum=0, maximum=2000),
            "knockback": _p("number", "Item knockback", minimum=0, maximum=20),
            "useTimeTicks": _p("integer", "Use time", minimum=1, maximum=600, units="ticks"),
            "useAnimationTicks": _p("integer", "Use animation", minimum=1, maximum=600, units="ticks"),
            "manaCost": _p("integer", "Mana consumed per use", minimum=0, maximum=500),
            "rarity": _p("integer", "Exact loaded Item.rare ID (built-in normal rarities are 0..11); copy modded IDs from parent facts, do not guess", minimum=0, maximum=65535, semantic_type="loaded_rarity_id"),
            "valueCopper": _p("integer", "Exact Terraria Item.value field in copper; NPC shop price/base value, not an inferred player resale amount", minimum=0, maximum=100000000, units="copper"),
            "maxStack": _p("integer", "Maximum stack", minimum=1, maximum=9999),
            "craftYield": _p("integer", "Items granted by one craft", minimum=1, maximum=9999),
            "widthPx": _p("integer", "Inventory/world hitbox width", minimum=8, maximum=256, units="pixels"),
            "heightPx": _p("integer", "Inventory/world hitbox height", minimum=8, maximum=256, units="pixels"),
            "scale": _p("number", "Item draw scale", minimum=0.25, maximum=4),
        },
        py=_COMPILER_OWNER,
        cs="GeneratedItemData.Apply.cs::ApplyToItem",
        wire=("gameplay.*",),
        provenance="existing set_item_stats fields split from weapon roots",
        repair_group="item_stats",
        lowering=("gameplay.damageClass", "gameplay.damage", "gameplay.knockback", "gameplay.useTime", "gameplay.useAnimation", "gameplay.manaCost", "gameplay.rarity", "gameplay.value", "gameplay.maxStack", "gameplay.craftYield", "gameplay.width", "gameplay.height", "gameplay.itemScale"),
    ),
    _cap(
        "configure_item_use",
        "Set exact item use/draw/input affordances.",
        "item",
        ("item_body",),
        {
            "useStyle": _p("string", "Named Terraria ItemUseStyleID", enum=_USE_STYLE),
            "autoReuse": _p("boolean", "Allow repeated use while input is held"),
            "useTurn": _p("boolean", "Allow facing turn during use"),
            "hideUseGraphic": _p("boolean", "Hide inventory sprite during use"),
            "disableMeleeHitbox": _p("boolean", "Disable vanilla item melee hitbox"),
            "channel": _p("boolean", "Keep use active while input is held"),
            "holdoutOffsetX": _p("integer", "Held draw offset X", minimum=-96, maximum=96, units="pixels"),
            "holdoutOffsetY": _p("integer", "Held draw offset Y", minimum=-96, maximum=96, units="pixels"),
            "handPose": _p("string", "Exact renderer hint", required=False, enum=("", "one_handed", "two_handed", "overhead", "forward")),
            "releaseTiming": _p("string", "Exact release timing", required=False, enum=("", "immediate", "on_release", "after_charge")),
        },
        py=_COMPILER_OWNER,
        cs="GeneratedItem.cs::CanUseItem/UseStyle",
        wire=("gameplay.useStyleName", "gameplay.autoReuse", "gameplay.useTurn", "gameplay.channelUse", "gameplay.holdoutOffsetX", "gameplay.holdoutOffsetY", "gameplay.handPose", "gameplay.releaseTiming", "runtimeProgram.itemUse.*"),
        provenance="existing use_affordance and explicit root affordance fields",
        repair_group="item_use",
        lowering=("gameplay.useStyle", "gameplay.autoReuse", "gameplay.useTurn", "gameplay.channelUse", "runtimeProgram.itemUse.*"),
    ),
    _cap(
        "enable_item_contact_damage",
        "Enable the authored item body's vanilla contact hitbox.",
        "item_combat",
        ("item_body",),
        {
            "hitboxScale": _p("number", "Contact hitbox scale", minimum=0.5, maximum=2),
            "contactForgivenessPx": _p("integer", "Extra contact radius", minimum=0, maximum=64, units="pixels"),
        },
        py=_COMPILER_OWNER,
        cs="GeneratedItem.cs::UseItemHitbox/OnHitNPC",
        wire=("runtimeProgram.itemContact.*",),
        provenance="existing swing/item-hitbox executor extracted from melee root",
        repair_group="item_contact",
    ),
    _cap(
        "configure_consumption",
        "Set exact stack-consumption behaviour. This does not mark the item as ammunition.",
        "item",
        ("item_body",),
        {
            "consumable": _p("boolean", "Consume stack on use"),
            "consumeChancePercent": _p("integer", "Chance of stack consumption", minimum=0, maximum=100, units="percent"),
        },
        py=_COMPILER_OWNER,
        cs="GeneratedItem.cs::ConsumeItem",
        wire=("gameplay.consumable", "gameplay.consumeChancePercent"),
        provenance="existing consumption_behavior separated from Terraria ammo identity",
        repair_group="consumption",
        lowering=("gameplay.consumable", "gameplay.consumeChancePercent"),
    ),
    _cap(
        "configure_vanilla_ammo_item",
        "Mark this generated item as one exact vanilla ammo category and projectile. Sets Item.ammo and Item.shoot; it does not configure a weapon to consume ammo.",
        "item",
        ("item_body",),
        {
            "ammoCategory": _p("string", "Exact stable Terraria AmmoID category", enum=VANILLA_AMMO_CATEGORY_TOKENS),
            "projectileId": _p("integer", "Exact vanilla ProjectileID fired when this ammo is consumed; do not guess", minimum=1, maximum=VANILLA_PROJECTILE_TYPE_ID_MAX),
            "shootSpeedPxPerTick": _p("number", "Exact Item.shootSpeed contribution of this ammo to vanilla PickAmmo", minimum=-20, maximum=80, units="pixels_per_tick"),
            "notAmmo": _p("boolean", "Exact Item.notAmmo flag for special ammo-slot/tooltip behaviour"),
        },
        py=_COMPILER_OWNER,
        cs="TerrariaRuntimeVocabulary.cs::ResolveAmmoCategory/GeneratedItemData.Apply.cs::ApplyToItem",
        wire=("gameplay.ammoCategory", "gameplay.ammoProjectileId", "gameplay.ammoShootSpeedPxPerTick", "gameplay.notAmmo"),
        provenance="existing ammo_behavior split into direct Terraria Item.ammo and Item.shoot fields",
        repair_group="ammo_item",
        lowering=("gameplay.ammoCategory", "gameplay.ammoProjectileId", "gameplay.ammoShootSpeedPxPerTick", "gameplay.notAmmo"),
        requirements=(RequirementSpec(
            kind="capability_param",
            capability="configure_consumption",
            target="same_target",
            param="consumable",
            equals=True,
            message="A vanilla ammo item must also be an explicitly consumable stack.",
        ),),
    ),
    _cap(
        "restore_resources_on_use",
        "Restore exact life and/or mana when use succeeds.",
        "item_utility",
        ("item_body",),
        {
            "healLife": _p("integer", "Life restored", minimum=0, maximum=500),
            "healMana": _p("integer", "Mana restored", minimum=0, maximum=500),
            "potionSickness": _p("boolean", "Set exact Terraria Item.potion flag; false allows non-potion healing items"),
        },
        py=_COMPILER_OWNER,
        cs="GeneratedItemData.Apply.cs::ApplyToItem",
        wire=("gameplay.healLife", "gameplay.healMana", "gameplay.potion"),
        provenance="existing healing item fields",
        repair_group="resource_restore",
        lowering=("gameplay.healLife", "gameplay.healMana", "gameplay.potion"),
    ),
    _cap(
        "apply_vanilla_buff_on_use",
        "Apply one concrete Terraria buff when use succeeds.",
        "item_utility",
        ("item_body",),
        {
            "buffId": _p("integer", "Exact loaded BuffID/ModContent.BuffType; copy from parent facts, do not guess", minimum=1, maximum=65535, semantic_type="loaded_buff_id"),
            "durationTicks": _p("integer", "Buff duration", minimum=1, maximum=21600, units="ticks"),
        },
        multiplicity="many_per_target",
        py=_COMPILER_OWNER,
        cs="GeneratedItem.cs::UseItem",
        wire=("gameplay.buffCode", "gameplay.buffTime", "gameplay.extraBuffs[].*"),
        provenance="existing apply_player_effect_on_use buff path",
        repair_group="use_buffs",
        lowering=("gameplay.buffCode", "gameplay.buffTime", "gameplay.extraBuffs[]"),
    ),
    _cap(
        "apply_generated_buff_on_use",
        "Apply a bounded generated stat/light/ore-sense buff.",
        "item_utility",
        ("item_body",),
        {
            "durationTicks": _p("integer", "Duration", minimum=1, maximum=21600, units="ticks"),
            "miningSpeedMultiplier": _p("number", "Mining-time multiplier", minimum=0.25, maximum=4),
            "lightStrength": _p("number", "Emitted light", minimum=0, maximum=1.5),
            "lightColor": _p("string", "Canonical light color", enum=_COLOR),
            "oreSenseRadiusTiles": _p("integer", "Ore-sense radius", minimum=0, maximum=60, units="tiles"),
            "movementSpeed": _p("number", "Additive movement speed", minimum=-0.5, maximum=2),
            "jumpBoost": _p("number", "Jump speed bonus", minimum=0, maximum=8),
            "manaRegen": _p("integer", "Mana regeneration bonus", minimum=0, maximum=120),
            "lifeRegen": _p("integer", "Life regeneration bonus", minimum=0, maximum=120),
        },
        py=_COMPILER_OWNER,
        cs="GeneratedItem.cs::UseItem/InfiniCraftPlayer",
        wire=("gameplay.generatedBuff.*",),
        provenance="existing generated-buff executor",
        repair_group="generated_buff",
        lowering=("gameplay.generatedBuff.*",),
    ),
    _cap(
        "configure_tool",
        "Set exact pick/axe/hammer powers and mining speed.",
        "item_tool",
        ("item_body",),
        {
            "pickPower": _p("integer", "Pickaxe power", minimum=0, maximum=1000),
            "axePower": _p("integer", "Exact Terraria Item.axe internal power; the in-game tooltip displays this value multiplied by 5", minimum=0, maximum=100, units="Item.axe units"),
            "hammerPower": _p("integer", "Hammer power", minimum=0, maximum=1000),
            "miningSpeedScale": _p("number", "Use-time multiplier while mining", minimum=0.1, maximum=4),
        },
        py=_COMPILER_OWNER,
        cs="GeneratedItemData.Apply.cs::ApplyToItem",
        wire=("gameplay.pickPower", "gameplay.axePower", "gameplay.hammerPower", "gameplay.miningSpeedScale"),
        provenance="existing tool_capability",
        repair_group="tool",
        lowering=("gameplay.pickPower", "gameplay.axePower", "gameplay.hammerPower", "gameplay.miningSpeedScale"),
    ),
    _cap(
        "configure_placeable",
        "Set one concrete tile/wall placement result.",
        "item_placeable",
        ("item_body",),
        {
            "tileId": _p("integer", "Exact loaded TileID/ModContent.TileType; -1 disables", minimum=-1, maximum=65535, semantic_type="loaded_tile_id"),
            "wallId": _p("integer", "Exact loaded WallID/ModContent.WallType; -1 disables", minimum=-1, maximum=65535, semantic_type="loaded_wall_id"),
            "placeStyle": _p("integer", "Placement style", minimum=0, maximum=255),
        },
        py=_COMPILER_OWNER,
        cs="GeneratedItemData.Apply.cs::ApplyToItem",
        wire=("gameplay.createTile", "gameplay.createWall", "gameplay.placeStyle"),
        provenance="existing placeable_behavior",
        repair_group="placeable",
        lowering=("gameplay.createTile", "gameplay.createWall", "gameplay.placeStyle"),
    ),
    _cap(
        "require_use_condition",
        "Gate use on one explicit runtime condition.",
        "item",
        ("item_body",),
        {
            "mode": _p("string", "Use condition", enum=("grounded", "not_wet", "life_above", "mana_above")),
            "minLife": _p("integer", "Required life for life_above", required=False, minimum=0, maximum=1000),
            "minMana": _p("integer", "Required mana for mana_above", required=False, minimum=0, maximum=1000),
        },
        py=_COMPILER_OWNER,
        cs="GeneratedItem.cs::CanUseItem",
        wire=("gameplay.useConditionMode", "gameplay.useConditionMinLife", "gameplay.useConditionMinMana"),
        provenance="existing use_condition",
        repair_group="use_condition",
        lowering=("gameplay.useConditionMode", "gameplay.useConditionMinLife", "gameplay.useConditionMinMana"),
    ),
    _cap(
        "add_hold_light",
        "Emit bounded light while the item is held.",
        "item_utility",
        ("item_body",),
        {
            "strength": _p("number", "Light strength", minimum=0.01, maximum=1.5),
            "color": _p("string", "Canonical light color", enum=_COLOR),
        },
        py=_COMPILER_OWNER,
        cs="GeneratedItem.cs::HoldItem",
        wire=("gameplay.holdLightStrength", "gameplay.holdLightColorName"),
        provenance="existing hold_item_effect/light executor",
        repair_group="hold_light",
        lowering=("gameplay.holdLightStrength", "gameplay.holdLightColorName"),
    ),
    _cap(
        "move_player_on_use",
        "Run one explicit bounded mobility action on successful use.",
        "item_utility",
        ("item_body",),
        {
            "mode": _p("string", "Mobility executor", enum=("recall_home", "blink_to_cursor")),
            "rangeTiles": _p("integer", "Maximum blink range", minimum=0, maximum=120, units="tiles"),
            "cooldownTicks": _p("integer", "Cooldown", minimum=0, maximum=3600, units="ticks"),
            "safeTileOnly": _p("boolean", "Require safe destination"),
        },
        py=_COMPILER_OWNER,
        cs="GeneratedItem.cs::UseItem/InfiniCraftPlayer.Mobility.cs",
        wire=("gameplay.mobilityMode", "gameplay.mobilityRangeTiles", "gameplay.mobilityCooldownTicks", "gameplay.mobilitySafeTileOnly"),
        provenance="existing mobility_effect",
        repair_group="mobility",
        lowering=("gameplay.mobilityMode", "gameplay.mobilityRangeTiles", "gameplay.mobilityCooldownTicks", "gameplay.mobilitySafeTileOnly"),
    ),
    _cap(
        "configure_accessory",
        "Apply exact passive player stat modifiers while equipped as an accessory.",
        "equipment",
        ("item_body",),
        {
            "defense": _p("integer", "Defense", minimum=-50, maximum=200),
            "maxLife": _p("integer", "Maximum life", minimum=-200, maximum=1000),
            "maxMana": _p("integer", "Maximum mana", minimum=-200, maximum=1000),
            "lifeRegen": _p("integer", "Life regeneration", minimum=-100, maximum=200),
            "manaRegen": _p("integer", "Mana regeneration", minimum=-100, maximum=200),
            "movementSpeed": _p("number", "Movement speed modifier", minimum=-0.9, maximum=3),
            "genericDamage": _p("number", "Generic damage additive modifier", minimum=-0.9, maximum=3),
            "genericCrit": _p("number", "Generic critical chance points", minimum=-100, maximum=100),
            "endurance": _p("number", "Damage reduction", minimum=0, maximum=0.75),
            "minionSlots": _p("integer", "Additional minion slots", minimum=0, maximum=20),
            "sentrySlots": _p("integer", "Additional sentry slots", minimum=0, maximum=20),
            "lightStrength": _p("number", "Equipped light", minimum=0, maximum=1.5),
            "lightColor": _p("string", "Canonical light color", enum=_COLOR),
        },
        py=_COMPILER_OWNER,
        cs="GeneratedItem.cs::UpdateAccessory",
        wire=("accessory.*",),
        provenance="existing accessory_effect",
        repair_group="accessory",
        lowering=("accessory.*",),
    ),
    _cap(
        "configure_armor",
        "Apply exact armor slot stats and optional set-key bonus.",
        "equipment",
        ("item_body",),
        {
            "slot": _p("string", "Armor equip slot", enum=("head", "body", "legs")),
            "setKey": _p("string", "Exact authored set key", pattern=r"^[a-z0-9_]{0,48}$"),
            "defense": _p("integer", "Defense", minimum=0, maximum=200),
            "maxLife": _p("integer", "Maximum life", minimum=-200, maximum=1000),
            "maxMana": _p("integer", "Maximum mana", minimum=-200, maximum=1000),
            "movementSpeed": _p("number", "Movement speed modifier", minimum=-0.9, maximum=3),
            "genericDamage": _p("number", "Generic damage additive modifier", minimum=-0.9, maximum=3),
            "genericCrit": _p("number", "Generic critical chance points", minimum=-100, maximum=100),
            "setBonusText": _p("string", "Player-facing set bonus text", required=False),
            "setBonusGenericDamage": _p("number", "Set bonus generic damage", required=False, minimum=-0.9, maximum=3),
            "setBonusMovementSpeed": _p("number", "Set bonus movement speed", required=False, minimum=-0.9, maximum=3),
            "setBonusLifeRegen": _p("integer", "Set bonus life regen", required=False, minimum=-100, maximum=200),
        },
        py=_COMPILER_OWNER,
        cs="GeneratedArmorItems.cs/GeneratedItem.cs::UpdateEquip",
        wire=("armor.*",),
        provenance="existing armor_effect",
        repair_group="armor",
        lowering=("armor.*",),
    ),
    _cap(
        "configure_spawn",
        "Set how this entity is spawned; does not choose its movement or damage.",
        "entity_spawn",
        PROJECTILE_ENTITY_KINDS,
        {
            "speedPxPerTick": _p("number", "Initial speed", minimum=0, maximum=80, units="pixels/tick"),
            "count": _p("integer", "Entities spawned per activation", minimum=1, maximum=12),
            "spreadRadians": _p("number", "Total angular spread", minimum=0, maximum=6.283185307179586, units="radians"),
            "offsetPx": _p("integer", "Forward spawn offset", minimum=-128, maximum=256, units="pixels"),
            "aim": _p("string", "Initial aim source", enum=("cursor", "facing", "velocity", "none")),
            "placement": _p("string", "Spawn position", enum=("item_use_origin", "owner_center", "cursor", "ground_at_cursor", "above_cursor")),
        },
        py=_COMPILER_OWNER,
        cs="GeneratedItem.cs::SpawnRuntimeEntity",
        wire=("runtimeProgram.entities[].spawn.*",),
        provenance="shot count/spread/aim/placement extracted from all roots",
        repair_group="spawn",
    ),
    _cap(
        "set_projectile_damage",
        "Enable contact damage with explicit class, damage and knockback.",
        "entity_combat",
        PROJECTILE_ENTITY_KINDS,
        {
            "damageClass": _p("string", "Exact built-in token or loaded tModLoader ModName/ClassName copied from parent facts", pattern=_DAMAGE_CLASS_PATTERN, semantic_type="terraria_damage_class"),
            "damage": _p("integer", "Projectile base damage", minimum=0, maximum=2000),
            "knockback": _p("number", "Projectile knockback", minimum=0, maximum=20),
            "ownerHitCheck": _p("boolean", "Require owner line/held hit check"),
        },
        py=_COMPILER_OWNER,
        cs="GeneratedProjectile.cs::SetDefaults/ModifyHitNPC",
        wire=("runtimeProgram.entities[].damage.*",),
        provenance="damage delivery extracted from root AttackSpec",
        repair_group="entity_damage",
    ),
    _cap(
        "set_projectile_lifetime",
        "Set exact bounded entity lifetime.",
        "entity_lifecycle",
        PROJECTILE_ENTITY_KINDS,
        {"lifetimeTicks": _p("integer", "Lifetime", minimum=1, maximum=21600, units="ticks")},
        py=_COMPILER_OWNER,
        cs="GeneratedProjectile.cs::SetDefaults",
        wire=("runtimeProgram.entities[].lifetimeTicks",),
        provenance="existing projectile lifetime field",
        repair_group="lifetime",
    ),
    _cap(
        "set_projectile_hitbox",
        "Set projectile collision box and draw scale.",
        "entity_collision",
        PROJECTILE_ENTITY_KINDS,
        {
            "widthPx": _p("integer", "Hitbox width", minimum=4, maximum=192, units="pixels"),
            "heightPx": _p("integer", "Hitbox height", minimum=4, maximum=192, units="pixels"),
            "drawScale": _p("number", "Sprite draw scale", minimum=0.25, maximum=4),
            "hitboxScale": _p("number", "Runtime hitbox multiplier", minimum=0.25, maximum=3),
        },
        py=_COMPILER_OWNER,
        cs="GeneratedProjectile.cs::SetDefaults",
        wire=("runtimeProgram.entities[].hitbox.*",),
        provenance="existing projectile geometry fields",
        repair_group="hitbox",
    ),
    _cap(
        "set_projectile_collision",
        "Set exact Terraria tile/liquid collision, penetration, update rate and NPC immunity mode.",
        "entity_collision",
        PROJECTILE_ENTITY_KINDS,
        {
            "tileCollide": _p("boolean", "Collide with solid tiles"),
            "ignoreWater": _p("boolean", "Ignore Terraria liquid drag; false keeps vanilla water interaction"),
            "bounceCount": _p("integer", "Maximum custom tile bounces", minimum=0, maximum=32),
            "pierce": _p("integer", "Terraria Projectile.penetrate count; -1 means infinite", minimum=-1, maximum=100),
            "extraUpdates": _p("integer", "Terraria Projectile.extraUpdates", minimum=0, maximum=5),
            "npcImmunityMode": _p("string", "owner uses Terraria shared owner immunity; local gives this projectile its own NPC timers", enum=("owner", "local")),
            "localNpcHitCooldownTicks": _p("integer", "Used only in local mode; -1 means this projectile can hit each NPC once", minimum=-1, maximum=600, units="ticks"),
        },
        py=_COMPILER_OWNER,
        cs="GeneratedProjectile.cs::SetDefaults/OnTileCollide",
        wire=("runtimeProgram.entities[].collision.*",),
        provenance="existing tile/bounce/pierce fields",
        repair_group="collision",
    ),
]


def _movement(
    name: str,
    summary: str,
    code: int,
    params: Mapping[str, ParamSpec] | None = None,
    *,
    targets: Iterable[str] = PROJECTILE_ENTITY_KINDS,
    cs: str = _MOVEMENT_OWNER,
    provenance: str,
) -> CapabilitySpec:
    return _cap(
        name,
        summary,
        "movement",
        targets,
        params or {},
        py=_COMPILER_OWNER,
        cs=cs,
        wire=("runtimeProgram.entities[].movement.*",),
        provenance=provenance,
        repair_group="movement",
        lowering=("runtimeProgram.entities[].movement.code", "runtimeProgram.entities[].movement.params"),
    )


_CAPS.extend([
    _movement("move_straight", "Keep initial velocity.", 0, provenance="existing movement code 0"),
    _movement("move_slow_homing", "Steer gradually toward a valid NPC.", 1, {
        "rangeTiles": _p("number", "Target search radius", minimum=1, maximum=120, units="tiles"),
        "homingStrength": _p("number", "Steering strength", minimum=0.001, maximum=1),
    }, provenance="existing movement code 1"),
    _movement("move_gravity_arc", "Apply downward acceleration each tick.", 2, {
        "gravityPerTick": _p("number", "Vertical acceleration", minimum=0.001, maximum=2, units="pixels/tick^2"),
    }, provenance="existing movement code 2"),
    _movement("move_drift", "Multiply velocity by authored retention each tick.", 3, {
        "velocityRetention": _p("number", "Velocity multiplier", minimum=0.8, maximum=1.05),
    }, provenance="existing movement code 3"),
    _movement("move_orbit", "Curve around the owner while remaining a projectile.", 4, {
        "rangeTiles": _p("number", "Orbit leash", minimum=1, maximum=80, units="tiles"),
    }, provenance="existing movement code 4"),
    _movement("move_boomerang", "Fly out, then return to the owner.", 5, {
        "returnAfterTicks": _p("integer", "Outbound duration", minimum=1, maximum=600, units="ticks"),
        "returnSpeed": _p("number", "Return speed", minimum=1, maximum=80, units="pixels/tick"),
    }, provenance="existing movement code 5"),
    _movement("move_bounce", "Use gravity and authored tile bounces.", 6, {
        "gravityPerTick": _p("number", "Vertical acceleration", minimum=0.001, maximum=2, units="pixels/tick^2"),
    }, provenance="existing movement code 6"),
    _movement("move_sine_homing", "Combine sinusoidal drift with bounded homing.", 7, {
        "rangeTiles": _p("number", "Target search radius", minimum=1, maximum=120, units="tiles"),
        "homingStrength": _p("number", "Steering strength", minimum=0.001, maximum=1),
        "waveAmplitude": _p("number", "Lateral wave amplitude", minimum=0, maximum=64, units="pixels"),
    }, provenance="existing movement code 7"),
    _movement("move_phase", "Phase-drift with explicit tile collision still controlled separately.", 8, {
        "phaseStrength": _p("number", "Phase drift strength", minimum=0, maximum=1),
    }, provenance="existing movement code 8"),
    _movement("move_accelerate", "Multiply speed up to an explicit cap.", 9, {
        "acceleration": _p("number", "Per-tick speed multiplier", minimum=1.0, maximum=1.2),
        "maxSpeed": _p("number", "Speed cap", minimum=1, maximum=80, units="pixels/tick"),
    }, provenance="existing movement code 9"),
    _movement("move_spiral", "Rotate velocity by an authored angle each tick.", 10, {
        "turnRadiansPerTick": _p("number", "Angular turn", minimum=-0.5, maximum=0.5, units="radians/tick"),
    }, provenance="existing movement code 10"),
    _movement("move_vortex_orb", "Run the existing vortex-orb controller.", 11, {
        "pullStrength": _p("number", "Nearby pull strength", minimum=0, maximum=4),
        "rangeTiles": _p("number", "Pull radius", minimum=1, maximum=80, units="tiles"),
    }, provenance="existing movement code 11"),
    _movement("move_blackhole_pull", "Run the existing black-hole pull controller.", 12, {
        "pullStrength": _p("number", "Pull strength", minimum=0, maximum=4),
        "rangeTiles": _p("number", "Pull radius", minimum=1, maximum=80, units="tiles"),
    }, provenance="existing movement code 12"),
    _movement("move_proximity_missile", "Home and trigger the authored on-expire/on-hit actions near a target.", 13, {
        "rangeTiles": _p("number", "Detection/search radius", minimum=1, maximum=120, units="tiles"),
        "homingStrength": _p("number", "Steering strength", minimum=0.001, maximum=1),
        "proximityRadiusPx": _p("integer", "Trigger radius", minimum=4, maximum=512, units="pixels"),
    }, provenance="existing movement code 13"),
    _movement("move_returning_glaive", "Fly, spin and return to the owner.", 14, {
        "returnAfterTicks": _p("integer", "Outbound duration", minimum=1, maximum=600, units="ticks"),
        "returnSpeed": _p("number", "Return speed", minimum=1, maximum=80, units="pixels/tick"),
    }, provenance="existing movement code 14"),
    _movement("move_expanding_wave", "Expand the entity while preserving authored collision/damage.", 15, {
        "scalePerTick": _p("number", "Scale increase", minimum=0.001, maximum=0.5),
        "maxScale": _p("number", "Scale cap", minimum=0.25, maximum=4),
    }, provenance="existing movement code 15"),
    _movement("move_flail_tether", "Tether to owner, fly out and return; only movement/owner controller.", 16, {
        "rangeTiles": _p("number", "Maximum tether length", minimum=2, maximum=60, units="tiles"),
        "returnSpeed": _p("number", "Return speed", minimum=1, maximum=80, units="pixels/tick"),
    }, targets=("owner_attached_projectile",), provenance="flail movement extracted from the retired melee macro"),
    _movement("move_yoyo_hover", "Follow owner cursor inside a leash and return on release.", 17, {
        "rangeTiles": _p("number", "Cursor leash", minimum=2, maximum=60, units="tiles"),
        "returnSpeed": _p("number", "Return speed", minimum=1, maximum=80, units="pixels/tick"),
    }, targets=("owner_attached_projectile",), provenance="yoyo movement extracted from the retired melee macro"),
    _movement("move_whip_lash", "Execute the bounded owner-attached lash curve.", 18, {
        "rangeTiles": _p("number", "Lash reach", minimum=2, maximum=60, units="tiles"),
        "segments": _p("integer", "Collision curve segments", minimum=3, maximum=48),
    }, targets=("owner_attached_projectile",), provenance="whip movement extracted from the retired melee macro"),
    _movement("move_forward_then_retract", "Move an owner-attached body forward and retract during one use animation.", 19, {
        "rangeTiles": _p("number", "Maximum reach", minimum=1, maximum=20, units="tiles"),
        "durationTicks": _p("integer", "Full forward/retract cycle", minimum=2, maximum=240, units="ticks"),
    }, targets=("owner_attached_projectile",), cs="Content/Projectiles/GeneratedProjectile.Executors.cs::RunMovement", provenance="held thrust logic extracted from spear root"),
])

_CAPS.extend([
    _cap(
        "channel_beam",
        "Keep an owner-attached line entity aimed at the cursor; collision is the explicit beam line.",
        "controller",
        ("owner_attached_projectile",),
        {
            "rangeTiles": _p("number", "Beam length", minimum=1, maximum=120, units="tiles"),
            "widthPx": _p("number", "Beam collision width", minimum=2, maximum=128, units="pixels"),
            "warmupTicks": _p("integer", "Warmup before full damage", minimum=0, maximum=600, units="ticks"),
        },
        py=_COMPILER_OWNER,
        cs="Content/Projectiles/GeneratedProjectile.Executors.cs::RunController/Colliding",
        wire=("runtimeProgram.entities[].controller.*",),
        provenance="beam scan/channel extracted from the retired magic macro",
        repair_group="controller",
    ),
    _cap(
        "charge_then_release",
        "Accumulate bounded charge while held, then release this entity using authored movement.",
        "controller",
        ("owner_attached_projectile", "free_projectile"),
        {
            "chargeTicks": _p("integer", "Full charge duration", minimum=1, maximum=600, units="ticks"),
            "powerMultiplier": _p("number", "Full-charge damage/knockback multiplier", minimum=1, maximum=4),
        },
        py=_COMPILER_OWNER,
        cs="Content/Projectiles/GeneratedProjectile.Executors.cs::RunController",
        wire=("runtimeProgram.entities[].controller.*",),
        provenance="charge/release controller extracted from cast root",
        repair_group="controller",
    ),
    _cap(
        "target_and_fire",
        "Make a stationary entity acquire NPC targets and periodically spawn an authored shot entity.",
        "controller",
        ("stationary_projectile", "temporary_helper"),
        {
            "shotEntity": _p("string", "Referenced projectile entity id", pattern=r"^[a-z][a-z0-9_]{0,47}$"),
            "intervalTicks": _p("integer", "Firing interval", minimum=6, maximum=3600, units="ticks"),
            "rangeTiles": _p("number", "Target range", minimum=1, maximum=120, units="tiles"),
            "sameTargetBias": _p("number", "Bias toward current target", minimum=0, maximum=1),
        },
        py=_COMPILER_OWNER,
        cs="Content/Projectiles/GeneratedProjectile.Executors.cs::RunController",
        wire=("runtimeProgram.entities[].controller.*", "runtimeProgram.entities[].targeting.*"),
        provenance="stationary targeting/firing split from the retired sentry macro",
        repair_group="targeting",
    ),
    _cap(
        "spawn_over_target",
        "Spawn this entity above the cursor/target with an explicit telegraph delay.",
        "entity_spawn",
        PROJECTILE_ENTITY_KINDS,
        {
            "heightTiles": _p("number", "Vertical spawn height", minimum=1, maximum=80, units="tiles"),
            "delayTicks": _p("integer", "Telegraph delay", minimum=0, maximum=600, units="ticks"),
        },
        py=_COMPILER_OWNER,
        cs="Content/Projectiles/GeneratedProjectile.cs::SpawnRuntimeEntity/Configure",
        wire=("runtimeProgram.entities[].spawn.overTarget.*",),
        provenance="overhead barrage placement extracted from root family",
        repair_group="spawn",
    ),
    _cap(
        "spawn_entity_on_event",
        "Spawn a referenced authored entity when one supported event occurs.",
        "event",
        ("item_body", *PROJECTILE_ENTITY_KIND_ORDER),
        {
            "event": _p("string", "Source event", enum=EVENT_KINDS),
            "entity": _p("string", "Referenced entity id", pattern=r"^[a-z][a-z0-9_]{0,47}$"),
            "count": _p("integer", "Spawn count", minimum=1, maximum=12),
            "spreadRadians": _p("number", "Total angular spread", minimum=0, maximum=6.283185307179586, units="radians"),
            "damageMultiplier": _p("number", "Multiplier applied to target entity base damage", minimum=0, maximum=4),
            "delayTicks": _p("integer", "Delay after event", minimum=0, maximum=600, units="ticks"),
            "periodTicks": _p("integer", "Required for periodic event", required=False, minimum=6, maximum=3600, units="ticks"),
        },
        multiplicity="many_per_target",
        py=_COMPILER_OWNER,
        cs="Common/Runtime/RuntimeProgramExecutor.cs::ExecuteAction",
        wire=("runtimeProgram.entities[].events[].*",),
        provenance="split/child/field/helper spawning extracted from secondary macros",
        repair_group="event_spawn",
        events=EVENT_KINDS,
        budget="max 12 per action, program child depth <= 3, total event spawn budget <= 32",
    ),
    _cap(
        "apply_status_on_event",
        "Apply one concrete Terraria debuff/buff to the hit target on a supported event.",
        "event",
        ("item_body", *PROJECTILE_ENTITY_KIND_ORDER),
        {
            "event": _p("string", "Source event", enum=("on_hit", "on_crit")),
            "buffId": _p("integer", "Exact loaded BuffID/ModContent.BuffType; copy from parent facts, do not guess", minimum=1, maximum=65535, semantic_type="loaded_buff_id"),
            "durationTicks": _p("integer", "Status duration", minimum=1, maximum=21600, units="ticks"),
        },
        multiplicity="many_per_target",
        py=_COMPILER_OWNER,
        cs="Common/Runtime/RuntimeProgramExecutor.cs::ExecuteAction",
        wire=("runtimeProgram.entities[].events[].*",),
        provenance="burn/frostburn/poison/slow/etc extracted from on-hit opcode",
        repair_group="event_status",
        events=("on_hit", "on_crit"),
    ),
    _cap(
        "damage_area_on_event",
        "Deal server-authoritative AoE damage around the event position.",
        "event",
        ("item_body", *PROJECTILE_ENTITY_KIND_ORDER),
        {
            "event": _p("string", "Source event", enum=("on_hit", "on_crit", "on_tile_collision", "on_expire", "on_kill")),
            "radiusPx": _p("integer", "Damage radius", minimum=8, maximum=768, units="pixels"),
            "damageMultiplier": _p("number", "Source damage multiplier", minimum=0.05, maximum=4),
        },
        multiplicity="many_per_target",
        py=_COMPILER_OWNER,
        cs="Common/Runtime/RuntimeProgramExecutor.cs::ExecuteAction",
        wire=("runtimeProgram.entities[].events[].*",),
        provenance="burst/aura/blackhole AoE extracted from on-hit executor",
        repair_group="event_damage",
        events=("on_hit", "on_crit", "on_tile_collision", "on_expire", "on_kill"),
    ),
    _cap(
        "chain_damage_on_event",
        "Chain bounded damage from the hit target to nearby NPCs.",
        "event",
        ("item_body", *PROJECTILE_ENTITY_KIND_ORDER),
        {
            "event": _p("string", "Source event", enum=("on_hit", "on_crit")),
            "count": _p("integer", "Maximum chained targets", minimum=1, maximum=12),
            "rangeTiles": _p("number", "Search radius", minimum=1, maximum=60, units="tiles"),
            "damageMultiplier": _p("number", "Source damage multiplier", minimum=0.05, maximum=2),
        },
        multiplicity="many_per_target",
        py=_COMPILER_OWNER,
        cs="Common/Runtime/RuntimeProgramExecutor.cs::ExecuteAction",
        wire=("runtimeProgram.entities[].events[].*",),
        provenance="chain/lightning arc extracted from on-hit opcode",
        repair_group="event_chain",
        events=("on_hit", "on_crit"),
    ),
    _cap(
        "pull_on_event",
        "Apply bounded pull between owner, target and event entity.",
        "event",
        PROJECTILE_ENTITY_KINDS,
        {
            "event": _p("string", "Source event", enum=("on_hit", "periodic", "on_expire")),
            "mode": _p("string", "Pull direction", enum=("target_to_owner", "target_to_entity", "owner_to_target")),
            "strength": _p("number", "Velocity impulse", minimum=0.01, maximum=4),
            "radiusTiles": _p("number", "Affected radius", minimum=1, maximum=60, units="tiles"),
            "periodTicks": _p("integer", "Required for periodic event", required=False, minimum=6, maximum=3600, units="ticks"),
        },
        multiplicity="many_per_target",
        py=_COMPILER_OWNER,
        cs="Common/Runtime/RuntimeProgramExecutor.cs::ExecuteAction",
        wire=("runtimeProgram.entities[].events[].*",),
        provenance="pull modes extracted from impact executor",
        repair_group="event_pull",
        events=("on_hit", "periodic", "on_expire"),
    ),
    _cap(
        "heal_owner_on_event",
        "Heal the owning player from dealt damage on hit/crit.",
        "event",
        ("item_body", *PROJECTILE_ENTITY_KIND_ORDER),
        {
            "event": _p("string", "Source event", enum=("on_hit", "on_crit")),
            "damageFraction": _p("number", "Fraction of damage healed", minimum=0.001, maximum=1),
            "maxHeal": _p("integer", "Per-event heal cap", minimum=1, maximum=200),
        },
        multiplicity="many_per_target",
        py=_COMPILER_OWNER,
        cs="Common/Runtime/RuntimeProgramExecutor.cs::ExecuteAction",
        wire=("runtimeProgram.entities[].events[].*",),
        provenance="lifesteal extracted from on-hit opcode",
        repair_group="event_heal",
        events=("on_hit", "on_crit"),
    ),
    _cap(
        "move_owner_on_event",
        "Run an explicit owner movement action after a projectile event.",
        "event",
        PROJECTILE_ENTITY_KINDS,
        {
            "event": _p("string", "Source event", enum=("on_hit", "on_tile_collision", "on_expire")),
            "mode": _p("string", "Mobility executor", enum=("blink_to_entity", "blink_to_event_position")),
            "rangeTiles": _p("integer", "Maximum movement range", minimum=1, maximum=120, units="tiles"),
            "cooldownTicks": _p("integer", "Cooldown", minimum=0, maximum=3600, units="ticks"),
            "safeTileOnly": _p("boolean", "Require safe destination"),
        },
        multiplicity="many_per_target",
        py=_COMPILER_OWNER,
        cs="Common/Runtime/RuntimeProgramExecutor.cs::ExecuteAction",
        wire=("runtimeProgram.entities[].events[].*",),
        provenance="blink-to-impact extracted from old attack mobility fields",
        repair_group="event_mobility",
        events=("on_hit", "on_tile_collision", "on_expire"),
    ),
    _cap(
        "emit_light_while_active",
        "Emit bounded world light from a live runtime entity.",
        "entity_utility",
        PROJECTILE_ENTITY_KINDS,
        {
            "strength": _p("number", "Light strength", minimum=0.01, maximum=1.5),
            "color": _p("string", "Canonical light color", enum=_COLOR),
        },
        py=_COMPILER_OWNER,
        cs="Content/Projectiles/GeneratedProjectile.Executors.cs::AI",
        wire=("runtimeProgram.entities[].light.*",),
        provenance="existing emit_light and runtime light fields",
        repair_group="entity_light",
    ),
])


ENTITY_KIND_REGISTRY: Final[Mapping[str, EntityKindSpec]] = MappingProxyType({
    "item_body": EntityKindSpec(
        "item_body",
        "The inventory/equipment/tool/placeable body. It is never spawned as a projectile.",
        "inventory_item",
        False,
        False,
        "not_applicable",
        ("configure_item_stats",),
        ("on_use", "periodic"),
    ),
    "owner_attached_projectile": EntityKindSpec(
        "owner_attached_projectile",
        "Projectile entity whose controller/movement may keep it attached to the owning player.",
        "held_body",
        True,
        True,
        "explicit movement or a position-owning controller",
        ("configure_spawn", "set_projectile_lifetime", "set_projectile_hitbox", "set_projectile_collision"),
        ("on_spawn", "on_expire", "on_kill", "periodic"),
        requires_position_driver=True,
    ),
    "free_projectile": EntityKindSpec(
        "free_projectile",
        "Independent projectile spawned from an input or another entity.",
        "projectile",
        True,
        True,
        "one explicit movement or a position-owning controller",
        ("configure_spawn", "set_projectile_lifetime", "set_projectile_hitbox", "set_projectile_collision"),
        ("on_spawn", "on_expire", "on_kill", "periodic"),
        requires_position_driver=True,
    ),
    "stationary_projectile": EntityKindSpec(
        "stationary_projectile",
        "Deployed stationary runtime projectile such as a trap or targeting platform.",
        "deployed_entity",
        True,
        True,
        "stationary by kind; movement is optional",
        ("configure_spawn", "set_projectile_lifetime", "set_projectile_hitbox", "set_projectile_collision"),
        ("on_spawn", "on_expire", "on_kill", "periodic"),
    ),
    "temporary_helper": EntityKindSpec(
        "temporary_helper",
        "Bounded helper projectile used for targeting, support, or event composition.",
        "helper",
        True,
        True,
        "stationary by kind unless movement is explicitly authored",
        ("configure_spawn", "set_projectile_lifetime", "set_projectile_hitbox", "set_projectile_collision"),
        ("on_spawn", "on_expire", "on_kill", "periodic"),
    ),
    "field": EntityKindSpec(
        "field",
        "Bounded area entity whose effects are expressed through damage, light, and periodic/event actions.",
        "field",
        True,
        True,
        "stationary by kind unless movement is explicitly authored",
        ("configure_spawn", "set_projectile_lifetime", "set_projectile_hitbox", "set_projectile_collision"),
        ("on_spawn", "on_expire", "on_kill", "periodic"),
    ),
    "child_projectile": EntityKindSpec(
        "child_projectile",
        "Projectile reachable only through an explicit event/controller reference.",
        "child_projectile",
        True,
        False,
        "one explicit movement or a position-owning controller",
        ("configure_spawn", "set_projectile_lifetime", "set_projectile_hitbox", "set_projectile_collision"),
        ("on_spawn", "on_expire", "on_kill", "periodic"),
        requires_position_driver=True,
    ),
})

BINDING_ACTION_REGISTRY: Final[Mapping[str, BindingActionSpec]] = MappingProxyType({
    "spawn_entity": BindingActionSpec(
        "spawn_entity", tuple(kind for kind in PROJECTILE_ENTITY_KIND_ORDER if ENTITY_KIND_REGISTRY[kind].spawnable_by_binding), ("primary_use", "alternate_use", "hold"),
        "Spawn the referenced runtime entity. Hold keeps one owner-held instance alive where supported.",
    ),
    "use_item_body": BindingActionSpec(
        "use_item_body", ("item_body",), ("primary_use", "alternate_use"),
        "One standalone input root for item-body use/contact behaviour without spawning a runtime entity. configure_item_use and the mere presence of item_body do not require this binding; never pair it with spawn_entity on the same input.",
    ),
    "apply_item_effects": BindingActionSpec(
        "apply_item_effects", ("item_body",), ("primary_use", "alternate_use"),
        "Apply explicitly authored item buffs/resource/mobility effects on use.",
        ("restore_resources_on_use", "apply_vanilla_buff_on_use", "apply_generated_buff_on_use", "move_player_on_use"),
    ),
    "place_item": BindingActionSpec(
        "place_item", ("item_body",), ("primary_use", "alternate_use"),
        "Use the explicitly configured tile/wall placement result.",
        ("configure_placeable",),
    ),
    "equip_passive": BindingActionSpec(
        "equip_passive", ("item_body",), ("equipped",),
        "Enable explicitly configured accessory or armor behaviour while equipped.",
        ("configure_accessory", "configure_armor"),
    ),
})

INPUT_KIND_REGISTRY: Final[Mapping[str, InputKindSpec]] = MappingProxyType({
    "primary_use": InputKindSpec("primary_use", True, ("spawn_entity", "use_item_body", "apply_item_effects", "place_item"), "Primary item-use input: choose exactly one action root; configure_item_use configures the input but is not another binding.", ("configure_item_use",)),
    "alternate_use": InputKindSpec("alternate_use", True, ("spawn_entity", "use_item_body", "apply_item_effects", "place_item"), "Alternate item-use input: choose exactly one action root; configure_item_use configures the input but is not another binding.", ("configure_item_use",)),
    "hold": InputKindSpec("hold", True, ("spawn_entity",), "While-held binding; currently supports maintaining one spawned runtime entity."),
    "equipped": InputKindSpec("equipped", False, ("equip_passive",), "Accessory/armor equipped state."),
})

EVENT_KIND_REGISTRY: Final[Mapping[str, EventKindSpec]] = MappingProxyType({
    "on_use": EventKindSpec("on_use", ("item_body",), (), False, "Emitted when an active item-body use binding succeeds."),
    "on_spawn": EventKindSpec("on_spawn", PROJECTILE_ENTITY_KIND_ORDER, (), True, "Emitted once when a runtime projectile entity activates."),
    "on_hit": EventKindSpec("on_hit", ("item_body", *PROJECTILE_ENTITY_KIND_ORDER), ("enable_item_contact_damage", "set_projectile_damage"), False, "Emitted after explicit contact/projectile damage hits an NPC."),
    "on_crit": EventKindSpec("on_crit", ("item_body", *PROJECTILE_ENTITY_KIND_ORDER), ("enable_item_contact_damage", "set_projectile_damage"), False, "Emitted after an explicitly damaging hit is critical."),
    "on_tile_collision": EventKindSpec("on_tile_collision", PROJECTILE_ENTITY_KIND_ORDER, ("set_projectile_collision",), False, "Emitted when explicit tile collision occurs."),
    "on_expire": EventKindSpec("on_expire", PROJECTILE_ENTITY_KIND_ORDER, ("set_projectile_lifetime",), True, "Emitted immediately before normal lifetime expiration."),
    "on_kill": EventKindSpec("on_kill", PROJECTILE_ENTITY_KIND_ORDER, (), True, "Emitted when the projectile entity is killed."),
    "periodic": EventKindSpec("periodic", ("item_body", *PROJECTILE_ENTITY_KIND_ORDER), (), False, "Bounded periodic event; each action must declare periodTicks >= 6."),
    "on_release": EventKindSpec("on_release", PROJECTILE_ENTITY_KIND_ORDER, ("charge_then_release",), False, "Emitted by charge_then_release when the held charge is released."),
    "channel_complete": EventKindSpec("channel_complete", PROJECTILE_ENTITY_KIND_ORDER, ("charge_then_release",), False, "Emitted by charge_then_release after a full authored charge."),
})


if tuple(ENTITY_KIND_REGISTRY) != ENTITY_KINDS:
    raise RuntimeError("ENTITY_KINDS must be the exact entity-kind registry projection")
if tuple(INPUT_KIND_REGISTRY) != INPUT_KINDS:
    raise RuntimeError("INPUT_KINDS must be the exact input registry projection")
if tuple(BINDING_ACTION_REGISTRY) != BINDING_ACTIONS:
    raise RuntimeError("BINDING_ACTIONS must be the exact binding-action registry projection")
if tuple(EVENT_KIND_REGISTRY) != EVENT_KINDS:
    raise RuntimeError("EVENT_KINDS must be the exact event registry projection")


def _exact_wire_paths(cap: CapabilitySpec) -> tuple[str, ...]:
    item_paths: dict[str, tuple[str, ...]] = {
        "configure_item_stats": (
            "gameplay.damageClass", "gameplay.damage", "gameplay.knockback", "gameplay.useTime", "gameplay.useAnimation",
            "gameplay.manaCost", "gameplay.rarity", "gameplay.value", "gameplay.maxStack", "gameplay.craftYield",
            "gameplay.width", "gameplay.height", "gameplay.itemScale",
        ),
        "configure_item_use": (
            "gameplay.useStyleName", "gameplay.autoReuse", "gameplay.useTurn", "gameplay.channelUse",
            "gameplay.holdoutOffsetX", "gameplay.holdoutOffsetY", "gameplay.handPose", "gameplay.releaseTiming",
            "runtimeProgram.itemUse.configured", "runtimeProgram.itemUse.useStyle", "runtimeProgram.itemUse.hideUseGraphic", "runtimeProgram.itemUse.disableMeleeHitbox",
            "runtimeProgram.itemUse.channel", "runtimeProgram.itemUse.handPose", "runtimeProgram.itemUse.releaseTiming",
            "runtimeProgram.itemUse.holdoutOffsetX", "runtimeProgram.itemUse.holdoutOffsetY",
        ),
        "enable_item_contact_damage": ("runtimeProgram.itemContact.enabled", "runtimeProgram.itemContact.hitboxScale", "runtimeProgram.itemContact.contactForgivenessPx"),
        "configure_consumption": ("gameplay.consumable", "gameplay.consumeChancePercent"),
        "configure_vanilla_ammo_item": ("gameplay.ammoCategory", "gameplay.ammoProjectileId", "gameplay.ammoShootSpeedPxPerTick", "gameplay.notAmmo"),
        "restore_resources_on_use": ("gameplay.healLife", "gameplay.healMana", "gameplay.potion"),
        "apply_vanilla_buff_on_use": ("gameplay.extraBuffs[].buffCode", "gameplay.extraBuffs[].buffTime"),
        "apply_generated_buff_on_use": (
            "gameplay.generatedBuff.durationTicks", "gameplay.generatedBuff.miningSpeedMultiplier", "gameplay.generatedBuff.emitLightStrength",
            "gameplay.generatedBuff.lightColorName", "gameplay.generatedBuff.oreSenseRadiusTiles", "gameplay.generatedBuff.movementSpeed",
            "gameplay.generatedBuff.jumpBoost", "gameplay.generatedBuff.manaRegen", "gameplay.generatedBuff.lifeRegen",
        ),
        "configure_tool": ("gameplay.pickPower", "gameplay.axePower", "gameplay.hammerPower", "gameplay.miningSpeedScale"),
        "configure_placeable": ("gameplay.createTile", "gameplay.createWall", "gameplay.placeStyle"),
        "require_use_condition": ("gameplay.useConditionMode", "gameplay.useConditionMinLife", "gameplay.useConditionMinMana"),
        "add_hold_light": ("gameplay.holdLightStrength", "gameplay.holdLightColorName"),
        "move_player_on_use": ("gameplay.mobilityMode", "gameplay.mobilityRangeTiles", "gameplay.mobilityCooldownTicks", "gameplay.mobilitySafeTileOnly"),
        "configure_accessory": tuple(["accessory.enabled", *[f"accessory.{name}" for name in ("defense", "maxLife", "maxMana", "lifeRegen", "manaRegen", "movementSpeed", "genericDamage", "genericCrit", "endurance", "minionSlots", "sentrySlots", "lightStrength", "lightColorName")]]),
        "configure_armor": tuple(["armor.enabled", *[f"armor.{name}" for name in ("slot", "setKey", "defense", "maxLife", "maxMana", "movementSpeed", "genericDamage", "genericCrit", "setBonusText", "setBonusGenericDamage", "setBonusMovementSpeed", "setBonusLifeRegen")]]),
    }
    if cap.name in item_paths:
        return item_paths[cap.name]
    if cap.name == "configure_spawn":
        return tuple(["runtimeProgram.entities[].spawn.enabled", *[f"runtimeProgram.entities[].spawn.{name}" for name in cap.params]])
    if cap.name == "set_projectile_damage":
        return tuple(["runtimeProgram.entities[].damage.enabled", *[f"runtimeProgram.entities[].damage.{name}" for name in cap.params]])
    if cap.name == "set_projectile_lifetime":
        return ("runtimeProgram.entities[].lifetimeTicks",)
    if cap.name == "set_projectile_hitbox":
        return tuple(f"runtimeProgram.entities[].hitbox.{name}" for name in cap.params)
    if cap.name == "set_projectile_collision":
        return tuple(f"runtimeProgram.entities[].collision.{name}" for name in cap.params)
    if cap.category == "movement":
        return tuple(["runtimeProgram.entities[].movement.name", "runtimeProgram.entities[].movement.code", *[f"runtimeProgram.entities[].movement.params.{name}" for name in cap.params]])
    if cap.name in {"channel_beam", "charge_then_release"}:
        return tuple(["runtimeProgram.entities[].controller.name", "runtimeProgram.entities[].controller.code", *[f"runtimeProgram.entities[].controller.params.{name}" for name in cap.params]])
    if cap.name == "target_and_fire":
        return (
            "runtimeProgram.entities[].controller.name", "runtimeProgram.entities[].controller.code",
            "runtimeProgram.entities[].targeting.shotEntityId", "runtimeProgram.entities[].targeting.intervalTicks",
            "runtimeProgram.entities[].targeting.rangeTiles", "runtimeProgram.entities[].targeting.sameTargetBias",
        )
    if cap.name == "spawn_over_target":
        return tuple(f"runtimeProgram.entities[].spawn.overTarget.{name}" for name in cap.params)
    if cap.category == "event":
        mapped = ["runtimeProgram.entities[].events[].event", "runtimeProgram.entities[].events[].action", "runtimeProgram.entities[].events[].actionCode"]
        for name in cap.params:
            if name == "event":
                continue
            mapped.append("runtimeProgram.entities[].events[].entityId" if name == "entity" else f"runtimeProgram.entities[].events[].{name}")
        return tuple(mapped)
    if cap.name == "emit_light_while_active":
        return tuple(f"runtimeProgram.entities[].light.{name}" for name in cap.params)
    raise RuntimeError(f"missing exact wire contract for capability {cap.name}")


def _component_slot(cap: CapabilitySpec) -> str:
    direct = {
        "configure_item_stats": "item_stats", "configure_item_use": "item_use", "enable_item_contact_damage": "item_contact",
        "configure_consumption": "consumption", "configure_vanilla_ammo_item": "ammo_item", "restore_resources_on_use": "resource_restore", "apply_vanilla_buff_on_use": "use_buff",
        "apply_generated_buff_on_use": "generated_use_buff", "configure_tool": "tool", "configure_placeable": "placeable",
        "require_use_condition": "use_condition", "add_hold_light": "held_light", "move_player_on_use": "item_mobility",
        "configure_accessory": "accessory", "configure_armor": "armor", "configure_spawn": "spawn",
        "set_projectile_damage": "damage", "set_projectile_lifetime": "lifetime", "set_projectile_hitbox": "hitbox",
        "set_projectile_collision": "collision", "spawn_over_target": "spawn_over_target", "emit_light_while_active": "light",
    }
    if cap.name in direct:
        return direct[cap.name]
    if cap.category == "movement":
        return "movement"
    if cap.category == "controller":
        return "controller"
    if cap.category == "event":
        return "event_action"
    raise RuntimeError(f"missing component slot for {cap.name}")


def _csharp_owner_for(cap: CapabilitySpec) -> str:
    item = {
        "configure_item_stats": "Common/Models/GeneratedItemData.Apply.cs::ApplyToItem",
        "configure_item_use": "Content/Items/GeneratedItem.cs::CanUseItem|Content/Items/GeneratedItem.UseStyle.cs::UseStyle",
        "enable_item_contact_damage": "Content/Items/GeneratedItem.cs::UseItemHitbox/OnHitNPC",
        "configure_consumption": "Content/Items/GeneratedItem.cs::ConsumeItem",
        "configure_vanilla_ammo_item": "Common/Models/TerrariaRuntimeVocabulary.cs::ResolveAmmoCategory|Common/Models/GeneratedItemData.Apply.cs::ApplyToItem",
        "restore_resources_on_use": "Common/Models/GeneratedItemData.Apply.cs::ApplyToItem",
        "apply_vanilla_buff_on_use": "Content/Items/GeneratedItem.cs::ApplyItemEffects",
        "apply_generated_buff_on_use": "Content/Items/GeneratedItem.cs::ApplyItemEffects",
        "configure_tool": "Common/Models/GeneratedItemData.Apply.cs::ApplyToItem",
        "configure_placeable": "Common/Models/GeneratedItemData.Apply.cs::ApplyToItem",
        "require_use_condition": "Content/Items/GeneratedItem.cs::UseBlockedReason",
        "add_hold_light": "Content/Items/GeneratedItem.cs::HoldItem",
        "move_player_on_use": "Content/Items/GeneratedItem.cs::ApplyItemEffects",
        "configure_accessory": "Content/Items/GeneratedItem.cs::UpdateAccessory",
        "configure_armor": "Content/Items/GeneratedItem.cs::UpdateEquip",
        "configure_spawn": "Content/Projectiles/GeneratedProjectile.cs::SpawnRuntimeEntity/Configure",
        "set_projectile_damage": "Content/Projectiles/GeneratedProjectile.cs::Configure",
        "set_projectile_lifetime": "Content/Projectiles/GeneratedProjectile.cs::Configure",
        "set_projectile_hitbox": "Content/Projectiles/GeneratedProjectile.cs::Configure",
        "set_projectile_collision": "Content/Projectiles/GeneratedProjectile.cs::Configure",
        "spawn_over_target": "Content/Projectiles/GeneratedProjectile.cs::SpawnRuntimeEntity/Configure",
        "emit_light_while_active": "Content/Projectiles/GeneratedProjectile.Executors.cs::AI",
    }
    if cap.name in item:
        return item[cap.name]
    if cap.category in {"movement", "controller"}:
        return "Content/Projectiles/GeneratedProjectile.Executors.cs::RunMovement/RunController"
    if cap.category == "event":
        return "Common/Runtime/RuntimeProgramExecutor.cs::ExecuteAction"
    raise RuntimeError(f"missing C# owner for {cap.name}")


def _authority_for(cap: CapabilitySpec) -> tuple[str, Mapping[str, str]]:
    if cap.category == "movement" or cap.category in {"entity_spawn", "entity_lifecycle", "entity_collision", "entity_combat", "controller"}:
        return "owner_execute_sync", {}
    if cap.name in {"apply_status_on_event", "damage_area_on_event", "chain_damage_on_event"}:
        return "server_execute", {}
    if cap.name == "pull_on_event":
        return "server_execute", {"owner_to_target": "owner_execute_sync", "target_to_owner": "server_execute", "target_to_entity": "server_execute"}
    if cap.name in {"spawn_entity_on_event", "move_owner_on_event", "move_player_on_use"}:
        return "owner_execute_sync", {}
    if cap.name == "heal_owner_on_event":
        return "owner_execute_sync", {}
    if cap.name in {"emit_light_while_active", "add_hold_light"}:
        return "client_visual_only", {}
    if cap.category == "equipment":
        return "owner_execute_sync", {}
    return "owner_request_server_execute", {}


def _requirements_for(cap: CapabilitySpec) -> tuple[RequirementSpec, ...]:
    if cap.name == "configure_vanilla_ammo_item":
        return (RequirementSpec(
            "item_capability_param",
            capability="configure_consumption",
            target="item_body",
            param="consumable",
            equals=True,
            message="vanilla ammo item requires configure_consumption(consumable=true)",
        ),)
    if cap.name == "spawn_over_target":
        return (RequirementSpec("capability_present", capability="configure_spawn", message="spawn_over_target extends the same entity's explicit spawn component"),)
    if cap.name in {"channel_beam", "charge_then_release"}:
        rows = [RequirementSpec("item_capability_param", capability="configure_item_use", target="item_body", param="channel", equals=True, message="channel controller requires channel=true on item_body")]
        if cap.name == "charge_then_release":
            rows.append(RequirementSpec("capability_group_present", target="same_target", any_of=tuple(sorted(row.name for row in _CAPS if row.category == "movement")), message="released projectile needs an explicit post-release movement"))
        return tuple(rows)
    if cap.name == "configure_placeable":
        return (RequirementSpec("at_least_one_param_nonnegative", param="tileId|wallId", message="at least one of tileId/wallId must be enabled"),)
    if cap.name == "require_use_condition":
        return (RequirementSpec("conditional_param", param="mode", any_of=("life_above:minLife", "mana_above:minMana"), message="threshold modes require their threshold parameter"),)
    if cap.name == "apply_generated_buff_on_use":
        return (RequirementSpec("non_neutral_param", message="at least one generated-buff effect must be non-neutral"),)
    if cap.category == "event":
        return (RequirementSpec("event_available", param="event", message="target entity must actually emit the selected event"),)
    return ()


def _semantic_param(cap: CapabilitySpec, name: str, spec: ParamSpec) -> ParamSpec:
    reference = spec.reference
    semantic_type = spec.semantic_type
    if cap.name == "target_and_fire" and name == "shotEntity":
        reference = ReferenceSpec("entity", PROJECTILE_ENTITY_KIND_ORDER, False, True)
        semantic_type = "runtime_entity_id"
    elif cap.name == "spawn_entity_on_event" and name == "entity":
        reference = ReferenceSpec("entity", PROJECTILE_ENTITY_KIND_ORDER, False, True)
        semantic_type = "runtime_entity_id"
    elif name in {"buffId"}:
        semantic_type = "terraria_buff_id"
    elif name == "tileId":
        semantic_type = "terraria_tile_id_or_disabled"
    elif name == "wallId":
        semantic_type = "terraria_wall_id_or_disabled"
    elif name in {"damageClass"}:
        semantic_type = "terraria_damage_class"
    elif name == "useStyle":
        semantic_type = "terraria_item_use_style"
    elif name == "ammoCategory":
        semantic_type = "terraria_ammo_id_category"
    elif name == "projectileId":
        semantic_type = "terraria_projectile_id"
    elif name == "npcImmunityMode":
        semantic_type = "terraria_npc_immunity_mode"
    elif name in {"color", "lightColor"}:
        semantic_type = "runtime_color"
    elif name == "event":
        semantic_type = "runtime_event_kind"
    elif name.endswith("Ticks") or name in {"useTimeTicks", "useAnimationTicks"}:
        semantic_type = "ticks"
    elif name.endswith("Px") or name in {"widthPx", "heightPx", "offsetPx", "radiusPx", "proximityRadiusPx"}:
        semantic_type = "pixels"
    elif name.endswith("Tiles") or name in {"rangeTiles", "radiusTiles", "heightTiles", "oreSenseRadiusTiles"}:
        semantic_type = "tiles"
    elif name.endswith("Radians") or name == "turnRadiansPerTick":
        semantic_type = "radians"
    if not semantic_type:
        semantic_by_name = {
            "damage": "damage_points", "knockback": "knockback_strength", "manaCost": "mana_points",
            "rarity": "terraria_rarity_id", "maxStack": "stack_count", "craftYield": "item_count",
            "scale": "draw_scale", "hitboxScale": "hitbox_scale", "drawScale": "draw_scale",
            "healLife": "life_points", "healMana": "mana_points", "minLife": "life_points", "minMana": "mana_points",
            "defense": "defense_points", "maxLife": "life_points", "maxMana": "mana_points",
            "lifeRegen": "terraria_life_regen", "manaRegen": "terraria_mana_regen",
            "pickPower": "terraria_pick_power", "axePower": "terraria_axe_power", "hammerPower": "terraria_hammer_power",
            "placeStyle": "terraria_place_style", "bounceCount": "bounce_count", "pierce": "penetration_count",
            "extraUpdates": "extra_ai_updates", "segments": "collision_segment_count", "count": "spawn_or_target_count",
            "maxHeal": "life_points", "minionSlots": "minion_slots", "sentrySlots": "sentry_slots",
            "genericCrit": "percentage_points", "setBonusText": "display_text",
            "acceleration": "pixels_per_tick_squared", "strength": "effect_strength",
        }
        semantic_type = semantic_by_name.get(name, "unitless_scalar" if spec.kind in {"integer", "number"} else "bounded_text")
    return replace(spec, semantic_type=semantic_type, reference=reference)


def _enrich_capability(cap: CapabilitySpec) -> CapabilitySpec:
    authority, by_effect = _authority_for(cap)
    slot = _component_slot(cap)
    exclusive_group = ""
    position_ownership = "none"
    emitted: tuple[str, ...] = ()
    if cap.category == "movement":
        exclusive_group = "movement"
        position_ownership = "velocity_or_position_controller"
    elif cap.category == "controller":
        exclusive_group = "controller"
        position_ownership = {
            "channel_beam": "owns_position_while_active",
            "charge_then_release": "owns_position_until_release",
            "target_and_fire": "owns_stationary_position",
        }[cap.name]
    if cap.name in {"enable_item_contact_damage", "set_projectile_damage"}:
        emitted = ("on_hit", "on_crit")
    elif cap.name == "charge_then_release":
        emitted = ("on_release", "channel_complete")
    exact = _exact_wire_paths(cap)
    technical = tuple(path for path in exact if path.endswith(".enabled") or path.endswith(".code") or path.endswith(".name"))
    params = MappingProxyType({name: _semantic_param(cap, name, spec) for name, spec in cap.params.items()})
    return replace(
        cap,
        params=params,
        csharp_owner=_csharp_owner_for(cap),
        final_wire_paths=exact,
        technical_lowering_outputs=technical,
        component_slot=slot,
        exclusive_group=exclusive_group,
        position_ownership=position_ownership,
        emitted_events=emitted,
        requirements=_requirements_for(cap),
        dependencies=tuple(dict.fromkeys(
            requirement.capability
            for requirement in _requirements_for(cap)
            if requirement.capability
        )),
        conflicts=(f"exclusive_group:{exclusive_group}",) if exclusive_group else (),
        network_authority=authority,
        authority_by_effect=MappingProxyType(dict(by_effect)),
        activation_spawn_count_param="count" if cap.name == "spawn_entity_on_event" else "",
        meaningful_for_stationary=(cap.category == "event" or cap.name in {"set_projectile_damage", "target_and_fire", "emit_light_while_active"}),
    )


_ENRICHED_CAPS: Final[tuple[CapabilitySpec, ...]] = tuple(
    _enrich_capability(cap) for cap in _CAPS
)


CAPABILITY_REGISTRY: Final[Mapping[str, CapabilitySpec]] = MappingProxyType(
    {cap.name: cap for cap in _ENRICHED_CAPS}
)
if len(CAPABILITY_REGISTRY) != len(_ENRICHED_CAPS):
    raise RuntimeError("duplicate capability name in CAPABILITY_REGISTRY")

MOVEMENT_CAPABILITIES: Final[frozenset[str]] = frozenset(
    cap.name for cap in _ENRICHED_CAPS if cap.category == "movement"
)
EVENT_CAPABILITIES: Final[frozenset[str]] = frozenset(
    cap.name for cap in _ENRICHED_CAPS if cap.category == "event"
)
ITEM_CAPABILITIES: Final[frozenset[str]] = frozenset(
    cap.name for cap in _ENRICHED_CAPS if cap.target_kinds == ("item_body",)
)

MOVEMENT_OPCODE: Final[Mapping[str, int]] = MappingProxyType({
    "move_straight": 0,
    "move_slow_homing": 1,
    "move_gravity_arc": 2,
    "move_drift": 3,
    "move_orbit": 4,
    "move_boomerang": 5,
    "move_bounce": 6,
    "move_sine_homing": 7,
    "move_phase": 8,
    "move_accelerate": 9,
    "move_spiral": 10,
    "move_vortex_orb": 11,
    "move_blackhole_pull": 12,
    "move_proximity_missile": 13,
    "move_returning_glaive": 14,
    "move_expanding_wave": 15,
    "move_flail_tether": 16,
    "move_yoyo_hover": 17,
    "move_whip_lash": 18,
    "move_forward_then_retract": 19,
})
CONTROLLER_OPCODE: Final[Mapping[str, int]] = MappingProxyType({
    "none": 0,
    "channel_beam": 1,
    "charge_then_release": 2,
    "target_and_fire": 3,
})
EVENT_ACTION_OPCODE: Final[Mapping[str, int]] = MappingProxyType({
    "spawn_entity_on_event": 1,
    "apply_status_on_event": 2,
    "damage_area_on_event": 3,
    "chain_damage_on_event": 4,
    "pull_on_event": 5,
    "heal_owner_on_event": 6,
    "move_owner_on_event": 7,
})


def visible_capabilities() -> tuple[CapabilitySpec, ...]:
    """Return the current canonical registry projection.

    Deliberately reads CAPABILITY_REGISTRY rather than the construction list so
    schema/prompt/mutation tests exercise the same single source of truth.
    """
    return tuple(cap for cap in CAPABILITY_REGISTRY.values() if cap.prompt_visible and cap.decision == "expose")


def compact_capability_catalog() -> list[dict[str, Any]]:
    return [cap.prompt_card() for cap in visible_capabilities()]


def capability_provider_union() -> list[dict[str, Any]]:
    return [cap.provider_variant_schema() for cap in visible_capabilities()]


def capability_inventory_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cap in CAPABILITY_REGISTRY.values():
        rows.append({
            "capability": cap.name,
            "purpose": cap.summary,
            "parameters": {
                name: {
                    "kind": spec.kind,
                    "required": spec.required,
                    "minimum": spec.minimum,
                    "maximum": spec.maximum,
                    "enum": list(spec.enum),
                    "units": spec.units,
                    "semanticType": spec.semantic_type,
                    "reference": spec.reference.card() if spec.reference is not None else None,
                }
                for name, spec in cap.params.items()
            },
            "targetKinds": list(cap.target_kinds),
            "events": list(cap.allowed_events),
            "emittedEvents": list(cap.emitted_events),
            "componentSlot": cap.component_slot,
            "exclusiveGroup": cap.exclusive_group,
            "positionOwnership": cap.position_ownership,
            "requirements": [row.card() for row in cap.requirements],
            "dependencies": list(cap.dependencies),
            "conflicts": list(cap.conflicts),
            "csharpOwner": cap.csharp_owner,
            "pythonOwner": cap.compiler_owner,
            "networkAuthority": cap.network_authority,
            "authorityByEffect": dict(cap.authority_by_effect),
            "safetyLimits": cap.performance_budget,
            "multiplicity": cap.multiplicity,
            "promptVisibility": cap.prompt_visible,
            "status": cap.implementation_status,
            "provenance": cap.provenance,
            "decision": cap.decision,
            "finalWirePaths": list(cap.final_wire_paths),
            "technicalLoweringOutputs": list(cap.technical_lowering_outputs),
        })
    return rows


def runtime_authoring_registry_manifest() -> dict[str, Any]:
    return {
        "schema": "infini.runtime-authoring-registry.v1",
        "apiVersion": RUNTIME_PROGRAM_API_VERSION,
        "authoringSchema": RUNTIME_PROGRAM_SCHEMA,
        "wireSchema": RUNTIME_WIRE_SCHEMA,
        "entityKinds": [row.prompt_card() for row in ENTITY_KIND_REGISTRY.values()],
        "inputs": [row.prompt_card() for row in INPUT_KIND_REGISTRY.values()],
        "bindingActions": [row.prompt_card() for row in BINDING_ACTION_REGISTRY.values()],
        "events": [row.prompt_card() for row in EVENT_KIND_REGISTRY.values()],
        "capabilities": compact_capability_catalog(),
    }


__all__ = [
    "runtime_authoring_registry_manifest",
    "RequirementSpec",
    "ReferenceSpec",
    "InputKindSpec",
    "EventKindSpec",
    "EntityKindSpec",
    "BindingActionSpec",
    "INPUT_KIND_REGISTRY",
    "EVENT_KIND_REGISTRY",
    "ENTITY_KIND_REGISTRY",
    "BINDING_ACTION_REGISTRY",
    "BINDING_ACTIONS",
    "CAPABILITY_REGISTRY",
    "CONTROLLER_OPCODE",
    "ENTITY_KINDS",
    "EVENT_ACTION_OPCODE",
    "EVENT_CAPABILITIES",
    "EVENT_KINDS",
    "INPUT_KINDS",
    "ITEM_CAPABILITIES",
    "MOVEMENT_CAPABILITIES",
    "MOVEMENT_OPCODE",
    "NETWORK_AUTHORITIES",
    "PROJECTILE_ENTITY_KIND_ORDER",
    "PROJECTILE_ENTITY_KINDS",
    "RUNTIME_PROGRAM_API_VERSION",
    "RUNTIME_PROGRAM_SCHEMA",
    "RUNTIME_WIRE_SCHEMA",
    "VISUAL_ROLE_BY_ENTITY_KIND",
    "CapabilitySpec",
    "ParamSpec",
    "capability_inventory_rows",
    "capability_provider_union",
    "compact_capability_catalog",
    "visible_capabilities",
]
