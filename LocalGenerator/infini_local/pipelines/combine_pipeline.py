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
    authored_int,
    authored_num,
    authored_weapon_damage,
    llm_category_without_router,
    llm_runtime_result_kind_policy,
    normalize_runtime_authoring_fields,
    runtime_plan_to_attack_genome_patch,
)
from infini_local.pipelines.llm_transport import (
    llm_chat_json,
    llm_json_response_format,
    resolve_llm_model,
)
from infini_local.pipelines.llm_authoring_pipeline import (
    call_llm_vfx_director,
    repair_runtime_plan_if_needed,
    try_llm_plan,
)
from infini_local.pipelines.combine_genome_contract import (
    combat_genome_required_for,
    is_llm_planner,
)

from infini_local.pipelines.parent_context_pipeline import (
    _pbool,
    _pnum,
    effective_projectile_profile_of,
    llm_parent_card,
    parent_weapon_profiles,
    proj_bool,
)

from infini_local.pipelines.visual_generation_pipeline import (
    apply_visual_director,
    attach_visual,
    assert_visual_delivery_ready,
    maybe_generate_visual_assets,
    visual_delivery_report,
)
from infini_local.pipelines.combine_balance import (
    apply_family_locks_to_genome,
    preservation_score,
    item_power_score,
    tier_rank,
    influenced_tier,
    universal_parent_relation,
    recipe_power_transfer,
    vanilla_like_weapon_envelope,
    clamp_vanilla_like_weapon_damage,
    stat_profile_for,
    stage_profile_for,
    canvas_tier_for,
    size_profile_for,
    balanced_damage,
)
from infini_local.pipelines.combine_genome import (
    _normalize_authored_enum_value,
    safe_enum,
    proposed_attack_genome,
    genome_defects,
    merge_genome_repair,
    try_llm_genome_repair,
    repair_llm_combat_genome_if_needed,
    _parse_required_float,
    _hard_clamp_authored_number,
    _require_authored_enum,
    llm_authored_weapon_genome,
    weapon_genome_for,
    normalize_authored_attack_pattern,
    weapon_numbers_from_genome,
    attack_pattern_for,
    _parent_tool_power,
    _bounded_parent_potion_stats,
)
from infini_local.pipelines.combine_validation import (
    _stringish,
    validate_and_repair,
)
from infini_local.pipelines.combine_gameplay import (
    attach_gameplay_and_attack,
)



# AGENT MAP: main /combine pipeline spine. The important shape is:
# request payload -> parent/world context -> LLM or fallback authored data ->
# runtimePlan compile/repair -> balance/final normalize -> visual/assets ->
# deliverable GeneratedItemData. Stage labels in combine() are debug breadcrumbs;
# do not insert hidden gameplay authoring into cache, visual, or trace helpers.
def record_combine_failure(stage: str, error: BaseException | str, payload: dict[str, Any] | None, partial_data: Any, pipeline_log: list[dict[str, Any]] | None) -> None:
    """Keep the last failed craft inspectable after C# refunds ingredients.

    This is intentionally diagnostic only: it does not change craft success/failure.
    v0.4.49: users were seeing generated PNGs in cache but /combine returned 424;
    the trace must say which pipeline stage rejected the recipe.
    """
    global LAST_COMBINE_FAILURE
    LAST_COMBINE_FAILURE = failure_state.build_combine_failure(
        app_version=APP_VERSION,
        stage=stage,
        error=error,
        payload=payload,
        partial_data=partial_data,
        pipeline_log=pipeline_log,
        parent_name=name_of,
        json_slim=_json_slim,
    )
    failure_state.persist_failure(CACHE_DIR, LAST_COMBINE_FAILURE_FILE, LAST_COMBINE_FAILURE, log_event)

def clear_combine_failure(reason: str = "success") -> None:
    """Clear stale diagnostic failure state after a successful/cached craft.

    last_combine_failure.json is a debug aid, not an authoritative current
    status.  Earlier versions cleared only the in-memory dict at the start of a
    fresh combine; /trace then reloaded an old file and made a later successful
    craft look failed.
    """
    global LAST_COMBINE_FAILURE
    LAST_COMBINE_FAILURE = {}
    failure_state.clear_persisted_failure(LAST_COMBINE_FAILURE_FILE, log_event, reason)

def last_combine_failure_summary() -> dict[str, Any]:
    return failure_state.read_failure_summary(LAST_COMBINE_FAILURE, LAST_COMBINE_FAILURE_FILE)

def combine_cache_lookup(payload: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    """Return a world-scoped cached recipe without starting generation.

    This is a transport/cache helper, not a design path: it computes the exact same
    recipe key as /combine and reads the existing world recipe file only. It is used
    so a Terraria client can recover an item after an earlier long /combine request
    timed out locally but finished and wrote the recipe on the generator side.
    """
    a = payload.get("itemA") or {}
    b = payload.get("itemB") or {}
    world_id = normalize_world_id_from_payload(payload)
    world_name = str(payload.get("worldName") or "").strip()
    recipe_identity_version = str(payload.get("recipeIdentityVersion") or payload.get("recipeKeyVersion") or RECIPE_IDENTITY_VERSION)
    key = recipe_key(a, b, world_id, recipe_identity_version)
    cached = cache_get(key, world_id, world_name)
    if cached is not None and not is_deliverable_recipe_payload(cached):
        trace_event("step", "HTTP:/combine", "world recipe cache skipped non-deliverable payload", {"recipeKey": key, "sourceMode": cached.get("sourceMode") if isinstance(cached, dict) else ""})
        cached = None
    if cached is not None:
        visual_report = visual_delivery_report(cached)
        if not visual_report.get("ok"):
            trace_event("step", "HTTP:/combine", "world recipe cache skipped missing required visual asset", {"recipeKey": key, "visualDelivery": visual_report})
            cached = None
    return key, cached

def combine(payload: dict[str, Any]) -> dict[str, Any]:
    global LAST_COMBINE_FAILURE
    a = payload.get("itemA") or {}
    b = payload.get("itemB") or {}
    world_id = normalize_world_id_from_payload(payload)
    world_name = str(payload.get("worldName") or "").strip()
    recipe_identity_version = str(payload.get("recipeIdentityVersion") or payload.get("recipeKeyVersion") or RECIPE_IDENTITY_VERSION)
    key = recipe_key(a, b, world_id, recipe_identity_version)
    cached = cache_get(key, world_id, world_name)
    if cached:
        visual_report = visual_delivery_report(cached)
        if visual_report.get("ok"):
            clear_combine_failure("cache_hit_delivered")
            return sanitize_recipe_for_delivery(cached)
        trace_event("step", "COMBINE:cache", "cached recipe ignored because required visual asset is not deliverable", {"recipeKey": key, "visualDelivery": visual_report})

    ca = canonicalize(a)
    cb = canonicalize(b)
    pipeline_log: list[dict[str, Any]] = []
    data: dict[str, Any] | None = None
    clear_combine_failure("new_combine_started")

    def step(label: str, fn, *args):
        t0 = time.time()
        try:
            out = fn(*args)
            pipeline_log.append({"stage": label, "ok": True, "ms": int((time.time() - t0) * 1000)})
            return out
        except Exception as e:
            pipeline_log.append({"stage": label, "ok": False, "ms": int((time.time() - t0) * 1000), "error": repr(e)})
            partial = args[0] if args and isinstance(args[0], dict) else data
            record_combine_failure(label, e, payload, partial, pipeline_log)
            raise

    try:
        if USE_LLM:
            data = step("01_author_llm_plan", try_llm_plan, a, b, ca, cb, key)

        if data is None:
            if ALLOW_DETERMINISTIC_DEV_FALLBACK:
                data = step("01b_deterministic_dev_fallback", deterministic_plan, a, b, ca, cb, key)
                data.setdefault("debug", {})["planner"] = "deterministic_dev_fallback"
            else:
                err = PlannerUnavailable("LLM planner unavailable or returned invalid output; craft failed and ingredients must be refunded")
                record_combine_failure("01_author_llm_plan", err, payload, data, pipeline_log)
                raise err

        # Author-first pipeline. The code is deliberately not the designer here:
        # it validates shape, computes safety envelope, asks/keeps authored toy fields,
        # then generates a visible asset pack for the authored behavior.
        data = step("02_schema_validate_and_minimal_repair", validate_and_repair, data, a, b, ca, cb, key)
        data = step("03_runtime_knowledge_context", apply_item_knowledge, data, a, b, ca, cb)
        data = step("04_author_gameplay_to_runtime_envelope", attach_gameplay_and_attack, data, a, b, ca, cb)
        data = step("05_presentation_sound_from_author_intent", attach_presentation_and_sound, data)
        data = step("06_result_card_after_runtime_stats", attach_result_knowledge_card, data, a, b)
        data = step("07_item_visual_brief_preserve_author", attach_visual, data, a, b, ca, cb)
        data = step("08_visual_director_asset_pack", apply_visual_director, data, a, b, ca, cb)
        data = step("09_visual_asset_generation", maybe_generate_visual_assets, data)
        data = step("09b_visual_delivery_gate", assert_visual_delivery_ready, data)
        data = step("10_hybrid_vfx_manifest", attach_hybrid_vfx_manifest, data, key, "", a, b, call_llm_vfx_director if USE_LLM else None)
        data = step("11_generated_parent_summary", attach_generated_parent_summary, data)
        data = step("12_final_normalize", final_normalize, data)
        data.setdefault("recipeMeta", {})["worldScoped"] = True
        data.setdefault("recipeMeta", {})["worldId"] = world_id
        data.setdefault("recipeMeta", {})["worldName"] = world_name
        data.setdefault("recipeMeta", {})["recipeKey"] = key
        data.setdefault("debug", {})["cacheScope"] = "world"
        data.setdefault("debug", {})["recipeIdentityVersion"] = recipe_identity_version
        data.setdefault("debug", {})["worldId"] = world_id
        data.setdefault("debug", {})["worldRecipesDir"] = str(world_recipe_dir(world_id))
        data.setdefault("debug", {})["pipelineProfile"] = VISUAL_PIPELINE_PROFILE
        data.setdefault("debug", {})["pipelineLog"] = json.dumps(pipeline_log, ensure_ascii=False)
        data = asset_sync_service.attach_asset_sync_meta(data, asset_public_base_url=ASSET_PUBLIC_BASE_URL)
        data = world_storage.attach_recipe_health(
            data,
            app_version=APP_VERSION,
            contract_versions=contract_versions_payload(),
            visual_report=visual_delivery_report(data),
        )
        data = sanitize_recipe_for_delivery(data)
        cache_put(key, a, b, data, world_id, world_name)
        clear_combine_failure("fresh_combine_success")
        return data
    except Exception as e:
        if not LAST_COMBINE_FAILURE:
            record_combine_failure("unknown", e, payload, data, pipeline_log)
        raise

def deterministic_plan(a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], key: str) -> dict[str, Any]:
    """Run the explicit dev-only fallback planner.

    Normal gameplay must not use this path unless
    INFINI_ALLOW_DETERMINISTIC_DEV_FALLBACK=1 is set.  The semantic fallback
    table lives in dev_fallback.py so server.py remains the authored LLM/runtime
    transport and validation shell.
    """
    import dev_fallback

    return dev_fallback.deterministic_plan(a, b, ca, cb, key, _dev_fallback_helpers())


def _dev_fallback_helpers() -> dict[str, Any]:
    """Return only the helper surface the explicit dev fallback is allowed to use."""
    return {
        "APP_VERSION": APP_VERSION,
        "ENGINE_RUNTIME_API_VERSION": ENGINE_RUNTIME_API_VERSION,
        "canonical_for_result": canonical_for_result,
        "category_policy": category_policy,
        "choose_result_category": choose_result_category,
        "creative_result_name": creative_result_name,
        "inh_for_parent": inh_for_parent,
        "name_of": name_of,
        "palette_from": palette_from,
        "recipe_meta": recipe_meta,
        "rep": rep,
        "rep_for_parent": rep_for_parent,
        "required_anchors_from": required_anchors_from,
        "stable_hash": stable_hash,
        "tags_of": tags_of,
    }


# Presentation/sound derivation helpers live in presentation_sound.py.
