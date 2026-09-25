"""Compare the actual C# equipment executor with the Author primitive vocabulary.

The grammar parses property declarations and member reads, not a hand-maintained
list of what the runtime allegedly implements. Engine methods containing ref-return
assignments are partially recovered by the grammar: exact AST member reads are
scoped to fixed method signatures, and missing anchors fail closed.
"""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from tree_sitter import Language, Parser, Node
import tree_sitter_c_sharp

from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY


_PARSER = Parser(Language(tree_sitter_c_sharp.language()))
_MODEL_ROOT = Path(__file__).resolve().parents[3] / "ModSources" / "InfiniCrafterLocal"
# These C# fields are not gameplay choices. Archetype is historical metadata;
# changing it cannot change an equipped player's stats or set matching.
_HIDDEN = {
    "Enabled": "Derived exactly from presence of the configured capability.",
    "Archetype": "Historical unused DTO metadata; never dispatched as gameplay.",
}


def _nodes(node: Node, kind: str) -> Iterator[Node]:
    if node.type == kind:
        yield node
    for child in node.named_children:
        yield from _nodes(child, kind)


def _class_properties(data: bytes, class_name: str) -> set[str]:
    root = _PARSER.parse(data).root_node
    for declaration in _nodes(root, "class_declaration"):
        name = next((n for n in declaration.named_children if n.type == "identifier"), None)
        if name is None or data[name.start_byte:name.end_byte] != class_name.encode():
            continue
        properties: set[str] = set()
        for property_node in _nodes(declaration, "property_declaration"):
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
        return properties
    raise ValueError(f"Missing executable C# DTO class {class_name}")


def _method_bounds(data: bytes, signature: bytes, next_signature: bytes) -> tuple[int, int]:
    start = data.find(signature)
    end = data.find(next_signature, start + len(signature)) if start >= 0 else -1
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
    capability = CAPABILITY_REGISTRY[f"configure_{group}"]
    direct = {(spec.wire_name or name)[0].upper() + (spec.wire_name or name)[1:]
              for name, spec in capability.params.items()}
    # Class selectors are Author params of a separate typed operation, but lower
    # into the existing legacy equipment DTO fields consumed by C#.
    prefix = group + "."
    class_paths = CAPABILITY_REGISTRY["add_equipment_damage_bonus"].final_wire_paths
    return direct | {path[len(prefix):][0].upper() + path[len(prefix):][1:]
                     for path in class_paths if path.startswith(prefix)}


def equipment_surface_audit(dto: bytes | None = None, executor: bytes | None = None) -> dict[str, Any]:
    dto = dto if dto is not None else (_MODEL_ROOT / "Common/Models/GeneratedItemData.Model.cs").read_bytes()
    executor = executor if executor is not None else (_MODEL_ROOT / "Content/Items/GeneratedItem.cs").read_bytes()
    accessory = _class_properties(dto, "AccessorySpec")
    armor = _class_properties(dto, "ArmorSpec")
    access_bounds = _method_bounds(executor,
        b"private static void ApplyEquipmentEffects(Player player, AccessorySpec a)",
        b"private static void ApplyEquipmentEffects(Player player, ArmorSpec a)")
    armor_bounds = _method_bounds(executor,
        b"private static void ApplyEquipmentEffects(Player player, ArmorSpec a)",
        b"private static void AddEquipmentLight(Player player")
    set_bounds = _method_bounds(executor,
        b"public override void UpdateArmorSet(Player player)",
        b"public override bool PreDrawInInventory(")
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
    dto = dto if dto is not None else (_MODEL_ROOT / "Common/Models/RuntimeProgramSpec.cs").read_bytes()
    executor = executor if executor is not None else (_MODEL_ROOT / "Common/Runtime/RuntimeProgramExecutor.cs").read_bytes()
    scheduler = scheduler if scheduler is not None else (_MODEL_ROOT / "Common/Runtime/RuntimeDelayedActionScheduler.cs").read_bytes()
    item_events = item_events if item_events is not None else (_MODEL_ROOT / "Content/Items/GeneratedItem.cs").read_bytes()
    projectile_events = projectile_events if projectile_events is not None else (_MODEL_ROOT / "Content/Projectiles/GeneratedProjectile.RuntimeEvents.cs").read_bytes()
    properties = _class_properties(dto, "RuntimeEventActionSpec")
    item_bounds = _method_bounds(item_events, b"private void RunPeriodicItemEvents(", b"public override bool Shoot(")
    reads_by_seam = {
        "executor": _member_reads(executor, (0, len(executor)), b"action"),
        "scheduler": _member_reads(scheduler, (0, len(scheduler)), b"action"),
        "item": _member_reads(item_events, item_bounds, b"action"),
        "projectile": _member_reads(projectile_events, (0, len(projectile_events)), b"action"),
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
        path[len(prefix):][0].upper() + path[len(prefix):][1:]
        for cap in CAPABILITY_REGISTRY.values() if cap.category == "event"
        for path in cap.final_wire_paths if path.startswith(prefix)
    }
    # Identity is authored at calls[].id, not a mechanic parameter.
    hidden = {"Id": "Authored call identity, carried unchanged into the event action."}
    missing = sorted(consumed - declared - hidden.keys())
    unclassified = sorted(properties - declared - hidden.keys())
    return {"ok": not missing and not unclassified, "missingAuthorFields": missing,
            "unclassifiedDtoFields": unclassified, "executableFields": sorted(consumed),
            "intentionallyHidden": hidden}


def runtime_component_surface_audit(dto: bytes | None = None) -> dict[str, Any]:
    """Require explicit Author projection or a reason for every component DTO field."""
    dto = dto if dto is not None else (_MODEL_ROOT / "Common/Models/RuntimeProgramSpec.cs").read_bytes()
    paths = {path for cap in CAPABILITY_REGISTRY.values() for path in cap.final_wire_paths}
    components: dict[str, tuple[str, ...]] = {
        "RuntimeSpawnSpec": ("runtimeProgram.entities[].spawn.",),
        "RuntimeOverTargetSpec": ("runtimeProgram.entities[].spawn.overTarget.",),
        "RuntimeDamageSpec": ("runtimeProgram.entities[].damage.",),
        "RuntimeHitboxSpec": ("runtimeProgram.entities[].hitbox.",),
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
            "ShotEntity": "Obsolete controller DTO slot; target_and_fire uses typed Targeting.ShotEntityId.",
            "IntervalTicks": "Legacy fallback only when Targeting.IntervalTicks is zero; Author always sets positive typed Targeting interval.",
            "SameTargetBias": "Obsolete controller DTO slot; target_and_fire uses typed Targeting.SameTargetBias.",
        },
        "RuntimeSpawnSpec": {
            "OverTarget": "Nested object with its own fully inventoried RuntimeOverTargetSpec fields.",
        },
    }
    unclassified: dict[str, list[str]] = {}
    for cls, prefixes in components.items():
        declared = {
            suffix[0].upper() + suffix[1:]
            for prefix in prefixes for path in paths
            if path.startswith(prefix) and (suffix := path[len(prefix):]) and "." not in suffix
        }
        properties = _class_properties(dto, cls)
        unclassified[cls] = sorted(properties - declared - hidden.get(cls, {}).keys())
        if declared - properties:
            raise ValueError(f"Registry projects absent {cls} DTO fields: {declared - properties}")
    return {"ok": not any(unclassified.values()), "unclassifiedByClass": unclassified,
            "intentionallyHidden": hidden}


def item_gameplay_surface_audit(dto: bytes | None = None) -> dict[str, Any]:
    """Ensure every gameplay/utility-buff DTO field is Author-facing or classified."""
    dto = dto if dto is not None else (_MODEL_ROOT / "Common/Models/GeneratedItemData.Model.cs").read_bytes()
    paths = {path for cap in CAPABILITY_REGISTRY.values() for path in cap.final_wire_paths}
    groups = {
        "GameplaySpec": "gameplay.",
        "GeneratedBuffSpec": "gameplay.generatedBuff.",
        "BuffEntrySpec": "gameplay.extraBuffs[].",
    }
    hidden = {
        "GameplaySpec": {
            "Kind": "Display-only category; never a gameplay router.",
            "Stage": "Historical generation-stage metadata; not executed as an effect.",
            "PowerBudget": "Historical planning metadata; not an engine mechanic.",
            "UseStyle": "Resolved Terraria ItemUseStyleID from authored useStyleName.",
            "BuffCode": "Legacy single Item.buffType; new Author uses explicit multi-buff ExtraBuffs; retained for old wire only.",
            "BuffTime": "Legacy single Item.buffTime; new Author uses explicit multi-buff ExtraBuffs; retained for old wire only.",
            "ExtraBuffs": "Nested list of authored BuffEntrySpec fields.",
            "GeneratedBuff": "Nested authored GeneratedBuffSpec fields.",
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


def structural_surface_audit(dto: bytes | None = None) -> dict[str, Any]:
    """Cross-check structural C# DTOs with Author, Visual and technical owners."""
    from infini_local.core.runtime_authoring import program_schema as author
    from infini_local.core.runtime_authoring import wire_validator as wire
    from infini_local.pipelines.visual_generation_pipeline import visual_response_schema

    dto = dto if dto is not None else (_MODEL_ROOT / "Common/Models/RuntimeProgramSpec.cs").read_bytes()
    pascal = lambda names: {name[0].upper() + name[1:] for name in names}
    program = author.runtime_program_author_schema()
    binding_variants = program["properties"]["bindings"]["items"]["oneOf"]
    bindings = set().union(*(row["properties"] for row in binding_variants))
    policy = set().union(*(row["properties"]["usePolicy"]["properties"] for row in binding_variants))
    actions = set().union(*(row["properties"]["usePolicy"]["properties"]["action"]["properties"] for row in binding_variants))
    prefixes = ("runtimeProgram.entities[].", "runtimeProgram.bindings[].usePolicy.action.placement.")
    paths = {path for cap in CAPABILITY_REGISTRY.values() for path in cap.final_wire_paths}
    entity_components = {path[len(prefixes[0]):].split(".", 1)[0].replace("[]", "")
                         for path in paths if path.startswith(prefixes[0])}
    placement_fields = {path[len(prefixes[1]):] for path in paths if path.startswith(prefixes[1])}
    visual_schema = visual_response_schema(["audit_entity"])
    visual_variants = visual_schema["properties"]["entities"]["items"]["oneOf"]
    visual_model_fields = set().union(*(row["properties"] for row in visual_variants))
    vfx_director_fields = {"ImpactPrompt", "ImpactNegativePrompt"}
    visual_internal = {
        "Role", "SpritePath", "SpriteUrl",
        "SpriteStatus", "SpriteTechnicalScore", "ImpactSpritePath", "ImpactSpriteUrl",
        "ImpactSpriteStatus", "ImpactSpriteTechnicalScore",
    }
    visual_contract = pascal(visual_model_fields) & _class_properties(dto, "RuntimeEntityVisualSpec")
    origins = {
        "RuntimeProgramSpec": pascal(program["properties"]) | {
            "ItemEntityId", "PrimaryOwner", "Limits", "ItemUse", "ItemContact"},
        "RuntimeLimitsSpec": pascal(wire._LIMIT_KEYS),  # compiler-owned fixed safety budgets
        "RuntimeBindingSpec": pascal(bindings) | {"Role"},
        "RuntimeBindingUsePolicySpec": pascal(policy),
        "RuntimeBindingActionSpec": (pascal(actions) - {"PlacementCallId"}) | {"Placement"},
        "RuntimePlacementSpec": pascal(placement_fields),
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
    return {"ok": not any(unclassified.values()) and not any(wire_drift.values()),
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
