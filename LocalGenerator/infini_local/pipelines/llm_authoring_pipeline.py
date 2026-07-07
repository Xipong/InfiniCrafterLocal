from __future__ import annotations

import base64
import copy
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

from infini_local.core.env_utils import env_bool, env_float, env_int, env_str, env_first, env_path
from urllib import request as urlrequest
from urllib import error as urlerror
from urllib.parse import urlencode



# AGENT MAP: LLM JSON authoring and targeted repair boundary.
# The model proposes structured item/runtime data; code then validates/compiles it.
# Repair prompts should be narrow and provenance-visible, not a hidden second author
# that rewrites identity or routes mechanics from prose.
def _normalized_llm_provider(configured: str) -> str:
    configured = (configured or "").strip().lower().replace("-", "_")
    if configured in {"openrouter", "or"}:
        return "openrouter"
    if configured in {"openai", "openai_compat", "api", "remote"}:
        return "openai_compat"
    if configured in {"local", "lmstudio", "lm_studio", "ollama", ""}:
        if not configured and OPENROUTER_API_KEY and OPENROUTER_MODEL and OPENROUTER_MODEL.lower() not in {"auto", "default"}:
            return "openrouter"
        return "local"
    return configured


def active_llm_provider(context: dict[str, Any] | None = None) -> str:
    if isinstance(context, dict) and context.get("provider"):
        return str(context.get("provider") or "local")
    return _normalized_llm_provider(LLM_PROVIDER or "")


def _llm_context_key(context: dict[str, Any] | None) -> str:
    ctx = context or {}
    return "|".join([
        str(ctx.get("provider") or "local"),
        str(ctx.get("base_url") or ""),
        str(ctx.get("model") or "auto"),
    ])


def _primary_llm_context() -> dict[str, Any]:
    provider = active_llm_provider()
    if provider == "openrouter":
        return {
            "provider": provider,
            "base_url": OPENROUTER_BASE_URL or "https://openrouter.ai/api/v1",
            "model": OPENROUTER_MODEL or "auto",
            "api_key": OPENROUTER_API_KEY,
            "http_referer": OPENROUTER_HTTP_REFERER,
            "app_title": OPENROUTER_APP_TITLE,
            "label": "primary",
        }
    if provider == "openai_compat":
        return {
            "provider": provider,
            "base_url": OPENAI_COMPAT_BASE_URL or env_str("OPENAI_BASE_URL", "").rstrip("/"),
            "model": OPENAI_COMPAT_MODEL or "auto",
            "api_key": OPENAI_COMPAT_API_KEY,
            "label": "primary",
        }
    return {
        "provider": "local",
        "base_url": LMSTUDIO_URL,
        "model": LMSTUDIO_MODEL or "auto",
        "api_key": "",
        "label": "primary",
    }


def _fallback_llm_context() -> dict[str, Any] | None:
    model = (LLM_FALLBACK_MODEL or "").strip()
    if not model:
        return None
    primary = _primary_llm_context()
    provider = _normalized_llm_provider(LLM_FALLBACK_PROVIDER or str(primary.get("provider") or "local"))
    ctx: dict[str, Any] = {
        "provider": provider,
        "model": model,
        "label": "fallback",
    }
    if provider == "openrouter":
        ctx["base_url"] = LLM_FALLBACK_BASE_URL or OPENROUTER_BASE_URL or "https://openrouter.ai/api/v1"
        ctx["api_key"] = LLM_FALLBACK_API_KEY or OPENROUTER_API_KEY
        ctx["http_referer"] = OPENROUTER_HTTP_REFERER
        ctx["app_title"] = OPENROUTER_APP_TITLE
    elif provider == "openai_compat":
        ctx["base_url"] = LLM_FALLBACK_BASE_URL or OPENAI_COMPAT_BASE_URL or env_str("OPENAI_BASE_URL", "").rstrip("/")
        ctx["api_key"] = LLM_FALLBACK_API_KEY or OPENAI_COMPAT_API_KEY
    else:
        ctx["provider"] = "local"
        ctx["base_url"] = LLM_FALLBACK_BASE_URL or LMSTUDIO_URL
        ctx["api_key"] = ""
    if _llm_context_key(ctx) == _llm_context_key(primary):
        return None
    return ctx


def _join_openai_compat_url(base: str, endpoint: str) -> str:
    base = (base or "").rstrip("/")
    endpoint = "/" + endpoint.strip("/")
    if not base:
        return endpoint
    if base.endswith("/v1") or base.endswith("/api/v1"):
        return base + endpoint
    return base + "/v1" + endpoint


def llm_base_url(context: dict[str, Any] | None = None) -> str:
    ctx = context or _primary_llm_context()
    return str(ctx.get("base_url") or "")


def llm_chat_completions_url(context: dict[str, Any] | None = None) -> str:
    return _join_openai_compat_url(llm_base_url(context), "/chat/completions")


def llm_models_url(context: dict[str, Any] | None = None) -> str:
    return _join_openai_compat_url(llm_base_url(context), "/models")


def llm_auth_snapshot() -> dict[str, Any]:
    """Small UI/trace diagnostic for the currently selected LLM backend.

    This is intentionally config-only; it does not call remote APIs. It makes the
    common failure mode visible: OpenRouter selected, but no API key is loaded.
    """
    primary = _primary_llm_context()
    provider = active_llm_provider(primary)
    fallback = _fallback_llm_context()
    fallback_view = None
    if fallback is not None:
        fallback_view = {
            "provider": fallback.get("provider"),
            "baseUrl": fallback.get("base_url"),
            "model": fallback.get("model"),
            "apiKeyConfigured": bool(fallback.get("api_key")) if fallback.get("provider") in {"openrouter", "openai_compat"} else None,
            "networkFailsBeforeSwitch": LLM_FALLBACK_NETWORK_FAILS,
        }
    if provider == "openrouter":
        configured = bool(primary.get("api_key"))
        return {
            "provider": provider,
            "baseUrl": primary.get("base_url") or "https://openrouter.ai/api/v1",
            "model": primary.get("model") or "auto",
            "apiKeyConfigured": configured,
            "status": "configured" if configured else "missing_api_key",
            "hint": "OK" if configured else "Set INFINI_OPENROUTER_API_KEY in config.env or choose the local LM Studio preset.",
            "fallback": fallback_view,
        }
    if provider == "openai_compat":
        configured = bool(primary.get("api_key"))
        return {
            "provider": provider,
            "baseUrl": primary.get("base_url"),
            "model": primary.get("model") or "auto",
            "apiKeyConfigured": configured,
            "status": "configured" if configured else "missing_or_optional_api_key",
            "hint": "Set INFINI_OPENAI_COMPAT_API_KEY if your compatible endpoint requires Bearer auth.",
            "fallback": fallback_view,
        }
    return {
        "provider": provider or "local",
        "baseUrl": primary.get("base_url") or LMSTUDIO_URL,
        "model": primary.get("model") or "auto",
        "apiKeyConfigured": None,
        "status": "local_endpoint_required",
        "hint": "LM Studio must be running and exposing /v1 on the configured URL.",
        "fallback": fallback_view,
    }


def ensure_llm_auth_configured(context: dict[str, Any] | None = None) -> None:
    ctx = context or _primary_llm_context()
    provider = active_llm_provider(ctx)
    if provider == "openrouter" and not ctx.get("api_key"):
        raise RuntimeError("OpenRouter API key is missing: set INFINI_OPENROUTER_API_KEY in config.env or choose the local LM Studio preset.")


def llm_headers(extra: dict[str, str] | None = None, context: dict[str, Any] | None = None) -> dict[str, str]:
    ctx = context or _primary_llm_context()
    provider = active_llm_provider(ctx)
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if provider == "openrouter":
        if ctx.get("api_key"):
            headers["Authorization"] = f"Bearer {ctx.get('api_key')}"
        if ctx.get("http_referer"):
            headers["HTTP-Referer"] = str(ctx.get("http_referer"))
        if ctx.get("app_title"):
            headers["X-OpenRouter-Title"] = str(ctx.get("app_title"))
    elif provider == "openai_compat":
        if ctx.get("api_key"):
            headers["Authorization"] = f"Bearer {ctx.get('api_key')}"
    if extra:
        headers.update(extra)
    return headers

def llm_json_response_format(name: str = "infini_json") -> dict[str, Any] | None:
    """OpenAI-compatible structured JSON hint.

    Local LM Studio usually handles json_schema well. Remote gateways/models vary, so
    INFINI_LLM_RESPONSE_FORMAT can be set to json_schema/json_object/off. In auto mode
    remote APIs use json_object and llm_chat_json retries without response_format if a
    provider rejects the field.
    """
    mode = LLM_RESPONSE_FORMAT_MODE
    if mode == "auto":
        mode = "json_schema" if active_llm_provider() == "local" else "json_object"
    if mode in {"off", "none", "0", "false", "disabled"}:
        return None
    if mode == "json_object":
        return {"type": "json_object"}
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": False,
            "schema": {"type": "object", "additionalProperties": True},
        },
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
    set_if("soundUse", pg.get("soundUse"), toy.get("soundUse"), vp.get("soundPalette"), limit=240)
    set_if("soundImpact", pg.get("soundImpact"), toy.get("soundImpact"), pg.get("impact"), vd.get("impactSound"), limit=260)
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
    cache = data.get("_runtimePlanCompileCache")
    if isinstance(cache, dict) and isinstance(cache.get("patch"), dict):
        return dict(cache.get("patch") or {})
    normalize_runtime_plan_inplace(data)
    result = compile_runtime_plan_to_genome_result(data)
    patch = result.get("patch") if isinstance(result, dict) else {}
    patch = patch if isinstance(patch, dict) else {}
    data["_runtimePlanCompileCache"] = {"patch": dict(patch), "result": result}
    debug = data.setdefault("debug", {})
    debug["runtimeApiVersion"] = ENGINE_RUNTIME_API_VERSION
    debug["runtimePlanCompiler"] = json.dumps(result.get("quality", {}), ensure_ascii=False)[:6000]
    debug["runtimePlanValidation"] = json.dumps(result.get("validation", {}), ensure_ascii=False)[:6000]
    debug["runtimePlanProvenance"] = json.dumps(result.get("provenance", {}), ensure_ascii=False)[:6000]
    data["runtimeCompiled"] = result.get("compiled", compiled_runtime_contract(data, patch))
    debug["runtimeCompiled"] = json.dumps(data.get("runtimeCompiled", {}), ensure_ascii=False)[:6000]
    if isinstance(data.get("attack"), dict):
        data["attack"]["runtimeAuthoringProvenance"] = result.get("provenance", {})
    return dict(patch)

def normalize_runtime_authoring_fields(data: dict[str, Any]) -> dict[str, Any]:
    if not LLM_RUNTIME_AUTHORING:
        return data
    normalize_runtime_plan_inplace(data)
    rp = runtime_plan(data)
    if not rp:
        if LLM_RUNTIME_PLAN_REQUIRED and combat_genome_required_for(data):
            raise PlannerUnavailable("LLM runtime authoring is enabled but runtimePlan/engineCalls is missing")
        return data
    data.setdefault("debug", {})["runtimeAuthoringMode"] = "llm_engine_calls_v0_4_25"
    validation = runtime_plan_validation_report(data)
    data.setdefault("debug", {})["runtimePlanQuality"] = json.dumps(runtime_plan_quality_report(data), ensure_ascii=False)[:6000]
    data.setdefault("debug", {})["runtimePlanValidation"] = json.dumps(validation, ensure_ascii=False)[:6000]
    if LLM_RUNTIME_STRICT_VALIDATION and not validation.get("ok", False) and combat_genome_required_for(data):
        raise PlannerUnavailable("LLM runtimePlan failed engine-call validation: " + "; ".join(validation.get("errors") or ["unknown error"]))
    patch = runtime_plan_to_attack_genome_patch(data)
    if patch:
        attack = data.setdefault("attack", {}) if isinstance(data.get("attack"), dict) else data.setdefault("attack", {})
        genome = attack.setdefault("genome", {}) if isinstance(attack.get("genome"), dict) else {}
        attack["genome"] = genome
        for k, v in patch.items():
            genome[k] = v
        data.setdefault("debug", {})["runtimePlanGenomePatch"] = json.dumps(patch, ensure_ascii=False)[:6000]
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
    affordance_fields = ["useFantasy", "heldVisibility", "releaseTiming", "handPose", "spawnStyle", "rotationMode", "initialOffsetPx", "drawDuringUse", "trailMode", "projectileSizePolicy"]
    for field in ["altUseMode", "altMobilityMode", "altMobilityRangeTiles", "altMobilityCooldownTicks", "altMobilitySafeTileOnly", "holdLightStrength", "holdLightColorName", "extractinatorOutputItemType", "extractinatorOutputStack", "itemScale", "holdoutOffsetX", "holdoutOffsetY", "autoReuse", "useTurn", "channelUse", "consumeChancePercent", "ammoFor", "useConditionMode", "useConditionMinLife", "useConditionMinMana"] + affordance_fields:
        if field in patch and patch.get(field) not in (None, ""):
            gp[field] = patch.get(field)
    authored_affordance = {field: patch.get(field) for field in ["itemScale", "holdoutOffsetX", "holdoutOffsetY", "autoReuse", "useTurn", "channelUse"] + affordance_fields if field in patch and patch.get(field) not in (None, "")}
    if authored_affordance:
        authored_affordance.setdefault("schema", "infini.runtime-affordance.v2")
        authored_affordance.setdefault("note", "Author-provided use/draw feel. It does not change damage, resultKind, or runtimeFamily by itself.")
        data["runtimeAffordance"] = authored_affordance
        data.setdefault("debug", {})["runtimeAffordance"] = json.dumps(authored_affordance, ensure_ascii=False)[:2000]
    if isinstance(patch.get("altGeneratedBuff"), dict):
        gp["altGeneratedBuff"] = patch.get("altGeneratedBuff")
    if isinstance(patch.get("holdGeneratedBuff"), dict):
        gp["holdGeneratedBuff"] = patch.get("holdGeneratedBuff")
    if isinstance(patch.get("runtimeState"), dict):
        gp["runtimeState"] = patch.get("runtimeState")
    if isinstance(patch.get("rejectedEngineCalls"), list):
        gp["rejectedEngineCalls"] = patch.get("rejectedEngineCalls")[:16]
        data.setdefault("debug", {})["rejectedEngineCalls"] = json.dumps(gp["rejectedEngineCalls"], ensure_ascii=False)[:6000]
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
    for field in ["damageClass", "damage", "useTime", "useAnimation", "maxStack", "consumable", "rarity", "value", "healLife", "healMana", "buffTime", "pickPower", "axePower", "hammerPower"]:
        val = runtime_value(data, "set_item_stats", field, None)
        if val not in (None, ""):
            gp[field] = val
    use_time_ticks = runtime_value(data, "set_item_stats", "useTimeTicks", None)
    if use_time_ticks not in (None, ""):
        gp["useTime"] = use_time_ticks
        gp.setdefault("useAnimation", use_time_ticks)
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
        attack = data.setdefault("attack", {}) if isinstance(data.get("attack"), dict) else data.setdefault("attack", {})
        for src, dst in [("projectile", "projectileImagePrompt"), ("impact", "impactImagePrompt"), ("item", "imagePrompt")]:
            if vi.get(src) and not visual.get(dst):
                visual[dst] = str(vi.get(src))
        if vi.get("vfxIntent"):
            visual["vfxIntent"] = str(vi.get("vfxIntent"))
            attack["vfxIntent"] = str(vi.get("vfxIntent"))
        if vi.get("vfxAvoid"):
            visual["vfxAvoid"] = str(vi.get("vfxAvoid"))
            attack["vfxAvoid"] = str(vi.get("vfxAvoid"))
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
        params = spec.get("params") if isinstance(spec.get("params"), dict) else {}
        card: dict[str, Any] = {
            "does": _catalog_text(spec.get("meaning")),
            "params": {str(k): _catalog_text(v) for k, v in params.items()},
        }
        if fn in {"state_meter", "triggered_action"}:
            card["runtimeStatus"] = "preserved intent; pair with concrete executable calls for immediate gameplay"
        if fn == "summon_combat_entity":
            card["safety"] = "minion/sentry/turret projectile only; boss/NPC/mob/enemy spawn calls are forbidden and rejected"
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
        "principle": "LLM authors identity, numbers and engineCalls; Python validates; C# executes finite primitives. Engine still executes only registered finite primitives.",
        "runtimeLanguage": "runtimeArchetype=optional family/feel; runtimeContract=sync/truth/mechanicClaims; unsupported is preserved intent, not hidden gameplay.",
        "plannerChecklist": [
            "Pick resultKind; playable non-material/non-furniture should start with set_item_stats.",
            "Then add one executable call: attack/effect/tool/accessory/armor/mobility/hold/alt/extractinator.",
            "Boomerang/yoyo/flail/whip/held/channel concepts may add runtimeArchetype/runtimeContract.",
            "Visual prompts/VFX never substitute gameplay; image prompts name exact role object.",
            "state_meter/triggered_action are intent unless paired with executable calls.",
            "Raw parent facts are evidence, not copy commands.",
        ],
        "inputDataPolicy": [
            "Parent cards are raw facts plus short notes; missing sections are unknown, not negative facts.",
            "Ammo candidates do not override item-owned projectiles unless your concept says so.",
            "Placeable consumable means spent when placed unless intentionally authored otherwise.",
            "Server does not pre-author materials/glow/source readings/no-magic/no-explosion claims.",
        ],
        "availableFunctions": available_functions,
        "tickGuide": concise_terraria_tick_guide_for_llm(),
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
            "Do not erase a complete weapon parent unless resultKind is ammo/material and mergeLogic explains it.",
            "Ammo: ammoFor=arrow/bullet for vanilla ammo; empty + shoot_projectile for generated darts.",
            "Dust/glow/slime/sparks need explicit engineCalls/visualIntent from raw facts.",
            "Impact VFX uses spawn_contact_particles/visual_effect_cue; burst/AoE is gameplay.",
            "Prefer family functions; shoot_projectile is low-level and needs runtimeFamily.",
            "Tooltip utility needs matching engineCalls/item/tool/buff fields.",
            "Promises (return/channel/charge/phase/starfall/sticky/heat/jam/lifesteal/paired/bounce) need mechanicClaims backing=engineCall/runtimeArchetype/visual_only/unsupported.",
            "Unsupported mechanics need honest tooltip + unsupportedPromises; channel beam/paired dual stay preserved.",
            "Generic oreSense radius is debug-only. Ore visual execution is not added in this patch; no fake spelunker visuals.",
            "Boss/NPC/mob/enemy spawning is hard-rejected; only bounded minion/sentry/turret/light_pet projectiles are in scope.",
            "state_meter/triggered_action preserve intent; they are not hidden gameplay routers.",
            "For promised mechanics, add mechanicClaims with backing=engineCall/runtimeArchetype/visual_only/unsupported and a supported engineCall when possible.",
            "Falling-star rain: apply_on_hit_effect onHit=starfall count=N; add child/projectile prompts for falling star bodies.",
        ],
        "validatorLimits": {
            "validatorOnly": True,
            "balanceAuthority": "python_post_authoring_soft_envelope",
            "note": "Prompt exposes hard engine limits only; parent-relative damage/DPS balance is applied after LLM authoring.",
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
    """Preserve authored damage unless it is outside a broad safety envelope.

    This is deliberately not a DPS optimizer. `weapon_numbers_from_genome` is only the
    fallback when the model omitted/garbled damage. If the LLM authored a plausible value,
    keep it, even if the reference economy would have picked another number.
    """
    stage_damage = int(stage.get("derivedDamage") or max_parent_damage or fallback or 4)
    power = max(0.5, float(stage.get("powerBudget") or 1.0))
    hard_cap = int(max(8, stage_damage * 2.60 + 10, max_parent_damage * 3.0 + 18, 14 + power * 35.0))
    parent_depths = stage.get("parentGeneratedDepths") if isinstance(stage, dict) else []
    try:
        recursive_depth = max(int(float(x or 0)) for x in (parent_depths or [0]))
    except Exception:
        recursive_depth = 0
    if recursive_depth > 0 and 0 < max_parent_damage <= 60:
        recursive_cap = max(12, max_parent_damage + 6, int(max_parent_damage * (1.30 + min(0.18, recursive_depth * 0.05)) + 8), stage_damage + 8)
        hard_cap = min(hard_cap, recursive_cap)
        debug["recursiveDamageSoftCap"] = {"parentDepth": recursive_depth, "cap": int(hard_cap), "reason": "generated-parent recursion should add behavior/tradeoff, not staircase raw damage"}
    # This final absolute guard is only for broken JSON / absurd API output, not balance.
    hard_cap = min(999, hard_cap)
    raw = src.get("damage") if isinstance(src, dict) else None
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
        try:
            cost = float(genome.get("costMultiplier") or behavior_cost_multiplier(genome))
        except (TypeError, ValueError, OverflowError):
            cost = 1.0
        bounded = clamp_vanilla_like_weapon_damage(
            authored,
            max_parent_damage,
            stage,
            use_time=use_time,
            shot_count=shot_count,
            cost_multiplier=cost,
            raise_floor=False,
        )
        if bounded != authored:
            debug["authoredDamageEnvelopeClamp"] = {
                "from": authored,
                "to": bounded,
                "reason": "code_owned_stage_dps_envelope",
                "useTime": use_time,
                "shotCount": shot_count,
                "costMultiplier": round(cost, 3),
                "referenceNumbersDamage": int(fallback),
            }
        else:
            debug["damageSource"] = "llm_authored_preserved"
        debug["referenceNumbersDamage"] = int(fallback)
        debug["authoredDamageHardCap"] = hard_cap
        return max(1, int(round(bounded)))
    except Exception:
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
        "creativeVariance": {
            "recipeSalt": stable_hash(key, name_of(a), name_of(b), length=8),
            "designLane": choose_from([
                "clean metamorphosis with one crisp tradeoff",
                "altered delivery or timing rather than raw damage gain",
                "on-hit utility with modest direct damage",
                "contact/timing interaction if the parents support it",
                "ammo/projectile reinterpretation with a clear cost",
                "short burst window with recovery or lower uptime",
                "visual-material fusion with conservative stats",
                "support/control twist rather than another straight damage stick"
            ], "creative_lane", key, name_of(a), name_of(b)),
            "rule": "Variety nudge only, not a category router. Avoid cloning the strongest generated parent's name/runtimeFamily/onHit unless intentional."
        },
        "balancePolicy": "LLM authors numbers; prompt has hard engine ranges only; Python applies post-authoring soft clamps; C# is final safety.",
        "engineRuntimeContract": engine_runtime_capability_contract_for_llm(a, b) if LLM_RUNTIME_AUTHORING else {},
        "rawParentSchema": {"mode": LLM_RAW_TOKEN_MODE, "sections": "item/directProjectile/effectiveProjectile/ammo/runtimeProbe/generatedParent + optional semantics notes", "rule": "raw fields are facts; semantics notes only clarify overloaded Terraria flags; absence is unknown, not a negative fact", "ammoRepresentativeLimit": 0},
        "authorRules": [
            "Author concept, resultKind, numbers, runtimePlan.engineCalls, and concise visual prompts.",
            "Use exact fn names from engineRuntimeContract.availableFunctions; prefer family calls over low-level shoot_projectile.",
            "Playable non-material/non-furniture: set_item_stats first, then at least one executable gameplay call.",
            "Secondary projectiles support trigger=on_hit only.",
            "Output: projectile weapon => weapon; generated darts/throwables => ammo + ammoFor empty + shoot_projectile; true bow/gun ammo => arrow/bullet.",
            "DamageClass: melee may emit projectiles; pure free-flight physical attacks are usually ranged/generic.",
            "Raw cards are facts, not instructions; placeable consumable means spent when placed unless authored otherwise.",
            "Do not claim no-magic/no-light/no-explosion/no-children unless raw fields say it; missing data is not a fact.",
            "Server rejects unsupported calls and catastrophic runtime/network/FPS values only.",
            "Secondary projectiles/trails/glow/sparks/motes/marks/tethers should be central and explicit.",
            "Generated parents: preserve one anchor, then add bounded tradeoff/timing/delivery/utility when it fits.",
            "Tethered/returning/harpoon sprites: moving body + optional short local attachment, not full-canvas rope/chain.",
            "Teleport/recall/mining/sensing/light/alt/hold utility: use a mobility engineCall, tool_capability, apply_player_effect_on_use, emit_light or hold_item_effect; otherwise VFX only.",
            "movement=phase is projectile travel, not player movement; use a mobility engineCall for player movement.",
            "Never author summon_boss/summon_npc/summon_mob/spawn_npc/spawn_enemy; only bounded minion/sentry/turret/pet_attack/light_pet summons are in scope.",
            "state_meter/triggered_action preserve charge/heat/mode intent; gameplay still needs executable calls.",
            "Use runtimeArchetype/runtimeContract for behavior/control/sync/promise truth; no hidden gameplay router.",
            "Unsupported promised mechanics: mark mechanicClaims unsupported/visual_only and keep tooltip honest.",
            "Image prompts: item=inventory/held; projectile=moving hit-object (same sword/blade/boomerang OK if it is hit body); impact=momentary hit; child=damaging child/mote.",
            "Return one JSON object. No markdown, analysis, legacy attackPattern, or attack.genome.",
        ],
        "validatorRanges": {
            "damage": [0, 999],
            "useTimeTicks": [10, 150], "shotCount": [1, 8], "pierce": [-1, 10],
            "rangeTiles": [4, 120], "lifetimeTicks": [25, 900], "extraUpdates": [0, 3],
            "note": "Schema/engine sanity ranges only. Parent-relative balance is applied after authoring; no legacy attack.genome."
        },
        "itemA": raw_parent_card_for_llm(a),
        "itemB": raw_parent_card_for_llm(b),
        "requiredJsonShape": {
            "name": "short flavorful item name, no Infini/Generated/Hybrid/Combined",
            "tooltip": "short in-game tooltip",
            "concept": {
                "fantasy": "one sentence describing the item",
                "mergeLogic": "one sentence: why these exact parents became this, based on raw parent fields",
                "weirdTwist": "one sentence: memorable non-vanilla behavior or clean metamorphosis"
            },
            "runtimeArchetype": "optional {schema:'infini.runtime-archetype.v1', source, family, phaseModel, overrideKnobs, supportStatus}; unknown knobs inert/preserved",
            "runtimeContract": "optional {schema:'infini.runtime-contract.v1', primaryVerb, controlStyle, stateFields, syncFields, mechanicClaims:[{claim,backing,status}], unsupportedPromises, executionStatus}",
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
    }

def planner_prompt_usability_report(a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], key: str) -> dict[str, Any]:
    payload = build_llm_author_payload(a, b, ca, cb, key)
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    contract = payload.get("engineRuntimeContract") if isinstance(payload.get("engineRuntimeContract"), dict) else {}
    functions = contract.get("availableFunctions") if isinstance(contract.get("availableFunctions"), dict) else {}
    return {
        "ok": len(text) <= 23000 and bool(functions) and "requiredJsonShape" in payload,
        "chars": len(text),
        "approxTokens": max(1, len(text) // 4),
        "contractStyle": contract.get("contractStyle"),
        "functionCount": len(functions),
        "hasRequiredShape": "requiredJsonShape" in payload,
        "hasRuntimePlanShape": isinstance(payload.get("requiredJsonShape", {}).get("runtimePlan"), dict),
        "hasNoBossRule": "boss" in json.dumps(payload, ensure_ascii=False).lower(),
        "note": "Prompt-only readiness check; does not call the LLM.",
    }

def try_llm_plan(a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], key: str) -> dict[str, Any] | None:
    """Author-first chaos planner.

    v0.3.9 keeps the author-first architecture. The LLM authors the playable item: fantasy,
    category, gameplay numbers, projectile identity, behavior timeline, and visual briefs.
    Python does not choose the item. It only validates JSON, fills trivial serialization
    fields, then clamps catastrophic power/performance after the fact.
    """
    if not USE_LLM:
        return None
    user = build_llm_author_payload(a, b, ca, cb, key)
    try:
        model_name = resolve_llm_model()
        system = (
            "You are the AUTHOR of a Terraria-like generated item. "
            "Use raw parent fields, semantic notes, and engine functions to design one playable result. "
            "Follow the priorityHeader before the detailed API card. "
            "The server validates executable safety only; do not rely on legacy attackPattern/attack.genome. "
            "Return ONLY one JSON object. No reasoning, no markdown, no second JSON."
            + llm_reasoning_system_suffix(model_name)
        )
        planner_user_content = json.dumps(user, ensure_ascii=False, separators=(",", ":"))
        req = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": planner_user_content},
            ],
            "temperature": _env_float("INFINI_LLM_TEMPERATURE", 0.38, 0.0, 1.2),
            "response_format": llm_json_response_format("infini_runtime_plan"),
        }
        req = apply_llm_common_options(req, model_name=model_name)
        trace_event("prompt", "LLM:author_plan", f"Planner request: {name_of(a)} + {name_of(b)}", {
            "provider": active_llm_provider(), "model": model_name, "temperature": req.get("temperature"),
            "maxTokens": req.get("max_tokens"), "reasoning": req.get("reasoning"),
            "responseFormat": bool(req.get("response_format")), "messages": _trace_message_summary(req.get("messages")),
        }, prompt=planner_user_content)
        raw = llm_chat_json(req, timeout=env_int("INFINI_LLM_TIMEOUT", 95))
        content = raw["choices"][0]["message"]["content"]
        trace_event("response", "LLM:author_plan", "Planner response", {"provider": active_llm_provider(), "model": model_name, "chars": len(str(content))}, response=content)
        parsed_child_json = parse_first_valid_llm_json(content)
        obj = normalize_behavior_toy_fields(normalize_llm_attack_shape(parsed_child_json))
        obj.setdefault("id", "g_" + stable_hash(key, content, length=16))
        obj.setdefault("recipeKey", key)
        obj.setdefault("schemaVersion", 1)
        obj.setdefault("parentA", name_of(a))
        obj.setdefault("parentB", name_of(b))
        obj.setdefault("sourceMode", "generated")
        obj.setdefault("debug", {})
        obj["debug"]["planner"] = "llm_author_first"
        obj["debug"]["model"] = model_name
        obj["debug"]["promptMode"] = "runtime_authoring_family_contract_v0.4.30_priority_header_placeable_semantics_v0.4.172"
        obj["debug"]["balanceAuthority"] = "llm_authors_numbers_python_clamps_after_authoring"
        obj["debug"]["llmRawOutput"] = content[:12000]
        obj["debug"]["llmTopLevelKeys"] = ",".join(sorted(str(k) for k in obj.keys()))
        obj["debug"]["llmContinuationStored"] = "planner_chat_v1"
        # Runtime/debug-only continuation context for the optional VFX Director.
        # OpenAI-compatible APIs are stateless, so the VFX pass must resend the
        # original planner turn explicitly when it wants to feel like a continuation.
        obj["_llmContinuation"] = {
            "kind": "planner_chat_v1",
            "plannerSystemPrompt": system,
            "plannerUserPayload": user,
            "plannerUserContent": planner_user_content,
            "plannerAssistantContent": content,
            "plannerParsedChildJson": parsed_child_json,
        }
        return obj
    except Exception as e:
        trace_event("error", "LLM:author_plan", "Planner failed", {"parents": [name_of(a), name_of(b)]}, error=repr(e))
        log_event("warn", "LLM author-first planner failed", {"error": repr(e)})
        return None


def _runtime_plan_repair_current_item_view(data: dict[str, Any]) -> dict[str, Any]:
    """Small, serializable view for a runtimePlan repair turn.

    Keep the model focused on authored gameplay/visual identity. Huge debug blobs and
    continuation transcripts are deliberately excluded so the repair request stays cheap
    and does not drown the missing schema error.
    """
    view: dict[str, Any] = {}
    for key in ["name", "tooltip", "concept", "category", "gameplay", "runtimePlan", "visual", "tags"]:
        value = data.get(key)
        if value not in (None, ""):
            view[key] = value
    return view


REPAIR_PATCH_ALLOWED_TOP_LEVEL = {
    "runtimePlan",
    "attack",
    "gameplay",
}

# Even inside a gameplay repair patch, keep this surface narrow.  Runtime repair may
# complete executable stats, utility flags and authored runtime affordances, but it must
# not silently re-author identity/prose/visuals or become a second item author.
REPAIR_PATCH_ALLOWED_GAMEPLAY_FIELDS = {
    "kind", "damageClass", "damage", "useTime", "useAnimation", "useStyle", "autoReuse", "useTurn",
    "maxStack", "consumable", "craftYield", "rarity", "value", "manaCost", "knockback",
    "healLife", "healMana", "buffCode", "buffType", "buffTime", "extraBuffs", "generatedBuff",
    "pickPower", "axePower", "hammerPower", "miningSpeedScale", "mobilityMode", "mobilityRangeTiles",
    "mobilityCooldownTicks", "mobilitySafeTileOnly", "altUseMode", "altMobilityMode",
    "altMobilityRangeTiles", "altMobilityCooldownTicks", "altMobilitySafeTileOnly", "altGeneratedBuff",
    "holdGeneratedBuff", "holdLightStrength", "holdLightColorName", "runtimeState", "ammoFor",
    "consumeChancePercent", "useConditionMode", "useConditionMinLife", "useConditionMinMana",
    "extractinatorOutputItemType", "extractinatorOutputStack", "itemScale", "holdoutOffsetX", "holdoutOffsetY",
    "channelUse", "runtimeOutputKind", "actualAmmoMode",
}


def _repair_patch_payload(repaired: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Return the explicit patch payload and how it was found.

    Repair responses may be either {"repairPatch": {...}}, {"patch": {...}} or an older
    full item JSON.  The caller will reduce full JSON to the same narrow patch surface.
    """
    for key in ("repairPatch", "patch", "runtimePatch"):
        if isinstance(repaired.get(key), dict):
            return copy.deepcopy(repaired[key]), key
    return copy.deepcopy(repaired), "full_json_reduced_to_patch"


def _filtered_runtime_repair_patch(repaired: dict[str, Any], original: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Extract a narrow runtime repair patch from an LLM response.

    This is the anti-chaos boundary: targeted repair may fix executable runtime fields,
    but it is not allowed to become a second free-form item author.  Unknown/full-item
    fields are ignored and recorded for debug.
    """
    payload, source = _repair_patch_payload(repaired)
    payload = normalize_llm_attack_shape(payload) if isinstance(payload, dict) else {}
    if not isinstance(payload, dict):
        payload = {}
    accepted: dict[str, Any] = {}
    rejected: list[str] = []
    for key, value in payload.items():
        if key == "debug":
            continue
        if key == "runtimePlan" and isinstance(value, dict):
            accepted[key] = copy.deepcopy(value)
            continue
        if key == "attack" and isinstance(value, dict):
            accepted[key] = copy.deepcopy(value)
            continue
        if key == "gameplay" and isinstance(value, dict):
            if source == "full_json_reduced_to_patch":
                rejected.append("gameplay")
                continue
            filtered = {str(k): copy.deepcopy(v) for k, v in value.items() if str(k) in REPAIR_PATCH_ALLOWED_GAMEPLAY_FIELDS}
            dropped = sorted(str(k) for k in value.keys() if str(k) not in REPAIR_PATCH_ALLOWED_GAMEPLAY_FIELDS)
            if filtered:
                accepted[key] = filtered
            rejected.extend(f"gameplay.{k}" for k in dropped[:32])
            continue
        if key in {"accessory", "armor"} and isinstance(value, dict) and isinstance(original.get(key), dict):
            # Only allow targeted completion of an already-authored accessory/armor surface.
            # Repair must not flip a weapon into armor/accessory by returning a full rewrite.
            accepted[key] = copy.deepcopy(value)
            continue
        if key == "category" and not str(original.get("category") or "").strip() and value not in (None, ""):
            accepted[key] = value
            continue
        rejected.append(str(key))
    report = {
        "schema": "infini.runtime-repair-patch-contract.v1",
        "source": source,
        "acceptedTopLevel": sorted(accepted.keys()),
        "rejectedTopLevel": sorted(set(rejected))[:48],
        "note": "Targeted repair is reduced to executable patch fields; identity/prose/visual/full rewrites are ignored.",
    }
    return accepted, report


def _merge_repair_patch_into_candidate(candidate: dict[str, Any], patch: dict[str, Any]) -> None:
    if isinstance(patch.get("runtimePlan"), dict):
        # Replacing runtimePlan is intentional: executable repair is allowed to replace
        # bad engineCalls with a valid authored runtime contract.
        candidate["runtimePlan"] = copy.deepcopy(patch["runtimePlan"])
        candidate.pop("_runtimePlanCompileCache", None)
    for key in ("attack", "gameplay", "accessory", "armor"):
        if isinstance(patch.get(key), dict):
            base = candidate.get(key) if isinstance(candidate.get(key), dict) else {}
            merged = copy.deepcopy(base)
            merged.update(copy.deepcopy(patch[key]))
            candidate[key] = merged
    if patch.get("category") not in (None, "") and not str(candidate.get("category") or "").strip():
        candidate["category"] = str(patch.get("category"))


def _adopt_runtime_plan_repair(data: dict[str, Any], repaired: dict[str, Any], *, key: str, content_preview: str = "") -> dict[str, Any]:
    """Adopt only the executable repair patch while preserving item identity.

    The repair LLM is a contract fixer, not a second item author.  If it returns a full
    item JSON, we reduce it to the same narrow runtime/gameplay/attack patch surface and
    record rejected fields in debug.
    """
    if not isinstance(repaired, dict):
        return data
    repaired = copy.deepcopy(repaired)
    repaired_debug = repaired.get("debug") if isinstance(repaired.get("debug"), dict) else {}
    patch, patch_report = _filtered_runtime_repair_patch(repaired, data)
    candidate = copy.deepcopy(data)
    original_debug = dict(candidate.get("debug") or {})
    protected = {
        "id": candidate.get("id") or ("g_" + stable_hash(key, candidate.get("name", ""), length=16)),
        "recipeKey": candidate.get("recipeKey") or key,
        "schemaVersion": candidate.get("schemaVersion") or 1,
        "parentA": candidate.get("parentA"),
        "parentB": candidate.get("parentB"),
        "sourceMode": candidate.get("sourceMode") or "generated",
        "_llmContinuation": candidate.get("_llmContinuation"),
        "itemKnowledge": candidate.get("itemKnowledge"),
        "recipeMeta": candidate.get("recipeMeta"),
        "inheritance": candidate.get("inheritance"),
        "sourceRepresentation": candidate.get("sourceRepresentation"),
        "name": candidate.get("name"),
        "tooltip": candidate.get("tooltip"),
        "concept": candidate.get("concept"),
        "visual": candidate.get("visual"),
        "tags": candidate.get("tags"),
        "category": candidate.get("category"),
    }
    _merge_repair_patch_into_candidate(candidate, patch)
    for k, v in protected.items():
        if v not in (None, ""):
            candidate[k] = v
    merged_debug = dict(original_debug)
    # Keep repair model/attempt metadata, but never let repair debug erase prior debug.
    for k, v in repaired_debug.items():
        merged_debug.setdefault(str(k), v)
    merged_debug["runtimePlanRepairPatchContract"] = json.dumps(patch_report, ensure_ascii=False)[:4000]
    if content_preview:
        merged_debug["runtimePlanRepairRawOutput"] = content_preview[:4000]
    candidate["debug"] = merged_debug
    return candidate


def try_llm_runtime_plan_repair(data: dict[str, Any], a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], key: str, validation: dict[str, Any], attempt: int) -> dict[str, Any] | None:
    """Ask the same planner to repair the runtimePlan contract, not just one field.

    This is the runtime-authoring successor to the old attack.genome repair loop: the
    model is allowed to return a corrected full item JSON, replace bad engineCalls, add
    missing set_item_stats, restore a missing primary action, or remove unsupported calls.
    Python does not choose the gameplay; it only revalidates the returned contract.
    """
    if not USE_LLM:
        return None
    try:
        model_name = resolve_llm_model()
        author_payload = build_llm_author_payload(a, b, ca, cb, key)
        user = {
            "task": "Repair the executable runtime contract so runtimePlan.engineCalls validates. Return a patch object if possible: {repairPatch:{runtimePlan:{...}, attack:{...}, gameplay:{...}}}. Full item JSON is tolerated, but code will reduce it to the same narrow patch surface and ignore identity/prose/visual rewrites.",
            "repairMode": "targeted_runtime_contract_repair",
            "attempt": attempt,
            "validationReport": validation,
            "mustFix": [
                "If resultKind/category is weapon, ammo, consumable_weapon, tool, accessory or potion, include set_item_stats with safe base item stats.",
                "If it is combat-capable, keep or add one concrete primary executable action such as perform_melee_attack, shoot_projectile, fire_ranged_weapon, cast_magic_weapon, summon_combat_entity, or a valid utility/tool/accessory call.",
                "You may replace the whole runtimePlan if that is cleaner, but return it inside repairPatch whenever possible.",
                "Do not use legacy attackPattern or attack.genome. Do not add boss/NPC/mob/enemy spawning.",
                "Do not change name, tooltip, concept, visual identity, parents, id, recipeKey, category, or tags. Runtime repair is not a second item author.",
                "Return JSON only: no markdown, no explanation, no second object."
            ],
            "currentItem": _runtime_plan_repair_current_item_view(data),
            "parents": [raw_parent_card_for_llm(a), raw_parent_card_for_llm(b)],
            "engineRuntimeContract": author_payload.get("engineRuntimeContract"),
            "requiredJsonShape": author_payload.get("requiredJsonShape"),
        }
        cont = data.get("_llmContinuation") if isinstance(data.get("_llmContinuation"), dict) else {}
        repair_user_content = json.dumps(user, ensure_ascii=False, separators=(",", ":"))
        messages: list[dict[str, str]] = []
        if cont.get("plannerSystemPrompt") and cont.get("plannerUserContent") and cont.get("plannerAssistantContent"):
            messages = [
                {"role": "system", "content": str(cont.get("plannerSystemPrompt") or "")},
                {"role": "user", "content": str(cont.get("plannerUserContent") or "")},
                {"role": "assistant", "content": str(cont.get("plannerAssistantContent") or "")},
                {"role": "user", "content": repair_user_content},
            ]
        else:
            messages = [
                {"role": "system", "content": (
                    "You are the same Terraria-like item author repairing your previous JSON. "
                    "Fix runtimePlan.engineCalls strongly while preserving the item concept. "
                    "Return only one JSON object."
                    + llm_reasoning_system_suffix(model_name)
                )},
                {"role": "user", "content": repair_user_content},
            ]
        req = {
            "model": model_name,
            "messages": messages,
            "temperature": 0.12,
            "response_format": llm_json_response_format("infini_runtime_plan_repair"),
        }
        req = apply_llm_common_options(req, model_name=model_name, default_max_tokens=min(5000, llm_answer_max_tokens(2400)))
        trace_event("prompt", "LLM:runtime_plan_repair", f"Runtime plan repair attempt {attempt}: {name_of(a)} + {name_of(b)}", {
            "provider": active_llm_provider(), "model": model_name, "temperature": req.get("temperature"),
            "maxTokens": req.get("max_tokens"), "reasoning": req.get("reasoning"),
            "messages": _trace_message_summary(req.get("messages")), "errors": validation.get("errors"),
        }, prompt=repair_user_content)
        raw = llm_chat_json(req, timeout=max(18, env_int("INFINI_LLM_REPAIR_TIMEOUT", env_int("INFINI_LLM_TIMEOUT", 95, lo=1, hi=3600), lo=1, hi=3600) // 2))
        content = raw["choices"][0]["message"]["content"]
        trace_event("response", "LLM:runtime_plan_repair", "Runtime plan repair response", {"model": model_name, "chars": len(str(content)), "attempt": attempt}, response=content)
        obj = parse_first_valid_llm_json(content)
        if isinstance(obj, dict):
            obj.setdefault("debug", {})
            if isinstance(obj.get("debug"), dict):
                obj["debug"]["runtimePlanRepairModel"] = model_name
                obj["debug"]["runtimePlanRepairAttempt"] = attempt
                obj["debug"]["runtimePlanRepairSource"] = "llm_same_planner_continuation" if cont else "llm_same_planner_standalone"
                obj["debug"]["runtimePlanRepairPreviousErrors"] = json.dumps(validation.get("errors") or [], ensure_ascii=False)
                obj["debug"]["runtimePlanRepairRawPreview"] = str(content)[:2000]
            return obj
    except Exception as e:
        trace_event("error", "LLM:runtime_plan_repair", "Runtime plan repair failed", {"attempt": attempt, "parents": [name_of(a), name_of(b)]}, error=repr(e))
        log_event("warn", "LLM runtimePlan repair failed", {"error": repr(e), "attempt": attempt})
    return None


def _runtime_repair_kind(validation: dict[str, Any], data: dict[str, Any]) -> str:
    errors = [str(e).lower() for e in (validation.get("errors") or [])]
    if not errors:
        return "none"
    if any("missing runtimeplan" in e for e in errors):
        return "dead_missing_runtime_plan_retry_once"
    if any("no accepted executable calls" in e for e in errors):
        return "structural_or_dead_no_executable_calls"
    if any("lacks set_item_stats" in e for e in errors):
        return "executable_missing_stats"
    if any("lacks a primary executable action" in e or "did not compile" in e or "runtimefamily" in e for e in errors):
        return "executable_targeted_retry"
    return "contract_retry"


def _runtime_repair_attempt_budget(repair_kind: str) -> int:
    # Full dead/missing-runtime cases get one classic retry: if the model returns
    # another corpse, fail + debug/refund. More precise executable repairs may get
    # the existing two-turn budget.
    if repair_kind == "dead_missing_runtime_plan_retry_once":
        return 1
    return 2


def repair_runtime_plan_if_needed(data: dict[str, Any], a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], key: str) -> dict[str, Any]:
    """Repair boundary for LLM runtime authoring before C# sees the item.

    Contract:
    - crooked shape with concrete authored data is repaired by code only;
    - formally valid but non-executable runtime is sent to a targeted LLM retry;
    - totally missing/dead runtime gets one classic retry, then fail/debug/refund;
    - C# remains hard safety only, not the repair layer.
    """
    if not LLM_RUNTIME_AUTHORING:
        return data
    debug = data.setdefault("debug", {})
    had_runtime_input = any(isinstance(data.get(k), dict) and bool(data.get(k)) for k in ("runtimePlan", "enginePlan", "runtimeAuthoring", "engineRuntimePlan", "runtime_plan", "runtime"))

    structural = structural_repair_runtime_plan_inplace(data)
    if structural.get("applied"):
        debug["runtimeStructuralRepair"] = json.dumps(structural, ensure_ascii=False)[:6000]
    normalize_runtime_plan_inplace(data)
    validation = runtime_plan_validation_report(data)
    debug["runtimePlanValidationBeforeRepair"] = json.dumps(validation, ensure_ascii=False)[:6000]
    if structural.get("applied") and validation.get("ok"):
        debug["runtimeRepairPath"] = "code_structural_repair_only"
        debug["runtimePlanValidationAfterRepair"] = json.dumps(validation, ensure_ascii=False)[:6000]
        return data

    needs_repair = not bool(validation.get("ok")) and (combat_genome_required_for(data) or bool(runtime_plan(data)))
    if not needs_repair:
        debug.setdefault("runtimeRepairPath", "not_needed")
        return data

    repair_kind = _runtime_repair_kind(validation, data)
    if not had_runtime_input and repair_kind == "structural_or_dead_no_executable_calls":
        repair_kind = "dead_missing_runtime_plan_retry_once"
    attempt_budget = _runtime_repair_attempt_budget(repair_kind)
    debug["runtimeRepairKind"] = repair_kind
    debug["runtimeRepairAttemptBudget"] = str(attempt_budget)

    repair_log: list[dict[str, Any]] = []
    working = data
    for attempt in range(1, attempt_budget + 1):
        patch = try_llm_runtime_plan_repair(working, a, b, ca, cb, key, validation, attempt)
        row = {
            "attempt": attempt,
            "repairKind": repair_kind,
            "errors": validation.get("errors") or [],
            "gotPatch": bool(patch),
        }
        if not patch:
            repair_log.append(row)
            continue
        candidate = _adopt_runtime_plan_repair(working, patch, key=key, content_preview=str((patch.get("debug") or {}).get("runtimePlanRepairRawPreview") or ""))
        structural_after = structural_repair_runtime_plan_inplace(candidate)
        if structural_after.get("applied"):
            row["structuralAfterPatch"] = structural_after.get("fixes", [])[:12]
        normalize_runtime_plan_inplace(candidate)
        after = runtime_plan_validation_report(candidate)
        row["okAfter"] = bool(after.get("ok"))
        row["errorsAfter"] = after.get("errors") or []
        repair_log.append(row)
        working = candidate
        validation = after
        if after.get("ok"):
            working.setdefault("debug", {})["runtimeRepairPath"] = "llm_targeted_runtime_contract_repair"
            working["debug"]["runtimeRepairKind"] = repair_kind
            working["debug"]["runtimePlanRepair"] = json.dumps(repair_log, ensure_ascii=False)[:6000]
            working["debug"]["runtimePlanValidationAfterRepair"] = json.dumps(after, ensure_ascii=False)[:6000]
            return working
    working.setdefault("debug", {})["runtimeRepairPath"] = "targeted_runtime_repair_failed_then_strict_validation"
    working["debug"]["runtimeRepairKind"] = repair_kind
    working["debug"]["runtimePlanRepair"] = json.dumps(repair_log, ensure_ascii=False)[:6000]
    working["debug"]["runtimePlanValidationAfterRepair"] = json.dumps(validation, ensure_ascii=False)[:6000]
    return working

def call_llm_vfx_director(system: str, user: dict[str, Any], max_tokens: int, temperature: float, timeout: int, messages: list[dict[str, str]] | None = None) -> dict[str, Any] | None:
    """Small adapter used by vfx_manifest.py.

    Keeps the VFX module from creating a new LLM backend or importing server.py.
    When messages is supplied, the caller already built the complete stateless
    chat history (planner system/user/assistant + VFX continuation instruction).
    """
    if not USE_LLM:
        return None
    try:
        model_name = resolve_llm_model()
        if messages is not None:
            req_messages = [
                {"role": str(m.get("role") or "user"), "content": str(m.get("content") or "")}
                for m in messages
                if isinstance(m, dict) and str(m.get("content") or "").strip()
            ]
            if not req_messages:
                return None
        else:
            req_messages = [
                {"role": "system", "content": system + llm_reasoning_system_suffix(model_name)},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False, separators=(",", ":"))},
            ]
        req = {
            "model": model_name,
            "messages": req_messages,
            "temperature": float(temperature),
            "response_format": llm_json_response_format("infini_vfx"),
        }
        req = apply_llm_common_options(req, model_name=model_name, default_max_tokens=int(max_tokens))
        trace_event("prompt", "LLM:vfx_director", "VFX director request", {
            "provider": active_llm_provider(), "model": model_name, "temperature": req.get("temperature"),
            "maxTokens": req.get("max_tokens"), "reasoning": req.get("reasoning"),
            "messageMode": "continuation" if messages is not None else "standalone", "messages": _trace_message_summary(req.get("messages")),
        }, prompt=req_messages)
        raw = llm_chat_json(req, timeout=int(timeout))
        content = raw["choices"][0]["message"]["content"]
        trace_event("response", "LLM:vfx_director", "VFX director response", {"model": model_name, "chars": len(str(content))}, response=content)
        obj = parse_first_valid_llm_json(content)
        obj.setdefault("_debug", {})
        if isinstance(obj.get("_debug"), dict):
            obj["_debug"]["model"] = model_name
            obj["_debug"]["rawPreview"] = content[:2000]
            obj["_debug"]["messageMode"] = "continuation" if messages is not None else "standalone"
            obj["_debug"]["messageCount"] = len(req_messages)
        return obj
    except Exception as e:
        trace_event("error", "LLM:vfx_director", "VFX director failed", error=repr(e))
        log_event("warn", "LLM VFX director failed", {"error": repr(e)})
        return None

def llm_answer_max_tokens(default: int | None = None) -> int:
    raw = LLM_MAX_TOKENS if default is None else default
    try:
        value = int(raw)
    except Exception:
        value = 9000
    return max(512, min(64000, value))

def visual_director_max_tokens() -> int:
    """Token budget for the visual-director LLM step.

    If INFINI_VISUAL_DIRECTOR_MAX_TOKENS is blank/unset, inherit the global
    INFINI_LLM_MAX_TOKENS so the main GUI setting also affects the Z-Image
    prompt-authoring hop.
    """
    raw = env_str("INFINI_VISUAL_DIRECTOR_MAX_TOKENS", "")
    if not raw:
        return llm_answer_max_tokens()
    try:
        value = int(raw)
    except Exception:
        return llm_answer_max_tokens()
    return max(512, min(64000, value))

def llm_reasoning_payload(model_name: str = "") -> dict[str, Any] | None:
    """Return OpenRouter/OpenAI-compatible reasoning controls, or None.

    OpenRouter normalizes reasoning through `reasoning`: effort/max_tokens/enabled/exclude.
    Local LM Studio/Ollama-compatible servers often reject this field, so local reasoning is
    handled by system-prompt hinting instead.
    """
    mode = (LLM_REASONING_MODE or "off").strip().lower().replace("-", "_")
    if mode in {"", "off", "false", "0", "disabled", "disable"}:
        return None
    provider = active_llm_provider()
    if provider == "local":
        return None
    exclude = bool(LLM_REASONING_EXCLUDE)
    if mode in {"auto", "default", "enabled", "on"}:
        return {"enabled": True, "exclude": exclude}
    if mode in {"none", "no_reasoning"}:
        return {"effort": "none", "exclude": exclude}
    if mode in {"minimal", "low", "medium", "high", "xhigh"}:
        return {"effort": mode, "exclude": exclude}
    if mode in {"tokens", "token_budget", "max_tokens", "budget"}:
        return {"max_tokens": max(0, min(64000, int(LLM_REASONING_MAX_TOKENS or 0))), "exclude": exclude}
    # prompt_light / prompt_strong are local-only/prompt-only modes; do not send API field.
    if mode in {"prompt", "prompt_light", "prompt_strong", "local_prompt", "local_light", "local_strong"}:
        return None
    return None

def llm_reasoning_system_suffix(model_name: str = "") -> str:
    """Tiny prompt-only reasoning hint for local models.

    This does not ask the model to expose chain-of-thought. It just allows a private
    checklist before emitting the required JSON. Useful for Qwen/Gemma local runs where
    OpenRouter-style `reasoning` parameters are unavailable.
    """
    mode = (LLM_REASONING_MODE or "off").strip().lower().replace("-", "_")
    provider = active_llm_provider()
    if mode in {"", "off", "false", "0", "disabled", "disable", "none", "no_reasoning"}:
        return ""
    if provider != "local" and mode not in {"prompt", "prompt_light", "prompt_strong", "local_prompt", "local_light", "local_strong"}:
        return ""
    if not LLM_LOCAL_REASONING_PROMPT:
        return ""
    if mode in {"prompt_strong", "local_strong"}:
        return " Privately check parent facts, engine functions, schema, and balance. Output only the final JSON object."
    return " Privately check constraints briefly. Output only the final JSON object."

def apply_llm_common_options(req: dict[str, Any], *, model_name: str, default_max_tokens: int | None = None, allow_reasoning: bool = True) -> dict[str, Any]:
    req["max_tokens"] = llm_answer_max_tokens(default_max_tokens)
    if allow_reasoning:
        reasoning = llm_reasoning_payload(model_name)
        if reasoning:
            req["reasoning"] = reasoning
    return req

_RESOLVED_LLM_MODELS: dict[str, str] = {}

# legacy contract marker for tests/documentation: ensure_llm_auth_configured()

def http_get_json(url: str, timeout: int = 5, headers: dict[str, str] | None = None) -> dict[str, Any]:
    merged = {"Accept": "application/json"}
    if headers:
        merged.update(headers)
    req = urlrequest.Request(url, headers=merged, method="GET")
    with urlrequest.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

def resolve_llm_model(context: dict[str, Any] | None = None) -> str:
    """Resolve the active OpenAI-compatible model name.

    Local: model=auto asks /v1/models and uses the first loaded model.
    OpenRouter: explicit INFINI_OPENROUTER_MODEL is preferred; model=auto tries to
    select a :free model from /models, then falls back to the first advertised model.
    """
    global _RESOLVED_LLM_MODELS
    ctx = context or _primary_llm_context()
    provider = active_llm_provider(ctx)
    configured = str(ctx.get("model") or "auto").strip()
    if configured and configured.lower() not in {"auto", "local-model", "local_model", "default"}:
        return configured
    cache_key = _llm_context_key(ctx)
    if _RESOLVED_LLM_MODELS.get(cache_key):
        return _RESOLVED_LLM_MODELS[cache_key]
    try:
        models = http_get_json(llm_models_url(ctx), timeout=6, headers=llm_headers({"Accept": "application/json"}, context=ctx))
        data = models.get("data") if isinstance(models, dict) else None
        if isinstance(data, list) and data:
            preferred = None
            if provider == "openrouter":
                for item in data:
                    mid = str((item or {}).get("id") or (item or {}).get("name") or "").strip()
                    if mid.endswith(":free"):
                        preferred = mid
                        break
            first = data[0] or {}
            mid = preferred or str(first.get("id") or first.get("name") or "").strip()
            if mid:
                _RESOLVED_LLM_MODELS[cache_key] = mid
                log_event("info", "resolved LLM model", {"provider": provider, "model": mid, "label": ctx.get("label")})
                return mid
    except Exception as e:
        log_event("warn", "could not auto-resolve LLM model", {"provider": provider, "error": repr(e), "url": llm_models_url(ctx), "label": ctx.get("label")})
    if provider == "openrouter":
        return configured if configured.lower() not in {"auto", "default"} else "~openai/gpt-latest"
    return configured or "local-model"

def _clean_llm_payload(payload: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(payload, ensure_ascii=False))
    if out.get("response_format") is None:
        out.pop("response_format", None)
    return out

def http_json(url: str, payload: dict[str, Any], timeout: int = 10, headers: dict[str, str] | None = None) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    merged = {"Content-Type": "application/json"}
    if headers:
        merged.update(headers)
    req = urlrequest.Request(url, data=data, headers=merged, method="POST")
    with urlrequest.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

def _llm_replay_stage_from_payload(payload: dict[str, Any]) -> str:
    """Best-effort label for an LLM hop, used only by raw replay fixtures.

    This is intentionally diagnostic/test infrastructure, not item design logic.
    It lets one INFINI_LLM_REPLAY_RAW directory feed planner, VFX-director,
    name/JSON repair, and genome-repair calls through the real JSON parse/repair path.
    """
    parts: list[str] = []
    for msg in payload.get("messages") or []:
        if isinstance(msg, dict):
            parts.append(str(msg.get("role") or ""))
            parts.append(str(msg.get("content") or ""))
    text = "\n".join(parts).lower()
    if "pixel-art asset director" in text or "infini_visual_director" in text or "visualkit" in text:
        return "vfx_director"
    if "repair incomplete combat genomes" in text or "infini_genome_repair" in text:
        return "genome_repair"
    if "repair" in text and "name" in text:
        return "name_repair"
    if "same planner" in text and "not a fallback" in text:
        return "author_repair"
    if "author of a terraria-like generated item" in text or "combine itema and itemb" in text or "infini_runtime_plan" in text:
        return "planner"
    return "llm"

def _replay_content_from_json_object(obj: Any, stage: str) -> str | None:
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        # Stage-keyed JSON object: {"planner":"...", "vfx_director":"..."}.
        direct = obj.get(stage)
        if isinstance(direct, str):
            return direct
        for key in ("content", "text", "response", "raw"):
            value = obj.get(key)
            if isinstance(value, str):
                return value
        choices = obj.get("choices")
        if isinstance(choices, list) and choices:
            try:
                content = choices[0]["message"]["content"]
                if isinstance(content, str):
                    return content
            except Exception:
                return None
    return None

def _load_llm_replay_raw(spec: str, stage: str) -> tuple[str, str]:
    path = Path(spec).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"INFINI_LLM_REPLAY_RAW path does not exist: {path}")

    if path.is_dir():
        candidates = [
            path / f"{stage}.txt",
            path / f"{stage}.json",
            path / f"{stage}.jsonl",
            path / "default.txt",
            path / "default.json",
        ]
        for candidate in candidates:
            if candidate.exists():
                content, source = _load_llm_replay_raw(str(candidate), stage)
                return content, source
        raise FileNotFoundError(f"No replay fixture for LLM stage '{stage}' in {path}")

    suffix = path.suffix.lower()
    raw = path.read_text(encoding="utf-8")
    if suffix == ".json":
        content = _replay_content_from_json_object(json.loads(raw), stage)
        if content is None:
            raise ValueError(f"Could not extract replay content from {path}")
        return content, str(path)

    if suffix == ".jsonl":
        fallback: str | None = None
        for line in raw.splitlines():
            if not line.strip():
                continue
            obj = json.loads(line)
            if isinstance(obj, dict):
                obj_stage = str(obj.get("stage") or obj.get("hop") or obj.get("kind") or "").strip()
                content = _replay_content_from_json_object(obj, stage)
                if content is None:
                    continue
                if obj_stage in {stage, "*", "all", "llm"}:
                    return content, f"{path}#{obj_stage or 'line'}"
                if fallback is None and not obj_stage:
                    fallback = content
            elif fallback is None and isinstance(obj, str):
                fallback = obj
        if fallback is not None:
            return fallback, f"{path}#fallback"
        raise ValueError(f"No replay content for LLM stage '{stage}' in {path}")

    return raw, str(path)

def _llm_replay_json_response(payload: dict[str, Any]) -> dict[str, Any] | None:
    spec = env_str("INFINI_LLM_REPLAY_RAW", "")
    if not spec:
        return None
    stage = _llm_replay_stage_from_payload(payload)
    content, source = _load_llm_replay_raw(spec, stage)
    log_event("info", "LLM replay raw response used", {"stage": stage, "source": source, "chars": len(content)})
    return {
        "choices": [
            {"message": {"role": "assistant", "content": content}}
        ],
        "_debug": {"replay": True, "stage": stage, "source": source},
    }

def _llm_error_text(exc: Exception) -> str:
    parts = [repr(exc), str(exc)]
    body = getattr(exc, "_infini_body", "")
    if body:
        parts.append(str(body))
    cause = getattr(exc, "__cause__", None)
    if cause is not None:
        parts.append(repr(cause))
        parts.append(str(cause))
    return " | ".join(p for p in parts if p).lower()


def _is_transport_error(exc: Exception) -> bool:
    if isinstance(exc, (urlerror.URLError, TimeoutError, ConnectionError)):
        return True
    text = _llm_error_text(exc)
    return any(tok in text for tok in ["timed out", "timeout", "connection refused", "connection reset", "temporarily unavailable", "name or service not known", "nodename nor servname", "failed to establish a new connection", "remote end closed connection"])


def _is_budget_or_auth_failure(exc: Exception) -> bool:
    if isinstance(exc, urlerror.HTTPError) and exc.code in {401, 402, 403, 429}:
        return True
    text = _llm_error_text(exc)
    return any(tok in text for tok in ["insufficient", "quota", "credit", "billing", "payment", "out of credits", "rate limit", "unauthorized", "api key", "余额", "balance", "no money"])


def _payload_for_context(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    out = _clean_llm_payload(payload)
    out["model"] = resolve_llm_model(context)
    return out


def _llm_chat_json_single_context(payload: dict[str, Any], timeout: int, context: dict[str, Any]) -> dict[str, Any]:
    ensure_llm_auth_configured(context)
    payload = _clean_llm_payload(payload)
    replay = _llm_replay_json_response(payload)
    if replay is not None:
        return replay
    payload = _payload_for_context(payload, context)
    url = llm_chat_completions_url(context)
    candidates: list[tuple[str, dict[str, Any]]] = [("original", payload)]
    if payload.get("reasoning") is not None:
        retry = dict(payload)
        retry.pop("reasoning", None)
        candidates.append(("without_reasoning", retry))
    if payload.get("response_format") is not None:
        retry = dict(payload)
        retry.pop("response_format", None)
        candidates.append(("without_response_format", retry))
    if payload.get("reasoning") is not None and payload.get("response_format") is not None:
        retry = dict(payload)
        retry.pop("reasoning", None)
        retry.pop("response_format", None)
        candidates.append(("without_reasoning_and_response_format", retry))

    last_error: Exception | None = None
    for label, candidate in candidates:
        try:
            if label != "original":
                log_event("warn", "retrying LLM request with reduced compatibility fields", {"provider": active_llm_provider(context), "mode": label, "label": context.get("label")})
            return http_json(url, candidate, timeout=timeout, headers=llm_headers(context=context))
        except urlerror.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")[:2000]
                setattr(e, "_infini_body", body)
            except Exception:
                pass
            last_error = e
            provider = active_llm_provider(context)
            if provider == "openrouter" and e.code == 401:
                msg = "OpenRouter auth failed: API key is missing/invalid or was not saved in config.env (401 Unauthorized)."
                log_event("warn", "OpenRouter auth failed", {"provider": provider, "mode": label, "status": e.code, "body": body, "hint": msg, "label": context.get("label")})
                raise RuntimeError(msg) from e
            if e.code in {400, 404, 422} and label != candidates[-1][0]:
                log_event("warn", "LLM endpoint rejected request fields; trying compatibility fallback", {"provider": provider, "mode": label, "status": e.code, "body": body, "label": context.get("label")})
                continue
            log_event("warn", "LLM HTTP error", {"provider": provider, "mode": label, "status": e.code, "body": body, "label": context.get("label")})
            raise
    if last_error:
        raise last_error
    raise RuntimeError("LLM request failed without HTTP response")


def llm_chat_json(payload: dict[str, Any], timeout: int = 10) -> dict[str, Any]:
    primary = _primary_llm_context()
    fallback = _fallback_llm_context()
    try:
        return _llm_chat_json_single_context(payload, timeout, primary)
    except Exception as first_error:
        if not fallback:
            raise
        if _is_budget_or_auth_failure(first_error):
            log_event("warn", "LLM primary failed; switching to fallback", {"reason": "budget_or_auth", "primaryProvider": active_llm_provider(primary), "primaryModel": primary.get("model"), "fallbackProvider": active_llm_provider(fallback), "fallbackModel": fallback.get("model")})
            return _llm_chat_json_single_context(payload, timeout, fallback)
        if _is_transport_error(first_error):
            last_error = first_error
            total_attempts = max(2, int(LLM_FALLBACK_NETWORK_FAILS or 2))
            for attempt in range(2, total_attempts + 1):
                try:
                    log_event("warn", "retrying primary LLM transport before fallback", {"attempt": attempt, "maxAttempts": total_attempts, "provider": active_llm_provider(primary), "model": primary.get("model")})
                    return _llm_chat_json_single_context(payload, timeout, primary)
                except Exception as retry_error:
                    last_error = retry_error
                    if _is_budget_or_auth_failure(retry_error):
                        log_event("warn", "LLM primary changed from transport failure to budget/auth failure; switching to fallback", {"provider": active_llm_provider(primary), "fallbackProvider": active_llm_provider(fallback), "fallbackModel": fallback.get("model")})
                        return _llm_chat_json_single_context(payload, timeout, fallback)
                    if not _is_transport_error(retry_error):
                        raise
            log_event("warn", "LLM primary transport failed repeatedly; switching to fallback", {"attempts": total_attempts, "primaryProvider": active_llm_provider(primary), "primaryModel": primary.get("model"), "fallbackProvider": active_llm_provider(fallback), "fallbackModel": fallback.get("model")})
            return _llm_chat_json_single_context(payload, timeout, fallback)
        raise

# =============================================================================
# Explicit pipeline dependencies
# =============================================================================
from infini_local.pipelines.pipeline_support import (
    ALLOWED_CATEGORIES,
    ENGINE_FN_CATALOG_V2,
    ENGINE_RUNTIME_API_VERSION,
    LLM_LOCAL_REASONING_PROMPT,
    LLM_MAX_TOKENS,
    LLM_FALLBACK_API_KEY,
    LLM_FALLBACK_BASE_URL,
    LLM_FALLBACK_MODEL,
    LLM_FALLBACK_NETWORK_FAILS,
    LLM_FALLBACK_PROVIDER,
    LLM_PROVIDER,
    LLM_RAW_TOKEN_MODE,
    LLM_REASONING_EXCLUDE,
    LLM_REASONING_MAX_TOKENS,
    LLM_REASONING_MODE,
    LLM_RESPONSE_FORMAT_MODE,
    LLM_RUNTIME_AUTHORING,
    LLM_RUNTIME_PLAN_REQUIRED,
    LLM_RUNTIME_STRICT_VALIDATION,
    LMSTUDIO_MODEL,
    LMSTUDIO_URL,
    OPENAI_COMPAT_API_KEY,
    OPENAI_COMPAT_BASE_URL,
    OPENAI_COMPAT_MODEL,
    OPENROUTER_API_KEY,
    OPENROUTER_APP_TITLE,
    OPENROUTER_BASE_URL,
    OPENROUTER_HTTP_REFERER,
    OPENROUTER_MODEL,
    PlannerUnavailable,
    USE_LLM,
    _env_float,
    _trace_message_summary,
    behavior_cost_multiplier,
    compile_runtime_plan_to_genome_result,
    compiled_runtime_contract,
    find_call,
    item_num,
    log_event,
    name_of,
    normalize_runtime_plan_inplace,
    structural_repair_runtime_plan_inplace,
    parse_first_valid_llm_json,
    runtime_plan,
    runtime_plan_quality_report,
    runtime_plan_validation_report,
    stable_hash,
    trace_event,
)

from infini_local.pipelines.combine_pipeline import (
    choose_from,
    clamp_vanilla_like_weapon_damage,
    combat_genome_required_for,
    normalize_category,
)

from infini_local.pipelines.parent_context_pipeline import (
    raw_parent_card_for_llm,
)
