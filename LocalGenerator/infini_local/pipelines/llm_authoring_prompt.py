from __future__ import annotations

import json
import math
import re
from copy import deepcopy
from typing import Any

from infini_local.pipelines.author_item_contract import author_item_prompt_shape_card

PLANNER_PROMPT_LIMIT_CHARS = 27_000

from infini_local.core.json_debug import bounded_json_dumps
from infini_local.core.errors import PlannerUnavailable

from infini_local.core.balance_mode import current_balance_mode, should_apply_soft_normalization


from infini_local.core.category_policy import ALLOWED_CATEGORIES
from infini_local.core.item_identity_tools import (
    item_num,
    name_of,
)
from infini_local.core.parent_role_facts import placeable_only_parent_obligation
from infini_local.core.runtime_authoring.common import ENGINE_RUNTIME_API_VERSION
from infini_local.core.runtime_authoring.normalize import (
    normalize_runtime_plan_inplace,
    runtime_plan,
)
from infini_local.core.runtime_authoring.final_projection import compile_runtime_plan_to_final_result
from infini_local.core.runtime_authoring.reports import (
    runtime_plan_quality_report,
    runtime_plan_validation_report,
)
from infini_local.core.runtime_authoring.schema import (
    COMBAT_EXECUTOR_RESULT_KINDS,
    PLANNER_HIDDEN_ENGINE_FUNCTIONS,
)
from infini_local.core.runtime_authoring.function_contract_registry import (
    ACCEPTED_PARAM_EXTRAS_BY_FUNCTION,
    ENGINE_FUNCTION_CATALOG,
    ROOT_EXECUTOR_FUNCTION_NAMES,
    ROOT_EXECUTOR_SHARED_PARAM_NAMES,
)
from infini_local.core.sound_catalog import sound_catalog_card_for_llm
from infini_local.core.runtime_authoring.structural import find_call
from infini_local.core.runtime_family_policy import (
    CANONICAL_RUNTIME_FAMILIES,
    runtime_family_delivery_pairs,
    runtime_family_required_movements,
)
from infini_local.pipelines.engine_pressure_metrics import behavior_cost_multiplier, effective_hit_cadence_ticks

from infini_local.pipelines.pipeline_runtime_constants import (
    LLM_RAW_TOKEN_MODE,
    LLM_RUNTIME_AUTHORING,
    LLM_RUNTIME_PLAN_REQUIRED,
    LLM_RUNTIME_STRICT_VALIDATION,
)
from infini_local.pipelines.result_identity_policy import normalize_category
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

VISIBLE_ENGINE_FUNCTIONS = tuple(sorted(set(ENGINE_FUNCTION_CATALOG) - set(PLANNER_HIDDEN_ENGINE_FUNCTIONS)))
COMBAT_EXECUTOR_RESULT_KIND_RULE = (
    "Combat engine calls are executable only for "
    + " or ".join(f"resultKind={kind}" for kind in sorted(COMBAT_EXECUTOR_RESULT_KINDS))
    + "; every other resultKind must omit combat roots and on-hit combat callbacks."
)
ROOT_EXECUTOR_AUTHOR_RULES = {
    "oneRootExecutor": True,
    "rootExecutorMeaning": "one item-use lifecycle/controller, not one damage source",
    "bodyPlusProjectileEncoding": "shoot_projectile shoot/swing: body hitbox + projectile",
    "temporaryHelperCanFire": False,
    "turretFunction": "deploy_sentry",
}
RUNTIME_PLAN_METADATA_TYPES = {
    "sourceReading": "string",
    "balanceIntent": "string",
    "anomalyFlags": "array[string]",
}
PULL_ON_HIT_ENCODING = {
    "onHit": "none",
    "requiredParams": ["pullStrength", "pullMode"],
}
NEVER_ON_SET_ITEM_STATS = (
    "shotCount", "spreadRadians", "soundUseCatalogId", "soundImpactCatalogId", "soundVolume",
)
RUNTIME_FAMILY_REQUIREMENTS = {
    "beam": ["beamWidthPx", "beamChargeTicks", "immunityCooldown"],
    "charge_release": ["chargeTicks", "chargePowerMultiplier"],
    "overhead_barrage": ["delayTicks", "secondaryDamageMultiplier", "secondaryLifetimeTicks"],
}
RUNTIME_FAMILY_DELIVERIES = {
    family: "|".join(
        delivery
        for candidate, delivery in runtime_family_delivery_pairs()
        if candidate == family
    )
    for family in sorted({family for family, _ in runtime_family_delivery_pairs()})
}
RUNTIME_FAMILY_REQUIRED_MOVEMENT = {
    family: "|".join(sorted(runtime_family_required_movements(family)))
    for family in sorted(CANONICAL_RUNTIME_FAMILIES)
    if runtime_family_required_movements(family)
}
VISUAL_TOPOLOGY_RULES = {
    "connected": {"partCountMin": 1, "partCountMax": 1},
    "multipart_separated": {"partCountMin": 2},
}
EQUIPMENT_LIGHT_ENCODING = {
    "resultKinds": ["armor", "accessory"],
    "authorIn": "armor_effect.stats|accessory_effect.stats",
    "requiredParams": ["lightStrength", "lightColorName"],
    "forbiddenFunction": "emit_light",
}

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
    compile_result = compile_runtime_plan_to_final_result(data)
    final_sections = compile_result.get("finalSections")
    final_sections = final_sections if isinstance(final_sections, dict) else {}
    compiled_gameplay = final_sections.get("gameplay")
    compiled_gameplay = compiled_gameplay if isinstance(compiled_gameplay, dict) else {}
    compiled_kind = str(compiled_gameplay.get("kind") or "").strip()
    if compiled_kind:
        data["category"] = normalize_category(compiled_kind)
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
            "Pressure active<=30; lifetime480/useTime20 + 4 children fails; lower lifetime/count/extraUpdates or slow useTime.",
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
    for fn, spec in ENGINE_FUNCTION_CATALOG.items():
        if fn in PLANNER_HIDDEN_ENGINE_FUNCTIONS:
            continue
        params = spec.get("params") if isinstance(spec.get("params"), dict) else {}
        card: dict[str, Any] = {
            "does": _catalog_text(spec.get("meaning")),
            "params": {str(k): _catalog_text(v) for k, v in params.items()},
        }
        if spec.get("requiresRootExecutor") is True:
            card["requiresRootExecutor"] = True
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
        "Author playable output from both parents; no visual-only result.",
        "Preserve both parents' strong raw/generated affordances; transformations need a central engineCall, not cosmetic stats.",
        "Output only requiredJsonShape keys; never copy input or prompt metadata.",
        "Playable: engineCalls[0]=set_item_stats(resultKind,...); combat also requires damageClass; normally 1-4 calls.",
        "Params=availableFunctions.params + acceptedParamExtras; never add unrelated params. Base item stats use set_item_stats; onHit→apply_on_hit_effect; equipment stats object; names aren't mechanics.",
        "Combat root requires speed,lifetimeTicks,shotCount,spreadRadians,pierce; root/sound params never belong on set_item_stats; shoot_projectile also needs runtimeFamily.",
        "Use runtimeContract family/movement tables; one root; whip damageClass=summon_melee_speed; buff alt needs cooldownTicks>0.",
        "Body pick/axe/hammer: tool_capability + native swing; no melee/projectile combat root.",
        "placeable_behavior is exclusive to resultKind=furniture; omit it for every other resultKind.",
        COMBAT_EXECUTOR_RESULT_KIND_RULE,
        "Child onHit split/chain/starburst/spore_cloud/mini_missiles/vortex_spawn/radial_beams/lightning_arc/overhead_barrage needs count (chainCount for chain/lightning)+secondaryDamageMultiplier+secondaryLifetimeTicks; debuffs need debuffTime.",
        "Named children need spawn_secondary_projectiles projectileShape/material; generic onHit has no identity.",
        "Physical throw defaults to movement=gravity_arc; use movement=straight only when explicitly authoring gravity-free straight flight as part of the item design.",
        "coreMechanic/runtimeStateIntent only engineCalls; tooltip from wire; timeline optional visible-only; sticky/cling unsupported.",
        "Stack-spent weapon uses resultKind=consumable_weapon, consumable=true, maxStack>1, craftYield>0; never spend a reusable gear parent this way. Reusable gear uses maxStack=1, craftYield=1, consumable=false and no consumption_behavior; booleans are true/false.",
        "MUST satisfy runtimeFamilyRequirements for the selected root executor family and visualTopologyRules for visualIntent.",
        "Equipment light requires lightStrength+lightColorName in its armor/accessory stats; no emit_light; utility armor is valid when its explicit stats are executable.",
        "ammoFor is exact inventory cost: empty=no ammo; arrow/bullet consume those vanilla stacks, never a parent material.",

    ]

def engine_runtime_capability_contract_for_llm(a: dict[str, Any], b: dict[str, Any], envelope: dict[str, Any] | None = None) -> dict[str, Any]:
    """Engine API card for the LLM planner.

    The planner receives executable runtime grammar and hard technical limits.
    Parent-relative balance is intentionally not placed in this prompt: the LLM
    authors numbers, then Python applies one code-owned soft balance pass after
    authoring.  This prevents prompt hints from becoming a second balance authority.
    """
    available_functions = sharp_engine_fn_catalog_for_llm()
    root_executor_functions = sorted(ROOT_EXECUTOR_FUNCTION_NAMES)
    parent_role_obligation = placeable_only_parent_obligation(a, b)
    return {
        "mode": ENGINE_RUNTIME_API_VERSION,
        "runtimeApiVersion": ENGINE_RUNTIME_API_VERSION,
        "contractStyle": "sharp",
        "principle": "LLM authors; Python validates; engine executes finite primitives.",
        "runtimeLanguage": "engineCalls=gameplay; runtimeContract=truth/sync.",
        "plannerChecklist": [
            "Pick resultKind; playable outputs start with set_item_stats.",
            "Add only relevant typed gameplay/tool/equipment calls.",
            "VFX never substitutes gameplay; sound ids come from soundCatalog.",
        ],
        "inputDataPolicy": [
            "Parent cards are facts; missing sections are unknown.",
            "Ammo and placeable consumption semantics change only when explicitly authored.",
            "Server does not pre-author visuals or mechanics.",
        ],
        "sourceDerivedParentRoleObligation": (
            parent_role_obligation if parent_role_obligation["applicable"] else {}
        ),
        "availableFunctions": available_functions,
        "acceptedParamExtras": {
            "rootExecutorFunctions": root_executor_functions,
            "rootExecutorParams": sorted(ROOT_EXECUTOR_SHARED_PARAM_NAMES),
            "apply_on_hit_effect": sorted(ACCEPTED_PARAM_EXTRAS_BY_FUNCTION["apply_on_hit_effect"]),
        },
        "requiredAuthorParams": {
            "everyCombatRootExecutor": [
                "speed", "lifetimeTicks", "shotCount", "spreadRadians", "pierce",
            ],
            "childProducingOnHit": [
                "count", "secondaryDamageMultiplier", "secondaryLifetimeTicks",
            ],
            "debuffingOnHit": ["debuffTime"],
            "stackConsumedWeaponIdentity": "consumable_weapon",
            "runtimePlanMetadataTypes": dict(RUNTIME_PLAN_METADATA_TYPES),
            "pullOnHitEncoding": dict(PULL_ON_HIT_ENCODING),
            "neverOnSetItemStats": list(NEVER_ON_SET_ITEM_STATS),
            "runtimeFamilyRequirements": {key: list(value) for key, value in RUNTIME_FAMILY_REQUIREMENTS.items()},
            "runtimeFamilyDeliveries": dict(RUNTIME_FAMILY_DELIVERIES),
            "requiredMovementByFamily": deepcopy(RUNTIME_FAMILY_REQUIRED_MOVEMENT),
            "visualTopologyRules": deepcopy(VISUAL_TOPOLOGY_RULES),
            "equipmentLightEncoding": deepcopy(EQUIPMENT_LIGHT_ENCODING),
            **ROOT_EXECUTOR_AUTHOR_RULES,
        },
        "soundCatalog": sound_catalog_card_for_llm(),
        "tickGuide": concise_terraria_tick_guide_for_llm(),
        "criticalValueSemantics": {
            "pierce": "-1=infinite hits; 0 or 1=one target total; 2..10=total targets, not extra targets.",
            "useTiming": "useTime is cadence; useAnimation=useTime gives one action per click; larger useAnimation may repeat.",
            "shots": "shotCount is simultaneous multishot; extraUpdates are simulation steps.",
            "expire": "on_expire means any projectile kill, not timeout-only.",
            "sentryBudget": "A sentry has at most 48 authored shots over its lifetime.",
            "zero": "beamChargeTicks=0 means beam full immediately; cooldown/count/radius 0 disables that optional behavior.",
            "families": "charge*→charge_release; sentry behavior→deploy_sentry; do not emulate either through prose.",
            "cadence": "immunityCooldown is same-NPC re-hit cadence, not item use cadence.",
        },
        "hardEngineLimits": {
            "maxShotCount": 8,
            "maxFinitePierce": 10,
            "maxLifetimeTicks": 900,
            "maxExtraUpdates": 3,
            "maxActiveProjectileEstimate": 85,
            "maxDustPerSecondEstimate": 260,
            "maxChildProjectiles": 48,
        },
        "semanticRules": [
            "Preserve both parents unless mergeLogic names an executable replacement.",
            "Custom projectiles use weapon or consumable_weapon; every stack-spent weapon uses consumable_weapon; arrow/bullet ammo keeps vanilla ammo identity.",
            "coreMechanic/runtimeStateIntent describe only executable engineCalls; public tooltip is compiled from wire and compiler provenance is not authored.",
            "VFX calls present effects; burst, AoE, sticky, mobility, and utility require their typed gameplay calls.",
            "Temporary helper projectiles never summon bosses, NPCs, mobs, or enemies.",
            "Ore-sense remains diagnostic-only because no ore visual executor is available.",
            "Starfury-style melee-on-use uses shoot_projectile with runtimeFamily=overhead_barrage and delivery=swing.",
        ],
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

def authored_weapon_damage(
    src: dict[str, Any],
    fallback: int,
    max_parent_damage: int,
    stage: dict[str, Any],
    genome: dict[str, Any],
    debug: dict[str, Any],
    *,
    runtime_authored: bool = False,
) -> int:
    """Preserve authored damage by default; normalize only in explicit legacy mode.

    Hard safety remains active in every mode. The stage/DPS envelope is reported
    as advice in report/safety and applied only in normalize. This function does
    not design a new damage value from prose, names or item taxonomy.
    """
    balance_mode = current_balance_mode()
    debug["balanceMode"] = balance_mode
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

def build_llm_author_payload(a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], key: str) -> dict[str, Any]:
    """Build the exact planner user payload without calling the LLM.

    Tests and tooling use this to make sure the prompt stayed usable after adding
    runtime primitives.  This is intentionally the same payload try_llm_plan sends.
    """
    return {
        "task": "Combine itemA+itemB into one playable item. Return one JSON object.",
        "priorityHeader": planner_priority_header_for_llm(),
        "designGoal": "Use both parents; distinct behavior or metamorphosis.",
        "balancePolicy": f"LLM authors numbers; Python reports/clamps per balanceMode={current_balance_mode()}; C# is final safety.",
        "engineRuntimeContract": engine_runtime_capability_contract_for_llm(a, b) if LLM_RUNTIME_AUTHORING else {},
        "rawParentSchema": {"mode": LLM_RAW_TOKEN_MODE, "sections": "item/directProjectile/effectiveProjectile/ammo/runtimeProbe/generatedParent + optional semantics", "rule": "raw=facts; semantics clarify overloaded flags; absent=unknown", "ammoRepresentativeLimit": 0},
        "authorRules": [
            "Return one JSON object exactly matching the source-derived requiredJsonShape card.",
            "Use one result identity: runtimePlan.resultKind equals set_item_stats.resultKind; top category is weapon only for consumable_weapon, otherwise it equals that resultKind.",
            "Use one secondary trigger: on_hit or on_expire; on_expire means any projectile kill. shotCount is simultaneous, not timed.",
            "Projectile=weapon. Custom dart/throwable/rocket=consumable_weapon or weapon + empty ammoFor + projectile call; arrow/bullet ammo has vanilla behavior.",
            "Put fusion physics in concept.mergeLogic, concise central design intent in concept.coreMechanic, and unusual shape/count/placement in runtimePlan.visualIntent topology/parts/arrangement; public gameplay text is compiled from executable wire fields.",
            "Tether/returning sprite is one moving body, never a full-canvas rope. Image prompts: item=inventory/held; projectile=hit body (same sword/blade/boomerang OK); impact=momentary; child=damaging.",
            "Utility/movement needs tool_capability, mobility_effect, or apply_player_effect_on_use; otherwise VFX-only. Never family=unsupported with executable calls.",
            "Non-combat: resultKind preserves sole equip role (head/body/leg→armor+matching armorSlot); otherwise require exact executable replacement; never default weapon.",
            "No markdown, analysis, legacy attackPattern, or attack.genome.",
        ],
        "requiredJsonShape": author_item_prompt_shape_card(),

        # Parent facts are the only recipe-specific suffix. The model authors the
        # concept and mechanics without a Python-selected semantic lane.
        "itemA": raw_parent_card_for_llm(a),
        "itemB": raw_parent_card_for_llm(b),
    }

def planner_prompt_usability_report(a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], key: str) -> dict[str, Any]:
    payload = build_llm_author_payload(a, b, ca, cb, key)
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    contract = payload.get("engineRuntimeContract") if isinstance(payload.get("engineRuntimeContract"), dict) else {}
    functions = contract.get("availableFunctions") if isinstance(contract.get("availableFunctions"), dict) else {}
    within_recommended_chars = len(text) <= PLANNER_PROMPT_LIMIT_CHARS
    return {
        "ok": bool(functions) and "requiredJsonShape" in payload and within_recommended_chars,
        "chars": len(text),
        "approxTokens": max(1, len(text) // 4),
        "recommendedLimitChars": PLANNER_PROMPT_LIMIT_CHARS,
        "withinRecommendedChars": within_recommended_chars,
        "sizeGateMode": "hard_limit",
        "contractStyle": contract.get("contractStyle"),
        "functionCount": len(functions),
        "hasRequiredShape": "requiredJsonShape" in payload,
        "hasRuntimePlanShape": isinstance(payload.get("requiredJsonShape", {}).get("runtimePlan"), dict),
        "hasNoBossRule": "boss" in json.dumps(payload, ensure_ascii=False).lower(),
        "note": "Prompt-only readiness check with a hard size limit; does not call the LLM.",
    }

__all__ = ['normalize_llm_attack_shape', 'normalize_behavior_toy_fields', 'runtime_value', 'normalize_runtime_authoring_fields', 'terraria_tick_guide_for_llm', '_catalog_text', 'sharp_engine_fn_catalog_for_llm', 'concise_terraria_tick_guide_for_llm', 'planner_priority_header_for_llm', 'engine_runtime_capability_contract_for_llm', 'authored_num', 'authored_int', 'authored_weapon_damage', 'authored_str', 'llm_category_without_router', 'build_llm_author_payload', 'planner_prompt_usability_report']
