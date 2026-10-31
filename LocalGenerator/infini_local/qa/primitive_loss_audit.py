"""Compare the actual C# equipment executor with the Author primitive vocabulary.

The grammar parses property declarations and member reads, not a hand-maintained
list of what the runtime allegedly implements. Engine methods containing ref-return
assignments are partially recovered by the grammar: exact AST member reads are
scoped to fixed method signatures, and missing anchors fail closed.
"""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
import math
import re
from typing import Any

from tree_sitter import Language, Parser, Node
import tree_sitter_c_sharp

from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY


_PARSER = Parser(Language(tree_sitter_c_sharp.language()))
_MODEL_ROOT = Path(__file__).resolve().parents[3] / "ModSources" / "InfiniCrafterLocal"
# Capability presence determines equipment activation; it is not a model choice.
_HIDDEN = {
    "Enabled": "Derived exactly from presence of the configured capability.",
}


def _nodes(node: Node, kind: str) -> Iterator[Node]:
    if node.type == kind:
        yield node
    for child in node.named_children:
        yield from _nodes(child, kind)


def _class_properties(data: bytes, class_name: str) -> set[str]:
    root = _PARSER.parse(data).root_node
    properties: set[str] = set()
    found = False
    for declaration in (*_nodes(root, "class_declaration"), *_nodes(root, "record_declaration")):
        name = next((n for n in declaration.named_children if n.type == "identifier"), None)
        if name is None or data[name.start_byte:name.end_byte] != class_name.encode():
            continue
        found = True
        for property_node in _nodes(declaration, "property_declaration"):
            if property_node.parent != declaration.child_by_field_name("body"):
                continue
            accessor = next((n for n in property_node.named_children if n.type == "accessor_list"), None)
            if accessor is None or not any(
                token.type in {"set", "init"}
                for declaration in accessor.named_children
                for token in declaration.children
            ):
                continue
            identifier = property_node.child_by_field_name("name")
            if identifier is not None:
                properties.add(data[identifier.start_byte:identifier.end_byte].decode())
    if found:
        return properties
    raise ValueError(f"Missing executable C# DTO class {class_name}")


def nullable_number_rejection_bounds(data: bytes, class_name: str, property_name: str) -> list[float] | None:
    """Read the strict nullable scalar setter, including null/finite rejection and storage.

    A changed guard/assignment or comment-only decoy fails this source proof;
    native execution is covered separately by EngineRuntimeChecks.
    """
    def tokens(node: Node) -> bytes:
        if node.type == "comment":
            return b""
        return b"".join(tokens(child) for child in node.children) if node.children else node.text or b""

    for declaration in _nodes(_PARSER.parse(data).root_node, "class_declaration"):
        name = declaration.child_by_field_name("name")
        if name is None or name.text != class_name.encode():
            continue
        for prop in _nodes(declaration, "property_declaration"):
            name = prop.child_by_field_name("name")
            if name is None or name.text != property_name.encode():
                continue
            storage = prop.child_by_field_name("type")
            if storage is None or storage.text not in {b"float?", b"double?", b"int?"}:
                return None
            scalar = storage.text[:-1]
            accessors = list(_nodes(prop, "accessor_declaration"))
            getter = next((row for row in accessors if row.children[0].type == "get"), None)
            setter = next((row for row in accessors if row.children[0].type == "set"), None)
            getter_match = re.fullmatch(rb"get=>([A-Za-z_][A-Za-z_0-9]*);", tokens(getter)) if getter else None
            body = next(_nodes(setter, "block"), None) if setter else None
            statements = [row for row in body.named_children if row.type != "comment"] if body else []
            if not getter_match or len(statements) != 2 or statements[0].type != "if_statement":
                return None
            condition = statements[0].child_by_field_name("condition")
            literal = (rb"-?[0-9]+" if scalar == b"int" else
                       rb"(?:-?[0-9.]+(?:[eE][+-]?[0-9]+)?f|MathF\.(?:PI|Tau))" if scalar == b"float" else
                       rb"(?:-?[0-9.]+(?:[eE][+-]?[0-9]+)?d|Math\.(?:PI|Tau))")
            finite = b"" if scalar == b"int" else rb"\|\|!" + scalar + rb"\.IsFinite\(\1\)"
            guard_pattern = (rb"valueisnot" + scalar + rb"([A-Za-z_][A-Za-z_0-9]*)" + finite
                             + rb"\|\|\1<(" + literal + rb")\|\|\1>(" + literal + rb")")
            guard = re.fullmatch(guard_pattern, tokens(condition)) if condition else None
            consequence = statements[0].child_by_field_name("consequence")
            if (not guard or consequence is None or consequence.type != "throw_statement"
                    or not tokens(consequence).startswith(b"thrownewInvalidDataException(")
                    or statements[0].child_by_field_name("alternative") is not None
                    or tokens(statements[1]) != getter_match[1] + b"=" + guard[1] + b";"):
                return None
            def bound(raw: bytes) -> float:
                if raw in {b"Math.PI", b"MathF.PI"}: return math.pi
                if raw in {b"Math.Tau", b"MathF.Tau"}: return math.tau
                return float(raw.rstrip(b"fd"))
            return [bound(guard[2]), bound(guard[3])]
    return None


def number_rejection_bounds(data: bytes, class_name: str, property_name: str) -> list[float] | None:
    """Prove bounded scalar setters, including a class-local finite guard helper.

    This recognizes exact native guard shapes, not names or declared bounds.
    A changed assignment, missing finite guard or unrecognized helper fails closed.
    """
    nullable = nullable_number_rejection_bounds(data, class_name, property_name)
    if nullable is not None:
        return nullable

    def tokens(node: Node) -> bytes:
        if node.type == "comment":
            return b""
        return b"".join(tokens(child) for child in node.children) if node.children else node.text or b""

    for declaration in _nodes(_PARSER.parse(data).root_node, "class_declaration"):
        name = declaration.child_by_field_name("name")
        if name is None or name.text != class_name.encode():
            continue
        for prop in declaration.child_by_field_name("body").named_children:
            if prop.type != "property_declaration" or prop.child_by_field_name("name").text != property_name.encode():
                continue
            storage = prop.child_by_field_name("type").text
            if storage not in {b"int", b"float", b"double"}:
                return None
            accessors = list(_nodes(prop, "accessor_declaration"))
            getter = next((row for row in accessors if row.children[0].type == "get"), None)
            setter = next((row for row in accessors if row.children[0].type == "set"), None)
            backing = re.fullmatch(rb"get=>([A-Za-z_][A-Za-z_0-9]*);", tokens(getter)) if getter else None
            if not backing or setter is None:
                return None
            literal = rb"-?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?[fd]?"
            direct = re.fullmatch(rb"set=>" + re.escape(backing[1]) + rb"=valueis>=(" + literal + rb")and<=(" + literal + rb")\?value:thrownewInvalidDataException\(.*\);", tokens(setter))
            if direct and storage == b"int":
                return [float(raw) for raw in direct.groups()]
            call = re.fullmatch(rb"set=>" + re.escape(backing[1]) + rb"=([A-Za-z_][A-Za-z_0-9]*)\(value,(" + literal + rb"),(" + literal + rb")\);", tokens(setter))
            if call is None or storage == b"int":
                return None
            helpers = [node for node in declaration.child_by_field_name("body").named_children
                       if node.type == "method_declaration" and node.child_by_field_name("name").text == call[1]]
            if len(helpers) != 1:
                return None
            guard = (b"privatestatic" + storage + call[1] + b"(" + storage + b"value," + storage + b"low," + storage + b"high)=>"
                     + storage + b".IsFinite(value)&&value>=low&&value<=high?value:thrownewInvalidDataException(")
            helper = tokens(helpers[0])
            if not helper.startswith(guard) or not re.fullmatch(rb'"(?:[^"\\]|\\.)*"\);', helper[len(guard):]):
                return None
            return [float(raw.rstrip(b"fd")) for raw in call.groups()[1:]]
    return None


def _method_bounds(data: bytes, signature: bytes, next_signature: bytes | None = None) -> tuple[int, int]:
    start = data.find(signature)
    # The last method in a dedicated owner partial needs no unrelated next hook.
    end = len(data) if next_signature is None else data.find(next_signature, start + len(signature))
    if start < 0 or end < 0 or data.find(signature, start + 1) != -1:
        raise ValueError(f"C# executor ownership anchors changed: {signature!r}")
    return start, end


def _member_reads(data: bytes, bounds: tuple[int, int], root_name: bytes = b"a") -> set[str]:
    found: set[str] = set()
    for member in _nodes(_PARSER.parse(data).root_node, "member_access_expression"):
        if not (bounds[0] <= member.start_byte < member.end_byte <= bounds[1]):
            continue
        children = member.named_children
        if len(children) != 2 or any(node.type != "identifier" for node in children):
            continue
        left, right = (data[node.start_byte:node.end_byte] for node in children)
        if left == root_name and data[member.start_byte:member.end_byte] == root_name + b"." + right:
            found.add(right.decode())
    return found


def _declared(group: str) -> set[str]:
    capability = CAPABILITY_REGISTRY[group]
    direct = {wire[0].upper() + wire[1:]
              for name, spec in capability.params.items()
              for wire in spec.wire_field_names(name)}
    # Class selectors are Author params of a separate typed operation, but lower
    # into the current equipment DTO fields consumed by C#.
    prefix = group + "."
    class_paths = CAPABILITY_REGISTRY["equipment_damage_bonus"].final_wire_paths
    return direct | {path[len(prefix):][0].upper() + path[len(prefix):][1:]
                     for path in class_paths if path.startswith(prefix)}


def equipment_surface_audit(dto: bytes | None = None, executor: bytes | None = None) -> dict[str, Any]:
    dto = dto if dto is not None else (_MODEL_ROOT / "Common/Models/Contracts/GeneratedItemData.Model.cs").read_bytes()
    executor = executor if executor is not None else (_MODEL_ROOT / "Content/Items/GeneratedItem.Equipment.cs").read_bytes()
    accessory = _class_properties(dto, "AccessorySpec")
    armor = _class_properties(dto, "ArmorSpec")
    access_bounds = _method_bounds(executor,
        b"private static void ApplyEquipmentEffects(Player player, AccessorySpec a)",
        b"private static void ApplyEquipmentEffects(Player player, ArmorSpec a)")
    armor_bounds = _method_bounds(executor,
        b"private static void ApplyEquipmentEffects(Player player, ArmorSpec a)",
        b"private static void AddEquipmentLight(Player player")
    set_bounds = _method_bounds(executor, b"public override void UpdateArmorSet(Player player)")
    consumed = {
        "accessory": _member_reads(executor, access_bounds) | {"Defense"},
        "armor": _member_reads(executor, armor_bounds) | _member_reads(executor, set_bounds) | {"Defense", "Slot", "SetKey"},
    }
    properties = {"accessory": accessory, "armor": armor}
    missing: dict[str, list[str]] = {}
    unclassified: dict[str, list[str]] = {}
    for group in ("accessory", "armor"):
        if not consumed[group] <= properties[group]:
            raise ValueError(f"C# executor reads undeclared {group} fields: {consumed[group] - properties[group]}")
        missing[group] = sorted(consumed[group] - _declared(group) - _HIDDEN.keys())
        unclassified[group] = sorted(properties[group] - consumed[group] - _declared(group) - _HIDDEN.keys())
    # The two proof anchors make a parser regression fail, rather than silently
    # yielding an empty executable inventory and reporting perfect parity.
    if "MeleeDamage" not in consumed["accessory"] or "SetBonusMagicDamage" not in consumed["armor"]:
        raise ValueError("C# equipment parser lost known executable references")
    return {
        "ok": not any(missing.values()) and not any(unclassified.values()),
        "missingAuthorFields": sorted(set().union(*map(set, missing.values()))),
        "missingByGroup": missing,
        "unclassifiedDtoFields": unclassified,
        "executableFields": {name: sorted(values) for name, values in consumed.items()},
        "intentionallyHidden": dict(_HIDDEN),
    }


def event_surface_audit(
    dto: bytes | None = None,
    executor: bytes | None = None,
    *,
    scheduler: bytes | None = None,
    item_events: bytes | None = None,
    projectile_events: bytes | None = None,
) -> dict[str, Any]:
    """Check event actions in executor, delayed queue, item and projectile producers."""
    dto = dto if dto is not None else (_MODEL_ROOT / "Common/Models/Contracts/RuntimeProgramSpec.cs").read_bytes()
    executor = executor if executor is not None else (_MODEL_ROOT / "Common/Runtime/RuntimeProgramExecutor.cs").read_bytes()
    scheduler = scheduler if scheduler is not None else (_MODEL_ROOT / "Common/Runtime/RuntimeDelayedActionScheduler.cs").read_bytes()
    item_events = item_events if item_events is not None else (_MODEL_ROOT / "Content/Items/GeneratedItem.RuntimeEvents.cs").read_bytes()
    projectile_events = projectile_events if projectile_events is not None else (_MODEL_ROOT / "Content/Projectiles/GeneratedProjectile.RuntimeEvents.cs").read_bytes()
    properties = _class_properties(dto, "RuntimeEventActionSpec")
    reads_by_seam = {
        "executor": _member_reads(executor, (0, len(executor)), b"action"),
        "scheduler": _member_reads(scheduler, (0, len(scheduler)), b"action"),
        "item": _member_reads(item_events, (0, len(item_events)), b"action"),
        "projectile": _member_reads(projectile_events, (0, len(projectile_events)), b"action"),
        "equipment_reactions": _member_reads(
            (_MODEL_ROOT / "Common/Players/InfiniCraftPlayer.Reactions.cs").read_bytes(),
            (0, len((_MODEL_ROOT / "Common/Players/InfiniCraftPlayer.Reactions.cs").read_bytes())), b"action"),
    }
    if not {"DamageMultiplier", "CooldownTicks"} <= reads_by_seam["executor"] or not (
        {"DelayTicks"} <= reads_by_seam["scheduler"]
        and {"DelayTicks", "PeriodTicks"} <= reads_by_seam["item"]
        and {"DelayTicks", "PeriodTicks"} <= reads_by_seam["projectile"]
    ):
        raise ValueError("C# event parser lost known executable references")
    consumed = set().union(*reads_by_seam.values())
    if not consumed <= properties:
        raise ValueError(f"C# event executors read undeclared action fields: {consumed - properties}")
    prefix = "runtimeProgram.entities[].events[]."
    declared = {
        suffix[0].upper() + suffix[1:]
        for cap in CAPABILITY_REGISTRY.values() if cap.category == "event"
        for path in cap.final_wire_paths if path.startswith(prefix)
        if (suffix := path[len(prefix):].split(".", 1)[0])
    }
    # Identity is authored at calls[].id, not a mechanic parameter.
    hidden = {"Id": "Authored call identity, carried unchanged into the event action."}
    missing = sorted(consumed - declared - hidden.keys())
    unclassified = sorted(properties - declared - hidden.keys())
    return {"ok": not missing and not unclassified, "missingAuthorFields": missing,
            "unclassifiedDtoFields": unclassified, "executableFields": sorted(consumed),
            "intentionallyHidden": hidden}


def _runtime_dto_source() -> bytes:
    # Both partial declarations are authoritative; inspecting only the original
    # file misses the additive entity fields even though strict wire admits them.
    directory = _MODEL_ROOT / "Common/Models/Contracts"
    files = {"RuntimeProgramSpec.cs", "RuntimeMotionComponents.cs"}
    files.update(cls + ".cs" for cap in CAPABILITY_REGISTRY.values()
                 for cls in cap.wire_components.values() if (directory / (cls + ".cs")).is_file())
    return b"\n".join((directory / name).read_bytes() for name in sorted(files))


def _dto_component_types(data: bytes) -> tuple[dict[str, dict[str, str]], dict[str, tuple[str, ...]]]:
    """Read concrete property/type bindings and inheritance, including partials."""
    properties: dict[str, dict[str, str]] = {}
    bases: dict[str, tuple[str, ...]] = {}
    for declaration in _nodes(_PARSER.parse(data).root_node, "class_declaration"):
        name = declaration.child_by_field_name("name").text.decode()
        own = properties.setdefault(name, {})
        base = next((n for n in declaration.named_children if n.type == "base_list"), None)
        if base is not None:
            bases[name] = tuple(n.text.decode() for n in base.named_children)
        body = declaration.child_by_field_name("body")
        for prop in body.named_children:
            if prop.type != "property_declaration":
                continue
            accessor = prop.child_by_field_name("accessors")
            if accessor is None or not any(token.type in {"set", "init"}
                    for row in accessor.named_children for token in row.children):
                continue
            field = prop.child_by_field_name("name").text.decode()
            storage = prop.child_by_field_name("type").text.decode()
            if field in own:
                raise ValueError(f"Duplicate C# DTO property {name}.{field}")
            own[field] = storage
    return properties, bases


def _schema_fields(schema: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    fields: dict[str, list[dict[str, Any]]] = {}
    for name, child in schema.get("properties", {}).items():
        fields.setdefault(name, []).append(child)
    for variant in schema.get("oneOf", []):
        for name, children in _schema_fields(variant).items():
            fields.setdefault(name, []).extend(children)
    return fields


def _inherited_dto_properties(own: dict[str, dict[str, str]], bases: dict[str, tuple[str, ...]],
                              cls: str, visiting: tuple[str, ...] = ()) -> dict[str, str]:
    if cls not in own or cls in visiting:
        raise ValueError(f"Missing or cyclic executable C# DTO class {cls}")
    fields = dict(own[cls])
    for base in bases.get(cls, ()):
        for field, storage in _inherited_dto_properties(own, bases, base, (*visiting, cls)).items():
            if field in fields:
                raise ValueError(f"Shadowed C# DTO property {cls}.{field}")
            fields[field] = storage
    return fields


def _motion_component_surface_audit(dto: bytes) -> dict[str, Any]:
    """Bind registry destinations to actual C# types, not a shadow DTO roster."""
    from infini_local.core.runtime_authoring.capability_registry import PROJECTILE_MODIFIER_COMPONENTS

    own, bases = _dto_component_types(dto)
    unclassified: dict[str, set[str]] = {}
    missing: dict[str, set[str]] = {}
    drift: dict[str, set[str]] = {}
    bindings: dict[str, str] = {}

    def compare(cls: str, actual: set[str], source: set[str], wire: set[str]) -> None:
        # Compare each destination before aggregating diagnostics. Unioning the
        # shared Window owner's inputs first would hide a missing leaf in one
        # capability behind the correct declaration of another capability.
        unclassified.setdefault(cls, set()).update(actual - source)
        missing.setdefault(cls, set()).update(source - actual)
        drift.setdefault(cls, set()).update(actual ^ wire)

    def inherited(cls: str, visiting: tuple[str, ...] = ()) -> dict[str, str]:
        return _inherited_dto_properties(own, bases, cls, visiting)

    def visit(cls: str, paths: set[str], schemas: list[dict[str, Any]]) -> None:
        fields = inherited(cls)
        source_fields = {path.split(".", 1)[0] for path in paths}
        wire_fields: dict[str, list[dict[str, Any]]] = {}
        for schema in schemas:
            for name, children in _schema_fields(schema).items():
                wire_fields.setdefault(name, []).extend(children)
        pascal = lambda names: {name[0].upper() + name[1:] for name in names}
        compare(cls, set(fields), pascal(source_fields), pascal(wire_fields))
        # Record inherited owners too. Newly added unexposed base fields remain
        # unclassified, both here and in every concrete inheritor.
        for base in bases.get(cls, ()):
            base_fields = set(inherited(base))
            compare(base, base_fields, pascal(source_fields) & base_fields, pascal(wire_fields) & base_fields)
        for name in source_fields | wire_fields.keys():
            field = name[0].upper() + name[1:]
            nested_paths = {path[len(name)+1:] for path in paths if path.startswith(name + ".")}
            children = wire_fields.get(name, [])
            if not nested_paths and not any(_schema_fields(child) for child in children):
                continue
            if field not in fields:
                continue  # Missing field is reported by the containing class.
            storage = fields[field].removesuffix("?").removesuffix("[]")
            visit(storage, nested_paths, children)

    entity_fields = inherited("RuntimeEntitySpec")
    for fn, member in PROJECTILE_MODIFIER_COMPONENTS.items():
        cap = CAPABILITY_REGISTRY[fn]
        field = member[0].upper() + member[1:]
        if field not in entity_fields:
            raise ValueError(f"Registry projects absent RuntimeEntitySpec DTO field: {field}")
        storage = entity_fields[field].removesuffix("?")
        is_array = storage.endswith("[]")
        if is_array != (cap.multiplicity == "many_per_target"):
            raise ValueError(f"C# component multiplicity differs from registry: {field}")
        cls = storage.removesuffix("[]")
        bindings[member] = cls
        prefix = f"runtimeProgram.entities[].{member}{'[]' if is_array else ''}."
        paths = {path[len(prefix):] for path in cap.final_wire_paths if path.startswith(prefix)}
        if not paths:
            raise ValueError(f"Missing registry component projection: {fn}")
        visit(cls, paths, [cap.flat_wire_params_schema()])
    # Every declared nested event destination is checked independently, including
    # its native field type, instead of unioning shared DTO inputs across calls.
    event_fields = inherited("RuntimeEventActionSpec")
    for cap in CAPABILITY_REGISTRY.values():
        for member, declared_class in cap.wire_components.items():
            if cap.category != "event":
                raise ValueError(f"Unsupported nested component owner: {cap.name}")
            field = member[0].upper() + member[1:]
            storage = event_fields.get(field, "").removesuffix("?")
            if storage != declared_class:
                raise ValueError(f"Registry/native nested component binding differs: {cap.name}.{member}")
            prefix = f"runtimeProgram.entities[].events[].{member}."
            paths = {path[len(prefix):] for path in cap.final_wire_paths if path.startswith(prefix)}
            schemas = _schema_fields(cap.flat_wire_params_schema()).get(member, [])
            visit(storage, paths, schemas)
    return {"ok": not any(unclassified.values()) and not any(missing.values()) and not any(drift.values()),
            "unclassifiedByClass": {cls: sorted(fields) for cls, fields in unclassified.items()},
            "missingDtoFieldsByClass": {cls: sorted(fields) for cls, fields in missing.items()},
            "wireDtoDriftByClass": {cls: sorted(fields) for cls, fields in drift.items()},
            "componentClasses": bindings}


def runtime_component_surface_audit(dto: bytes | None = None) -> dict[str, Any]:
    """Require explicit Author projection or a reason for every component DTO field."""
    dto = dto if dto is not None else _runtime_dto_source()
    paths = {path for cap in CAPABILITY_REGISTRY.values() for path in cap.final_wire_paths}
    components: dict[str, tuple[str, ...]] = {
        "RuntimeSpawnSpec": ("runtimeProgram.entities[].spawn.",),
        "RuntimeOverTargetSpec": ("runtimeProgram.entities[].spawn.overTarget.",),
        "RuntimeSpawnVelocitySpec": ("runtimeProgram.entities[].spawn.velocityDistribution.",),
        "RuntimeHitTargetSpawnSpec": ("runtimeProgram.entities[].events[].hitTargetSpawn.",),
        "RuntimeDamageSpec": ("runtimeProgram.entities[].damage.",),
        "RuntimeHitboxSpec": ("runtimeProgram.entities[].hitbox.",),
        "RuntimeHitboxCurveSpec": ("runtimeProgram.entities[].hitboxCurve.",),
        "RuntimeTurnModifierSpec": ("runtimeProgram.entities[].turnModifier.",),
        "RuntimeSpeedModifierSpec": ("runtimeProgram.entities[].speedModifier.",),
        "RuntimeHomingModifierSpec": ("runtimeProgram.entities[].homingModifier.",),
        "RuntimeNpcAttractionSpec": ("runtimeProgram.entities[].npcAttraction.",),
        "RuntimeVisualScaleCurveSpec": ("runtimeProgram.entities[].visualScaleCurve.",),
        "RuntimeCollisionSpec": ("runtimeProgram.entities[].collision.",),
        "RuntimeParamsSpec": ("runtimeProgram.entities[].movement.params.",
                              "runtimeProgram.entities[].controller.params."),
        "RuntimeTargetingSpec": ("runtimeProgram.entities[].targeting.",),
        "RuntimeLightSpec": ("runtimeProgram.entities[].light.",),
        "RuntimeItemUseSpec": ("runtimeProgram.itemUse.",),
        "RuntimeItemContactSpec": ("runtimeProgram.itemContact.",),
    }
    hidden: dict[str, dict[str, str]] = {
        "RuntimeParamsSpec": {
            "PowerMultiplier": "Retained-v5 coupled charge scalar only; fresh Author independently projects chargeDamageMultiplier, knockbackMultiplier and speedMultiplier. Absent all three preserves the old saved runtime, and current controls require this old bag field to stay zero.",
        },
        "RuntimeSpawnSpec": {
            "OverTarget": "Nested object with its own fully inventoried RuntimeOverTargetSpec fields.",
            "VelocityDistribution": "Nested exact authored union with fully inventoried RuntimeSpawnVelocitySpec fields; absence preserves old constant wire.",
        },
    }
    unclassified: dict[str, list[str]] = {}
    own, bases = _dto_component_types(dto)
    for cls, prefixes in components.items():
        declared = {
            suffix[0].upper() + suffix[1:]
            for prefix in prefixes for path in paths
            if path.startswith(prefix) and (suffix := path[len(prefix):]) and "." not in suffix
        }
        properties = set(_inherited_dto_properties(own, bases, cls))
        unclassified[cls] = sorted(properties - declared - hidden.get(cls, {}).keys())
        if declared - properties:
            raise ValueError(f"Registry projects absent {cls} DTO fields: {declared - properties}")
    motion = _motion_component_surface_audit(dto)
    unclassified.update(motion["unclassifiedByClass"])
    return {**motion, "ok": not any(unclassified.values()) and motion["ok"],
            "unclassifiedByClass": unclassified, "intentionallyHidden": hidden}


def item_gameplay_surface_audit(dto: bytes | None = None) -> dict[str, Any]:
    """Ensure every gameplay/utility-buff DTO field is Author-facing or classified."""
    dto = dto if dto is not None else (_MODEL_ROOT / "Common/Models/Contracts/GeneratedItemData.Model.cs").read_bytes()
    dto += b"\n" + (_MODEL_ROOT / "Common/Models/Contracts/GeneratedCombatBuffSpec.cs").read_bytes()
    paths = {path for cap in CAPABILITY_REGISTRY.values() for path in cap.final_wire_paths}
    groups = {
        "GameplaySpec": "gameplay.",
        "RuntimeUseConditionSpec": "gameplay.useConditions[].",
        "GeneratedBuffSpec": "gameplay.generatedBuff.",
        "GeneratedCombatBuffSpec": "gameplay.generatedBuff.combat.",
        "BuffEntrySpec": "gameplay.extraBuffs[].",
    }
    hidden = {
        "GeneratedBuffSpec": {"Combat": "Nested authored GeneratedCombatBuffSpec fields; audited individually below."},
        "GameplaySpec": {
            "Kind": "Display-only category; never a gameplay router.",
            "UseStyle": "Resolved Terraria ItemUseStyleID from authored useStyleName.",
            "ExtraBuffs": "Nested list of authored BuffEntrySpec fields.",
            "GeneratedBuff": "Nested authored GeneratedBuffSpec fields.",
            "UseConditions": "Nested authored RuntimeUseConditionSpec input-local gates.",
            "UseConditionMode": "Existing persisted item-wide gate, executed by UseBlockedReason before an input-local gate; fresh Author expresses it with two explicit input calls.",
            "UseConditionMinLife": "Inclusive life threshold of the existing persisted item-wide gate.",
            "UseConditionMinMana": "Inclusive mana threshold of the existing persisted item-wide gate.",
        },
    }
    unclassified: dict[str, list[str]] = {}
    for cls, prefix in groups.items():
        declared = {
            suffix[0].upper() + suffix[1:]
            for path in paths if path.startswith(prefix)
            if (suffix := path[len(prefix):]) and "." not in suffix and "[" not in suffix
        }
        properties = _class_properties(dto, cls)
        unclassified[cls] = sorted(properties - declared - hidden.get(cls, {}).keys())
        if declared - properties:
            raise ValueError(f"Registry projects absent {cls} DTO fields: {declared - properties}")
    return {"ok": not any(unclassified.values()), "unclassifiedByClass": unclassified,
            "intentionallyHidden": hidden}


def placed_body_surface_audit(dto: bytes | None = None) -> dict[str, Any]:
    return _placed_component_surface_audit("placed_sprite", "RuntimePlacedBodySpec", dto)


def placed_vfx_surface_audit(dto: bytes | None = None) -> dict[str, Any]:
    return _placed_component_surface_audit("placed_vfx", "RuntimePlacedVfxSpec", dto)


def placed_light_surface_audit(dto: bytes | None = None) -> dict[str, Any]:
    return _placed_component_surface_audit("placed_light", "RuntimePlacedLightSpec", dto)


def _placed_component_surface_audit(fn: str, class_name: str, dto: bytes | None) -> dict[str, Any]:
    """Classify nested placed DTO storage/bounds, not GPU execution."""
    dto = dto if dto is not None else (_MODEL_ROOT / "Common/Models/Contracts/RuntimeProgramSpec.cs").read_bytes()
    cap = CAPABILITY_REGISTRY[fn]
    expected = {(spec.wire_name or name)[0].upper() + (spec.wire_name or name)[1:]:
                ("double" if spec.consumer_storage == "float64" else "float") if spec.kind == "number"
                else "int" if spec.kind == "integer" else "bool" if spec.kind == "boolean"
                else "string" if spec.required else "string?"
                for name, spec in cap.params.items() if name != "placementCallId"}
    actual: dict[str, str] = {}
    block = ""
    for declaration in _nodes(_PARSER.parse(dto).root_node, "class_declaration"):
        name = declaration.child_by_field_name("name")
        if name is None or dto[name.start_byte:name.end_byte].decode() != class_name:
            continue
        # Inspect code only: comments/string literals cannot satisfy a guard.
        code = bytearray(dto[declaration.start_byte:declaration.end_byte])
        for child in _nodes(declaration, "comment"):
            code[child.start_byte-declaration.start_byte:child.end_byte-declaration.start_byte] = b" " * (child.end_byte-child.start_byte)
        for child in _nodes(declaration, "string_literal"):
            code[child.start_byte-declaration.start_byte:child.end_byte-declaration.start_byte] = b" " * (child.end_byte-child.start_byte)
        for nested in _nodes(declaration, "class_declaration"):
            if nested != declaration:
                code[nested.start_byte-declaration.start_byte:nested.end_byte-declaration.start_byte] = b" " * (nested.end_byte-nested.start_byte)
        block = code.decode()
        for prop in _nodes(declaration, "property_declaration"):
            if prop.parent != declaration.child_by_field_name("body"):
                continue
            identifier, storage = prop.child_by_field_name("name"), prop.child_by_field_name("type")
            if identifier is not None and storage is not None:
                actual[dto[identifier.start_byte:identifier.end_byte].decode()] = dto[storage.start_byte:storage.end_byte].decode()
    wire = {name[0].upper() + name[1:] for name in cap.params if name != "placementCallId"}
    import re
    bounds: dict[str, list[int | float]] = {}
    number = r"(-?\d+(?:\.\d+)?)"
    for field, low, high in re.findall(r"(\w+)\s+is\s*<\s*" + number + r"\s+or\s*>\s*" + number, block):
        bounds[field] = [float(low), float(high)]
    unit = re.search(r"bool\s+Unit\(double\s+(\w+)\)\s*=>\s*double\.IsFinite\(\1\)\s*&&\s*\1\s*>=\s*" + number + r"\s*&&\s*\1\s*<=\s*" + number, block)
    if unit:
        for field in re.findall(r"!Unit\((\w+)\)", block):
            bounds[field] = [float(unit.group(2)), float(unit.group(3))]
    expected_bounds = {name[0].upper() + name[1:]: [spec.minimum, spec.maximum]
                       for name, spec in cap.params.items() if spec.kind in {"integer", "number"}}
    finite = {field for field in expected_bounds
              if re.search(r"!double\.IsFinite\(" + re.escape(field) + r"\)", block)
              or (unit and re.search(r"!Unit\(" + re.escape(field) + r"\)", block))}
    required_finite = {name[0].upper()+name[1:] for name, spec in cap.params.items() if spec.kind == "number"}
    return {"ok": actual == expected and wire == set(expected) and bounds == expected_bounds
                  and finite == required_finite and "Math.Clamp" not in block,
            "boundsByField": bounds, "expectedBoundsByField": expected_bounds,
            "finiteFields": sorted(finite),
            "storageByField": actual, "expectedStorageByField": expected,
            "unclassifiedDtoFields": sorted(set(actual)-set(expected)),
            "missingDtoFields": sorted(set(expected)-set(actual)),
            "wireDtoDrift": sorted(set(actual)^wire)}


def item_effect_group_surface_audit(dto: bytes | None = None) -> dict[str, Any]:
    """A named container cannot grow item stats or a second undocumented effect slot."""
    from infini_local.core.runtime_authoring.wire_validator import _item_effect_group_wire_schema

    dto = dto if dto is not None else (_MODEL_ROOT / "Common/Models/Contracts/RuntimeItemEffectGroupSpec.cs").read_bytes()
    prefix = "runtimeProgram.effectGroups[]."
    fields = {path[len(prefix):].split(".", 1)[0].replace("[]", "")
              for cap in CAPABILITY_REGISTRY.values() for path in cap.final_wire_paths if path.startswith(prefix)}
    pascal = lambda names: {name[0].upper() + name[1:] for name in names}
    actual = _class_properties(dto, "RuntimeItemEffectGroupSpec")
    wire_fields = set(_item_effect_group_wire_schema()["properties"])
    return {"ok": actual == pascal(fields) == pascal(wire_fields),
            "unclassifiedDtoFields": sorted(actual - pascal(fields)),
            "missingDtoFields": sorted(pascal(fields) - actual),
            "wireDtoDrift": sorted(actual ^ pascal(wire_fields))}


def weapon_ammo_surface_audit(dto: bytes | None = None) -> dict[str, Any]:
    """Exact typed native-ammo choices, without an unregistered weapon profile."""
    dto = dto if dto is not None else (_MODEL_ROOT / "Common/Models/Contracts/RuntimeWeaponAmmoSpec.cs").read_bytes()
    expected = {name[0].upper() + name[1:] for name in CAPABILITY_REGISTRY["weapon_ammo"].params}
    actual = _class_properties(dto, "RuntimeWeaponAmmoSpec")
    return {"ok": actual == expected, "unclassifiedDtoFields": sorted(actual - expected),
            "missingDtoFields": sorted(expected - actual)}


def structural_surface_audit(dto: bytes | None = None) -> dict[str, Any]:
    """Cross-check structural C# DTOs with Author, Visual and technical owners."""
    import infini_local.core.runtime_authoring.program_schema as author
    import infini_local.core.runtime_authoring.wire_validator as wire
    from infini_local.pipelines.visual.contract import visual_response_schema

    dto = dto if dto is not None else _runtime_dto_source()
    pascal = lambda names: {name[0].upper() + name[1:] for name in names}
    program = author.runtime_program_author_schema()
    binding_variants = program["properties"]["bindings"]["items"]["oneOf"]
    bindings = set().union(*(row["properties"] for row in binding_variants))
    policy = (bindings - {"id", "input"}) | {"action", "stackCost", "contactDamage"}  # exact fixed wire lanes + every current source policy member
    actions = set().union(*(row["properties"].get("action", {}).get("properties", {}) for row in binding_variants))
    actions.update({"kind", "targetId"})  # exact registry-selected fixed/body reference projections
    prefixes = ("runtimeProgram.entities[].", "runtimeProgram.bindings[].usePolicy.action.placement.")
    paths = {path for cap in CAPABILITY_REGISTRY.values() for path in cap.final_wire_paths}
    runtime_capability_roots = {path.split(".")[1].replace("[]", "") for path in paths if path.startswith("runtimeProgram.")}
    entity_components = {path[len(prefixes[0]):].split(".", 1)[0].replace("[]", "")
                         for path in paths if path.startswith(prefixes[0])}
    placement_fields = {path[len(prefixes[1]):].split(".", 1)[0] for path in paths if path.startswith(prefixes[1])}
    visual_schema = visual_response_schema(["audit_entity"])
    visual_variants = visual_schema["properties"]["entities"]["items"]["oneOf"]
    visual_model_fields = set().union(*(row["properties"] for row in visual_variants))
    vfx_director_fields = {"ImpactPrompt", "ImpactNegativePrompt", "ImpactCanvasSize"}
    visual_internal = {
        "Role", "SpritePath", "SpriteUrl",
        "SpriteStatus", "SpriteTechnicalScore", "ImpactSpritePath", "ImpactSpriteUrl",
        "ImpactSpriteStatus", "ImpactSpriteTechnicalScore",
    }
    visual_contract = pascal(visual_model_fields) & _class_properties(dto, "RuntimeEntityVisualSpec")
    origins = {
        "RuntimeProgramSpec": pascal(program["properties"]) | {
            "ItemEntityId", "PrimaryOwner", "Limits", "ItemUse", "ItemContact"} | pascal(runtime_capability_roots),
        "RuntimeLimitsSpec": pascal(wire._LIMIT_KEYS),  # compiler-owned fixed safety budgets
        "RuntimeBindingSpec": pascal(bindings - policy) | {"Role", "UsePolicy"},
        "RuntimeBindingUsePolicySpec": pascal(policy),
        "RuntimeBindingActionSpec": (pascal(actions) - {"PlacementCallId"}) | {"Placement"},
        "RuntimePlacementSpec": pascal(placement_fields),
        "RuntimePlacedBodySpec": pascal(wire._PLACED_BODY_KEYS),
        "RuntimePlacedLightSpec": pascal(CAPABILITY_REGISTRY["placed_light"].params.keys() - {"placementCallId"}),
        "RuntimePlacedVfxSpec": pascal(CAPABILITY_REGISTRY["placed_vfx"].params.keys() - {"placementCallId"}),
        "RuntimeEntitySpec": pascal(author.entity_schema()["properties"]) | pascal(entity_components)
                             | {"Visual", "VisualRole"},
        "RuntimeEntityVisualSpec": visual_contract | vfx_director_fields | visual_internal,
        "RuntimeMovementSpec": pascal(wire._DRIVER_KEYS),
        "RuntimeControllerSpec": pascal(wire._DRIVER_KEYS),
    }
    accepted_wire = {
        "RuntimeProgramSpec": wire._RUNTIME_KEYS,
        "RuntimeLimitsSpec": wire._LIMIT_KEYS,
        "RuntimeBindingSpec": wire._BINDING_KEYS,
        "RuntimeBindingUsePolicySpec": wire._USE_POLICY_KEYS,
        "RuntimeBindingActionSpec": wire._BINDING_ACTION_KEYS,
        "RuntimePlacementSpec": wire._PLACEMENT_KEYS,
        "RuntimePlacedBodySpec": wire._PLACED_BODY_KEYS,
        "RuntimePlacedLightSpec": CAPABILITY_REGISTRY["placed_light"].params.keys() - {"placementCallId"},
        "RuntimePlacedVfxSpec": CAPABILITY_REGISTRY["placed_vfx"].params.keys() - {"placementCallId"},
        "RuntimeEntitySpec": wire._ENTITY_KEYS,
        "RuntimeEntityVisualSpec": wire._VISUAL_KEYS,
        "RuntimeMovementSpec": wire._DRIVER_KEYS,
        "RuntimeControllerSpec": wire._DRIVER_KEYS,
    }
    unclassified: dict[str, list[str]] = {}
    wire_drift: dict[str, list[str]] = {}
    for cls, owner_fields in origins.items():
        properties = _class_properties(dto, cls)
        unclassified[cls] = sorted(properties - owner_fields)
        wire_drift[cls] = sorted(properties ^ pascal(accepted_wire[cls]))
    placed_storage = placed_body_surface_audit(dto)
    placed_light = placed_light_surface_audit(dto)
    placed_vfx = placed_vfx_surface_audit(dto)
    effect_groups = item_effect_group_surface_audit()
    weapon_ammo = weapon_ammo_surface_audit()
    return {"ok": not any(unclassified.values()) and not any(wire_drift.values()) and placed_storage["ok"] and placed_light["ok"] and placed_vfx["ok"] and effect_groups["ok"] and weapon_ammo["ok"],
            "placedBodyStorage": placed_storage,
            "placedLightStorage": placed_light,
            "placedVfxStorage": placed_vfx,
            "itemEffectGroups": effect_groups,
            "weaponAmmo": weapon_ammo,
            "unclassifiedByClass": unclassified, "wireDtoDriftByClass": wire_drift,
            "visualStageFields": sorted(visual_contract),
            "vfxDirectorFields": sorted(vfx_director_fields),
            "technicalVisualFields": sorted(visual_internal)}


def main() -> int:
    import json
    report = {"equipment": equipment_surface_audit(), "events": event_surface_audit(),
              "runtimeComponents": runtime_component_surface_audit(),
              "itemGameplay": item_gameplay_surface_audit(),
              "structural": structural_surface_audit()}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(row["ok"] for row in report.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
