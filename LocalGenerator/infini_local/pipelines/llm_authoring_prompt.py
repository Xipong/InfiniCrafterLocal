from __future__ import annotations

import json
import math
import re
from typing import Any

PLANNER_PROMPT_LIMIT_CHARS = 24_750
MECHANIC_BACKING_REF_RULES: tuple[str, ...] = (
    "backingRefs.source must be exactly compiledAttack, runtimeArchetype, or engineCall; never put an engine function name in source.",
    "For source=engineCall, callIndex is the zero-based absolute index into runtimePlan.engineCalls (including set_item_stats); fn must exactly match engineCalls[callIndex].fn.",
    'Example for the first projectile call after set_item_stats: {"source":"engineCall","callIndex":1,"fn":"shoot_projectile","field":"movement","expected":"boomerang"}.',
)

from infini_local.core.json_debug import bounded_json_dumps
from infini_local.core.errors import PlannerUnavailable

from infini_local.core.balance_mode import current_balance_mode, should_apply_soft_normalization


from infini_local.core.category_policy import ALLOWED_CATEGORIES
from infini_local.core.item_identity_tools import (
    item_num,
    name_of,
    stable_hash,
)
from infini_local.core.runtime_authoring.common import ENGINE_RUNTIME_API_VERSION
from infini_local.core.runtime_authoring.normalize import (
    normalize_runtime_plan_inplace,
    runtime_plan,
)
from infini_local.core.runtime_authoring.reports import (
    compile_runtime_plan_to_genome_result,
    compiled_runtime_contract,
    runtime_plan_quality_report,
    runtime_plan_validation_report,
)

from infini_local.core.runtime_authoring.schema import (
    ENGINE_FN_CATALOG_V2,
    PLANNER_HIDDEN_ENGINE_FUNCTIONS,
)
from infini_local.core.sound_catalog import sound_catalog_card_for_llm
from infini_local.core.runtime_authoring.structural import find_call
from infini_local.pipelines.engine_pressure_metrics import behavior_cost_multiplier, effective_hit_cadence_ticks

from infini_local.pipelines.pipeline_runtime_constants import (
    LLM_RAW_TOKEN_MODE,
    LLM_RUNTIME_AUTHORING,
    LLM_RUNTIME_PLAN_REQUIRED,
    LLM_RUNTIME_STRICT_VALIDATION,
)
from infini_local.pipelines.result_identity_policy import (
    choose_from,
    normalize_category,
)
from infini_local.pipelines.combine_balance import (
    clamp_vanilla_like_weapon_damage,
)
from infini_local.pipelines.combine_genome_contract import (
    combat_genome_required_for,
    is_llm_planner,
)
from infini_local.pipelines.parent_context_cards import (
    raw_parent_card_for_llm,
)

def normalize_llm_attack_shape(obj: dict[str, Any]) -> dict[str, Any]:
    """Normalize only structural attack/genome duplication from older LLM shapes."""
    attack = obj.get("attack") if isinstance(obj.get("attack"), dict) else {}
    if not attack:
        return obj
    genome = attack.get("genome") if isinstance(attack.get("genome"), dict) else {}
    conflicts = []
    for k in ["delivery", "movement", "effect", "onHit"]:
        if k in attack and k in genome and str(attack.get(k)).lower() != str(genome.get(k)).lower():
            conflicts.append({"field": k, "attack": attack.get(k), "genome": genome.get(k)})
    if conflicts:
        obj.setdefault("debug", {})["attackGenomeConflictsIgnored"] = json.dumps(conflicts, ensure_ascii=False)
    if genome:
        obj["attack"] = {"enabled": bool(attack.get("enabled", True)), "genome": genome}
    return obj

def normalize_behavior_toy_fields(obj: dict[str, Any]) -> dict[str, Any]:
    """Preserve authored text/visual fields without inferring mechanics from keywords.

    This is deliberately not a semantic router. It only maps slim visual prompt fields and
    optional behaviorToy/projectileGenome text into existing string slots, so older cached
    responses do not crash while runtimePlan remains the authored executable source.
    """
    attack = obj.get("attack") if isinstance(obj.get("attack"), dict) else {}
    if not isinstance(attack, dict):
        attack = {}
        obj["attack"] = attack
    toy = obj.get("behaviorToy") if isinstance(obj.get("behaviorToy"), dict) else {}
    pg = obj.get("projectileGenome") if isinstance(obj.get("projectileGenome"), dict) else {}
    concept = obj.get("concept") if isinstance(obj.get("concept"), dict) else {}
    visual = obj.get("visual") if isinstance(obj.get("visual"), dict) else {}
    vp = obj.get("visualPipeline") if isinstance(obj.get("visualPipeline"), dict) else {}
    vd = obj.get("visualDirectives") if isinstance(obj.get("visualDirectives"), dict) else {}

    def flat(x: Any, limit: int = 900) -> str:
        if x is None:
            return ""
        if isinstance(x, str):
            return x.strip()[:limit]
        if isinstance(x, (int, float, bool)):
            return str(x)
        if isinstance(x, list):
            parts = [flat(v, 220) for v in x]
            return "; ".join(v for v in parts if v)[:limit]
        if isinstance(x, dict):
            parts = []
            for k, v in x.items():
                fv = flat(v, 240)
                if fv:
                    parts.append(f"{k}: {fv}")
            return "; ".join(parts)[:limit]
        return str(x).strip()[:limit]

    def set_if(dst: str, *sources: Any, limit: int = 700) -> None:
        if attack.get(dst):
            return
        for src in sources:
            txt = flat(src, limit).strip()
            if txt:
                attack[dst] = txt[:limit]
                return

    # Deprecated prose/script attack fields are not filled here anymore. Runtime behavior is
    # authored through runtimePlan.engineCalls and compiled to explicit AttackSpec fields.
    set_if("projectileShape", pg.get("shape"), vd.get("projectileShape"), visual.get("projectileBrief"), visual.get("objectType"), limit=420)
    set_if("projectileMotion", pg.get("motionFeel"), pg.get("motion"), vd.get("motion"), limit=420)
    set_if("projectileRotation", pg.get("rotation"), vd.get("rotation"), limit=280)
    set_if("projectileTrail", pg.get("trail"), vd.get("trail"), limit=420)
    set_if("projectileImpact", pg.get("impact"), vd.get("impact"), limit=420)
    set_if("projectileChild", pg.get("childProjectile"), pg.get("children"), vd.get("child"), limit=500)
    if isinstance(visual, dict):
        if visual.get("itemPrompt") and not visual.get("imagePrompt"):
            visual["imagePrompt"] = flat(visual.get("itemPrompt"), 1200)
        if visual.get("projectilePrompt") and not visual.get("projectileImagePrompt"):
            visual["projectileImagePrompt"] = flat(visual.get("projectilePrompt"), 1200)
        if visual.get("impactPrompt") and not visual.get("impactImagePrompt"):
            visual["impactImagePrompt"] = flat(visual.get("impactPrompt"), 1200)
        if not visual.get("projectileImagePrompt"):
            visual["projectileImagePrompt"] = flat(vp.get("projectile") or vd.get("projectilePrompt") or pg.get("spritePrompt") or pg.get("shape"), 1200)
        if not visual.get("impactImagePrompt"):
            visual["impactImagePrompt"] = flat(vp.get("impact") or vd.get("impactPrompt") or pg.get("impactSpritePrompt") or pg.get("impact"), 1200)
        if not visual.get("childImagePrompt"):
            visual["childImagePrompt"] = flat(vp.get("child") or vd.get("childPrompt") or pg.get("childProjectile"), 1000)
        if not visual.get("fieldImagePrompt"):
            visual["fieldImagePrompt"] = flat(vp.get("field") or vd.get("fieldPrompt"), 1000)
        if not visual.get("imagePrompt"):
            visual["imagePrompt"] = flat(vp.get("item") or vd.get("itemPrompt") or visual.get("brief"), 1200)
        obj["visual"] = visual
    obj["attack"] = attack
    return obj

def runtime_value(data: dict[str, Any], fn: str, field: str, fallback: Any = None) -> Any:
    rp = runtime_plan(data)
    params = find_call(rp, fn)
    if isinstance(params, dict) and field in params:
        return params.get(field)
    if isinstance(rp.get("runtimeParams"), dict) and field in rp["runtimeParams"]:
        return rp["runtimeParams"].get(field)
    if isinstance(rp.get("combat"), dict) and field in rp["combat"]:
        return rp["combat"].get(field)
    return fallback

def runtime_plan_to_attack_genome_patch(data: dict[str, Any]) -> dict[str, Any]:
    """Compile authored runtimePlan.engineCalls into executable AttackSpec-shaped keys once per craft."""
    if not LLM_RUNTIME_AUTHORING:
        return {}
    normalize_runtime_plan_inplace(data)
    signature = json.dumps(runtime_plan(data), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    cache = data.get("_runtimePlanCompileCache")
    if (
        isinstance(cache, dict)
        and cache.get("signature") == signature
        and isinstance(cache.get("patch"), dict)
    ):
        return dict(cache.get("patch") or {})
    result = compile_runtime_plan_to_genome_result(data)
    patch = result.get("patch") if isinstance(result, dict) else {}
    patch = patch if isinstance(patch, dict) else {}
    data["_runtimePlanCompileCache"] = {"signature": signature, "patch": dict(patch), "result": result}
    debug = data.setdefault("debug", {})
    debug["runtimeApiVersion"] = ENGINE_RUNTIME_API_VERSION
    debug["runtimePlanCompiler"] = bounded_json_dumps(result.get("quality", {}), max_chars=6000)
    debug["runtimePlanValidation"] = bounded_json_dumps(result.get("validation", {}), max_chars=6000)
    debug["runtimePlanProvenance"] = bounded_json_dumps(result.get("provenance", {}), max_chars=6000)
    data["runtimeCompiled"] = result.get("compiled", compiled_runtime_contract(data, patch))
    debug["runtimeCompiled"] = bounded_json_dumps(data.get("runtimeCompiled", {}), max_chars=6000)
    if isinstance(data.get("attack"), dict):
        data["attack"]["runtimeAuthoringProvenance"] = result.get("provenance", {})
    return dict(patch)

def normalize_runtime_authoring_fields(data: dict[str, Any]) -> dict[str, Any]:
    if not LLM_RUNTIME_AUTHORING:
        return data
    rp = runtime_plan(data)
    if not rp:
        if LLM_RUNTIME_PLAN_REQUIRED and is_llm_planner(data):
            raise PlannerUnavailable(
                "LLM-authored result is missing runtimePlan/engineCalls; "
                "code will not fall back to parent/tag semantic gameplay authoring"
            )
        return data
    data.setdefault("debug", {})["runtimeAuthoringMode"] = "llm_engine_calls_v0_4_25"
    # Validation owns normalization.  Pre-normalizing here would feed semantic
    # compiler expansions back into the public raw-authoring schema and reject
    # legitimate deploy_sentry/overhead_barrage fields as unknown.
    validation = runtime_plan_validation_report(data)
    rp = runtime_plan(data)
    data.setdefault("debug", {})["runtimePlanQuality"] = bounded_json_dumps(runtime_plan_quality_report(data), max_chars=6000)
    data.setdefault("debug", {})["runtimePlanValidation"] = bounded_json_dumps(validation, max_chars=6000)
    if LLM_RUNTIME_STRICT_VALIDATION and not validation.get("ok", False) and combat_genome_required_for(data):
        raise PlannerUnavailable("LLM runtimePlan failed engine-call validation: " + "; ".join(validation.get("errors") or ["unknown error"]))
    patch = runtime_plan_to_attack_genome_patch(data)
    if patch:
        attack = data.setdefault("attack", {}) if isinstance(data.get("attack"), dict) else data.setdefault("attack", {})
        genome = attack.setdefault("genome", {}) if isinstance(attack.get("genome"), dict) else {}
        attack["genome"] = genome
        for k, v in patch.items():
            genome[k] = v
        data.setdefault("debug", {})["runtimePlanGenomePatch"] = bounded_json_dumps(patch, max_chars=6000)
    result_kind = runtime_value(data, "set_item_stats", "resultKind", None) or rp.get("resultKind")
    if result_kind:
        data["category"] = normalize_category(str(result_kind))
        data.setdefault("gameplay", {})["kind"] = data["category"]
    gp = data.setdefault("gameplay", {}) if isinstance(data.get("gameplay"), dict) else data.setdefault("gameplay", {})
    # Utility engineCalls compile into the same concrete gameplay fields as set_item_stats.
    # This is not a semantic router: it only copies explicit executable fields authored in
    # runtimePlan to the tML item contract.
    for field in ["healLife", "healMana", "buffCode", "buffTime", "pickPower", "axePower", "hammerPower"]:
        if field in patch and patch.get(field) not in (None, ""):
            gp[field] = patch.get(field)
    if isinstance(patch.get("extraBuffs"), list):
        gp["extraBuffs"] = patch.get("extraBuffs")[:4]
    if isinstance(patch.get("generatedBuff"), dict):
        gp["generatedBuff"] = patch.get("generatedBuff")
    if patch.get("miningSpeedScale") not in (None, ""):
        gp["miningSpeedScale"] = patch.get("miningSpeedScale")
    if patch.get("mobilityMode"):
        gp["mobilityMode"] = patch.get("mobilityMode")
        gp["mobilityRangeTiles"] = patch.get("mobilityRangeTiles", 0)
        gp["mobilityCooldownTicks"] = patch.get("mobilityCooldownTicks", 0)
        gp["mobilitySafeTileOnly"] = bool(patch.get("mobilitySafeTileOnly", True))
    affordance_fields = ["heldVisibility", "releaseTiming", "handPose", "initialOffsetPx"]
    for field in ["altUseMode", "altMobilityMode", "altMobilityRangeTiles", "altMobilityCooldownTicks", "altMobilitySafeTileOnly", "holdLightStrength", "holdLightColorName", "itemScale", "holdoutOffsetX", "holdoutOffsetY", "autoReuse", "useTurn", "channelUse", "consumeChancePercent", "ammoFor", "useConditionMode", "useConditionMinLife", "useConditionMinMana"] + affordance_fields:
        if field in patch and patch.get(field) not in (None, ""):
            gp[field] = patch.get(field)
    authored_affordance = {field: patch.get(field) for field in ["itemScale", "holdoutOffsetX", "holdoutOffsetY", "autoReuse", "useTurn", "channelUse"] + affordance_fields if field in patch and patch.get(field) not in (None, "")}
    if authored_affordance:
        authored_affordance.setdefault("schema", "infini.runtime-affordance.v2")
        authored_affordance.setdefault("note", "Author-provided use/draw feel. It does not change damage, resultKind, or runtimeFamily by itself.")
        data["runtimeAffordance"] = authored_affordance
        data.setdefault("debug", {})["runtimeAffordance"] = bounded_json_dumps(authored_affordance, max_chars=2000)
    if isinstance(patch.get("altGeneratedBuff"), dict):
        gp["altGeneratedBuff"] = patch.get("altGeneratedBuff")
    if isinstance(patch.get("holdGeneratedBuff"), dict):
        gp["holdGeneratedBuff"] = patch.get("holdGeneratedBuff")
    if isinstance(patch.get("runtimeState"), dict):
        gp["runtimeState"] = patch.get("runtimeState")
    if isinstance(patch.get("rejectedEngineCalls"), list):
        gp["rejectedEngineCalls"] = patch.get("rejectedEngineCalls")[:16]
        data.setdefault("debug", {})["rejectedEngineCalls"] = bounded_json_dumps(gp["rejectedEngineCalls"], max_chars=6000)
    if isinstance(patch.get("accessory"), dict):
        data["accessory"] = patch.get("accessory")
        gp["kind"] = "accessory"
        data["category"] = "accessory"
    if isinstance(patch.get("armor"), dict):
        data["armor"] = patch.get("armor")
        gp["kind"] = "armor"
        data["category"] = "armor"
    if patch.get("kind") not in (None, ""):
        gp["kind"] = patch.get("kind")
    for field in ["damageClass", "damage", "useTime", "useAnimation", "knockback", "autoReuse", "maxStack", "consumable", "rarity", "value", "healLife", "healMana", "buffTime", "pickPower", "axePower", "hammerPower", "manaCost"]:
        val = runtime_value(data, "set_item_stats", field, None)
        if val not in (None, ""):
            gp[field] = val
    use_time_ticks = runtime_value(data, "set_item_stats", "useTimeTicks", None)
    if use_time_ticks not in (None, ""):
        gp["useTime"] = use_time_ticks
        gp.setdefault("useAnimation", use_time_ticks)
    use_animation_ticks = runtime_value(data, "set_item_stats", "useAnimationTicks", None)
    if use_animation_ticks not in (None, ""):
        gp["useAnimation"] = use_animation_ticks
    buff_type = runtime_value(data, "set_item_stats", "buffType", None)
    if buff_type not in (None, ""):
        gp["buffCode"] = buff_type
    buff_code = runtime_value(data, "set_item_stats", "buffCode", None)
    if buff_code not in (None, ""):
        gp["buffCode"] = buff_code
    craft_yield = runtime_value(data, "set_item_stats", "craftYield", None)
    if craft_yield not in (None, ""):
        try:
            gp["craftYield"] = max(1, int(float(craft_yield)))
        except Exception:
            gp["craftYield"] = craft_yield
    ammo_for = runtime_value(data, "set_item_stats", "ammoFor", None)
    if ammo_for not in (None, ""):
        gp["ammoFor"] = str(ammo_for)
    vi = rp.get("visualIntent") if isinstance(rp.get("visualIntent"), dict) else {}
    if vi:
        visual = data.setdefault("visual", {}) if isinstance(data.get("visual"), dict) else data.setdefault("visual", {})
        for src, dst in [("projectile", "projectileImagePrompt"), ("impact", "impactImagePrompt"), ("item", "imagePrompt")]:
            if vi.get(src) and not visual.get(dst):
                visual[dst] = str(vi.get(src))
        # Visual intent belongs to presentation/VFX owners.  AttackSpec is the strict
        # executable Python <-> C# contract and must not carry authoring prose.
        if vi.get("vfxIntent"):
            visual["vfxIntent"] = str(vi.get("vfxIntent"))
        if vi.get("vfxAvoid"):
            visual["vfxAvoid"] = str(vi.get("vfxAvoid"))
    return data

def terraria_tick_guide_for_llm() -> dict[str, Any]:
    """Compact timing/reference card for authored runtimePlan values.

    Data-only prompt helper: it explains Terraria ticks and safe numeric bands, but it does
    not infer item families or rewrite mechanics.
    """
    return {
        "clock": {
            "ticksPerSecond": 60,
            "oneTickSeconds": 0.0167,
            "rule": "60 ticks = 1 second; author timings in ticks.",
        },
        "itemUse": {
            "useTimeTicks": "Cooldown between uses; lower is faster; clamped to >=10.",
            "useAnimationTicks": "Usually match useTime unless a longer swing/cast is intended.",
            "safeBands": {
                "veryFast": "10-14: tiny blades/darts; high projectile pressure risk",
                "fast": "15-22: quick bows, light guns, small throwables",
                "normal": "23-34: most generated weapons",
                "slow": "35-55: heavy shots, hammers, payoff casts",
                "verySlow": "56-90+: cannons, rituals, large payoff attacks",
            },
        },
        "projectiles": {
            "lifetimeTicks": {"30": "0.5s", "60": "1s", "90": "1.5s", "180": "3s", "300": "5s", "600": "10s"},
            "rangeEstimate": "pixels ~= speed*lifetime; 16px = 1 tile.",
            "rangeTilesEstimate": "tiles ~= speed*lifetime/16; speed 8, lifetime 90 => ~45 tiles.",
            "extraUpdates": "0 default; 1 smoother; 2-3 only for fast/precise effects, costs CPU/network.",
        },
        "commonNumbers": {
            "shortMeleeExtension": {"useTimeTicks": "16-26", "lifetimeTicks": "10-24", "rangeTiles": "2-8"},
            "smallThrowable": {"useTimeTicks": "14-24", "speed": "7-11", "lifetimeTicks": "45-90", "rangeTiles": "20-60"},
            "bowLikeShot": {"useTimeTicks": "20-32", "speed": "8-13", "lifetimeTicks": "60-120", "rangeTiles": "35-90"},
            "heavyProjectile": {"useTimeTicks": "34-55", "speed": "5-9", "lifetimeTicks": "90-180", "rangeTiles": "30-85"},
            "secondaryShard": {"lifetimeTicks": "6-20", "damageMultiplier": "0.15-0.45", "spreadRadians": "0.15-0.65"},
        },
        "warnings": [
            "useTimeTicks <10 is clamped.",
            "shotCount * low useTime * extraUpdates raises projectile pressure.",
            "Visual motes => spawn_contact_particles; damaging fragments => spawn_secondary_projectiles(on_hit).",
            "For damaging fragments set count, damageMultiplier, and lifetimeTicks.",
        ],
    }

def _catalog_text(value: Any) -> str:
    """Return catalog text without semantic loss.

    The engine catalog is the model's API manual.  It may be short and dense,
    but it must not truncate ranges, enum values, safety notes, or execution
    semantics.  Keep full field text here; reduce prompt size only by removing
    unrelated prompt prose, not by damaging capability descriptions.
    """
    text = str(value or "").strip().replace("\n", " ")
    return re.sub(r"\s+", " ", text)

def sharp_engine_fn_catalog_for_llm() -> dict[str, Any]:
    """Short, dense, complete engine-call catalog for the planner.

    This is not a semantic router and not a lossy summary.  It keeps every
    executable function, every parameter, full ranges/enums, and safety notes.
    The model needs this catalog to understand what each generated item can do.
    """
    out: dict[str, Any] = {}
    for fn, spec in ENGINE_FN_CATALOG_V2.items():
        if fn in PLANNER_HIDDEN_ENGINE_FUNCTIONS:
            continue
        params = spec.get("params") if isinstance(spec.get("params"), dict) else {}
        card: dict[str, Any] = {
            "does": _catalog_text(spec.get("meaning")),
            "params": {str(k): _catalog_text(v) for k, v in params.items()},
        }
        if fn == "spawn_temporary_helper_projectile":
            card["safety"] = "temporary projectile helper only; boss/NPC/mob/enemy spawn calls are forbidden and rejected"
        out[fn] = card
    return out

def concise_terraria_tick_guide_for_llm() -> dict[str, str]:
    return {
        "time": "60 ticks = 1 second. useTime/useAnimation are ticks.",
        "itemSpeed": "10-18 very fast, 20-30 normal-fast, 35-50 slow, 60+ heavy.",
        "projectiles": "lifetime 60=1s, 180=3s, 900=15s. extraUpdates 0..3 only.",
        "stacks": "gear maxStack=1; ammo/material outputs usually craftYield/maxStack 25+.",
        "safety": "Large AoE, many projectiles, or high dust counts are clamped, not re-authored.",
    }

def planner_priority_header_for_llm() -> list[str]:
    """Short hierarchy for the authoring model before the full API card.

    This intentionally does not remove raw facts or engine functions.  It only tells
    small/fast planners which obligations outrank the surrounding reference material.
    """
    return [
        "Author one playable result from both parents; do not merely describe visuals.",
        "Playable non-material/non-furniture: set_item_stats first, then one executable gameplay call.",
        "Promises need engineCalls/numbers/contracts; do not infer mechanics from names.",
        "Simulate held sprite, emitted body, surface collision, NPC collision, return/expiry; write 4+ runtimeContract.playerViewTimeline steps. Thrust reuses item body. Resource consumption requires an exact call.",
        "Visual prose/VFX is presentation; raw parent fields are evidence.",
        "Placeable consumable usually means spent when placed; not potion/ammo/throwing unless authored.",
        "Keep weird ideas when bounded; unsupported/catastrophic output is rejected.",
        "Return one JSON object only.",
    ]

def engine_runtime_capability_contract_for_llm(a: dict[str, Any], b: dict[str, Any], envelope: dict[str, Any] | None = None) -> dict[str, Any]:
    """Engine API card for the LLM planner.

    The planner receives executable runtime grammar and hard technical limits.
    Parent-relative balance is intentionally not placed in this prompt: the LLM
    authors numbers, then Python applies one code-owned soft balance pass after
    authoring.  This prevents prompt hints from becoming a second balance authority.
    """
    available_functions = sharp_engine_fn_catalog_for_llm()
    return {
        "mode": ENGINE_RUNTIME_API_VERSION,
        "runtimeApiVersion": ENGINE_RUNTIME_API_VERSION,
        "contractStyle": "sharp",
        "principle": "LLM authors identity/numbers/engineCalls; Python validates. Engine still executes only registered finite primitives.",
        "runtimeLanguage": "runtimeArchetype=feel; runtimeContract=sync/truth; unsupported stays explicit.",
        "plannerChecklist": [
            "Pick resultKind; playable outputs start with set_item_stats.",
            "Add one executable attack/effect/tool/equipment/mobility/alt/extractinator call.",
            "Held/channel families may add runtimeArchetype/runtimeContract.",
            "VFX never substitutes gameplay; image prompts name the exact role object.",
            "Sound: exact ids from soundCatalog; never classify names/tooltips.",
            "Parent facts are evidence, not copy commands.",
        ],
        "inputDataPolicy": [
            "Parent cards are facts; missing sections are unknown.",
            "Ammo does not override item-owned projectiles unless authored.",
            "Placeable consumables are spent unless authored otherwise.",
            "Server does not pre-author visuals or mechanics.",
        ],
        "availableFunctions": available_functions,
        "soundCatalog": sound_catalog_card_for_llm(),
        "tickGuide": concise_terraria_tick_guide_for_llm(),
        "criticalValueSemantics": {
            "pierce": "-1=infinite hits; 0 or 1=one target total; 2..10=total targets, not extra targets.",
            "useTiming": "useTime interval; useAnimation=useTime one action/click; useAnimation>useTime may repeat.",
            "shots": "shotCount simultaneous; extraUpdates are steps, not shots.",
            "ammo": "empty custom; arrow/bullet vanilla; custom rocket=launcher+empty.",
            "range": "rangeTiles targets/beam/homing/barrage; straight distance≈speed*lifetime.",
            "families": "homing→homing; beam*→beam; charge*→charge_release; delay→barrage; sentry*→deploy_sentry.",
            "zero": "explicit 0 authored: delay immediate; beam full immediately.",
            "expire": "on_expire is any projectile kill, not timeout-only.",
            "cadence": "immunityCooldown same-NPC re-hit ticks; lower=more DPS.",
            "sentryBudget": "at most 48 shots for sentry lifetime; ends when spent.",
        },
        "hardEngineLimits": {
            "maxShotCount": 8,
            "maxFinitePierce": 10,
            "infinitePierceValue": -1,
            "maxAoeRadiusTiles": 10,
            "maxLifetimeTicks": 900,
            "maxExtraUpdates": 3,
            "maxActiveProjectileEstimate": 85,
            "maxDustPerSecondEstimate": 260,
            "maxChildProjectiles": 48,
            "maxVisualScaleHint": "small/normal unless source explicitly justifies large",
        },
        "semanticRules": [

            "Preserve a complete weapon parent unless ammo/material resultKind and mergeLogic justify replacement.",
            "Generated ammo ammoFor=arrow/bullet has vanilla projectile identity only. For an authored dart/throwable attack use consumable_weapon or weapon, empty ammoFor, and shoot_projectile.",
            "Gameplay/utility promises require an executable call and mechanicClaims backingRefs that resolve exact fields; free-text backing is descriptive only. Visual motifs stay visual_only. Never advertise unsupported mechanics in name, tooltip, concept or runtime intent.",
            "VFX calls present effects; burst/AoE/sticky are gameplay. Player movement must use a mobility engineCall; low-level shoot_projectile needs explicit runtimeFamily.",
            "Ore visual execution is not added in this patch; generic oreSense remains report/debug-only.",
            "spawn_temporary_helper_projectile is short-lived projectile behavior, not a persistent minion/sentry lifecycle. summon_boss/spawn_npc/spawn_enemy are hard-rejected.",
            "Overhead barrage is delivery geometry: on-hit uses apply_on_hit_effect; ranged/magic on-use uses the family call; Starfury-style melee-on-use uses shoot_projectile(runtimeFamily=overhead_barrage,delivery=swing,weaponFamily=broadsword). Authored projectile family/shape/effect keeps the star, arrow, meteor, ice or other theme.",

        ],
        "validatorLimits": {
            "validatorOnly": True,
            "balanceAuthority": f"python_balance_mode:{current_balance_mode()}",
            "note": "Prompt exposes hard engine limits only. Soft parent-relative normalization is applied only in balanceMode=normalize.",
        },
    }

def authored_num(src: dict[str, Any], key: str, fallback: float, lo: float, hi: float) -> float:
    try:
        v = src.get(key)
        if v is None or v == "":
            return fallback
        f = float(v)
        if not math.isfinite(f):
            return fallback
        return max(lo, min(hi, f))
    except Exception:
        return fallback

def authored_int(src: dict[str, Any], key: str, fallback: int, lo: int, hi: int) -> int:
    return int(round(authored_num(src, key, float(fallback), float(lo), float(hi))))

def authored_weapon_damage(src: dict[str, Any], fallback: int, max_parent_damage: int, stage: dict[str, Any], genome: dict[str, Any], debug: dict[str, Any]) -> int:
    """Preserve authored damage by default; normalize only in explicit legacy mode.

    Hard safety remains active in every mode. The stage/DPS envelope is reported
    as advice in report/safety and applied only in normalize. This function does
    not design a new damage value from prose, names or item taxonomy.
    """
    balance_mode = current_balance_mode()
    debug["balanceMode"] = balance_mode
    runtime_authored = bool(genome.get("runtimePlanAuthored"))
    raw = src.get("damage") if isinstance(src, dict) else None
    if runtime_authored:
        debug["damageSource"] = "llm_authored_runtime_contract"
        debug["authoredDamageHardCap"] = 9999
        if raw in (None, ""):
            debug["fallbackDamage"] = int(max(0, fallback))
            return int(max(0, min(9999, fallback)))
        try:
            value = float(raw)
            if not math.isfinite(value):
                raise ValueError("non-finite damage")
            final = max(0, min(9999, int(round(value))))
            if final != int(round(value)):
                debug["authoredDamageClamp"] = {
                    "from": raw,
                    "to": final,
                    "reason": "absolute_runtime_safety_bound",
                }
            return final
        except (TypeError, ValueError, OverflowError):
            debug["invalidAuthoredDamage"] = str(raw)[:80]
            return int(max(0, min(9999, fallback)))

    stage_damage = int(stage.get("derivedDamage") or max_parent_damage or fallback or 4)
    power = max(0.5, float(stage.get("powerBudget") or 1.0))
    hard_cap = int(max(8, stage_damage * 2.60 + 10, max_parent_damage * 3.0 + 18, 14 + power * 35.0))
    parent_depths = stage.get("parentGeneratedDepths") if isinstance(stage, dict) else []
    try:
        recursive_depth = max(int(float(x or 0)) for x in (parent_depths or [0]))
    except (TypeError, ValueError, OverflowError):
        recursive_depth = 0
    if recursive_depth > 0 and 0 < max_parent_damage <= 60:
        recursive_cap = max(12, max_parent_damage + 6, int(max_parent_damage * (1.30 + min(0.18, recursive_depth * 0.05)) + 8), stage_damage + 8)
        row = {
            "parentDepth": recursive_depth,
            "cap": int(recursive_cap),
            "reason": "generated-parent recursion should add behavior/tradeoff, not staircase raw damage",
            "mode": balance_mode,
        }
        if should_apply_soft_normalization(balance_mode):
            hard_cap = min(hard_cap, recursive_cap)
            row["cap"] = int(hard_cap)
            row["applied"] = True
            debug["recursiveDamageSoftCap"] = row
        else:
            row["applied"] = False
            debug["recursiveDamageBalanceAdvice"] = row

    # Absolute guard for broken JSON / absurd API output. It is not the soft balance layer.
    hard_cap = min(999, hard_cap)
    if raw in (None, ""):
        debug["damageSource"] = "fallback_reference_numbers"
        debug["fallbackDamage"] = int(max(1, fallback))
        debug["authoredDamageHardCap"] = hard_cap
        return int(max(1, fallback))
    try:
        f = float(raw)
        if not math.isfinite(f):
            raise ValueError("non-finite damage")
        if f < 0:
            debug["authoredDamageClamp"] = {"from": raw, "to": 0, "reason": "negative"}
            return 0
        authored = max(1, int(round(f)))
        if f > hard_cap:
            debug["authoredDamageClamp"] = {"from": raw, "to": hard_cap, "reason": "hard_safety_cap", "referenceNumbersDamage": int(fallback)}
            authored = max(1, int(round(hard_cap)))
        try:
            use_time = int(float(genome.get("useTimeTicks") or stage.get("useTime") or 24))
        except (TypeError, ValueError, OverflowError):
            use_time = int(stage.get("useTime") or 24)
        try:
            shot_count = int(float(genome.get("shotCount") or 1))
        except (TypeError, ValueError, OverflowError):
            shot_count = 1
        hit_cadence = effective_hit_cadence_ticks(genome, use_time)
        try:
            cost = float(genome.get("costMultiplier") or behavior_cost_multiplier(genome))
        except (TypeError, ValueError, OverflowError):
            cost = 1.0
        suggested = clamp_vanilla_like_weapon_damage(
            authored,
            max_parent_damage,
            stage,
            use_time=int(round(hit_cadence)),
            shot_count=shot_count,
            cost_multiplier=cost,
            raise_floor=False,
        )
        row = {
            "from": authored,
            "to": suggested,
            "reason": "code_owned_stage_dps_envelope",
            "useTime": use_time,
            "effectiveHitCadenceTicks": round(hit_cadence, 3),
            "shotCount": shot_count,
            "costMultiplier": round(cost, 3),
            "referenceNumbersDamage": int(fallback),
            "mode": balance_mode,
        }
        result = authored
        if suggested != authored and should_apply_soft_normalization(balance_mode):
            row["applied"] = True
            debug["authoredDamageEnvelopeClamp"] = row
            result = suggested
        else:
            debug["damageSource"] = "llm_authored_preserved"
            if suggested != authored:
                row["applied"] = False
                debug["authoredDamageBalanceAdvice"] = row
        debug["referenceNumbersDamage"] = int(fallback)
        debug["authoredDamageHardCap"] = hard_cap
        return max(1, int(round(result)))
    except (TypeError, ValueError, OverflowError):
        debug["damageSource"] = "fallback_reference_numbers_invalid_authored"
        debug["invalidAuthoredDamage"] = str(raw)[:80]
        debug["authoredDamageHardCap"] = hard_cap
        return int(max(1, fallback))

def authored_str(src: dict[str, Any], key: str, fallback: str = "") -> str:
    v = src.get(key) if isinstance(src, dict) else None
    return str(v).strip() if v not in (None, "") else fallback

def llm_category_without_router(data: dict[str, Any], requested_kind: Any, tags: set[str], a: dict[str, Any], b: dict[str, Any], key: str | None) -> tuple[str, dict[str, Any]]:
    """Author-first category handling.

    The old category router sometimes rewrote Storage furniture into potion and turned
    LLM design into code output. In LLM mode we accept any known category the model chose;
    only unknown categories are normalized to generic/weapon if combat is obvious.
    """
    raw = normalize_category(requested_kind or data.get("category") or "generic")
    if raw in ALLOWED_CATEGORIES:
        return raw, {"mode": "author_first", "requested": requested_kind, "final": raw, "note": "LLM category preserved; router did not author item"}
    max_parent_damage = max(int(item_num(a, "damage", 0)), int(item_num(b, "damage", 0)))
    fallback = "weapon" if max_parent_damage > 0 or "weapon" in tags else "generic"
    return fallback, {"mode": "author_first", "requested": requested_kind, "final": fallback, "repair": "unknown category only"}

def llm_runtime_result_kind_policy(data: dict[str, Any], requested_kind: Any, tags: set[str], a: dict[str, Any], b: dict[str, Any], key: str | None) -> tuple[str, dict[str, Any]]:
    """Runtime authoring category boundary.

    In v0.4 runtime mode the LLM's set_item_stats.resultKind/runtimePlan.resultKind is the
    authored category. Code may normalize unsupported labels, but it must not sample or route
    the category from parent tags. This keeps category_policy as legacy fallback only.
    """
    rp = runtime_plan(data)
    result_kind = runtime_value(data, "set_item_stats", "resultKind", None) or (rp.get("resultKind") if isinstance(rp, dict) else None) or requested_kind or data.get("category") or "generic"
    raw = str(result_kind or "generic").strip().lower().replace("-", "_")
    if raw in {"thrown_stack", "stackable_weapon", "consumable_projectile", "consumable_weapon"}:
        # Internal runtime category must stay weapon so attach_gameplay_and_attack keeps
        # the authored projectile executor alive. The stack/consume behavior is recorded
        # separately as gameplay.runtimeOutputKind=consumable_weapon. Mapping this to
        # potion/consumable erased the attack and turned grenade/flask outputs back into
        # ordinary parent-buff potions.
        selected = "weapon"
    else:
        selected = normalize_category(raw)
    if selected not in ALLOWED_CATEGORIES:
        selected = "generic"
    return selected, {
        "mode": "llm_runtime_result_kind",
        "requested": requested_kind,
        "runtimeResultKind": raw,
        "final": selected,
        "note": "category comes from authored runtimePlan/set_item_stats; category_policy not used in runtime authoring mode",
    }

def build_llm_author_payload(a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], key: str) -> dict[str, Any]:
    """Build the exact planner user payload without calling the LLM.

    Tests and tooling use this to make sure the prompt stayed usable after adding
    runtime primitives.  This is intentionally the same payload try_llm_plan sends.
    """
    return {
        "task": "Combine itemA and itemB into one playable Terraria-like item. Return one JSON object.",
        "priorityHeader": planner_priority_header_for_llm(),
        "designGoal": "Derive a testable item from both parents. Prefer distinct behavior, but clean metamorphosis is fine.",
        "balancePolicy": f"LLM authors numbers; balanceMode={current_balance_mode()}; report/safety preserve authored soft-balance values, normalize applies the legacy soft envelope; C# is final safety.",
        "engineRuntimeContract": engine_runtime_capability_contract_for_llm(a, b) if LLM_RUNTIME_AUTHORING else {},
        "rawParentSchema": {"mode": LLM_RAW_TOKEN_MODE, "sections": "item/directProjectile/effectiveProjectile/ammo/runtimeProbe/generatedParent + optional semantics notes", "rule": "raw fields are facts; semantics notes only clarify overloaded Terraria flags; absence is unknown, not a negative fact", "ammoRepresentativeLimit": 0},
        "backingRefRules": list(MECHANIC_BACKING_REF_RULES),
        "authorRules": [
            "Return one JSON object with concept, resultKind, authored numbers, engineCalls and concise visual prompts.",
            "Use exactly one secondary trigger: on_hit or on_expire. on_expire means any projectile kill, not timeout-only. shotCount is simultaneous multishot, never a timed burst.",
            "Projectile weapon=weapon. Authored dart/throwable/rocket=consumable_weapon or weapon + empty ammoFor + projectile call. Plain arrow/bullet ammo cannot promise custom runtime effects.",
            "Preserve a generated-parent anchor, then add one bounded tradeoff, timing, delivery or utility twist.",
            "Tether/returning sprite is one moving body with only a short local attachment; never a full-canvas rope. Image prompts: item=inventory/held; projectile=moving hit body (same sword/blade/boomerang OK); impact=momentary hit; child=damaging child/mote.",
            "Utility/player movement needs its exact executable call such as tool_capability, mobility_effect or apply_player_effect_on_use; otherwise keep it VFX-only. Use custom_executor for normal/utility engineCalls; never family=unsupported when executable calls exist.",
            "No markdown, analysis, legacy attackPattern, or attack.genome.",
        ],
        "validatorRanges": {
            "damage": [0, 999],
            "useTimeTicks": [10, 150], "shotCount": [1, 8], "pierce": [-1, 10],
            "rangeTiles": [4, 120], "lifetimeTicks": [25, 900], "extraUpdates": [0, 3],
            "note": "Schema/engine sanity ranges only. Parent-relative balance is applied after authoring; no legacy attack.genome."
        },
        "requiredJsonShape": {
            "name": "short flavorful item name, no Infini/Generated/Hybrid/Combined",
            "tooltip": "short in-game tooltip",
            "concept": {
                "fantasy": "one sentence describing the item",
                "mergeLogic": "one sentence: why these exact parents became this, based on raw parent fields",
                "weirdTwist": "one sentence: memorable non-vanilla behavior or clean metamorphosis"
            },
            "runtimeArchetype": {
                "schema": "infini.runtime-archetype.v1",
                "source": "generated",
                "family": "known finite family",
                "overrideKnobs": {},
            },
            "runtimeContract": {
                "schema": "infini.runtime-contract.v2",
                "primaryVerb": "actual player action",
                "controlStyle": "tap|hold-to-channel|passive|toggle|automatic",
                "stateFields": [],
                "syncFields": [],
                "mechanicClaims": [{"claim": "every public gameplay claim from tooltip/concept", "backing": "human-readable summary only", "backingRefs": [{"source": "compiledAttack|runtimeArchetype|engineCall", "callIndex": "required only for engineCall", "fn": "exact fn for engineCall", "field": "exact machine field", "expected": "exact JSON scalar"}], "status": "executable only when all backingRefs resolve"}],
                "playerViewTimeline": ["held/use", "outbound or active phase", "surface collision", "NPC collision", "return/expiry and what remains on screen"],
                "unsupportedPromises": [],
                "executionStatus": "executable"
            },
            "runtimePlan": {
                "resultKind": "weapon|ammo|consumable_weapon|tool|accessory|armor|potion|material|furniture|generic",
                "sourceRolePreservation": {"itemA": "short", "itemB": "short"},
                "engineCalls": "array of {fn, params}; exact fn names from availableFunctions. No legacy attack.genome or boss/NPC/mob spawn calls.",
                "runtimeStateIntent": "optional state intent; gameplay still needs executable calls",
                "visualIntent": {"item": "brief", "projectile": "brief/empty", "impact": "brief/empty", "vfxIntent": "short", "vfxAvoid": "short"},
                "sourceReading": "short interpretation from raw parent fields; absent data is unknown",
                "balanceIntent": "short tradeoff / why not free power",
                "anomalyFlags": []
            },
            "visual": {
                "itemPrompt": "concise item icon sprite prompt",
                "projectilePrompt": "concise projectile sprite prompt or empty",
                "impactPrompt": "concise impact/expire sprite prompt or empty",
                "notes": "optional short visual note"
            }
        },
        # Recipe-specific fields deliberately form one final suffix. Everything above
        # stays byte-identical across crafts so provider prefix caching can retain the
        # complete executable API card and required output contract.
        "creativeVariance": {
            "recipeSalt": stable_hash(key, name_of(a), name_of(b), length=8),
            "designLane": choose_from([
                "clean metamorphosis with one crisp tradeoff",
                "altered delivery/movement (arc, bounce, return, cast) if parents justify it",
                "on-hit utility with modest direct damage",
                "contact/timing interaction if the parents support it",
                "ammo/projectile reinterpretation with a clear cost",
                "returning/tether or utility twist instead of another straight shot",
                "visual-material fusion with conservative stats",
                "support/control twist rather than another straight damage stick"
            ], "creative_lane", key, name_of(a), name_of(b)),
            "rule": "Avoid cloning the strongest generated parent's name/runtimeFamily/onHit; do not default every weapon to straight+split."
        },
        "itemA": raw_parent_card_for_llm(a),
        "itemB": raw_parent_card_for_llm(b),
    }

def planner_prompt_usability_report(a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], key: str) -> dict[str, Any]:
    payload = build_llm_author_payload(a, b, ca, cb, key)
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    contract = payload.get("engineRuntimeContract") if isinstance(payload.get("engineRuntimeContract"), dict) else {}
    functions = contract.get("availableFunctions") if isinstance(contract.get("availableFunctions"), dict) else {}
    return {
        "ok": len(text) <= PLANNER_PROMPT_LIMIT_CHARS and bool(functions) and "requiredJsonShape" in payload,
        "chars": len(text),
        "approxTokens": max(1, len(text) // 4),
        "contractStyle": contract.get("contractStyle"),
        "functionCount": len(functions),
        "hasRequiredShape": "requiredJsonShape" in payload,
        "hasRuntimePlanShape": isinstance(payload.get("requiredJsonShape", {}).get("runtimePlan"), dict),
        "hasNoBossRule": "boss" in json.dumps(payload, ensure_ascii=False).lower(),
        "note": "Prompt-only readiness check; does not call the LLM.",
    }

__all__ = ['normalize_llm_attack_shape', 'normalize_behavior_toy_fields', 'runtime_value', 'runtime_plan_to_attack_genome_patch', 'normalize_runtime_authoring_fields', 'terraria_tick_guide_for_llm', '_catalog_text', 'sharp_engine_fn_catalog_for_llm', 'concise_terraria_tick_guide_for_llm', 'planner_priority_header_for_llm', 'engine_runtime_capability_contract_for_llm', 'authored_num', 'authored_int', 'authored_weapon_damage', 'authored_str', 'llm_category_without_router', 'llm_runtime_result_kind_policy', 'build_llm_author_payload', 'planner_prompt_usability_report']
