from __future__ import annotations

import json
import math
from typing import AbstractSet, Any
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.runtime_executor_vocabulary import EFFECT_CODE, MOVEMENT_CODE, ONHIT_CODE
from infini_local.core.effect_catalog import resolve_attack_pattern
from infini_local.core.item_identity_tools import item_num
from infini_local.core.llm_json_tools import parse_first_valid_llm_json
from infini_local.core.llm_stage_messages import agent_handoff, planner_history_state, stage_chat_message
from infini_local.core.runtime_authoring.normalize import runtime_plan
from infini_local.core.runtime_authoring.reports import infer_attack_pattern_from_runtime
from infini_local.core.runtime_authoring.schema import _runtime_family_affordances
from infini_local.core.runtime_family_policy import CANONICAL_RUNTIME_FAMILIES as RUNTIME_FAMILIES
from infini_local.core.runtime_authoring.vocabulary import (
    DELIVERIES,
    normalize_authoring_enum,
)
from infini_local.pipelines.engine_pressure_metrics import (
    behavior_cost_multiplier,
    effective_hit_cadence_ticks,
    clamp_float,
    estimate_engine_metrics,
    sanitize_genome_engine,
)
from infini_local.pipelines.pipeline_runtime_constants import (
    LLM_NUMERIC_GENOME_LIMITS,
    LLM_OPTIONAL_GENOME_DEFAULTS,
    LLM_REQUIRED_GENOME_FIELDS,
    LLM_RUNTIME_AUTHORING,
)
from infini_local.storage.trace_runtime import log_event
from infini_local.pipelines.presentation_sound import (
    effect_for,
    movement_for,
    onhit_for,
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
    llm_parent_card,
    parent_weapon_profiles,
)

from infini_local.pipelines.combine_balance import apply_family_locks_to_genome, balanced_damage, clamp_vanilla_like_weapon_damage
from infini_local.pipelines.combine_genome_contract import combat_genome_required_for

def _normalize_authored_enum_value(value: Any, field: str) -> str:
    return normalize_authoring_enum(value, field)


def safe_enum(value: Any, allowed: dict[str, int], fallback: str, field: str) -> tuple[str, int]:
    v = _normalize_authored_enum_value(value, field)
    if v in allowed:
        return v, allowed[v]
    return fallback, allowed[fallback]

def proposed_attack_genome(data: dict[str, Any]) -> dict[str, Any]:
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    genome = attack.get("genome") if isinstance(attack.get("genome"), dict) else {}
    # runtimePlan compiler is authoritative. Flat attack fields fill only numeric/presentation gaps;
    # deprecated prose/script fields are intentionally not copied into executable genome.
    merged = dict(genome)
    for k in ["attackPattern", "pattern", "movement", "effect", "onHit", "shotCount", "spreadRadians", "pierce", "aoeRadiusTiles", "homingStrength", "lifetimeTicks", "extraUpdates", "rangeTiles", "useTimeTicks", "useAnimationTicks", "beamWidthPx", "beamChargeTicks", "chargeTicks", "chargePowerMultiplier", "delayTicks", "sentryPlacement", "sentryAttackIntervalTicks", "sentryTargetRangeTiles", "sentryLifetimeTicks", "immunityCooldown", "secondaryTrigger", "pullStrength", "pullMode", "runtimeFamily", "delivery", "weaponFamily", "projectileFamily", "ammoKind", "projectileShape", "projectileMotion", "projectileTrail", "projectileImpact", "soundUseCatalogId", "soundImpactCatalogId", "soundCatalogSource", "soundVolume", "soundPitch", "soundPitchVariance"]:
        if k in attack and k not in merged:
            merged[k] = attack[k]
    if LLM_RUNTIME_AUTHORING and runtime_plan(data):
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
    enum_checks: list[tuple[str, dict[str, int] | AbstractSet[str]]] = [
        ("delivery", DELIVERIES),
        ("runtimeFamily", RUNTIME_FAMILIES),
        ("movement", MOVEMENT_CODE),
        ("effect", EFFECT_CODE),
        ("onHit", ONHIT_CODE),
        ("pullMode", {"none", "target_to_owner", "owner_to_target", "target_to_projectile"}),
    ]
    for field, allowed in enum_checks:
        if field not in proposed or proposed.get(field) in (None, ""):
            continue
        value = _normalize_authored_enum_value(proposed.get(field), field)
        if isinstance(allowed, dict):
            ok = value in allowed
        else:
            ok = value in allowed
        if field == "runtimeFamily" and value == "none":
            ok = False
        if not ok:
            defects.append(f"unsupported attack.genome.{field}={proposed.get(field)!r}")

    try:
        pull_strength = float(proposed.get("pullStrength") or 0.0)
    except (TypeError, ValueError, OverflowError):
        pull_strength = 0.0
    pull_mode = str(proposed.get("pullMode") or "none").strip().lower()
    if pull_strength > 0.0 and pull_mode == "none":
        defects.append("attack.genome.pullStrength>0 requires pullMode=target_to_owner|owner_to_target|target_to_projectile")
    if pull_strength <= 0.0 and pull_mode != "none":
        defects.append("attack.genome.pullMode requires pullStrength>0")

    # Required numeric fields must be parseable numbers. Out-of-range numbers are later
    # hard-clamped for engine safety; non-numeric values require LLM repair.
    for field in [
        "useTimeTicks", "shotCount", "pierce", "aoeRadiusTiles", "lifetimeTicks",
        "rangeTiles", "spreadRadians", "speed",
    ]:
        if field not in proposed or proposed.get(field) in (None, ""):
            continue
        try:
            x = float(proposed.get(field))
            if not math.isfinite(x):
                raise ValueError("not finite")
        except Exception:
            defects.append(f"non-numeric attack.genome.{field}={proposed.get(field)!r}")

    # Reject unsafe combinations instead of silently rewriting authored numbers.
    # Legal individual maxima can still multiply into a projectile/network flood.
    try:
        stage_value = data.get("gameplay")
        stage: dict[str, Any] = stage_value if isinstance(stage_value, dict) else {}
        power = max(0.5, min(8.0, float(proposed.get("powerBudget") or stage.get("powerBudget") or 1.0)))
        metrics = estimate_engine_metrics(proposed, stage)
        max_active = 22.0 + power * 8.0
        max_sync = 26.0 + power * 8.0
        if metrics["activeProjectileEstimate"] > max_active or metrics["networkSyncPressureEstimate"] > max_sync:
            defects.append(
                "composite projectile pressure exceeds runtime safety envelope: "
                f"active={metrics['activeProjectileEstimate']}>{round(max_active, 3)} or "
                f"sync={metrics['networkSyncPressureEstimate']}>{round(max_sync, 3)}; "
                "author lower shotCount/extraUpdates/lifetime or slower useTimeTicks"
            )
    except (TypeError, ValueError, OverflowError):
        defects.append("composite projectile pressure could not be evaluated from authored numbers")

    # Families with dedicated Terraria lifecycle executors must be paired with their
    # exact movement opcode. Otherwise the item affordance says flail/yoyo/whip while
    # the projectile silently executes as an unrelated free shot.
    family = _normalize_authored_enum_value(proposed.get("runtimeFamily"), "runtimeFamily")
    movement = _normalize_authored_enum_value(proposed.get("movement"), "movement")
    required_movement = {
        "flail": "flail_tether",
        "yoyo": "yoyo_hover",
        "whip": "whip_lash",
    }
    if family == "returning" and movement not in {"boomerang", "returning_glaive"}:
        defects.append(f"runtimeFamily=returning requires movement=boomerang|returning_glaive, got {movement or '<empty>'}")
    elif family in required_movement and movement != required_movement[family]:
        defects.append(f"runtimeFamily={family} requires movement={required_movement[family]}, got {movement or '<empty>'}")
    movement_owner = {
        "flail_tether": "flail",
        "yoyo_hover": "yoyo",
        "whip_lash": "whip",
    }
    if movement in movement_owner and family != movement_owner[movement]:
        defects.append(f"movement={movement} requires runtimeFamily={movement_owner[movement]}, got {family or '<empty>'}")

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

    known = set(LLM_REQUIRED_GENOME_FIELDS) | set(LLM_OPTIONAL_GENOME_DEFAULTS) | {"spreadRadians", "homingStrength", "extraUpdates", "beamWidthPx", "beamChargeTicks", "chargeTicks", "chargePowerMultiplier", "delayTicks", "sentryPlacement", "sentryAttackIntervalTicks", "sentryTargetRangeTiles", "sentryLifetimeTicks", "immunityCooldown", "useAnimationTicks", "secondaryTrigger"}
    for key, value in src.items():
        if key in known:
            genome[key] = value
    attack["enabled"] = True

def try_llm_genome_repair(data: dict[str, Any], a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], key: str, defects: list[str], attempt: int) -> dict[str, Any] | None:
    """Repair combat genome from one rich authoritative v3.1 stage dossier."""
    try:
        history_state = planner_history_state(data)
        live_planner = str((data.get("debug") or {}).get("planner") or "") == "llm_author_first"
        if history_state == "malformed" or (history_state == "absent" and live_planner):
            data.setdefault("debug", {})["genomeRepairHistoryStatus"] = (
                "malformed_fail_closed" if history_state == "malformed" else "missing_live_planner_history_fail_closed"
            )
            return None
        model_name = resolve_llm_model()
        existing = proposed_attack_genome(data)
        user = {
            "task": "Repair only missing/malformed attack.genome fields. Return JSON only.",
            "agentHandoff": agent_handoff(
                previous_speaker="item_planner",
                current_speaker="genome_validator",
                next_speaker="genome_repairer",
                cause_by="genome_validation",
                artifact_source="currentItem",
            ),
            "important": [
                "Keep name, tooltip, category, parents, and visual concept.",
                "Pick concrete mechanics now; code will not invent them.",
                "Use weapon-family fields and executable numbers, not prose tags.",
                "Strong ideas must pay through executable fields: slower useTime, finite range/lifetime, lower pierce/shotCount, or no AoE/homing.",
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
            "allowed": {
                "delivery": ["swing", "thrust", "spear", "stab", "rapier", "shortsword", "shoot", "bow", "gun", "launcher", "cast", "staff", "wand", "book", "throw", "boomerang", "summon", "minion", "sentry"],
                "movement": "straight|gravity_arc|drift|orbit|boomerang|bounce|sine_homing|phase|accelerate|spiral|returning_glaive|expanding_wave|flail_tether|yoyo_hover|whip_lash",
                "effect": "none|dust|electric|slime|star|flame|frost|leaf|shadow|poison|blood|honey|sand|lunar|heal|holy|smoke",
                "onHit": "none|burst|split|chain|burn|frostburn|poison|shadowflame|starburst|overhead_barrage|aura_pulse|spore_cloud|mini_missiles|vortex_spawn|blackhole|radial_beams|lightning_arc|heal",
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
        user["parents"] = [
            llm_parent_card(a, ca),
            llm_parent_card(b, cb),
        ]
        system = (
            "You are the Genome Repairer for this Terraria-like item generator. "
            "The latest genome_validator currentItem is the authoritative current combat truth; any earlier item_planner response is provenance only. "
            "Return JSON only and fill only missing/malformed fields with concrete executable values."
        )
        user_content = json.dumps(user, ensure_ascii=False, separators=(",", ":"))
        messages = [
            stage_chat_message("system", "genome_repair_contract", system),
            stage_chat_message("user", "genome_validator", user_content),
        ]
        message_mode = (
            "authoritative_stage_dossier_v31"
            if history_state == "valid"
            else "legacy_authoritative_stage_dossier_v31"
        )
        req = {
            "model": model_name,
            "messages": messages,
            "temperature": 0.15,
            "max_tokens": 900,
            "response_format": llm_json_response_format("infini_genome_repair"),
        }
        raw = llm_chat_json(req, timeout=16)
        content = raw["choices"][0]["message"]["content"]
        data.setdefault("debug", {})["genomeRepairMessageMode"] = message_mode
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

def _require_authored_enum(proposed: dict[str, Any], field: str, allowed: dict[str, int] | AbstractSet[str]) -> tuple[str, int | None]:
    raw = proposed.get(field)
    v = _normalize_authored_enum_value(raw, field)
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
    delivery, _ = _require_authored_enum(proposed, "delivery", DELIVERIES)
    movement, mcode = _require_authored_enum(proposed, "movement", MOVEMENT_CODE)
    effect, ecode = _require_authored_enum(proposed, "effect", EFFECT_CODE)
    onhit, hcode = _require_authored_enum(proposed, "onHit", ONHIT_CODE)

    # Required numeric fields: authored by the LLM, hard-clamped only for engine sanity.
    runtime_family = _normalize_authored_enum_value(proposed.get("runtimeFamily"), "runtimeFamily")
    if runtime_family not in RUNTIME_FAMILIES or runtime_family == "none":
        raise PlannerUnavailable("LLM planner must author a canonical executable attack.genome.runtimeFamily; craft failed and ingredients must be refunded")
    g: dict[str, Any] = {
        "runtimeFamily": runtime_family,
        "delivery": delivery,
        "movement": movement, "movementCode": int(mcode),
        "effect": effect, "effectCode": int(ecode),
        "onHit": onhit, "onHitCode": int(hcode),
    }
    for field in [
        "useTimeTicks", "shotCount", "pierce", "aoeRadiusTiles", "lifetimeTicks",
        "rangeTiles", "spreadRadians", "speed",
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

    pull_mode = _normalize_authored_enum_value(proposed.get("pullMode") or "none", "pullMode")
    if pull_mode not in {"none", "target_to_owner", "owner_to_target", "target_to_projectile"}:
        raise PlannerUnavailable(f"LLM planner returned unsupported attack.genome.pullMode={pull_mode!r}; craft failed and ingredients must be refunded")
    g["pullMode"] = pull_mode

    # Preserve only authored presentation strings. Prose/script-like behavior fields are not executable.
    for field in ["projectileShape", "projectileMotion", "projectileTrail", "projectileImpact", "secondaryProjectileShape", "secondaryMaterial", "weaponFamily", "projectileFamily", "ammoKind", "runtimeFamily", "soundUseCatalogId", "soundImpactCatalogId", "soundCatalogSource"]:
        if field in proposed and proposed.get(field) not in (None, ""):
            g[field] = str(proposed.get(field))[:260]
    if proposed.get("useAnimationTicks") not in (None, ""):
        g["useAnimationTicks"] = int(round(clamp_float(proposed.get("useAnimationTicks"), 6, 150, g.get("useTimeTicks", 24))))
    if proposed.get("beamWidthPx") not in (None, ""):
        g["beamWidthPx"] = round(clamp_float(proposed.get("beamWidthPx"), 2, 96, 14), 2)
    if proposed.get("beamChargeTicks") not in (None, ""):
        g["beamChargeTicks"] = int(round(clamp_float(proposed.get("beamChargeTicks"), 0, 300, 0)))
    if proposed.get("delayTicks") not in (None, ""):
        g["delayTicks"] = int(round(clamp_float(proposed.get("delayTicks"), 0, 300, 30)))
    if proposed.get("secondaryTrigger") not in (None, ""):
        g["secondaryTrigger"] = str(proposed.get("secondaryTrigger"))[:24]
    if proposed.get("immunityCooldown") not in (None, ""):
        g["immunityCooldown"] = int(round(clamp_float(proposed.get("immunityCooldown"), 0, 60, 0)))

    # Preserve exact compiler-owned fields through the last Python projection.
    # These values already came from typed engineCalls; replacing them with DTO
    # defaults here would silently re-author the item after validation.
    for field, lo, hi, integer in [
        ("debuffTime", 0, 600, True),
        ("secondaryDamageMultiplier", 0, 1, False),
        ("secondarySpreadRadians", 0, 1.2, False),
        ("secondaryLifetimeTicks", 5, 180, True),
        ("sameTargetBias", 0, 1, False),
        ("runtimeLightStrength", 0, 1.5, False),
        ("runtimeLightDurationTicks", 0, 240, True),
        ("vfxParticleScale", 0, 2, False),
        ("vfxParticleDurationTicks", 0, 80, True),
        ("vfxFieldLifetimeTicks", 0, 240, True),
        ("vfxFieldRadiusTiles", 0, 6, False),
        ("vfxFieldTickRate", 0, 60, True),
        ("impactVfxRadiusPx", 0, 192, True),
        ("contactForgivenessPx", 0, 32, True),
    ]:
        if proposed.get(field) not in (None, ""):
            value = clamp_float(proposed.get(field), lo, hi, lo)
            g[field] = int(round(value)) if integer else round(value, 3)
    for field in ("primaryColorName", "runtimeLightColorName", "secondaryMaterial", "vfxMaterial"):
        if proposed.get(field) not in (None, ""):
            g[field] = str(proposed.get(field))[:120]

    # Family-specific compiler output. These values already come from exact engine
    # calls and finite policies; this projection must preserve them rather than
    # silently replacing them with AttackSpec defaults.
    if runtime_family == "charge_release":
        g["chargeTicks"] = int(round(clamp_float(proposed.get("chargeTicks"), 1, 300, 45)))
        g["chargePowerMultiplier"] = round(clamp_float(proposed.get("chargePowerMultiplier"), 1, 3, 1.6), 3)
    if runtime_family == "sentry":
        placement = str(proposed.get("sentryPlacement") or "grounded").strip().lower()
        if placement not in {"grounded", "floating"}:
            raise PlannerUnavailable("sentryPlacement must be exact grounded|floating")
        g["sentryPlacement"] = placement
        g["sentryAttackIntervalTicks"] = int(round(clamp_float(proposed.get("sentryAttackIntervalTicks"), 12, 180, 45)))
        g["sentryTargetRangeTiles"] = round(clamp_float(proposed.get("sentryTargetRangeTiles"), 8, 60, 30), 3)
        g["sentryLifetimeTicks"] = int(round(clamp_float(proposed.get("sentryLifetimeTicks"), 120, 36000, 3600)))
        g["secondaryLifetimeTicks"] = int(round(clamp_float(proposed.get("secondaryLifetimeTicks"), 5, 180, 24)))

    # Compiler-owned child safety fields are not creative defaults. Preserve the
    # finite caps produced by the runtime policy after LLM authoring.
    for field in ("maxChildProjectiles", "maxChildDepth"):
        if proposed.get(field) not in (None, ""):
            g[field] = int(max(0, float(proposed.get(field))))

    for field, lo, hi, default in [
        ("soundVolume", 0.05, 1.0, 0.85),
        ("soundPitch", -0.9, 0.9, 0.0),
        ("soundPitchVariance", 0.0, 0.6, 0.18),
    ]:
        if proposed.get(field) not in (None, ""):
            g[field] = round(clamp_float(proposed.get(field), lo, hi, default), 3)

    # Runtime-family affordances are executor safety, not creative authoring. Reapply
    # them after the authored genome has been sanitized so the final AttackSpec cannot
    # lose noMelee/noUseGraphic/channel semantics at a later projection boundary.
    g.update(_runtime_family_affordances(runtime_family, g.get("weaponFamily") or "", g.get("delivery") or ""))
    g.setdefault("channelUse", False)

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
    if LLM_RUNTIME_AUTHORING and runtime_plan(data):

        genome = llm_authored_weapon_genome(data, a, b, stage)
        genome["damageClass"] = damage_class
        return genome


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
    proposed_delivery = _normalize_authored_enum_value(proposed.get("delivery"), "delivery")
    if proposed_delivery in DELIVERIES and proposed_delivery != "none":
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
    movement, mcode = safe_enum(proposed.get("movement"), MOVEMENT_CODE, movement, "movement")
    effect, ecode = safe_enum(proposed.get("effect"), EFFECT_CODE, effect, "effect")
    onhit, hcode = safe_enum(proposed.get("onHit"), ONHIT_CODE, onhit, "onHit")

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

    genome = {
        "delivery": delivery,
        "movement": movement, "movementCode": mcode,
        "effect": effect, "effectCode": ecode,
        "onHit": onhit, "onHitCode": hcode,
        "shotCount": shot_count, "spreadRadians": round(spread, 3),
        "pierce": pierce, "aoeRadiusTiles": round(aoe_tiles, 3), "homingStrength": round(homing, 3),
        "lifetimeTicks": lifetime, "extraUpdates": extra_updates, "rangeTiles": round(range_tiles, 2),
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
    hit_cadence = effective_hit_cadence_ticks(genome, use_time)
    # Convert current derived damage into a rough DPS envelope, then let the real
    # executable per-target cadence/cost buy burst. Held beams use local immunity.
    base_dps = max(4.0, base_damage * 60.0 / max(10.0, float(stage.get("useTime", 24))))
    if hit_cadence >= 60:
        # Slow damage opportunities may hit hard, but not linearly forever.
        burst_bonus = 1.0 + min(0.45, (hit_cadence - 60) / 220.0)
    else:
        burst_bonus = 1.0
    hit_damage = int(max(1.0, base_dps * hit_cadence / 60.0 * burst_bonus / cost))

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
        use_time=int(round(hit_cadence)),
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

__all__ = [
    "_normalize_authored_enum_value",
    "safe_enum",
    "proposed_attack_genome",
    "genome_defects",
    "merge_genome_repair",
    "try_llm_genome_repair",
    "repair_llm_combat_genome_if_needed",
    "_parse_required_float",
    "_hard_clamp_authored_number",
    "_require_authored_enum",
    "llm_authored_weapon_genome",
    "weapon_genome_for",
    "normalize_authored_attack_pattern",
    "weapon_numbers_from_genome",
    "attack_pattern_for",
    "_parent_tool_power",
    "_bounded_parent_potion_stats",
]
