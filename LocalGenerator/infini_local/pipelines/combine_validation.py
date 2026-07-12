from __future__ import annotations

import json
from typing import Any
from infini_local.core.item_identity_tools import name_of, slug, stable_hash
from infini_local.core.runtime_authoring.normalize import runtime_plan
from infini_local.pipelines.combine_balance import preservation_score
from infini_local.pipelines.result_identity_policy import (
    canonical_for_result,
    category_policy,
    coerce_category_by_policy,
    inh_for_parent,
    normalize_category,
    palette_from,
    required_anchors_from_tags,
    repair_name_if_needed,
    rep_for_parent,
)
from infini_local.pipelines.item_power_knowledge import (
    build_item_knowledge,
    generation_depth,
    recipe_meta,
    tags_of,
)
from infini_local.pipelines.pipeline_runtime_constants import LLM_RUNTIME_AUTHORING
from infini_local.pipelines.llm_authoring_prompt import (
    llm_category_without_router,
    llm_runtime_result_kind_policy,
    normalize_runtime_authoring_fields,
)
from infini_local.pipelines.llm_authoring_pipeline import repair_runtime_plan_if_needed

def _stringish(x: Any, fallback: str = "") -> str:
    if x is None:
        return fallback
    if isinstance(x, (list, tuple)):
        return "; ".join(str(v) for v in x if str(v).strip()) or fallback
    if isinstance(x, dict):
        return json.dumps(x, ensure_ascii=False, separators=(",", ":"))
    return str(x)

def validate_and_repair(data: dict[str, Any], a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], key: str) -> dict[str, Any]:
    from infini_local.pipelines.combine_genome import repair_llm_combat_genome_if_needed
    from infini_local.pipelines.combine_genome_contract import is_llm_planner

    llm_runtime_authoring = bool(LLM_RUNTIME_AUTHORING)
    repair_runtime_plan = repair_runtime_plan_if_needed
    normalize_runtime_authoring = normalize_runtime_authoring_fields
    llm_runtime_kind_policy = llm_runtime_result_kind_policy
    llm_category_policy = llm_category_without_router

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
    if llm_runtime_authoring and runtime_plan(data):
        policy_for_meta = {"mode": "llm_runtime_result_kind", "selected": normalize_category(data.get("category", "generic")), "default": normalize_category(data.get("category", "generic")), "allowed": [normalize_category(data.get("category", "generic"))], "creativeAllowed": [normalize_category(data.get("category", "generic"))]}
    else:
        policy_for_meta = category_policy(set(str(t).lower() for t in data.get("tags", [])) | tags_of(a) | tags_of(b), a, b, key)
    meta = data.get("recipeMeta") if isinstance(data.get("recipeMeta"), dict) else {}
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
    if not (llm_runtime_authoring and runtime_plan(data)):
        tags |= parent_hard
    data["tags"] = sorted(tags)

    requested_category = data.get("category", "generic")
    gameplay = data.setdefault("gameplay", {})
    if gameplay.get("kind"):
        requested_category = gameplay.get("kind")
    if llm_runtime_authoring and runtime_plan(data):
        selected_category, policy = llm_runtime_kind_policy(data, requested_category, tags, a, b, key)
    elif is_llm_planner(data):
        selected_category, policy = llm_category_policy(data, requested_category, tags, a, b, key)
    else:
        selected_category, policy = coerce_category_by_policy(requested_category, tags, a, b, key)
    data["category"] = selected_category
    gameplay["kind"] = selected_category
    data.setdefault("debug", {})["categoryPolicy"] = json.dumps(policy, ensure_ascii=False)
    # Names must be item names, not mod/service labels. The LLM owns naming when enabled;
    # deterministic fallback only repairs empty/service-looking names.
    data = repair_name_if_needed(data, a, b, ca, cb, key)
    if llm_runtime_authoring:
        data = repair_runtime_plan(data, a, b, ca, cb, key)
    data = normalize_runtime_authoring(data)
    if llm_runtime_authoring:
        # repair_runtime_plan_if_needed() may already have recorded an actual repair
        # result.  Do not overwrite it with the legacy-genome skip note; in runtime
        # authoring mode we skip only the old attack.genome repair loop, not the
        # runtimePlan validation/repair path above.
        data.setdefault("debug", {}).setdefault(
            "runtimeRepairPath",
            "not_needed: runtimePlan.engineCalls is the authored source; legacy attack.genome repair skipped",
        )
    else:
        data = repair_llm_combat_genome_if_needed(data, a, b, ca, cb, key)
    if data["category"] == "accessory":
        data.setdefault("accessory", {})["enabled"] = True
        data.setdefault("attack", {})["enabled"] = False

    # Required visual anchors must include hard visual anchors.
    visual = data.setdefault("visual", {})
    anchors = list(visual.get("requiredAnchors") or [])
    for c in (ca, cb):
        hard_tags = {
            str(tag).strip().lower()
            for tag in (c.get("hardTags") or [])
            if str(tag).strip()
        }
        anchors.extend(required_anchors_from_tags(hard_tags))
        anchors.extend(str(x) for x in (c.get("visualAnchors") or []) if str(x).strip())
    visual["requiredAnchors"] = list(dict.fromkeys([a for a in anchors if a]))[:10]
    raw_palette = visual.get("palette")
    if isinstance(raw_palette, list) and raw_palette:
        visual["palette"] = [str(x) for x in raw_palette if str(x).strip()][:8]
        data["debug"]["visualPaletteSource"] = "planner_authored"
    else:
        # Runtime-authoring deliberately does not inject parent semantic tags into the
        # result item, but visual grounding still needs the physical parent materials.
        # Using result tags alone made ordinary Wood + Work Bench fall back to gray/white
        # and pushed the image model toward a generic steel sword.
        visual_grounding_tags = tags | tags_of(a) | tags_of(b)
        visual["palette"] = palette_from(visual_grounding_tags)
        data["debug"]["visualPaletteSource"] = "result_and_parent_grounding_tags"
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
