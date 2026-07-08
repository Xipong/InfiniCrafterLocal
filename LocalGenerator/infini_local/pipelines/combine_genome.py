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
    runtime_plan_to_attack_genome_patch,
)
from infini_local.pipelines.llm_transport import (
    llm_chat_json,
    llm_json_response_format,
    resolve_llm_model,
)
from infini_local.pipelines.parent_context_pipeline import (
    _pbool,
    _pnum,
    effective_projectile_profile_of,
    llm_parent_card,
    parent_weapon_profiles,
    proj_bool,
)

from infini_local.pipelines.combine_balance import apply_family_locks_to_genome, balanced_damage, clamp_vanilla_like_weapon_damage
from infini_local.pipelines.combine_genome_contract import combat_genome_required_for, is_llm_planner

def _normalize_authored_enum_value(value: Any, allowed: dict[str, int] | set[str], field: str = "") -> str:
    v = str(value or "").lower().strip().replace("-", "_").replace(" ", "_")
    if allowed is MOVEMENT_CODE or field == "movement":
        v = MOVEMENT_ALIASES.get(v, v)
    elif allowed is EFFECT_CODE or field == "effect":
        v = EFFECT_ALIASES.get(v, v)
    elif allowed is ONHIT_CODE or field == "onHit":
        v = ONHIT_ALIASES.get(v, v)
    elif allowed is DELIVERY_VALUES or field == "delivery":
        v = DELIVERY_ALIASES.get(v, v)
    elif allowed is RUNTIME_FAMILY_VALUES or field == "runtimeFamily":
        v = "returning" if v in {"boomerang", "chakram", "returning_throw", "glaive_throw"} else DELIVERY_ALIASES.get(v, v)
    return v

def safe_enum(value: Any, allowed: dict[str, int], fallback: str) -> tuple[str, int]:
    v = _normalize_authored_enum_value(value, allowed)
    if v in allowed:
        return v, allowed[v]
    return fallback, allowed[fallback]

def proposed_attack_genome(data: dict[str, Any]) -> dict[str, Any]:
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    genome = attack.get("genome") if isinstance(attack.get("genome"), dict) else {}
    # runtimePlan compiler is authoritative. Flat attack fields fill only numeric/presentation gaps;
    # deprecated prose/script fields are intentionally not copied into executable genome.
    merged = dict(genome)
    for k in ["attackPattern", "pattern", "movement", "effect", "onHit", "shotCount", "spreadRadians", "pierce", "aoeRadiusTiles", "homingStrength", "lifetimeTicks", "extraUpdates", "rangeTiles", "reliability", "selfLockTicks", "missPunish", "useTimeTicks", "runtimeFamily", "delivery", "weaponFamily", "weaponSubfamily", "attackPatternTags", "projectileFamily", "ammoKind", "projectileShape", "projectileMotion", "projectileTrail", "projectileImpact", "soundUseSearchQuery", "soundImpactSearchQuery"]:
        if k in attack and k not in merged:
            merged[k] = attack[k]
    if LLM_RUNTIME_AUTHORING:
        merged.update(runtime_plan_to_attack_genome_patch(data))
    return merged

def genome_defects(data: dict[str, Any]) -> list[str]:
    """Describe missing/malformed required LLM-authored genome fields.

    This function intentionally does not judge fun, novelty, or balance. It only checks
    whether the genome is complete enough to become executable without code inventing
    creative mechanics.
    """
    proposed = proposed_attack_genome(data)
    defects: list[str] = []
    for field in LLM_REQUIRED_GENOME_FIELDS:
        if field not in proposed or proposed.get(field) in (None, ""):
            defects.append(f"missing attack.genome.{field}")

    # Enum fields must be chosen by the LLM from the grammar.
    enum_checks: list[tuple[str, dict[str, int] | set[str]]] = [
        ("delivery", DELIVERY_VALUES),
        ("movement", MOVEMENT_CODE),
        ("effect", EFFECT_CODE),
        ("onHit", ONHIT_CODE),
    ]
    for field, allowed in enum_checks:
        if field not in proposed or proposed.get(field) in (None, ""):
            continue
        value = _normalize_authored_enum_value(proposed.get(field), allowed, field)
        if isinstance(allowed, dict):
            ok = value in allowed
        else:
            ok = value in allowed
        if not ok:
            defects.append(f"unsupported attack.genome.{field}={proposed.get(field)!r}")

    # Required numeric fields must be parseable numbers. Out-of-range numbers are later
    # hard-clamped for engine safety; non-numeric values require LLM repair.
    for field in [
        "useTimeTicks", "shotCount", "pierce", "aoeRadiusTiles", "lifetimeTicks",
        "rangeTiles", "reliability", "selfLockTicks", "missPunish",
    ]:
        if field not in proposed or proposed.get(field) in (None, ""):
            continue
        try:
            x = float(proposed.get(field))
            if not math.isfinite(x):
                raise ValueError("not finite")
        except Exception:
            defects.append(f"non-numeric attack.genome.{field}={proposed.get(field)!r}")

    return defects

def merge_genome_repair(data: dict[str, Any], patch: dict[str, Any]) -> None:
    """Merge a repair response into data.attack.genome.

    The repair model may return {"attack":{"genome":{...}}}, {"genome":{...}}, or a flat
    object containing genome fields. Only known genome fields are merged.
    """
    attack = data.setdefault("attack", {})
    if not isinstance(attack, dict):
        data["attack"] = attack = {}
    genome = attack.setdefault("genome", {})
    if not isinstance(genome, dict):
        attack["genome"] = genome = {}

    src: Any = patch
    if isinstance(patch.get("attack"), dict) and isinstance(patch["attack"].get("genome"), dict):
        src = patch["attack"]["genome"]
    elif isinstance(patch.get("genome"), dict):
        src = patch["genome"]
    if not isinstance(src, dict):
        return

    known = set(LLM_REQUIRED_GENOME_FIELDS) | set(LLM_OPTIONAL_GENOME_DEFAULTS) | {"spreadRadians", "homingStrength", "extraUpdates"}
    for key, value in src.items():
        if key in known:
            genome[key] = value
    attack["enabled"] = True

def try_llm_genome_repair(data: dict[str, Any], a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], key: str, defects: list[str], attempt: int) -> dict[str, Any] | None:
    """Ask the same LLM to fill only missing/malformed combat genome fields.

    This is not a deterministic fallback and not a second critic model. It is the same
    planner being asked to choose concrete mechanics it omitted. If it fails, gameplay
    craft refunds instead of code inventing the missing knobs.
    """
    try:
        model_name = resolve_llm_model()
        existing = proposed_attack_genome(data)
        user = {
            "task": "Repair only missing/malformed attack.genome fields. Return JSON only.",
            "important": [
                "Keep name, tooltip, category, parents, and visual concept.",
                "Pick concrete mechanics now; code will not invent them.",
                "Use weapon-family fields and executable numbers, not prose tags.",
                "Strong ideas need costs: slower useTime, selfLock, missPunish, low reliability, no AoE, or low shotCount.",
            ],
            "defects": defects,
            "attempt": attempt,
            "currentItem": {
                "name": data.get("name"),
                "tooltip": data.get("tooltip"),
                "category": data.get("category"),
                "tags": data.get("tags"),
                "attackGenomeCurrent": existing,
            },
            "parents": [
                llm_parent_card(a, ca),
                llm_parent_card(b, cb),
            ],
            "allowed": {
                "delivery": ["swing", "thrust", "spear", "stab", "rapier", "shortsword", "shoot", "bow", "gun", "launcher", "cast", "staff", "wand", "book", "throw", "boomerang", "summon", "minion", "sentry"],
                "movement": "straight|gravity_arc|drift|orbit|boomerang|bounce|sine_homing|phase|accelerate|spiral|returning_glaive|expanding_wave|flail_tether|yoyo_hover|whip_lash",
                "effect": "none|dust|electric|slime|star|flame|frost|leaf|shadow|poison|blood|honey|sand|lunar|heal|holy|smoke",
                "onHit": "none|burst|split|chain|burn|frostburn|poison|shadowflame|starburst|starfall|aura_pulse|spore_cloud|mini_missiles|vortex_spawn|blackhole|radial_beams|lightning_arc|heal",
                "requiredFields": list(LLM_REQUIRED_GENOME_FIELDS),
                "numericRanges": LLM_NUMERIC_GENOME_LIMITS,
                "optionalFields": LLM_OPTIONAL_GENOME_DEFAULTS,
            },
            "required_json_shape": {
                "attack": {
                    "enabled": True,
                    "genome": {
                        "delivery": "swing|thrust|spear|stab|rapier|shortsword|shoot|bow|gun|launcher|cast|staff|wand|book|throw|boomerang|summon|minion|sentry",
                        "movement": "one of allowed.movement",
                        "effect": "one of allowed.effect",
                        "onHit": "one of allowed.onHit",
                        "useTimeTicks": 24,
                        "shotCount": 1,
                        "pierce": 0,
                        "aoeRadiusTiles": 0,
                        "rangeTiles": 35,
                        "lifetimeTicks": 90,
                        "reliability": 1.0,
                        "selfLockTicks": 0,
                        "missPunish": 0,
                        "homingStrength": 0,
                        "extraUpdates": 0,
                        "spreadRadians": 0
                    }
                }
            }
        }
        system = (
            "Repair incomplete combat genomes for this Terraria-like item generator. "
            "Return JSON only. Fill missing/malformed fields with concrete values. "
            "You are the same planner, not a validator or fallback."
        )
        req = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            "temperature": 0.15,
            "max_tokens": 900,
            "response_format": llm_json_response_format("infini_genome_repair"),
        }
        raw = llm_chat_json(req, timeout=16)
        content = raw["choices"][0]["message"]["content"]
        return parse_first_valid_llm_json(content)
    except Exception as e:
        log_event("warn", "LLM genome repair failed", {"error": repr(e), "attempt": attempt})
        return None

def repair_llm_combat_genome_if_needed(data: dict[str, Any], a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], key: str) -> dict[str, Any]:
    if not combat_genome_required_for(data):
        return data

    debug = data.setdefault("debug", {})
    repair_log: list[dict[str, Any]] = []
    for attempt in range(1, 3):
        defects = genome_defects(data)
        if not defects:
            if repair_log:
                debug["genomeRepair"] = json.dumps(repair_log, ensure_ascii=False)
            return data
        patch = try_llm_genome_repair(data, a, b, ca, cb, key, defects, attempt)
        repair_log.append({"attempt": attempt, "defects": defects, "gotPatch": bool(patch)})
        if not patch:
            break
        merge_genome_repair(data, patch)

    defects = genome_defects(data)
    if defects:
        debug["genomeRepair"] = json.dumps(repair_log, ensure_ascii=False)
        raise PlannerUnavailable("LLM planner did not complete attack.genome after repair loop (" + "; ".join(defects) + "); craft failed and ingredients must be refunded")
    debug["genomeRepair"] = json.dumps(repair_log, ensure_ascii=False)
    return data

def _parse_required_float(value: Any, field: str) -> float:
    try:
        x = float(value)
    except Exception:
        raise PlannerUnavailable(f"LLM planner returned non-numeric attack.genome.{field}; craft failed and ingredients must be refunded")
    if not math.isfinite(x):
        raise PlannerUnavailable(f"LLM planner returned invalid attack.genome.{field}; craft failed and ingredients must be refunded")
    return x

def _hard_clamp_authored_number(value: Any, field: str, debug: dict[str, Any]) -> float:
    x = _parse_required_float(value, field)
    lo, hi = LLM_NUMERIC_GENOME_LIMITS[field]
    y = max(lo, min(hi, x))
    if y != x:
        debug.setdefault("llmGenomeHardClamps", []).append({"field": field, "from": x, "to": y})
    return y

def _require_authored_enum(proposed: dict[str, Any], field: str, allowed: dict[str, int] | set[str]) -> tuple[str, int | None]:
    raw = proposed.get(field)
    v = _normalize_authored_enum_value(raw, allowed, field)
    if isinstance(allowed, dict):
        if v in allowed:
            return v, allowed[v]
        raise PlannerUnavailable(f"LLM planner returned unsupported attack.genome.{field}={raw!r}; craft failed and ingredients must be refunded")
    if v in allowed:
        return v, None
    raise PlannerUnavailable(f"LLM planner returned unsupported attack.genome.{field}={raw!r}; craft failed and ingredients must be refunded")

def llm_authored_weapon_genome(data: dict[str, Any], a: dict[str, Any], b: dict[str, Any], stage: dict[str, Any]) -> dict[str, Any]:
    """Use the LLM's concrete combat genome as the source of truth.

    This is the opposite of the old v2.16 behavior where code/random defaults created most
    knobs and the LLM merely nudged them. If the first LLM response is incomplete, the
    server asks the same LLM to choose the missing mechanics in a repair loop. Only if
    that repair still fails does the craft refund. The validator hard-clamps engine/
    progression outliers and derives execution caps; it does not invent cadence, AoE,
    pierce, delivery, or on-hit fantasy.
    """
    proposed = proposed_attack_genome(data)
    # By the time this function runs, validate_and_repair() has already run the
    # LLM repair loop for missing/malformed fields. Any remaining defect is a hard failure.
    defects = genome_defects(data)
    if defects:
        raise PlannerUnavailable("LLM planner did not author a complete attack.genome after repair (" + "; ".join(defects) + "); craft failed and ingredients must be refunded")

    debug: dict[str, Any] = {}
    delivery, _ = _require_authored_enum(proposed, "delivery", DELIVERY_VALUES)
    movement, mcode = _require_authored_enum(proposed, "movement", MOVEMENT_CODE)
    effect, ecode = _require_authored_enum(proposed, "effect", EFFECT_CODE)
    onhit, hcode = _require_authored_enum(proposed, "onHit", ONHIT_CODE)

    # Required numeric fields: authored by the LLM, hard-clamped only for engine sanity.
    runtime_family = _normalize_authored_enum_value(proposed.get("runtimeFamily"), RUNTIME_FAMILY_VALUES, "runtimeFamily")
    if runtime_family not in RUNTIME_FAMILY_VALUES or runtime_family == "none":
        # Legacy combat-genome compatibility only: accept exact delivery family as light repair.
        runtime_family = "thrust" if delivery in {"thrust", "spear"} else delivery if delivery in RUNTIME_FAMILY_VALUES else "none"
        if runtime_family == "none":
            raise PlannerUnavailable("LLM planner did not author attack.genome.runtimeFamily and delivery was not an exact runtime family; craft failed and ingredients must be refunded")
    g: dict[str, Any] = {
        "runtimeFamily": runtime_family,
        "delivery": delivery,
        "movement": movement, "movementCode": int(mcode),
        "effect": effect, "effectCode": int(ecode),
        "onHit": onhit, "onHitCode": int(hcode),
    }
    for field in [
        "useTimeTicks", "shotCount", "pierce", "aoeRadiusTiles", "lifetimeTicks",
        "rangeTiles", "reliability", "selfLockTicks", "missPunish",
    ]:
        val = _hard_clamp_authored_number(proposed.get(field), field, debug)
        if field in {"useTimeTicks", "shotCount", "pierce", "lifetimeTicks"}:
            val = int(round(val))
        else:
            val = round(val, 3)
        g[field] = val

    # Optional numeric fields may be omitted. These are not creative core; they are execution detail.
    for field, default in LLM_OPTIONAL_GENOME_DEFAULTS.items():
        if field in proposed and proposed.get(field) not in (None, ""):
            val = _hard_clamp_authored_number(proposed.get(field), field, debug)
        else:
            val = default
        if field in {"extraUpdates", "splitCount", "chainCount", "trailLength", "burstDustCap"}:
            val = int(round(val))
        else:
            val = round(float(val), 3)
        g[field] = val

    # Preserve only authored presentation strings. Prose/script-like behavior fields are not executable.
    for field in ["projectileShape", "projectileMotion", "projectileTrail", "projectileImpact", "weaponFamily", "weaponSubfamily", "projectileFamily", "ammoKind", "runtimeFamily", "projectileSizePolicy", "soundUseSearchQuery", "soundImpactSearchQuery"]:
        if field in proposed and proposed.get(field) not in (None, ""):
            g[field] = str(proposed.get(field))[:260 if field not in {"soundUseSearchQuery", "soundImpactSearchQuery"} else 160]
    if isinstance(proposed.get("attackPatternTags"), list):
        g["attackPatternTags"] = [str(x)[:40] for x in proposed.get("attackPatternTags")[:12] if x not in (None, "")]

    # Server-side family locks keep only catastrophic/progression limits; they should not author the item.
    g = apply_family_locks_to_genome(g, a, b, data, stage)
    # Parent profiles are context for debug/recursion only. They do not rewrite authored knobs.
    g["parentProfiles"] = []
    g["llmAuthored"] = True
    g["authoringCoverage"] = {
        "requiredFields": list(LLM_REQUIRED_GENOME_FIELDS),
        "optionalDefaultsUsed": sorted([f for f in LLM_OPTIONAL_GENOME_DEFAULTS if f not in proposed]),
        "hardClampCount": len(debug.get("llmGenomeHardClamps", [])),
    }
    g = sanitize_genome_engine(g, stage)
    # sanitize_genome_engine may adjust lifetime/shotCount/extraUpdates only for technical pressure;
    # cost is then evaluated from the actual executable genome.
    g["costMultiplier"] = round(behavior_cost_multiplier(g), 3)
    if debug:
        g["llmValidationDebug"] = debug
    return g

def weapon_genome_for(data: dict[str, Any], a: dict[str, Any], b: dict[str, Any], tags: set[str], stage: dict[str, Any], damage_class: str) -> dict[str, Any]:
    """Build the executable combat genome.

    Real gameplay crafts use an LLM-authored genome. Deterministic parent-derived defaults are kept
    only for explicit dev/self-test fallback. This keeps the mod fun-first: the model improvises the
    actual cadence/pierce/AoE/delivery, while code only guards engine safety and progression cliffs.
    """
    if is_llm_planner(data):
        return llm_authored_weapon_genome(data, a, b, stage)

    profiles = parent_weapon_profiles(a, b)
    proposed = proposed_attack_genome(data)
    power = float(stage.get("powerBudget", 1.0))
    # Parent-derived behavioral center of mass.
    if profiles:
        best = max(profiles, key=lambda p: float(p.get("effectiveDpsSignal") or 0))
        avg_use = sum(float(p.get("useTime") or 30) for p in profiles) / len(profiles)
        base_use = clamp_float(proposed.get("useTimeTicks"), 10, 150, avg_use)
        inherited_pierce = max(float(p.get("piercePotential") or 0) for p in profiles)
        inherited_extra = max(float(p.get("extraUpdates") or 0) for p in profiles)
        inherited_lifetime = max(float(p.get("lifetime") or 0) for p in profiles)
        parent_projectile = any(float(p.get("shoot") or 0) > 0 for p in profiles)
        parent_no_melee = any(bool(p.get("noMelee")) for p in profiles)
        parent_channel = any(bool(p.get("channel")) for p in profiles)
        owner_hit = any(bool(p.get("ownerHitCheck")) for p in profiles)
        parent_hit_damage = max(float(p.get("damage") or 0) for p in profiles)
    else:
        best = {}
        base_use = float(stage.get("useTime", 24))
        inherited_pierce = 0.0
        inherited_extra = 0.0
        inherited_lifetime = 90.0
        parent_projectile = False
        parent_no_melee = False
        parent_channel = False
        owner_hit = False
        parent_hit_damage = 0.0

    # Delivery is not damage class. Melee can still have projectile channels.
    proposed_delivery = _normalize_authored_enum_value(proposed.get("delivery"), DELIVERY_VALUES, "delivery")
    if proposed_delivery in DELIVERY_VALUES and proposed_delivery != "none":
        delivery = proposed_delivery
    elif damage_class == "magic":
        delivery = "cast"
    elif damage_class == "ranged" or parent_no_melee:
        delivery = "shoot"
    elif parent_projectile and not owner_hit:
        delivery = "shoot" if damage_class != "melee" else "swing"
    else:
        delivery = "swing"

    # Non-runtime fallback uses raw parent cadence only. No item-name/type exceptions.
    fastest_parent_use = min([float(p.get("useTime") or 999) for p in profiles] or [base_use])
    slowest_parent_use = max([float(p.get("useTime") or 0) for p in profiles] or [base_use])
    if fastest_parent_use <= 12:
        base_use = min(base_use, max(7.0, fastest_parent_use + (1.0 if power >= 3.0 else 0.0)))
    if slowest_parent_use >= 60 and parent_hit_damage >= 90:
        base_use = max(base_use, min(95.0, slowest_parent_use))
    if parent_channel:
        base_use = max(base_use, 24.0)

    movement, mcode = movement_for(tags | set(best.get("behaviorTags") or []), stage)
    effect, ecode = effect_for(tags, stage)
    onhit, hcode = onhit_for(tags, stage)
    movement, mcode = safe_enum(proposed.get("movement"), MOVEMENT_CODE, movement)
    effect, ecode = safe_enum(proposed.get("effect"), EFFECT_CODE, effect)
    onhit, hcode = safe_enum(proposed.get("onHit"), ONHIT_CODE, onhit)

    shot_count = int(clamp_float(proposed.get("shotCount"), 1, 8, 1))
    spread = clamp_float(proposed.get("spreadRadians"), 0.0, 0.75, 0.0 if shot_count <= 1 else 0.18 + 0.04 * shot_count)
    pierce = int(clamp_float(proposed.get("pierce"), 0, 10, min(6.0, inherited_pierce)))
    aoe_tiles = clamp_float(proposed.get("aoeRadiusTiles"), 0.0, 10.0, 0.0)
    if onhit in {"burst", "starburst", "radial_beams", "mini_missiles", "vortex_spawn", "aura_pulse"}:
        aoe_tiles = max(aoe_tiles, min(5.0, 1.2 + power * 0.65))
    homing = clamp_float(proposed.get("homingStrength"), 0.0, 1.0, 0.28 if movement in {"slow_homing", "sine_homing"} else 0.0)
    lifetime = int(clamp_float(proposed.get("lifetimeTicks"), 25, 900, max(70.0 + power * 20.0, min(240.0, inherited_lifetime or 90.0))))
    extra_updates = int(clamp_float(proposed.get("extraUpdates"), 0, 3, min(2.0, inherited_extra)))
    range_tiles = clamp_float(proposed.get("rangeTiles"), 4, 120, 65.0 if delivery in {"shoot", "cast"} else 12.0)
    reliability = clamp_float(proposed.get("reliability"), 0.45, 1.25, 0.95 if delivery in {"shoot", "cast"} else 0.82)
    self_lock = clamp_float(proposed.get("selfLockTicks"), 0, 120, max(0.0, base_use - 40.0) * 0.35)
    miss_punish = clamp_float(proposed.get("missPunish"), 0.0, 1.0, 0.55 if base_use >= 70 else 0.15)

    genome = {
        "delivery": delivery,
        "movement": movement, "movementCode": mcode,
        "effect": effect, "effectCode": ecode,
        "onHit": onhit, "onHitCode": hcode,
        "shotCount": shot_count, "spreadRadians": round(spread, 3),
        "pierce": pierce, "aoeRadiusTiles": round(aoe_tiles, 3), "homingStrength": round(homing, 3),
        "lifetimeTicks": lifetime, "extraUpdates": extra_updates, "rangeTiles": round(range_tiles, 2),
        "reliability": round(reliability, 3), "selfLockTicks": round(self_lock, 2), "missPunish": round(miss_punish, 3),
        "useTimeTicks": int(round(base_use)),
        "parentProfiles": profiles,
    }
    genome = sanitize_genome_engine(genome, stage)
    genome["costMultiplier"] = round(behavior_cost_multiplier(genome), 3)
    return genome

def normalize_authored_attack_pattern(genome: dict[str, Any], attack: dict[str, Any], damage_class: str, *, allow_fallback: bool) -> tuple[str, str]:
    """Normalize execution pattern.

    Runtime authoring no longer asks the LLM to choose attackPattern.
    The LLM authors engineCalls/numbers; this compiler chooses the smallest compatible
    C# executor pattern mechanically. Non-runtime fallback may still carry explicit pattern ids.
    """
    raw = genome.get("attackPattern") or genome.get("pattern") or attack.get("pattern") or attack.get("attackPattern")
    delivery = genome.get("delivery") or attack.get("delivery")
    pattern, source = resolve_attack_pattern(raw, delivery=delivery, damage_class=damage_class, allow_fallback=allow_fallback)
    if pattern:
        return pattern, source
    if LLM_RUNTIME_AUTHORING:
        return infer_attack_pattern_from_runtime(genome, damage_class), "runtime_compiler"
    raise PlannerUnavailable("LLM planner did not author a valid attackPattern after repair; craft failed and ingredients must be refunded")

def weapon_numbers_from_genome(max_parent_damage: int, tags: set[str], stage: dict[str, Any], genome: dict[str, Any]) -> dict[str, Any]:
    # Budget is mostly stage/resultPower, but exact hit damage is derived from cadence and cost.
    base_damage = balanced_damage(max_parent_damage, tags | {"weapon"}, stage)
    use_time = int(clamp_float(genome.get("useTimeTicks"), 10, 150, float(stage.get("useTime", 24))))
    cost = max(0.35, float(genome.get("costMultiplier") or 1.0))
    # Convert current derived damage into a rough DPS envelope, then let cadence/cost buy burst.
    base_dps = max(4.0, base_damage * 60.0 / max(10.0, float(stage.get("useTime", 24))))
    if use_time >= 60:
        # Slow weapons may hit hard, but not linearly forever.
        burst_bonus = 1.0 + min(0.45, (use_time - 60) / 220.0)
    else:
        burst_bonus = 1.0
    hit_damage = int(max(1.0, base_dps * use_time / 60.0 * burst_bonus / cost))

    # Fun-first does not mean "accidentally nerf every complex endgame weapon into starter damage".
    # Expensive delivery (pierce, homing, long lifetime, multi-shot) may lower raw hit damage, but if two
    # credible weapon parents are being merged, keep a broad floor relative to the strongest parent hit.
    # Weak-anchor mixes such as Dirt + Last Prism still stay diluted.
    transfer = stage.get("powerTransfer") if isinstance(stage.get("powerTransfer"), dict) else {}
    quality = str(transfer.get("quality") or "")
    weak_anchor = bool(transfer.get("weakAnchor"))
    catalyst_info = stage.get("catalystPressure") if isinstance(stage.get("catalystPressure"), dict) else {}
    catalyst_pressure = float(catalyst_info.get("pressure") or 0.0)
    parent_floor = 0
    if not weak_anchor and max_parent_damage > 0:
        if quality in {"same_role_synergy", "same_family", "same_mod_runtime_synergy", "strong_material_item_synergy"}:
            parent_floor = int(max_parent_damage * (0.42 if use_time < 90 else 0.34))
        elif float(stage.get("powerBudget", 1.0)) >= 3.0:
            parent_floor = int(max_parent_damage * 0.25)
        if catalyst_pressure > 0 and not weak_anchor:
            # Serious crafting materials should not make a weapon feel like it went backwards.
            parent_floor = max(parent_floor, int(max_parent_damage * (0.62 + min(0.28, catalyst_pressure * 0.10))))
    depths = stage.get("parentGeneratedDepths") if isinstance(stage.get("parentGeneratedDepths"), list) else []
    recursive_weapon_parent = any(float(x or 0) > 0 for x in depths)
    primitive_drag = bool(tags & {"dirt", "wood", "stone", "sand", "block", "torch"})
    if recursive_weapon_parent and not primitive_drag and max_parent_damage > 0:
        # A generated weapon used as a playthrough spine should have inertia. It may turn
        # sideways by category policy, but if it remains a weapon, adding a normal material
        # should not randomly collapse hit damage by 70-90%.
        recursive_floor = 0.72 + min(0.20, catalyst_pressure * 0.08)
        parent_floor = max(parent_floor, int(max_parent_damage * recursive_floor))
    if parent_floor > 0:
        hit_damage = max(hit_damage, parent_floor)

    # Fast weapon chains are judged by DPS, not hit damage. Expensive starburst/homing
    # Generic fast-parent floor: based on raw useTime only, not weapon-name/type tags.
    fast_floor_allowed = (not weak_anchor) or catalyst_pressure > 0
    if use_time <= 14 and max_parent_damage > 0 and fast_floor_allowed:
        parent_dps_floor = max_parent_damage * 60.0 / max(6.0, float(stage.get("sourceFastestUseTime") or use_time))
        if weak_anchor:
            target_dps_floor = parent_dps_floor * 0.88
        else:
            target_dps_floor = parent_dps_floor * (1.14 + min(0.42, catalyst_pressure * 0.12))
        hit_damage = max(hit_damage, int(target_dps_floor * use_time / 60.0))

    # Do not let one item become a permanent one-click destroyer. The cap is high enough for comedy rifles.
    hard_cap = max(base_damage + 14, int(max(base_damage, max_parent_damage, 1) * (3.10 + min(1.35, float(stage.get("powerBudget", 1.0)) * 0.16))))
    if use_time >= 90 and int(genome.get("shotCount") or 1) == 1 and float(genome.get("aoeRadiusTiles") or 0) <= 1.0:
        hard_cap = max(hard_cap, int(max(base_damage, max_parent_damage, 1) * 4.35))

    # Recursive fun should not become exponential damage just because a high generated
    # weapon was mixed with a weak bench/block/ammo. Big burst spikes are allowed for
    # credible weapon+weapon/material catalysts, but weak-anchor upgrades get only a
    # small ceiling increase unless the category actually drifted away from weapon.
    if weak_anchor and max_parent_damage > 0:
        weak_anchor_cap = max(max_parent_damage + 26, int(max_parent_damage * (1.38 if use_time >= 60 else 1.26)))
        hard_cap = min(hard_cap, weak_anchor_cap)
    hit_damage = max(1, min(hit_damage, hard_cap))
    hit_damage = clamp_vanilla_like_weapon_damage(
        hit_damage,
        max_parent_damage,
        stage,
        use_time=use_time,
        shot_count=int(genome.get("shotCount") or 1),
        cost_multiplier=cost,
    )
    return {"damage": hit_damage, "useTime": use_time, "useAnimation": use_time}

def attack_pattern_for(tags: set[str], stage: dict[str, Any], damage_class: str) -> dict[str, Any]:
    """Non-runtime fallback pattern, not production design.

    No item-name/tag archetype table here. If runtime authoring is enabled, the model should
    provide the actual behavior through runtimePlan/attack.genome. This fallback only keeps
    non-LLM/dev paths executable.
    """
    power = float(stage.get("powerBudget", 1.0))
    movement, mcode = movement_for(tags, stage)
    effect, ecode = effect_for(tags, stage)
    onhit, hcode = onhit_for(tags, stage)
    name = "basic bolt"
    shot_count = 1
    spread = 0.0
    split = 0
    chain = 0
    bounce = 0
    proc = 0
    if damage_class == "ranged" and power >= 2.0:
        name = "basic volley"
        shot_count = 2
        spread = 0.18
    elif damage_class == "magic" and power >= 1.8:
        name = "basic spell"
        movement, mcode = "slow_homing", MOVEMENT_CODE["slow_homing"]
        effect, ecode = "star", EFFECT_CODE["star"]
    elif damage_class == "summon":
        name = "basic summon"
        movement, mcode = "drift", MOVEMENT_CODE["drift"]
    return {
        "pattern": name,
        "movement": movement, "movementCode": mcode,
        "effect": effect, "effectCode": ecode,
        "onHit": onhit, "onHitCode": hcode,
        "shotCount": shot_count,
        "spreadRadians": spread,
        "procMode": proc,
        "splitCount": split,
        "chainCount": chain,
        "bounceCount": bounce,
    }

# Result knowledge-card helpers live in result_knowledge_card.py.

# Projectile visual-family and parent-affordance helpers live in projectile_affordance.py.

def _parent_tool_power(parent: dict[str, Any], *fields: str) -> int:
    for field in fields:
        try:
            value = int(float(item_num(parent, field, 0)))
        except Exception:
            value = 0
        if value > 0:
            return value
    return 0

def _bounded_parent_potion_stats(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Blend raw parent potion channels without crossing incompatible buff fields.

    Terraria has independent healLife/healMana fields but only one item.buffType slot.
    Old logic used healLife elif healMana elif buff and max(buffType)/max(buffTime), which
    made two-potion merges lose channels or pair one potion's buff id with another potion's
    duration.  Keep the channels independent and keep buff id/time as a real pair.
    """
    parents: list[dict[str, int | str]] = []
    for label, item in (("A", a), ("B", b)):
        def read(field: str) -> int:
            try:
                return max(0, int(float(item_num(item, field, 0))))
            except Exception:
                return 0
        parents.append({
            "label": label,
            "healLife": read("healLife"),
            "healMana": read("healMana"),
            "buffType": read("buffType"),
            "buffTime": read("buffTime"),
        })

    def blend(values: list[int], single_mult: float, cap: int) -> int:
        vals = sorted([int(v) for v in values if int(v) > 0], reverse=True)
        if not vals:
            return 0
        if len(vals) == 1:
            raw = vals[0] * single_mult
        else:
            raw = vals[0] * 1.25 + sum(vals[1:]) * 0.25
        return max(25, min(cap, int(round(raw))))

    heal_life = blend([int(p["healLife"]) for p in parents], 1.45, 200)
    heal_mana = blend([int(p["healMana"]) for p in parents], 1.35, 200)
    buff_code = 0
    buff_time = 0
    buff_note = "none"
    buff_sources = [p for p in parents if int(p["buffType"]) > 0]
    if buff_sources:
        types = {int(p["buffType"]) for p in buff_sources}
        if len(types) == 1:
            buff_code = next(iter(types))
            times = sorted([int(p["buffTime"]) for p in buff_sources if int(p["buffTime"]) > 0], reverse=True)
            raw_time = times[0] + int(round(sum(times[1:]) * 0.25)) if times else 60 * 30
            buff_time = max(60 * 10, min(60 * 60 * 6, raw_time))
            buff_note = "merged_same_buff"
        else:
            chosen = sorted(buff_sources, key=lambda p: (int(p["buffTime"]), int(p["buffType"])), reverse=True)[0]
            buff_code = int(chosen["buffType"])
            buff_time = max(60 * 10, min(60 * 60 * 6, int(chosen["buffTime"]) or 60 * 30))
            buff_note = f"different_parent_buffs_one_item_slot_chose_{chosen['label']}"

    return {
        "healLife": heal_life,
        "healMana": heal_mana,
        "buffCode": max(0, min(1024, buff_code)),
        "buffTime": max(0, min(60 * 60 * 6, buff_time)),
        "extraBuffs": [
            {"buffCode": int(p["buffType"]), "buffTime": max(60 * 10, min(60 * 60 * 6, int(p["buffTime"]) or 60 * 30))}
            for p in buff_sources[:4]
            if int(p["buffType"]) > 0
        ],
        "debug": {
            "parents": parents,
            "buffPolicy": buff_note,
            "rule": "healLife/healMana are independent; buffType/buffTime stay paired; generated items may carry extraBuffs for multi-buff use",
        },
    }

__all__ = [name for name in globals() if callable(globals().get(name)) and not name.startswith("__")]
