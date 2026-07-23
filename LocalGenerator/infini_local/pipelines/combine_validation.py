from __future__ import annotations

import json
from copy import deepcopy
from typing import Any
from infini_local.core.boundary_models import runtime_plan_boundary_report
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.item_identity_tools import item_bool, item_field, item_num, name_of, slug, stable_hash
from infini_local.core.parent_role_facts import (
    placeable_only_parent_obligation,
    sole_strong_parent_role_obligation,
    strong_parent_roles,
)
from infini_local.core.runtime_authoring.reports import (
    compile_runtime_plan_to_genome_result,
    runtime_plan_validation_report,
)
from infini_local.core.runtime_authoring.result_identity import (
    effective_runtime_result_kind,
    project_runtime_result_identity,
)
from infini_local.core.runtime_authoring.function_contract_registry import ROOT_EXECUTOR_FUNCTION_NAMES
from infini_local.core.runtime_authoring.normalize import runtime_plan
from infini_local.core.runtime_authoring.structural import find_call
from infini_local.core.runtime_contracts import validate_structural_planner_contract
from infini_local.core.json_debug import bounded_json_dumps
from infini_local.pipelines.author_item_contract import strict_author_item_v3_report
from infini_local.pipelines.combine_balance import preservation_score
from infini_local.pipelines.result_identity_policy import (
    canonical_for_result,
    category_policy,
    coerce_category_by_policy,
    inh_for_parent,
    normalize_category,
    required_anchors_from_tags,
    bad_result_name,
    rep_for_parent,
)
from infini_local.pipelines.item_power_knowledge import (
    build_item_knowledge,
    generation_depth,
    recipe_meta,
    tags_of,
)
from infini_local.pipelines.engine_pressure_metrics import (
    projectile_pressure_envelope_report,
)


def _parent_role_preservation_report(
    data: dict[str, Any],
    a: dict[str, Any] | None,
    b: dict[str, Any] | None,
) -> dict[str, Any]:
    obligation = sole_strong_parent_role_obligation(a, b)
    if not obligation["applicable"]:
        return {
            "ok": True,
            "applicable": False,
            "parentStrongRoles": obligation["strongParentRoles"],
        }
    role = str(obligation["strongParentRoles"][0])
    expected_kind = str(obligation["expectedResultKind"])
    plan = data.get("runtimePlan")
    plan = plan if isinstance(plan, dict) else {}
    result_kind = effective_runtime_result_kind(data)
    report: dict[str, Any] = {
        "ok": result_kind == expected_kind,
        "applicable": True,
        "parentStrongRoles": [role],
        "expectedResultKind": expected_kind,
        "actualResultKind": result_kind,
    }
    if role != "armor":
        return report
    expected_slots = set(obligation["expectedArmorSlots"])
    stats = next(
        (
            call.get("params")
            for call in plan.get("engineCalls") or []
            if isinstance(call, dict)
            and call.get("fn") == "set_item_stats"
            and isinstance(call.get("params"), dict)
        ),
        {},
    )
    authored_slot = str((stats or {}).get("armorSlot") or "").strip()
    report.update({
        "ok": result_kind == "armor" and authored_slot in expected_slots,
        "expectedArmorSlots": sorted(expected_slots),
        "actualArmorSlot": authored_slot,
    })
    return report


def _consumable_parent_economy_report(
    data: dict[str, Any],
    a: dict[str, Any] | None,
    b: dict[str, Any] | None,
) -> dict[str, Any]:
    if effective_runtime_result_kind(data) != "consumable_weapon":
        return {"ok": True, "applicable": False}
    # Reusable durable gear: strong weapon/tool/armor/accessory role and consumable
    # is not explicitly True (False or missing both count as durable).
    reusable_gear = [
        name_of(parent)
        for parent in (a, b)
        if isinstance(parent, dict)
        and item_field(parent, "consumable", None) is not True
        and bool(strong_parent_roles(parent) & {"weapon", "tool", "accessory", "armor"})
    ]
    return {
        "ok": not reusable_gear,
        "applicable": bool(reusable_gear),
        "reusableGearParents": reusable_gear,
        "actualResultKind": "consumable_weapon",
    }


def _placeable_parent_role_report(
    data: dict[str, Any],
    a: dict[str, Any] | None,
    b: dict[str, Any] | None,
) -> dict[str, Any]:
    obligation = placeable_only_parent_obligation(a, b)
    if not obligation["applicable"]:
        return {
            "ok": True,
            "applicable": False,
            "parentStrongRoles": obligation["strongParentRoles"],
        }
    candidates = obligation["placeableParents"]
    plan = data.get("runtimePlan")
    plan = plan if isinstance(plan, dict) else {}
    placeable_candidate = next((
        call.get("params")
        for call in plan.get("engineCalls") or []
        if isinstance(call, dict)
        and call.get("fn") == "placeable_behavior"
        and isinstance(call.get("params"), dict)
    ), {})
    placeable: dict[str, Any] = placeable_candidate if isinstance(placeable_candidate, dict) else {}
    authored_tile = int(item_num(placeable, "createTile", -1))
    authored_wall = int(item_num(placeable, "createWall", -1))
    exact_parent_id = any(
        (authored_tile >= 0 and authored_tile == row["createTile"])
        or (authored_wall >= 0 and authored_wall == row["createWall"])
        for row in candidates
    )
    result_kind = effective_runtime_result_kind(data)
    return {
        "ok": result_kind == "furniture" and exact_parent_id,
        "applicable": True,
        "expectedResultKind": "furniture",
        "placeableParents": candidates,
        "actualResultKind": result_kind,
        "actualCreateTile": authored_tile,
        "actualCreateWall": authored_wall,
    }


def _strict_authoring_validation(data: dict[str, Any], a: dict[str, Any] | None = None, b: dict[str, Any] | None = None) -> None:
    raw_candidate = data.get("_authorItemRaw")
    raw_author: Any = raw_candidate if isinstance(raw_candidate, dict) else data
    author_item_schema = (
        strict_author_item_v3_report(raw_author)
        if isinstance(raw_candidate, dict)
        else {"schema": "infini.author-item-v3-local-validation.v1", "ok": True, "skipped": "no_raw_snapshot"}
    )
    authored_name = str(raw_author.get("name") or "") if isinstance(raw_author, dict) else ""
    name_error = "invalid_item_name" if bad_result_name(authored_name, a, b) else ""
    raw_plan = data.get("runtimePlan")
    raw_boundary = runtime_plan_boundary_report(raw_plan) if isinstance(raw_plan, dict) else {
        "ok": False,
        "errors": ["runtimePlan: exact object is required"],
        "unknownParams": [],
    }
    runtime_validation = runtime_plan_validation_report(deepcopy(data))
    structural_contract = validate_structural_planner_contract(data)
    parent_role = _parent_role_preservation_report(data, a, b)
    parent_economy = _consumable_parent_economy_report(data, a, b)
    placeable_role = _placeable_parent_role_report(data, a, b)
    pressure_envelope: dict[str, Any] = {"ok": True, "skipped": "no_compiled_root"}
    pressure_candidate: dict[str, Any] | None = deepcopy(data) if isinstance(raw_plan, dict) else None
    pressure_ignored_unknowns: list[dict[str, Any]] = []
    if pressure_candidate is not None and not raw_boundary.get("ok"):
        candidate_plan = pressure_candidate.get("runtimePlan")
        candidate_calls = candidate_plan.get("engineCalls") if isinstance(candidate_plan, dict) else None
        for unknown in raw_boundary.get("unknownParams") or []:
            if not isinstance(unknown, dict) or not isinstance(candidate_calls, list):
                continue
            try:
                call_index = int(str(unknown.get("index") or ""))
            except (TypeError, ValueError, OverflowError):
                continue
            if call_index < 0 or call_index >= len(candidate_calls):
                continue
            call = candidate_calls[call_index]
            params = call.get("params") if isinstance(call, dict) else None
            if not isinstance(params, dict):
                continue
            for param_name in unknown.get("params") or []:
                name = str(param_name or "").strip()
                if name and name in params:
                    params.pop(name)
                    pressure_ignored_unknowns.append({
                        "callIndex": call_index,
                        "fn": str(call.get("fn") or ""),
                        "param": name,
                    })
        projected_plan = pressure_candidate.get("runtimePlan")
        projected_boundary = (
            runtime_plan_boundary_report(projected_plan)
            if isinstance(projected_plan, dict)
            else {"ok": False}
        )
        if not pressure_ignored_unknowns or not projected_boundary.get("ok"):
            pressure_candidate = None
    if pressure_candidate is not None:
        compiled_preview = compile_runtime_plan_to_genome_result(pressure_candidate)
        preview_patch = compiled_preview.get("patch")
        if isinstance(preview_patch, dict) and preview_patch:
            try:
                pressure_envelope = projectile_pressure_envelope_report(
                    preview_patch,
                    data.get("gameplay") if isinstance(data.get("gameplay"), dict) else {},
                )
                if pressure_ignored_unknowns:
                    pressure_envelope["diagnosticIgnoredUnknownParams"] = pressure_ignored_unknowns
            except (TypeError, ValueError, OverflowError):
                pressure_envelope = {
                    "ok": False,
                    "reason": "composite projectile pressure could not be evaluated from authored numbers",
                }
    report = {
        "schema": "infini.strict-authoring-validation.v1",
        "ok": bool(author_item_schema.get("ok") and not name_error and raw_boundary.get("ok") and runtime_validation.get("ok") and structural_contract.get("ok") and pressure_envelope.get("ok") and parent_role.get("ok") and parent_economy.get("ok") and placeable_role.get("ok")),
        "authorItemV3": author_item_schema,
        "identityError": name_error,
        "rawRuntimePlan": raw_boundary,
        "runtimeValidation": runtime_validation,
        "structuralRuntimeContract": structural_contract,
        "pressureEnvelope": pressure_envelope,
        "parentRolePreservation": parent_role,
        "consumableParentEconomy": parent_economy,
        "placeableParentRole": placeable_role,
    }
    debug = data.setdefault("debug", {})
    debug["runtimePlanRawStrictBoundary"] = bounded_json_dumps(raw_boundary, max_chars=6000)
    debug["authorItemV3LocalStrictBoundary"] = bounded_json_dumps(author_item_schema, max_chars=6000)
    debug["runtimePlanValidationBeforeRepair"] = bounded_json_dumps(runtime_validation, max_chars=6000)
    debug["structuralRuntimeContract"] = bounded_json_dumps(structural_contract, max_chars=6000)
    debug["runtimePressureEnvelopeBeforeRepair"] = bounded_json_dumps(pressure_envelope, max_chars=3000)
    debug["parentRolePreservation"] = bounded_json_dumps(parent_role, max_chars=2000)
    debug["consumableParentEconomy"] = bounded_json_dumps(parent_economy, max_chars=2000)
    debug["placeableParentRole"] = bounded_json_dumps(placeable_role, max_chars=2000)
    if not report["ok"]:
        repair_targets: list[dict[str, Any]] = []
        runtime_details = [
            deepcopy(row)
            for row in runtime_validation.get("errorDetails") or []
            if isinstance(row, dict)
        ]
        repair_targets.extend(runtime_details)
        runtime_paths = {str(row.get("path") or "") for row in runtime_details}
        repair_targets.extend(
            deepcopy(row)
            for row in author_item_schema.get("errors") or []
            if isinstance(row, dict) and str(row.get("path") or "") not in runtime_paths
        )
        repair_targets.extend(
            deepcopy(row)
            for row in structural_contract.get("blockingClaims") or []
            if isinstance(row, dict)
        )
        if not pressure_envelope.get("ok") and isinstance(raw_plan, dict):
            pressure_reason = str(
                pressure_envelope.get("reason")
                or "composite projectile pressure exceeds runtime safety envelope"
            )
            calls = raw_plan.get("engineCalls")
            pressure_constraints = pressure_envelope.get("repairParamConstraints")
            constraint_map = pressure_constraints if isinstance(pressure_constraints, dict) else {}
            for index, call in enumerate(calls if isinstance(calls, list) else []):
                if not isinstance(call, dict):
                    continue
                fn = str(call.get("fn") or "").strip()
                call_id = str(call.get("callId") or "").strip()
                if fn in ROOT_EXECUTOR_FUNCTION_NAMES:
                    params = call.get("params")
                    ignored_pressure_params = {
                        str(row.get("param") or "").strip()
                        for row in pressure_ignored_unknowns
                        if row.get("callIndex") == index
                    }
                    authored_pressure_params = [
                        name
                        for name in ("shotCount", "extraUpdates", "lifetimeTicks")
                        if isinstance(params, dict)
                        and name in params
                        and name not in ignored_pressure_params
                    ]
                    if authored_pressure_params:
                        call_constraints = {
                            name: deepcopy(constraint_map[name])
                            for name in authored_pressure_params
                            if isinstance(constraint_map.get(name), dict)
                        }
                        repair_targets.append({
                            "path": f"$.runtimePlan.engineCalls[{index}]",
                            "callId": call_id,
                            "fn": fn,
                            "reason": pressure_reason,
                            "repairParamNames": authored_pressure_params,
                            "pressureEnvelope": deepcopy(pressure_envelope),
                            "repairParamConstraints": call_constraints,
                        })
                elif fn == "set_item_stats":
                    params = call.get("params")
                    if isinstance(params, dict) and "useTimeTicks" in params:
                        repair_targets.append({
                            "path": f"$.runtimePlan.engineCalls[{index}]",
                            "callId": call_id,
                            "fn": fn,
                            "reason": pressure_reason,
                            "repairParamNames": ["useTimeTicks"],
                            "pressureEnvelope": deepcopy(pressure_envelope),
                            "repairParamConstraints": {
                                "useTimeTicks": deepcopy(constraint_map["useTimeTicks"]),
                            } if isinstance(constraint_map.get("useTimeTicks"), dict) else {},
                        })
        if not parent_role.get("ok"):
            expected_kind = str(parent_role.get("expectedResultKind") or "").strip()
            strong_role = str((parent_role.get("parentStrongRoles") or [""])[0])
            reason = (
                "unrepresentable_mechanic: sole strong parent role is "
                + strong_role
                + "; full redesign requires resultKind="
                + expected_kind
            )
            if expected_kind == "armor":
                reason += " and armorSlot=" + "|".join(parent_role.get("expectedArmorSlots") or [])
            repair_targets.append({
                "path": "$.runtimePlan.engineCalls",
                "kind": "parent_role_unrepresentable_mechanic",
                "reason": reason,
                "expectedResultKind": expected_kind,
                "expectedArmorSlots": deepcopy(parent_role.get("expectedArmorSlots") or []),
                "parentStrongRole": strong_role,
            })
        if not parent_economy.get("ok"):
            repair_targets.append({
                "path": "$.runtimePlan.engineCalls",
                "kind": "parent_economy_unrepresentable_mechanic",
                "reason": (
                    "unrepresentable_mechanic: consumable_weapon cannot spend reusable gear parent(s): "
                    + ", ".join(parent_economy.get("reusableGearParents") or [])
                    + "; full redesign must preserve reusable gear economy"
                ),
                "reusableGearParents": deepcopy(parent_economy.get("reusableGearParents") or []),
            })
        if not placeable_role.get("ok"):
            repair_targets.append({
                "path": "$.runtimePlan.engineCalls",
                "kind": "placeable_parent_unrepresentable_mechanic",
                "reason": (
                    "unrepresentable_mechanic: placeable-only parents require resultKind=furniture "
                    "and placeable_behavior using an exact parent createTile/createWall id"
                ),
                "expectedResultKind": "furniture",
                "placeableParents": deepcopy(placeable_role.get("placeableParents") or []),
            })
        if name_error:
            repair_targets.append({
                "path": "$.name",
                "kind": "invalid_item_name",
                "reason": name_error,
            })
        if not runtime_details and not raw_boundary.get("ok"):
            repair_targets.extend({
                "path": "$.runtimePlan",
                "kind": "runtime_boundary",
                "reason": str(reason),
            } for reason in raw_boundary.get("errors") or [])
        raise PlannerUnavailable(
            "strict authoring rejected: " + bounded_json_dumps(report, max_chars=12000),
            author_repair_targets=repair_targets,
        )


def strict_validate_authored_item(data: dict[str, Any], a: dict[str, Any] | None = None, b: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate the exact model-authored v3 object before any deterministic projection."""
    _strict_authoring_validation(data, a, b)
    data.pop("_authorItemRaw", None)
    return data


def _project_authored_visual_intent(data: dict[str, Any]) -> None:
    plan_candidate = data.get("runtimePlan")
    plan: dict[str, Any] = plan_candidate if isinstance(plan_candidate, dict) else {}
    intent_candidate = plan.get("visualIntent")
    intent: dict[str, Any] = intent_candidate if isinstance(intent_candidate, dict) else {}
    if not intent:
        return
    visual = data.setdefault("visual", {}) if isinstance(data.get("visual"), dict) else {}
    data["visual"] = visual
    for source, target in (("projectile", "projectileImagePrompt"), ("impact", "impactImagePrompt"), ("item", "imagePrompt")):
        if intent.get(source) and not visual.get(target):
            visual[target] = str(intent[source])
    for field in (
        "vfxIntent", "vfxAvoid", "topology", "arrangement",
        "projectileVisualFamily", "projectileOrientation",
    ):
        if intent.get(field) is not None:
            visual[field] = str(intent[field])
    for field in ("partCountMin", "partCountMax", "preferredCanvasSize", "projectileCanvasSize"):
        if isinstance(intent.get(field), int):
            visual[field] = int(intent[field])
    palette = intent.get("palette")
    if isinstance(palette, list):
        visual["palette"] = [str(color) for color in palette if str(color).strip()][:8]
        data.setdefault("debug", {})["visualPaletteSource"] = "planner_authored"
    anime_reference = intent.get("animeReference")
    if isinstance(anime_reference, dict):
        visual["animeReference"] = deepcopy(anime_reference)
    parts = intent.get("parts")
    if isinstance(parts, list):
        visual["parts"] = [str(part) for part in parts]

def _stringish(x: Any, fallback: str = "") -> str:
    if x is None:
        return fallback
    if isinstance(x, (list, tuple)):
        return "; ".join(str(v) for v in x if str(v).strip()) or fallback
    if isinstance(x, dict):
        return json.dumps(x, ensure_ascii=False, separators=(",", ":"))
    return str(x)

def validate_and_repair(data: dict[str, Any], a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], key: str) -> dict[str, Any]:
    """Project validated authored data plus deterministic dev payloads; never call a repair model."""

    data.setdefault("schemaVersion", 1)
    data.setdefault("id", "g_" + stable_hash(key, data.get("name", ""), length=16))
    data.setdefault("recipeKey", key)
    data.setdefault("parentA", name_of(a))
    data.setdefault("parentB", name_of(b))
    data.setdefault("sourceMode", "generated")
    data.setdefault("mergeMode", "literal")
    data["category"] = normalize_category(data.get("category", "generic"))
    data.setdefault("tags", [])
    data.setdefault("canonical", canonical_for_result(data.get("name", "Generated Item"), data.get("category", "generic"), data.get("tags", [])))
    data.setdefault("sourceRepresentation", [])
    data.setdefault("inheritance", [])
    data.setdefault("lossBudget", {})
    data.setdefault("visual", {})
    data.setdefault("gameplay", {})
    data.setdefault("accessory", {})
    data.setdefault("attack", {})
    data.setdefault("debug", {})
    if "itemKnowledge" not in data:
        data["itemKnowledge"] = build_item_knowledge(a, b, ca, cb)
    if runtime_plan(data):
        policy_for_meta = {"mode": "llm_runtime_result_kind", "selected": normalize_category(data.get("category", "generic")), "default": normalize_category(data.get("category", "generic")), "allowed": [normalize_category(data.get("category", "generic"))], "creativeAllowed": [normalize_category(data.get("category", "generic"))]}
    else:
        policy_for_meta = category_policy(set(str(t).lower() for t in data.get("tags", [])) | tags_of(a) | tags_of(b), a, b, key)
    meta_candidate = data.get("recipeMeta")
    meta: dict[str, Any] = meta_candidate if isinstance(meta_candidate, dict) else {}
    repaired_meta = recipe_meta(a, b, set(str(t).lower() for t in data.get("tags", [])) | tags_of(a) | tags_of(b), policy_for_meta)
    repaired_meta.update(meta)
    # These fields are authoritative and should not be dropped by the LLM.
    repaired_meta["universalRecipe"] = True
    repaired_meta["generationDepth"] = max(generation_depth(a), generation_depth(b)) + 1
    repaired_meta["parentGeneratedDepths"] = [generation_depth(a), generation_depth(b)]
    data["recipeMeta"] = repaired_meta
    data["debug"]["generationDepth"] = str(repaired_meta["generationDepth"])
    data["debug"]["recipeCoherence"] = str(repaired_meta.get("recipeCoherence", ""))

    # Force parent representation if planner dropped it.
    existing_parents = {x.get("parent") for x in data.get("inheritance", []) if isinstance(x, dict)}
    for item, c, role in [(a, ca, "base_shape"), (b, cb, "influence")]:
        if name_of(item) not in existing_parents:
            data["inheritance"].append(inh_for_parent(item, c, role))
    existing_rep = {x.get("parent") for x in data.get("sourceRepresentation", []) if isinstance(x, dict)}
    for item, c, imp in [(a, ca, "primary"), (b, cb, "secondary")]:
        if name_of(item) not in existing_rep:
            data["sourceRepresentation"].append(rep_for_parent(item, c, imp))

    # Hard tag preservation belongs only to non-runtime fallback. In runtime-authoring mode,
    # parent tags are raw context, not semantic tags injected after the LLM already authored it.
    parent_hard = set(ca.get("hardTags") or []) | set(cb.get("hardTags") or [])
    tags = set(str(t).lower() for t in data.get("tags", []))
    if not runtime_plan(data):
        tags |= parent_hard
    data["tags"] = sorted(tags)

    requested_category = data.get("category", "generic")
    gameplay = data.setdefault("gameplay", {})
    if gameplay.get("kind"):
        requested_category = gameplay.get("kind")
    if runtime_plan(data):
        result_kind = effective_runtime_result_kind(data)
        stats = find_call(data, "set_item_stats")
        projection = project_runtime_result_identity(
            result_kind,
            ammo_for=stats.get("ammoFor"),
            has_root_executor=bool(find_call(data, "shoot_projectile")),
        )
        selected_category = projection.gameplay_kind
        policy = {
            "mode": "runtime_result_identity",
            "requested": requested_category,
            "runtimeResultKind": projection.authored_kind,
            "final": selected_category,
        }
    else:
        selected_category, policy = coerce_category_by_policy(requested_category, tags, a, b, key)
    data["category"] = selected_category
    gameplay["kind"] = selected_category
    data.setdefault("debug", {})["categoryPolicy"] = json.dumps(policy, ensure_ascii=False)
    _project_authored_visual_intent(data)
    data.setdefault("debug", {})["runtimeRepairPath"] = "one bounded same-author scoped repair owns domain rejection"
    if data["category"] == "accessory":
        data.setdefault("accessory", {})["enabled"] = True
        data.setdefault("attack", {})["enabled"] = False

    # Keep author-owned required anchors separate from code-derived parent context.
    # Parent facts must reach the Visual Director, but code must not silently turn them
    # into mandatory literal parts of the final design.
    visual = data.setdefault("visual", {})
    authored_anchors = [str(x).strip() for x in (visual.get("requiredAnchors") or []) if str(x).strip()]
    visual["requiredAnchors"] = list(dict.fromkeys(authored_anchors))[:10]
    data["debug"]["visualRequiredAnchorsSource"] = "planner_authored" if authored_anchors else "none"

    parent_visual_context: list[str] = []
    for c in (ca, cb):
        hard_tags = {
            str(tag).strip().lower()
            for tag in (c.get("hardTags") or [])
            if str(tag).strip()
        }
        parent_visual_context.extend(required_anchors_from_tags(hard_tags))
        parent_visual_context.extend(str(x).strip() for x in (c.get("visualAnchors") or []) if str(x).strip())
    visual["parentVisualContext"] = list(dict.fromkeys(parent_visual_context))[:16]
    raw_palette = visual.get("palette")
    if isinstance(raw_palette, list) and raw_palette:
        visual["palette"] = [str(x) for x in raw_palette if str(x).strip()][:8]
        data["debug"]["visualPaletteSource"] = "planner_authored"
    else:
        visual["palette"] = []
        data["debug"]["visualPaletteSource"] = "none"
    visual.setdefault("objectType", slug(data.get("name", "generated_item")))
    if isinstance(data.get("attack"), dict) and data["attack"].get("genome") is None:
        data["attack"]["genome"] = {}
    data["canonical"] = canonical_for_result(data.get("name", "Generated Item"), data.get("category", "generic"), list(tags))
    score = preservation_score(data, ca, cb)
    visual["preservationScore"] = score
    if score < 0.65:
        data["debug"]["repair"] = "low preservation; source anchors forcibly injected"
    return data

__all__ = ["_stringish", "validate_and_repair"]
