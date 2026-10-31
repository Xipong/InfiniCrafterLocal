"""Typed Author parameter contracts and exact schema/wire projections.

These declarations are independent of the capability inventory. Registry owners
compose them; consumers read the same types without initializing that inventory.
"""
from __future__ import annotations

import copy
import json
import math
import struct
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Iterable, Mapping


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
    exclusive_minimum: float | None = None
    exclusive_maximum: float | None = None
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
    consumer_storage: str = ""
    consumer_preserve_nonzero: bool = False
    properties: Mapping[str, ParamSpec] = field(default_factory=lambda: MappingProxyType({}), compare=False)
    alternatives: tuple[ParamSpec, ...] = ()
    wire_literals: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}), compare=False)
    wire_enum: Mapping[Any, Any] = field(default_factory=lambda: MappingProxyType({}), compare=False)
    wire_offset: int = 0
    min_properties: int | None = None
    omission_condition: OmissionCondition | None = None
    wire_presence_requires_receipt: bool = False
    # Additive neutral leaf: fresh compilation emits its omission receipt, but
    # saved wire may retain historical absence without inventing that receipt.
    wire_preserve_absence: bool = False
    shared_type: str = ""
    # Explicit numeric wire contract. Predecessors are receipt paths only, never Author aliases.
    predecessor_names: tuple[str, ...] = ()
    previous_author_names: tuple[str, ...] = ()  # Same-domain saved receipt spellings only.
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
                "context": "same_target.projectile_collision.updatesPerTick" if self.wire_updates_power else None,
                "rounding": self.wire_rounding or "exact",
                "wireMinimum": self.wire_minimum, "wireMaximum": self.wire_maximum,
                "predecessorNames": list(self.predecessor_names), "previousAuthorNames": list(self.previous_author_names), "authorUnits": self.units,
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
            out["targetContext"] = "same target's unique projectile_collision.updatesPerTick"
            out["boundsAtUpdatesPerTick1To6"] = [
                list(self.contextual_author_bounds(updates_per_tick=n).values()) for n in range(1, 7)]
        return out

    def contextual_author_bounds(self, *, updates_per_tick: int | None = None) -> dict[str, Any]:
        """Human bounds for one validated target clock; static schema covers their union."""
        if not self.wire_kind or not self.wire_updates_power:
            return {"minimum": self.minimum, "maximum": self.maximum}
        factor = self._update_factor(updates_per_tick)
        return {"minimum": self.wire_minimum * self.wire_divisor * factor / self.wire_multiplier
                    if self.wire_minimum is not None else None,
                "maximum": self.wire_maximum * self.wire_divisor * factor / self.wire_multiplier
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
                   if head == name or head in spec.predecessor_names or head in spec.previous_author_names]
        if len(matches) != 1:
            return None
        name, spec = matches[0]
        rest = spec.canonical_receipt_leaf_path(tail) if separator else ""
        return name + ("." + rest if rest else "") if rest is not None else None

    def wire_schema(self) -> dict[str, Any]:
        """Engine-domain scalar schema; never reuse changed Author units for wire."""
        if not self.wire_kind:
            if self.alternatives:
                return {"oneOf": [variant.wire_schema() for variant in self.alternatives]}
            if self.properties:
                # Closed nested DTO records (e.g. motion Window). Leaf wire
                # names remain full relative paths for compiler provenance.
                return {"type": "object", "additionalProperties": False,
                        "properties": {(spec.wire_name or name).rsplit(".", 1)[-1]: spec.wire_schema()
                                       for name, spec in self.properties.items()},
                        "required": [(spec.wire_name or name).rsplit(".", 1)[-1]
                                     for name, spec in self.properties.items() if spec.required]}
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

    def flat_wire_variants(self, name: str) -> tuple[tuple[dict[str, Any], tuple[str, ...]], ...]:
        """Schema fragments for the same declared projection, not another writer."""
        fields = self.wire_field_names(name)
        if self.structured and fields and all(path.startswith(name + ".") for path in fields):
            return (({name: self.wire_schema()}, (name,) if self.required else ()),)
        if self.alternatives:
            return tuple(row for variant in self.alternatives for row in variant.flat_wire_variants(name))
        properties = {key: {"const": value} for key, value in self.wire_literals.items()}
        required = tuple(properties)
        variants = ((properties, required),)
        if self.properties:
            for key, child in self.properties.items():
                variants = tuple(({**left, **right}, tuple(dict.fromkeys((*lr, *rr))))
                    for left, lr in variants for right, rr in child.flat_wire_variants(key))
            return variants
        if not self.wire_literals or self.wire_name:
            key = self.wire_name or name
            return (({**properties, key: self.wire_schema()},
                     (*required, key) if self.required else required),)
        return variants

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
                    **({"nonzeroMustRemainNonzero": True} if self.consumer_preserve_nonzero else {}),
                    "rule": "nonneutral_must_remain_nonneutral",
                    "meaning": "Deterministic lowering and finite float32 storage must preserve non-neutral values as non-neutral; exact neutral is allowed. Validation never rewrites Author values."}
        if self.consumer_storage == "float64":
            return {"storage": "float64", "rule": "finite_double_no_normalization",
                    "meaning": "Preserves the admitted JSON number; no float32 guard, rounding or replacement."}
        constraint = {"storage": self.consumer_storage, "neutral": self.neutral,
                      **({"nonzeroMustRemainNonzero": True} if self.consumer_preserve_nonzero else {}),
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
        if type(value) in (int, float):
            if self.exclusive_minimum is not None and value <= self.exclusive_minimum:
                return f"value must be > {self.exclusive_minimum}"
            if self.exclusive_maximum is not None and value >= self.exclusive_maximum:
                return f"value must be < {self.exclusive_maximum}"
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
        if self.consumer_preserve_nonzero and value != 0 and stored == 0:
            return "nonzero value collapses to zero in float32 consumer storage"
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
        if self.exclusive_minimum is not None:
            out["exclusiveMinimum"] = self.exclusive_minimum
        if self.exclusive_maximum is not None:
            out["exclusiveMaximum"] = self.exclusive_maximum
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


def author_parameter_shape(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Present a registry schema in the same notation as scalar Author params.

    Only schema nodes are transformed: literal enum/default/reference/projection
    data remain untouched. Object requiredness becomes per-property optionality;
    oneOf branches and additionalProperties retain their exact schema meaning.
    The validator/provider schema is never changed by this presentation view.
    """
    names = {"description": "meaning", "minimum": "min", "maximum": "max",
             "x-infini-units": "units", "x-infini-reference": "reference",
             "x-infini-neutral": "neutral", "x-infini-consumerConstraint": "consumerConstraint",
             "x-infini-authorProjection": "projectionConstraints"}
    result = {}
    for key, value in schema.items():
        if key == "x-infini-semanticType":
            # Same non-executable descriptive label omitted by scalar cards.
            continue
        if key == "required" and isinstance(schema.get("properties"), dict):
            # A JSON-schema composition may require a name declared in another
            # branch. Per-property optionality cannot express that constraint.
            nonlocal_names = [name for name in value if name not in schema["properties"]]
            if nonlocal_names:
                result[key] = nonlocal_names
            continue
        if key == "properties" and isinstance(value, dict):
            required = schema.get("required", [])
            result[key] = {}
            for name, child in value.items():
                row = author_parameter_shape(child)
                if name not in required:
                    row["optional"] = True
                result[key][name] = row
        elif key in {"oneOf", "anyOf", "allOf"} and isinstance(value, list):
            result[key] = [author_parameter_shape(child) for child in value]
        elif key in {"items", "additionalProperties"} and isinstance(value, dict):
            result[key] = author_parameter_shape(value)
        else:
            result[names.get(key, key)] = copy.deepcopy(value)
    return result
