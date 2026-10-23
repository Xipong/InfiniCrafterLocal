from __future__ import annotations

from dataclasses import dataclass, field, replace
import json
import math
import struct
from types import MappingProxyType
from typing import Any, Final, Iterable, Mapping

from infini_local.core.repair_merge import json_values_equal

STACK_COST_RULE = (
    "The placement stack is spent only after accepted placement "
    "and the placed generated item is returned by the placement ledger when broken. "
    "For non-placement active use, stackCost=1 consumes one whole generated item (not ammo, projectile or a charge); "
    "stackCost=0 retains it, including reusable throws. Projectile return does not refund a consumed item. "
    "Choose cost to match the final object's intended lifetime and purposeful action, not automatically from a parent or from a temporary projectile's lifetime."
    " In a complete Author binding, optional stackConsumeChancePercent is an explicit integer 0..100 chance of spending that unit after "
    "the completed active use. It is valid only with stackCost=1 outside placement; omission retains "
    "the existing 100 percent debit. This never controls ammo saving or placement escrow."
)

from infini_local.core.runtime_authoring.terraria_vocabulary import (
    DAMAGE_CLASS_TOKEN_PATTERN,
    DAMAGE_CLASS_TOKENS,
    ITEM_USE_STYLE_TOKENS,
    VANILLA_AMMO_CATEGORY_TOKENS,
    VANILLA_PROJECTILE_TYPE_ID_MAX,
)


RUNTIME_PROGRAM_API_VERSION: Final[str] = "infini.runtime-program.v5"
RUNTIME_PROGRAM_SCHEMA: Final[str] = "infini.runtime-program.authoring.v6"
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
PROJECTILE_MODIFIER_COMPONENTS: Final[Mapping[str, str]] = MappingProxyType({
    "set_projectile_vector_acceleration": "vectorAcceleration",
    "set_projectile_speed_ramp": "speedRamp",
    "set_projectile_turn_modifier": "turnModifier",
    "set_projectile_speed_modifier": "speedModifier",
    "set_projectile_homing_modifier": "homingModifier",
    "attract_npcs_while_active": "npcAttraction",
    "set_projectile_visual_scale_curve": "visualScaleCurve",
})
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
    "on_hurt",
    "on_enemy_kill",
)
NETWORK_AUTHORITIES: Final[tuple[str, ...]] = (
    "owner_request_server_execute",
    "server_execute",
    "owner_execute_sync",
    "client_visual_only",
    "native_worldgen",  # Existing WorldGen lifecycle/owner; inventory witness only.
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
    other_param: str = ""
    allow_absent: bool = False
    when_spawned_by_inputs: tuple[str, ...] = ()

    def ordered_values(self, minimum: Any, maximum: Any) -> bool:
        """Compare typed numeric endpoints or an explicitly declared enum order."""
        if self.any_of:
            return (minimum not in self.any_of or maximum not in self.any_of
                    or self.any_of.index(minimum) <= self.any_of.index(maximum))
        return not (type(minimum) in (int, float) and type(maximum) in (int, float) and minimum > maximum)

    def card(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": self.kind, "target": self.target}
        if self.capability:
            out["capability"] = self.capability
        if self.param:
            out["param"] = self.param
            if self.kind != "item_capability_param" or not self.any_of:
                out["equals"] = dict(self.equals) if isinstance(self.equals, Mapping) else self.equals
        if self.any_of:
            out["anyOf"] = list(self.any_of)
        if self.nonzero_params:
            out["nonzeroParams"] = list(self.nonzero_params)
        if self.message:
            out["message"] = self.message
        if self.other_param:
            out["otherParam"] = self.other_param
        if self.allow_absent:
            out["allowAbsent"] = True
        if self.when_spawned_by_inputs:
            out["whenSpawnedByInputs"] = list(self.when_spawned_by_inputs)
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
class ParamProjection:
    """One exact Author leaf/variant to relative wire-field projection."""

    authored_path: str
    wire_path: str
    value: Any
    literal: bool = False


@dataclass(frozen=True, slots=True)
class OmissionCondition:
    """Exact consumer branches where a declared neutral field is inactive."""

    target_kinds: tuple[str, ...] = ()
    param_equals: tuple[tuple[str, Any], ...] = ()
    target_capabilities: tuple[str, ...] = ()

    def allows(self, params: Mapping[str, Any], kind: str, capabilities: Iterable[str]) -> bool:
        names = frozenset(capabilities)
        return (kind in self.target_kinds
                or any(key in params and type(params[key]) is type(value) and params[key] == value
                       for key, value in self.param_equals)
                or any(name in names for name in self.target_capabilities))

    def card(self) -> dict[str, Any]:
        return {"anyTargetKind": list(self.target_kinds), "anyExactParam": dict(self.param_equals),
                "anyTargetCapability": list(self.target_capabilities)}


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
    wire_multiplier: int | float = 1
    multiple_of: float | int | None = None
    wire_boolean_true_value: int | None = None
    runtime_minimum: float | int | None = None
    runtime_maximum: float | int | None = None
    neutral: Any = None
    execution_phase: str = ""
    consumer_storage: str = ""
    properties: Mapping[str, ParamSpec] = field(default_factory=lambda: MappingProxyType({}), compare=False)
    alternatives: tuple[ParamSpec, ...] = ()
    wire_literals: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}), compare=False)
    wire_enum: Mapping[Any, Any] = field(default_factory=lambda: MappingProxyType({}), compare=False)
    wire_offset: int = 0
    min_properties: int | None = None
    omission_condition: OmissionCondition | None = None
    wire_presence_requires_receipt: bool = False
    # Explicit numeric wire contract. Predecessors are receipt paths only, never Author aliases.
    predecessor_names: tuple[str, ...] = ()
    wire_kind: str = ""
    wire_minimum: float | int | None = None
    wire_maximum: float | int | None = None
    wire_updates_power: int = 0
    wire_rounding: str = ""
    predecessor_omission_wire_value: Any = None

    def wire_projection_card(self) -> dict[str, Any]:
        """Canonical introspection for source-wire readers and test-only fixture inverses.

        Wire = Author * multiplier / (divisor * updatesPerTick**power), followed
        only by the declared rounding. Context always belongs to the projectile
        receiving this parameter (a child uses its own collision call).
        """
        return {"wireName": self.wire_name, "wireKind": self.projected_kind,
                "multiplier": self.wire_multiplier, "divisor": self.wire_divisor, "offset": self.wire_offset,
                "updatesPerTickPower": self.wire_updates_power,
                "context": "same_target.set_projectile_collision.updatesPerTick" if self.wire_updates_power else None,
                "rounding": self.wire_rounding or "exact",
                "wireMinimum": self.wire_minimum, "wireMaximum": self.wire_maximum,
                "predecessorNames": list(self.predecessor_names), "authorUnits": self.units,
                "blockPixels": 16, "worldTicksPerSecond": 60,
                "rejectNonzeroToZero": bool(self.wire_kind),
                **({"authorBoundsByUpdatesPerTick": {str(n): self.contextual_author_bounds(updates_per_tick=n)
                                                     for n in range(1, 7)}} if self.wire_updates_power else {})}

    def author_projection_card(self) -> dict[str, Any]:
        """Only human-unit constraints; historical paths/engine math stay introspection-only."""
        out: dict[str, Any] = {"nonzeroMustRemainNonzero": True}
        if self.wire_rounding:
            out["secondsRounding"] = "nearest world tick (60/s); half-tick ties UP"
        if self.wire_updates_power:
            out["targetContext"] = "same target's unique set_projectile_collision.updatesPerTick"
            out["boundsAtUpdatesPerTick1To6"] = [
                list(self.contextual_author_bounds(updates_per_tick=n).values()) for n in range(1, 7)]
        return out

    def contextual_author_bounds(self, *, updates_per_tick: int | None = None) -> dict[str, Any]:
        """Human bounds for one validated target clock; static schema covers their union."""
        if not self.wire_kind or not self.wire_updates_power:
            return {"minimum": self.minimum, "maximum": self.maximum}
        return {"minimum": self.from_wire(self.wire_minimum, updates_per_tick=updates_per_tick)
                    if self.wire_minimum is not None else None,
                "maximum": self.from_wire(self.wire_maximum, updates_per_tick=updates_per_tick)
                    if self.wire_maximum is not None else None}

    @property
    def projected_kind(self) -> str:
        return self.wire_kind or ("integer" if self.kind == "integer" or self.wire_multiplier != 1 or self.wire_boolean_true_value is not None else self.kind)

    @property
    def requires_update_context(self) -> bool:
        return bool(self.wire_updates_power or any(spec.requires_update_context for spec in self.properties.values())
                    or any(spec.requires_update_context for spec in self.alternatives))

    def _update_factor(self, updates_per_tick: int | None) -> int:
        if not self.wire_updates_power:
            return 1
        if type(updates_per_tick) is not int or not 1 <= updates_per_tick <= 6:
            raise ValueError("projection requires the same target's unique validated updatesPerTick (1..6)")
        return updates_per_tick ** self.wire_updates_power

    def from_wire(self, value: Any, *, updates_per_tick: int | None = None) -> Any:
        """Unit inverse for reading wire/QA fixtures, NOT an Author admission adapter."""
        if self.wire_enum:
            matches = [key for key, wire in self.wire_enum.items() if type(wire) is type(value) and wire == value]
            if len(matches) != 1:
                raise ValueError("wire enum has no unique inverse")
            return matches[0]
        if self.wire_boolean_true_value is not None:
            if type(value) is not int or value not in (0, self.wire_boolean_true_value):
                raise ValueError("invalid boolean wire projection")
            return bool(value)
        if self.wire_offset:
            return value - self.wire_offset
        factor = self._update_factor(updates_per_tick)
        result = value * self.wire_divisor * factor / self.wire_multiplier
        if self.wire_kind and not self.wire_rounding:
            # The inverse's binary64 rounding can place an exact wire endpoint
            # just outside its own domain on re-projection. Expose the adjacent
            # representable Author endpoint inside that domain. Author admission
            # and forward projection stay strict and never alter input values.
            projected = self.to_wire(result, updates_per_tick=updates_per_tick)
            if value == self.wire_minimum and projected < value:
                result = math.nextafter(result, math.inf)
            elif value == self.wire_maximum and projected > value:
                result = math.nextafter(result, -math.inf)
        return int(result) if self.kind == "integer" and float(result).is_integer() else result

    def canonical_receipt_leaf_path(self, suffix: str) -> str | None:
        """Finite predecessor path admission for source-free receipts ONLY."""
        if not suffix:
            return ""
        if self.alternatives:
            matches = {path for variant in self.alternatives
                       if (path := variant.canonical_receipt_leaf_path(suffix)) is not None}
            return next(iter(matches)) if len(matches) == 1 else None
        head, separator, tail = suffix.partition(".")
        matches = [(name, spec) for name, spec in self.properties.items()
                   if head == name or head in spec.predecessor_names]
        if len(matches) != 1:
            return None
        name, spec = matches[0]
        rest = spec.canonical_receipt_leaf_path(tail) if separator else ""
        return name + ("." + rest if rest else "") if rest is not None else None

    def wire_schema(self) -> dict[str, Any]:
        """Engine-domain scalar schema; never reuse changed Author units for wire."""
        if not self.wire_kind:
            if self.structured:
                raise ValueError("structured parameters have variant wire projections, not a scalar wire schema")
            out = self.schema()
            if self.wire_enum:
                out["enum"] = list(self.wire_enum.values())
            elif self.wire_boolean_true_value is not None:
                out = {"type": "integer", "enum": [0, self.wire_boolean_true_value]}
            elif self.wire_multiplier != 1 or self.wire_divisor != 1 or self.wire_offset:
                out = {"type": self.projected_kind}
                if self.minimum is not None:
                    out["minimum"] = self.to_wire(self.minimum)
                if self.maximum is not None:
                    out["maximum"] = self.to_wire(self.maximum)
            return out
        out: dict[str, Any] = {"type": self.wire_kind}
        for key, bound in (("minimum", self.wire_minimum), ("maximum", self.wire_maximum)):
            if bound is None:
                continue
            # A native Single endpoint can lie just outside the original
            # binary64 literal. Admit that exact storage image as well, not an
            # epsilon or the next outside Single. Fresh Author bounds stay exact.
            if self.wire_kind == "number" and self.consumer_storage == "float32":
                stored = struct.unpack("!f", struct.pack("!f", bound))[0]
                bound = min(bound, stored) if key == "minimum" else max(bound, stored)
            out[key] = bound
        return out

    @property
    def structured(self) -> bool:
        return bool(self.properties or self.alternatives or self.wire_literals)

    def selected_variant(self, value: Any) -> ParamSpec:
        """Resolve exactly one declared variant; never guess an absent discriminator."""
        if not self.alternatives:
            return self
        # Lazy import keeps schema shape at its canonical owner without a
        # parallel shape matcher or a module initialization dependency cycle.
        from infini_local.core.schema_validation import strict_schema_errors
        matches = [variant for variant in self.alternatives
                   if not strict_schema_errors(value, variant.schema())]
        if len(matches) != 1:
            raise ValueError("parameter requires exactly one explicit registered variant")
        return matches[0]

    def leaf_values(self, value: Any, name: str) -> tuple[tuple[str, ParamSpec, Any], ...]:
        """Read present typed leaves for validation; absence is not materialized."""
        try:
            selected = self.selected_variant(value)
        except ValueError:
            return ()  # strict shape owns invalid/ambiguous variant diagnostics
        if selected is not self:
            return selected.leaf_values(value, name)
        if self.kind == "object":
            if not isinstance(value, Mapping):
                return ()
            return tuple(leaf for key, spec in self.properties.items() if key in value
                         for leaf in spec.leaf_values(value[key], f"{name}.{key}"))
        return ((name, self, value),)

    def projected_fields(self, value: Any, name: str, *, updates_per_tick: int | None = None) -> tuple[ParamProjection, ...]:
        """Project a validated value, retaining its exact nested source paths.

        Objects group Author decisions only. Wire names are relative to the
        capability's existing component; they may name a nested DTO field.
        Literal fields belong to an explicitly selected variant, not a default.
        """
        from infini_local.core.schema_validation import strict_schema_errors
        selected = self.selected_variant(value)
        if strict_schema_errors(value, self.schema()):
            raise ValueError("parameter does not satisfy its declared schema")
        if any(spec.consumer_value_error(leaf, updates_per_tick=updates_per_tick) is not None
               for _, spec, leaf in self.leaf_values(value, name)):
            raise ValueError("parameter does not satisfy its declared consumer domain")
        if selected is not self:
            return selected.projected_fields(value, name, updates_per_tick=updates_per_tick)
        rows = [ParamProjection(name, key, item, True) for key, item in self.wire_literals.items()]
        if self.kind == "object":
            if not isinstance(value, Mapping):
                raise ValueError("object parameter has no object value")
            for key, spec in self.properties.items():
                if key in value:
                    rows.extend(spec.projected_fields(value[key], f"{name}.{key}", updates_per_tick=updates_per_tick))
        elif not self.wire_literals or self.wire_name:
            rows.append(ParamProjection(name, self.wire_name or name.rsplit(".", 1)[-1], self.to_wire(value, updates_per_tick=updates_per_tick)))
        destinations = [row.wire_path for row in rows]
        if len(destinations) != len(set(destinations)):
            raise ValueError("parameter projects multiple decisions into one wire field")
        return tuple(rows)

    def wire_field_names(self, name: str) -> tuple[str, ...]:
        """Finite output inventory for every admitted variant, without values."""
        if self.alternatives:
            return tuple(dict.fromkeys(field_name for variant in self.alternatives
                                       for field_name in variant.wire_field_names(name)))
        outputs = list(self.wire_literals)
        if self.kind == "object":
            outputs.extend(field_name for key, spec in self.properties.items()
                           for field_name in spec.wire_field_names(key))
        elif not self.wire_literals or self.wire_name:
            outputs.append(self.wire_name or name.rsplit(".", 1)[-1])
        return tuple(dict.fromkeys(outputs))

    def projection_paths(self, name: str) -> tuple[tuple[str, str, bool], ...]:
        """Exact finite source/output pairs for source-free receipt inspection."""
        if self.alternatives:
            return tuple(dict.fromkeys(row for variant in self.alternatives
                                       for row in variant.projection_paths(name)))
        rows = [(name, key, True) for key in self.wire_literals]
        if self.kind == "object":
            rows.extend(row for key, spec in self.properties.items()
                        for row in spec.projection_paths(f"{name}.{key}"))
        elif not self.wire_literals or self.wire_name:
            rows.append((name, self.wire_name or name.rsplit(".", 1)[-1], False))
        return tuple(rows)

    def matches_scalar_projection(self, value: Any) -> bool:
        """Admitted wire domain only; never reconstruct or authenticate an Author."""
        from infini_local.core.schema_validation import strict_schema_errors
        if self.structured:
            return False
        if self.wire_kind:
            return (not strict_schema_errors(value, self.wire_schema())
                    and self.consumer_value_error(value, wire_value=True) is None)
        if self.wire_enum:
            return any(type(value) is type(v) and json.dumps(value) == json.dumps(v)
                       for v in self.wire_enum.values())
        if self.wire_boolean_true_value is not None:
            return type(value) is int and value in (0, self.wire_boolean_true_value)
        try:
            if self.wire_offset:
                if type(value) is not int:
                    return False
                authored = value - self.wire_offset
            elif self.wire_multiplier != 1:
                if type(value) is not int:
                    return False
                authored = value / self.wire_multiplier
            elif self.wire_divisor != 1:
                if self.kind == "number":
                    # Binary64 division is not injective: retain its admitted
                    # projected envelope, not a fabricated inverse Author float.
                    # Number division emits floats; the wire must also satisfy
                    # the same consumer storage constraint, without redivision.
                    return (type(value) is float and math.isfinite(value)
                            and (self.minimum is None or value >= self.to_wire(self.minimum))
                            and (self.maximum is None or value <= self.to_wire(self.maximum))
                            and self.consumer_value_error(value, wire_value=True) is None)
                authored = value * self.wire_divisor
            else:
                authored = value
            return (not strict_schema_errors(authored, self.schema())
                    and self.consumer_value_error(authored) is None
                    and type(self.to_wire(authored)) is type(value)
                    and json.dumps(self.to_wire(authored)) == json.dumps(value))
        except (ValueError, TypeError, OverflowError):
            return False

    def matches_projection_records(self, records: tuple[tuple[str, str, bool, Any], ...], name: str) -> bool:
        """Require one complete declared variant with unique typed output leaves.

        Records describe claimed source paths, not available source values.
        Recursion avoids enumerating optional-object Cartesian products.
        """
        if self.alternatives:
            return sum(variant.matches_projection_records(records, name)
                       for variant in self.alternatives) == 1
        remaining = list(records)
        for destination, value in self.wire_literals.items():
            matches = [r for r in remaining if r[:3] == (name, destination, True)
                       and type(r[3]) is type(value) and json.dumps(r[3]) == json.dumps(value)]
            if len(matches) != 1:
                return False
            remaining.remove(matches[0])
        if self.kind == "object":
            count = 0
            for key, spec in self.properties.items():
                prefix = f"{name}.{key}"
                group = tuple(r for r in remaining if r[0] == prefix or r[0].startswith(prefix + "."))
                if not group:
                    if spec.required:
                        return False
                    continue
                if not spec.matches_projection_records(group, prefix):
                    return False
                count += 1
                remaining = [r for r in remaining if r not in group]
            return not remaining and (self.min_properties is None or count >= self.min_properties)
        if not self.wire_literals or self.wire_name:
            return (len(remaining) == 1
                    and remaining[0][:3] == (name, self.wire_name or name.rsplit(".", 1)[-1], False)
                    and self.matches_scalar_projection(remaining[0][3]))
        return not remaining

    def consumer_constraint(self) -> dict[str, Any]:
        if self.wire_kind and self.consumer_storage == "float32":
            return {"storage": "float32", "neutral": self.neutral,
                    "rule": "nonneutral_must_remain_nonneutral",
                    "meaning": "Deterministic lowering and finite float32 storage must preserve non-neutral values as non-neutral; exact neutral is allowed. Validation never rewrites Author values."}
        if self.consumer_storage == "float64":
            return {"storage": "float64", "rule": "finite_double_no_normalization",
                    "meaning": "C# double preserves the admitted JSON number; only GPU API coordinates convert to float. No float32 guard, rounding or replacement."}
        constraint = {"storage": self.consumer_storage, "neutral": self.neutral,
                      "rule": "nonneutral_must_remain_nonneutral",
                      "meaning": "Finite float32 storage must preserve a non-neutral value as non-neutral; exact neutral is allowed. No rounding or replacement is performed by validation."}
        if self.wire_divisor != 1 or self.wire_multiplier != 1:
            constraint["wireProjection"] = {"divisor": self.wire_divisor, "multiplier": self.wire_multiplier}
            constraint["meaning"] = (
                "Apply wireProjection in binary64, then finite float32 storage. Non-neutral values must stay "
                "non-neutral at both steps; exact neutral is allowed. No rounding or replacement by validation. "
                "Guards neutral collapse, not exact float round-trip or later gameplay arithmetic."
            )
        return constraint

    def consumer_value_error(self, value: Any, *, wire_value: bool = False, updates_per_tick: int | None = None) -> str | None:
        """Check declared consumer storage without modifying Author or wire."""
        if self.wire_kind:
            try:
                projected = value if wire_value else self.to_wire(value, updates_per_tick=updates_per_tick)
                if type(projected) not in (int, float) or not math.isfinite(projected):
                    return "wire projection must remain finite"
                if not wire_value and value != 0 and projected == 0:
                    return "nonzero value collapses to zero in declared wire projection"
                bounds = self.wire_schema() if wire_value else {"minimum": self.wire_minimum, "maximum": self.wire_maximum}
                lower, upper = bounds.get("minimum"), bounds.get("maximum")
                if lower is not None and projected < lower:
                    return f"projected engine value must be >= {lower}"
                if upper is not None and projected > upper:
                    return f"projected engine value must be <= {upper}"
            except (ValueError, TypeError, OverflowError) as exc:
                return str(exc)
        if not self.consumer_storage:
            return None
        if self.consumer_storage == "float64":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return "expected a finite number for float64 consumer storage"
            # Bounded JSON ints need no float conversion; retain indexed shape
            # range diagnostics even for oversized malformed JSON integers.
            if isinstance(value, float) and not math.isfinite(value):
                return "value is not finite in float64 consumer storage"
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return "expected a finite number for float32 consumer storage"
        try:
            # Storage consumes the declared wire projection, not the Author unit.
            # Check both boundaries: /100 may already underflow in binary64.
            projected = value if wire_value else self.to_wire(value, updates_per_tick=updates_per_tick)
            neutral = (0 if self.wire_kind and self.neutral in (None, 0)
                       else self.to_wire(self.neutral, updates_per_tick=updates_per_tick))
            source_neutral = neutral if wire_value else (0 if self.wire_kind and self.neutral is None else self.neutral)
            if value != source_neutral and projected == neutral:
                return f"non-neutral value collapses to neutral {neutral} in declared wire projection"
            stored = struct.unpack("!f", struct.pack("!f", projected))[0]
        except (OverflowError, struct.error):
            return "value is not finite in float32 consumer storage"
        if not math.isfinite(stored):
            return "value is not finite in float32 consumer storage"
        if value != source_neutral and stored == neutral:
            return f"non-neutral value collapses to neutral {neutral} in float32 consumer storage after declared wire projection"
        return None

    def to_wire(self, value: Any, *, updates_per_tick: int | None = None) -> Any:
        # Declared unit conversion, not a choice of mechanic or a numeric clamp.
        if self.wire_enum:
            if value not in self.wire_enum:
                raise ValueError("undeclared wire enum value")
            return self.wire_enum[value]
        if self.wire_offset:
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError("integer offset requires an integer Author value")
            return value + self.wire_offset
        if self.wire_boolean_true_value is not None:
            return self.wire_boolean_true_value if value else 0
        if self.wire_kind:
            factor = self._update_factor(updates_per_tick)
            # One declared binary64 scale application; do not introduce an
            # intermediate velocity/acceleration rounding before target scaling.
            result = value * (self.wire_multiplier / (self.wire_divisor * factor))
            if self.wire_rounding == "nearest_world_tick_half_up":
                if result < 0 or not math.isfinite(result):
                    raise ValueError("seconds must project to nonnegative finite world ticks")
                return math.floor(result + 0.5)
            if self.wire_kind == "integer":
                if not math.isfinite(result) or not result.is_integer():
                    raise ValueError("non-integral wire projection")
                return int(result)
            return result
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
        out: dict[str, Any] = ({"oneOf": [variant.schema() for variant in self.alternatives]}
                               if self.alternatives else {"type": self.kind})
        if self.kind == "object":
            out.update({"properties": {name: spec.schema() for name, spec in self.properties.items()},
                        "required": [name for name, spec in self.properties.items() if spec.required],
                        "additionalProperties": False})
            if self.min_properties is not None:
                out["minProperties"] = self.min_properties
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
        if self.consumer_storage:
            out["x-infini-consumerConstraint"] = self.consumer_constraint()
        if self.wire_kind:
            out["x-infini-authorProjection"] = self.author_projection_card()
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
    allowed_events: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    technical_lowering_outputs: tuple[str, ...] = ()
    technical_lowering_inputs: tuple[str, ...] = ()
    component_slot: str = ""
    exclusive_group: str = ""
    position_ownership: str = "none"
    emitted_events: tuple[str, ...] = ()
    requirements: tuple[RequirementSpec, ...] = ()
    authority_by_effect: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}), compare=False)
    activation_spawn_count_param: str = ""
    meaningful_for_stationary: bool = False
    effect_groupable: bool = False
    wire_action: str = ""
    fixed_wire_literals: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}), compare=False)
    wire_presence_path: str = ""  # Optional whole component selected only by this capability.

    def canonical_receipt_param_path(self, path: str) -> str | None:
        """Resolve a finite declared historical source path, never fresh Author input."""
        head, separator, tail = path.partition(".")
        matches = [(name, spec) for name, spec in self.params.items()
                   if head == name or head in spec.predecessor_names]
        if len(matches) != 1:
            return None
        name, spec = matches[0]
        rest = spec.canonical_receipt_leaf_path(tail) if separator else ""
        return name + ("." + rest if rest else "") if rest is not None else None

    def flat_wire_params_schema(self) -> dict[str, Any]:
        """Strict flat engine component schema derived only from declared projections."""
        return {"type": "object", "additionalProperties": False,
                "properties": {spec.wire_name or name: spec.wire_schema() for name, spec in self.params.items()},
                "required": [spec.wire_name or name for name, spec in self.params.items() if spec.required]}

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
        # One call envelope for the model. Existing exact omissions remain
        # valid; a redundant *correct* owner or empty params is not an error.
        # Present fields still receive the same type/reference/key validation.
        if self.target_kinds == ("item_body",):
            variant["required"].remove("target")
        if not self.params:
            variant["required"].remove("params")
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
            if spec.consumer_storage:
                row["consumerConstraint"] = spec.consumer_constraint()
            if spec.structured:
                row["shape"] = spec.schema()
            if spec.wire_kind:
                row["projectionConstraints"] = spec.author_projection_card()
            if spec.omission_condition is not None:
                row["omissionAllowedOnlyWhen"] = spec.omission_condition.card()
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
        if self.effect_groupable:
            card["effectGroups"] = "Optional params.effectGroupId partitions this component's multiplicity and exclusive group ownership; an apply_item_effects binding, held refresh or generated-buff equipment reaction selects the same exact ID. Omit both selectors for the existing default group. Mobility cooldown remains shared per player."
        if self.performance_budget != "bounded by runtime program limits":
            card["budget"] = self.performance_budget
        return card

    def has_non_neutral_effect(self, params: Mapping[str, Any]) -> bool:
        """Registry-owned effect predicate; shape/range acceptance stays separate.

        An operation without declared neutral effect params is unconditional
        once valid (for example a concrete vanilla buff or mobility action).
        No value is coerced or materialized by this predicate.
        """
        def nested_effect(spec: ParamSpec, value: Any) -> bool:
            if spec.kind == "object" and isinstance(value, Mapping):
                return any(nested_effect(child, value.get(key)) for key, child in spec.properties.items())
            return (spec.neutral is not None and type(value) in (int, float, bool)
                    and (type(value) is not float or math.isfinite(value)) and value != spec.neutral)
        if any(nested_effect(spec, params.get(name)) for name, spec in self.params.items() if spec.kind == "object"):
            return True
        effect_params = {name: spec for name, spec in self.params.items() if spec.neutral is not None}
        if not effect_params:
            return True
        for name, spec in effect_params.items():
            value = params.get(name)
            if spec.kind == "boolean":
                if isinstance(value, bool) and value is not spec.neutral:
                    return True
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                if isinstance(value, float) and not math.isfinite(value):
                    continue
                if value != spec.neutral:
                    return True
        return False

    def author_prompt_card(self) -> dict[str, Any]:
        """Compact only repeated presentation metadata, never the authored contract.

        The complete prompt_card remains the machine/audit projection. Gemini's
        json_object transport does not send the local provider schema, so bounds,
        types, enums, patterns, references and dependencies stay in this card.
        """
        card = self.prompt_card()
        # Seconds, nearest-tick rounding and subupdate conversion are already
        # stated once in fieldGuide.paramNotation. Retain each consumer's own
        # meaning and all units/bounds/projection metadata, including nested shapes.
        seconds_primer = "World duration (seconds); shared nearest-tick rounding applies. Native consumer: "
        def compact_meanings(value: Any) -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    if key in {"meaning", "description"} and isinstance(child, str):
                        value[key] = child.removeprefix(seconds_primer)
                    else:
                        compact_meanings(child)
            elif isinstance(value, list):
                for child in value:
                    compact_meanings(child)
        compact_meanings(card)
        for name, row in card["params"].items():
            # Structured params already carry the identical root description as
            # their meaning. Nested branch/leaf descriptions remain complete.
            shape = row.get("shape")
            if isinstance(shape, dict) and shape.get("description") == row.get("meaning"):
                shape.pop("description", None)
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
            for suffix, units in (("Seconds", "seconds"), ("Tiles", "blocks (tiles)"),
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
            "effectGroupable": self.effect_groupable,
            "budget": self.performance_budget,
            "activationSpawnCountParam": self.activation_spawn_count_param or None,
            "meaningfulForStationary": self.meaningful_for_stationary,
            **({"wirePresencePath": self.wire_presence_path} if self.wire_presence_path else {}),
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
    consumer_storage: str = "",
    properties: Mapping[str, ParamSpec] | None = None,
    alternatives: Iterable[ParamSpec] = (),
    wire_literals: Mapping[str, Any] | None = None,
    wire_enum: Mapping[Any, Any] | None = None,
    wire_offset: int = 0,
    min_properties: int | None = None,
    omission_condition: OmissionCondition | None = None,
    wire_presence_requires_receipt: bool = False,
) -> ParamSpec:
    return ParamSpec(
        kind=kind,
        description=description,
        required=required,
        minimum=minimum,
        maximum=maximum,
        enum=tuple(enum),
        pattern=pattern,
        units="blocks (tiles)" if units == "tiles" else units,
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
        consumer_storage=consumer_storage,
        properties=MappingProxyType(dict(properties or {})),
        alternatives=tuple(alternatives),
        wire_literals=MappingProxyType(dict(wire_literals or {})),
        wire_enum=MappingProxyType(dict(wire_enum or {})),
        wire_offset=wire_offset,
        min_properties=min_properties,
        omission_condition=omission_condition,
        wire_presence_requires_receipt=wire_presence_requires_receipt,
    )


def target_updates_per_tick(calls: Iterable[object], target: str) -> int:
    """Resolve only the same projectile's unique explicit collision declaration."""
    matches = [call for call in calls if isinstance(call, Mapping)
               and call.get("fn") == "set_projectile_collision" and call.get("target") == target]
    if len(matches) != 1:
        raise ValueError("projection requires the same target's unique set_projectile_collision updatesPerTick")
    params = matches[0].get("params")
    value = params.get("updatesPerTick") if isinstance(params, Mapping) else None
    if type(value) is not int or not 1 <= value <= 6:
        raise ValueError("projection requires validated updatesPerTick (1..6)")
    return value


def _world_units(spec: ParamSpec, predecessor: str, *, multiplier: int | float, divisor: int = 1,
                 updates_power: int = 0, units: str, seconds: bool = False) -> ParamSpec:
    """Declare changed Author units while freezing the pre-existing engine domain.

    The provider range covers every N=1..6. Validation additionally checks the
    projected engine range at the actual target's N; it never clamps or guesses N.
    """
    low = spec.to_wire(spec.minimum) if spec.minimum is not None else None
    high = spec.to_wire(spec.maximum) if spec.maximum is not None else None
    def inverse(value: Any) -> Any:
        return value * divisor / multiplier if value is not None else None
    author_low, author_high = inverse(low), inverse(high)
    if updates_power:
        if author_low is not None and author_low < 0:
            author_low *= 6 ** updates_power
        if author_high is not None and author_high > 0:
            author_high *= 6 ** updates_power
    if seconds:
        author_low = max(0, (low - 0.5) / 60) if low is not None else None
    geometry_lattice = spec.projected_kind == "integer" and not seconds
    # Clock quantization, target-context bounds and nonzero/storage rules are
    # shared in the field guide and author_projection_card. Do not repeat that
    # identical engine primer for every leaf, or clip literal source facts to
    # make room for it. Keep each consumer's distinct execution meaning here.
    meaning = ("World duration (seconds); shared nearest-tick rounding applies. Native consumer: "
               if seconds else f"Author units: {units}. Native consumer: ")
    converted = replace(spec, kind="number", description=meaning + spec.description,
                   minimum=author_low, maximum=author_high, units=units, semantic_type=units,
                   default=inverse(spec.default), neutral=inverse(spec.neutral),
                   # Converted floating scalars are stored by native float32
                   # fields; preserve an explicitly declared double consumer.
                   consumer_storage=spec.consumer_storage or ("float32" if spec.projected_kind == "number" else ""),
                   predecessor_omission_wire_value=(spec.to_wire(spec.default)
                       if not spec.required and spec.default is not None
                       and type(spec.default) is type(spec.neutral) and spec.default == spec.neutral else None),
                   wire_name=spec.wire_name or predecessor,
                   wire_multiplier=multiplier, wire_divisor=divisor,
                   wire_updates_power=updates_power,
                   wire_kind=spec.projected_kind, wire_minimum=low, wire_maximum=high,
                   wire_rounding="nearest_world_tick_half_up" if seconds else "",
                   multiple_of=1 / multiplier if geometry_lattice else None,
                   predecessor_names=(predecessor,))
    if not seconds:
        # Publish the same representable endpoints as the target-clock inverse;
        # the static schema is the union of the admitted N=1..6 domains.
        low_clock = 6 if updates_power and low is not None and low < 0 else 1
        high_clock = 6 if updates_power and high is not None and high > 0 else 1
        if low is not None and converted.to_wire(author_low, updates_per_tick=low_clock) < low:
            author_low = converted.from_wire(low, updates_per_tick=low_clock)
        if high is not None and converted.to_wire(author_high, updates_per_tick=high_clock) > high:
            author_high = converted.from_wire(high, updates_per_tick=high_clock)
        converted = replace(converted, minimum=author_low, maximum=author_high)
    return converted


def _seconds(spec: ParamSpec, predecessor: str) -> ParamSpec:
    return _world_units(spec, predecessor, multiplier=60, units="seconds", seconds=True)


def _cap(
    name: str,
    summary: str,
    category: str,
    targets: Iterable[str],
    params: Mapping[str, ParamSpec],
    *,
    multiplicity: str = "single_per_target",
    authority: str = "owner_request_server_execute",
    budget: str = "bounded by runtime program limits",
    py: str,
    cs: str,
    wire: Iterable[str] = (),
    events: Iterable[str] = (),
    lowering: Iterable[str] = (),
    lowering_inputs: Iterable[str] = (),
    component_slot: str,
    exclusive_group: str = "",
    position_ownership: str = "none",
    emitted_events: Iterable[str] = (),
    requirements: Iterable[RequirementSpec] = (),
    authority_by_effect: Mapping[str, str] | None = None,
    activation_spawn_count_param: str = "",
    meaningful_for_stationary: bool = False,
    effect_groupable: bool = False,
    wire_action: str = "",
    fixed_wire_literals: Mapping[str, Any] | None = None,
    wire_presence_path: str = "",
) -> CapabilitySpec:
    """Declare capability facts once; finalization only projects shared metadata.

    An explicit wire tuple contains exact paths. Leave it empty for an existing
    parameter-derived component projection; never maintain a wildcard shadow.
    Requirements declared here precede any shared, parameter-derived rules.
    Dependencies and conflict labels are derived, not separate inputs.
    """
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
        allowed_events=tuple(events),
        technical_lowering_outputs=tuple(lowering),
        technical_lowering_inputs=tuple(lowering_inputs),
        component_slot=component_slot,
        exclusive_group=exclusive_group,
        position_ownership=position_ownership,
        emitted_events=tuple(emitted_events),
        requirements=tuple(requirements),
        authority_by_effect=MappingProxyType(dict(authority_by_effect or {})),
        activation_spawn_count_param=activation_spawn_count_param,
        meaningful_for_stationary=meaningful_for_stationary,
        effect_groupable=effect_groupable,
        wire_action=wire_action,
        fixed_wire_literals=MappingProxyType(dict(fixed_wire_literals or {})),
        wire_presence_path=wire_presence_path,
    )


_DAMAGE_CLASS = DAMAGE_CLASS_TOKENS
_DAMAGE_CLASS_PATTERN = DAMAGE_CLASS_TOKEN_PATTERN
# Exact C# equipment GetDamage overloads, not all item/projectile DamageClass IDs.
EQUIPMENT_DAMAGE_CLASSES: Final[tuple[str, ...]] = ("generic", "melee", "ranged", "magic", "summon")
# Native equipment DTO safety bounds are independent of Author parameter bounds.
# GeneratedEquipmentBounds projects these bounds alongside typed parameter limits.
EQUIPMENT_CLASS_DAMAGE_RUNTIME_BOUNDS: Final[Mapping[str, Mapping[str, tuple[float, float]]]] = MappingProxyType({
    "accessory": MappingProxyType({"genericDamage": (-0.9, 3.0)}),
    "armor": MappingProxyType({"genericDamage": (-0.9, 3.0), "setBonusGenericDamage": (-0.9, 3.0)}),
})


def equipment_damage_wire_path(phase: str, damage_class: str, *, armor: bool) -> str:
    """One-to-one selector over the supported native equipment DTO fields."""
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
_NATIVE_ARM_STRETCH: Final[tuple[str, ...]] = ("none", "quarter", "three_quarters", "full")
_MOVEMENT_OWNER = "Content/Projectiles/GeneratedProjectile.Executors.cs::RunMovement/RunController"
_COMPILER_OWNER = "infini_local.core.runtime_authoring.compiler::compile_runtime_program"


def _equipment_params(*, armor: bool) -> Mapping[str, ParamSpec]:
    """One Author vocabulary for equipped effects and their exact DTO projection."""
    phase = "ModItem.UpdateEquip" if armor else "ModItem.UpdateAccessory"

    # These fields have native DTO clamps in addition to strict Author bounds.
    # Other fields still require their declared Author bounds at admission.
    runtime_safety = ({
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
             percent: bool = False, integer: bool = False, wire_multiplier: int = 1,
             multiple_of: float | None = None) -> ParamSpec:
        safety = runtime_safety.get(wire)
        return _p("integer" if integer else "number", meaning, required=False,
                  minimum=low, maximum=high, units=units, semantic_type=units,
                  wire_name=wire, wire_divisor=100 if percent else 1,
                  wire_multiplier=wire_multiplier, multiple_of=multiple_of,
                  runtime_minimum=safety[0] if safety else None,
                  runtime_maximum=safety[1] if safety else None,
                  neutral=0, execution_phase=phase,
                  consumer_storage="float32" if percent else "")

    p: dict[str, ParamSpec] = {
        "defensePoints": stat("defense", "Add to Item.defense; Terraria applies it, not an extra equip-hook adjustment", 0 if armor else -50, 200, "defense_points", integer=True),
        "maxLifePoints": stat("maxLife", "Add maximum life", -200, 1000, "life_points", integer=True),
        "maxManaPoints": stat("maxMana", "Add maximum mana", -200, 1000, "mana_points", integer=True),
        "lifeRegenHpPerSecond": stat("lifeRegen", "Add signed HP/s regeneration contribution before other Terraria effects; +1 HP/s writes +2 Player.lifeRegen engine units, -1 HP/s writes -2; 0 adds nothing", -50, 100, "HP/s", wire_multiplier=2, multiple_of=0.5),
        "manaRegenBonusPoints": stat("manaRegen", "Add raw Player.manaRegenBonus points; 0 adds nothing, not mana/s", -100, 200, "engine units: manaRegenBonus points", integer=True),
        "moveSpeedBonusPercent": stat("movementSpeed", "Add percent/100 to Player.moveSpeed", -90, 300, "additive_percent", percent=True),
        "maxRunSpeedBonusBlocksPerSecond": _world_units(stat("maxRunSpeed", "Add to Player.maxRunSpeed, subject to other Terraria movement limits", -5, 20, "pixels_per_tick"), "maxRunSpeedBonusPxPerTick", multiplier=16, divisor=60, updates_power=0, units='blocks/s'),
        "jumpSpeedBonusBlocksPerSecond": _world_units(stat("jumpSpeed", "Add to Player.jumpSpeedBoost (positive raises jump speed)", -5, 20, "pixels_per_tick"), "jumpSpeedBonusPxPerTick", multiplier=16, divisor=60, updates_power=0, units='blocks/s'),
        "genericCritChancePercentagePoints": stat("genericCrit", "Add percentage points to generic critical chance", -100, 100, "percentage_points"),
        "genericAttackSpeedBonusPercent": stat("attackSpeed", "Add percent/100 to generic attack speed", -90, 300, "additive_percent", percent=True),
        "genericKnockbackBonusPercent": stat("knockback", "Add percent/100 to generic StatModifier knockback; not flat points", -90, 300, "additive_percent", percent=True),
        "minionSlotsBonus": stat("minionSlots", "Add minion slots", 0, 20, "slots", integer=True),
        "sentrySlotsBonus": stat("sentrySlots", "Add sentry slots", 0, 20, "slots", integer=True),
        "manaCostReductionPercentagePoints": stat("manaCostReduction", "Subtract percent/100 from Player.manaCost factor, floored at 0.1", 0, 90, "percentage_points", percent=True),
        "ammoSaveChancePercent": stat("ammoSaveChance", "Equipped owner's ammo saving chance via Player.CanConsumeAmmo for any weapon; equipped item chances combine as 1−product(1−p)", 0, 99, "probability_percent", percent=True),
        "aggroPoints": stat("aggro", "Add raw Player.aggro engine points (negative reduces targeting); not a probability or radius", -1000, 1000, "engine units: aggro points", integer=True),
        "damageReductionPercentagePoints": stat("endurance", "Add percent/100 to Player.endurance damage reduction", 0, 75, "percentage_points", percent=True),
        "genericArmorPenetrationPoints": stat("armorPenetration", "Add flat armor penetration points to DamageClass.Generic; not damage percent", 0, 100, "armor_points"),
        "whipRangeBonusPercent": stat("whipRange", "Add percent/100 to Player.whipRangeMultiplier", -90, 300, "additive_percent", percent=True),
        "taggedSummonSourceDamageBonusPercent": stat("summonTagDamage", "Multiply summon projectile source damage by 1+percent/100 only against an NPC tagged by this owner's generated whip", 0, 300, "source_damage_percent", percent=True),
        "lightStrength": stat("lightStrength", "Client-only RGB light coefficient multiplying lightColor; not tile radius; requires lightColor when positive", 0, 1.5, "engine units: RGB coefficient"),
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
    if not armor:
        p["gravityControl"] = _p("boolean", "Native gravity potion control; up input flips gravity. Independently authored; false grants nothing. Native ResetEffects/extra-jump reset removes on unequip; no automatic sibling grants.", required=False, wire_name="gravityControl", neutral=False, execution_phase=phase, wire_presence_requires_receipt=True)
        p["featherFall"] = _p("boolean", "Native feather fall with up/down descent controls. Independently authored; false grants nothing. Native ResetEffects/extra-jump reset removes on unequip; no automatic sibling grants.", required=False, wire_name="featherFall", neutral=False, execution_phase=phase, wire_presence_requires_receipt=True)
        p["extraFallTiles"] = _p("integer", "Additional native fall damage threshold in tiles; additive, not immunity", required=False, minimum=0, maximum=100, wire_name="extraFallTiles", neutral=0, execution_phase=phase, wire_presence_requires_receipt=True)
        p["autoPaint"] = _p("boolean", "Native automatic painting consumes carried paint with placement. Independently authored; false grants nothing. Native ResetEffects/extra-jump reset removes on unequip; no automatic sibling grants.", required=False, wire_name="autoPaint", neutral=False, execution_phase=phase, wire_presence_requires_receipt=True)
        p["rulerGrid"] = _p("boolean", "Native ruler grid controlled by builder toggles. Independently authored; false grants nothing. Native ResetEffects/extra-jump reset removes on unequip; no automatic sibling grants.", required=False, wire_name="rulerGrid", neutral=False, execution_phase=phase, wire_presence_requires_receipt=True)
        p["buildRangeTiles"] = _p("integer", "Additional native tile placement reach in tiles; additive", required=False, minimum=0, maximum=20, wire_name="buildRangeTiles", neutral=0, execution_phase=phase, wire_presence_requires_receipt=True)
        p["tileSpeedBonusPercent"] = _p("integer", "Add percent/100 native tile placement speed; additive, native limits apply", required=False, minimum=0, maximum=100, wire_name="tileSpeedBonusPercent", neutral=0, execution_phase=phase, wire_presence_requires_receipt=True)
        p["wallSpeedBonusPercent"] = _p("integer", "Add percent/100 native wall placement speed; additive, native limits apply", required=False, minimum=0, maximum=100, wire_name="wallSpeedBonusPercent", neutral=0, execution_phase=phase, wire_presence_requires_receipt=True)
        p["autoJump"] = _p("boolean", "Native held-button auto jump. Independently authored; false grants nothing. Native ResetEffects/extra-jump reset removes on unequip; no automatic sibling grants.", required=False, wire_name="autoJump", neutral=False, execution_phase=phase, wire_presence_requires_receipt=True)
        p["frogJump"] = _p("boolean", "Native frog jump height and safe fall allowance. Independently authored; false grants nothing. Native ResetEffects/extra-jump reset removes on unequip; no automatic sibling grants.", required=False, wire_name="frogJump", neutral=False, execution_phase=phase, wire_presence_requires_receipt=True)
        p["wallGrip"] = _p("integer", "Native spiked-boots level: 0 none, 1 wall slide/jump, 2 wall cling; combines by maximum", required=False, minimum=0, maximum=2, wire_name="wallGrip", neutral=0, execution_phase=phase, wire_presence_requires_receipt=True)
        p["swimFlipper"] = _p("boolean", "Native flipper swimming jump while wet. Independently authored; false grants nothing. Native ResetEffects/extra-jump reset removes on unequip; no automatic sibling grants.", required=False, wire_name="swimFlipper", neutral=False, execution_phase=phase, wire_presence_requires_receipt=True)
        p["divingHelm"] = _p("boolean", "Native diving helmet breath conservation. Independently authored; false grants nothing. Native ResetEffects/extra-jump reset removes on unequip; no automatic sibling grants.", required=False, wire_name="divingHelm", neutral=False, execution_phase=phase, wire_presence_requires_receipt=True)
        p["underwaterBreathing"] = _p("boolean", "Native gills: breathe air and water; getGoodWorld reverses drowning and requires water. Independently authored; false grants nothing. Native ResetEffects/extra-jump reset removes on unequip; no automatic sibling grants.", required=False, wire_name="underwaterBreathing", neutral=False, execution_phase=phase, wire_presence_requires_receipt=True)
        p["waterFloat"] = _p("boolean", "Native water flotation, descend with down control. Independently authored; false grants nothing. Native ResetEffects/extra-jump reset removes on unequip; no automatic sibling grants.", required=False, wire_name="waterFloat", neutral=False, execution_phase=phase, wire_presence_requires_receipt=True)
        p["jumpCloud"] = _p("boolean", "Cloud bottle extra jump. Independently authored; false grants nothing. Native ResetEffects/extra-jump reset removes on unequip; no automatic sibling grants. Only enables this native jump; native order, movement restrictions and landing recharge apply; equip never refreshes spent jumps.", required=False, wire_name="jumpCloud", neutral=False, execution_phase=phase, wire_presence_requires_receipt=True)
        p["jumpBlizzard"] = _p("boolean", "Blizzard bottle extra jump. Independently authored; false grants nothing. Native ResetEffects/extra-jump reset removes on unequip; no automatic sibling grants. Only enables this native jump; native order, movement restrictions and landing recharge apply; equip never refreshes spent jumps.", required=False, wire_name="jumpBlizzard", neutral=False, execution_phase=phase, wire_presence_requires_receipt=True)
        p["jumpSandstorm"] = _p("boolean", "Sandstorm bottle extra jump. Independently authored; false grants nothing. Native ResetEffects/extra-jump reset removes on unequip; no automatic sibling grants. Only enables this native jump; native order, movement restrictions and landing recharge apply; equip never refreshes spent jumps.", required=False, wire_name="jumpSandstorm", neutral=False, execution_phase=phase, wire_presence_requires_receipt=True)
        p["jumpFart"] = _p("boolean", "Fart jar extra jump. Independently authored; false grants nothing. Native ResetEffects/extra-jump reset removes on unequip; no automatic sibling grants. Only enables this native jump; native order, movement restrictions and landing recharge apply; equip never refreshes spent jumps.", required=False, wire_name="jumpFart", neutral=False, execution_phase=phase, wire_presence_requires_receipt=True)
        p["jumpTsunami"] = _p("boolean", "Tsunami bottle extra jump. Independently authored; false grants nothing. Native ResetEffects/extra-jump reset removes on unequip; no automatic sibling grants. Only enables this native jump; native order, movement restrictions and landing recharge apply; equip never refreshes spent jumps.", required=False, wire_name="jumpTsunami", neutral=False, execution_phase=phase, wire_presence_requires_receipt=True)
        for name, meaning in (
            ("fishingLine", "Enable native Player.accFishingLine while equipped: caught fish cannot be lost by the line-break roll. Does not preserve bait, select a rod or spawn fish."),
            ("lavaFishing", "Enable native Player.accLavaFishing while equipped. Terraria still requires a usable pole and bait and owns biome/catch rules; this grants no lava damage immunity."),
            ("fishingSonar", "Enable native Player.sonarPotion catch preview while equipped. Visual information only; does not select or improve the catch."),
            ("fishingCrates", "Enable native Player.cratePotion while equipped: use the engine crate-chance modifier, not a guaranteed crate or custom loot table."),
            ("lifePickup", "Enable native Player.lifeMagnet: extend pickup for native heart variants only. Does not heal or create drops."),
            ("manaPickup", "Enable native Player.manaMagnet: extend pickup for native mana star variants only. Does not restore mana directly."),
            ("coinPickup", "Enable native Player.goldRing: extend pickup for coin items only. Does not increase coin drops."),
            ("treasurePickup", "Enable native Player.treasureMagnet: add native treasure grab range to eligible world items, stacking with native specialized magnets. Does not bypass pickup eligibility or inventory space."),
            ("treasureVision", "Enable native Player.findTreasure highlighting for engine-recognized treasure tiles. Does not reveal unexplored map or spawn treasure."),
            ("dangerVision", "Enable native Player.dangerSense highlighting for engine-recognized dangerous tiles. Does not grant hazard immunity."),
            ("creatureVision", "Enable native Player.detectCreature highlighting. Information only; does not target, damage or summon creatures."),
            ("nightVision", "Enable native Player.nightVision lighting visibility. Does not create light sources, map reveal, treasure detection or danger detection."),
            ("iceSkate", "Enable Player.iceSkate: native ice acceleration/sliding behavior and no thin-ice break; not general movement speed"),
            ("noKnockback", "Enable Player.noKnockback for native hurt knockback immunity; damage, defense and enemy-knockback modifiers remain separate"),
            ("fireWalk", "Enable Player.fireWalk: immunity to TileID.Sets.TouchDamageHot blocks only; NOT lava immunity, fire debuffs or all harmful tiles"),
        ):
            p[name] = _p("boolean", meaning, required=False, wire_name=name, neutral=False,
                         execution_phase=phase, wire_presence_requires_receipt=True)
        p["accRunSpeedBlocksPerSecond"] = _world_units(_p("number", "Native sprint-speed floor: max(Player.accRunSpeed, lowered value) in equip phase; 0 grants nothing. Later native terrain/mount/wing/chilled rules still apply; distinct from moveSpeed percent and the post-vanilla maxRunSpeed flat bonus", required=False, minimum=0, maximum=20, units="pixels_per_tick", wire_name="accRunSpeed", neutral=0, consumer_storage="float32", execution_phase=phase, wire_presence_requires_receipt=True), "accRunSpeedPxPerTick", multiplier=16, divisor=60, updates_power=0, units='blocks/s')
        p["rocketBoots"] = _p("integer", "Native Player.rocketBoots mode: 0 grants nothing, 1 uses 30-tick rocketDelay2, 2..5 use 15-tick rocketDelay2. Any nonzero mode enables native charge/thrust flight, not wings. Modes combine by max; does not choose vanityRocketBoots, ice skating, sprint speed or refresh rocketTime. Native rocketTimeMax=7 charges with 10-tick thrust windows; landing/sliding/RefreshMovementAbilities refill, wings may convert charges to wingTime; mounts suppress flight", required=False, minimum=0, maximum=5, units="native rocket flight mode", wire_name="rocketBoots", neutral=0, execution_phase=phase, wire_presence_requires_receipt=True)
        p["fishingPower"] = _p("integer", "Add raw Player.fishingSkill points while equipped; Terraria combines them with pole/bait and environment multipliers. Zero adds nothing; does not create a fishing rod, bait or projectile", required=False, minimum=0, maximum=100, units="fishing power points", wire_name="fishingPower", neutral=0, execution_phase=phase, wire_presence_requires_receipt=True)
        p["wireVision"] = _p("boolean", "Enable Player.InfoAccMechShowWires while equipped; native builder toggles choose wire colors and actuators; not ruler, placement or inventory activation", required=False, wire_name="wireVision", neutral=False, execution_phase=phase, wire_presence_requires_receipt=True)
    if armor:
        set_phase = "ModItem.UpdateArmorSet; exact setKey on head, body and legs"
        set_effects = (
            "genericCritChancePercentagePoints",
            "moveSpeedBonusPercent", "lifeRegenHpPerSecond", "manaRegenBonusPoints",
            "minionSlotsBonus", "sentrySlotsBonus", "manaCostReductionPercentagePoints",
            "ammoSaveChancePercent", "aggroPoints", "damageReductionPercentagePoints",
            "genericArmorPenetrationPoints",
        )
        for name in set_effects:
            spec = p[name]
            set_wire = "setBonus" + spec.wire_name[0].upper() + spec.wire_name[1:]
            safety = runtime_safety.get(set_wire)
            p["setBonus" + name[0].upper() + name[1:]] = replace(
                spec, description="Matching armor set (head piece only; matching head, body and legs must actually be equipped): " + spec.description,
                wire_name=set_wire,
                runtime_minimum=safety[0] if safety else None,
                runtime_maximum=safety[1] if safety else None,
                execution_phase=set_phase)
    if armor:
        grouped = {}
        for name in tuple(p):
            if name.startswith("setBonus"):
                leaf = name[len("setBonus"):]
                grouped[leaf[0].lower() + leaf[1:]] = p.pop(name)
        p["setBonuses"] = _p("object", "Matching three-piece armor set bonuses, executed once by its head piece; exact setKey required for non-neutral effects", required=False, properties=grouped, min_properties=1)
    return MappingProxyType(p)


_ACCESSORY_PRIMITIVES = _equipment_params(armor=False)
_ARMOR_PRIMITIVES = _equipment_params(armor=True)
PLACEMENT_CAPABILITIES: Final[tuple[str, ...]] = ("configure_tile_placement", "configure_wall_placement")

def _immunity_param() -> ParamSpec:
    return _p("union", "Choose owner_shared, once_per_npc, or {localCooldown:0..600} raw unscaled engine counts; independent of penetration and updatesPerTick.",
              semantic_type="terraria_npc_immunity", alternatives=(
        _p("string", "Terraria shared owner immunity; this projectile has no separate NPC timer", enum=("owner_shared",),
           wire_literals={"npcImmunityMode": "owner", "localNpcHitCooldownTicks": -1}),
        _p("string", "This projectile may hit each NPC once", enum=("once_per_npc",),
           wire_literals={"npcImmunityMode": "local", "localNpcHitCooldownTicks": -1}),
        _p("object", "Per-projectile NPC immunity with explicit engine cooldown counts", properties={
            "localCooldown": _p("integer", "Raw unscaled Projectile.localNPCHitCooldown, including 0; not seconds/world ticks",
                                minimum=0, maximum=600, units="engine units: local NPC cooldown counts",
                                wire_name="localNpcHitCooldownTicks"),
        }, wire_literals={"npcImmunityMode": "local"}),
    ))


_SPAWN_ANCHORS: Final[Mapping[str, str]] = MappingProxyType({
    "activation_origin": "item_use_origin", "owner_center": "owner_center",
    "cursor": "cursor", "ground_at_cursor": "ground_at_cursor",
    "native_resting_spot": "native_resting_spot",
})


def _spawn_position_param() -> ParamSpec:
    def anchor() -> ParamSpec:
        return _p("string", "Exact spawn anchor; activation_origin is the invoking producer's origin. For generic projectile event spawns, on_hit/on_crit: struck NPC center; periodic/on_spawn/on_kill: source projectile center. Do not generalize these origins to other producers. native_resting_spot explicitly calls Player.FindSentryRestingSpot with native reachable-area clamp and centers above returned ground by half the entity hitbox height; it does not enable native sentry lifecycle",
                  enum=_SPAWN_ANCHORS, wire_enum=_SPAWN_ANCHORS, wire_name="placement")
    return _p("union", "Choose an anchor and optionally a literal vertical height above it; aim is computed after this shift",
              semantic_type="spawn_position", alternatives=(
        _p("object", "At the explicit anchor, with no vertical offset", properties={"at": anchor()},
           wire_literals={"overTarget.heightTiles": 0, "overTarget.delayTicks": 0}),
        _p("object", "Above the explicit anchor", properties={
            "above": anchor(), "heightTiles": _p("number", "Vertical offset above the selected anchor", minimum=1,
                maximum=80, units="tiles", wire_name="overTarget.heightTiles"),
            "activationDelaySeconds": _seconds(_p("integer", "Delay activation of this already spawned projectile; occupies a live slot, and initial timeLeft includes both lifetime and this delay", minimum=0, maximum=600, units="ticks", wire_name="overTarget.delayTicks"), "activationDelayTicks"),
        }),
    ))


def _event_when_param(events: Iterable[str]) -> ParamSpec:
    allowed = tuple(events)
    ordinary = tuple(event for event in allowed if event not in {"periodic", "on_hurt", "on_enemy_kill"})
    variants = [_p("string", "Exact emitted event", enum=ordinary, wire_name="event")] if ordinary else []
    if "on_use" in allowed:
        variants.append(_p("object", "Accepted item use from the selected input; both matches each use once.", properties={
            "on": _p("string", "Accepted item-use event", enum=("on_use",), wire_name="event"),
            "useInput": _p("string", "Input that caused this use, captured before any delay; both selects either input, not two executions.", enum=("primary_use", "alternate_use", "both")),
        }))
    if "periodic" in allowed:
        variants.append(_p("object", "Periodic event; call ID fixes the item phase", properties={
            "everySeconds": _seconds(_p("integer", "World-time interval; producer clocks retain their phase",
                             minimum=6, maximum=3600, units="ticks", wire_name="periodTicks"), "everyTicks"),
        }, wire_literals={"event": "periodic"}))
    reactions = tuple(event for event in allowed if event in {"on_hurt", "on_enemy_kill"})
    if reactions:
        variants.append(_p("object", "Functional equipment reaction; identical copies share cooldown.", properties={
            "on": _p("string", "Equipment event", enum=reactions, wire_name="event"),
            "cooldownSeconds": _seconds(_p("integer", "Shared interval reserved before dispatch", minimum=6, maximum=3600, units="ticks", wire_name="reactionCooldownTicks"), "reactionCooldownTicks"),
        }))
    return (_p("union", "Explicit event trigger", alternatives=variants, semantic_type="runtime_event_trigger")
            if len(variants) > 1 else replace(variants[0], semantic_type="runtime_event_trigger"))


def authored_event(params: Mapping[str, Any]) -> str:
    """Read the explicit current Author trigger, including malformed-value diagnostics."""
    when = params.get("when")
    if isinstance(when, str):
        return when
    if isinstance(when, Mapping):
        if when.get("on") in ("on_use", "on_hurt", "on_enemy_kill"): return str(when["on"])
        return "periodic"
    return ""
def _spawn_velocity() -> ParamSpec:
    def speed(description: str, wire: str) -> ParamSpec:
        return _p("number", description, minimum=0, maximum=80,
                  units="pixels/projectile update", semantic_type="initial_velocity_speed",
                  neutral=0, consumer_storage="float32", wire_name=wire)

    variants = [_p("object", "Exact constant-speed deterministic fan; preserves the established wire.", properties={
        "constantSpeedBlocksPerSecond": _world_units(speed("Initial world-speed magnitude before subsequent movement and collisions.", "speedPxPerTick"), "constantSpeedPxPerUpdate", multiplier=16, divisor=60, updates_power=1, units='blocks/s'),
    })]
    for name, kind, description in (
        ("fanSpeed", "fan_speed", "Keep the authored deterministic fan directions; independently sample each speed uniformly between min and max."),
        ("radial", "radial", "Sample each direction uniformly over the full circle and speed uniformly between min and max."),
        ("disk", "disk", "Sample velocity uniformly by area in the zero-centred disk; radial speed is max*sqrt(U), not uniform radius."),
        ("cone", "cone", "Independently jitter each authored fan direction uniformly within the selected half-angle, and sample speed uniformly between min and max."),
    ):
        fields = {"maxSpeedBlocksPerSecond": _world_units(speed("Upper sampled speed, inclusive at the degenerate min=max boundary.", "velocityDistribution.maxSpeedPxPerUpdate"), "maxSpeedPxPerUpdate", multiplier=16, divisor=60, updates_power=1, units='blocks/s')}
        if kind != "disk":
            fields = {"minSpeedBlocksPerSecond": _world_units(speed("Lower sampled speed; must not exceed maxSpeedBlocksPerSecond.", "velocityDistribution.minSpeedPxPerUpdate"), "minSpeedPxPerUpdate", multiplier=16, divisor=60, updates_power=1, units='blocks/s'), **fields}
        if kind == "cone":
            fields["halfAngleRadians"] = _p("number", "Uniform signed angular jitter around each existing fan direction.",
                minimum=0, maximum=math.pi, units="radians", semantic_type="radians", neutral=0,
                consumer_storage="float32", wire_name="velocityDistribution.halfAngleRadians")
        variants.append(_p("object", description, properties={name: _p("object", description,
            properties=fields, wire_literals={"velocityDistribution.kind": kind, "speedPxPerTick": 0})}))
    return _p("union", "Select exactly one initial velocity rule. Owner samples a seeded batch once; native projectile state synchronizes the result. No peer reroll or inferred distribution.",
              alternatives=variants, semantic_type="initial_velocity_distribution", wire_presence_requires_receipt=True)


def _hit_target_spawn_geometry() -> ParamSpec:
    fields = {}
    for name, wire, maximum, units, meaning in (
        ("beforeProbability", "beforeProbability", 1, "probability", "Independent per-child probability of the before-target branch; this is geometry, not a promised re-hit chance."),
        ("hitboxMaxSideFactor", "hitboxMaxSideFactor", 2, "hitbox max-side factor", "Clearance radius uses max(target.width,target.height) times this factor, plus clearanceBlocks converted to pixels."),
        ("clearanceBlocks", "clearancePx", 128, "blocks", "Additional target-centre clearance, explicitly added to the selected hitbox radius."),
        ("beforePositionJitterRadiusBlocks", "beforePositionJitterRadiusPx", 128, "blocks", "Before-target origin gets uniform-area disk jitter of this radius; 0 disables positional jitter."),
        ("beforeDirectionJitterRadians", "beforeDirectionJitterRadians", math.pi, "radians", "Before-target direction gets uniform signed jitter within this half-angle around the event direction."),
        ("afterFanSpreadRadians", "afterFanSpreadRadians", math.tau, "radians", "After-target directions use the deterministic inclusive fan over all child indices; each origin lies on its own ray."),
    ):
        spec = _p("number", meaning, minimum=0, maximum=maximum, units=units,
            semantic_type="spawn_geometry", consumer_storage="float64" if name == "beforeProbability" else "float32", neutral=0,
            wire_name="hitTargetSpawn." + wire)
        fields[name] = (_world_units(spec, wire, multiplier=16, units="blocks") if units == "blocks" else spec)
    fields["initialIgnoreCountdownUpdates"] = _p("integer", "Exact initial NPC exclusion counter, decremented before collision: 10 excludes the target before first AI and the next 9 post-AI collision opportunities; 1 only before first AI; 0 disables exclusion. Counts extra AI updates, not world ticks.",
        minimum=0, maximum=600, units="projectile AI countdown updates", semantic_type="initial_target_exclusion_countdown",
        wire_name="hitTargetSpawn.initialIgnoreCountdownUpdates")
    return _p("object", "Explicit hit-target-relative origin and direction sampling. Capture target geometry/event direction and owner seed at action admission, including delayed actions. Positive exclusion retains the exact NPC incarnation and refuses reused slots; zero disables exclusion and its incarnation cancellation guard.",
              properties=fields, wire_literals={"spreadRadians": 0},
              semantic_type="hit_target_spawn_geometry", wire_presence_requires_receipt=True)


_CAPS: list[CapabilitySpec] = [
    _cap(
        "configure_item_stats",
        "Set exact item stats; no weapon class or behaviour is inferred.",
        "item",
        ("item_body",),
        {
            "damageClass": _p("string", "Exact built-in token or loaded tModLoader DamageClass.FullName copied only from parent damageClass facts (not item FullName)", pattern=_DAMAGE_CLASS_PATTERN, semantic_type="terraria_damage_class"),
            "damage": _p("integer", "Base item damage", minimum=0, maximum=2000),
            "knockback": _p("number", "Item.knockBack engine strength, not pixels or damage", minimum=0, maximum=20, units="engine units: Item.knockBack"),
            "useTimeSeconds": _seconds(_p("integer", "Terraria use/reuse interval (60 ticks/s), not the animation length", minimum=1, maximum=600, units="ticks", wire_name="useTime"), "useTimeTicks"),
            "useAnimationSeconds": _seconds(_p("integer", "Duration of one use animation, independent of useTimeSeconds; differing values can allow multiple uses during one animation, not necessarily one projectile per click", minimum=1, maximum=600, units="ticks", wire_name="useAnimation"), "useAnimationTicks"),
            "manaCost": _p("integer", "Base Item.mana points before player mana-cost modifiers, not guaranteed final mana spent. For primary_use/alternate_use, native mana payment is attempted when a new use animation starts; useTimeSeconds can permit additional Shoot/UseItem activations inside that animation without another native mana payment. This is not a per-projectile or per-successful-spawn debit. A separately explicit controller manaPayment may add recurring payment; do not infer it. Omitted means no mana cost, independently of DamageClass.", minimum=0, maximum=500, required=False, default=0, neutral=0),
            "manaCostInput": _p("string", "Which active input pays manaCost through native animation-start payment. The other input costs no base item mana. Omitted means both, preserving shared-cost behavior. This does not change explicit controller manaPayment.", enum=("primary_use", "alternate_use", "both"), required=False, default="both", neutral="both"),
            "rarity": _p("integer", "Exact loaded Item.rare ID; copy modded IDs from parent facts, do not guess", minimum=0, maximum=65535, semantic_type="loaded_rarity_id"),
            "valueCopper": _p("integer", "Exact Terraria Item.value field in copper; NPC shop price/base value, not an inferred player resale amount", minimum=0, maximum=100000000, units="copper", wire_name="value"),
            "maxStack": _p("integer", "Maximum stack", minimum=1, maximum=9999),
            "craftYield": _p("integer", "Requested items per craft; actual granted stack is capped by maxStack", minimum=1, maximum=9999),
            "widthPx": _p("integer", "Inventory/world hitbox width", minimum=8, maximum=256, units="pixels", wire_name="width"),
            "heightPx": _p("integer", "Inventory/world hitbox height", minimum=8, maximum=256, units="pixels", wire_name="height"),
            "scale": _p("number", "Dimensionless held Item scale via ModifyItemScale (1 unchanged/neutral); multiplies the presentation base size, not bake resolution. Independent of dropped worldScale and projectile hitbox.drawScale/visual.scale", minimum=0.25, maximum=4, wire_name="itemScale"),
        },
        component_slot="item_stats",
        py=_COMPILER_OWNER,
        cs="Common/Models/Runtime/GeneratedItemData.Apply.cs::ApplyToItem",
        lowering=("gameplay.damageClass", "gameplay.damage", "gameplay.knockback", "gameplay.useTime", "gameplay.useAnimation", "gameplay.manaCost", "gameplay.manaCostInput", "gameplay.rarity", "gameplay.value", "gameplay.maxStack", "gameplay.craftYield", "gameplay.width", "gameplay.height", "gameplay.itemScale"),
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
            "hideUseGraphic": _p("boolean", "Suppress vanilla item-use sprite. Choose true for deliberate invisibility or an actual physical held-body replacement, not merely because the item fires. Free projectiles do not replace the held launcher/body. customHeldSprite=inherit or omission also follows this flag for the custom generated root; explicit visible keeps that root visible while active, so true may intentionally hide vanilla while retaining the custom body. Coordinate the authored visibility with Visual/VFX physical representation; neither stage edits this flag"),
            "disableMeleeHitbox": _p("boolean", "Disable vanilla item melee hitbox"),
            "channel": _p("boolean", "Keep use active while input is held"),
            "holdoutOffsetX": _p("integer", "Held draw offset X", minimum=-96, maximum=96, units="pixels", required=False, default=0, neutral=0),
            "holdoutOffsetY": _p("integer", "Held draw offset Y", minimum=-96, maximum=96, units="pixels", required=False, default=0, neutral=0),
            "handPose": _p("string", "Exact renderer hint", required=False, enum=("", "one_handed", "two_handed", "overhead", "forward")),
            "customHeldSprite": _p("string", "Custom held-root visibility only, not gameplay release timing: hidden suppresses it; visible keeps it while use is active; inherit or omission follows hideUseGraphic. This does not schedule gameplay release or change vanilla hideUseGraphic.", required=False, enum=("hidden", "visible", "inherit"), wire_name="releaseTiming", wire_enum={"hidden": "immediate", "visible": "on_release", "inherit": ""}),
        },
        component_slot="item_use",
        py=_COMPILER_OWNER,
        cs="Content/Items/GeneratedItem.Use.cs::CanUseItem|Content/Items/GeneratedItem.UseStyle.cs::UseStyle",
        wire=(
            "gameplay.useStyleName",
            "gameplay.autoReuse",
            "gameplay.useTurn",
            "gameplay.holdoutOffsetX",
            "gameplay.holdoutOffsetY",
            "gameplay.handPose",
            "gameplay.releaseTiming",
            "runtimeProgram.itemUse.configured",
            "runtimeProgram.itemUse.useStyle",
            "runtimeProgram.itemUse.hideUseGraphic",
            "runtimeProgram.itemUse.disableMeleeHitbox",
            "runtimeProgram.itemUse.channel",
            "runtimeProgram.itemUse.handPose",
            "runtimeProgram.itemUse.releaseTiming",
            "runtimeProgram.itemUse.holdoutOffsetX",
            "runtimeProgram.itemUse.holdoutOffsetY",
        ),
        lowering=("gameplay.useStyle", "gameplay.autoReuse", "gameplay.useTurn", "runtimeProgram.itemUse.*"),
    ),
    _cap(
        "collect_seeds_from_grass",
        "Inventory passive: explicitly let this generated definition satisfy Terraria's native grass seed-collection inventory check. No use/equip/hold binding is needed. Only carried inventory slots 0..57 count (not mouse slot, equipment, banks or Void Bag); native tile admission, 50% seed RNG, nearest-player selection and drop/MP lifecycle remain unchanged. Does not consume the item, choose ammo, change attack costs, or inherit automatically from a parent flag. No parameters.",
        "item_inventory",
        ("item_body",),
        {},
        component_slot="inventory_seed_collection",
        authority="native_worldgen",
        budget="one bounded native inventory witness; no added spawns or RNG",
        py=_COMPILER_OWNER,
        cs="Common/Systems/Utility/GeneratedInventorySeedSystem.cs::HasItem",
        wire=("gameplay.collectSeedsFromGrass",),
        fixed_wire_literals={"collectSeedsFromGrass": True},
        wire_presence_path="gameplay.collectSeedsFromGrass",
    ),
    _cap(
        "configure_item_contact_hitbox",
        "Modify the current Terraria contact rectangle when a binding enables item-body contact; not a fixed PNG box. Keep its center; round each dimension times hitboxScale, add contactForgivenessPx on each side, minimum 1px. Omission leaves native geometry unchanged.",
        "item_combat",
        ("item_body",),
        {
            "hitboxScale": _p("number", "Contact hitbox scale; 1 unchanged", minimum=0.5, maximum=2),
            "contactForgivenessPx": _p("integer", "Extend scaled contact hitbox by this many pixels on each side", minimum=0, maximum=64, units="pixels"),
        },
        component_slot="item_contact",
        emitted_events=("on_hit", "on_crit"),
        py=_COMPILER_OWNER,
        cs="Content/Items/GeneratedItem.Use.cs::UseItemHitbox/OnHitNPC",
        wire=("runtimeProgram.itemContact.hitboxScale", "runtimeProgram.itemContact.contactForgivenessPx"),
    ),
    _cap(
        "configure_weapon_ammo",
        "Require native Terraria ammo selection and conservation for every active spawn_entity shot of this item. The authored runtime entity always supplies projectile behavior; selected ammo projectile AI is not copied. Native weapon-plus-ammo damage and knockback reach that root unchanged. native_shot requires constant velocity on each active binding target; authored_spawn preserves explicitly sampled velocity. Other actions and passive hold spawns do not consume ammo. Native inventory-only item flags are not inherited by this call. This capability cannot coexist with configure_vanilla_ammo_item on the same item.",
        "item",
        ("item_body",),
        {
            "ammoCategory": _p("string", "Exact stable AmmoID category required by this weapon; Terraria chooses the inventory ammo and applies native saving hooks. Seeds share the dart category; the category does not select projectile appearance or copy the chosen ammo's AI", enum=VANILLA_AMMO_CATEGORY_TOKENS),
            "speedBasis": _p("string", "authored_spawn keeps configure_spawn initial speed; native_shot uses the final native shot velocity magnitude, including ammo/prefix/player/late-hook speed, along the independently authored aim. Stationary entities still have zero velocity; later authored movement/controller logic remains authoritative", enum=("authored_spawn", "native_shot")),
        },
        requirements=(RequirementSpec(
            "binding_tuple_present", target="any_entity",
            any_of=("primary_use|spawn_entity", "alternate_use|spawn_entity"),
            message="Weapon ammo requires an explicit active spawn_entity shot; hold/equipped events or item effects are not native ammo consumers.",
        ),),
        component_slot="weapon_ammo",
        authority="owner_execute_sync",
        exclusive_group="ammo_role",
        py=_COMPILER_OWNER,
        cs="Common/Models/Runtime/GeneratedItemData.Apply.cs::ApplyToItem|Content/Items/GeneratedItem.Use.cs::ApplyActiveUseProjection/Shoot",
        lowering=("runtimeProgram.weaponAmmo",),
        lowering_inputs=("runtimeProgram.calls[].fn",),
    ),
    _cap(
        "configure_vanilla_ammo_item",
        "Mark this generated item as one exact vanilla ammo category and projectile. Sets Item.ammo and Item.shoot; it does not configure a weapon to consume ammo.",
        "item",
        ("item_body",),
        {
            "ammoCategory": _p("string", "Exact stable Terraria AmmoID category", enum=VANILLA_AMMO_CATEGORY_TOKENS),
            "projectileId": _p("integer", "Exact vanilla ProjectileID fired when this ammo is consumed; do not guess", minimum=1, maximum=VANILLA_PROJECTILE_TYPE_ID_MAX, wire_name="ammoProjectileId"),
            "shootSpeedContributionBlocksPerSecond": _world_units(_p("number", "Base/native launch contribution to Item.shootSpeed via vanilla PickAmmo, in blocks/s. No eventual projectile updatesPerTick is known here; this contribution is not a guaranteed final projectile speed", minimum=-20, maximum=80, units="pixels/projectile update contribution", wire_name="ammoShootSpeedPxPerTick"), "shootSpeedContributionPxPerUpdate", multiplier=16, divisor=60, updates_power=0, units='blocks/s (base native launch contribution, not final projectile speed)'),
            "notAmmo": _p("boolean", "Exact Item.notAmmo flag for special ammo-slot/tooltip behaviour"),
        },
        component_slot="ammo_item",
        exclusive_group="ammo_role",
        py=_COMPILER_OWNER,
        cs="Common/Models/Contracts/TerrariaRuntimeVocabulary.cs::ResolveAmmoCategory|Common/Models/Runtime/GeneratedItemData.Apply.cs::ApplyToItem",
        wire=("gameplay.ammoCategory", "gameplay.ammoProjectileId", "gameplay.ammoShootSpeedPxPerTick", "gameplay.notAmmo"),
        lowering=("gameplay.ammoCategory", "gameplay.ammoProjectileId", "gameplay.ammoShootSpeedPxPerTick", "gameplay.notAmmo"),
    ),
    _cap(
        "restore_resources_on_use",
        "Restore exact life and/or mana when use succeeds.",
        "item_utility",
        ("item_body",),
        {
            "healLife": _p("integer", "Life restored", minimum=0, maximum=500, neutral=0),
            "healMana": _p("integer", "Mana restored", minimum=0, maximum=500, neutral=0),
            "usesPotionRules": _p("boolean", "Set Terraria Item.potion rules including Quick Heal eligibility and potion-sickness use gating; not a duration; false allows non-potion healing", wire_name="potion"),
        },
        component_slot="resource_restore",
        py=_COMPILER_OWNER,
        cs="Common/Models/Runtime/GeneratedItemData.Apply.cs::ApplyToItem",
        wire=("gameplay.healLife", "gameplay.healMana", "gameplay.potion"),
        lowering=("gameplay.healLife", "gameplay.healMana", "gameplay.potion"),
        effect_groupable=True,
    ),
    _cap(
        "apply_vanilla_buff_on_use",
        "Apply one concrete Terraria buff when use succeeds.",
        "item_utility",
        ("item_body",),
        {
            "buffId": _p("integer", "Exact loaded BuffID/ModContent.BuffType; copy from parent facts, do not guess", minimum=1, maximum=65535, semantic_type="loaded_buff_id", wire_name="buffCode"),
            "durationSeconds": _seconds(_p("integer", "Buff duration", minimum=1, maximum=21600, units="ticks", wire_name="buffTime"), "durationTicks"),
        },
        component_slot="use_buff",
        multiplicity="many_per_target",
        py=_COMPILER_OWNER,
        cs="Content/Items/GeneratedItem.Use.cs::ApplyItemEffects",
        wire=("gameplay.extraBuffs[].buffCode", "gameplay.extraBuffs[].buffTime"),
        lowering=("gameplay.extraBuffs[]",),
        effect_groupable=True,
    ),
    _cap(
        "apply_generated_buff_on_use",
        "Apply a bounded generated utility effect. Refreshing an identical effect retains maximum remaining duration, not extra strength; distinct effects coexist under player stat caps. exhaustionSeconds starts at successful application or refresh, independently of buff duration. Normal attacks and other item effects are unchanged; attack cadence is separately authored. Free repeatable refresh can sustain indefinite uptime despite a short duration. No recurring cost is implied.",
        "item_utility",
        ("item_body",),
        {
            "combat": _p("object", "Optional temporary combat bonuses; all fields explicit when selected. Zero values have no effect. Same-effect refresh does not stack. No automatic active binding.", required=False, properties={
                "defensePoints": _p("integer", "Flat Player.statDefense points; aggregate generated-buff cap 100", minimum=0, maximum=100, neutral=0, wire_name="combat.defensePoints"),
                "attackSpeedPercent": _p("number", "Add percent/100 to generic attack speed; aggregate generated-buff cap 100", minimum=0, maximum=100, neutral=0, wire_name="combat.attackSpeedPercent", consumer_storage="float32"),
                "critChancePoints": _p("number", "Add percentage points to generic critical chance; aggregate generated-buff cap 100", minimum=0, maximum=100, neutral=0, wire_name="combat.critChancePoints", consumer_storage="float32"),
                "damagePercent": _p("number", "Add percent/100 to the explicitly selected damage class; aggregate generated-buff cap 200 per selected class. Generic and specific bonuses may combine through native inheritance", minimum=0, maximum=200, neutral=0, wire_name="combat.damagePercent", consumer_storage="float32"),
                "damageClass": _p("string", "Exact class receiving damagePercent; generic also contributes through native class inheritance", enum=("generic", "melee", "ranged", "magic", "summon", "throwing"), wire_name="combat.damageClass"),
            }),
            "durationSeconds": _seconds(_p("integer", "Remaining effect lifetime for one application; not a reuse cooldown. Identical-effect refresh retains the greater of current remaining ticks and this duration", minimum=1, maximum=21600, units="ticks"), "durationTicks"),
            "exhaustionSeconds": _seconds(_p("integer", "Optional per-player/item-definition generated-buff lockout; copies/groups share it, including zero/omitted groups while active. Blocked attempts refresh neither timer. Omission stays absent; explicit zero stays zero; neither starts exhaustion. Policy only, not a buff stat or normal-attack cooldown.", minimum=0, maximum=21600, units="world ticks", required=False, wire_presence_requires_receipt=True), "exhaustionTicks"),
            "miningSpeedMultiplier": _p("number", "Divides Player.pickSpeed (mining-time factor); >1 mines faster", minimum=0.25, maximum=4, units="engine units: pickSpeed divisor", required=False, default=1, neutral=1, consumer_storage="float32"),
            "lightStrength": _p("number", "Client light RGB coefficient multiplying selected light color; not tile radius", minimum=0, maximum=1.5, wire_name="emitLightStrength", units="engine units: RGB coefficient", neutral=0, consumer_storage="float32"),
            "lightColor": _p("string", "Canonical light color", enum=_COLOR, wire_name="lightColorName"),
            "oreSenseEnabled": _p("boolean", "Enable native Spelunker treasure highlighting, including eligible ores, chests and life crystals; not a radius or ore-only filter", semantic_type="boolean_capability", wire_name="oreSenseRadiusTiles", wire_boolean_true_value=1, neutral=False, required=False, default=False),
            "moveSpeedBonusPercent": _p("number", "Add percent/100 to Player.moveSpeed; 20 adds 20% before other modifiers", minimum=-50, maximum=200, wire_name="movementSpeed", wire_divisor=100, units="additive_percent", semantic_type="additive_percent", required=False, default=0, neutral=0, consumer_storage="float32"),
            "jumpSpeedBonusBlocksPerSecond": _world_units(_p("number", "Add to Player.jumpSpeedBoost in pixels/tick", minimum=0, maximum=8, wire_name="jumpBoost", units="pixels/world tick", required=False, default=0, neutral=0, consumer_storage="float32"), "jumpSpeedBonusPxPerTick", multiplier=16, divisor=60, updates_power=0, units='blocks/s'),
            "manaRegenBonusPoints": _p("integer", "Add Player.manaRegenBonus engine points; not directly mana/second", minimum=0, maximum=120, wire_name="manaRegen", units="engine units: manaRegenBonus points", required=False, default=0, neutral=0),
            "lifeRegenHpPerSecond": _p("number", "Generated buff: HP restored per second before other effects; exact half-HP steps map to Terraria Player.lifeRegen units (2 units = 1 HP/s)", minimum=0, maximum=60, multiple_of=0.5, units="HP/s", wire_name="lifeRegen", wire_multiplier=2, required=False, default=0, neutral=0),
        },
        component_slot="generated_use_buff",
        py=_COMPILER_OWNER,
        cs="Content/Items/GeneratedItem.Use.cs::ApplyItemEffects",
        wire=(
            "gameplay.generatedBuff.durationTicks",
            "gameplay.generatedBuff.exhaustionTicks",
            "gameplay.generatedBuff.miningSpeedMultiplier",
            "gameplay.generatedBuff.emitLightStrength",
            "gameplay.generatedBuff.lightColorName",
            "gameplay.generatedBuff.oreSenseRadiusTiles",
            "gameplay.generatedBuff.movementSpeed",
            "gameplay.generatedBuff.jumpBoost",
            "gameplay.generatedBuff.manaRegen",
            "gameplay.generatedBuff.lifeRegen",
            "gameplay.generatedBuff.combat.defensePoints",
            "gameplay.generatedBuff.combat.attackSpeedPercent",
            "gameplay.generatedBuff.combat.critChancePoints",
            "gameplay.generatedBuff.combat.damagePercent",
            "gameplay.generatedBuff.combat.damageClass",

        ),
        lowering=("gameplay.generatedBuff.*",),
        effect_groupable=True,
    ),
    _cap(
        "refresh_generated_effect_group_while_held",
        "Attempt to refresh one named generated utility buff group each world tick while this exact item is held; its exhaustionSeconds policy still applies. durationSeconds controls lingering after release, independently of exhaustion. Only apply_generated_buff_on_use may populate the group; no healing, teleport, native buff or invisible projectile is inferred.",
        "item_utility", ("item_body",),
        {"effectGroupId": _p("string", "Exact existing named generated-buff group", pattern=r"^[a-z][a-z0-9_]{0,47}$", wire_name="heldEffectGroupId", semantic_type="item_effect_group_reference")},
        component_slot="held_generated_buff",
        py=_COMPILER_OWNER, cs="Content/Items/GeneratedItem.Use.cs::HoldItem",
        wire=("runtimeProgram.heldEffectGroupId",),
    ),
    _cap(
        "configure_tool",
        "Set exact pick/axe/hammer powers and mining speed. Requires explicit item-use configuration and one executable primary_use binding so Terraria can execute mining. Native powers execute on use_item_body and spawn_entity actions, including projectile-plus-tool compositions on either active input, independently of contactDamage. apply_item_effects and place_item actions temporarily isolate all three native powers for their use window; canonical powers are restored before idle inventory discovery or on the next eligible active projection. A pure alternate recall does not mine even when its mobility effect is refused.",
        "item_tool",
        ("item_body",),
        {
            "pickPower": _p("integer", "Terraria Item.pick tooltip power percent", minimum=0, maximum=1000),
            "axePowerTooltipPercent": _p("integer", "Axe power as displayed in Terraria's tooltip; exact Item.axe internal value = this / 5", minimum=0, maximum=500, multiple_of=5, units="tooltip percent", wire_name="axePower", wire_divisor=5),
            "hammerPower": _p("integer", "Terraria Item.hammer tooltip power percent", minimum=0, maximum=1000),
            "miningSpeedMultiplier": _p("number", "Divides Player.pickSpeed (mining-time factor); >1 mines faster. Applies while held only when at least one of pickPower/axePowerTooltipPercent/hammerPower > 0 and abs(miningSpeedMultiplier - 1) > 0.001. Intentional all-zero powers remain valid but give no mining-speed effect; no tool power is inferred.", minimum=0.1, maximum=4, units="engine units: pickSpeed divisor", wire_name="miningSpeedScale"),
        },
        requirements=(
            RequirementSpec(
                kind="capability_present",
                capability="configure_item_use",
                target="item_body",
                message="A configured tool requires explicit item-use configuration; no use behavior is inferred.",
            ),
            RequirementSpec(
                kind="binding_tuple_present",
                target="any_entity",
                any_of=("primary_use|use_item_body", "primary_use|spawn_entity"),
                message="A configured tool requires one explicit primary-use root matching one listed binding transaction. Tool power remains on the item body; the action root is authored explicitly and no ownership is inferred.",
            ),
        ),
        component_slot="tool",
        py=_COMPILER_OWNER,
        cs="Common/Models/Runtime/GeneratedItemData.Apply.cs::ApplyToItem",
        wire=("gameplay.pickPower", "gameplay.axePower", "gameplay.hammerPower", "gameplay.miningSpeedScale"),
        lowering=("gameplay.pickPower", "gameplay.axePower", "gameplay.hammerPower", "gameplay.miningSpeedScale"),
    ),
    *(
        _cap(
            "configure_" + layer + "_placement", "Select one exact loaded " + layer + " and placement style for one referenced placement transaction."
            + (" Supported native containers keep Terraria inventory, opening and persistence; generated-item identity and return remain with this same placement. Unsupported custom callback families are refused." if layer == "tile" else ""),
            "item_placeable", ("item_body",),
            {layer + "Id": _p("integer", "Exact loaded " + layer + " ID; copy from parent facts, do not guess", minimum=0, maximum=65535, semantic_type="loaded_" + layer + "_id"),
             "placeStyle": _p("integer", "Exact Item.placeStyle for the selected loaded placement", minimum=0, maximum=255)},
            py=_COMPILER_OWNER, cs="Common/Models/Runtime/GeneratedItemData.Apply.cs::ApplyToItem",
            component_slot="placeable",
            exclusive_group="placeable",
            wire=tuple("runtimeProgram.bindings[].usePolicy.action.placement." + name
                       for name in ("tileId", "wallId", "placeStyle")),
            fixed_wire_literals={inactive + "Id": -1},
        ) for layer, inactive in (("tile", "wall"), ("wall", "tile"))
    ),
    _cap(
        "present_placed_item_sprite",
        "Explicit persistent static presentation of the same item_body's existing full-frame root PNG over one exact native tile placement. Replaces all native body/flame pictures: native animation and on/off visual states do not survive in this single PNG; baked flames stay static and visible when the native tile is switched off. To retain native animation/state pictures omit this call. Independently opt-in enable_placed_vfx can later support separate live effects selected by placementBindingId; it does not animate this root PNG or restore native flame pictures. No new image project or source choice. Native tile support, solidity, mining, wiring, interactions and light remain unchanged; a two-headed sprite does not create two mechanical lights. Absent call retains native presentation and adds no wire member. Requires an exact bounded native footprint (16x16/256 cells max) from configure_tile_placement. Container behavior belongs to that native placement, not this presentation call.",
        "item_placed_body",
        ("item_body",),
        {
            "placementCallId": _p("string", "Exact same-item configure_tile_placement call executed by a place_item binding; wall placements cannot carry this presentation", pattern=r"^[a-z][a-z0-9_]{0,47}$", reference=ReferenceSpec("call", ("item_body",)), wire_name="placedBody"),
            "renderSizePx": _p("integer", "Longest side of the final full PNG frame in world pixels; aspect preserved, independent of item scale, dropped worldScale and Visual renderSizePx", minimum=1, maximum=512, units="world pixels"),
            "footprintAnchorX": _p("number", "Normalized committed footprint rectangle X: 0 left, 1 right", minimum=0, maximum=1),
            "footprintAnchorY": _p("number", "Normalized committed footprint rectangle Y: 0 top, 1 bottom", minimum=0, maximum=1),
            "pivotSpace": _p("string", "Pivot basis only: frame (also omission) preserves full delivered PNG padding; alpha_bounds maps imagePivotX/Y inside the nonzero-alpha bounding rectangle of the final selected PNG, using pixel edges. For deliberate visible bottom contact choose alpha_bounds with imagePivotY=1; frame remains legal for intentional padding. Unknown or empty alpha bounds refuse the custom body draw. Whole PNG stays uncropped and renderSizePx/rotation/flips/offsets are unchanged; never infer this choice from names or parents", enum=("frame", "alpha_bounds"), required=False, default="frame", neutral="frame"),
            "imagePivotX": _p("number", "Normalized X inside the selected pivotSpace rectangle, not held grip", minimum=0, maximum=1),
            "imagePivotY": _p("number", "Normalized Y inside the selected pivotSpace rectangle: 0 top pixel edge, 1 bottom pixel edge", minimum=0, maximum=1),
            "offsetXPx": _p("integer", "World-axis offset; positive right", minimum=-512, maximum=512, units="world pixels"),
            "offsetYPx": _p("integer", "World-axis offset; positive down", minimum=-512, maximum=512, units="world pixels"),
            "rotationDegrees": _p("number", "Clockwise bitmap rotation in y-down world axes; no inferred forward-axis correction", minimum=-180, maximum=180, units="degrees"),
            "flipX": _p("boolean", "Reflect image horizontally about its pivot before rotation"),
            "flipY": _p("boolean", "Reflect image vertically about its pivot before rotation"),
        },
        component_slot="placed_body",
        multiplicity="per_placement_reference",
        py=_COMPILER_OWNER,
        cs="Common/Models/Contracts/RuntimeProgramSpec.cs::Validate",
        lowering=("runtimeProgram.bindings[].usePolicy.action.placement.placedBody",),
        lowering_inputs=("runtimeProgram.calls[].fn", "runtimeProgram.calls[].target",
                         "runtimeProgram.calls[].params.placementCallId",
                         "runtimeProgram.bindings[].action.kind",
                         "runtimeProgram.bindings[].action.targetId",
                         "runtimeProgram.bindings[].action.placementCallId"),
    ),
    _cap(
        "add_placed_light",
        "Add independent persistent light at the center tile of one exact committed native tile footprint. Explicit strength and color; no held/projectile light, PNG dependency or inferred emitter count. Absent call adds no light. Native tile light and interactions remain unchanged. Requires an exact bounded native footprint (16x16/256 cells max) from configure_tile_placement. Container behavior belongs to that native placement, not this light call.",
        "item_placed_body", ("item_body",),
        {
            "placementCallId": _p("string", "Exact same-item configure_tile_placement call executed by a place_item binding; no walls or unused placement", pattern=r"^[a-z][a-z0-9_]{0,47}$", reference=ReferenceSpec("call", ("item_body",)), wire_name="placedLight"),
            "strength": _p("number", "RGB coefficient multiplying the explicit color, not tile radius", minimum=0.01, maximum=1.5, units="engine units: RGB coefficient", consumer_storage="float64", execution_phase="PostUpdateEverything: persistent committed placement light; final native RGB converts to float32"),
            "color": _p("string", "Canonical light color", enum=_COLOR, execution_phase="PostUpdateEverything: persistent committed placement light"),
        },
        component_slot="placed_light",
        authority_by_effect={"placement": "owner_request_server_execute", "light": "client_visual_only"},
        multiplicity="per_placement_reference", py=_COMPILER_OWNER,
        cs="Common/Systems/Placement/GeneratedPlacementLedgerSystem.PlacedLight.cs::TryGetPlacedLight",
        lowering=("runtimeProgram.bindings[].usePolicy.action.placement.placedLight",),
        lowering_inputs=("runtimeProgram.calls[].fn", "runtimeProgram.calls[].target",
                         "runtimeProgram.calls[].params.placementCallId", "runtimeProgram.bindings[].action.kind",
                         "runtimeProgram.bindings[].action.targetId", "runtimeProgram.bindings[].action.placementCallId"),
    ),
    _cap(
        "enable_placed_vfx",
        "Opt in to independent live placed VFX slots on one exact committed native tile footprint, not held-item effects. Bounds consume actual top-left native TileFrameY inclusively, not animation time/count: 0..32767 selects all nonnegative frames. Native state facts are read-only; never infer a gate from names. VFX Director later selects this placement binding for periodic self spriteElement/libraryParticle/lightCue. Same item root PNG remains stable physical art; existing independent VFX assets can animate separate flames without rotating/pulsing the whole root. No effects/defaults are inserted. Requires an exact bounded native footprint (16x16/256 cells max) from configure_tile_placement. Does not change its native container behavior, material ownership or returns.",
        "item_placed_body", ("item_body",),
        {
            "placementCallId": _p("string", "Exact same-item configure_tile_placement call executed by a place_item binding; no walls or unused placement", pattern=r"^[a-z][a-z0-9_]{0,47}$", reference=ReferenceSpec("call", ("item_body",)), wire_name="placedVfx"),
            "minFrameY": _p("integer", "Inclusive actual top-left native TileFrameY lower bound, not animation age", minimum=0, maximum=32767, units="native frame coordinate", execution_phase="PostUpdateEverything: authenticated placed source gate"),
            "maxFrameY": _p("integer", "Inclusive actual top-left native TileFrameY upper bound", minimum=0, maximum=32767, units="native frame coordinate", execution_phase="PostUpdateEverything: authenticated placed source gate"),
        },
        component_slot="placed_vfx",
        requirements=(RequirementSpec("ordered_params", param="minFrameY", other_param="maxFrameY", message="minFrameY must not exceed maxFrameY."),),
        authority_by_effect={"placement": "owner_request_server_execute", "vfx": "client_visual_only"},
        multiplicity="per_placement_reference", py=_COMPILER_OWNER,
        cs="Common/Systems/Placement/GeneratedPlacementLedgerSystem.PlacedVfx.cs::TryGetPlacedVfxFrame",
        lowering=("runtimeProgram.bindings[].usePolicy.action.placement.placedVfx",),
        lowering_inputs=("runtimeProgram.calls[].fn", "runtimeProgram.calls[].target",
                         "runtimeProgram.calls[].params.placementCallId", "runtimeProgram.bindings[].action.kind",
                         "runtimeProgram.bindings[].action.targetId", "runtimeProgram.bindings[].action.placementCallId"),
    ),
    _cap(
        "require_use_condition",
        "Gate one active input; one condition per input. Omit for unrestricted use.",
        "item",
        ("item_body",),
        {
            "input": _p("string", "Existing active input", enum=("primary_use", "alternate_use")),
            "condition": _p("union", "One condition; thresholds include equality.", alternatives=(
                _p("string", "Player is grounded", enum=("grounded",), wire_literals={"useConditionMode": "grounded"}),
                _p("string", "Player is not wet", enum=("not_wet",), wire_literals={"useConditionMode": "not_wet"}),
                _p("object", "Player.statLife >= the authored life threshold", properties={"lifeAtLeast": _p("integer", "Inclusive life threshold", minimum=0, maximum=1000, wire_name="useConditionMinLife")}, wire_literals={"useConditionMode": "life_above"}),
                _p("object", "Player.statMana >= the authored mana threshold", properties={"manaAtLeast": _p("integer", "Inclusive mana threshold", minimum=0, maximum=1000, wire_name="useConditionMinMana")}, wire_literals={"useConditionMode": "mana_above"}),
            )),
        },
        component_slot="use_condition",
        multiplicity="many_per_target",
        py=_COMPILER_OWNER,
        cs="Content/Items/GeneratedItem.Use.cs::UseBlockedReason",
        wire=("gameplay.useConditions[].input", "gameplay.useConditions[].useConditionMode", "gameplay.useConditions[].useConditionMinLife", "gameplay.useConditions[].useConditionMinMana"),
        lowering=("gameplay.useConditions[].input", "gameplay.useConditions[].useConditionMode", "gameplay.useConditions[].useConditionMinLife", "gameplay.useConditions[].useConditionMinMana"),
    ),
    _cap(
        "add_hold_light",
        "Emit bounded light while the item is held.",
        "item_utility",
        ("item_body",),
        {
            "strength": _p("number", "Client light RGB coefficient multiplying selected color (not a tile radius)", minimum=0.01, maximum=1.5, wire_name="holdLightStrength", units="engine units: RGB coefficient"),
            "color": _p("string", "Canonical light color", enum=_COLOR, wire_name="holdLightColorName"),
        },
        component_slot="held_light",
        authority="client_visual_only",
        py=_COMPILER_OWNER,
        cs="Content/Items/GeneratedItem.Use.cs::HoldItem",
        wire=("gameplay.holdLightStrength", "gameplay.holdLightColorName"),
        lowering=("gameplay.holdLightStrength", "gameplay.holdLightColorName"),
    ),
    _cap(
        "move_player_on_use",
        "Run a bounded blink-to-cursor action on successful use; home recall has its own operation with no inactive blink fields.",
        "item_utility",
        ("item_body",),
        {
            "mode": _p("string", "Mobility executor", enum=("blink_to_cursor",), wire_name="mobilityMode"),
            "rangeTiles": _p("integer", "Maximum blink range", minimum=0, maximum=120, units="tiles", wire_name="mobilityRangeTiles"),
            "cooldownSeconds": _seconds(_p("integer", "Cooldown", minimum=0, maximum=3600, units="ticks", wire_name="mobilityCooldownTicks"), "cooldownTicks"),
            "safeTileOnly": _p("boolean", "Blink bounds, solid-tile overlap and nearby lava checks; false skips them; ignored for recall_home; not a general hazard check", wire_name="mobilitySafeTileOnly"),
        },
        component_slot="item_mobility",
        authority="owner_execute_sync",
        exclusive_group="item_mobility",
        py=_COMPILER_OWNER,
        cs="Content/Items/GeneratedItem.Use.cs::ApplyItemEffects",
        wire=(
            "gameplay.mobilityMode",
            "gameplay.mobilityRangeTiles",
            "gameplay.mobilityCooldownTicks",
            "gameplay.mobilitySafeTileOnly",
        ),
        lowering=("gameplay.mobilityMode", "gameplay.mobilityRangeTiles", "gameplay.mobilityCooldownTicks", "gameplay.mobilitySafeTileOnly"),
        effect_groupable=True,
    ),
    _cap(
        "recall_home_on_use", "Recall the owner home after a successful apply_item_effects use. The player mobility cooldown is shared with blink actions.",
        "item_utility", ("item_body",),
        {"cooldownSeconds": _seconds(_p("integer", "Shared player mobility cooldown after success", minimum=0, maximum=3600, units="ticks", wire_name="mobilityCooldownTicks"), "cooldownTicks")},
        component_slot="item_mobility",
        authority="owner_execute_sync",
        exclusive_group="item_mobility",
        py=_COMPILER_OWNER, cs="Content/Items/GeneratedItem.Use.cs::ApplyItemEffects",
        wire=(
            "gameplay.mobilityMode",
            "gameplay.mobilityRangeTiles",
            "gameplay.mobilityCooldownTicks",
            "gameplay.mobilitySafeTileOnly",
        ),
        fixed_wire_literals={"mobilityMode": "recall_home", "mobilityRangeTiles": 0, "mobilitySafeTileOnly": False},
        effect_groupable=True,
    ),
    _cap(
        "configure_accessory",
        "Apply independently chosen passive equipment effects; numeric bonuses use explicit units.",
        "equipment",
        ("item_body",),
        _ACCESSORY_PRIMITIVES,
        component_slot="accessory",
        authority="owner_execute_sync",
        py=_COMPILER_OWNER,
        cs="Content/Items/GeneratedItem.Equipment.cs::UpdateAccessory",
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
        requirements=(RequirementSpec(
            kind="nonneutral_params_require_param",
            param="setKey",
            nonzero_params=("setBonuses",),
            message="A three-piece armor set bonus needs an explicit non-empty setKey shared by head, body and legs.",
        ), RequirementSpec(
            kind="nonneutral_params_require_exact_param", param="slot", equals="head",
            nonzero_params=("setBonuses",),
            message="Only the head piece executes an armor set bonus once a matching head, body and legs are equipped.",
        ), RequirementSpec(
            kind="positive_param_requires_param", param="lightColor",
            nonzero_params=("lightStrength",),
            message="Positive equipped light requires explicit lightColor; no hidden white fallback.",
        )),
        component_slot="armor",
        authority="owner_execute_sync",
        py=_COMPILER_OWNER,
        cs="Content/Items/GeneratedItem.Equipment.cs::UpdateEquip",
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
            "bonusPercent": _p("number", "Add this percent to the selected class damage additive modifier; 15 means +15%", minimum=-90, maximum=300, units="additive_percent", semantic_type="additive_percent", wire_divisor=100, neutral=0, consumer_storage="float32", execution_phase="UpdateAccessory/UpdateEquip or UpdateArmorSet according to authored phase"),
        },
        requirements=(RequirementSpec(
            "capability_group_present", target="item_body", any_of=("configure_accessory", "configure_armor"),
            message="Equipment class damage requires exactly one explicit accessory or armor configuration on the same item.",
        ),),
        component_slot="equipment_class_damage",
        authority="owner_execute_sync",
        multiplicity="many_per_target",
        py=_COMPILER_OWNER,
        cs="Content/Items/GeneratedItem.Equipment.cs::UpdateAccessory/UpdateEquip/UpdateArmorSet",
    ),
    _cap(
        "configure_spawn",
        "Set this entity spawn cardinality per activation, initial direction and position; cardinality is separate from the optional set_projectile_concurrency live cap, not a singleton guarantee. Does not choose movement or damage.",
        "entity_spawn",
        PROJECTILE_ENTITY_KINDS,
        {
            "velocity": _spawn_velocity(),
            "count": _p("integer", "Default root binding spawn count per activation, not live concurrency; event actions and target_and_fire select their own counts. Select set_projectile_concurrency separately only when an explicit live cap is intended. May be omitted only for child_projectile, whose producers override it", minimum=1, maximum=12, required=False, default=1, neutral=1, omission_condition=OmissionCondition(target_kinds=("child_projectile",))),
            "spreadRadians": _p("number", "Total angular spread. May be omitted only for child_projectile, whose producers override it", minimum=0, maximum=6.283185307179586, units="radians", required=False, default=0, neutral=0, omission_condition=OmissionCondition(target_kinds=("child_projectile",))),
            "offsetBlocks": _world_units(_p("integer", "Forward spawn offset", minimum=-128, maximum=256, units="pixels"), "offsetPx", multiplier=16, divisor=1, updates_power=0, units='blocks'),
            "aim": _p("string", "Initial aim axis and forward offset: facing uses current owner.direction on the horizontal axis; velocity uses the producer-supplied gameplay axis; cursor uses MouseWorld minus the shifted spawn position. These are not the visible sprite's rotation. radial/disk sample their own directions. none is zero velocity for constant speed.", enum=("cursor", "facing", "velocity", "none")),
            "position": _spawn_position_param(),
        },
        component_slot="spawn",
        authority="owner_execute_sync",
        py=_COMPILER_OWNER,
        cs="Content/Projectiles/GeneratedProjectile.cs::SpawnRuntimeEntity/Configure",
    ),
    _cap(
        "set_projectile_concurrency",
        ("Explicit opt-in concurrency cap: count live projectiles for the same owner + generated item ID + exact entity ID, "
         "across all producers regardless of root/child, binding or input; pending scheduler entries are not live. "
         "The requested effective batch is admitted all-or-nothing when enough slots remain, otherwise refused; no clipping "
         "by this cap of the effective batch after existing global/depth/event-budget limits. count is per activation; concurrency is separate. Select maxActive=1 for one returned physical "
         "copy, or deliberately choose a larger positive cap. Same-ID different inventory copies and an alternate binding "
         "to the same entity share the cap. This does not override existing producer semantics: the owner-attached "
         "active-use singleton remains, and hold maintains one existing batch; maxActive>1 does not bypass repeat-use "
         "singleton or make hold refill to this cap. First-batch count retains its existing meaning. Late spawn refusal "
         "does not roll back other activation events or native item/mana costs. Capability absence adds no admission cap; no neutral/default "
         "is materialized, no name/category/movement routing and no other mechanic is selected."),
        "entity_spawn",
        PROJECTILE_ENTITY_KINDS,
        {"maxActive": _p("integer", "Maximum live projectiles for this owner, generated item ID and exact entity ID", minimum=1, maximum=96, units="live projectiles")},
        component_slot="spawn",
        authority="owner_execute_sync",
        py=_COMPILER_OWNER,
        cs="Content/Projectiles/GeneratedProjectile.cs::SpawnRuntimeEntity",
    ),
    _cap(
        "set_projectile_sentry",
        "Explicitly choose Projectile.sentry registration for this entity. enabled=true participates in the owner's native maxTurrets cap; Player.UpdateMaxTurrets runs immediately after each successful native sentry spawn and may retire the oldest sentry. Active item bindings project Item.sentry from their exact target. Lifetime, position, damage, collision, targeting and child budget remain separate authored choices; native sentry does not imply stationary movement or choose a weapon family. Omission preserves prior non-sentry behaviour.",
        "entity_lifecycle", PROJECTILE_ENTITY_KINDS,
        {"enabled": _p("boolean", "Native Projectile.sentry flag; false explicitly disables registration", wire_name="nativeSentry")},
        component_slot="native_sentry",
        authority="owner_execute_sync",
        py=_COMPILER_OWNER, cs="Content/Projectiles/GeneratedProjectile.cs::Configure|Content/Items/GeneratedItem.Use.cs::ApplyActiveUseProjection",
        wire=("runtimeProgram.entities[].nativeSentry",),
    ),
    _cap(
        "set_descendant_concurrency",
        "Explicitly bound pending spawn reservations plus live descendants of each physical source projectile. A free root binding gets its own replenishable descendant pool instead of the monotonic activation event ledger; the root itself is excluded. A nested source adds this cap while retaining every ancestor pool and any ancestor lifetime ledger. All descendant event/controller producers share that ancestry; death or retirement releases only concurrent occupancy, never restores a lifetime allowance. Failed or cancelled spawns refund their reservation. Independent roots have independent pools; global owner/depth/entity caps remain. Absence retains the existing lifetime budget, with no fresh capacity created by network hydration.",
        "entity_spawn", PROJECTILE_ENTITY_KINDS,
        {"maxActive": _p("integer", "Maximum simultaneous pending reservations plus live descendants for this physical source and its nested descendants", minimum=1, maximum=96, units="pending or live descendants", wire_name="descendantMaxActive")},
        component_slot="spawn",
        authority="owner_execute_sync",
        py=_COMPILER_OWNER, cs="Content/Projectiles/GeneratedProjectile.cs::Configure|Common/Runtime/RuntimeSpawnBudget.cs::Reserve",
    ),
    _cap(
        "set_projectile_damage",
        "Enable contact damage with explicit class, damage and knockback.",
        "entity_combat",
        PROJECTILE_ENTITY_KINDS,
        {
            "damageClass": _p("string", "Exact built-in token or loaded tModLoader DamageClass.FullName copied only from parent damageClass facts (not item FullName)", pattern=_DAMAGE_CLASS_PATTERN, semantic_type="terraria_damage_class"),
            "damage": _p("integer", "Projectile base damage", minimum=0, maximum=2000),
            "knockback": _p("number", "Projectile.knockBack engine strength, not pixels or damage", minimum=0, maximum=20, units="engine units: Projectile.knockBack"),
            "ownerHitCheck": _p("boolean", "Require owner line/held hit check"),
        },
        component_slot="damage",
        authority="owner_execute_sync",
        emitted_events=("on_hit", "on_crit"),
        meaningful_for_stationary=True,
        py=_COMPILER_OWNER,
        cs="Content/Projectiles/GeneratedProjectile.cs::Configure",
    ),
    _cap(
        "set_projectile_lifetime",
        "Set exact bounded entity lifetime.",
        "entity_lifecycle",
        PROJECTILE_ENTITY_KINDS,
        {"lifetimeSeconds": _seconds(_p("integer", "Lifetime", minimum=1, maximum=36000, units="ticks"), "lifetimeTicks")},
        component_slot="lifetime",
        authority="owner_execute_sync",
        py=_COMPILER_OWNER,
        cs="Content/Projectiles/GeneratedProjectile.cs::Configure",
        wire=("runtimeProgram.entities[].lifetimeTicks",),
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
        component_slot="hitbox",
        authority="owner_execute_sync",
        py=_COMPILER_OWNER,
        cs="Content/Projectiles/GeneratedProjectile.cs::Configure",
    ),
    _cap(
        "set_projectile_hitbox_curve",
        "Scale the native rectangular damage hitbox along an explicit active-age curve, independently of sprite/VFX size. Start/end are multipliers on set_projectile_hitbox.hitboxScale. Active world ticks begin after spawn activation delay; extraUpdates changes sample frequency, not duration. Optional visual coupling is an explicit mirrorToSprite choice. Beam and whip line geometry are excluded.",
        "entity_collision", PROJECTILE_ENTITY_KINDS,
        {
            "startScale": _p("number", "Damage-rectangle multiplier before/start of the curve", minimum=0.25, maximum=8, units="dimensionless multiplier", consumer_storage="float32"),
            "endScale": _p("number", "Damage-rectangle multiplier at/after curve completion", minimum=0.25, maximum=8, units="dimensionless multiplier", consumer_storage="float32"),
            "startDelaySeconds": _seconds(_p("integer", "Active world-time delay holding startScale before interpolation", minimum=0, maximum=21600, units="ticks"), "startDelayTicks"),
            "durationSeconds": _seconds(_p("integer", "World-time duration from startScale to endScale", minimum=1, maximum=21600, units="ticks"), "durationTicks"),
            "curve": _p("string", "linear: start+(end-start)*t; exponential: start*(end/start)^t; t clamps to 0..1", enum=("linear", "exponential")),
            "mirrorToSprite": _p("boolean", "True multiplies the authored base sprite scale by this same curve; false leaves visual growth independent. Never reads VFX scale for gameplay. Cannot combine true with move_expanding_wave, which independently owns dynamic sprite scale."),
        },
        requirements=(
            RequirementSpec("capability_present", capability="set_projectile_hitbox", message="A hitbox curve multiplies the same entity's explicit static hitbox."),
            RequirementSpec("capability_absent", any_of=("channel_beam", "move_whip_lash"), message="Rectangular hitbox curves cannot coexist with a beam/whip line-collision driver; choose the geometry explicitly."),
            RequirementSpec("capability_absent", param="mirrorToSprite", equals=True, any_of=("move_expanding_wave", "set_projectile_visual_scale_curve"), message="mirrorToSprite=true owns dynamic sprite scale; expanding-wave movement or a visual scale curve is a second owner. Disable the mirror or choose one scale owner."),
        ),
        component_slot="hitbox_curve",
        authority="owner_execute_sync",
        py=_COMPILER_OWNER, cs="Content/Projectiles/GeneratedProjectile.RuntimeEvents.cs::ModifyDamageHitbox|Content/Projectiles/GeneratedProjectile.Executors.cs::ApplyHitboxCurveVisual",
         wire_presence_path="runtimeProgram.entities[].hitboxCurve",
    ),
    _cap("set_projectile_vector_acceleration", 'Timed signed two-axis world acceleration, independent of the selected trajectory. Adds the authored vector after movement, turn and multiplicative speed, before absolute speed ramp and homing; zero axes are explicit. The compiler divides acceleration by the square of updatesPerTick so the same world-time phase gives the same world velocity change. It can launch a stationary zero-velocity projectile without inventing a direction.', "motion_modifier", ("free_projectile", "child_projectile"), {
            "accelerationXBlocksPerSecondSquared": _world_units(_p("number", "Signed horizontal acceleration; positive right", minimum=-2, maximum=2, units="pixels/update²", consumer_storage="float32", neutral=0), "accelerationX", multiplier=16, divisor=3600, updates_power=2, units="blocks/s²"),
            "accelerationYBlocksPerSecondSquared": _world_units(_p("number", "Signed vertical acceleration; positive down", minimum=-2, maximum=2, units="pixels/update²", consumer_storage="float32", neutral=0), "accelerationY", multiplier=16, divisor=3600, updates_power=2, units="blocks/s²"),
            "startDelaySeconds": _seconds(_p("integer", "Start after this active world-time delay; activation waiting is excluded", minimum=0, maximum=21600, units="ticks"), "startDelayTicks"),
            "durationSeconds": _seconds(_p("integer", "Active world-time duration", minimum=1, maximum=21600, units="ticks"), "durationTicks"),
        }, component_slot="vectorAcceleration", authority="owner_execute_sync", py=_COMPILER_OWNER,
        cs="Content/Projectiles/GeneratedProjectile.MotionComposition.cs::ApplyVectorAcceleration",
        wire_presence_path="runtimeProgram.entities[].vectorAcceleration"),
    _cap("set_projectile_speed_ramp", 'Absolute linear speed envelope over an authored active world-time interval. Unlike multiplicative speedModifier, speed at a given age is independent of prior magnitude and extraUpdates. After vector acceleration and before homing it preserves current heading and assigns a linearly interpolated start/end magnitude, reaching the endpoint on the last phase update. Outside the interval it releases velocity ownership. Zero velocity remains zero: this capability does not invent a launch direction. May compose with turn and targeting; a movement that replaces velocity each frame still receives the envelope in the fixed modifier pass.', "motion_modifier", ("free_projectile", "child_projectile"), {
            "startSpeedBlocksPerSecond": _world_units(_p("number", "Absolute speed at the beginning of the interval", minimum=0.1, maximum=80, units="pixels/update", consumer_storage="float32"), "startSpeed", multiplier=16, divisor=60, updates_power=1, units="blocks/s"),
            "endSpeedBlocksPerSecond": _world_units(_p("number", "Absolute endpoint speed; zero stops on the last phase update", minimum=0, maximum=80, units="pixels/update", consumer_storage="float32", neutral=0), "endSpeed", multiplier=16, divisor=60, updates_power=1, units="blocks/s"),
            "startDelaySeconds": _seconds(_p("integer", "Start after this active world-time delay; activation waiting is excluded", minimum=0, maximum=21600, units="ticks"), "startDelayTicks"),
            "durationSeconds": _seconds(_p("integer", "Active world-time duration", minimum=1, maximum=21600, units="ticks"), "durationTicks"),
        }, component_slot="speedRamp", authority="owner_execute_sync", py=_COMPILER_OWNER,
        cs="Content/Projectiles/GeneratedProjectile.MotionComposition.cs::ApplySpeedRamp",
        wire_presence_path="runtimeProgram.entities[].speedRamp"),
    _cap(
        "set_projectile_turn_modifier",
        "After the explicit movement driver, rotate velocity during an authored active-age phase. Fixed modifier order is turn, multiplicative speed, vector acceleration, absolute speed ramp, then homing. This is independent of the single movement slot; it does not create a trajectory or choose another driver.",
        "motion_modifier", ("free_projectile", "child_projectile"),
        {
            "turnRadiansPerSecond": _world_units(_p("number", "Signed world-time velocity rotation rate during the active phase", minimum=-0.5, maximum=0.5, units="radians/projectile update", consumer_storage="float32", neutral=0), "turnRadiansPerUpdate", multiplier=1, divisor=60, updates_power=1, units='radians/s'),
            "startDelaySeconds": _seconds(_p("integer", "Begin phase after this active world-time delay; activation waiting is excluded", minimum=0, maximum=21600, units="ticks"), "startDelayTicks"),
            "durationSeconds": _seconds(_p("integer", "Phase duration in active world time; start inclusive and end exclusive at the beginning of each AI step", minimum=1, maximum=21600, units="ticks"), "durationTicks"),
        }, component_slot="turnModifier",
        authority="owner_execute_sync",
        py=_COMPILER_OWNER, cs="Content/Projectiles/GeneratedProjectile.Modifiers.cs::ApplyActiveModifiers",
         wire_presence_path="runtimeProgram.entities[].turnModifier",
    ),
    _cap(
        "set_projectile_speed_modifier",
        "After movement and turn, multiply velocity on each active projectile update and clamp its magnitude to the authored cap. Values below one slow; above one accelerate. Phase timing is in world ticks, while the multiplier is explicitly per projectile update.",
        "motion_modifier", ("free_projectile", "child_projectile"),
        {
            "speedMultiplierPerUpdate": _p("number", "Velocity multiplier per active projectile update", minimum=0.8, maximum=1.2, units="dimensionless multiplier/update", consumer_storage="float32", neutral=1),
            "maxSpeedBlocksPerSecond": _world_units(_p("number", "Inclusive magnitude cap applied after the multiplication", minimum=0.1, maximum=80, units="pixels/projectile update", consumer_storage="float32"), "maxSpeed", multiplier=16, divisor=60, updates_power=1, units='blocks/s'),
            "startDelaySeconds": _seconds(_p("integer", "Begin phase after this active world-time delay; activation waiting is excluded", minimum=0, maximum=21600, units="ticks"), "startDelayTicks"),
            "durationSeconds": _seconds(_p("integer", "Phase duration in active world time; start inclusive and end exclusive at the beginning of each AI step", minimum=1, maximum=21600, units="ticks"), "durationTicks"),
        }, component_slot="speedModifier",
        authority="owner_execute_sync",
        py=_COMPILER_OWNER, cs="Content/Projectiles/GeneratedProjectile.Modifiers.cs::ApplyActiveModifiers",
         wire_presence_path="runtimeProgram.entities[].speedModifier",
    ),
    _cap(
        "set_projectile_homing_modifier",
        "After movement, turn, multiplicative speed, vector acceleration and absolute speed ramp, steer toward the nearest chaseable NPC within the hard radius, preserving current speed. Owner selects the target and synchronizes velocity. Equal distances use NPC index. Zero velocity stays zero; no target means no steering.",
        "motion_modifier", ("free_projectile", "child_projectile"),
        {
            "rangeTiles": _p("number", "Hard target radius from this projectile center", minimum=1, maximum=120, units="tiles", consumer_storage="float32"),
            "maxTurnRadiansPerSecond": _world_units(_p("number", "Maximum angular turn rate toward the target; each update integrates its elapsed world time and stops at full alignment", minimum=0.0001, maximum=3.2, units="radians/projectile update", consumer_storage="float32"), "maxTurnRadiansPerUpdate", multiplier=1, divisor=60, updates_power=1, units='radians/s'),
            "requireLineOfSight": _p("boolean", "Require native CanHitLine from projectile box to candidate box before selecting it"),
            "startDelaySeconds": _seconds(_p("integer", "Begin phase after this active world-time delay; activation waiting is excluded", minimum=0, maximum=21600, units="ticks"), "startDelayTicks"),
            "durationSeconds": _seconds(_p("integer", "Phase duration in active world time; start inclusive and end exclusive at the beginning of each AI step", minimum=1, maximum=21600, units="ticks"), "durationTicks"),
        }, component_slot="homingModifier",
        authority="owner_execute_sync",
        py=_COMPILER_OWNER, cs="Content/Projectiles/GeneratedProjectile.Modifiers.cs::ApplyHomingModifier",
         wire_presence_path="runtimeProgram.entities[].homingModifier",
        budget="one bounded native NPC-array scan per active projectile update",
    ),
    _cap(
        "attract_npcs_while_active",
        "Independent server NPC attraction every active projectile update, after movement/modifiers, without changing projectile velocity or selecting a movement family. Scan NPC slots in index order, require chaseable positive-resistance targets within hard range, then apply at most maxTargets. Uses native resistance clamped 0.1..1. No periodic event clock or owner hit callback is substituted.",
        "active_effect", PROJECTILE_ENTITY_KINDS,
        {
            "rangeTiles": _p("number", "Hard pull radius from projectile center", minimum=1, maximum=80, units="tiles", consumer_storage="float32"),
            "accelerationBlocksPerSecondSquared": _world_units(_p("number", "World acceleration of NPC velocity before falloff and resistance, integrated over the active projectile clock", minimum=0.001, maximum=4, units="NPC velocity units/projectile update", consumer_storage="float32"), "strengthPerUpdate", multiplier=16, divisor=3600, updates_power=1, units='blocks/s² (NPC world-tick velocity)'),
            "falloff": _p("string", "constant=1; linear=max(0,1-distance/radius), including zero at radius", enum=("constant", "linear")),
            "maxTargets": _p("integer", "Maximum accepted NPC slots per projectile update", minimum=1, maximum=16),
            "startDelaySeconds": _seconds(_p("integer", "Begin phase after this active world-time delay; activation waiting is excluded", minimum=0, maximum=21600, units="ticks"), "startDelayTicks"),
            "durationSeconds": _seconds(_p("integer", "Phase duration in active world time; start inclusive and end exclusive at the beginning of each AI step", minimum=1, maximum=21600, units="ticks"), "durationTicks"),
        }, component_slot="npcAttraction",
        authority="server_execute",
        meaningful_for_stationary=True,
        py=_COMPILER_OWNER, cs="Content/Projectiles/GeneratedProjectile.Modifiers.cs::ApplyNpcAttraction",
         wire_presence_path="runtimeProgram.entities[].npcAttraction",
        budget="one bounded native NPC-array scan, at most authored 1..16 targets/update",
    ),
    _cap(
        "set_projectile_visual_scale_curve",
        "Set sprite/generic body scale to authored drawScale times visual.scale times an independent time curve. Linear or exponential interpolation uses active world ticks. This does not change damage or tile collision. Beam/whip line drivers are excluded because their exact body geometry uses collision dimensions. A separate gameplay hitbox curve can coexist only with its mirrorToSprite=false; no_asset still deliberately hides the body.",
        "entity_visual", PROJECTILE_ENTITY_KINDS,
        {
            "startScale": _p("number", "Visual multiplier before/start of the curve", minimum=0.25, maximum=8, units="dimensionless multiplier", consumer_storage="float32"),
            "endScale": _p("number", "Visual multiplier at/after curve completion", minimum=0.25, maximum=8, units="dimensionless multiplier", consumer_storage="float32"),
            "startDelaySeconds": _seconds(_p("integer", "Active world-time delay holding startScale", minimum=0, maximum=21600, units="ticks"), "startDelayTicks"),
            "durationSeconds": _seconds(_p("integer", "World-time duration from startScale to endScale", minimum=1, maximum=21600, units="ticks"), "durationTicks"),
            "curve": _p("string", "linear=start+(end-start)*t; exponential=start*(end/start)^t; t clamped 0..1", enum=("linear", "exponential")),
        }, requirements=(RequirementSpec("capability_absent", any_of=("move_expanding_wave", "channel_beam", "move_whip_lash"), message="A visual scale curve excludes another scale owner and special beam/whip line geometry that does not consume sprite scale."),),
           component_slot="visualScaleCurve",
        authority="client_visual_only",
        py=_COMPILER_OWNER, cs="Content/Projectiles/GeneratedProjectile.Modifiers.cs::ApplyVisualScaleCurve",
         wire_presence_path="runtimeProgram.entities[].visualScaleCurve",
    ),
    _cap(
        "orient_whip_to_owner_gravity",
        "Mirror the existing whip sweep and bend around its explicitly aimed axis when owner.gravDir is inverted. Does not change authored aim, range or damage; collision and body use the same whip points. Choosing this fn supplies the sole true wire marker.",
        "entity_collision", ("owner_attached_projectile",), {},
        requirements=(RequirementSpec("capability_present", capability="move_whip_lash", message="Owner-gravity orientation requires the same entity's explicit whip geometry."),
                RequirementSpec("capability_absent", any_of=("channel_beam",), message="Beam geometry takes precedence and would leave whip gravity orientation unconsumed.")),
        component_slot="whip_gravity",
        authority="owner_execute_sync",
        py=_COMPILER_OWNER, cs="Content/Projectiles/GeneratedProjectile.Executors.cs::BuildWhipPoints",
        wire=("runtimeProgram.entities[].whipUsesOwnerGravity",),
        lowering=("runtimeProgram.entities[].whipUsesOwnerGravity",), lowering_inputs=("runtimeProgram.calls[].fn",),
        fixed_wire_literals={"whipUsesOwnerGravity": True}, wire_presence_path="runtimeProgram.entities[].whipUsesOwnerGravity",
    ),
    _cap(
        "set_projectile_collision",
        "Set exact Terraria tile/liquid collision, penetration, update rate and NPC immunity mode.",
        "entity_collision",
        PROJECTILE_ENTITY_KINDS,
        {
            "tileCollide": _p("boolean", "Collide with solid tiles"),
            "ignoreWater": _p("boolean", "Ignore Terraria liquid drag; false keeps vanilla water interaction"),
            "bounceCount": _p("integer", "bounceCount=N reflects N tile contacts using bounceSpeedRetention on collided-axis velocity (each collided axis reverses); the next contact kills. move_boomerang, move_returning_glaive and move_flail_tether instead start returning and disable tile collision before bounce/kill handling. Otherwise 0 kills on the first tile contact; this does not add horizontal friction between contacts", minimum=0, maximum=32, required=False, default=0, neutral=0, omission_condition=OmissionCondition(param_equals=(("tileCollide", False),), target_capabilities=("move_boomerang", "move_returning_glaive", "move_flail_tether"))),
            "bounceSpeedRetention": _p("number", "Multiply only each collided velocity axis after reflection; 1 preserves it, 0 stops that axis. Tangential speed is unchanged. No friction between contacts. Only used when tileCollide=true and bounceCount>0; return-on-wall drivers keep their separate return behavior", minimum=0, maximum=1, required=False, default=1, neutral=1, consumer_storage="float32"),
            "pierce": _p("integer", "Terraria Projectile.penetrate count: pierce=1 causes native kill after the first damaging NPC contact; pierce=-1 does not kill from NPC contact. on_hit has no implicit explosion; an on_kill effect is a separate authored event action, not implied by penetration or an explosive name", minimum=-1, maximum=100),
            "updatesPerTick": _p("integer", "Total Projectile AI/movement updates per world tick; does not rescale any per-update parameter", minimum=1, maximum=6, wire_offset=-1, wire_name="extraUpdates"),
            "immunity": _immunity_param(),
        },
        component_slot="collision",
        authority="owner_execute_sync",
        py=_COMPILER_OWNER,
        cs="Content/Projectiles/GeneratedProjectile.cs::Configure|Content/Projectiles/GeneratedProjectile.RuntimeEvents.cs::OnTileCollide",
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
    requirements: Iterable[RequirementSpec] = (),
) -> CapabilitySpec:
    return _cap(
        name,
        summary,
        "movement",
        targets,
        params or {},
        py=_COMPILER_OWNER,
        cs=cs,
        authority="owner_execute_sync",
        component_slot="movement",
        exclusive_group="movement",
        position_ownership="velocity_or_position_controller",
        lowering=("runtimeProgram.entities[].movement.code", "runtimeProgram.entities[].movement.params"),
        requirements=requirements,
    )


_CAPS.extend([
    _movement("move_spring_tether", 'A bounded tension-only spring between projectile and owner mounted center. Inside rest radius the tether is slack; outside it applies displacement-proportional inward acceleration. Exponential world-time damping applies to velocity everywhere; an explicit speed cap prevents runaway integration. Owner movement changes the anchor naturally. Invalid/dead owner ends the projectile. No channel requirement, target selection, teleport, forced collision change or return-to-owner kill. Composes with timed vector forces, speed envelopes and homing. Stiffness is s^-2 and damping is s^-1, lowered against the explicit projectile clock.', 21, {
        "restRadiusTiles": _p("number", "Slack radius around owner mounted center", minimum=0, maximum=80, units="tiles", consumer_storage="float32", wire_name="springRestRadius", neutral=0),
        "stiffnessPerSecondSquared": _world_units(_p("number", "Inward acceleration per pixel of stretch", minimum=0.000001, maximum=1, units="update^-2", consumer_storage="float32"), "springStiffness", multiplier=1, divisor=3600, updates_power=2, units="s^-2"),
        "dampingPerSecond": _world_units(_p("number", "Velocity decays by exp(-damping * elapsed seconds)", minimum=0, maximum=1, units="update^-1", consumer_storage="float32", neutral=0), "springDamping", multiplier=1, divisor=60, updates_power=1, units="s^-1"),
        "maxSpeedBlocksPerSecond": _world_units(_p("number", "Magnitude cap after spring and damping", minimum=0.1, maximum=80, units="pixels/update", consumer_storage="float32"), "springMaxSpeed", multiplier=16, divisor=60, updates_power=1, units="blocks/s"),
    }, targets=("free_projectile", "child_projectile"), cs="Content/Projectiles/GeneratedProjectile.SpringTether.cs::MoveSpringTether"),
    _movement("move_elliptic_orbit", 'Owner-relative ellipse with independently authored major/minor radii, explicit phase and signed angular speed. The ellipse X axis follows the synchronized initial launch direction, not world X or current cursor; orbit phase uses synchronized active age. Unlike circular move_orbit, non-equal radii and orientation shape a true ellipse and the author chooses initial phase rather than projectile identity. Sets velocity to the next owner-relative point for native integration, and disables tile collision. Normal lifetime applies; invalid/dead owner ends the projectile. Rotation remains tangent to actual velocity. World angular rate is invariant under extraUpdates.', 22, {
        "radiusAlongTiles": _p("number", "Ellipse semi-axis along initial direction", minimum=0.25, maximum=80, units="tiles", consumer_storage="float32", wire_name="ellipseRadiusAlong"),
        "radiusAcrossTiles": _p("number", "Ellipse semi-axis perpendicular to initial direction", minimum=0.25, maximum=80, units="tiles", consumer_storage="float32", wire_name="ellipseRadiusAcross"),
        "angularSpeedRadiansPerSecond": _world_units(_p("number", "Signed phase increment; zero follows owner at fixed phase", minimum=-0.5, maximum=0.5, units="radians/update", consumer_storage="float32", neutral=0), "ellipseAngularRate", multiplier=1, divisor=60, updates_power=1, units="radians/s"),
        "phaseRadians": _p("number", "Explicit starting phase; no identity-derived offset", minimum=-3.1415927, maximum=3.1415927, units="radians", consumer_storage="float32", wire_name="ellipsePhase", neutral=0),
    }, targets=("free_projectile", "child_projectile"), cs="Content/Projectiles/GeneratedProjectile.EllipticOrbit.cs::MoveEllipticOrbit", requirements=(RequirementSpec("item_capability_param", capability="configure_spawn", param="aim", any_of=("cursor", "facing", "velocity"), message="This trajectory requires an explicit synchronized launch axis; aim=none cannot invent one."),)),
    _movement("move_traveling_wave", 'A traveling sine displacement around the synchronized initial launch axis: constant authored forward speed plus the exact change of lateral sinusoidal offset across each active update. Amplitude is a world distance, frequency is cycles per second, and phase is explicit. Unlike sine_homing this never selects targets, rotates velocity cumulatively or depends on prior heading; its integrated lateral displacement is bounded by twice amplitude even across extraUpdates. Native integration/collision remains enabled; each next AI recomputes the trajectory velocity from active age. Modifiers may add independent deviations after this driver. Late hydration resumes the same differential step without snapping to a saved origin.', 23, {
        "forwardSpeedBlocksPerSecond": _world_units(_p("number", "Constant forward speed along initial direction", minimum=0.1, maximum=80, units="pixels/update", consumer_storage="float32"), "waveForwardSpeed", multiplier=16, divisor=60, updates_power=1, units="blocks/s"),
        "amplitudeTiles": _p("number", "Lateral sine amplitude; zero is explicitly straight", minimum=0, maximum=16, units="tiles", consumer_storage="float32", wire_name="waveDisplacementAmplitude", neutral=0),
        "frequencyCyclesPerSecond": _world_units(_p("number", "Oscillation frequency in world time", minimum=0.0001, maximum=1, units="radians/update", consumer_storage="float32"), "wavePhaseRate", multiplier=6.283185307179586, divisor=60, updates_power=1, units="cycles/s"),
        "phaseRadians": _p("number", "Starting oscillator phase; no initial lateral teleport", minimum=-3.1415927, maximum=3.1415927, units="radians", consumer_storage="float32", wire_name="waveStartPhase", neutral=0),
    }, targets=("free_projectile", "child_projectile"), cs="Content/Projectiles/GeneratedProjectile.TravelingWave.cs::MoveTravelingWave", requirements=(RequirementSpec("item_capability_param", capability="configure_spawn", param="aim", any_of=("cursor", "facing", "velocity"), message="This trajectory requires an explicit synchronized launch axis; aim=none cannot invent one."),)),
    _movement("move_straight", "Keep initial velocity: no gravity, no drag, no falling arc. The generated proxy never invokes native projectile AI merely because a source is an arrow or has aiStyle=1.", 0),
    _movement("move_slow_homing", "Steer gradually toward a valid NPC.", 1, {
        "rangeTiles": _p("number", "Target search radius", minimum=1, maximum=120, units="tiles"),
        "homingStrength": _p("number", "Per movement-update linear interpolation fraction toward target velocity", minimum=0.001, maximum=1, units="engine units: velocity lerp fraction"),
    }),
    _movement("move_gravity_arc", "Movement adds gravity as signed vertical acceleration per projectile update after activation, with no horizontal friction: negative accelerates upward, positive downward, zero preserves vertical velocity. Tile collision uses the separate bounceCount. No terminal-speed cap, rolling, resting or explosion is implied.", 2, {
        "accelerationYBlocksPerSecondSquared": _world_units(_p("number", "Signed world vertical acceleration after activation; Terraria Y increases downward. Lowered over the explicitly authored target clock. Explicit zero adds no acceleration; missing is invalid. Not displacement or a speed cap", minimum=-2, maximum=2, units="engine units: vertical velocity increment per update", wire_name="gravityPerTick", neutral=0, consumer_storage="float32"), "accelY", multiplier=16, divisor=3600, updates_power=2, units='blocks/s²'),
    }),
    _movement("move_drift", "Multiply velocity by authored retention per projectile update.", 3, {
        "velocityRetention": _p("number", "Multiply velocity each projectile update (updatesPerTick times per world tick); 1 preserves speed, below 1 slows, above 1 accelerates; not necessarily retention per 1/60 s", minimum=0.8, maximum=1.05, units="engine units: velocity multiplier per update"),
    }),
    _movement("move_orbit", "Orbit the owner at the authored radius and signed world-time angular rate, with an identity-based starting offset. Positive rotates clockwise on screen; negative counterclockwise; zero keeps the angle fixed while following the owner. Launch speed does not set orbit rate. This controller forces tileCollide=false.", 4, {
        "radiusTiles": _p("number", "Fixed orbit radius around the owner", minimum=1, maximum=80, units="tiles", wire_name="rangeTiles"),
        "turnRadiansPerSecond": _world_units(_p("number", "Signed orbit angular increment; positive clockwise, negative counterclockwise, zero fixed-angle owner following", minimum=-0.5, maximum=0.5, units="radians/projectile update", consumer_storage="float32", wire_name="orbitRadiansPerUpdate"), "orbitRadiansPerUpdate", multiplier=1, divisor=60, updates_power=1, units="radians/s"),
    }),
    _movement("move_boomerang", "Fly out, then return to owner. A wall collision starts return and disables tileCollide; does not kill or spend tile bounces. NPC penetration is authored separately.", 5, {
        "returnAfterSeconds": _seconds(_p("integer", "Outbound duration", minimum=1, maximum=600, units="ticks"), "returnAfterTicks"),
        "returnSpeedBlocksPerSecond": _world_units(_p("number", "Return speed", minimum=1, maximum=80, units="pixels/projectile update"), "returnSpeed", multiplier=16, divisor=60, updates_power=1, units='blocks/s'),
    }),
    _movement("move_sine_homing", "Combine sinusoidal drift with bounded homing.", 7, {
        "rangeTiles": _p("number", "Target search radius", minimum=1, maximum=120, units="tiles"),
        "homingStrength": _p("number", "Per movement-update linear interpolation fraction toward target velocity", minimum=0.001, maximum=1, units="engine units: velocity lerp fraction"),
        "waveVelocityCoefficient": _p("number", "Raw lateral velocity coefficient: sin(age×0.18) × waveVelocityCoefficient × 0.03 before velocity direction normalization; not displacement pixels", minimum=0, maximum=64, units="engine units: lateral velocity coefficient", wire_name="waveAmplitude"),
    }),
    _movement("move_phase", "Couple a sinusoidal velocity-direction wobble with reduced opacity. This does not itself disable tile collision; tile collision is controlled separately.", 8, {
        "phaseStrength": _p("number", "Per-update velocity rotation = sin(age×0.1) × strength × 0.01 radians AND alpha = int(80×strength); not collision phasing", minimum=0, maximum=1, units="engine units: coupled rotation/alpha coefficient"),
    }),
    _movement("move_accelerate", "Multiply speed up to an explicit cap.", 9, {
        "speedMultiplierPerUpdate": _p("number", "Velocity multiplier per projectile update until maxSpeed cap; 1 unchanged", minimum=1.0, maximum=1.2, wire_name="acceleration", units="engine units: velocity multiplier per update"),
        "maxSpeedBlocksPerSecond": _world_units(_p("number", "Speed cap", minimum=1, maximum=80, units="pixels/projectile update"), "maxSpeed", multiplier=16, divisor=60, updates_power=1, units='blocks/s'),
    }),
    _movement("move_spiral", "Rotate velocity by an authored angle per projectile update.", 10, {
        "turnRadiansPerSecond": _world_units(_p("number", "World-time angular velocity turn rate", minimum=-0.5, maximum=0.5, units="radians/update", wire_name="turnRadiansPerTick"), "turnRadiansPerUpdate", multiplier=1, divisor=60, updates_power=1, units='radians/s'),
    }),
    _movement("move_vortex_orb", "Pull nearby chaseable NPCs toward the projectile and multiply projectile velocity by 0.99 per projectile update. Pull respects knockback resistance and affects at most 16 NPCs per update.", 11, {
        "accelerationBlocksPerSecondSquared": _world_units(_p("number", "World acceleration toward the center, scaled by clamped NPC knockBackResist", minimum=0, maximum=4, units="engine units: NPC velocity impulse coefficient"), "pullStrength", multiplier=16, divisor=3600, updates_power=1, units='blocks/s² (NPC world-tick velocity)'),
        "rangeTiles": _p("number", "Pull radius", minimum=1, maximum=80, units="tiles"),
    }),
    _movement("move_blackhole_pull", "Pull nearby chaseable NPCs toward the projectile and multiply projectile velocity by 0.985 per projectile update. Pull respects knockback resistance and affects at most 16 NPCs per update.", 12, {
        "accelerationBlocksPerSecondSquared": _world_units(_p("number", "World acceleration toward the center, scaled by clamped NPC knockBackResist", minimum=0, maximum=4, units="engine units: NPC velocity impulse coefficient"), "pullStrength", multiplier=16, divisor=3600, updates_power=1, units='blocks/s² (NPC world-tick velocity)'),
        "rangeTiles": _p("number", "Pull radius", minimum=1, maximum=80, units="tiles"),
    }),
    _movement("move_proximity_missile", "Home; proximity inside triggerRadiusTiles triggers on_expire then on_kill and kills the missile. on_hit requires an actual hit, not mere proximity.", 13, {
        "rangeTiles": _p("number", "Detection/search radius", minimum=1, maximum=120, units="tiles"),
        "homingStrength": _p("number", "Per movement-update linear interpolation fraction toward target velocity", minimum=0.001, maximum=1, units="engine units: velocity lerp fraction"),
        "triggerRadiusTiles": _p("number", "Trigger radius on the exact 1/16-tile pixel lattice", minimum=0.25, maximum=32, multiple_of=1 / 16, wire_multiplier=16, wire_name="proximityRadiusPx", units="tiles"),
    }),
    _movement("move_returning_glaive", "Fly, spin and return to the owner.", 14, {
        "returnAfterSeconds": _seconds(_p("integer", "Outbound duration", minimum=1, maximum=600, units="ticks"), "returnAfterTicks"),
        "returnSpeedBlocksPerSecond": _world_units(_p("number", "Return speed", minimum=1, maximum=80, units="pixels/projectile update"), "returnSpeed", multiplier=16, divisor=60, updates_power=1, units='blocks/s'),
    }),
    _movement("move_expanding_wave", "Add to the projectile's visual scale, then clamp it to the authored cap. Collision size and damage do not grow with this scale; use an independent hitbox curve for growing contact geometry.", 15, {
        "scaleGrowthPerUpdate": _p("number", "Additive Projectile.scale delta per projectile update, capped by maxScale", minimum=0.001, maximum=0.5, wire_name="scalePerTick", units="engine units: scale increment per update"),
        "maxScale": _p("number", "Projectile.scale cap (not a pixel radius)", minimum=0.25, maximum=4),
    }),
    _movement("move_flail_tether", "Tether to owner; outbound flight ends at the leash or when owner.channel becomes false, then return is latched. An active spawn root requires configure_item_use.channel=true: native StartChanneling(Item) otherwise leaves an idle owner unchannelled and return begins on the first AI. Passive/event-driven copies only observe the owner channel established by another active source; this controller does not start channeling.", 16, {
        "rangeTiles": _p("number", "Maximum tether length", minimum=2, maximum=60, units="tiles"),
        "returnSpeedBlocksPerSecond": _world_units(_p("number", "Return speed", minimum=1, maximum=80, units="pixels/projectile update"), "returnSpeed", multiplier=16, divisor=60, updates_power=1, units='blocks/s'),
    }, requirements=(RequirementSpec(
        "item_capability_param", target="item_body", capability="configure_item_use", param="channel", equals=True,
        when_spawned_by_inputs=("primary_use", "alternate_use"),
        message="An active flail spawn requires explicit item channel=true so native StartChanneling(Item) supplies owner.channel; release or reaching the leash latches return. Passive/event producers only observe existing owner channel.",
    ),), targets=("owner_attached_projectile",)),
    _movement("move_yoyo_hover", "Follow the owner's cursor inside a leash and return on release. The same authored speed controls both cursor tracking and return, with velocity smoothing. This movement rotates the body by 0.35 radians per projectile update and does not turn the player toward the cursor; a child aiming by facing still uses the player's direction, not the rotating body. An active spawn root requires configure_item_use.channel=true: native StartChanneling(Item) otherwise leaves an idle owner unchannelled and return is latched on the first AI. Passive/event-driven copies observe existing owner channel; this movement does not start channeling.", 17, {
        "rangeTiles": _p("number", "Cursor leash", minimum=2, maximum=60, units="tiles"),
        "speedBlocksPerSecond": _world_units(_p("number", "Desired speed for both cursor tracking and return to owner; desired velocity is limited by target distance, then current velocity lerps 28% toward it per projectile update", minimum=1, maximum=80, units="pixels/projectile update", wire_name="returnSpeed"), "speed", multiplier=16, divisor=60, updates_power=1, units='blocks/s'),
    }, requirements=(RequirementSpec(
        "item_capability_param", target="item_body", capability="configure_item_use", param="channel", equals=True,
        when_spawned_by_inputs=("primary_use", "alternate_use"),
        message="An active yoyo spawn requires explicit item channel=true so native StartChanneling(Item) supplies owner.channel; release latches return. Passive/event producers only observe existing owner channel.",
    ),), targets=("owner_attached_projectile",)),
    _movement("move_whip_lash", "Execute the bounded owner-attached curved polyline from hand to tip; collision checks every segment, while Projectile.Center is the terminal point. Lash progress follows the owner's current itemAnimation/itemAnimationMax; the projectile remains active only while that animation is positive, including when an activation delay ends. A baked/reused PNG draws once at that tip, not along the curve. runtime_geometry draws the exact collision curve; a separately authored VFX texturedPath source=whip can accompany a baked tip. A channel_beam controller takes collision/geometry precedence. No automatic sprite stretching or representation selection.", 18, {
        "rangeTiles": _p("number", "Lash reach", minimum=2, maximum=60, units="tiles"),
        "segments": _p("integer", "Collision curve segments", minimum=3, maximum=48),
    }, targets=("owner_attached_projectile",)),
    _movement("move_forward_then_retract", "Move the body center from owner center + aimed axis * (18px + triangular range displacement), extending then retracting during the cycle. The axis follows the live owner cursor (bounded synced aim for remote owners) every AI update, rotating both body and hitbox; not a fixed initial launch axis. configure_spawn.aim controls launch only, not this ongoing aim. This is not hand-attached: no native arm control, grip consumption or PNG stretching. It remains an independent legal movement choice.", 19, {
        "rangeTiles": _p("number", "Peak triangular displacement beyond the 18px owner-center baseline; not distance from the hand", minimum=1, maximum=20, units="tiles"),
        "durationSeconds": _seconds(_p("integer", "Full forward/retract cycle", minimum=2, maximum=240, units="ticks"), "durationTicks"),
    }, targets=("owner_attached_projectile",)),
    _movement("move_front_hand", "Attach this explicit body's pose and collision center to the native front hand. Initial aim keeps the spawn axis; cursor aim follows synced live owner aim. No damage, lifecycle, visibility, asset or item-use choice is inserted. Collision center = native hand + aimed axis * hitboxOffsetPx, independent of PNG metadata; the existing axis-aligned rectangle is not pixel-matched blade collision. none-to-full stretch moves the hand only 6px; hitboxOffsetPx is a fixed center offset, not thrust reach or an extra sprite shift. Compare source use/collision geometry and resulting hand-to-damage coverage before deliberately choosing a short jab; sprite length alone adds no reach.", 20, {
        "aimMode": _p("string", "initial keeps the configured spawn axis; cursor explicitly follows bounded synced owner aim", enum=("initial", "cursor"), wire_presence_requires_receipt=True),
        "durationSeconds": _seconds(_p("integer", "One extension/retraction pose cycle in world seconds, lowered to whole active ticks. Native activeTicks=floor(activeAIUpdates/(extraUpdates+1)). Subupdates retain that tick's stretch. After completion hold startStretch; lifetime and item animation remain independent", minimum=2, maximum=240, units="active world ticks", wire_presence_requires_receipt=True), "durationTicks"),
        "startStretch": _p("string", "Native front-arm starting/ending stretch; none/quarter/three_quarters/full correspond to hand lengths 4/6/8/10px. Must not exceed peakStretch", enum=_NATIVE_ARM_STRETCH, wire_presence_requires_receipt=True),
        "peakStretch": _p("string", "Native peak stretch. Over the lowered whole-tick duration, use triangular extension/retraction progress; interpolate native lengths and select nearest, ties shorter. Equal endpoints keep a fixed stretch", enum=_NATIVE_ARM_STRETCH, wire_presence_requires_receipt=True),
        "hitboxOffsetPx": _p("number", "Signed collision-center offset from native hand along the aimed world axis. Explicit zero is valid; not inferred from art, scale or grip", minimum=-192, maximum=192, units="pixels", consumer_storage="float32", wire_presence_requires_receipt=True),
    }, requirements=(
            RequirementSpec("ordered_params", param="startStretch", other_param="peakStretch",
                any_of=_NATIVE_ARM_STRETCH, message="Native startStretch must not exceed peakStretch."),
            RequirementSpec("primary_target", message="This shared native front hand may be owned only by the exact primary entity."),
            RequirementSpec("binding_tuple_present", any_of=("primary_use|spawn_entity", "alternate_use|spawn_entity"),
                message="The hand owner requires an active spawn binding on this exact target, not a hold lane or another entity's active binding."),
            RequirementSpec("item_capability_param", capability="set_projectile_concurrency", param="maxActive", equals=1,
                message="The hand owner requires explicit same-item/entity maxActive=1; count=1 is not a concurrency cap."),
            RequirementSpec("item_capability_param", capability="configure_spawn", param="aim", any_of=("cursor", "facing", "velocity"),
                message="The hand owner requires an explicit launch axis: configure_spawn aim must be cursor, facing or velocity, never none, even when aimMode=cursor."),
            RequirementSpec("item_capability_param", capability="configure_spawn", param="count", equals=1,
                message="The hand owner requires explicit spawn count=1."),
            RequirementSpec("item_capability_param", capability="configure_spawn", param="spreadRadians", equals=0,
                message="The hand owner requires explicit zero spawn fan spread."),
            RequirementSpec("item_capability_param", capability="configure_spawn", param="velocity", equals={"constantSpeedBlocksPerSecond": 0},
                message="The hand owner requires constant zero translational launch speed, not a sampled distribution."),
            RequirementSpec("item_capability_param", capability="set_projectile_collision", param="tileCollide", equals=False,
                message="The hand-driven body requires explicit tileCollide=false."),
            RequirementSpec("item_capability_param", target="item_body", capability="configure_item_use", param="handPose", equals="", allow_absent=True,
                message="Another item handPose cannot own the same arm; leave handPose empty or absent."),
            RequirementSpec("capability_absent", any_of=("channel_beam", "charge_then_release", "target_and_fire"),
                message="Another position controller or over-target transform cannot own this hand-driven body."),
            RequirementSpec("capability_param_absent", capability="configure_spawn", param="position.above",
                message="The hand-driven body cannot use an over-target spawn displacement."),
       ),
       targets=("owner_attached_projectile",)),
])

_CAPS.extend([
    _cap(
        "channel_beam",
        "Keep an owner-attached line entity aimed at the cursor; collision is the explicit beam segment, taking precedence over movement collision. Sustain mana, warmup ramps and tile raycast are independent explicit params. ownerHitCheck remains a separate native owner-to-target hit check, not beam clipping. A baked/reused PNG draws once at Projectile.Center, not over the full segment. runtime_geometry and VFX texturedPath source=beam share the exact clipped collision line; no automatic representation selection.",
        "controller",
        ("owner_attached_projectile",),
        {
            "rangeTiles": _p("number", "Beam length", minimum=1, maximum=120, units="tiles"),
            "widthPx": _p("number", "Beam collision width", minimum=2, maximum=128, units="pixels"),
            "warmupSeconds": _seconds(_p("integer", "Warmup ramp duration in world seconds; progress is projectile age divided by duration with extraUpdates accounted for. Zero means immediately full width and damage.", minimum=0, maximum=600, units="ticks"), "warmupTicks"),
            "manaPayment": _p("string", "initial_use_only retains native initial item-use payment. each_use_time additionally makes each physical beam call owner.CheckMana(HeldItem, amount=-1, pay=true, blockQuickMana=false) every current HeldItem.useTime world ticks after first active update; uses native GetManaCost and missing-mana effects, and terminates the beam when payment fails. Owner peer only; extraUpdates never duplicates payment.", required=False, enum=("initial_use_only", "each_use_time"), default="initial_use_only", neutral="initial_use_only", units="native mana payment cadence", execution_phase="owner channel sustain"),
            "initialDamageMultiplier": _p("number", "NPC source-damage multiplier at warmup progress zero, interpolated linearly to 1. Applied in ModifyHitNPC to the live projectile damage; does not overwrite Projectile.damage or redefine child inheritance. Native defense/crit/rounding follow the hit modifier.", required=False, minimum=0.01, maximum=1, default=1.0, neutral=1.0, units="source damage multiplier", consumer_storage="float32", execution_phase="NPC hit"),
            "initialWidthMultiplier": _p("number", "Multiplier of widthPx at warmup progress zero, interpolated linearly to 1 for collision and runtime_geometry width, including subpixel widths. VFX uses the shared segment with its separately authored textured-path width; PNG size is independent.", required=False, minimum=0.01, maximum=1, default=1.0, neutral=1.0, units="beam width multiplier", consumer_storage="float32", execution_phase="beam geometry"),
            "damageStartProgress": _p("number", "Minimum warmup progress that enables the native friendly hit lane, inclusive. 1 retains the full-warmup gate; 0 enables hits from the start. Progress and threshold use binary64 before native hit dispatch.", required=False, minimum=0, maximum=1, default=1.0, neutral=1.0, units="fraction of warmup", execution_phase="channel update"),
            "raycastTiles": _p("boolean", "When true, Collision.LaserScan samples three rays across current beam width and clips the shared segment to the shortest bounded sample without temporal smoothing. False retains full range. Does not set collision.tileCollide or damage.ownerHitCheck.", required=False, default=False, neutral=False, units="tile clipping enabled", execution_phase="beam geometry"),
        },
        component_slot="controller",
        authority="owner_execute_sync",
        authority_by_effect={"sustain_mana": "owner_execute_sync", "beam_geometry": "native_local_collision_and_visual", "NPC_source_damage": "native_projectile_hit_authority"},
        exclusive_group="controller",
        position_ownership="owns_position_while_active",
        py=_COMPILER_OWNER,
        cs="Content/Projectiles/GeneratedProjectile.Executors.cs::ApplyChannelBeam/TryPayChannelBeamMana|Content/Projectiles/GeneratedProjectile.RuntimeEvents.cs::GetChannelBeamGeometry/ModifyHitNPC",
    ),
    _cap(
        "charge_then_release",
        "Accumulate bounded charge while held, then release this entity using authored movement. Charging pauses the native lifetime countdown; the authored lifetime is available for flight after release. Other active-age clocks are not reset.",
        "controller",
        ("owner_attached_projectile", "free_projectile"),
        {
            "chargeSeconds": _seconds(_p("integer", "Full charge duration", minimum=1, maximum=600, units="ticks"), "chargeTicks"),
            "damageMultiplier": _p("number", "Full-charge multiplier of current native damage only, applied once at release; partial charge interpolates from 1. 1 preserves damage", minimum=1, maximum=4, wire_name="chargeDamageMultiplier", neutral=1, consumer_storage="float32"),
            "knockbackMultiplier": _p("number", "Independent full-charge knockback multiplier; partial charge interpolates from 1. 1 preserves knockback", minimum=0, maximum=4, neutral=1, consumer_storage="float32"),
            "speedMultiplier": _p("number", "Independent full-charge release-speed multiplier; partial charge interpolates from 1. 1 preserves launch speed; values below 1 make a slower charged shot", minimum=0.1, maximum=4, neutral=1, consumer_storage="float32"),
        },
        component_slot="controller",
        authority="owner_execute_sync",
        exclusive_group="controller",
        position_ownership="owns_position_until_release",
        emitted_events=("on_release", "channel_complete"),
        py=_COMPILER_OWNER,
        cs="Content/Projectiles/GeneratedProjectile.Executors.cs::RunMovement/RunController",
    ),
    _cap(
        "target_and_fire",
        "Acquire NPC targets and periodically spawn an authored shot entity from this entity's current position. Explicit same-entity movement executes before firing. Stationary/helper entities without movement remain stationary; free/child entities require explicit movement. Independent shot entities keep their own movement. Explicit combat bases select the child's authored stats or this projectile's current damage/knockback; the selected damage is multiplied once, without repeating player/class modifiers. Volley count/spread belong to this controller; child spawn count/spread remain independent for its other producers. Shared activation, depth and owner budgets still bound spawning. Child configure_spawn aim=velocity consumes the acquired target direction, and position={at:activation_origin} consumes the firing entity origin; other explicit child aim/position choices remain literal.",
        "controller",
        ("stationary_projectile", "temporary_helper", "free_projectile", "child_projectile"),
        {
            "shotEntity": _p("string", "Referenced projectile entity id", pattern=r"^[a-z][a-z0-9_]{0,47}$", wire_name="shotEntityId"),
            "intervalSeconds": _seconds(_p("integer", "Firing interval", minimum=6, maximum=3600, units="ticks"), "intervalTicks"),
            "rangeTiles": _p("number", "Target range: hard geometric maximum when hardRange=true; otherwise previous target may be chosen outside it after distance discount", minimum=1, maximum=120, units="tiles"),
            "sameTargetBias": _p("number", "Previous target distance score = distance × (1 − bias); fresh bias is 0..0.9. Choose the smallest score below rangeTiles × 16; with hardRange=false the previous target may therefore lie outside that physical radius. With hardRange=true the geometric range is checked before discounting. This is a distance discount, not a hit probability", minimum=0, maximum=0.9, units="engine units: distance-score discount"),
            "damageBasis": _p("string", "Child damage magnitude: its authored base, or this parent projectile's actual damage at firing time (including prior native/charge changes). Does not enable damage: the child needs set_projectile_damage; authored damage=0 is valid with live_parent", enum=("authored_child", "live_parent"), wire_presence_requires_receipt=True),
            "knockbackBasis": _p("string", "Child knockback source: its authored knockback, or this parent projectile's actual knockBack at firing time", enum=("authored_child", "live_parent"), wire_presence_requires_receipt=True),
            "damageMultiplier": _p("number", "Multiply the selected damage basis exactly once; zero preserves a zero-damage child", minimum=0, maximum=4, wire_presence_requires_receipt=True),
            "count": _p("integer", "Shots per firing volley, independently of child configure_spawn.count; 1 retains a single shot", minimum=1, maximum=4, units="projectiles/volley", required=False, default=1, neutral=1),
            "spreadRadians": _p("number", "Full symmetric fan angle for this firing volley; count=1 has zero angular offset", minimum=0, maximum=0.75, units="radians", required=False, default=0.0, neutral=0.0, consumer_storage="float32"),
            "targetPolicy": _p("string", "distance_score selects the lowest distance score; player_assigned_first gives the owner's exact assigned NPC priority if it passes the same range/LOS filters, then uses distance score", enum=("distance_score", "player_assigned_first"), required=False, default="distance_score", neutral="distance_score"),
            "requireLineOfSight": _p("boolean", "Require native Collision.CanHit from this projectile hitbox to the candidate NPC hitbox for both assigned and scanned targets", required=False, default=False, neutral=False),
            "hardRange": _p("boolean", "Reject geometric distance beyond rangeTiles before applying previous-target score discount; false retains the existing soft score limit", required=False, default=False, neutral=False),
        },
        component_slot="controller",
        authority="owner_execute_sync",
        exclusive_group="controller",
        position_ownership="none",
        meaningful_for_stationary=True,
        py=_COMPILER_OWNER,
        cs="Content/Projectiles/GeneratedProjectile.Executors.cs::RunMovement/RunController",
    ),
    _cap(
        "spawn_entity_on_event",
        "Spawn a referenced authored entity when one supported event occurs. Explicit combat bases select the child's authored stats or the event-owning projectile's actual damage/knockback. Delayed actions snapshot live parent stats when enqueued, including terminal events; player/class modifiers are not applied again. Item-body events can select only authored_child.",
        "event",
        ("item_body", *PROJECTILE_ENTITY_KIND_ORDER),
        {
            "when": _event_when_param(EVENT_KINDS),
            "entity": _p("string", "Referenced entity id", pattern=r"^[a-z][a-z0-9_]{0,47}$", wire_name="entityId"),
            "count": _p("integer", "Spawn count", minimum=1, maximum=12),
            "spreadRadians": _p("number", "Total angular spread", minimum=0, maximum=6.283185307179586, units="radians"),
            "damageBasis": _p("string", "Child damage magnitude: its authored base, or this event-owning projectile's actual damage at event time; live_parent requires a projectile source. Does not enable damage: the child needs set_projectile_damage; authored damage=0 is valid with live_parent", enum=("authored_child", "live_parent"), wire_presence_requires_receipt=True),
            "knockbackBasis": _p("string", "Child knockback source: its authored knockback, or this event-owning projectile's actual knockBack at event time; live_parent requires a projectile source", enum=("authored_child", "live_parent"), wire_presence_requires_receipt=True),
            "damageMultiplier": _p("number", "Multiply the selected damage basis exactly once; zero preserves a zero-damage child", minimum=0, maximum=4),
            "delaySeconds": _seconds(_p("integer", "Delay after event", minimum=0, maximum=600, units="ticks"), "delayTicks"),
        },
        component_slot="event_action",
        authority="owner_execute_sync",
        activation_spawn_count_param="count",
        meaningful_for_stationary=True,
        multiplicity="many_per_target",
        py=_COMPILER_OWNER,
        cs="Common/Runtime/RuntimeProgramExecutor.cs::ExecuteAction",
        events=EVENT_KINDS,
        budget="max 12 per action, program child depth <= 3, total event spawn budget <= 32",
    ),
    _cap(
        "spawn_entity_from_hit_target",
        "Emit authored moving children from explicit before/after geometry around the actually hit NPC. Capture its centre, size, event direction and owner seed at event admission, including delay. Each child uses its own authored velocity rule; geometry does not promise a re-hit or inherit a hidden parent-speed formula.",
        "event",
        PROJECTILE_ENTITY_KINDS,
        {
            "when": _event_when_param(("on_hit", "on_crit")),
            "entity": _p("string", "Referenced moving child; its spawn position must be {at:activation_origin}, aim velocity, offsetBlocks 0, with no above-position transform", pattern=r"^[a-z][a-z0-9_]{0,47}$", wire_name="entityId"),
            "count": _p("integer", "Number of independently placed children", minimum=1, maximum=12),
            "geometry": _hit_target_spawn_geometry(),
            "damageBasis": _p("string", "Child damage magnitude, selected independently of its velocity and knockback. Does not enable damage: the child needs set_projectile_damage; authored damage=0 is valid with live_parent", enum=("authored_child", "live_parent"), wire_presence_requires_receipt=True),
            "knockbackBasis": _p("string", "Child knockback source, selected independently of damage", enum=("authored_child", "live_parent"), wire_presence_requires_receipt=True),
            "damageMultiplier": _p("number", "Multiply the selected damage exactly once; zero preserves a zero-damage child", minimum=0, maximum=4),
            "delaySeconds": _seconds(_p("integer", "World-time delay; target geometry, direction, exclusion incarnation and random seed are captured when admitted", minimum=0, maximum=600, units="ticks"), "delayTicks"),
        },
        component_slot="event_action",
        authority="owner_execute_sync",
        activation_spawn_count_param="count",
        meaningful_for_stationary=True,
        multiplicity="many_per_target",
        py=_COMPILER_OWNER,
        cs="Common/Runtime/RuntimeProgramExecutor.cs::ExecuteAction",
        wire_action="spawn_entity_on_event",
        events=("on_hit", "on_crit"),
        budget="max 12 per action, program child depth <= 3, shared event spawn budget <= 32; no reservation is recreated on hydration",
    ),
    _cap(
        "select_targets_and_emit_on_event",
        "Plan bounded NPC links at the hit callback and emit a separate authored projectile for each link. "
        "Each search and initial emission starts at the selected anchor; all links are planned at dispatch, not after child hits. "
        "The child owns its speed, movement, damage and native collision; a selected target is an initial direction, not a guaranteed hit. "
        "No direct damage, status or VFX is implied.",
        "event",
        ("item_body", *PROJECTILE_ENTITY_KIND_ORDER),
        {
            "when": _event_when_param(("on_hit", "on_crit")),
            "entity": _p("string", "Independent free/child projectile with explicit origin/velocity spawn, zero offset and no over-target adapter", pattern=r"^[a-z][a-z0-9_]{0,47}$", wire_name="entityId",
                         reference=ReferenceSpec("entity", ("free_projectile", "child_projectile"), False, True)),
            "stepCount": _p("integer", "Maximum planned links, one child per link; bounded by the shared activation spawn budget", minimum=1, maximum=12, units="projectiles"),
            "stepRangeTiles": _p("number", "Inclusive geometric search radius measured anew from the selected anchor on each step", minimum=1, maximum=60, units="tiles"),
            "selectionAnchor": _p("string", "previous_target advances search/emission origin to each selected NPC; event_target keeps the dispatch-time source NPC center", enum=("previous_target", "event_target")),
            "repeatPolicy": _p("string", "The current anchor is always excluded. allow_revisits permits earlier NPCs again; exclude_visited excludes source and every previously selected NPC", enum=("allow_revisits", "exclude_visited")),
            "requireLineOfSight": _p("boolean", "Require native Collision.CanHit from the current anchor hitbox to each candidate; independent of child tileCollide/ownerHitCheck"),
            "initialIgnoreCountdownUpdates": _p("integer", "Exclude the exact emission-anchor NPC while this native AI countdown is positive; decremented before collision, so 10 means pre-AI plus nine post-AI collision opportunities; 0 disables", minimum=0, maximum=600, units="native projectile AI updates"),
            "delaySeconds": _seconds(_p("integer", "Dispatch delay in world seconds; delayed source NPC must retain its active exact incarnation", minimum=0, maximum=600, units="world ticks"), "delayTicks"),
        },
        requirements=(
            RequirementSpec("event_available", param="when", message="The source entity must actually emit the selected hit event."),
            RequirementSpec("referenced_entity_capability_params", param="entity", capability="configure_spawn",
                equals={"position": {"at": "activation_origin"}, "aim": "velocity", "offsetBlocks": 0},
                message="The emission reference requires configure_spawn position={at:activation_origin}, aim=velocity, offsetBlocks=0; Repair permissions distinguish an exclusive dependency from an independently used child."),
        ),
        component_slot="event_action",
        authority="owner_execute_sync",
        activation_spawn_count_param="stepCount",
        meaningful_for_stationary=True,
        multiplicity="many_per_target",
        py=_COMPILER_OWNER,
        cs="Common/Runtime/RuntimeProgramExecutor.cs::ExecuteAction/PlanTargetEmissions/SelectTargetsAndEmit",
        events=("on_hit", "on_crit"),
        budget="at most 12 planned physical children; one shared activation reservation each; acyclic entity graph, depth <= 3 and aggregate event spawn count <= 32",
    ),
    _cap(
        "apply_generated_buff_on_event",
        "Apply one exact named generated-utility-buff group to the owner after a functional equipment reaction. Populate it with apply_generated_buff_on_use using the same effectGroupId; no active-use binding is needed for that group. The group must contain only this generated buff, never healing, native buffs or teleport. Identical effects refresh remaining duration without stacking strength; existing item exhaustion and shared per-action reaction cooldowns still apply. In multiplayer the owner predicts the effect, while native server hurt/death occurrences build the authoritative utility snapshot; client stat claims cannot commit it.",
        "event", ("item_body",),
        {
            "when": _event_when_param(("on_hurt", "on_enemy_kill")),
            "effectGroupId": _p("string", "Exact named generated-buff-only group on this item", pattern=r"^[a-z][a-z0-9_]{0,47}$", semantic_type="item_effect_group_reference", wire_presence_requires_receipt=True),
        },
        component_slot="event_action", authority="server_execute",
        multiplicity="many_per_target", py=_COMPILER_OWNER,
        cs="Common/Runtime/RuntimeProgramExecutor.cs::ExecuteAction",
        events=("on_hurt", "on_enemy_kill"),
    ),
    _cap(
        "apply_status_on_event",
        "Apply one concrete Terraria debuff/buff to the hit target on a supported event.",
        "event",
        ("item_body", *PROJECTILE_ENTITY_KIND_ORDER),
        {
            "when": _event_when_param(("on_hit", "on_crit")),
            "buffId": _p("integer", "Exact loaded BuffID/ModContent.BuffType; copy from parent facts, do not guess", minimum=1, maximum=65535, semantic_type="loaded_buff_id"),
            "durationSeconds": _seconds(_p("integer", "Status duration", minimum=1, maximum=21600, units="ticks"), "durationTicks"),
        },
        component_slot="event_action",
        authority="owner_execute_sync",
        meaningful_for_stationary=True,
        multiplicity="many_per_target",
        py=_COMPILER_OWNER,
        cs="Common/Runtime/RuntimeProgramExecutor.cs::ExecuteAction",
        events=("on_hit", "on_crit"),
    ),
    _cap(
        "damage_area_on_event",
        "Deal bounded AoE damage at the event position. Exclude the event's direct target only for on_hit/on_crit. "
        "For other events, including on_expire/on_kill, ignore direct-target exclusion; a previously hit NPC is not excluded by hit history. "
        "An additional hit is not guaranteed: native NPC eligibility/damage rules still apply.",
        "event",
        ("item_body", *PROJECTILE_ENTITY_KIND_ORDER),
        {
            "when": _event_when_param(("on_hit", "on_crit", "on_tile_collision", "on_expire", "on_kill", "on_hurt", "on_enemy_kill")),
            "radiusTiles": _p("number", "Damage radius on the exact 1/16-tile pixel lattice", minimum=0.5, maximum=48, multiple_of=1 / 16, wire_multiplier=16, wire_name="radiusPx", units="tiles"),
            "damageMultiplier": _p("number", "Multiply event-owning entity's authored base damage: item_body uses configure_item_stats.damage, projectile uses set_projectile_damage.damage; rounded, at least 1 before target defense. 1 is base damage, 0.05 is 5% of base, not +5% or damageDone", minimum=0.05, maximum=4),
        },
        component_slot="event_action",
        authority="server_execute",
        authority_by_effect={"on_hit": "owner_execute_sync", "on_crit": "owner_execute_sync", "on_hurt": "owner_execute_sync", "on_enemy_kill": "owner_execute_sync"},
        meaningful_for_stationary=True,
        multiplicity="many_per_target",
        py=_COMPILER_OWNER,
        cs="Common/Runtime/RuntimeProgramExecutor.cs::ExecuteAction",
        events=("on_hit", "on_crit", "on_tile_collision", "on_expire", "on_kill", "on_hurt", "on_enemy_kill"),
    ),
    _cap(
        "damage_nearest_on_event",
        "Damage up to maxTargets nearest chaseable NPCs within one radius of the recorded event center, excluding the directly hit NPC. Every target is ranked from that same center and receives the same authored base-damage multiplier; no sequential hopping or distance falloff.",
        "event",
        ("item_body", *PROJECTILE_ENTITY_KIND_ORDER),
        {
            "when": _event_when_param(("on_hit", "on_crit")),
            "maxTargets": _p("integer", "Maximum additional NPCs selected from the same event center, nearest first; the directly hit NPC is excluded", minimum=1, maximum=12, wire_name="count", semantic_type="spawn_or_target_count"),
            "rangeTiles": _p("number", "Inclusive physical search radius around the recorded event center, in tiles; it does not move between targets", minimum=1, maximum=60, units="tiles"),
            "damageMultiplier": _p("number", "Multiply event-owning entity's authored base damage: item_body uses configure_item_stats.damage, projectile uses set_projectile_damage.damage; rounded, at least 1 before target defense. 1 is base damage, 0.05 is 5% of base, not +5% or damageDone", minimum=0.05, maximum=2),
        },
        component_slot="event_action",
        authority="owner_execute_sync",
        meaningful_for_stationary=True,
        multiplicity="many_per_target",
        py=_COMPILER_OWNER,
        cs="Common/Runtime/RuntimeProgramExecutor.cs::ExecuteAction",
        events=("on_hit", "on_crit"),
        wire_action="chain_damage_on_event",
    ),
    _cap(
        "pull_on_event",
        "Apply bounded pull between owner, target and event entity.",
        "event",
        PROJECTILE_ENTITY_KINDS,
        {
            "when": _event_when_param(("on_hit", "periodic", "on_expire")),
            "mode": _p("string", "Pull direction", enum=("target_to_owner", "target_to_entity")),
            "impulseBlocksPerSecond": _world_units(_p("number", "Add velocity impulse toward selected endpoint on each event (NPC impulse also multiplies knockBackResist); not displacement", minimum=0.01, maximum=4, units="engine units: velocity impulse coefficient per event"), "strength", multiplier=16, divisor=60, units="blocks/s (one-off velocity impulse)"),
            "radiusTiles": _p("number", "NPC search radius with no active direct target; also used by on_hit if its target became inactive", minimum=1, maximum=60, units="tiles"),
        },
        component_slot="event_action",
        authority="server_execute",
        authority_by_effect={"target_to_owner": "server_execute", "target_to_entity": "server_execute", "on_hit:target_to_owner": "owner_request_server_execute", "on_hit:target_to_entity": "owner_request_server_execute"},
        meaningful_for_stationary=True,
        multiplicity="many_per_target",
        py=_COMPILER_OWNER,
        cs="Common/Runtime/RuntimeProgramExecutor.cs::ExecuteAction",
        events=("on_hit", "periodic", "on_expire"),
    ),
    _cap(
        "pull_owner_to_event_target",
        "Pull the owning player toward the active direct target recorded by the event. No target means no movement; it never searches for a replacement NPC.",
        "event",
        PROJECTILE_ENTITY_KINDS,
        {
            "when": _event_when_param(("on_hit", "periodic", "on_expire")),
            "impulseBlocksPerSecond": _world_units(_p("number", "Player velocity impulse toward the event's active direct target", minimum=0.01,
                           maximum=4, units="engine units: velocity impulse coefficient per event"), "strength", multiplier=16, divisor=60, units="blocks/s (one-off velocity impulse)"),
        },
        component_slot="event_action",
        authority="owner_execute_sync",
        meaningful_for_stationary=True,
        multiplicity="many_per_target",
        py=_COMPILER_OWNER,
        cs="Common/Runtime/RuntimeProgramExecutor.cs::ExecuteAction",
        events=("on_hit", "periodic", "on_expire"),
        wire_action="pull_on_event",
        fixed_wire_literals={"mode": "owner_to_target", "radiusTiles": 1},
    ),
    _cap(
        "heal_owner_on_event",
        "Heal the owning player from dealt damage on hit/crit.",
        "event",
        ("item_body", *PROJECTILE_ENTITY_KIND_ORDER),
        {
            "when": _event_when_param(("on_hit", "on_crit")),
            "damageFraction": _p("number", "Fraction of damageDone healed (0.15 = 15%), capped by maxHeal; not a whole-number percent", minimum=0.001, maximum=1),
            "maxHeal": _p("integer", "Per-event heal cap", minimum=1, maximum=200, units="HP"),
        },
        component_slot="event_action",
        authority="owner_execute_sync",
        meaningful_for_stationary=True,
        multiplicity="many_per_target",
        py=_COMPILER_OWNER,
        cs="Common/Runtime/RuntimeProgramExecutor.cs::ExecuteAction",
        events=("on_hit", "on_crit"),
    ),
    _cap(
        "move_owner_on_event",
        "Execute owner teleport to the recorded event position, limited by range and shared mobility cooldown.",
        "event",
        PROJECTILE_ENTITY_KINDS,
        {
            "when": _event_when_param(("on_hit", "on_tile_collision", "on_expire")),
            "rangeTiles": _p("integer", "Maximum movement range", minimum=1, maximum=120, units="tiles"),
            "cooldownSeconds": _seconds(_p("integer", "Shared owner mobility cooldown", minimum=0, maximum=3600, units="ticks"), "cooldownTicks"),
            "safeTileOnly": _p("boolean", "Check destination solid-tile overlap only; false skips it. No world-bounds or lava check in this event action; not a general hazard check"),
        },
        component_slot="event_action",
        authority="owner_execute_sync",
        meaningful_for_stationary=True,
        multiplicity="many_per_target",
        py=_COMPILER_OWNER,
        cs="Common/Runtime/RuntimeProgramExecutor.cs::ExecuteAction",
        events=("on_hit", "on_tile_collision", "on_expire"),
    ),
    _cap(
        "emit_light_while_active",
        "Emit bounded world light from a live runtime entity.",
        "entity_utility",
        PROJECTILE_ENTITY_KINDS,
        {
            "strength": _p("number", "Client light RGB coefficient multiplying selected color (not a tile radius)", minimum=0.01, maximum=1.5, units="engine units: RGB coefficient"),
            "color": _p("string", "Canonical light color", enum=_COLOR),
        },
        component_slot="light",
        authority="client_visual_only",
        meaningful_for_stationary=True,
        py=_COMPILER_OWNER,
        cs="Content/Projectiles/GeneratedProjectile.Executors.cs::AI",
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
        ("restore_resources_on_use", "apply_vanilla_buff_on_use", "apply_generated_buff_on_use", "move_player_on_use", "recall_home_on_use"),
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
        "Emitted by item_body after an accepted non-placement primary_use/alternate_use, including spawn_entity actions; the emitting source is not the action target.",
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
        "Bounded periodic event; each action selects when={everySeconds:n}, nominally 0.1..60 seconds before declared nearest-tick lowering. Item-body gameplay runs while held or functionally equipped through equip_passive; inventory or vanity alone does not produce it.",
    ),
    "on_release": EventKindSpec(
        "on_release", PROJECTILE_ENTITY_KIND_ORDER, ("charge_then_release",),
        "Emitted by charge_then_release when the held charge is released.",
    ),
    "channel_complete": EventKindSpec(
        "channel_complete", PROJECTILE_ENTITY_KIND_ORDER, ("charge_then_release",),
        "Emitted by charge_then_release after a full authored charge.",
    ),
    "on_hurt": EventKindSpec(
        "on_hurt", ("item_body",), (),
        "Owner survives positive damage. Functional equipment only; no NPC target or damageDone.",
        producer_binding_inputs=("equipped",), producer_binding_actions=("equip_passive",), producer_binding_kinds=("item_body",),
    ),
    "on_enemy_kill": EventKindSpec(
        "on_enemy_kill", ("item_body",), (),
        "Server-confirmed hostile NPC death credited by lastInteraction. Functional equipment only; excludes critters/segments. Position=enemy center; no live target. Not projectile on_kill.",
        producer_binding_inputs=("equipped",), producer_binding_actions=("equip_passive",), producer_binding_kinds=("item_body",),
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
        for row in binding_rows:
            raw_action = row.get("action")
            action: Mapping[str, Any] = raw_action if isinstance(raw_action, Mapping) else {}
            input_name = row.get("input")
            inp = INPUT_KIND_REGISTRY.get(input_name) if isinstance(input_name, str) else None
            action_name = action.get("kind")
            if action_name is None and inp is not None and len(inp.allowed_actions) == 1:
                action_name = inp.allowed_actions[0]
            if (isinstance(input_name, str) and input_name in allowed_inputs
                and (not allowed_actions or isinstance(action_name, str) and action_name in allowed_actions)
                and action.get("targetId") == target_id
                and (requirement.required_contact_damage is None or
                     (row.get("contactDamage") is True) is requirement.required_contact_damage)):
                return True
        return False

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
    if cap.final_wire_paths:
        paths = cap.final_wire_paths
        if cap.effect_groupable:
            return (*paths, "runtimeProgram.effectGroups[].id",
                    *(path.replace("gameplay.", "runtimeProgram.effectGroups[].", 1) for path in paths))
        return paths
    param_fields = tuple(dict.fromkeys(field_name for name, spec in cap.params.items()
                                      for field_name in spec.wire_field_names(name)))
    if cap.name == "configure_weapon_ammo":
        return ("runtimeProgram.weaponAmmo", *(f"runtimeProgram.weaponAmmo.{name}" for name in cap.params))
    if cap.category == "item_placed_body":
        base = "runtimeProgram.bindings[].usePolicy.action.placement." + cap.params["placementCallId"].wire_name
        return (base, *(f"{base}.{name}" for name in cap.params if name != "placementCallId"))
    if cap.name == "configure_item_stats":
        return tuple(f"gameplay.{spec.wire_name or name}" for name, spec in cap.params.items())
    if cap.name in {"configure_accessory", "configure_armor"}:
        prefix = "accessory" if cap.name == "configure_accessory" else "armor"
        return (f"{prefix}.enabled", *(f"{prefix}.{name}" for name in param_fields))
    if cap.name == "add_equipment_damage_bonus":
        return tuple(
            equipment_damage_wire_path(phase, damage_class, armor=armor)
            for armor in (False, True)
            for phase in (("equipped", "matching_armor_set") if armor else ("equipped",))
            for damage_class in EQUIPMENT_DAMAGE_CLASSES
        )
    if cap.name == "configure_spawn":
        return tuple(["runtimeProgram.entities[].spawn.enabled", *[f"runtimeProgram.entities[].spawn.{name}" for name in param_fields]])
    if cap.name in {"set_projectile_concurrency", "set_descendant_concurrency"}:
        return tuple(f"runtimeProgram.entities[].spawn.{name}" for name in param_fields)
    if cap.name == "set_projectile_damage":
        return tuple(["runtimeProgram.entities[].damage.enabled", *[f"runtimeProgram.entities[].damage.{name}" for name in cap.params]])
    if cap.name == "set_projectile_hitbox":
        return tuple(f"runtimeProgram.entities[].hitbox.{name}" for name in cap.params)
    if cap.name == "set_projectile_hitbox_curve":
        return tuple(f"runtimeProgram.entities[].hitboxCurve.{name}" for name in param_fields)
    if cap.name in PROJECTILE_MODIFIER_COMPONENTS:
        return tuple(f"runtimeProgram.entities[].{PROJECTILE_MODIFIER_COMPONENTS[cap.name]}.{name}" for name in param_fields)
    if cap.name == "set_projectile_collision":
        return tuple(f"runtimeProgram.entities[].collision.{name}" for name in param_fields)
    if cap.category == "movement":
        return tuple(["runtimeProgram.entities[].movement.name", "runtimeProgram.entities[].movement.code", *[f"runtimeProgram.entities[].movement.params.{name}" for name in param_fields]])
    if cap.name in {"channel_beam", "charge_then_release"}:
        return tuple(["runtimeProgram.entities[].controller.name", "runtimeProgram.entities[].controller.code", *[f"runtimeProgram.entities[].controller.params.{name}" for name in param_fields]])
    if cap.name == "target_and_fire":
        return tuple([
            "runtimeProgram.entities[].controller.name", "runtimeProgram.entities[].controller.code",
            *[f"runtimeProgram.entities[].targeting.{name}" for name in param_fields],
        ])
    if cap.category == "event":
        mapped = ["runtimeProgram.entities[].events[].event", "runtimeProgram.entities[].events[].action", "runtimeProgram.entities[].events[].actionCode"]
        for name in param_fields:
            if name == "event":
                continue
            mapped.append("runtimeProgram.entities[].events[].entityId" if name == "entity" else f"runtimeProgram.entities[].events[].{name}")
        mapped.extend(f"runtimeProgram.entities[].events[].{name}" for name in cap.fixed_wire_literals)
        if cap.name == "move_owner_on_event":
            mapped.append("runtimeProgram.entities[].events[].mode")  # fixed DTO discriminator for the only executed destination
        return tuple(dict.fromkeys(mapped))
    if cap.name == "emit_light_while_active":
        return tuple(f"runtimeProgram.entities[].light.{name}" for name in cap.params)
    raise RuntimeError(f"missing exact wire contract for capability {cap.name}")








def _derived_requirements(cap: CapabilitySpec) -> tuple[RequirementSpec, ...]:
    """Project rules that depend on parameters, registry topology or shared categories."""
    if cap.name == "configure_spawn":
        moving = ("owner_attached_projectile", "free_projectile", "child_projectile")
        rows = [RequirementSpec("present_param_requires_target_kind", param=f"velocity.{variant}", any_of=moving,
            message="Sampled initial velocity requires an entity whose initial velocity is executed; stationary/field entities require the constant-speed variant.")
            for variant in ("fanSpeed", "radial", "disk", "cone")]
        rows.extend(RequirementSpec("ordered_params", param=f"velocity.{variant}.minSpeedBlocksPerSecond",
            other_param=f"velocity.{variant}.maxSpeedBlocksPerSecond",
            message="Minimum sampled speed must not exceed the explicitly authored maximum.")
            for variant in ("fanSpeed", "radial", "cone"))
        rows.extend(RequirementSpec("present_param_requires_param_value", param=f"velocity.{variant}", other_param="aim",
            any_of=("cursor", "facing", "velocity"), message="The selected directional distribution requires an explicit non-zero aim axis.")
            for variant in ("fanSpeed", "cone"))
        rows.extend(RequirementSpec("present_param_requires_param_value", param=f"velocity.{variant}", other_param="spreadRadians", equals=0,
            message="Radial/disk directions own the full distribution; select zero deterministic fan spread.")
            for variant in ("radial", "disk"))
        rows.extend(RequirementSpec("present_param_forbids_capability", param=f"velocity.{variant}", capability=controller,
            message="This controller owns launch velocity; select the explicit constant-speed variant.")
            for variant in ("fanSpeed", "radial", "disk", "cone") for controller in ("charge_then_release", "channel_beam"))
        rows.append(RequirementSpec("present_params_forbid_item_capability_when_active_spawn",
            param="velocity", any_of=tuple(f"velocity.{variant}" for variant in ("fanSpeed", "radial", "disk", "cone")),
            capability="configure_weapon_ammo", other_param="speedBasis", equals="native_shot",
            message="An active native_shot ammo root requires the constant-speed variant; sampled authored min/max and native shot magnitude cannot both own initial speed."))
        return tuple(rows)


    if cap.category == "motion_modifier":
        return (RequirementSpec("capability_absent", any_of=("channel_beam", "charge_then_release"), message="Velocity modifiers require the explicit movement driver to own motion throughout their active phase."),
                RequirementSpec("capability_group_present", target="same_target", any_of=tuple(sorted(row.name for row in _CAPS if row.category == "movement")), message="Velocity modifiers require explicit movement, including on a target_and_fire entity."))
    if cap.name in {"channel_beam", "charge_then_release"}:
        rows = [RequirementSpec("item_capability_param", capability="configure_item_use", target="item_body", param="channel", equals=True, message="channel controller requires channel=true on item_body")]
        if cap.name == "charge_then_release":
            rows.append(RequirementSpec("capability_group_present", target="same_target", any_of=tuple(sorted(row.name for row in _CAPS if row.category == "movement")), message="released projectile needs an explicit post-release movement"))
        return tuple(rows)
    if cap.category == "item_placed_body":
        return (
            RequirementSpec("executed_tile_placement_reference", capability="configure_tile_placement",
                            param="placementCallId", any_of=("place_item",),
                            message="Reference an exact same-item tile-only placement used by an executable place_item binding, or explicitly delete this placed component call. No walls, inferred source, or unused reference."),
            RequirementSpec("unique_call_reference", param="placementCallId",
                            message="Only one call of this operation may reference a placement call; independent placed sprite and light calls may compose."),
        )
    if cap.name in PLACEMENT_CAPABILITIES:
        return (RequirementSpec("binding_action_reference", target="item_body", any_of=("place_item",), message="The placement call must be referenced by exactly one binding action.placementCallId."),)
    if cap.name in BINDING_ACTION_REGISTRY["apply_item_effects"].required_item_capabilities_any_of:
        requirements = [RequirementSpec(
            kind="binding_action_present", target="item_body", any_of=("apply_item_effects",),
            message=("This generated buff requires a matching effectGroupId in an apply_item_effects binding, refresh_generated_effect_group_while_held, or apply_generated_buff_on_event; an ungrouped buff requires an ungrouped apply_item_effects binding. A spawn_entity or use_item_body binding alone does not apply it."
                     if cap.name == "apply_generated_buff_on_use" else
                     "This item-use effect executes only through an explicit apply_item_effects binding on item_body; a spawn_entity or use_item_body binding alone does not apply it."),
        )]
        if cap.name == "restore_resources_on_use":
            requirements.append(RequirementSpec(
                "capability_group_present",
                any_of=BINDING_ACTION_REGISTRY["apply_item_effects"].required_item_capabilities_any_of,
                nonzero_params=tuple(name for name, spec in cap.params.items() if spec.neutral is not None),
                message="An apply_item_effects lane needs at least one effective use effect: positive healing or another active registered item-use effect. Potion rules alone are not an effect.",
            ))
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
    if cap.category == "event":
        requirements = ([] if any(row.kind == "event_available" for row in cap.requirements) else
                        [RequirementSpec("event_available", param="when", message="target entity must actually emit the selected event")])
        if cap.name == "spawn_entity_from_hit_target":
            requirements.extend((
                RequirementSpec("referenced_entity_capability_params", param="entity", capability="configure_spawn",
                    equals={"position": {"at": "activation_origin"}, "aim": "velocity", "offsetBlocks": 0},
                    message="Exact hit-target geometry requires a child configured for event origin/direction without another position transform."),
            ))
        if cap.name == "spawn_entity_on_event":
            requirements.append(RequirementSpec(
                "referenced_param_presence_requires_value", param="spreadRadians", other_param="entity",
                capability="configure_spawn", any_of=("velocity.radial", "velocity.disk"), equals=0,
                message="A radial/disk child owns its complete direction distribution; this event must explicitly select spreadRadians=0.",
            ))
            requirements.extend(RequirementSpec(
                "param_requires_target_kind", param=name, equals="live_parent",
                any_of=PROJECTILE_ENTITY_KIND_ORDER,
                message="live_parent requires the actual event-owning projectile; an item-body event must explicitly select authored_child.",
            ) for name in ("damageBasis", "knockbackBasis"))
        return tuple(requirements)
    return ()


def referenced_entity_requirement_satisfied(
    requirement: RequirementSpec,
    entity_id: str,
    calls_by_target: Mapping[str, Iterable[Mapping[str, Any]]],
) -> bool:
    """Evaluate declared reference constraints without changing another entity."""
    matches = [row for row in calls_by_target.get(entity_id, ())
               if row.get("fn") == requirement.capability]
    if requirement.kind == "referenced_entity_without_capability":
        return not matches
    if requirement.kind != "referenced_entity_capability_params":
        raise ValueError(f"unsupported entity reference requirement {requirement.kind!r}")
    required_cap = CAPABILITY_REGISTRY.get(requirement.capability)
    if required_cap is None or len(matches) != 1 or not isinstance(requirement.equals, Mapping):
        return False
    params = matches[0].get("params")
    if not isinstance(params, Mapping):
        return False
    for name, expected in requirement.equals.items():
        if name not in params or name not in required_cap.params:
            return False
        value = params[name]
        if required_cap.params[name].kind == "number":
            # JSON number accepts 0 and 0.0, but false cannot satisfy numeric 0.
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or isinstance(expected, bool) or not isinstance(expected, (int, float))
                    or value != expected):
                return False
        elif not json_values_equal(value, expected):
            return False
    return True


def compatible_entity_reference_ids(
    cap: CapabilitySpec,
    param_name: str,
    source_entity_id: str,
    entities_by_id: Mapping[str, Mapping[str, Any]],
    calls_by_target: Mapping[str, Iterable[Mapping[str, Any]]],
) -> tuple[str, ...]:
    """Exact kind/self/declared-child compatibility; global graph validation follows."""
    spec = cap.params.get(param_name)
    reference = spec.reference if spec is not None else None
    if reference is None or reference.namespace != "entity":
        return ()
    requirements = [row for row in cap.requirements if row.param == param_name
                    and row.kind in {"referenced_entity_capability_params", "referenced_entity_without_capability"}]
    return tuple(entity_id for entity_id, entity in entities_by_id.items()
                 if (reference.allow_self or entity_id != source_entity_id)
                 and (not reference.target_kinds or entity.get("kind") in reference.target_kinds)
                 and all(referenced_entity_requirement_satisfied(row, entity_id, calls_by_target)
                         for row in requirements))


def _semantic_param(cap: CapabilitySpec, name: str, spec: ParamSpec) -> ParamSpec:
    reference = spec.reference
    semantic_type = spec.semantic_type
    if cap.name == "present_placed_item_sprite" and spec.kind == "number":
        spec = replace(spec, consumer_storage="float64")
    if cap.name == "target_and_fire" and name == "shotEntity":
        reference = ReferenceSpec("entity", PROJECTILE_ENTITY_KIND_ORDER, False, True)
        semantic_type = "runtime_entity_id"
    elif cap.name == "spawn_entity_on_event" and name == "entity":
        reference = ReferenceSpec("entity", PROJECTILE_ENTITY_KIND_ORDER, False, True)
        semantic_type = "runtime_entity_id"
    elif cap.name == "spawn_entity_from_hit_target" and name == "entity":
        reference = ReferenceSpec("entity", ("free_projectile", "child_projectile"), False, True)
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
    elif name.endswith("Seconds"):
        semantic_type = "seconds"
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


EVENT_ACTION_OPCODE: Final[Mapping[str, int]] = MappingProxyType({
    "spawn_entity_on_event": 1,
    "apply_status_on_event": 2,
    "damage_area_on_event": 3,
    "chain_damage_on_event": 4,
    "pull_on_event": 5,
    "heal_owner_on_event": 6,
    "move_owner_on_event": 7,
    "select_targets_and_emit_on_event": 8,
    "apply_generated_buff_on_event": 9,
})


def _enrich_capability(cap: CapabilitySpec) -> CapabilitySpec:
    """Finalize mechanical projections without replacing declared capability facts."""
    if cap.effect_groupable:
        cap = replace(cap, params=MappingProxyType({
            **cap.params,
            "effectGroupId": _p("string", "Optional explicit named effect group. Calls with the same ID compose only that group's effects; absent uses the default item group. Select the group explicitly in apply_item_effects.action.effectGroupId or the held refresh / apply_generated_buff_on_event capability.",
                required=False, pattern=r"^[a-z][a-z0-9_]{0,47}$", wire_name="id", semantic_type="item_effect_group_identity"),
        }))
    if cap.category == "event":
        wire_action = cap.wire_action or cap.name
        cap = replace(cap, fixed_wire_literals=MappingProxyType({
            **cap.fixed_wire_literals, "action": wire_action, "actionCode": EVENT_ACTION_OPCODE[wire_action],
        }))
    if cap.category == "event" and "delaySeconds" not in cap.params:
        cap = replace(cap, params=MappingProxyType({
            **cap.params,
            "delaySeconds": _seconds(_p("integer", "Delay this exact action after the chosen event; 0 executes immediately", required=False,
                             minimum=0, maximum=600, units="ticks", neutral=0,
                             execution_phase="bounded delayed action scheduler"), "delayTicks"),
        }))
    exact = _exact_wire_paths(cap)
    technical = (cap.technical_lowering_outputs if cap.technical_lowering_inputs else
                 tuple(path for path in exact if path.endswith(".enabled") or path.endswith(".code") or path.endswith(".name")))
    params = MappingProxyType({name: _semantic_param(cap, name, spec) for name, spec in cap.params.items()})
    requirements = (*cap.requirements, *_derived_requirements(cap))
    return replace(
        cap,
        params=params,
        final_wire_paths=exact,
        technical_lowering_outputs=technical,
        requirements=(*requirements, *(RequirementSpec("conditional_omission", param=name,
            message="This parameter is required outside its declared inactive consumer branch")
            for name, spec in params.items() if spec.omission_condition is not None)),
        dependencies=tuple(dict.fromkeys(
            requirement.capability
            for requirement in requirements
            if requirement.capability and requirement.kind not in {"capability_param_absent", "present_param_forbids_capability", "referenced_entity_capability_params", "referenced_entity_without_capability", "referenced_param_presence_requires_value"}
        )),
        conflicts=(f"exclusive_group:{cap.exclusive_group}",) if cap.exclusive_group else (),
    )


_ENRICHED_CAPS: Final[tuple[CapabilitySpec, ...]] = tuple(
    _enrich_capability(cap) for cap in _CAPS
)


# Registry membership is the complete current Author/Repair admission contract.
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
    # Opcode 6 is retired/reserved; later movement identities stay unchanged.
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
    "move_front_hand": 20,
    "move_traveling_wave": 23,
    "move_elliptic_orbit": 22,
    "move_spring_tether": 21,
})
CONTROLLER_OPCODE: Final[Mapping[str, int]] = MappingProxyType({
    "none": 0,
    "channel_beam": 1,
    "charge_then_release": 2,
    "target_and_fire": 3,
})


def compact_capability_catalog() -> list[dict[str, Any]]:
    return [cap.author_prompt_card() for cap in CAPABILITY_REGISTRY.values()]


def runtime_authoring_prompt_field_guide() -> dict[str, Any]:
    """Project shared low-level field semantics without duplicating capability rules."""
    return {
        "handRelativeMovement": (
            "move_front_hand is an explicit native front hand attachment choice, not a short-weapon/name selector; no weapon preset. "
            "Choose initial/cursor aim, active durationSeconds cycle, ordered native start/peak stretch and signed hitboxOffsetPx independently. "
            "The native hand drives visible pose and collision center together; hitboxOffsetPx locates the existing axis-aligned rectangle, "
            "not exact blade pixels. Selected PNG grip/axis/size belong to Visual and never derive gameplay reach. "
            "Author explicitly provides the primary entity, active spawn binding, same-item/entity maxActive=1, count=1, zero spread, "
            "constant zero launch speed, tileCollide=false and empty/absent item handPose; no competing position controller or above spawn. "
            "This operation adds no damage or lifetime. Choose lifetime, item animation, hideUseGraphic, DamageClass and topology deliberately; "
            "none is selected by this driver. Other movements, a visible root, independent shots and non-damaging hand bodies remain legal."
        ),
        "stableIdPattern": r"^[a-z][a-z0-9_]{0,47}$",
        "paramNotation": (
            "Every listed param is required unless marked optional; optional params may be omitted. "
            "In a full Author object, an optional param with an explicit card default may be omitted "
            "to select exactly that neutral value only when its omissionAllowedOnlyWhen condition holds; this is not universal and never replaces an invalid present value. "
            "For full one-shot Author generation, prefer explicit values for params with omissionAllowedOnlyWhen; permitted omissions remain valid. "
            "A neutral annotation alone does not make a required param optional. "
            "All requires/conditional dependencies still apply to the combined params; optional fields "
            "cannot leave a selected effect incomplete or inert. "
            "Other optional zero-neutral params make no authored nonzero effect when absent. "
            "World distances use blocks; existing Tiles suffixes also mean blocks (tiles). 1 block = 16 pixels. "
            "Times use Seconds, speeds BlocksPerSecond, true angular rates RadiansPerSecond. "
            "Seconds lower to the nearest world tick at 60 ticks/s, half-tick ties UP; nonzero-to-zero collapse is rejected. "
            "Projectile velocity/rates use that target projectile’s unique explicit updatesPerTick for deterministic subupdate conversion; children use their own N. "
            "Px hitbox/sprite/hand/beam geometry stays pixels; UV coordinates stay normalized. "
            "updatesPerTick, immunity.localCooldown and initialIgnoreCountdownUpdates are algorithm counters, not seconds. "
            "Percent/percentage-point/chance cards use percent-scale values (15 means 15%, not 0.15): "
            "bonusPercent=15 adds +0.15 to a damage modifier; CritChancePercentagePoints=15 adds "
            "15 raw crit-chance points; manaCostReductionPercentagePoints=15 subtracts 0.15 from "
            "manaCost factor (floor 0.1 per application); damageReductionPercentagePoints=15 adds "
            "0.15 to endurance; ammoSaveChancePercent=15 is a 15% independent save chance per "
            "equipped piece (combined as 1-product(1-p)). Raw crit points need not equal final crit: "
            "Default receives no Generic modifiers, Summon crit is nonstandard, modded DamageClass "
            "may override inheritance. By contrast damageMultiplier=1 multiplies authored base by 1 "
            "(AoE/nearest-event damage floor at 1), damageFraction=0.15 heals 15% of damageDone, and homingStrength=0.15 "
            "lerps velocity per update. Neutral examples (not inserted defaults): velocityRetention=1, "
            "speedMultiplierPerUpdate=1, damageMultiplier/knockbackMultiplier/speedMultiplier=1, hitboxScale/drawScale/scale=1; spreadRadians=0 "
            "has no fan; pierce=-1 is infinite. configure_tile_placement selects tileId>=0; configure_wall_placement selects wallId>=0. The inactive -1 placement field exists only in wire. "
            "Use each card's own bounds/units; no universal zero neutral."
            " Item timing/cost: useTimeSeconds is the base native activation interval; useAnimationSeconds is "
            "the base animation duration. Native manaCost payment is attempted at animation start, not "
            "at every activation inside it; spawn count is a batch count, not a payment count. "
            "Extra recurring payment requires an explicit capability. Player/prefix timing and mana "
            "modifiers can change effective values; do not report base seconds or mana as measured totals."
        ),
        "stackCost": STACK_COST_RULE,
        "armorParamInheritance": "configure_armor params without meaning inherit exact meaning from configure_accessory params of the same name; all own bounds and units still apply.",
        "setBonusParamPrefix": "Matching armor set (head piece only; matching head, body and legs must actually be equipped): ",
        "exclusiveGroup": {
            "scope": "per exact target entity",
            "rule": "At most one call in the same non-empty exclusiveGroup may target one entity.",
            "groups": sorted({
                capability.exclusive_group
                for capability in CAPABILITY_REGISTRY.values()
                if capability.exclusive_group
            }),
        },
        "bindingTarget": (
            "bindings[].action.targetId is the exact entity acted on. The selected action's targets list "
            "is the entity-kind allowlist; spawn_entity targets the entity created, while "
            "use_item_body targets the item body being used. "
            "contactDamage is an independent item-body hitbox lane for primary_use/alternate_use: "
            "spawn_entity with contactDamage=true executes both body contact and projectile spawn without a second binding. "
            "It does not select primaryEntityId or projectile held ownership. "
            "Actual item-body contact requires configure_item_use.disableMeleeHitbox=false and no ammo category: "
            "either may set Item.noMelee and suppress item_body on_hit/on_crit despite contactDamage=true. "
            "Item-body damage uses configure_item_stats.damage; projectile damage uses set_projectile_damage."
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
    return [cap.provider_variant_schema() for cap in CAPABILITY_REGISTRY.values()]


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
        "capabilities": [cap.audit_card() for cap in CAPABILITY_REGISTRY.values()],
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
    "compatible_entity_reference_ids",
    "referenced_entity_requirement_satisfied",
]
