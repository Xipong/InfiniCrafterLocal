from __future__ import annotations

import json
from copy import deepcopy
from typing import Any
from infini_local.core.boundary_models import runtime_plan_boundary_report
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.item_identity_tools import name_of, slug, stable_hash
from infini_local.core.runtime_authoring.reports import runtime_plan_validation_report
from infini_local.core.runtime_authoring.normalize import runtime_plan
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
from infini_local.pipelines.llm_authoring_prompt import llm_runtime_result_kind_policy


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
    report = {
        "schema": "infini.strict-authoring-validation.v1",
        "ok": bool(author_item_schema.get("ok") and not name_error and raw_boundary.get("ok") and runtime_validation.get("ok") and structural_contract.get("ok")),
        "authorItemV3": author_item_schema,
        "identityError": name_error,
        "rawRuntimePlan": raw_boundary,
        "runtimeValidation": runtime_validation,
        "structuralRuntimeContract": structural_contract,
    }
    debug = data.setdefault("debug", {})
    debug["runtimePlanRawStrictBoundary"] = bounded_json_dumps(raw_boundary, max_chars=6000)
    debug["authorItemV3LocalStrictBoundary"] = bounded_json_dumps(author_item_schema, max_chars=6000)
    debug["runtimePlanValidationBeforeRepair"] = bounded_json_dumps(runtime_validation, max_chars=6000)
    debug["structuralRuntimeContract"] = bounded_json_dumps(structural_contract, max_chars=6000)
    if not report["ok"]:
        raise PlannerUnavailable("strict authoring rejected: " + bounded_json_dumps(report, max_chars=12000))


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
        selected_category, policy = llm_runtime_result_kind_policy(data, requested_category, tags, a, b, key)
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
