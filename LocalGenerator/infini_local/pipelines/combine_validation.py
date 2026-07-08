from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import queue
import random
import re
import shlex
import subprocess
import time
import traceback
from pathlib import Path
from typing import Any
from urllib import request as urlrequest
from urllib import error as urlerror
from urllib.parse import urlencode

from infini_local.core.balance_report import attach_balance_report
from infini_local.core.balance_policy import weapon_envelope_for_bucket
from infini_local.pipelines.result_identity_policy import (
    _policy_seed,
    _weighted_choice,
    bad_result_name,
    canonical_for_result,
    category_policy,
    choose_from,
    choose_result_category,
    clean_name,
    coerce_category_by_policy,
    creative_result_name,
    inh_for_parent,
    is_weapon_like_parent,
    name_noun_for,
    name_prefixes_for,
    normalize_category,
    palette_from,
    parent_primary_category,
    repair_name_if_needed,
    rep,
    rep_for_parent,
    required_anchors_from,
    required_anchors_from_tags,
    theme_word,
    title_words,
    try_llm_name_repair,
)
from infini_local.pipelines.equipment_stats import (
    _ACCESSORY_BOOLEAN_COSTS,
    _ACCESSORY_COST_WEIGHTS,
    _ARMOR_BOOLEAN_COSTS,
    _ARMOR_PIECE_COST_WEIGHTS,
    _SET_BONUS_COST_WEIGHTS,
    _equipment_budget_base,
    _equipment_cost,
    _equipment_float,
    _equipment_int,
    _scale_equipment_fields,
    accessory_stats_for,
    apply_accessory_soft_budget,
    apply_armor_soft_budget,
    armor_slot_from_authoring,
    armor_stats_for,
)
from infini_local.pipelines.pipeline_support import (
    ACCESSORY_HINT_TAGS,
    ALLOWED_CATEGORIES,
    ALLOW_DETERMINISTIC_DEV_FALLBACK,
    AMMO_HINT_TAGS,
    APP_VERSION,
    ARMOR_HINT_TAGS,
    ASSET_PUBLIC_BASE_URL,
    BAD_NAME_PATTERNS,
    CACHE_DIR,
    CATEGORY_CREATIVITY,
    CATEGORY_ENFORCE_SAMPLED,
    CATEGORY_SALT,
    COMBAT_CATEGORIES,
    DELIVERY_ALIASES,
    DELIVERY_VALUES,
    EFFECT_ALIASES,
    EFFECT_CODE,
    EFFECT_PRESENTATION,
    HARD_TAGS,
    LAST_COMBINE_FAILURE,
    LAST_COMBINE_FAILURE_FILE,
    LLM_NUMERIC_GENOME_LIMITS,
    LLM_OPTIONAL_GENOME_DEFAULTS,
    LLM_REQUIRED_GENOME_FIELDS,
    LLM_RUNTIME_AUTHORING,
    MODDED_HIGH_TIERS,
    MOVEMENT_ALIASES,
    MOVEMENT_CODE,
    NON_WEAPON_CATEGORIES,
    ONHIT_ALIASES,
    ONHIT_CODE,
    PALETTES,
    PLACEABLE_HINT_TAGS,
    PlannerUnavailable,
    RECIPE_IDENTITY_VERSION,
    RECURSIVE_POWER_GROWTH,
    RUNTIME_FAMILY_VALUES,
    STRONG_ACCESSORY_TAGS,
    TIER_DEFAULT_POWER,
    TIER_RANK,
    TOOL_HINT_TAGS,
    USE_LLM,
    VANILLA_ENDGAME_POWER,
    VISUAL_PIPELINE_PROFILE,
    VISUAL_SYNONYMS,
    WEAPON_UPGRADE_TAGS,
    _json_slim,
    all_calls,
    apply_item_knowledge,
    asset_sync_service,
    attach_generated_parent_summary,
    attach_hybrid_vfx_manifest,
    behavior_cost_multiplier,
    build_item_knowledge,
    cache_get,
    cache_put,
    canonicalize,
    contract_versions_payload,
    clamp_float,
    estimate_engine_metrics,
    failure_state,
    final_normalize,
    find_call,
    generated_data_of,
    generation_depth,
    guess_head,
    infer_attack_pattern_from_runtime,
    infer_item_card,
    is_deliverable_recipe_payload,
    item_bool,
    item_field,
    item_identity,
    item_num,
    log_event,
    lower_name,
    mechanic_signal_power,
    name_of,
    normalize_world_id_from_payload,
    pair_catalyst_pressure,
    parse_first_valid_llm_json,
    rarity_baseline_signal,
    recipe_coherence,
    recipe_key,
    recipe_meta,
    resolve_attack_pattern,
    runtime_plan,
    sanitize_genome_engine,
    sanitize_recipe_for_delivery,
    slug,
    stable_hash,
    tags_of,
    trace_event,
    world_recipe_dir,
    world_storage,
)
from infini_local.pipelines.projectile_affordance import (
    _explicit_visual_family_value,
    apply_parent_projectile_affordance,
    choose_parent_projectile_size_reference,
    infer_projectile_visual_family,
    parent_combo_looks_like_bow,
    parent_projectile_family,
    projectile_family_text,
)
from infini_local.pipelines.presentation_sound import (
    attach_presentation_and_sound,
    clamp,
    effect_for,
    movement_for,
    onhit_for,
    presentation_from_genome,
    sound_profile_from_genome,
)
from infini_local.pipelines.result_knowledge_card import (
    attach_result_knowledge_card,
    build_result_item_card,
)
from infini_local.pipelines.llm_authoring_prompt import (
    llm_category_without_router,
    llm_runtime_result_kind_policy,
    normalize_runtime_authoring_fields,
)
from infini_local.pipelines.parent_context_pipeline import (
    _pbool,
    _pnum,
    effective_projectile_profile_of,
    llm_parent_card,
    parent_weapon_profiles,
    proj_bool,
)

from infini_local.pipelines.combine_balance import preservation_score

def _stringish(x: Any, fallback: str = "") -> str:
    if x is None:
        return fallback
    if isinstance(x, (list, tuple)):
        return "; ".join(str(v) for v in x if str(v).strip()) or fallback
    if isinstance(x, dict):
        return json.dumps(x, ensure_ascii=False, separators=(",", ":"))
    return str(x)

def validate_and_repair(data: dict[str, Any], a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], key: str) -> dict[str, Any]:
    from infini_local.pipelines import combine_pipeline as _facade
    from infini_local.pipelines.combine_genome import is_llm_planner, repair_llm_combat_genome_if_needed

    llm_runtime_authoring = bool(getattr(_facade, "LLM_RUNTIME_AUTHORING", LLM_RUNTIME_AUTHORING))
    repair_runtime_plan = getattr(_facade, "repair_runtime_plan_if_needed")
    normalize_runtime_authoring = getattr(_facade, "normalize_runtime_authoring_fields", normalize_runtime_authoring_fields)
    llm_runtime_kind_policy = getattr(_facade, "llm_runtime_result_kind_policy", llm_runtime_result_kind_policy)
    llm_category_policy = getattr(_facade, "llm_category_without_router", llm_category_without_router)

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
    for c in [ca, cb]:
        for t in c.get("hardTags") or []:
            anchors.extend(VISUAL_SYNONYMS.get(t, []))
        anchors.extend(c.get("visualAnchors") or [])
    visual["requiredAnchors"] = list(dict.fromkeys([a for a in anchors if a]))[:10]
    raw_palette = visual.get("palette")
    if isinstance(raw_palette, list) and raw_palette:
        visual["palette"] = [str(x) for x in raw_palette if str(x).strip()][:8]
    else:
        visual["palette"] = palette_from(tags)
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
