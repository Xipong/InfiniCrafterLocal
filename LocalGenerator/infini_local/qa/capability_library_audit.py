from __future__ import annotations

"""Machine-readable quality audit for the low-level runtime component library.

The audit intentionally evaluates the registry as an API, not as prose.  A row
is green only when schema, prompt, validator, compiler receipt and C# ownership
can all be mechanically traced from the same declaration.
"""

from dataclasses import asdict, dataclass
import importlib
import importlib.util
import math
from pathlib import Path
import re
from typing import Any, Mapping

from infini_local.core.runtime_authoring.capability_registry import (
    BINDING_ACTION_REGISTRY,
    CAPABILITY_REGISTRY,
    ENTITY_KIND_REGISTRY,
    EVENT_KIND_REGISTRY,
    INPUT_KIND_REGISTRY,
    NETWORK_AUTHORITIES,
    CapabilitySpec,
    capability_provider_union,
    compact_capability_catalog,
    runtime_authoring_registry_manifest,
)
from infini_local.core.runtime_authoring.technical_lowering import GLOBAL_TECHNICAL_LOWERINGS, path_matches
from infini_local.qa.capability_witnesses import capability_vertical_slice_report


AUDIT_SCHEMA = "infini.capability-library-audit.v1"
KNOWN_REQUIREMENT_KINDS = frozenset({
    "capability_present",
    "capability_group_present",
    "item_capability_param",
    "at_least_one_param_nonnegative",
    "at_least_one_param_nonzero",
    "binding_input_present",
    "binding_tuple_present",
    "binding_action_reference",
    "conditional_param",
    "non_neutral_param",
    "event_available",
})


@dataclass(frozen=True, slots=True)
class AuditIssue:
    severity: str
    code: str
    path: str
    message: str

    def row(self) -> dict[str, str]:
        return asdict(self)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _resolve_csharp_owner(owner: str) -> Path | None:
    filename = owner.split("::", 1)[0].strip()
    root = _repo_root() / "ModSources" / "InfiniCrafterLocal"
    direct = root / filename
    if direct.is_file():
        return direct
    matches = list(root.rglob(Path(filename).name))
    return matches[0] if len(matches) == 1 else None


def _csharp_owner_issue(owner: str) -> str | None:
    errors: list[str] = []
    references = [row.strip() for row in owner.split("|") if row.strip()]
    if not references:
        return "no owner reference was declared"
    for reference in references:
        path = _resolve_csharp_owner(reference)
        if path is None:
            errors.append(f"{reference}: owner file was not found uniquely")
            continue
        _, separator, raw_symbols = reference.partition("::")
        if not separator or not raw_symbols.strip():
            errors.append(f"{reference}: owner must name at least one method after ::")
            continue
        text = path.read_text("utf-8", errors="ignore")
        missing = [
            symbol
            for symbol in (token.strip() for token in raw_symbols.split("/") if token.strip())
            if re.search(rf"\b{re.escape(symbol)}\s*\(", text) is None
        ]
        if missing:
            errors.append(f"{reference}: missing method symbol(s): {missing}")
    return "; ".join(errors) if errors else None


def _python_owner_issue(owner: str) -> str | None:
    module_name, separator, raw_symbol = owner.partition("::")
    module_name = module_name.strip()
    if not module_name or importlib.util.find_spec(module_name) is None:
        return "owner module was not found"
    if not separator or not raw_symbol.strip():
        return "owner must name a compiler symbol after ::"
    try:
        value: Any = importlib.import_module(module_name)
        for part in raw_symbol.strip().split("."):
            value = getattr(value, part)
    except (ImportError, AttributeError) as exc:
        return f"owner symbol cannot be resolved: {exc}"
    return None if callable(value) else "owner symbol is not callable"


def _number(token: str, constants: Mapping[str, float]) -> float | None:
    value = token.strip().rstrip("fFdDmM").replace("_", "")
    if value == "MathF.Tau":
        return math.tau
    if value in constants:
        return constants[value]
    try:
        return float(value)
    except ValueError:
        return None


def _csharp_constants(root: Path) -> dict[str, float]:
    path = root / "ModSources" / "InfiniCrafterLocal" / "Common" / "InfiniRuntimeLimits.cs"
    text = path.read_text("utf-8", errors="ignore")
    out: dict[str, float] = {}
    for name, raw in re.findall(r"public const (?:int|float|double) (\w+)\s*=\s*([^;]+);", text):
        parsed = _number(raw, {})
        if parsed is not None:
            out[f"InfiniRuntimeLimits.{name}"] = parsed
    return out


def _class_block(text: str, class_name: str) -> str:
    match = re.search(rf"public sealed class {re.escape(class_name)}\b", text)
    if not match:
        return ""
    next_match = re.search(r"\npublic (?:sealed |static )?class ", text[match.end():])
    end = match.end() + next_match.start() if next_match else len(text)
    return text[match.start():end]


def _clamp_bounds(text: str, class_name: str, constants: Mapping[str, float]) -> dict[str, tuple[float, float]]:
    block = _class_block(text, class_name)
    out: dict[str, tuple[float, float]] = {}
    pattern = re.compile(r"(\w+)\s*=\s*Math\.Clamp\(\1(?:\s*<=\s*[^?]+\?\s*[^:]+\s*:\s*\1)?,\s*([^,]+),\s*([^\)]+)\)")
    for name, raw_min, raw_max in pattern.findall(block):
        lo = _number(raw_min, constants)
        hi = _number(raw_max, constants)
        if lo is not None and hi is not None:
            out[name] = (lo, hi)
    return out


def _runtime_param_bound_rows() -> list[dict[str, Any]]:
    root = _repo_root()
    dto_path = root / "ModSources" / "InfiniCrafterLocal" / "Common" / "Models" / "RuntimeProgramSpec.cs"
    text = dto_path.read_text("utf-8", errors="ignore")
    constants = _csharp_constants(root)
    class_bounds = {
        name: _clamp_bounds(text, name, constants)
        for name in (
            "RuntimeSpawnSpec", "RuntimeOverTargetSpec", "RuntimeDamageSpec", "RuntimeHitboxSpec",
            "RuntimeCollisionSpec", "RuntimeParamsSpec", "RuntimeTargetingSpec", "RuntimeLightSpec",
            "RuntimeEventActionSpec", "RuntimeItemContactSpec",
        )
    }
    property_map: dict[str, tuple[str, str]] = {
        "configure_spawn": ("RuntimeSpawnSpec", ""),
        "set_projectile_damage": ("RuntimeDamageSpec", ""),
        "set_projectile_hitbox": ("RuntimeHitboxSpec", ""),
        "set_projectile_collision": ("RuntimeCollisionSpec", ""),
        "spawn_over_target": ("RuntimeOverTargetSpec", ""),
        "emit_light_while_active": ("RuntimeLightSpec", ""),
        "configure_item_contact_hitbox": ("RuntimeItemContactSpec", ""),
    }
    rows: list[dict[str, Any]] = []
    for cap in CAPABILITY_REGISTRY.values():
        if cap.category in {"movement", "controller"} and cap.name != "target_and_fire":
            class_name = "RuntimeParamsSpec"
        elif cap.name == "target_and_fire":
            class_name = "RuntimeTargetingSpec"
        elif cap.category == "event":
            class_name = "RuntimeEventActionSpec"
        elif cap.name in property_map:
            class_name = property_map[cap.name][0]
        else:
            continue
        bounds = class_bounds[class_name]
        for param_name, spec in cap.params.items():
            if spec.kind not in {"integer", "number"}:
                continue
            csharp_name = {
                "shotEntity": "ShotEntityId",
                "entity": "EntityId",
            }.get(param_name, param_name[:1].upper() + param_name[1:])
            csharp = bounds.get(csharp_name)
            if csharp is None:
                # Lifetime is clamped at the entity level, not a sub-spec.
                if cap.name == "set_projectile_lifetime" and param_name == "lifetimeTicks":
                    csharp = (1.0, constants.get("InfiniRuntimeLimits.MaxRuntimeLifetimeTicks", 21600.0))
                else:
                    continue
            authored = (float(spec.minimum), float(spec.maximum)) if spec.minimum is not None and spec.maximum is not None else None
            rows.append({
                "capability": cap.name,
                "param": param_name,
                "csharpClass": class_name,
                "authorBounds": list(authored) if authored else None,
                "csharpBounds": list(csharp),
                "preserved": bool(authored and authored[0] >= csharp[0] and authored[1] <= csharp[1]),
            })
    return rows


def capability_library_audit() -> dict[str, Any]:
    issues: list[AuditIssue] = []
    metrics: dict[str, Any] = {}

    def error(code: str, path: str, message: str) -> None:
        issues.append(AuditIssue("error", code, path, message))

    def warning(code: str, path: str, message: str) -> None:
        issues.append(AuditIssue("warning", code, path, message))

    capability_names = set(CAPABILITY_REGISTRY)
    provider_names = {row["properties"]["fn"]["const"] for row in capability_provider_union()}
    prompt_names = {row["fn"] for row in compact_capability_catalog()}
    manifest = runtime_authoring_registry_manifest()
    manifest_names = {row["fn"] for row in manifest["capabilities"]}
    for projection, names in (("provider", provider_names), ("prompt", prompt_names), ("manifest", manifest_names)):
        if names != capability_names:
            error("registry_projection_mismatch", projection, f"missing={sorted(capability_names - names)} extra={sorted(names - capability_names)}")

    known_slots: dict[str, list[str]] = {}
    reference_params = 0
    numeric_params = 0
    bounded_numeric_params = 0
    semantic_params = 0
    exact_wire_paths = 0
    for cap in CAPABILITY_REGISTRY.values():
        base = f"capabilities.{cap.name}"
        if not cap.summary or not cap.category or not cap.component_slot:
            error("incomplete_capability_identity", base, "summary/category/componentSlot must be declared")
        if not cap.target_kinds or any(kind not in ENTITY_KIND_REGISTRY for kind in cap.target_kinds):
            error("invalid_target_kinds", f"{base}.targetKinds", str(cap.target_kinds))
        if cap.network_authority not in NETWORK_AUTHORITIES:
            error("unknown_network_authority", f"{base}.networkAuthority", cap.network_authority)
        if not cap.performance_budget or not cap.compiler_owner or not cap.csharp_owner or not cap.provenance or not cap.repair_group:
            error("missing_runtime_ownership", base, "budget/compiler/C#/provenance/repairGroup are required")
        python_owner_issue = _python_owner_issue(cap.compiler_owner)
        if python_owner_issue:
            error("missing_python_owner", f"{base}.pythonOwner", f"{cap.compiler_owner}: {python_owner_issue}")
        csharp_owner_issue = _csharp_owner_issue(cap.csharp_owner)
        if csharp_owner_issue:
            error("missing_csharp_owner", f"{base}.csharpOwner", f"{cap.csharp_owner}: {csharp_owner_issue}")
        if not cap.final_wire_paths:
            error("missing_wire_obligation", f"{base}.finalWirePaths", "no output paths")
        for path in cap.final_wire_paths:
            if "*" in path:
                error("broad_wire_pattern", f"{base}.finalWirePaths", path)
            else:
                exact_wire_paths += 1
        for path in cap.technical_lowering_outputs:
            if not any(path_matches(declared, path) for declared in cap.final_wire_paths):
                error("lowering_output_not_wire_output", f"{base}.technicalLoweringOutputs", path)
        if cap.exclusive_group:
            known_slots.setdefault(cap.exclusive_group, []).append(cap.name)
        for requirement in cap.requirements:
            if requirement.kind not in KNOWN_REQUIREMENT_KINDS:
                error("unknown_requirement_kind", f"{base}.requirements", requirement.kind)
            if requirement.capability and requirement.capability not in capability_names:
                error("unknown_requirement_capability", f"{base}.requirements", requirement.capability)
            for name in requirement.any_of:
                if requirement.kind == "capability_group_present" and name not in capability_names:
                    error("unknown_requirement_group_member", f"{base}.requirements", name)
            if requirement.kind == "at_least_one_param_nonzero":
                if not requirement.nonzero_params:
                    error("empty_nonzero_requirement", f"{base}.requirements", requirement.kind)
                for name in requirement.nonzero_params:
                    if name not in cap.params:
                        error("unknown_nonzero_requirement_param", f"{base}.requirements", name)
            if requirement.kind == "binding_input_present":
                if not requirement.any_of:
                    error("empty_binding_input_requirement", f"{base}.requirements", requirement.kind)
                for input_name in requirement.any_of:
                    if input_name not in INPUT_KIND_REGISTRY:
                        error("unknown_requirement_input", f"{base}.requirements", input_name)
            if requirement.kind == "binding_action_reference":
                if not requirement.any_of:
                    error("empty_binding_action_requirement", f"{base}.requirements", requirement.kind)
                for action_name in requirement.any_of:
                    if action_name not in BINDING_ACTION_REGISTRY:
                        error("unknown_requirement_action", f"{base}.requirements", action_name)
            if requirement.kind == "binding_tuple_present":
                if not requirement.any_of:
                    error("empty_binding_tuple_requirement", f"{base}.requirements", requirement.kind)
                for tuple_value in requirement.any_of:
                    parts = tuple_value.split("|")
                    valid_policy = len(parts) == 2 or (
                        len(parts) == 3 and parts[2] in {"contactDamage=true", "contactDamage=false"}
                    )
                    if (
                        not valid_policy
                        or parts[0] not in INPUT_KIND_REGISTRY
                        or parts[1] not in BINDING_ACTION_REGISTRY
                    ):
                        error("invalid_requirement_binding_tuple", f"{base}.requirements", tuple_value)
        for event in (*cap.allowed_events, *cap.emitted_events):
            if event not in EVENT_KIND_REGISTRY:
                error("unknown_event", f"{base}.events", event)
        if cap.activation_spawn_count_param:
            budget_param = cap.params.get(cap.activation_spawn_count_param)
            if budget_param is None or budget_param.kind not in {"integer", "number"}:
                error("invalid_spawn_budget_param", f"{base}.activationSpawnCountParam", cap.activation_spawn_count_param)
        for param_name, spec in cap.params.items():
            ppath = f"{base}.params.{param_name}"
            if not spec.description or not spec.semantic_type:
                error("incomplete_param_semantics", ppath, "description and semanticType are required")
            semantic_params += bool(spec.semantic_type)
            if spec.kind in {"integer", "number"}:
                numeric_params += 1
                if spec.minimum is None or spec.maximum is None:
                    error("unbounded_numeric_param", ppath, "numeric params require min and max")
                else:
                    bounded_numeric_params += 1
                    if float(spec.minimum) > float(spec.maximum):
                        error("reversed_numeric_bounds", ppath, f"{spec.minimum}>{spec.maximum}")
            if spec.reference is not None:
                reference_params += 1
                ref = spec.reference
                if ref.namespace != "entity" or not ref.target_kinds:
                    error("incomplete_typed_reference", ppath, str(ref.card()))
                if any(kind not in ENTITY_KIND_REGISTRY for kind in ref.target_kinds):
                    error("unknown_reference_target_kind", ppath, str(ref.target_kinds))
            elif param_name in {"entity", "shotEntity"}:
                error("untyped_entity_reference", ppath, "entity references must use ReferenceSpec")

    for kind, spec in ENTITY_KIND_REGISTRY.items():
        for required in spec.required_components:
            cap = CAPABILITY_REGISTRY.get(required)
            if cap is None or kind not in cap.target_kinds:
                error("invalid_entity_required_component", f"entityKinds.{kind}.requiredComponents", required)
        for event in spec.base_events:
            if event not in EVENT_KIND_REGISTRY:
                error("invalid_entity_base_event", f"entityKinds.{kind}.baseEvents", event)

    for input_name, input_spec in INPUT_KIND_REGISTRY.items():
        for required in input_spec.required_item_capabilities_any_of:
            if required not in CAPABILITY_REGISTRY or CAPABILITY_REGISTRY[required].target_kinds != ("item_body",):
                error("invalid_input_dependency", f"inputs.{input_name}.requiresItemAnyOf", required)
        for action_name in input_spec.allowed_actions:
            action = BINDING_ACTION_REGISTRY.get(action_name)
            if action is None or input_name not in action.allowed_inputs:
                error("input_action_asymmetry", f"inputs.{input_name}", action_name)
    for action_name, action in BINDING_ACTION_REGISTRY.items():
        for required in action.required_item_capabilities_any_of:
            if required not in CAPABILITY_REGISTRY or CAPABILITY_REGISTRY[required].target_kinds != ("item_body",):
                error("invalid_action_dependency", f"bindingActions.{action_name}.requiresItemAnyOf", required)
        for input_name in action.allowed_inputs:
            input_spec = INPUT_KIND_REGISTRY.get(input_name)
            if input_spec is None or action_name not in input_spec.allowed_actions:
                error("action_input_asymmetry", f"bindingActions.{action_name}", input_name)
        if any(kind not in ENTITY_KIND_REGISTRY for kind in action.target_kinds):
            error("binding_action_unknown_target", f"bindingActions.{action_name}", str(action.target_kinds))
        if action_name == "spawn_entity":
            non_spawnable = [kind for kind in action.target_kinds if not ENTITY_KIND_REGISTRY[kind].spawnable_by_binding]
            if non_spawnable:
                error("binding_action_advertises_unspawnable_kind", f"bindingActions.{action_name}", str(non_spawnable))

    for event_name, event in EVENT_KIND_REGISTRY.items():
        if any(kind not in ENTITY_KIND_REGISTRY for kind in event.source_kinds):
            error("event_unknown_source_kind", f"events.{event_name}", str(event.source_kinds))
        for producer in event.producer_capabilities:
            if producer not in CAPABILITY_REGISTRY:
                error("event_unknown_producer", f"events.{event_name}", producer)

    global_lowerer_ids: set[str] = set()
    global_lowerer_output_count = 0
    for lowerer in GLOBAL_TECHNICAL_LOWERINGS:
        lowerer_id = str(lowerer.get("id") or "")
        base = f"globalLowerers.{lowerer_id or '<missing>'}"
        if not lowerer_id or lowerer_id in global_lowerer_ids:
            error("invalid_global_lowerer_id", base, "id must be non-empty and unique")
        global_lowerer_ids.add(lowerer_id)
        if not lowerer.get("inputs") or not lowerer.get("outputs") or not lowerer.get("equivalence") or not lowerer.get("preserves"):
            error("incomplete_global_lowerer", base, "inputs/outputs/equivalence/preserves are required")
        for output in lowerer.get("outputs", []):
            global_lowerer_output_count += 1
            if "*" in str(output):
                error("broad_global_lowerer_output", f"{base}.outputs", str(output))

    bound_rows = _runtime_param_bound_rows()
    for row in bound_rows:
        if not row["preserved"]:
            error(
                "author_range_exceeds_csharp_clamp",
                f"capabilities.{row['capability']}.params.{row['param']}",
                f"author={row['authorBounds']} C#={row['csharpBounds']}",
            )

    vertical = capability_vertical_slice_report()
    if not vertical["ok"]:
        for row in vertical["rows"]:
            if not row["ok"]:
                error("missing_vertical_slice", f"capabilities.{row['fn']}", str(row.get("authorErrors") or row.get("wireErrors")))

    error_count = sum(issue.severity == "error" for issue in issues)
    warning_count = sum(issue.severity == "warning" for issue in issues)
    criteria = {
        "registryIdentity": not any(issue.code in {"incomplete_capability_identity", "invalid_target_kinds"} for issue in issues),
        "typedParameters": not any(issue.code in {"incomplete_param_semantics", "unbounded_numeric_param", "untyped_entity_reference", "incomplete_typed_reference"} for issue in issues),
        "compositionMetadata": not any(issue.code in {"unknown_requirement_kind", "input_action_asymmetry", "action_input_asymmetry", "invalid_entity_required_component", "binding_action_advertises_unspawnable_kind", "invalid_input_dependency", "invalid_action_dependency", "invalid_spawn_budget_param"} for issue in issues),
        "exactDelivery": not any(issue.code in {"broad_wire_pattern", "missing_wire_obligation", "lowering_output_not_wire_output", "broad_global_lowerer_output", "incomplete_global_lowerer"} for issue in issues),
        "runtimeOwnership": not any(issue.code in {"missing_python_owner", "missing_csharp_owner", "unknown_network_authority"} for issue in issues),
        "rangeParity": not any(issue.code == "author_range_exceeds_csharp_clamp" for issue in issues),
        "projectionParity": not any(issue.code == "registry_projection_mismatch" for issue in issues),
        "verticalSlices": bool(vertical["ok"]),
    }
    weights = {
        "registryIdentity": 10,
        "typedParameters": 15,
        "compositionMetadata": 15,
        "exactDelivery": 15,
        "runtimeOwnership": 15,
        "rangeParity": 10,
        "projectionParity": 10,
        "verticalSlices": 10,
    }
    score = sum(weight for name, weight in weights.items() if criteria[name])
    metrics.update({
        "capabilities": len(CAPABILITY_REGISTRY),
        "entityKinds": len(ENTITY_KIND_REGISTRY),
        "inputs": len(INPUT_KIND_REGISTRY),
        "bindingActions": len(BINDING_ACTION_REGISTRY),
        "events": len(EVENT_KIND_REGISTRY),
        "parameters": sum(len(cap.params) for cap in CAPABILITY_REGISTRY.values()),
        "numericParameters": numeric_params,
        "boundedNumericParameters": bounded_numeric_params,
        "semanticParameters": semantic_params,
        "typedEntityReferences": reference_params,
        "requirements": sum(len(cap.requirements) for cap in CAPABILITY_REGISTRY.values()),
        "bindingDependencyEdges": sum(len(row.required_item_capabilities_any_of) for row in INPUT_KIND_REGISTRY.values()) + sum(len(row.required_item_capabilities_any_of) for row in BINDING_ACTION_REGISTRY.values()),
        "spawnBudgetCapabilities": sum(bool(cap.activation_spawn_count_param) for cap in CAPABILITY_REGISTRY.values()),
        "stationaryMeaningfulCapabilities": sum(cap.meaningful_for_stationary for cap in CAPABILITY_REGISTRY.values()),
        "exactWirePaths": exact_wire_paths,
        "globalTechnicalLowerers": len(GLOBAL_TECHNICAL_LOWERINGS),
        "globalTechnicalLowererOutputs": global_lowerer_output_count,
        "exclusiveGroups": {name: sorted(values) for name, values in known_slots.items()},
        "authorityDistribution": {
            authority: sum(cap.network_authority == authority for cap in CAPABILITY_REGISTRY.values())
            for authority in NETWORK_AUTHORITIES
        },
        "rangeParityRows": len(bound_rows),
        "verticalSliceCount": vertical["capabilityCount"],
    })
    return {
        "schema": AUDIT_SCHEMA,
        "ok": error_count == 0,
        "score": score,
        "scoreMax": sum(weights.values()),
        "criteria": criteria,
        "metrics": metrics,
        "issues": [issue.row() for issue in issues],
        "errorCount": error_count,
        "warningCount": warning_count,
        "rangeParity": bound_rows,
    }


__all__ = ["AUDIT_SCHEMA", "AuditIssue", "capability_library_audit"]
