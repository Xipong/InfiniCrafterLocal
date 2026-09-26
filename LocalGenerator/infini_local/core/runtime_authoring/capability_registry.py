from __future__ import annotations

from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any, Final, Iterable, Mapping

from infini_local.core.runtime_authoring.binding_use_policy import (
    STACK_COST_RULE,
    action_kind,
    contact_damage as binding_contact_damage,
    target_id as binding_target_id,
)
from infini_local.core.runtime_authoring.terraria_vocabulary import (
    DAMAGE_CLASS_TOKEN_PATTERN,
    DAMAGE_CLASS_TOKENS,
    ITEM_USE_STYLE_TOKENS,
    VANILLA_AMMO_CATEGORY_TOKENS,
    VANILLA_PROJECTILE_TYPE_ID_MAX,
)


RUNTIME_PROGRAM_API_VERSION: Final[str] = "infini.runtime-program.v5"
RUNTIME_PROGRAM_SCHEMA: Final[str] = "infini.runtime-program.authoring.v4"
RUNTIME_WIRE_SCHEMA: Final[str] = "infini.runtime-program.wire.v3"

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
    nonzero_params: tuple[str, ...] = ()
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
        if self.nonzero_params:
            out["nonzeroParams"] = list(self.nonzero_params)
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
class EventCallRequirement:
    capability: str
    exact_params: tuple[tuple[str, Any], ...] = ()

    @classmethod
    def create(
        cls,
        capability: str,
        exact_params: Mapping[str, Any] | None = None,
    ) -> EventCallRequirement:
        return cls(
            capability=capability,
            exact_params=tuple(sorted((exact_params or {}).items())),
        )

    def exact_params_dict(self) -> dict[str, Any]:
        return dict(self.exact_params)


@dataclass(frozen=True, slots=True)
class EventBindingRequirement:
    any_of_inputs: tuple[str, ...]
    any_of_actions: tuple[str, ...] = ()
    required_contact_damage: bool | None = None


@dataclass(frozen=True, slots=True)
class EventDependencyAlternative:
    required_calls: tuple[EventCallRequirement, ...] = ()
    required_bindings: tuple[EventBindingRequirement, ...] = ()

    @classmethod
    def required_call(
        cls,
        capability: str,
        exact_params: Mapping[str, Any] | None = None,
    ) -> EventDependencyAlternative:
        return cls(required_calls=(EventCallRequirement.create(capability, exact_params),))

    @classmethod
    def any_binding_input(
        cls,
        inputs: Iterable[str],
        actions: Iterable[str] = (),
        *,
        contact_damage: bool | None = None,
    ) -> EventDependencyAlternative:
        return cls(required_bindings=(EventBindingRequirement(
            tuple(inputs),
            tuple(actions),
            contact_damage,
        ),))


@dataclass(frozen=True, slots=True)
class EventKindSpec:
    name: str
    source_kinds: tuple[str, ...]
    producer_capabilities: tuple[str, ...]
    summary: str
    producer_binding_inputs: tuple[str, ...] = ()
    producer_binding_actions: tuple[str, ...] = ()
    producer_binding_kinds: tuple[str, ...] = ()
    producer_binding_contact_damage: bool | None = None
    producer_exact_params: Mapping[str, Mapping[str, Any]] = field(
        default_factory=lambda: MappingProxyType({}),
        compare=False,
    )

    def prompt_card(self) -> dict[str, Any]:
        producer_free_kinds = [
            kind.name
            for kind in ENTITY_KIND_REGISTRY.values()
            if self.name in kind.base_events
        ]
        return {
            "event": self.name,
            "sources": list(self.source_kinds),
            "producedBy": list(self.producer_capabilities),
            "producedByBindingInputs": list(self.producer_binding_inputs),
            "producedByBindingActions": list(self.producer_binding_actions),
            "producedByBindingKinds": list(self.producer_binding_kinds),
            "producerBindingContactDamage": self.producer_binding_contact_damage,
            "producerFreeKinds": producer_free_kinds,
            "producerExactParams": {
                capability: dict(params)
                for capability, params in self.producer_exact_params.items()
            },
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
    wire_name: str = ""
    wire_divisor: int = 1
    wire_multiplier: int = 1
    multiple_of: float | int | None = None
    wire_boolean_true_value: int | None = None
    runtime_minimum: float | int | None = None
    runtime_maximum: float | int | None = None
    neutral: Any = None
    execution_phase: str = ""

    def to_wire(self, value: Any) -> Any:
        # Declared unit conversion, not a choice of mechanic or a numeric clamp.
        if self.wire_boolean_true_value is not None:
            return self.wire_boolean_true_value if value else 0
        if self.wire_multiplier != 1:
            result = value * self.wire_multiplier
            if not isinstance(result, (int, float)) or not float(result).is_integer():
                raise ValueError("non-integral wire projection")
            return int(result)
        if self.wire_divisor != 1:
            if self.kind == "integer":
                if value % self.wire_divisor:
                    raise ValueError("non-integral wire projection")
                return value // self.wire_divisor
            return value / self.wire_divisor
        return value

    def schema(self) -> dict[str, Any]:
        out: dict[str, Any] = {"type": self.kind}
        if self.minimum is not None:
            out["minimum"] = self.minimum
        if self.maximum is not None:
            out["maximum"] = self.maximum
        if self.multiple_of is not None:
            out["multipleOf"] = self.multiple_of
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
        if self.neutral is not None:
            out["x-infini-neutral"] = self.neutral
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
        variant: dict[str, Any] = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "id": {
                    "type": "string",
                    "pattern": r"^[a-z][a-z0-9_]{0,47}$",
                    "description": "Stable call id used by Repair and self-evaluation runtimeRefs.",
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
        if self.name in {"spawn_entity_on_event", "pull_on_event"}:
            variant["properties"]["params"]["if"] = {
                "properties": {"event": {"const": "periodic"}}, "required": ["event"],
            }
            variant["properties"]["params"]["then"] = {"required": ["periodTicks"]}
        return variant

    def prompt_card(self) -> dict[str, Any]:
        params: dict[str, dict[str, Any]] = {}
        for name, spec in self.params.items():
            row: dict[str, Any] = {
                "type": spec.kind,
                "meaning": spec.description,
            }
            if spec.required:
                row["required"] = True
            if spec.minimum is not None:
                row["min"] = spec.minimum
            if spec.maximum is not None:
                row["max"] = spec.maximum
            if spec.multiple_of is not None:
                row["multipleOf"] = spec.multiple_of
            if spec.enum:
                row["enum"] = list(spec.enum)
            if spec.pattern:
                row["pattern"] = spec.pattern
            if spec.units:
                row["units"] = spec.units
            if spec.semantic_type and spec.semantic_type != spec.units:
                row["semanticType"] = spec.semantic_type
            if spec.reference is not None:
                row["reference"] = spec.reference.card()
            if spec.default is not None:
                row["default"] = spec.default
            if spec.neutral is not None:
                row["neutral"] = spec.neutral
            params[name] = row
        card: dict[str, Any] = {
            "fn": self.name,
            "does": self.summary,
            "targets": list(self.target_kinds),
            "params": params,
        }
        if self.exclusive_group:
            card["exclusiveGroup"] = self.exclusive_group
        if self.position_ownership != "none":
            card["positionOwnership"] = self.position_ownership
        if self.allowed_events:
            card["acceptedEvents"] = list(self.allowed_events)
        if self.emitted_events:
            card["emitsEvents"] = list(self.emitted_events)
        if self.requirements:
            card["requires"] = [row.card() for row in self.requirements]
        if self.multiplicity != "single_per_target":
            card["multiplicity"] = self.multiplicity
        if self.performance_budget != "bounded by runtime program limits":
            card["budget"] = self.performance_budget
        return card

    def author_prompt_card(self) -> dict[str, Any]:
        """Compact only repeated presentation metadata, never the authored contract.

        The complete prompt_card remains the machine/audit projection. Gemini's
        json_object transport does not send the local provider schema, so bounds,
        types, enums, patterns, references and dependencies stay in this card.
        """
        card = self.prompt_card()
        for name, row in card["params"].items():
            spec = self.params[name]
            if self.name == "configure_armor":
                if name.startswith("setBonus"):
                    row["meaning"] = row["meaning"].removeprefix(
                        "Matching armor set (head piece only; matching head, body and legs must actually be equipped): "
                    )
                elif (name in CAPABILITY_REGISTRY["configure_accessory"].params
                      and spec.description == CAPABILITY_REGISTRY["configure_accessory"].params[name].description):
                    row.pop("meaning", None)
            # All required fields are the default; optionality is explicit.
            row.pop("required", None)
            if not spec.required:
                row["optional"] = True
            # semanticType labels repeat the parameter meaning/units and are
            # often generic (including bounded_text for boolean parameters).
            row.pop("semanticType", None)
            # A zero neutral for an optional bounded parameter is not a new
            # value or design decision; absence and the numeric bounds remain.
            if not spec.required and spec.neutral == 0:
                row.pop("neutral", None)
            for suffix, units in (("Ticks", "ticks"), ("Tiles", "tiles"),
                                  ("Px", "pixels"), ("Radians", "radians")):
                if name.endswith(suffix) and spec.units == units:
                    row.pop("units", None)
                    break
        return card

    def audit_card(self) -> dict[str, Any]:
        """Complete machine projection; hook/wire/authority are not LLM design choices."""
        card = self.prompt_card()
        card.update({
            "slot": self.component_slot,
            "authority": self.network_authority,
            "authorityByEffect": dict(self.authority_by_effect),
            "positionOwnership": self.position_ownership,
            "requires": [row.card() for row in self.requirements],
            "wirePaths": list(self.final_wire_paths),
            "csharpOwner": self.csharp_owner,
            "multiplicity": self.multiplicity,
            "budget": self.performance_budget,
            "activationSpawnCountParam": self.activation_spawn_count_param or None,
            "meaningfulForStationary": self.meaningful_for_stationary,
            "acceptedEvents": list(self.allowed_events),
            "emitsEvents": list(self.emitted_events),
            "exclusiveGroup": self.exclusive_group or None,
        })
        return card



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
    wire_name: str = "",
    wire_divisor: int = 1,
    wire_multiplier: int = 1,
    multiple_of: float | int | None = None,
    wire_boolean_true_value: int | None = None,
    runtime_minimum: float | int | None = None,
    runtime_maximum: float | int | None = None,
    neutral: Any = None,
    execution_phase: str = "",
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
        wire_name=wire_name,
        wire_divisor=wire_divisor,
        wire_multiplier=wire_multiplier,
        multiple_of=multiple_of,
        wire_boolean_true_value=wire_boolean_true_value,
        runtime_minimum=runtime_minimum,
        runtime_maximum=runtime_maximum,
        neutral=neutral,
        execution_phase=execution_phase,
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
# Exact C# equipment GetDamage overloads, not all item/projectile DamageClass IDs.
EQUIPMENT_DAMAGE_CLASSES: Final[tuple[str, ...]] = ("generic", "melee", "ranged", "magic", "summon")
# Selective pre-IR clamps belong to the saved C# DTO, not to old Author names.
# GeneratedEquipmentBounds must retain these after class modifiers become typed calls.
LEGACY_EQUIPMENT_CLASS_DAMAGE_BOUNDS: Final[Mapping[str, Mapping[str, tuple[float, float]]]] = MappingProxyType({
    "accessory": MappingProxyType({"genericDamage": (-0.9, 3.0)}),
    "armor": MappingProxyType({"genericDamage": (-0.9, 3.0), "setBonusGenericDamage": (-0.9, 3.0)}),
})


def equipment_damage_wire_path(phase: str, damage_class: str, *, armor: bool) -> str:
    """One-to-one selector over the supported legacy equipment DTO fields."""
    if damage_class not in EQUIPMENT_DAMAGE_CLASSES or phase not in {"equipped", "matching_armor_set"}:
        raise ValueError("unsupported equipment damage selector")
    if phase == "matching_armor_set" and not armor:
        raise ValueError("accessories do not have a matching armor set phase")
    field = damage_class + "Damage"
    if phase == "matching_armor_set":
        field = "setBonus" + field[0].upper() + field[1:]
    return ("armor." if armor else "accessory.") + field

_COLOR = ("white", "red", "orange", "yellow", "green", "cyan", "blue", "purple", "pink", "gray", "black")
_USE_STYLE = ITEM_USE_STYLE_TOKENS
_MOVEMENT_OWNER = "InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile.Executors.cs"
_MODEL_OWNER = "InfiniCrafterLocal.Common.Models.RuntimeProgramSpec.cs"
_COMPILER_OWNER = "infini_local.core.runtime_authoring.compiler::compile_runtime_program"


def _equipment_params(*, armor: bool) -> Mapping[str, ParamSpec]:
    """One Author vocabulary for equipped effects and their exact DTO projection."""
    phase = "ModItem.UpdateEquip" if armor else "ModItem.UpdateAccessory"

    # Preserve exactly the clamps that existed before the Author refit.
    # Fields absent here were previously passed through the DTO unchanged:
    # their Author bounds are still validated, but legacy saved recipes are not narrowed.
    legacy_safety = ({
        "defense": (0, 500), "maxLife": (-500, 5000), "maxMana": (-500, 5000),
        "movementSpeed": (-0.9, 3),
        "genericCrit": (-100, 100),
        "setBonusMovementSpeed": (-0.9, 3), "setBonusLifeRegen": (-120, 200),
    } if armor else {
        "defense": (-100, 500), "maxLife": (-500, 5000), "maxMana": (-500, 5000),
        "lifeRegen": (-120, 200), "manaRegen": (-120, 200),
        "movementSpeed": (-0.9, 3),
        "genericCrit": (-100, 100), "endurance": (0, 0.75),
        "minionSlots": (0, 20), "sentrySlots": (0, 20),
        "lightStrength": (0, 1.5),
    })

    def stat(wire: str, meaning: str, low: float, high: float, units: str, *,
             percent: bool = False, integer: bool = False) -> ParamSpec:
        safety = legacy_safety.get(wire)
        return _p("integer" if integer else "number", meaning, required=False,
                  minimum=low, maximum=high, units=units, semantic_type=units,
                  wire_name=wire, wire_divisor=100 if percent else 1,
                  runtime_minimum=safety[0] if safety else None,
                  runtime_maximum=safety[1] if safety else None,
                  neutral=0, execution_phase=phase)

    p: dict[str, ParamSpec] = {
        "defensePoints": stat("defense", "Add to Item.defense; Terraria applies it, not an extra equip-hook adjustment", 0 if armor else -50, 200, "defense_points", integer=True),
        "maxLifePoints": stat("maxLife", "Add maximum life", -200, 1000, "life_points", integer=True),
        "maxManaPoints": stat("maxMana", "Add maximum mana", -200, 1000, "mana_points", integer=True),
        "lifeRegenHalfHpPerSecond": stat("lifeRegen", "Add Terraria lifeRegen units: +2 contributes +1 HP/s, -2 contributes -1 HP/s before other effects; 0 adds nothing", -100, 200, "half_hp_per_second", integer=True),
        "manaRegenBonusPoints": stat("manaRegen", "Add raw Player.manaRegenBonus points; 0 adds nothing, not mana/s", -100, 200, "mana_regen_bonus_points", integer=True),
        "moveSpeedBonusPercent": stat("movementSpeed", "Add percent/100 to Player.moveSpeed", -90, 300, "additive_percent", percent=True),
        "maxRunSpeedBonusPxPerTick": stat("maxRunSpeed", "Add to Player.maxRunSpeed, subject to other Terraria movement limits", -5, 20, "pixels_per_tick"),
        "jumpSpeedBonusPxPerTick": stat("jumpSpeed", "Add to Player.jumpSpeedBoost (positive raises jump speed)", -5, 20, "pixels_per_tick"),
        "genericCritChancePercentagePoints": stat("genericCrit", "Add percentage points to generic critical chance", -100, 100, "percentage_points"),
        "genericAttackSpeedBonusPercent": stat("attackSpeed", "Add percent/100 to generic attack speed", -90, 300, "additive_percent", percent=True),
        "genericKnockbackBonusPercent": stat("knockback", "Add percent/100 to generic StatModifier knockback; not flat points", -90, 300, "additive_percent", percent=True),
        "minionSlotsBonus": stat("minionSlots", "Add minion slots", 0, 20, "slots", integer=True),
        "sentrySlotsBonus": stat("sentrySlots", "Add sentry slots", 0, 20, "slots", integer=True),
        "manaCostReductionPercentagePoints": stat("manaCostReduction", "Subtract percent/100 from Player.manaCost factor, floored at 0.1", 0, 90, "percentage_points", percent=True),
        "ammoSaveChancePercent": stat("ammoSaveChance", "Equipped owner's ammo saving chance via Player.CanConsumeAmmo for any weapon; equipped item chances combine as 1−product(1−p)", 0, 99, "probability_percent", percent=True),
        "aggroPoints": stat("aggro", "Add raw Player.aggro engine points (negative reduces targeting); not a probability or radius", -1000, 1000, "aggro_points", integer=True),
        "damageReductionPercentagePoints": stat("endurance", "Add percent/100 to Player.endurance damage reduction", 0, 75, "percentage_points", percent=True),
        "genericArmorPenetrationPoints": stat("armorPenetration", "Add flat armor penetration points to DamageClass.Generic; not damage percent", 0, 100, "armor_points"),
        "whipRangeBonusPercent": stat("whipRange", "Add percent/100 to Player.whipRangeMultiplier", -90, 300, "additive_percent", percent=True),
        "taggedSummonSourceDamageBonusPercent": stat("summonTagDamage", "Multiply summon projectile source damage by 1+percent/100 only against an NPC tagged by this owner's generated whip", 0, 300, "source_damage_percent", percent=True),
        "lightStrength": stat("lightStrength", "Client-only RGB light coefficient multiplying lightColor; not tile radius; requires lightColor when positive", 0, 1.5, "light_intensity"),
        "lightColor": _p("string", "Explicit equipped light color", required=False, enum=_COLOR,
                         wire_name="lightColorName", neutral="", execution_phase=phase),
    }
    for name, meaning in (
        ("fallDamageImmune", "Prevent fall damage while equipped"),
        ("lavaImmune", "Grant lava immunity while equipped"),
        ("waterWalk", "Walk on water while equipped"),
    ):
        p[name] = _p("boolean", meaning, required=False, wire_name=name,
                     neutral=False, execution_phase=phase)
    if armor:
        set_phase = "ModItem.UpdateArmorSet; exact setKey on head, body and legs"
        set_effects = (
            "genericCritChancePercentagePoints",
            "moveSpeedBonusPercent", "lifeRegenHalfHpPerSecond", "manaRegenBonusPoints",
            "minionSlotsBonus", "sentrySlotsBonus", "manaCostReductionPercentagePoints",
            "ammoSaveChancePercent", "aggroPoints", "damageReductionPercentagePoints",
            "genericArmorPenetrationPoints",
        )
        for name in set_effects:
            spec = p[name]
            set_wire = "setBonus" + spec.wire_name[0].upper() + spec.wire_name[1:]
            safety = legacy_safety.get(set_wire)
            p["setBonus" + name[0].upper() + name[1:]] = replace(
                spec, description="Matching armor set (head piece only; matching head, body and legs must actually be equipped): " + spec.description,
                wire_name=set_wire,
                runtime_minimum=safety[0] if safety else None,
                runtime_maximum=safety[1] if safety else None,
                execution_phase=set_phase)
    return MappingProxyType(p)


_ACCESSORY_PRIMITIVES = _equipment_params(armor=False)
_ARMOR_PRIMITIVES = _equipment_params(armor=True)

_CAPS: list[CapabilitySpec] = [
    _cap(
        "configure_item_stats",
        "Set exact item stats; no weapon class or behaviour is inferred.",
        "item",
        ("item_body",),
        {
            "damageClass": _p("string", "Exact built-in token or loaded tModLoader DamageClass.FullName copied only from parent damageClass facts (not item FullName)", pattern=_DAMAGE_CLASS_PATTERN, semantic_type="terraria_damage_class"),
            "damage": _p("integer", "Base item damage", minimum=0, maximum=2000),
            "knockback": _p("number", "Item.knockBack engine strength, not pixels or damage", minimum=0, maximum=20),
            "useTimeTicks": _p("integer", "Terraria use/reuse interval (60 ticks/s), not the animation length", minimum=1, maximum=600, units="ticks", wire_name="useTime"),
            "useAnimationTicks": _p("integer", "Duration of one use animation, independent of useTimeTicks; differing values can allow multiple uses during one animation, not necessarily one projectile per click", minimum=1, maximum=600, units="ticks", wire_name="useAnimation"),
            "manaCost": _p("integer", "Mana consumed per use", minimum=0, maximum=500),
            "rarity": _p("integer", "Exact loaded Item.rare ID (built-in normal rarities are 0..11); copy modded IDs from parent facts, do not guess", minimum=0, maximum=65535, semantic_type="loaded_rarity_id"),
            "valueCopper": _p("integer", "Exact Terraria Item.value field in copper; NPC shop price/base value, not an inferred player resale amount", minimum=0, maximum=100000000, units="copper", wire_name="value"),
            "maxStack": _p("integer", "Maximum stack", minimum=1, maximum=9999),
            "craftYield": _p("integer", "Items granted by one craft", minimum=1, maximum=9999),
            "widthPx": _p("integer", "Inventory/world hitbox width", minimum=8, maximum=256, units="pixels", wire_name="width"),
            "heightPx": _p("integer", "Inventory/world hitbox height", minimum=8, maximum=256, units="pixels", wire_name="height"),
            "scale": _p("number", "Item display scale multiplier (1 unchanged)", minimum=0.25, maximum=4, wire_name="itemScale"),
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
            "useStyle": _p("string", "Named Terraria ItemUseStyleID", enum=_USE_STYLE, wire_name="useStyleName"),
            "autoReuse": _p("boolean", "Allow repeated use while input is held"),
            "useTurn": _p("boolean", "Allow facing turn during use"),
            "hideUseGraphic": _p("boolean", "Hide inventory sprite during use"),
            "disableMeleeHitbox": _p("boolean", "Disable vanilla item melee hitbox"),
            "channel": _p("boolean", "Keep use active while input is held"),
            "holdoutOffsetX": _p("integer", "Held draw offset X", minimum=-96, maximum=96, units="pixels"),
            "holdoutOffsetY": _p("integer", "Held draw offset Y", minimum=-96, maximum=96, units="pixels"),
            "handPose": _p("string", "Exact renderer hint", required=False, enum=("", "one_handed", "two_handed", "overhead", "forward")),
            "releaseTiming": _p("string", "Held-item presentation lifetime hint; immediate hides the held sprite, on_release/after_charge keep it while use is active", required=False, enum=("", "immediate", "on_release", "after_charge")),
        },
        py=_COMPILER_OWNER,
        cs="GeneratedItem.cs::CanUseItem/UseStyle",
        wire=("gameplay.useStyleName", "gameplay.autoReuse", "gameplay.useTurn", "gameplay.holdoutOffsetX", "gameplay.holdoutOffsetY", "gameplay.handPose", "gameplay.releaseTiming", "runtimeProgram.itemUse.*"),
        provenance="existing use_affordance and explicit root affordance fields",
        repair_group="item_use",
        lowering=("gameplay.useStyle", "gameplay.autoReuse", "gameplay.useTurn", "runtimeProgram.itemUse.*"),
    ),
    _cap(
        "configure_item_contact_hitbox",
        "Configure geometry for item-body contact that is enabled by a binding usePolicy; omitting this call keeps Terraria's unscaled hitbox.",
        "item_combat",
        ("item_body",),
        {
            "hitboxScale": _p("number", "Contact hitbox scale; 1 unchanged", minimum=0.5, maximum=2),
            "contactForgivenessPx": _p("integer", "Extend scaled contact hitbox by this many pixels on each side", minimum=0, maximum=64, units="pixels"),
        },
        py=_COMPILER_OWNER,
        cs="GeneratedItem.cs::UseItemHitbox/OnHitNPC",
        wire=("runtimeProgram.itemContact.*",),
        provenance="exact geometry for binding-owned item-body contact",
        repair_group="item_contact",
    ),
    _cap(
        "configure_vanilla_ammo_item",
        "Mark this generated item as one exact vanilla ammo category and projectile. Sets Item.ammo and Item.shoot; it does not configure a weapon to consume ammo.",
        "item",
        ("item_body",),
        {
            "ammoCategory": _p("string", "Exact stable Terraria AmmoID category", enum=VANILLA_AMMO_CATEGORY_TOKENS),
            "projectileId": _p("integer", "Exact vanilla ProjectileID fired when this ammo is consumed; do not guess", minimum=1, maximum=VANILLA_PROJECTILE_TYPE_ID_MAX, wire_name="ammoProjectileId"),
            "shootSpeedPxPerTick": _p("number", "Exact Item.shootSpeed contribution of this ammo to vanilla PickAmmo", minimum=-20, maximum=80, units="pixels_per_tick", wire_name="ammoShootSpeedPxPerTick"),
            "notAmmo": _p("boolean", "Exact Item.notAmmo flag for special ammo-slot/tooltip behaviour"),
        },
        py=_COMPILER_OWNER,
        cs="TerrariaRuntimeVocabulary.cs::ResolveAmmoCategory/GeneratedItemData.Apply.cs::ApplyToItem",
        wire=("gameplay.ammoCategory", "gameplay.ammoProjectileId", "gameplay.ammoShootSpeedPxPerTick", "gameplay.notAmmo"),
        provenance="existing ammo_behavior split into direct Terraria Item.ammo and Item.shoot fields",
        repair_group="ammo_item",
        lowering=("gameplay.ammoCategory", "gameplay.ammoProjectileId", "gameplay.ammoShootSpeedPxPerTick", "gameplay.notAmmo"),
    ),
    _cap(
        "restore_resources_on_use",
        "Restore exact life and/or mana when use succeeds.",
        "item_utility",
        ("item_body",),
        {
            "healLife": _p("integer", "Life restored", minimum=0, maximum=500),
            "healMana": _p("integer", "Mana restored", minimum=0, maximum=500),
            "potionSickness": _p("boolean", "Set exact Terraria Item.potion flag; false allows non-potion healing items", wire_name="potion"),
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
            "buffId": _p("integer", "Exact loaded BuffID/ModContent.BuffType; copy from parent facts, do not guess", minimum=1, maximum=65535, semantic_type="loaded_buff_id", wire_name="buffCode"),
            "durationTicks": _p("integer", "Buff duration", minimum=1, maximum=21600, units="ticks", wire_name="buffTime"),
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
            "miningSpeedMultiplier": _p("number", "Divides Player.pickSpeed (mining-time factor); >1 mines faster", minimum=0.25, maximum=4),
            "lightStrength": _p("number", "Client light RGB coefficient multiplying selected light color; not tile radius", minimum=0, maximum=1.5, wire_name="emitLightStrength"),
            "lightColor": _p("string", "Canonical light color", enum=_COLOR, wire_name="lightColorName"),
            "oreSenseEnabled": _p("boolean", "Enable Terraria spelunker-style ore highlighting; not a radius", semantic_type="boolean_capability", wire_name="oreSenseRadiusTiles", wire_boolean_true_value=1, neutral=False),
            "movementSpeed": _p("number", "Additive Player.moveSpeed factor; 0.2 adds 20% before other modifiers", minimum=-0.5, maximum=2),
            "jumpBoost": _p("number", "Add to Player.jumpSpeedBoost in pixels/tick", minimum=0, maximum=8),
            "manaRegen": _p("integer", "Add Player.manaRegenBonus engine points; not directly mana/second", minimum=0, maximum=120),
            "lifeRegenHpPerSecond": _p("number", "Generated buff: HP restored per second before other effects; exact half-HP steps map to Terraria Player.lifeRegen units (2 units = 1 HP/s)", minimum=0, maximum=60, multiple_of=0.5, units="HP/s", wire_name="lifeRegen", wire_multiplier=2),
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
        "Set exact pick/axe/hammer powers and mining speed. Requires explicit item-use configuration and one executable primary_use binding so Terraria can execute mining.",
        "item_tool",
        ("item_body",),
        {
            "pickPower": _p("integer", "Terraria Item.pick tooltip power percent", minimum=0, maximum=1000),
            "axePowerTooltipPercent": _p("integer", "Axe power as displayed in Terraria's tooltip; exact Item.axe internal value = this / 5", minimum=0, maximum=500, multiple_of=5, units="tooltip percent", wire_name="axePower", wire_divisor=5),
            "hammerPower": _p("integer", "Terraria Item.hammer tooltip power percent", minimum=0, maximum=1000),
            "miningSpeedScale": _p("number", "Divides Player.pickSpeed (mining-time factor); >1 mines faster", minimum=0.1, maximum=4),
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
            "placeStyle": _p("integer", "Exact Item.placeStyle style index for the loaded tile/wall, not a universal visual style", minimum=0, maximum=255),
        },
        py=_COMPILER_OWNER,
        cs="RuntimeProgramSpec.cs::RuntimeBindingActionSpec",
        wire=("runtimeProgram.bindings[].usePolicy.action.placement.*",),
        provenance="placement payload referenced by one exact binding transaction",
        repair_group="placeable",
        lowering=("runtimeProgram.bindings[].usePolicy.action.placement.*",),
    ),
    _cap(
        "require_use_condition",
        "Gate use on one explicit runtime condition.",
        "item",
        ("item_body",),
        {
            "mode": _p("string", "Use condition", enum=("grounded", "not_wet", "life_above", "mana_above"), wire_name="useConditionMode"),
            "minLife": _p("integer", "Current HP (Player.statLife >= minLife) required for life_above; equality allowed", required=False, minimum=0, maximum=1000, wire_name="useConditionMinLife"),
            "minMana": _p("integer", "Current mana points (Player.statMana >= minMana) required for mana_above; equality allowed", required=False, minimum=0, maximum=1000, wire_name="useConditionMinMana"),
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
            "strength": _p("number", "Client light RGB coefficient multiplying selected color (not a tile radius)", minimum=0.01, maximum=1.5, wire_name="holdLightStrength"),
            "color": _p("string", "Canonical light color", enum=_COLOR, wire_name="holdLightColorName"),
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
            "mode": _p("string", "Mobility executor", enum=("recall_home", "blink_to_cursor"), wire_name="mobilityMode"),
            "rangeTiles": _p("integer", "Maximum blink range", minimum=0, maximum=120, units="tiles", wire_name="mobilityRangeTiles"),
            "cooldownTicks": _p("integer", "Cooldown", minimum=0, maximum=3600, units="ticks", wire_name="mobilityCooldownTicks"),
            "safeTileOnly": _p("boolean", "Require safe destination", wire_name="mobilitySafeTileOnly"),
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
        "Apply independently chosen passive equipment effects; numeric bonuses use explicit units.",
        "equipment",
        ("item_body",),
        _ACCESSORY_PRIMITIVES,
        py=_COMPILER_OWNER,
        cs="GeneratedItem.cs::UpdateAccessory",
        wire=("accessory.*",),
        provenance="existing accessory_effect",
        repair_group="accessory",
        lowering=("accessory.*",),
    ),
    _cap(
        "configure_armor",
        "Apply independently chosen armor effects and matching three-piece set bonuses.",
        "equipment",
        ("item_body",),
        MappingProxyType({
            "slot": _p("string", "Armor equip slot", enum=("head", "body", "legs")),
            "setKey": _p("string", "Exact authored set key (empty when no matching set is intended)", pattern=r"^[a-z0-9_]{0,48}$", neutral=""),
            **_ARMOR_PRIMITIVES,
        }),
        py=_COMPILER_OWNER,
        cs="GeneratedArmorItems.cs/GeneratedItem.cs::UpdateEquip",
        wire=("armor.*",),
        provenance="existing armor_effect",
        repair_group="armor",
        lowering=("armor.*",),
    ),
    _cap(
        "add_equipment_damage_bonus",
        "Add one selected DamageClass modifier while equipped or with a matching armor set; each class and phase is a separate explicit choice.",
        "equipment",
        ("item_body",),
        {
            "phase": _p("string", "equipped applies while wearing this accessory/armor; matching_armor_set applies only on the head of a complete matching set", enum=("equipped", "matching_armor_set")),
            "damageClass": _p("string", "Equipped damage class; this equipment operation supports only these five classes", enum=EQUIPMENT_DAMAGE_CLASSES, semantic_type="equipment_damage_class"),
            "bonusPercent": _p("number", "Add this percent to the selected class damage additive modifier; 15 means +15%", minimum=-90, maximum=300, units="additive_percent", semantic_type="additive_percent", wire_divisor=100, neutral=0, execution_phase="UpdateAccessory/UpdateEquip or UpdateArmorSet according to authored phase"),
        },
        multiplicity="many_per_target",
        py=_COMPILER_OWNER,
        cs="GeneratedItem.cs::UpdateAccessory/UpdateEquip/UpdateArmorSet",
        wire=(),
        provenance="factorized equipment GetDamage(DamageClass) without changing legacy DTO",
        repair_group="equipment_class_damage",
    ),
    _cap(
        "configure_spawn",
        "Set how this entity is spawned; does not choose its movement or damage.",
        "entity_spawn",
        PROJECTILE_ENTITY_KINDS,
        {
            "speedPxPerTick": _p("number", "Initial Projectile.velocity pixels per projectile update; without steering/collisions, speed 10 with extraUpdates=1 moves ~20 px/world tick", minimum=0, maximum=80, units="pixels/projectile update"),
            "count": _p("integer", "Default root binding spawn count per activation; event actions and target_and_fire select their own counts", minimum=1, maximum=12),
            "spreadRadians": _p("number", "Total angular spread", minimum=0, maximum=6.283185307179586, units="radians"),
            "offsetPx": _p("integer", "Forward spawn offset", minimum=-128, maximum=256, units="pixels"),
            "aim": _p("string", "Initial aim source: cursor=spawn-to-cursor, facing=owner direction, velocity=incoming activation direction, none=zero velocity", enum=("cursor", "facing", "velocity", "none")),
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
            "damageClass": _p("string", "Exact built-in token or loaded tModLoader DamageClass.FullName copied only from parent damageClass facts (not item FullName)", pattern=_DAMAGE_CLASS_PATTERN, semantic_type="terraria_damage_class"),
            "damage": _p("integer", "Projectile base damage", minimum=0, maximum=2000),
            "knockback": _p("number", "Projectile.knockBack engine strength, not pixels or damage", minimum=0, maximum=20),
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
            "drawScale": _p("number", "Projectile sprite draw multiplier before entity visual scale; 1 unchanged, not damage hitbox size", minimum=0.25, maximum=4),
            "hitboxScale": _p("number", "Runtime damage hitbox multiplier; 1 unchanged (beam/whip use special line collisions)", minimum=0.25, maximum=3),
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
            "extraUpdates": _p("integer", "Terraria Projectile.extraUpdates: adds this many AI/movement updates per world tick (1 + extraUpdates total)", minimum=0, maximum=5),
            "npcImmunityMode": _p("string", "owner uses Terraria shared owner immunity; local gives this projectile its own NPC timers", enum=("owner", "local")),
            "localNpcHitCooldownTicks": _p("integer", "Only npcImmunityMode=local: direct unscaled Projectile.localNPCHitCooldown, not a world-tick duration. -1 lets this projectile hit each NPC only once; 0..600 are engine local cooldown counts. owner mode uses shared owner immunity instead; with extraUpdates>0 do not infer elapsed seconds", minimum=-1, maximum=600, units="engine cooldown units"),
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
        "homingStrength": _p("number", "Per movement-update linear interpolation fraction toward target velocity", minimum=0.001, maximum=1),
    }, provenance="existing movement code 1"),
    _movement("move_gravity_arc", "Apply downward velocity acceleration per projectile update.", 2, {
        "gravityPerTick": _p("number", "Add to vertical velocity (pixels/update) per projectile update", minimum=0.001, maximum=2, units="pixels/update per projectile update"),
    }, provenance="existing movement code 2"),
    _movement("move_drift", "Multiply velocity by authored retention per projectile update.", 3, {
        "velocityRetention": _p("number", "Multiply velocity each projectile update (1 + extraUpdates per world tick); 1 preserves speed, below 1 slows, above 1 accelerates; not necessarily retention per 1/60 s", minimum=0.8, maximum=1.05),
    }, provenance="existing movement code 3"),
    _movement("move_orbit", "Curve around the owner while remaining a projectile.", 4, {
        "rangeTiles": _p("number", "Orbit leash", minimum=1, maximum=80, units="tiles"),
    }, provenance="existing movement code 4"),
    _movement("move_boomerang", "Fly out, then return to the owner.", 5, {
        "returnAfterTicks": _p("integer", "Outbound duration", minimum=1, maximum=600, units="ticks"),
        "returnSpeed": _p("number", "Return speed", minimum=1, maximum=80, units="pixels/projectile update"),
    }, provenance="existing movement code 5"),
    _movement("move_bounce", "Use per-update gravity and authored tile bounces.", 6, {
        "gravityPerTick": _p("number", "Add to vertical velocity (pixels/update) per projectile update", minimum=0.001, maximum=2, units="pixels/update per projectile update"),
    }, provenance="existing movement code 6"),
    _movement("move_sine_homing", "Combine sinusoidal drift with bounded homing.", 7, {
        "rangeTiles": _p("number", "Target search radius", minimum=1, maximum=120, units="tiles"),
        "homingStrength": _p("number", "Per movement-update linear interpolation fraction toward target velocity", minimum=0.001, maximum=1),
        "waveAmplitude": _p("number", "Raw lateral velocity coefficient: sin(age×0.18) × waveAmplitude × 0.03 before velocity direction normalization; not displacement pixels", minimum=0, maximum=64, units="engine lateral velocity coefficient"),
    }, provenance="existing movement code 7"),
    _movement("move_phase", "Phase-drift with explicit tile collision still controlled separately.", 8, {
        "phaseStrength": _p("number", "Per-update velocity rotation = sin(age×0.1) × strength × 0.01 radians; not collision phasing", minimum=0, maximum=1),
    }, provenance="existing movement code 8"),
    _movement("move_accelerate", "Multiply speed up to an explicit cap.", 9, {
        "acceleration": _p("number", "Velocity multiplier per projectile update until maxSpeed cap; 1 unchanged", minimum=1.0, maximum=1.2),
        "maxSpeed": _p("number", "Speed cap", minimum=1, maximum=80, units="pixels/projectile update"),
    }, provenance="existing movement code 9"),
    _movement("move_spiral", "Rotate velocity by an authored angle per projectile update.", 10, {
        "turnRadiansPerTick": _p("number", "Angular velocity turn per projectile update", minimum=-0.5, maximum=0.5, units="radians/update"),
    }, provenance="existing movement code 10"),
    _movement("move_vortex_orb", "Run the existing vortex-orb controller.", 11, {
        "pullStrength": _p("number", "Add NPC velocity impulse of strength × clamped knockBackResist toward center per projectile update", minimum=0, maximum=4),
        "rangeTiles": _p("number", "Pull radius", minimum=1, maximum=80, units="tiles"),
    }, provenance="existing movement code 11"),
    _movement("move_blackhole_pull", "Run the existing black-hole pull controller.", 12, {
        "pullStrength": _p("number", "Add NPC velocity impulse of strength × clamped knockBackResist toward center per projectile update", minimum=0, maximum=4),
        "rangeTiles": _p("number", "Pull radius", minimum=1, maximum=80, units="tiles"),
    }, provenance="existing movement code 12"),
    _movement("move_proximity_missile", "Home; proximity inside proximityRadiusPx triggers on_expire then on_kill and kills the missile. on_hit requires an actual hit, not mere proximity.", 13, {
        "rangeTiles": _p("number", "Detection/search radius", minimum=1, maximum=120, units="tiles"),
        "homingStrength": _p("number", "Per movement-update linear interpolation fraction toward target velocity", minimum=0.001, maximum=1),
        "proximityRadiusPx": _p("integer", "Trigger radius", minimum=4, maximum=512, units="pixels"),
    }, provenance="existing movement code 13"),
    _movement("move_returning_glaive", "Fly, spin and return to the owner.", 14, {
        "returnAfterTicks": _p("integer", "Outbound duration", minimum=1, maximum=600, units="ticks"),
        "returnSpeed": _p("number", "Return speed", minimum=1, maximum=80, units="pixels/projectile update"),
    }, provenance="existing movement code 14"),
    _movement("move_expanding_wave", "Expand the entity while preserving authored collision/damage.", 15, {
        "scalePerTick": _p("number", "Additive Projectile.scale delta per projectile update, capped by maxScale", minimum=0.001, maximum=0.5),
        "maxScale": _p("number", "Projectile.scale cap (not a pixel radius)", minimum=0.25, maximum=4),
    }, provenance="existing movement code 15"),
    _movement("move_flail_tether", "Tether to owner, fly out and return; only movement/owner controller.", 16, {
        "rangeTiles": _p("number", "Maximum tether length", minimum=2, maximum=60, units="tiles"),
        "returnSpeed": _p("number", "Return speed", minimum=1, maximum=80, units="pixels/projectile update"),
    }, targets=("owner_attached_projectile",), provenance="flail movement extracted from the retired melee macro"),
    _movement("move_yoyo_hover", "Follow owner cursor inside a leash and return on release.", 17, {
        "rangeTiles": _p("number", "Cursor leash", minimum=2, maximum=60, units="tiles"),
        "returnSpeed": _p("number", "Return speed", minimum=1, maximum=80, units="pixels/projectile update"),
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
            "powerMultiplier": _p("number", "Full-charge damage/knockback multiplier; 1 unchanged", minimum=1, maximum=4),
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
            "shotEntity": _p("string", "Referenced projectile entity id", pattern=r"^[a-z][a-z0-9_]{0,47}$", wire_name="shotEntityId"),
            "intervalTicks": _p("integer", "Firing interval", minimum=6, maximum=3600, units="ticks"),
            "rangeTiles": _p("number", "Soft target range: previous target may be chosen outside it after distance discount", minimum=1, maximum=120, units="tiles"),
            "sameTargetBias": _p("number", "Previous target distance multiplied by (1 − min(bias, 0.9)); 0.9..1 saturates at 0.9", minimum=0, maximum=1),
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
            "entity": _p("string", "Referenced entity id", pattern=r"^[a-z][a-z0-9_]{0,47}$", wire_name="entityId"),
            "count": _p("integer", "Spawn count", minimum=1, maximum=12),
            "spreadRadians": _p("number", "Total angular spread", minimum=0, maximum=6.283185307179586, units="radians"),
            "damageMultiplier": _p("number", "Multiplier applied to the referenced child entity's authored base damage", minimum=0, maximum=4),
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
        "Deal bounded AoE damage around the event position; excludes an already-hit direct target.",
        "event",
        ("item_body", *PROJECTILE_ENTITY_KIND_ORDER),
        {
            "event": _p("string", "Source event", enum=("on_hit", "on_crit", "on_tile_collision", "on_expire", "on_kill")),
            "radiusPx": _p("integer", "Damage radius", minimum=8, maximum=768, units="pixels"),
            "damageMultiplier": _p("number", "Multiply event-owning entity's authored base damage: item_body uses configure_item_stats.damage, projectile uses set_projectile_damage.damage; rounded, at least 1 before target defense. 1 is base damage, 0.05 is 5% of base, not +5% or damageDone", minimum=0.05, maximum=4),
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
            "damageMultiplier": _p("number", "Multiply event-owning entity's authored base damage: item_body uses configure_item_stats.damage, projectile uses set_projectile_damage.damage; rounded, at least 1 before target defense. 1 is base damage, 0.05 is 5% of base, not +5% or damageDone", minimum=0.05, maximum=2),
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
            "strength": _p("number", "Add velocity impulse toward selected endpoint on each event (NPC impulse also multiplies knockBackResist); not displacement", minimum=0.01, maximum=4),
            "radiusTiles": _p("number", "NPC search radius only with no directTarget; ignored for owner_to_target", minimum=1, maximum=60, units="tiles"),
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
            "damageFraction": _p("number", "Fraction of damageDone healed (0.15 = 15%), capped by maxHeal; not a whole-number percent", minimum=0.001, maximum=1),
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
        "Execute owner teleport to the recorded event position, limited by range and shared mobility cooldown.",
        "event",
        PROJECTILE_ENTITY_KINDS,
        {
            "event": _p("string", "Source event", enum=("on_hit", "on_tile_collision", "on_expire")),
            "rangeTiles": _p("integer", "Maximum movement range", minimum=1, maximum=120, units="tiles"),
            "cooldownTicks": _p("integer", "Shared owner mobility cooldown", minimum=0, maximum=3600, units="ticks"),
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
            "strength": _p("number", "Client light RGB coefficient multiplying selected color (not a tile radius)", minimum=0.01, maximum=1.5),
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
        ("periodic",),
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
        "The only active binding that enables authored item buffs/resource/mobility effects; combine with item_body.on_use events for simultaneous projectile spawns.",
        ("restore_resources_on_use", "apply_vanilla_buff_on_use", "apply_generated_buff_on_use", "move_player_on_use"),
    ),
    "place_item": BindingActionSpec(
        "place_item", ("item_body",), ("primary_use", "alternate_use"),
        "Execute the one placement payload referenced by this binding action.",
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
    "equipped": InputKindSpec("equipped", True, ("equip_passive",), "Accessory/armor equipped state; exactly one binding owns this input."),
})

EVENT_KIND_REGISTRY: Final[Mapping[str, EventKindSpec]] = MappingProxyType({
    "on_use": EventKindSpec(
        "on_use",
        ("item_body",),
        (),
        "Emitted when an active item-body use binding succeeds.",
        producer_binding_inputs=("primary_use", "alternate_use"),
        producer_binding_actions=("spawn_entity", "use_item_body", "apply_item_effects"),
        producer_binding_kinds=("item_body",),
    ),
    "on_spawn": EventKindSpec(
        "on_spawn", PROJECTILE_ENTITY_KIND_ORDER, (),
        "Emitted once when a runtime projectile entity activates.",
    ),
    "on_hit": EventKindSpec(
        "on_hit", ("item_body", *PROJECTILE_ENTITY_KIND_ORDER),
        ("set_projectile_damage",),
        "Emitted after explicit contact/projectile damage hits an NPC.",
        producer_binding_inputs=("primary_use", "alternate_use"),
        producer_binding_actions=("spawn_entity", "use_item_body", "apply_item_effects"),
        producer_binding_kinds=("item_body",),
        producer_binding_contact_damage=True,
    ),
    "on_crit": EventKindSpec(
        "on_crit", ("item_body", *PROJECTILE_ENTITY_KIND_ORDER),
        ("set_projectile_damage",),
        "Emitted after an explicitly damaging hit is critical.",
        producer_binding_inputs=("primary_use", "alternate_use"),
        producer_binding_actions=("spawn_entity", "use_item_body", "apply_item_effects"),
        producer_binding_kinds=("item_body",),
        producer_binding_contact_damage=True,
    ),
    "on_tile_collision": EventKindSpec(
        "on_tile_collision",
        PROJECTILE_ENTITY_KIND_ORDER,
        ("set_projectile_collision",),
        "Emitted when explicit tile collision occurs.",
        producer_exact_params=MappingProxyType({
            "set_projectile_collision": MappingProxyType({"tileCollide": True}),
        }),
    ),
    "on_expire": EventKindSpec(
        "on_expire", PROJECTILE_ENTITY_KIND_ORDER, ("set_projectile_lifetime",),
        "Emitted immediately before natural lifetime expiration, or when move_proximity_missile detonates on proximity; an early kill otherwise emits on_kill only.",
    ),
    "on_kill": EventKindSpec(
        "on_kill", PROJECTILE_ENTITY_KIND_ORDER, (),
        "Emitted when the projectile entity is killed.",
    ),
    "periodic": EventKindSpec(
        "periodic", ("item_body", *PROJECTILE_ENTITY_KIND_ORDER), (),
        "Bounded periodic event; each action must declare periodTicks >= 6.",
    ),
    "on_release": EventKindSpec(
        "on_release", PROJECTILE_ENTITY_KIND_ORDER, ("charge_then_release",),
        "Emitted by charge_then_release when the held charge is released.",
    ),
    "channel_complete": EventKindSpec(
        "channel_complete", PROJECTILE_ENTITY_KIND_ORDER, ("charge_then_release",),
        "Emitted by charge_then_release after a full authored charge.",
    ),
})


def event_dependency_alternatives(event: str, kind: str) -> tuple[EventDependencyAlternative, ...]:
    """Project finite producer alternatives from registry data without choosing one."""

    event_spec = EVENT_KIND_REGISTRY.get(event)
    kind_spec = ENTITY_KIND_REGISTRY.get(kind)
    if event_spec is None or kind_spec is None or kind not in event_spec.source_kinds:
        return ()
    binding_requirement = (
        EventBindingRequirement(
            event_spec.producer_binding_inputs,
            event_spec.producer_binding_actions,
            event_spec.producer_binding_contact_damage,
        )
        if event_spec.producer_binding_inputs and kind in event_spec.producer_binding_kinds
        else None
    )
    if event in kind_spec.base_events:
        return (EventDependencyAlternative(),)
    alternatives: list[EventDependencyAlternative] = []
    for capability_name in event_spec.producer_capabilities:
        capability = CAPABILITY_REGISTRY.get(capability_name)
        if capability is None or kind not in capability.target_kinds:
            continue
        alternatives.append(EventDependencyAlternative(
            required_calls=(EventCallRequirement.create(
                capability_name,
                event_spec.producer_exact_params.get(capability_name),
            ),),
            required_bindings=((binding_requirement,) if binding_requirement is not None else ()),
        ))
    if not alternatives and binding_requirement is not None:
        alternatives.append(EventDependencyAlternative(required_bindings=(binding_requirement,)))
    return tuple(alternatives)


def event_alternative_is_present(
    alternative: EventDependencyAlternative,
    *,
    target_id: str,
    target_calls: Iterable[Mapping[str, Any]],
    bindings: Iterable[Mapping[str, Any]],
) -> bool:
    call_rows = tuple(target_calls)
    binding_rows = tuple(bindings)

    def call_present(requirement: EventCallRequirement) -> bool:
        expected = requirement.exact_params_dict()
        for call in call_rows:
            if str(call.get("fn") or "") != requirement.capability:
                continue
            raw_params = call.get("params")
            params: Mapping[str, Any] = raw_params if isinstance(raw_params, Mapping) else {}
            if all(params.get(key) == value for key, value in expected.items()):
                return True
        return False

    def binding_present(requirement: EventBindingRequirement) -> bool:
        allowed_inputs = set(requirement.any_of_inputs)
        allowed_actions = set(requirement.any_of_actions)
        return any(
            str(row.get("input") or "") in allowed_inputs
            and (not allowed_actions or action_kind(row) in allowed_actions)
            and binding_target_id(row) == target_id
            and (
                requirement.required_contact_damage is None
                or binding_contact_damage(row) is requirement.required_contact_damage
            )
            for row in binding_rows
        )

    return (
        all(call_present(requirement) for requirement in alternative.required_calls)
        and all(binding_present(requirement) for requirement in alternative.required_bindings)
    )


def event_dependency_descriptors(
    alternatives: Iterable[EventDependencyAlternative],
) -> tuple[str, ...]:
    allowed: list[str] = []
    for alternative in alternatives:
        for requirement in alternative.required_calls:
            exact = requirement.exact_params_dict()
            suffix = "" if not exact else "(" + ",".join(
                f"{key}={value!r}" for key, value in exact.items()
            ) + ")"
            allowed.append(requirement.capability + suffix)
        for requirement in alternative.required_bindings:
            descriptor = "binding input one of: " + ",".join(requirement.any_of_inputs)
            if requirement.any_of_actions:
                descriptor += "; action one of: " + ",".join(requirement.any_of_actions)
            if requirement.required_contact_damage is not None:
                descriptor += "; contactDamage=" + str(requirement.required_contact_damage).lower()
            allowed.append(descriptor)
    return tuple(allowed)


if tuple(ENTITY_KIND_REGISTRY) != ENTITY_KINDS:
    raise RuntimeError("ENTITY_KINDS must be the exact entity-kind registry projection")
if tuple(INPUT_KIND_REGISTRY) != INPUT_KINDS:
    raise RuntimeError("INPUT_KINDS must be the exact input registry projection")
if tuple(BINDING_ACTION_REGISTRY) != BINDING_ACTIONS:
    raise RuntimeError("BINDING_ACTIONS must be the exact binding-action registry projection")
if tuple(EVENT_KIND_REGISTRY) != EVENT_KINDS:
    raise RuntimeError("EVENT_KINDS must be the exact event registry projection")


def _exact_wire_paths(cap: CapabilitySpec) -> tuple[str, ...]:
    if cap.name == "configure_item_stats":
        return tuple(f"gameplay.{spec.wire_name or name}" for name, spec in cap.params.items())
    item_paths: dict[str, tuple[str, ...]] = {
        "configure_item_use": (
            "gameplay.useStyleName", "gameplay.autoReuse", "gameplay.useTurn",
            "gameplay.holdoutOffsetX", "gameplay.holdoutOffsetY", "gameplay.handPose", "gameplay.releaseTiming",
            "runtimeProgram.itemUse.configured", "runtimeProgram.itemUse.useStyle", "runtimeProgram.itemUse.hideUseGraphic", "runtimeProgram.itemUse.disableMeleeHitbox",
            "runtimeProgram.itemUse.channel", "runtimeProgram.itemUse.handPose", "runtimeProgram.itemUse.releaseTiming",
            "runtimeProgram.itemUse.holdoutOffsetX", "runtimeProgram.itemUse.holdoutOffsetY",
        ),
        "configure_item_contact_hitbox": ("runtimeProgram.itemContact.hitboxScale", "runtimeProgram.itemContact.contactForgivenessPx"),
        "configure_vanilla_ammo_item": ("gameplay.ammoCategory", "gameplay.ammoProjectileId", "gameplay.ammoShootSpeedPxPerTick", "gameplay.notAmmo"),
        "restore_resources_on_use": ("gameplay.healLife", "gameplay.healMana", "gameplay.potion"),
        "apply_vanilla_buff_on_use": ("gameplay.extraBuffs[].buffCode", "gameplay.extraBuffs[].buffTime"),
        "apply_generated_buff_on_use": (
            "gameplay.generatedBuff.durationTicks", "gameplay.generatedBuff.miningSpeedMultiplier", "gameplay.generatedBuff.emitLightStrength",
            "gameplay.generatedBuff.lightColorName", "gameplay.generatedBuff.oreSenseRadiusTiles", "gameplay.generatedBuff.movementSpeed",
            "gameplay.generatedBuff.jumpBoost", "gameplay.generatedBuff.manaRegen", "gameplay.generatedBuff.lifeRegen",
        ),
        "configure_tool": ("gameplay.pickPower", "gameplay.axePower", "gameplay.hammerPower", "gameplay.miningSpeedScale"),
        "configure_placeable": ("runtimeProgram.bindings[].usePolicy.action.placement.tileId", "runtimeProgram.bindings[].usePolicy.action.placement.wallId", "runtimeProgram.bindings[].usePolicy.action.placement.placeStyle"),
        "require_use_condition": ("gameplay.useConditionMode", "gameplay.useConditionMinLife", "gameplay.useConditionMinMana"),
        "add_hold_light": ("gameplay.holdLightStrength", "gameplay.holdLightColorName"),
        "move_player_on_use": ("gameplay.mobilityMode", "gameplay.mobilityRangeTiles", "gameplay.mobilityCooldownTicks", "gameplay.mobilitySafeTileOnly"),

    }
    if cap.name in item_paths:
        return item_paths[cap.name]
    if cap.name in {"configure_accessory", "configure_armor"}:
        prefix = "accessory" if cap.name == "configure_accessory" else "armor"
        return (f"{prefix}.enabled", *(f"{prefix}.{spec.wire_name or name}" for name, spec in cap.params.items()))
    if cap.name == "add_equipment_damage_bonus":
        return tuple(
            equipment_damage_wire_path(phase, damage_class, armor=armor)
            for armor in (False, True)
            for phase in (("equipped", "matching_armor_set") if armor else ("equipped",))
            for damage_class in EQUIPMENT_DAMAGE_CLASSES
        )
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
        if cap.name == "move_owner_on_event":
            mapped.append("runtimeProgram.entities[].events[].mode")  # fixed DTO discriminator for the only executed destination
        return tuple(mapped)
    if cap.name == "emit_light_while_active":
        return tuple(f"runtimeProgram.entities[].light.{name}" for name in cap.params)
    raise RuntimeError(f"missing exact wire contract for capability {cap.name}")


def _component_slot(cap: CapabilitySpec) -> str:
    direct = {
        "configure_item_stats": "item_stats", "configure_item_use": "item_use", "configure_item_contact_hitbox": "item_contact",
        "configure_vanilla_ammo_item": "ammo_item", "restore_resources_on_use": "resource_restore", "apply_vanilla_buff_on_use": "use_buff",
        "apply_generated_buff_on_use": "generated_use_buff", "configure_tool": "tool", "configure_placeable": "placeable",
        "require_use_condition": "use_condition", "add_hold_light": "held_light", "move_player_on_use": "item_mobility",
        "configure_accessory": "accessory", "configure_armor": "armor", "add_equipment_damage_bonus": "equipment_class_damage", "configure_spawn": "spawn",
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
        "configure_item_contact_hitbox": "Content/Items/GeneratedItem.cs::UseItemHitbox/OnHitNPC",
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
        "add_equipment_damage_bonus": "Content/Items/GeneratedItem.cs::UpdateAccessory/UpdateEquip/UpdateArmorSet",
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
    if cap.name in {"apply_status_on_event", "chain_damage_on_event"}:
        return "owner_execute_sync", {}
    if cap.name == "damage_area_on_event":
        return "server_execute", {"on_hit": "owner_execute_sync", "on_crit": "owner_execute_sync"}
    if cap.name == "pull_on_event":
        return "server_execute", {
            "owner_to_target": "owner_execute_sync",
            "target_to_owner": "server_execute", "target_to_entity": "server_execute",
            "on_hit:target_to_owner": "owner_request_server_execute",
            "on_hit:target_to_entity": "owner_request_server_execute",
        }
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
    if cap.name == "add_equipment_damage_bonus":
        return (RequirementSpec(
            "capability_group_present", target="item_body", any_of=("configure_accessory", "configure_armor"),
            message="Equipment class damage requires exactly one explicit accessory or armor configuration on the same item.",
        ),)
    if cap.name == "spawn_over_target":
        return (RequirementSpec("capability_present", capability="configure_spawn", message="spawn_over_target extends the same entity's explicit spawn component"),)
    if cap.name in {"channel_beam", "charge_then_release"}:
        rows = [RequirementSpec("item_capability_param", capability="configure_item_use", target="item_body", param="channel", equals=True, message="channel controller requires channel=true on item_body")]
        if cap.name == "charge_then_release":
            rows.append(RequirementSpec("capability_group_present", target="same_target", any_of=tuple(sorted(row.name for row in _CAPS if row.category == "movement")), message="released projectile needs an explicit post-release movement"))
        return tuple(rows)
    if cap.name == "configure_placeable":
        return (
            RequirementSpec("at_least_one_param_nonnegative", param="tileId|wallId", message="at least one of tileId/wallId must be enabled"),
            RequirementSpec(
                kind="binding_action_reference",
                target="item_body",
                any_of=("place_item",),
                message="configure_placeable must be referenced by exactly one binding usePolicy.action.placementCallId.",
            ),
        )
    if cap.name == "configure_tool":
        return (
            RequirementSpec(
                kind="capability_present",
                capability="configure_item_use",
                target="item_body",
                message="A configured tool requires explicit item-use configuration; no use behavior is inferred.",
            ),
            RequirementSpec(
                kind="binding_tuple_present",
                target="any_entity",
                any_of=("primary_use|use_item_body|contactDamage=true", "primary_use|spawn_entity"),
                message="A configured tool requires one explicit primary-use root matching one listed binding transaction. Tool power remains on the item body; the action root is authored explicitly and no ownership is inferred.",
            ),
        )
    if cap.name in BINDING_ACTION_REGISTRY["apply_item_effects"].required_item_capabilities_any_of:
        requirements = [RequirementSpec(
            kind="binding_action_present", target="item_body", any_of=("apply_item_effects",),
            message="This item-use effect executes only through an explicit apply_item_effects binding on item_body; a spawn_entity or use_item_body binding alone does not apply it.",
        )]
        if cap.name == "apply_generated_buff_on_use":
            requirements.append(RequirementSpec(
                "non_neutral_param", message="at least one generated-buff effect must be non-neutral",
            ))
        return tuple(requirements)
    if cap.name == "configure_accessory":
        return (RequirementSpec(
            kind="at_least_one_param_nonzero",
            nonzero_params=tuple(name for name in cap.params if name != "lightColor"),
            any_of=("add_equipment_damage_bonus",),
            message="An accessory call must author at least one non-zero executable effect or be removed.",
        ), RequirementSpec(
            kind="positive_param_requires_param", param="lightColor",
            nonzero_params=("lightStrength",),
            message="Positive equipped light requires explicit lightColor; no hidden white fallback.",
        ))
    if cap.name == "configure_armor":
        return (RequirementSpec(
            kind="nonneutral_params_require_param",
            param="setKey",
            nonzero_params=tuple(name for name in cap.params if name.startswith("setBonus")),
            message="A three-piece armor set bonus needs an explicit non-empty setKey shared by head, body and legs.",
        ), RequirementSpec(
            kind="nonneutral_params_require_exact_param", param="slot", equals="head",
            nonzero_params=tuple(name for name in cap.params if name.startswith("setBonus")),
            message="Only the head piece executes an armor set bonus once a matching head, body and legs are equipped.",
        ), RequirementSpec(
            kind="positive_param_requires_param", param="lightColor",
            nonzero_params=("lightStrength",),
            message="Positive equipped light requires explicit lightColor; no hidden white fallback.",
        ))
    if cap.name == "require_use_condition":
        return (RequirementSpec("conditional_param", param="mode", any_of=("life_above:minLife", "mana_above:minMana"), message="threshold modes require their threshold parameter"),)
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
    elif name in {"damageClass"} and not semantic_type:
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
            "genericCrit": "percentage_points",
            "acceleration": "pixels_per_tick_squared", "strength": "effect_strength",
        }
        semantic_type = semantic_by_name.get(name, "unitless_scalar" if spec.kind in {"integer", "number"} else "bounded_text")
    return replace(spec, semantic_type=semantic_type, reference=reference)


def _enrich_capability(cap: CapabilitySpec) -> CapabilitySpec:
    if cap.category == "event" and "delayTicks" not in cap.params:
        cap = replace(cap, params=MappingProxyType({
            **cap.params,
            "delayTicks": _p("integer", "Delay this exact action after the chosen event; 0 executes immediately", required=False,
                             minimum=0, maximum=600, units="ticks", neutral=0,
                             execution_phase="bounded delayed action scheduler"),
        }))
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
    if cap.name in {"configure_item_contact_hitbox", "set_projectile_damage"}:
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
    return [cap.author_prompt_card() for cap in visible_capabilities()]


def runtime_authoring_prompt_field_guide() -> dict[str, Any]:
    """Project shared low-level field semantics without duplicating capability rules."""
    return {
        "stableIdPattern": r"^[a-z][a-z0-9_]{0,47}$",
        "paramNotation": (
            "Every listed param is required unless marked optional; optional params may be omitted. "
            "A missing optional zero-neutral param makes no authored nonzero effect. "
            "Suffix units: Ticks=ticks (60/s), Tiles=tiles (16 px), Px=pixels, Radians=radians. "
            "Projectile movement/velocity is per projectile update (1 + extraUpdates updates per world tick); "
            "authored durations and event intervals "
            "ending Ticks remain world ticks, except raw localNpcHitCooldownTicks (see card). "
            "Percent/percentage-point/chance cards use percent-scale values (15 means 15%, not 0.15): "
            "bonusPercent=15 adds +0.15 to a damage modifier; CritChancePercentagePoints=15 adds "
            "15 raw crit-chance points; manaCostReductionPercentagePoints=15 subtracts 0.15 from "
            "manaCost factor (floor 0.1 per application); damageReductionPercentagePoints=15 adds "
            "0.15 to endurance; ammoSaveChancePercent=15 is a 15% independent save chance per "
            "equipped piece (combined as 1-product(1-p)). Raw crit points need not equal final crit: "
            "Default receives no Generic modifiers, Summon crit is nonstandard, modded DamageClass "
            "may override inheritance. By contrast damageMultiplier=1 multiplies authored base by 1 "
            "(AoE/chain floor at 1), damageFraction=0.15 heals 15% of damageDone, and homingStrength=0.15 "
            "lerps velocity per update. Neutral examples (not inserted defaults): velocityRetention=1, "
            "acceleration=1, powerMultiplier=1, hitboxScale/drawScale/scale=1; spreadRadians=0 "
            "has no fan; pierce=-1 is infinite and tileId/wallId=-1 disables placement. "
            "Use each card's own bounds/units; no universal zero neutral."
        ),
        "stackCost": STACK_COST_RULE,
        "armorParamInheritance": "configure_armor params without meaning inherit exact meaning from configure_accessory params of the same name; all own bounds and units still apply.",
        "setBonusParamPrefix": "Matching armor set (head piece only; matching head, body and legs must actually be equipped): ",
        "exclusiveGroup": {
            "scope": "per exact target entity",
            "rule": "At most one call in the same non-empty exclusiveGroup may target one entity.",
            "groups": sorted({
                capability.exclusive_group
                for capability in visible_capabilities()
                if capability.exclusive_group
            }),
        },
        "bindingTarget": (
            "bindings[].usePolicy.action.targetId is the exact entity acted on. The selected action's targets list "
            "is the entity-kind allowlist; spawn_entity targets the entity created, while "
            "use_item_body targets the item body being used. Only place_item additionally requires "
            "bindings[].usePolicy.action.placementCallId; every other action must omit that key. "
            "usePolicy.contactDamage is an independent item-body hitbox lane for primary_use/alternate_use: "
            "spawn_entity with contactDamage=true executes both body contact and projectile spawn without a second binding. "
            "It does not select primaryEntityId or projectile held ownership; place_item/hold/equipped require false."
        ),
        "positionOwnership": {
            "none": "Does not author movement or position ownership.",
            "velocity_or_position_controller": "Owns velocity or position updates while active.",
            "owns_position_until_release": "Owns position until the authored release transition.",
            "owns_position_while_active": "Owns position for the capability's active lifetime.",
            "owns_stationary_position": "Keeps an explicitly stationary entity positioned.",
        },
        "meaningfulForStationary": (
            "Machine readability hint only. targets is the validity allowlist; true says the "
            "capability still has an effect when the target is stationary."
        ),
    }


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
        "capabilities": [cap.audit_card() for cap in visible_capabilities()],
    }


__all__ = [
    "runtime_authoring_registry_manifest",
    "runtime_authoring_prompt_field_guide",
    "event_alternative_is_present",
    "event_dependency_alternatives",
    "event_dependency_descriptors",
    "RequirementSpec",
    "ReferenceSpec",
    "InputKindSpec",
    "EventBindingRequirement",
    "EventCallRequirement",
    "EventDependencyAlternative",
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
