from __future__ import annotations

import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any

from infini_local.core.effect_catalog import normalize_attack_pattern
from infini_local.core.env_utils import load_env_file, env_bool, env_float, env_int
from infini_local.core.item_identity_tools import (
    _stringish,
    dict_get_ci,
    fingerprint_of,
    generation_depth,
    generated_data_of,
    item_bool,
    item_field,
    item_identity,
    item_num,
    name_of,
    slug,
    stable_hash,
    tags_of,
)


# AGENT MAP: Python VFX manifest authoring/normalization contract.
# Produces presentation slots/channels/renderers that C# can execute safely. Keep
# gameplay out of motif/effect prose; combat behavior belongs in explicit runtime
# fields compiled by runtime_authoring.py.
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"


def load_json_file(path: Path, fallback: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        pass
    return fallback



def _vfx_clean_tag(value: Any) -> str:
    return slug(str(value or "").strip()).lower()


def _vfx_list_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in value:
        s = _vfx_clean_tag(raw)
        if s and s not in seen:
            out.append(s)
            seen.add(s)
    return out


def _vfx_director_name_tokens(item: dict[str, Any]) -> list[str]:
    fp = fingerprint_of(item)
    tokens = _vfx_list_strings(item.get("nameTokens"))
    if not tokens:
        tokens = _vfx_list_strings(fp.get("nameTokens") if isinstance(fp, dict) else [])
    return tokens


def _vfx_director_runtime_auto_features(item: dict[str, Any]) -> list[str]:
    fp = fingerprint_of(item)
    features = _vfx_list_strings(item.get("autoFeatures"))
    if isinstance(fp, dict):
        for tag in _vfx_list_strings(fp.get("autoFeatures")):
            if tag not in features:
                features.append(tag)
    return features


def _vfx_generated_authored_tags(item: dict[str, Any]) -> list[str]:
    gd = generated_data_of(item)
    out: list[str] = []
    for tag in _vfx_list_strings(dict_get_ci(gd, "tags", [])):
        if tag not in out:
            out.append(tag)
    can = dict_get_ci(gd, "canonical", {}) if isinstance(gd, dict) else {}
    if isinstance(can, dict):
        for field in ("hardTags", "softTags"):
            for tag in _vfx_list_strings(dict_get_ci(can, field, [])):
                if tag not in out:
                    out.append(tag)
    return out


def _vfx_semantic_expansion_for_director(name_tokens: list[str], runtime_features: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    """Transparent Director-only semantic expansion; not used by recipe selector scoring.

    This exists so Gemma can see why a parent got tags such as light/mana, without
    pretending that vanilla items have hand-authored tags.
    """
    derived: list[str] = []
    provenance: list[dict[str, str]] = []

    def add(tag: str, matched: str, source: str = "pythonSemanticExpansion") -> None:
        tag = _vfx_clean_tag(tag)
        if not tag or tag in derived:
            return
        derived.append(tag)
        provenance.append({"tag": tag, "source": source, "matched": matched})

    token_set = set(name_tokens)
    phrase = " ".join(name_tokens)

    # Include name/runtime tags in pythonDerivedTags as a complete readable bag.
    # Provenance for those source categories is emitted by _vfx_director_tag_packet,
    # so we do not duplicate it here.
    for token in name_tokens:
        token = _vfx_clean_tag(token)
        if token and token not in derived:
            derived.append(token)
    for feature in runtime_features:
        feature = _vfx_clean_tag(feature)
        if feature and feature not in derived:
            derived.append(feature)

    if "star" in token_set:
        add("light", "star")
        add("mana", "star")
    if "fallen" in token_set and "star" in token_set:
        add("light", "fallen star")
        add("mana", "fallen star")
    if "gel" in token_set or "slime" in token_set:
        add("slime", "gel/slime")
    if "wire" in token_set:
        add("electric", "wire")
        add("mechanism", "wire")
    if "lens" in token_set:
        add("glass", "lens")
        add("light", "lens")
    if "crystal" in token_set:
        add("crystal", "crystal")
        add("light", "crystal")
    if "torch" in token_set or "flame" in token_set or "fire" in token_set:
        add("fire", "torch/flame/fire")
        add("light", "torch/flame/fire")
    if "shadow" in token_set or "demon" in token_set or "corrupt" in token_set or "corruption" in token_set:
        add("shadow", "shadow/demon/corrupt")
    if "holy" in token_set or "hallowed" in token_set:
        add("holy", "holy/hallowed")
        add("light", "holy/hallowed")
    if "meteor" in token_set or "meteorite" in token_set:
        add("fire", "meteor/meteorite")
        add("star", "meteor/meteorite")
    if "mana" in token_set:
        add("mana", "mana")
        add("magic", "mana")
    if "book" in token_set or "tome" in token_set:
        add("magic", "book/tome")
    if "bullet" in token_set or "musket" in token_set or "gun" in token_set:
        add("metal", "bullet/musket/gun")
        add("ranged", "bullet/musket/gun")
    if "sword" in token_set or "blade" in token_set or "saber" in token_set:
        add("blade", "sword/blade/saber")
        add("melee", "sword/blade/saber")
    if "bow" in token_set or "arrow" in token_set:
        add("ranged", "bow/arrow")
    if phrase.strip():
        if "fallen star" in phrase:
            add("light", "fallen star")
            add("mana", "fallen star")

    return derived, provenance


def _vfx_director_tag_packet(item: dict[str, Any]) -> dict[str, Any]:
    name_tokens = _vfx_director_name_tokens(item)
    runtime_features = _vfx_director_runtime_auto_features(item)
    generated_tags = _vfx_generated_authored_tags(item)
    python_derived, derived_prov = _vfx_semantic_expansion_for_director(name_tokens, runtime_features)

    provenance: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    def add_prov(tag: str, source: str, matched: str) -> None:
        tag = _vfx_clean_tag(tag)
        if not tag:
            return
        key = (tag, source, matched)
        if key in seen:
            return
        seen.add(key)
        provenance.append({"tag": tag, "source": source, "matched": matched})

    raw_match = "/".join(str(x or "") for x in [item.get("internalName") or fingerprint_of(item).get("internalName"), name_of(item)] if str(x or "").strip())
    for token in name_tokens:
        add_prov(token, "nameToken", raw_match or token)
    for feature in runtime_features:
        add_prov(feature, "runtimeAutoFeature", "runtime/item facts")
    for tag in generated_tags:
        add_prov(tag, "generatedData", "generatedData.tags/canonical")
    for entry in derived_prov:
        add_prov(entry.get("tag", ""), entry.get("source", "pythonSemanticExpansion"), entry.get("matched", ""))

    return {
        "nameTokens": name_tokens,
        "runtimeAutoFeatures": runtime_features,
        "pythonDerivedTags": python_derived,
        "generatedAuthoredTags": generated_tags,
        "tagProvenance": provenance[:64],
        "provenanceNote": "Vanilla/modded parent items do not have hand-authored tags here; pythonDerivedTags are transparent substring/semantic expansion for the VFX Director packet only.",
    }




def _vfx_weak_hint_confidence(tag: str, sources: set[str], count: int, notes: list[str] | None = None) -> float:
    """Tiny, non-authoritative confidence for legacy codifier hints.

    This score is deliberately low. It is only prompt context for Gemma, never a
    Python-side selector or composer weight.
    """
    notes = notes or []
    score = 0.22
    if any(n.startswith("tags_of:") for n in notes):
        score += 0.08
    if any(n.startswith("pythonDerivedTags:") for n in notes):
        score += 0.05
    if any(n.startswith("generatedData:") for n in notes):
        score += 0.09
    if "child" in sources:
        score += 0.04
    if "parentA" in sources and "parentB" in sources:
        score += 0.04
    if count >= 2:
        score += 0.05
    if count >= 3:
        score += 0.03
    try:
        cap = float(VFX_LLM_WEAK_HINTS_CONFIDENCE_CAP)
    except Exception:
        cap = 0.45
    return round(max(0.05, min(cap, score)), 3)


def _vfx_collect_legacy_hint_tags(item: dict[str, Any] | None, label: str) -> list[tuple[str, str]]:
    """Collect weak prompt hints from the legacy tag/codifier surface.

    The return value is intentionally just (tag, source-note). Callers must not
    feed this back into recipe selection or slot routing.
    """
    if not isinstance(item, dict):
        return []
    tags: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(tag: Any, note: str) -> None:
        t = _vfx_clean_tag(tag)
        key = (t, note)
        if not t or key in seen:
            return
        seen.add(key)
        tags.append((t, note))

    # tags_of is the old mixed semantic/codifier bag. Keep it visible only as weak context.
    for tag in sorted(tags_of(item)):
        add(tag, f"tags_of:{label}")

    packet = _vfx_director_tag_packet(item)
    for tag in packet.get("pythonDerivedTags", []):
        add(tag, f"pythonDerivedTags:{label}")
    for tag in packet.get("generatedAuthoredTags", []):
        add(tag, f"generatedData:{label}")
    return tags


def build_vfx_director_weak_hints(parent_a: dict[str, Any] | None = None, parent_b: dict[str, Any] | None = None, child_item: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Optional non-authoritative weak hints for the LLM VFX Director.

    These hints are visible prompt context only. They do not select renderers,
    particle systems, recipes, slots, channels, or colors in Python.
    """
    if not VFX_LLM_WEAK_HINTS_ENABLED:
        return []
    counts: dict[str, int] = {}
    sources: dict[str, set[str]] = {}
    notes: dict[str, list[str]] = {}

    for label, item in (("parentA", parent_a), ("parentB", parent_b), ("child", child_item)):
        for tag, note in _vfx_collect_legacy_hint_tags(item, label):
            counts[tag] = counts.get(tag, 0) + 1
            sources.setdefault(tag, set()).add(label)
            if note.startswith("generatedData"):
                sources[tag].add("generatedData")
            notes.setdefault(tag, [])
            if note not in notes[tag]:
                notes[tag].append(note)

    ranked: list[tuple[float, str]] = []
    for tag, count in counts.items():
        score = _vfx_weak_hint_confidence(tag, sources.get(tag, set()), count, notes.get(tag, []))
        ranked.append((score, tag))
    ranked.sort(key=lambda x: (-x[0], x[1]))
    max_hints = max(0, int(VFX_LLM_WEAK_HINTS_MAX))
    out: list[dict[str, Any]] = []
    for score, tag in ranked[:max_hints]:
        out.append({
            "hint": tag,
            "source": "legacy_codifier",
            "confidence": score,
            "nonAuthoritative": True,
            "matched": notes.get(tag, [])[:4],
        })
    return out

def projectile_profile_of(item: dict[str, Any]) -> dict[str, Any]:
    gd = generated_data_of(item)
    attack = dict_get_ci(gd, "attack", {}) if gd else {}
    if isinstance(attack, dict) and attack.get("enabled"):
        try:
            pierce = int(float(attack.get("pierce") or 1))
        except Exception:
            pierce = 1
        penetrate = -1 if pierce == -1 else max(1, min(12, pierce))
        return {
            "type": int(item_num(item, "shoot", 0)),
            "sourceMod": "InfiniCrafterLocal",
            "internalName": "GeneratedProjectile",
            "fullName": "InfiniCrafterLocal/GeneratedProjectile",
            "itemShootSpeed": float(attack.get("speed") or item_num(item, "shootSpeed", 0)),
            "width": int(float(attack.get("projectileWidth") or 14)),
            "height": int(float(attack.get("projectileHeight") or 14)),
            "scale": float(attack.get("projectileScale") or 1.0),
            "aiStyle": 0,
            "penetrate": penetrate,
            "maxPenetrate": penetrate,
            "timeLeft": int(float(attack.get("lifetime") or 90)),
            "extraUpdates": int(float(attack.get("extraUpdates") or 0)),
            "tileCollide": bool(attack.get("tileCollide", True)),
            "ownerHitCheck": str(attack.get("delivery") or "") == "swing",
            "usesLocalNPCImmunity": True,
            "localNPCHitCooldown": int(float(attack.get("immunityCooldown") or 10)),
            "usesIDStaticNPCImmunity": False,
            "light": 0,
            "minion": False,
            "sentry": False,
            "engineMetrics": attack.get("engineMetrics") if isinstance(attack.get("engineMetrics"), dict) else {},
        }
    pp = item.get("projectileProfile")
    if isinstance(pp, dict):
        return pp
    fp = fingerprint_of(item)
    pp = fp.get("projectileProfile") if isinstance(fp, dict) else None
    return pp if isinstance(pp, dict) else {}


def effective_projectile_profile_of(item: dict[str, Any]) -> dict[str, Any]:
    return projectile_profile_of(item)


def proj_num(proj: dict[str, Any], name: str, default: float = 0.0) -> float:
    try:
        return float(proj.get(name, default) or 0)
    except Exception:
        return default


def proj_bool(proj: dict[str, Any], name: str) -> bool:
    v = proj.get(name, False)
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.lower() in {"1", "true", "yes", "y"}
    return bool(v)


def projectile_behavior_tags(item: dict[str, Any]) -> set[str]:
    tags: set[str] = set()
    proj = effective_projectile_profile_of(item)
    if not proj or proj.get("unavailable"):
        return tags
    tags.add("projectile")
    ai_style = int(proj_num(proj, "aiStyle", 0))
    penetrate = int(proj_num(proj, "penetrate", 1))
    time_left = int(proj_num(proj, "timeLeft", 0))
    extra_updates = int(proj_num(proj, "extraUpdates", 0))
    if penetrate == -1 or penetrate > 1:
        tags.add("piercing")
    if penetrate == -1:
        tags.add("infinite_pierce")
    if extra_updates > 0:
        tags.add("fast_projectile")
    if extra_updates >= 2:
        tags.add("very_fast_projectile")
    if not proj_bool(proj, "tileCollide"):
        tags.add("noncolliding_projectile")
    if proj_bool(proj, "ownerHitCheck"):
        tags.add("melee_projection")
    if proj_bool(proj, "minion"):
        tags.update({"summon", "minion"})
    if proj_bool(proj, "sentry"):
        tags.update({"summon", "sentry"})
    if proj_bool(proj, "usesLocalNPCImmunity") or proj_bool(proj, "usesIDStaticNPCImmunity"):
        tags.add("multi_hit_projectile")
    if time_left >= 240:
        tags.add("long_lived_projectile")
    if ai_style > 0:
        tags.add("vanilla_ai_style")
    return tags


def source_weapon_profile(item: dict[str, Any]) -> dict[str, Any]:
    proj = effective_projectile_profile_of(item)
    damage = max(0.0, item_num(item, "damage"))
    use_time = max(6.0, item_num(item, "useTime", item_num(item, "useAnimation", 30)))
    shoot = item_num(item, "shoot")
    shoot_speed = item_num(item, "shootSpeed")
    channel = item_bool(item, "channel")
    damage_class = str(item_field(item, "damageClass", "generic") or "generic").lower()
    behavior = sorted(projectile_behavior_tags(item))
    pierce = 0.0
    lifetime = 0.0
    extra_updates = 0.0
    ai_style = 0
    local_immune = False
    if proj:
        penetrate = int(proj_num(proj, "penetrate", 1))
        pierce = 8.0 if penetrate == -1 else max(0.0, float(penetrate - 1))
        lifetime = max(0.0, min(1800.0, proj_num(proj, "timeLeft", 0)))
        extra_updates = max(0.0, min(4.0, proj_num(proj, "extraUpdates", 0)))
        ai_style = int(proj_num(proj, "aiStyle", 0))
        local_immune = proj_bool(proj, "usesLocalNPCImmunity") or proj_bool(proj, "usesIDStaticNPCImmunity")
    attacks_per_second = 60.0 / max(6.0, use_time)
    effective_dps = damage * attacks_per_second * (1.0 + min(1.15, pierce * 0.18)) * (1.0 + min(0.35, extra_updates * 0.12))
    return {
        "damage": damage,
        "damageClass": damage_class,
        "shoot": shoot,
        "shootSpeed": shoot_speed,
        "channel": channel,
        "aiStyle": ai_style,
        "piercePotential": pierce,
        "lifetime": lifetime,
        "extraUpdates": extra_updates,
        "localImmunity": local_immune,
        "effectiveDpsSignal": round(effective_dps, 3),
        "projectileProfile": proj,
        "behaviorTags": behavior,
    }


load_env_file(ROOT / "config.env")

# v0.3.39: VFX manifest pipeline lives in this module. server.py remains the entrypoint.
VFX_MORPH_LIBRARY = load_json_file(DATA_DIR / "vfx_morph_recipes.json", {"recipes": []})
VFX_SLOT_MACRO_LIBRARY = load_json_file(DATA_DIR / "vfx_slot_macros.json", {"macros": {}})
VFX_SLOT_MACROS = VFX_SLOT_MACRO_LIBRARY.get("macros", {}) if isinstance(VFX_SLOT_MACRO_LIBRARY, dict) and isinstance(VFX_SLOT_MACRO_LIBRARY.get("macros"), dict) else {}
VFX_MORPH_RECIPES_RAW = [r for r in (VFX_MORPH_LIBRARY.get("recipes") or []) if isinstance(r, dict) and not r.get("disabled")] if isinstance(VFX_MORPH_LIBRARY, dict) else []
VFX_MORPH_RECIPES = VFX_MORPH_RECIPES_RAW  # expanded lazily by get_vfx_recipes(); kept for old debug code.
_VFX_EXPANDED_RECIPE_CACHE: list[dict[str, Any]] | None = None

# v0.3.16+ VFX selector/env knobs.
VFX_SELECTOR_ENABLED = env_bool("INFINI_VFX_SELECTOR", True)
# v0.4.3: when runtimePlan.engineCalls exists, prefer a tiny author-intent manifest over
# legacy recipe roulette. This keeps VFX as execution, not game design.
VFX_RUNTIME_INTENT_FIRST = env_bool("INFINI_VFX_RUNTIME_INTENT_FIRST", True)
VFX_SELECTOR_DEBUG = env_bool("INFINI_VFX_SELECTOR_DEBUG", True)
VFX_SELECTOR_TOP = env_int("INFINI_VFX_SELECTOR_TOP", 5)
VFX_SELECTOR_HINT_WEIGHT = env_float("INFINI_VFX_SELECTOR_HINT_WEIGHT", 1.0)
VFX_SELECTOR_JITTER = env_float("INFINI_VFX_SELECTOR_JITTER", 18.0)
VFX_SELECTOR_NOVELTY_WEIGHT = env_float("INFINI_VFX_SELECTOR_NOVELTY_WEIGHT", 6.0)

# v0.3.40 optional second-pass LLM VFX Director.
# It authors a concrete frozen manifest surface; Python only validates/clamps it,
# and falls back to the old selector if disabled or invalid. The prompt is intentionally
# limited to parentA, parentB, childItem, vfxSurface and constraints; name-bank words
# must not steer director generation.
VFX_LLM_DIRECTOR_ENABLED = env_bool("INFINI_VFX_LLM_DIRECTOR", False)
VFX_LLM_DIRECTOR_MAX_SLOTS = env_int("INFINI_VFX_LLM_DIRECTOR_MAX_SLOTS", 5)
VFX_LLM_DIRECTOR_MAX_TOKENS = env_int("INFINI_VFX_LLM_DIRECTOR_MAX_TOKENS", 1800)
VFX_LLM_DIRECTOR_TEMPERATURE = env_float("INFINI_VFX_LLM_DIRECTOR_TEMPERATURE", 0.34)
VFX_LLM_DIRECTOR_TIMEOUT = env_int("INFINI_VFX_LLM_DIRECTOR_TIMEOUT", 75)
VFX_LLM_DIRECTOR_REPAIR_ATTEMPTS = env_int("INFINI_VFX_LLM_DIRECTOR_REPAIR_ATTEMPTS", 1)
VFX_LLM_WEAK_HINTS_ENABLED = env_bool("INFINI_VFX_LLM_WEAK_HINTS", False)
VFX_LLM_WEAK_HINTS_MAX = env_int("INFINI_VFX_LLM_WEAK_HINTS_MAX", 6)
VFX_LLM_WEAK_HINTS_CONFIDENCE_CAP = env_float("INFINI_VFX_LLM_WEAK_HINTS_CONFIDENCE_CAP", 0.45)
VFX_EFFECT_NAME_BANK_MAX_CARDS = env_int("INFINI_VFX_EFFECT_NAME_BANK_MAX_CARDS", 8)
VFX_EFFECT_NAME_BANK_MAX_NAMES = env_int("INFINI_VFX_EFFECT_NAME_BANK_MAX_NAMES", 42)
VFX_EFFECT_NAME_BANK_PATH = DATA_DIR / "vfx_effect_name_bank.json"


VFX_PROCEDURAL_COMPOSE = env_bool("INFINI_VFX_PROCEDURAL_COMPOSE", True)
VFX_RECIPE_BLEND_ENABLED = env_bool("INFINI_VFX_RECIPE_BLEND", True)
VFX_PROCEDURAL_MAX_EXTRA_SLOTS = env_int("INFINI_VFX_PROCEDURAL_MAX_EXTRA_SLOTS", 5)
VFX_PROCEDURAL_BLEND_CANDIDATES = env_int("INFINI_VFX_PROCEDURAL_BLEND_CANDIDATES", 2)
VFX_PROCEDURAL_CHANCE = env_float("INFINI_VFX_PROCEDURAL_CHANCE", 0.82)

VFX_MUNDANE_DUPLICATE_GUARD = env_bool("INFINI_VFX_MUNDANE_DUPLICATE_GUARD", True)
VFX_MUNDANE_MAX_SLOTS = env_int("INFINI_VFX_MUNDANE_MAX_SLOTS", 3)

VFX_PARENT_EFFECT_INHERITANCE = env_bool("INFINI_VFX_PARENT_EFFECT_INHERITANCE", True)
VFX_PARENT_EFFECT_WEIGHT = env_float("INFINI_VFX_PARENT_EFFECT_WEIGHT", 0.75)
VFX_PARENT_EFFECT_STRONG_THRESHOLD = env_float("INFINI_VFX_PARENT_EFFECT_STRONG_THRESHOLD", 0.48)
VFX_PARENT_EFFECT_MAX_INHERITED_SLOTS = env_int("INFINI_VFX_PARENT_EFFECT_MAX_INHERITED_SLOTS", 3)

VFX_RENDER_QUALITY = "Full"
VFX_EMERGENCY_MAX_PARTICLES_PER_TICK = env_int("INFINI_VFX_EMERGENCY_MAX_PARTICLES_PER_TICK", 240)
VFX_EMERGENCY_MAX_PARTICLES_TOTAL = env_int("INFINI_VFX_EMERGENCY_MAX_PARTICLES_TOTAL", 9000)
VFX_EMERGENCY_MAX_DRAW_CALLS = env_int("INFINI_VFX_EMERGENCY_MAX_DRAW_CALLS", 420)
VFX_MAGNITUDE_JITTER = env_float("INFINI_VFX_MAGNITUDE_JITTER", 0.18)



def get_vfx_effect_name_bank() -> dict[str, Any]:
    """Load the tiny VFX naming bank for the debug endpoint/documentation only.

    The optional LLM VFX Director no longer receives this bank; generated manifests
    are controlled only by canonical enum/range fields.
    """
    data = load_json_file(VFX_EFFECT_NAME_BANK_PATH, {})
    return data if isinstance(data, dict) else {}


def _vfx_text_for_name_bank(parent_a: dict[str, Any] | None, parent_b: dict[str, Any] | None, child_item: dict[str, Any] | None) -> str:
    parts: list[str] = []
    for item in (parent_a, parent_b, child_item):
        if not isinstance(item, dict):
            continue
        gd = generated_data_of(item)
        attack = dict_get_ci(gd, "attack", {}) if isinstance(gd, dict) else item.get("attack") if isinstance(item.get("attack"), dict) else {}
        visual = dict_get_ci(gd, "visual", {}) if isinstance(gd, dict) else item.get("visual") if isinstance(item.get("visual"), dict) else {}
        kit = item.get("visualKit") if isinstance(item.get("visualKit"), dict) else {}
        parts.extend([
            str(item.get("name") or ""),
            str(item.get("tooltip") or ""),
            str(dict_get_ci(attack, "pattern", "") or dict_get_ci(attack, "attackPattern", "")),
            str(dict_get_ci(attack, "toyIdentity", "")),
            str(dict_get_ci(attack, "projectileTrail", "")),
            str(dict_get_ci(attack, "projectileImpact", "")),
            str(dict_get_ci(attack, "visualAnimationPlan", "")),
            str(dict_get_ci(visual, "styleGuide", "") or kit.get("styleGuide", "")),
            str(dict_get_ci(visual, "projectileImagePrompt", "") or kit.get("projectileSpritePrompt", "")),
            str(dict_get_ci(visual, "impactImagePrompt", "") or kit.get("impactSpritePrompt", "")),
            " ".join(str(t) for t in (item.get("tags") or [])[:12]) if isinstance(item.get("tags"), list) else "",
        ])
    return "\n".join(x for x in parts if x)


def vfx_director_name_bank(parent_a: dict[str, Any] | None = None, parent_b: dict[str, Any] | None = None, child_item: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return compact VFX name cards for the debug endpoint/documentation only.

    These names are not passed to the optional LLM VFX Director and are never
    executable identifiers.
    """
    bank = get_vfx_effect_name_bank()
    cards = [c for c in (bank.get("cards") or []) if isinstance(c, dict)]
    if not cards:
        return {"note": "empty name bank", "cards": []}
    words = _vfx_words(_vfx_text_for_name_bank(parent_a, parent_b, child_item))
    scored: list[tuple[float, dict[str, Any]]] = []
    for idx, card in enumerate(cards):
        families = {str(x).lower() for x in (card.get("families") or [])}
        names = [str(x) for x in (card.get("names") or [])]
        card_words = _vfx_words(" ".join(list(families) + names))
        score = len(words & card_words) * 6.0 + (len(words & families) * 8.0)
        # Keep a little stable diversity even with sparse text.
        score += (idx % 3) * 0.05
        scored.append((score, card))
    scored.sort(key=lambda x: x[0], reverse=True)
    max_cards = max(1, VFX_EFFECT_NAME_BANK_MAX_CARDS)
    max_names = max(8, VFX_EFFECT_NAME_BANK_MAX_NAMES)
    selected = []
    used_names = 0
    for score, card in scored[:max_cards]:
        names = [str(x) for x in (card.get("names") or []) if str(x).strip()]
        if used_names + len(names) > max_names:
            names = names[:max(0, max_names - used_names)]
        if not names:
            continue
        used_names += len(names)
        selected.append({
            "id": str(card.get("id") or ""),
            "families": [str(x) for x in (card.get("families") or [])[:5]],
            "names": names,
            "runtimeBias": card.get("runtimeBias") if isinstance(card.get("runtimeBias"), dict) else {},
        })
        if used_names >= max_names:
            break
    return {
        "note": "Debug/documentation VFX vocabulary only. Not passed to the LLM VFX Director and not used as runtime enum values.",
        "sources": [s for s in (bank.get("sources") or [])[:4] if isinstance(s, dict)],
        "cards": selected,
    }

def vfx_director_surface() -> dict[str, Any]:
    """Compact runtime surface for the optional Gemma VFX Director.

    This is intentionally a tiny enum/range contract, not the recipe library and not C# code.
    The LLM authors slots; Python validates/clamps and freezes them into the normal manifest.
    """
    return {
        "events": ["travel", "active", "tick", "hit", "kill", "expire"],
        "rendererKind": [
            "projectileAfterimage", "spriteStampTrail", "historyRibbon", "tipTrail",
            "ghostArc", "wavyStrip", "beamLine", "fieldPulse", "orbitingMotes",
            "actorAfterimage", "impactRing", "impactSprite", "childMotes", "lightCue", "soundCue",
        ],
        "backend": ["Auto", "Realtime", "Primitive", "Sprite", "Particle"],
        "textureRole": ["projectile", "impact", "child", "field"],
        "particleRole": ["projectile", "impact", "child", "field"],
        "anchor": ["self", "owner", "tip", "tipHistory", "hitPoint", "velocity", "field"],
        "channel": ["motionTrail", "coreGlow", "ambientParticles", "impactShape", "impactParticles", "decaySmoke", "light", "sound"],
        "lane": ["primary", "support", "accent", "ornament", "cue"],
        "emissionMode": ["wake", "orbit", "residue", "burst", "cone", "ring", "spiral", "point"],
        "blend": ["alpha", "additive"],
        "particleSystemId": ["pl:glow", "pl:shard", "pl:smoke", "pl:spark", "dust"],
        "numericRanges": {
            "effectMagnitude": [0.0, 1.0],
            "scale": [0.15, 5.0],
            "density": [0.0, 1.0],
            "duration": [3, 120],
            "alpha": [0.0, 1.0],
            "spread": [0.0, 2.0],
            "jitter": [0.0, 1.5],
            "phaseOffset": [-1.0, 1.0],
            "budgetWeight": [0.1, 4.0],
            "signatureWeight": [0.0, 1.0],
            "visualCost": [0.0, 1.0],
            "fadeIn": [0.0, 0.8],
            "fadeOut": [0.0, 0.8],
            "startTick": [0, 120],
            "repeatEvery": [0, 120],
        },
    }


def _vfx_compact_item_for_director(item: dict[str, Any] | None) -> dict[str, Any]:
    item = item if isinstance(item, dict) else {}
    gd = generated_data_of(item)
    attack = dict_get_ci(gd, "attack", {}) if isinstance(gd, dict) else {}
    visual = dict_get_ci(gd, "visual", {}) if isinstance(gd, dict) else {}
    fp = fingerprint_of(item)
    tags_packet = _vfx_director_tag_packet(item)
    return {
        "name": name_of(item),
        "id": item.get("id"),
        "sourceMod": item.get("sourceMod") or fp.get("sourceMod"),
        "internalName": item.get("internalName") or fp.get("internalName"),
        "displayName": name_of(item),
        "fullName": item.get("fullName") or fp.get("fullName"),
        "damage": item_field(item, "damage", 0),
        "rare": item_field(item, "rare", item_field(item, "rarity", 0)),
        "useTime": item_field(item, "useTime", 0),
        "shoot": item_field(item, "shoot", 0),
        "shootSpeed": item_field(item, "shootSpeed", 0),
        "nameTokens": tags_packet["nameTokens"],
        "runtimeAutoFeatures": tags_packet["runtimeAutoFeatures"],
        "pythonDerivedTags": tags_packet["pythonDerivedTags"],
        "generatedAuthoredTags": tags_packet["generatedAuthoredTags"],
        "tagProvenance": tags_packet["tagProvenance"],
        "tagProvenanceNote": tags_packet["provenanceNote"],
        # Deprecated compatibility field: keep it readable, but expose provenance above.
        "tags": sorted(set(tags_packet["pythonDerivedTags"]) | set(tags_packet["generatedAuthoredTags"]))[:24],
        "projectileProfile": effective_projectile_profile_of(item),
        "parentVfxSignals": item.get("parentVfxSignals") or fp.get("parentVfxSignals"),
        "generatedAttack": {
            "enabled": bool(attack.get("enabled")) if isinstance(attack, dict) else False,
            "pattern": dict_get_ci(attack, "pattern", dict_get_ci(attack, "attackPattern", "")) if isinstance(attack, dict) else "",
            "toyIdentity": dict_get_ci(attack, "toyIdentity", "") if isinstance(attack, dict) else "",
            "projectileTrail": dict_get_ci(attack, "projectileTrail", "") if isinstance(attack, dict) else "",
            "projectileImpact": dict_get_ci(attack, "projectileImpact", "") if isinstance(attack, dict) else "",
        },
        "visual": {
            "palette": dict_get_ci(visual, "palette", []) if isinstance(visual, dict) else [],
            "projectilePrompt": dict_get_ci(visual, "projectileImagePrompt", "") if isinstance(visual, dict) else "",
            "impactPrompt": dict_get_ci(visual, "impactImagePrompt", "") if isinstance(visual, dict) else "",
            "childPrompt": dict_get_ci(visual, "childImagePrompt", "") if isinstance(visual, dict) else "",
            "fieldPrompt": dict_get_ci(visual, "fieldImagePrompt", "") if isinstance(visual, dict) else "",
        },
    }


def _vfx_compact_child_for_director(data: dict[str, Any]) -> dict[str, Any]:
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    kit = data.get("visualKit") if isinstance(data.get("visualKit"), dict) else {}
    gameplay = data.get("gameplay") if isinstance(data.get("gameplay"), dict) else {}
    return {
        "name": data.get("name"),
        "tooltip": data.get("tooltip"),
        "category": data.get("category"),
        "gameplay": {
            "damage": gameplay.get("damage"),
            "damageClass": gameplay.get("damageClass"),
            "useTime": gameplay.get("useTime"),
            "rarity": gameplay.get("rarity"),
            "stage": gameplay.get("stage"),
            "powerBudget": gameplay.get("powerBudget"),
        },
        "attack": {
            "enabled": attack.get("enabled"),
            "pattern": attack.get("pattern") or attack.get("attackPattern"),
            "delivery": attack.get("delivery"),
            "toyIdentity": attack.get("toyIdentity"),
            "specialRule": attack.get("specialRule"),
            "behaviorTimeline": attack.get("behaviorTimeline"),
            "projectileShape": attack.get("projectileShape"),
            "projectileMotion": attack.get("projectileMotion"),
            "projectileTrail": attack.get("projectileTrail"),
            "projectileImpact": attack.get("projectileImpact"),
            "projectileChild": attack.get("projectileChild"),
            "visualAnimationPlan": attack.get("visualAnimationPlan"),
        },
        "visual": {
            "styleGuide": kit.get("styleGuide") or visual.get("styleGuide"),
            "palette": kit.get("palette") or visual.get("palette"),
            "projectilePrompt": attack.get("projectileSpritePrompt") or kit.get("projectileSpritePrompt") or visual.get("projectileImagePrompt"),
            "impactPrompt": attack.get("impactSpritePrompt") or kit.get("impactSpritePrompt") or visual.get("impactImagePrompt"),
            "childPrompt": attack.get("childSpritePrompt") or kit.get("childSpritePrompt") or visual.get("childImagePrompt"),
            "fieldPrompt": attack.get("fieldSpritePrompt") or kit.get("fieldSpritePrompt") or visual.get("fieldImagePrompt"),
        },
        "availableRoles": sorted(_vfx_available_roles(data)),
    }


def build_vfx_director_prompt(parent_a: dict[str, Any] | None, parent_b: dict[str, Any] | None, child_item: dict[str, Any], vfx_surface: dict[str, Any] | None = None, constraints: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the user payload for the optional LLM VFX Director pass.

    Keep this payload narrow: Gemma receives only the two parents, the child item,
    canonical VFX surface enums/ranges, constraints, and a field contract.
    """
    surface = vfx_surface or vfx_director_surface()
    parent_a_card = _vfx_compact_item_for_director(parent_a)
    parent_b_card = _vfx_compact_item_for_director(parent_b)
    child_card = _vfx_compact_child_for_director(child_item)
    weak_hints = build_vfx_director_weak_hints(parent_a, parent_b, child_item)
    packet = {
        "parentA": parent_a_card,
        "parentB": parent_b_card,
        "childItem": child_card,
        "provenanceContract": {
            "nameTokens": "tokens sent by C# GeneratorClient.NameTokens from internalName/displayName only",
            "runtimeAutoFeatures": "mechanical facts from C# AutoFeaturesFromItem / runtime fields",
            "pythonDerivedTags": "transparent Python semantic expansion from nameTokens/runtime facts for Director context only",
            "generatedAuthoredTags": "only tags authored in generatedData for generated items",
            "tagProvenance": "per-tag source + matched text/fact; vanilla parents are not treated as hand-authored tagged items",
        },
    }
    if VFX_LLM_WEAK_HINTS_ENABLED:
        packet["weakHints"] = weak_hints
        packet["weakHintsPolicy"] = "optional_non_authoritative"
        packet["weakHintsContract"] = "Weak hints come from the legacy codifier/tags_of layer. They are optional, may be wrong or generic, and are not theme tags or semantic tags."
    return {
        "vfxInputPacket": packet,
        "weakHintsInstruction": "Weak hints are optional. Choose VFX from combined child concept, attack/visual fields, parent facts, VFX surface, and hints; avoid same-hint repetition.",
        "parentA": parent_a_card,
        "parentB": parent_b_card,
        "childItem": child_card,
        "vfxSurface": surface,
        "constraints": constraints or {},
        "requiredJsonShape": {
            "type": "object",
            "requiredTopLevelFields": ["effectMagnitude", "visualBudgetClass", "slots"],
            "optionalTopLevelFields": ["identity"],
            "additionalTopLevelFields": "do not add keys outside this contract. Known forbidden fields are rejected; unknown extras are validation errors.",
            "topLevelContract": {
                "effectMagnitude": "float in vfxSurface.numericRanges.effectMagnitude",
                "visualBudgetClass": "one of tiny|small|normal|large|signature",
                "identity": "optional short debug note only; runtime must not parse it",
            },
            "slots": {
                "type": "array",
                "count": "between constraints.slots[0] and constraints.slots[1]",
                "additionalSlotFields": "do not add keys outside this contract. Known forbidden fields are rejected; unknown extras are validation errors.",
                "requiredSlotFields": [
                    "event", "rendererKind", "backend", "textureRole", "particleRole",
                    "anchor", "channel", "lane", "emissionMode", "blend", "particleSystemId",
                    "scale", "density", "duration", "alpha", "spread", "jitter",
                    "budgetWeight", "signatureWeight", "visualCost", "fadeIn", "fadeOut"
                ],
                "enumFields": {
                    "event": "one vfxSurface.events value",
                    "rendererKind": "one vfxSurface.rendererKind value",
                    "backend": "one vfxSurface.backend value",
                    "textureRole": "one vfxSurface.textureRole value",
                    "particleRole": "one vfxSurface.particleRole value",
                    "anchor": "one vfxSurface.anchor value",
                    "channel": "one vfxSurface.channel value",
                    "lane": "one vfxSurface.lane value",
                    "emissionMode": "one vfxSurface.emissionMode value",
                    "blend": "one vfxSurface.blend value",
                    "particleSystemId": "one explicit vfxSurface.particleSystemId value: pl:glow, pl:shard, pl:smoke, pl:spark, or dust",
                },
                "numericFields": {
                    "scale": "float in vfxSurface.numericRanges.scale",
                    "density": "float in vfxSurface.numericRanges.density",
                    "duration": "integer in vfxSurface.numericRanges.duration",
                    "alpha": "float in vfxSurface.numericRanges.alpha",
                    "spread": "float in vfxSurface.numericRanges.spread",
                    "jitter": "float in vfxSurface.numericRanges.jitter",
                    "phaseOffset": "optional float in vfxSurface.numericRanges.phaseOffset",
                    "budgetWeight": "float in vfxSurface.numericRanges.budgetWeight",
                    "signatureWeight": "float in vfxSurface.numericRanges.signatureWeight",
                    "visualCost": "float in vfxSurface.numericRanges.visualCost",
                    "fadeIn": "float in vfxSurface.numericRanges.fadeIn",
                    "fadeOut": "float in vfxSurface.numericRanges.fadeOut",
                    "startTick": "optional integer in vfxSurface.numericRanges.startTick",
                    "repeatEvery": "optional integer in vfxSurface.numericRanges.repeatEvery",
                },
            },
        },
    }


def build_vfx_director_continuation_payload(parent_a: dict[str, Any] | None = None, parent_b: dict[str, Any] | None = None, child_item: dict[str, Any] | None = None, vfx_surface: dict[str, Any] | None = None, constraints: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build only the final continuation instruction for the VFX pass.

    Parent/item context comes from the preceding planner system/user/assistant
    messages. This payload intentionally contains no vfxNameBank, no effectName,
    no inspirationNames, and no example-like numeric slot.
    """
    surface = vfx_surface or vfx_director_surface()
    constraints = constraints or {}
    required_shape = build_vfx_director_prompt(None, None, {}, surface, constraints).get("requiredJsonShape", {})
    vfx_input_packet = build_vfx_director_prompt(parent_a, parent_b, child_item or {}, surface, constraints).get("vfxInputPacket", {})
    return {
        "task": "Continue from the generated item and author only its runtime VFX manifest.",
        "continuationMode": "Use the previous assistant item JSON plus VFX_INPUT_PACKET provenance.",
        "vfxInputPacket": vfx_input_packet,
        "rules": [
            "Return one JSON object; no markdown or reasoning.",
            "Do not redesign, rename, rebalance, or add gameplay mechanics.",
            "No unauthored glow, magic, energy, material effects, child motes, or fields.",
            "If no visible VFX was requested, return empty slots when allowed.",
            "Weak hints are optional; combine them with child concept, attack/visual fields, parent facts, and VFX surface; avoid same-hint repetition.",
            "Use only listed VFX enums/ranges.",
            "particleSystemId must be explicit: pl:glow, pl:shard, pl:smoke, pl:spark, or dust.",
            "Author concrete slot parameters only; Python validates enums/ranges/budget.",
            "No baked commands or engine code."
        ],
        "vfxSurface": surface,
        "constraints": constraints,
        "requiredJsonShape": required_shape,
    }


def _vfx_planner_continuation_from_item(child_item: dict[str, Any]) -> dict[str, Any] | None:
    """Read hidden/debug planner-chat continuation data from the child item."""
    if not isinstance(child_item, dict):
        return None
    cont = child_item.get("_llmContinuation")
    if not isinstance(cont, dict):
        debug = child_item.get("debug") if isinstance(child_item.get("debug"), dict) else {}
        cont = debug.get("_llmContinuation") if isinstance(debug.get("_llmContinuation"), dict) else None
    if not isinstance(cont, dict):
        return None
    system = str(cont.get("plannerSystemPrompt") or cont.get("systemPrompt") or "").strip()
    user_content = str(cont.get("plannerUserContent") or "").strip()
    if not user_content and isinstance(cont.get("plannerUserPayload"), dict):
        user_content = json.dumps(cont.get("plannerUserPayload"), ensure_ascii=False, separators=(",", ":"))
    assistant_content = str(cont.get("plannerAssistantContent") or "").strip()
    if not assistant_content and isinstance(cont.get("plannerParsedChildJson"), dict):
        assistant_content = json.dumps(cont.get("plannerParsedChildJson"), ensure_ascii=False, separators=(",", ":"))
    if not system or not user_content or not assistant_content:
        return None
    return {
        "system": system,
        "user": user_content,
        "assistant": assistant_content,
    }


def build_vfx_director_continuation_messages(child_item: dict[str, Any], parent_a: dict[str, Any] | None = None, parent_b: dict[str, Any] | None = None, vfx_surface: dict[str, Any] | None = None, constraints: dict[str, Any] | None = None) -> list[dict[str, str]] | None:
    """Build the full stateless messages[] for continuation VFX Director."""
    cont = _vfx_planner_continuation_from_item(child_item)
    if not cont:
        return None
    instruction = build_vfx_director_continuation_payload(parent_a, parent_b, child_item, vfx_surface, constraints)
    return [
        {"role": "system", "content": cont["system"]},
        {"role": "user", "content": cont["user"]},
        {"role": "assistant", "content": cont["assistant"]},
        {"role": "user", "content": json.dumps(instruction, ensure_ascii=False, separators=(",", ":"))},
    ]


def _vfx_float(value: Any, lo: float, hi: float, fallback: float) -> float:
    try:
        x = float(value)
    except Exception:
        x = fallback
    if not math.isfinite(x):
        x = fallback
    return max(lo, min(hi, x))


def _vfx_int(value: Any, lo: int, hi: int, fallback: int) -> int:
    try:
        x = int(round(float(value)))
    except Exception:
        x = fallback
    return max(lo, min(hi, x))


def _vfx_director_enum(value: Any, allowed: list[str], fallback: str | None = None) -> str | None:
    raw = str(value or "").strip()
    if raw in allowed:
        return raw
    low = raw.lower().replace("_", "").replace("-", "")
    for item in allowed:
        if item.lower().replace("_", "").replace("-", "") == low:
            return item
    return fallback


def _vfx_director_enum_required(slot: dict[str, Any], field: str, allowed: list[str]) -> str | None:
    if field not in slot:
        return None
    value = _vfx_director_enum(slot.get(field), allowed)
    return value if value in allowed else None


def _vfx_director_number_required(slot: dict[str, Any], field: str, lo: float, hi: float, integer: bool = False) -> float | int | None:
    if field not in slot:
        return None
    try:
        x = float(slot.get(field))
    except Exception:
        return None
    if not math.isfinite(x):
        return None
    # Clamp authored numeric values instead of rejecting the whole manifest for a small range miss.
    # Enum mistakes still invalidate; numeric range mistakes are safe to sanitize.
    x = max(lo, min(hi, x))
    return int(round(x)) if integer else x


def _vfx_director_error(errors: list[dict[str, Any]], path: str, error: str, actual: Any = None, expected: Any = None, allowed: Any = None) -> None:
    item: dict[str, Any] = {"path": path, "error": error}
    if actual is not None:
        item["actual"] = actual
    if expected is not None:
        item["expected"] = expected
    if allowed is not None:
        item["allowed"] = allowed
    errors.append(item)


def _vfx_director_warning(warnings: list[dict[str, Any]], path: str, warning: str, actual: Any = None, clamped: Any = None, expected: Any = None) -> None:
    item: dict[str, Any] = {"path": path, "warning": warning}
    if actual is not None:
        item["actual"] = actual
    if clamped is not None:
        item["clamped"] = clamped
    if expected is not None:
        item["expected"] = expected
    warnings.append(item)


def _vfx_director_check_enum(errors: list[dict[str, Any]], obj: dict[str, Any], path: str, field: str, allowed: list[str], required: bool = True) -> str | None:
    if field not in obj:
        if required:
            _vfx_director_error(errors, f"{path}.{field}" if path else field, "missing_required", expected={"allowed": allowed})
        return None
    value = obj.get(field)
    if not isinstance(value, str):
        _vfx_director_error(errors, f"{path}.{field}" if path else field, "invalid_type", actual=value, expected="string", allowed=allowed)
        return None
    normalized = _vfx_director_enum(value, allowed)
    if normalized not in allowed:
        _vfx_director_error(errors, f"{path}.{field}" if path else field, "unknown_enum", actual=value, allowed=allowed)
        return None
    return normalized


def _vfx_director_check_number(errors: list[dict[str, Any]], warnings: list[dict[str, Any]], obj: dict[str, Any], path: str, field: str, lo: float, hi: float, integer: bool = False, required: bool = True) -> float | int | None:
    full_path = f"{path}.{field}" if path else field
    if field not in obj:
        if required:
            _vfx_director_error(errors, full_path, "missing_required", expected={"min": lo, "max": hi})
        return None
    value = obj.get(field)
    if isinstance(value, bool):
        _vfx_director_error(errors, full_path, "invalid_type", actual=value, expected="integer" if integer else "number")
        return None
    try:
        x = float(value)
    except Exception:
        _vfx_director_error(errors, full_path, "invalid_type", actual=value, expected="integer" if integer else "number")
        return None
    if not math.isfinite(x):
        _vfx_director_error(errors, full_path, "invalid_type", actual=value, expected="finite number")
        return None
    if x < lo or x > hi:
        # Numeric range mistakes are clampable and should not make the entire VFX manifest invalid.
        # Record a warning so audits/debug can see that validation intervened without suffocating the model.
        clamped = int(round(max(lo, min(hi, x)))) if integer else max(lo, min(hi, x))
        _vfx_director_warning(warnings, full_path, "clamped_out_of_range", actual=value, clamped=clamped, expected={"min": lo, "max": hi})
        return clamped
    return int(round(x)) if integer else x


def _vfx_director_validation_report(raw: Any, max_slots: int | None = None) -> dict[str, Any]:
    surface = vfx_director_surface()
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if not isinstance(raw, dict):
        _vfx_director_error(errors, "", "invalid_type", actual=type(raw).__name__, expected="object")
        return {"valid": False, "errors": errors, "warnings": warnings}

    allowed_top_fields = {"effectMagnitude", "visualBudgetClass", "identity", "slots"}
    for field in sorted(raw.keys()):
        if field not in allowed_top_fields:
            _vfx_director_error(errors, field, "forbidden_field", actual=raw.get(field), expected={"allowed": sorted(allowed_top_fields)})

    _vfx_director_check_number(errors, warnings, raw, "", "effectMagnitude", 0.0, 1.0)
    _vfx_director_check_enum(errors, raw, "", "visualBudgetClass", ["tiny", "small", "normal", "large", "signature"])

    raw_slots = raw.get("slots")
    if not isinstance(raw_slots, list):
        _vfx_director_error(errors, "slots", "invalid_type" if "slots" in raw else "missing_required", actual=raw_slots if "slots" in raw else None, expected="non-empty array")
        return {"valid": False, "errors": errors, "warnings": warnings}
    if not raw_slots:
        _vfx_director_error(errors, "slots", "missing_required", actual=[], expected="non-empty array")
        return {"valid": False, "errors": errors, "warnings": warnings}
    if max_slots is None:
        max_slots = max(2, min(8, VFX_LLM_DIRECTOR_MAX_SLOTS))
    if len(raw_slots) > max_slots:
        _vfx_director_error(errors, "slots", "out_of_range", actual=len(raw_slots), expected={"min": 1, "max": max_slots})

    numeric_ranges = surface.get("numericRanges", {}) if isinstance(surface.get("numericRanges"), dict) else {}
    enum_fields = {
        "event": surface["events"],
        "rendererKind": surface["rendererKind"],
        "backend": surface["backend"],
        "textureRole": surface["textureRole"],
        "particleRole": surface["particleRole"],
        "anchor": surface["anchor"],
        "channel": surface["channel"],
        "lane": surface["lane"],
        "emissionMode": surface["emissionMode"],
        "blend": surface["blend"],
        "particleSystemId": surface["particleSystemId"],
    }
    numeric_fields = {
        "scale": (0.15, 5.0, False, True),
        "density": (0.0, 1.0, False, True),
        "duration": (3, 120, True, True),
        "alpha": (0.0, 1.0, False, True),
        "spread": (0.0, 2.0, False, True),
        "jitter": (0.0, 1.5, False, True),
        "budgetWeight": (0.1, 4.0, False, True),
        "signatureWeight": (0.0, 1.0, False, True),
        "visualCost": (0.0, 1.0, False, True),
        "fadeIn": (0.0, 0.8, False, True),
        "fadeOut": (0.0, 0.8, False, True),
        "phaseOffset": (-1.0, 1.0, False, False),
        "startTick": (0, 120, True, False),
        "repeatEvery": (0, 120, True, False),
    }

    allowed_slot_fields = set(enum_fields.keys()) | set(numeric_fields.keys())
    for i, slot in enumerate(raw_slots[:max_slots]):
        path = f"slots[{i}]"
        if not isinstance(slot, dict):
            _vfx_director_error(errors, path, "invalid_type", actual=type(slot).__name__, expected="object")
            continue
        for field in sorted(slot.keys()):
            if field not in allowed_slot_fields:
                _vfx_director_error(errors, f"{path}.{field}", "forbidden_field", actual=slot.get(field), expected={"allowed": sorted(allowed_slot_fields)})

        normalized_enums: dict[str, str | None] = {}
        for field, allowed in enum_fields.items():
            normalized_enums[field] = _vfx_director_check_enum(errors, slot, path, field, allowed)
        for field, (lo, hi, integer, required) in numeric_fields.items():
            _vfx_director_check_number(errors, warnings, slot, path, field, lo, hi, integer=integer, required=required)

        channel = normalized_enums.get("channel")
        pid = normalized_enums.get("particleSystemId")
        
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def _vfx_director_repair_prompt(previous_json: Any, validation_report: dict[str, Any], vfx_surface: dict[str, Any]) -> dict[str, Any]:
    return {
        "task": "Repair the invalid VFX manifest fields only.",
        "instructions": [
            "Fix fields listed in VALIDATION_REPORT.",
            "Keep the effect design.",
            "No explanations or invented enums.",
            "Use VFX_SURFACE enums and ranges.",
            "Return the full corrected JSON object.",
        ],
        "PREVIOUS_JSON": previous_json,
        "VALIDATION_REPORT": validation_report,
        "VFX_SURFACE": vfx_surface,
    }


def _vfx_director_error_fields(report: dict[str, Any]) -> list[str]:
    return [str(e.get("path")) for e in report.get("errors", []) if isinstance(e, dict) and e.get("path")][:64]


def _vfx_particle_id_is_explicit(value: str | None) -> bool:
    return str(value or "").strip() in {"pl:glow", "pl:shard", "pl:smoke", "pl:spark", "dust"}


def _vfx_validate_director_output(raw: dict[str, Any], data: dict[str, Any], recipe_key_value: str, parent_a: dict[str, Any] | None = None, parent_b: dict[str, Any] | None = None) -> dict[str, Any] | None:
    report = _vfx_director_validation_report(raw)
    if not report.get("valid"):
        return None
    if not isinstance(raw, dict):
        return None
    surface = vfx_director_surface()
    raw_slots = raw.get("slots")
    if not isinstance(raw_slots, list) or not raw_slots:
        return None
    max_slots = max(2, min(8, VFX_LLM_DIRECTOR_MAX_SLOTS))
    raw_slots = [s for s in raw_slots if isinstance(s, dict)][:max_slots]
    if not raw_slots:
        return None

    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    pattern = normalize_attack_pattern(attack.get("pattern") or attack.get("attackPattern") or "basic")
    power = float(attack.get("powerBudget") or data.get("gameplay", {}).get("powerBudget") or 1.0) if isinstance(data.get("gameplay"), dict) else float(attack.get("powerBudget") or 1.0)
    seed = _vfx_seed_int(recipe_key_value, data.get("id"), "llm_vfx_director")
    if "effectMagnitude" not in raw:
        return None
    try:
        effect_magnitude = float(raw.get("effectMagnitude"))
    except Exception:
        return None
    if not math.isfinite(effect_magnitude) or effect_magnitude < 0.0 or effect_magnitude > 1.0:
        return None
    budget_class = str(raw.get("visualBudgetClass") or "").strip()
    if budget_class not in {"tiny", "small", "normal", "large", "signature"}:
        return None
    budget = _vfx_budget_for_recipe({"id": "llm_vfx_director", "cost": "medium"}, power, seed, data)
    budget["effectMagnitude"] = effect_magnitude
    budget["visualBudgetClass"] = budget_class

    compiled_raw: list[dict[str, Any]] = []
    explicit_particle_count = 0
    for i, slot in enumerate(raw_slots):
        if "bakedCommands" in slot:
            return None

        # Strict Director contract: if Gemma gives an invalid/missing enum or out-of-range numeric
        # field, reject the Director manifest and let the deterministic VFX pipeline take over.
        # We do not silently replace bad enum values with inferred defaults here.
        rk = _vfx_director_enum_required(slot, "rendererKind", surface["rendererKind"])
        if not rk and "renderer" in slot:
            # compatibility: accept renderer only when it is already a canonical rendererKind value.
            rk = _vfx_director_enum(slot.get("renderer"), surface["rendererKind"])
        ev = _vfx_director_enum_required(slot, "event", surface["events"])
        backend = _vfx_director_enum_required(slot, "backend", surface["backend"])
        texture_role = _vfx_director_enum_required(slot, "textureRole", surface["textureRole"])
        particle_role = _vfx_director_enum_required(slot, "particleRole", surface["particleRole"])
        anchor = _vfx_director_enum_required(slot, "anchor", surface["anchor"])
        channel = _vfx_director_enum_required(slot, "channel", surface["channel"])
        lane = _vfx_director_enum_required(slot, "lane", surface["lane"])
        emission_mode = _vfx_director_enum_required(slot, "emissionMode", surface["emissionMode"])
        blend = _vfx_director_enum_required(slot, "blend", surface["blend"])
        particle_system_id = _vfx_director_enum_required(slot, "particleSystemId", surface["particleSystemId"])
        if not all([rk, ev, backend, texture_role, particle_role, anchor, channel, lane, emission_mode, blend, particle_system_id]):
            return None

        scale = _vfx_director_number_required(slot, "scale", 0.15, 5.0)
        density = _vfx_director_number_required(slot, "density", 0.0, 1.0)
        duration = _vfx_director_number_required(slot, "duration", 3, 120, integer=True)
        alpha = _vfx_director_number_required(slot, "alpha", 0.0, 1.0)
        spread = _vfx_director_number_required(slot, "spread", 0.0, 2.0)
        jitter = _vfx_director_number_required(slot, "jitter", 0.0, 1.5)
        budget_weight = _vfx_director_number_required(slot, "budgetWeight", 0.1, 4.0)
        signature_weight = _vfx_director_number_required(slot, "signatureWeight", 0.0, 1.0)
        visual_cost = _vfx_director_number_required(slot, "visualCost", 0.0, 1.0)
        fade_in = _vfx_director_number_required(slot, "fadeIn", 0.0, 0.8)
        fade_out = _vfx_director_number_required(slot, "fadeOut", 0.0, 0.8)
        phase_offset = _vfx_director_number_required(slot, "phaseOffset", -1.0, 1.0) if "phaseOffset" in slot else 0.0
        if any(x is None for x in [scale, density, duration, alpha, spread, jitter, budget_weight, signature_weight, visual_cost, fade_in, fade_out, phase_offset]):
            return None

        # Director must make an explicit particle material choice.
        if _vfx_particle_id_is_explicit(particle_system_id):
            explicit_particle_count += 1

        compiled_raw.append({
            "event": ev,
            "renderer": rk,
            "rendererKind": rk,
            "backend": backend,
            "textureRole": texture_role,
            "particleRole": particle_role,
            "anchor": anchor,
            "channel": channel,
            "lane": lane,
            "emissionMode": emission_mode,
            "blend": blend,
            "particleSystemId": particle_system_id,
            "scale": scale,
            "density": density,
            "duration": duration,
            "alpha": alpha,
            "spread": spread,
            "jitter": jitter,
            "phaseOffset": phase_offset,
            "budgetWeight": budget_weight,
            "signatureWeight": signature_weight,
            "visualCost": visual_cost,
            "fadeIn": fade_in,
            "fadeOut": fade_out,
            "source": "llmDirector",
        })

    slots = [_vfx_compile_slot(slot, seed, i, power, effect_magnitude) for i, slot in enumerate(compiled_raw)]
    slots = _vfx_arbitrate_slots(slots, budget_class)
    if not slots:
        return None
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    kit = data.get("visualKit") if isinstance(data.get("visualKit"), dict) else {}
    words = _vfx_words(" ".join(str(x or "") for x in [data.get("name"), data.get("tooltip"), raw.get("identity"), kit.get("styleGuide"), visual.get("styleGuide"), attack.get("toyIdentity"), attack.get("projectileTrail"), attack.get("projectileImpact")]))
    provenance = attack.get("runtimeAuthoringProvenance") if isinstance(attack.get("runtimeAuthoringProvenance"), dict) else {}
    effect_lineage = {
        "mode": "llm_vfx_director",
        "gameplayChildren": provenance.get("gameplayChildren", {}),
        "pureVfx": provenance.get("pureVfx", {}),
        "fieldSources": provenance.get("fieldSources", {}),
        "note": "VFX slots are visual execution of authored VFX intent; real damaging children are only those reported under gameplayChildren.",
    }
    manifest = {
        "schema": "infini.vfx.hybrid.v14",
        "recipeId": "llm_vfx_director",
        "playbackMode": "Hybrid",
        "seed": seed,
        "confidence": 0.84,
        "effectMagnitude": effect_magnitude,
        "visualBudgetClass": budget_class,
        "motif": _vfx_motif_from_data(data, words, pattern),
        "parentEffectProfile": {k: v for k, v in _vfx_parent_effect_profile(data, parent_a, parent_b).items() if k != "_rawParentSlots"},
        "overlayPolicy": "LocalOnly",
        "budget": budget,
        "slots": slots,
        "debug": {
            "composition": {
                "mode": "llm_vfx_director",
                "identity": str(raw.get("identity") or "")[:240],
                "preArbitrationSlotCount": len(compiled_raw),
                "postArbitrationSlotCount": len(slots),
                "explicitParticleSystemSlots": explicit_particle_count,
                "directorEnumMode": "strict",
                "blendedSlots": [],
                "proceduralSlots": [],
            },
            "pattern": pattern,
            "roles": sorted(_vfx_available_roles(data)),
            "selectedReasons": ["llm_director_validated", "fallback_pipeline_available_if_invalid"],
            "topCandidates": [],
            "wordProbe": sorted(list(words))[:40] if VFX_SELECTOR_DEBUG else [],
        }
    }
    return manifest


def try_llm_vfx_director(parent_a: dict[str, Any] | None, parent_b: dict[str, Any] | None, child_item: dict[str, Any], recipe_key_value: str, llm_client: Any = None) -> dict[str, Any] | None:
    """Optional Gemma E4B VFX Director pass.

    Primary mode is continuation of the original item-generation chat: because
    OpenAI-compatible APIs are stateless, server.py stores the original planner
    messages in the child item and this function explicitly resends them.
    If that hidden continuation data is absent/invalid, we fall back to the old
    standalone director request; if that fails too, the old procedural VFX pipeline runs.
    """
    if not VFX_LLM_DIRECTOR_ENABLED or llm_client is None:
        return None
    constraints = {
        "attackPattern": (child_item.get("attack") or {}).get("pattern") if isinstance(child_item.get("attack"), dict) else "basic",
        "noBakedCommands": True,
        "slots": [2, max(2, VFX_LLM_DIRECTOR_MAX_SLOTS)],
    }
    surface = vfx_director_surface()
    system = (
        "You are a VFX director for a Terraria/tModLoader generated item. "
        "Return ONLY one JSON object. No markdown. No reasoning. "
        "Use only the listed VFX surface enums and ranges. Author concrete slot parameters; do not invent code names. "
        "Do not output prose explanations or keys outside the provided JSON contract."
    )
    debug = child_item.setdefault("debug", {})
    try:
        input_packet = build_vfx_director_prompt(parent_a, parent_b, child_item, surface, constraints).get("vfxInputPacket", {})
        weak_hints = input_packet.get("weakHints") if isinstance(input_packet, dict) else []
        if not isinstance(weak_hints, list):
            weak_hints = []
        debug["vfxLlmDirectorInputPacket"] = json.dumps(input_packet, ensure_ascii=False)[:12000]
        debug["vfxWeakHintsEnabled"] = bool(VFX_LLM_WEAK_HINTS_ENABLED)
        debug["vfxWeakHintsCount"] = len(weak_hints)
        debug["vfxWeakHints"] = json.dumps(weak_hints, ensure_ascii=False)[:4000]
    except Exception:
        debug["vfxWeakHintsEnabled"] = bool(VFX_LLM_WEAK_HINTS_ENABLED)
        debug["vfxWeakHintsCount"] = 0
        pass

    def validate_or_repair(raw: Any, mode: str, base_messages: list[dict[str, str]] | None = None) -> dict[str, Any] | None:
        def _reason_key() -> str:
            if mode == "planner_chat_continuation":
                return "vfxLlmDirectorContinuationFallbackReason"
            if mode == "standalone_fallback":
                return "vfxLlmDirectorStandaloneFallbackReason"
            return "vfxLlmDirectorUnknownModeFallbackReason"

        def _set_mode_fallback(reason: str) -> None:
            debug[_reason_key()] = reason
            debug["vfxLlmDirectorLastFallbackReason"] = reason

        report = _vfx_director_validation_report(raw)
        debug["vfxLlmDirectorValidationErrorCount"] = len(report.get("errors", []))
        debug["vfxLlmDirectorValidationFields"] = _vfx_director_error_fields(report)
        debug["vfxLlmDirectorRepairAttempts"] = 0
        debug["vfxLlmDirectorRepairEnabled"] = max(0, VFX_LLM_DIRECTOR_REPAIR_ATTEMPTS)
        if report.get("valid"):
            manifest = _vfx_validate_director_output(raw, child_item, recipe_key_value, parent_a, parent_b)
            if isinstance(manifest, dict) and manifest.get("slots"):
                comp = manifest.setdefault("debug", {}).setdefault("composition", {})
                comp["repairAttempted"] = False
                comp["validationErrorCountBeforeRepair"] = 0
                comp["weakHintsEnabled"] = bool(VFX_LLM_WEAK_HINTS_ENABLED)
                comp["weakHintsCount"] = int(debug.get("vfxWeakHintsCount") or 0)
                comp["weakHints"] = json.loads(debug.get("vfxWeakHints") or "[]") if isinstance(debug.get("vfxWeakHints"), str) else []
                comp["vfxPath"] = "llm_director"
                return manifest
            _set_mode_fallback("valid_contract_but_compile_failed")
            return None

        if VFX_LLM_DIRECTOR_REPAIR_ATTEMPTS <= 0:
            _set_mode_fallback("invalid_director_output_repair_disabled")
            debug["vfxLlmDirectorValidationReport"] = json.dumps(report, ensure_ascii=False)[:6000]
            return None

        repair_raw: Any = raw
        last_report = report
        for attempt in range(1, max(0, VFX_LLM_DIRECTOR_REPAIR_ATTEMPTS) + 1):
            debug["vfxLlmDirectorRepairAttempts"] = attempt
            debug["vfxLlmDirectorRepairFields"] = _vfx_director_error_fields(last_report)
            repair_payload = _vfx_director_repair_prompt(repair_raw, last_report, surface)
            if base_messages:
                repair_messages = list(base_messages) + [
                    {"role": "assistant", "content": json.dumps(repair_raw, ensure_ascii=False, separators=(",", ":"))},
                    {"role": "user", "content": json.dumps(repair_payload, ensure_ascii=False, separators=(",", ":"))},
                ]
                repair_raw = llm_client("", {}, VFX_LLM_DIRECTOR_MAX_TOKENS, VFX_LLM_DIRECTOR_TEMPERATURE, VFX_LLM_DIRECTOR_TIMEOUT, messages=repair_messages)
            else:
                repair_raw = llm_client(system, repair_payload, VFX_LLM_DIRECTOR_MAX_TOKENS, VFX_LLM_DIRECTOR_TEMPERATURE, VFX_LLM_DIRECTOR_TIMEOUT)
            last_report = _vfx_director_validation_report(repair_raw)
            debug["vfxLlmDirectorRepairLastErrorCount"] = len(last_report.get("errors", []))
            debug["vfxLlmDirectorRepairLastFields"] = _vfx_director_error_fields(last_report)
            if last_report.get("valid"):
                manifest = _vfx_validate_director_output(repair_raw, child_item, recipe_key_value, parent_a, parent_b)
                if isinstance(manifest, dict) and manifest.get("slots"):
                    comp = manifest.setdefault("debug", {}).setdefault("composition", {})
                    comp["repairAttempted"] = True
                    comp["repairAttempts"] = attempt
                    comp["validationErrorCountBeforeRepair"] = len(report.get("errors", []))
                    comp["repairedFields"] = _vfx_director_error_fields(report)
                    comp["weakHintsEnabled"] = bool(VFX_LLM_WEAK_HINTS_ENABLED)
                    comp["weakHintsCount"] = int(debug.get("vfxWeakHintsCount") or 0)
                    comp["weakHints"] = json.loads(debug.get("vfxWeakHints") or "[]") if isinstance(debug.get("vfxWeakHints"), str) else []
                    comp["vfxPath"] = "llm_director"
                    debug["vfxLlmDirectorRepairStatus"] = "success"
                    return manifest
                _set_mode_fallback("repair_valid_contract_but_compile_failed")
                return None

        debug["vfxLlmDirectorRepairStatus"] = "failed"
        _set_mode_fallback("invalid_after_repair")
        debug["vfxLlmDirectorValidationReport"] = json.dumps(last_report, ensure_ascii=False)[:6000]
        return None

    try:
        messages = build_vfx_director_continuation_messages(child_item, parent_a, parent_b, surface, constraints)
        if messages:
            raw = llm_client("", {}, VFX_LLM_DIRECTOR_MAX_TOKENS, VFX_LLM_DIRECTOR_TEMPERATURE, VFX_LLM_DIRECTOR_TIMEOUT, messages=messages)
            manifest = validate_or_repair(raw, "planner_chat_continuation", base_messages=messages)
            if isinstance(manifest, dict) and manifest.get("slots"):
                debug["vfxLlmDirectorMode"] = "planner_chat_continuation"
                debug["vfxLlmDirectorContinuationMessages"] = len(messages)
                debug["vfxPath"] = "llm_director"
                return manifest
            debug["vfxLlmDirectorContinuationFallback"] = debug.get("vfxLlmDirectorContinuationFallbackReason") or "invalid_or_empty_output"
        else:
            debug["vfxLlmDirectorContinuationFallbackReason"] = "missing_planner_chat_history"
            debug["vfxLlmDirectorContinuationFallback"] = "missing_planner_chat_history"

        # Legacy fallback: standalone VFX director prompt with compact parent/child cards.
        payload = build_vfx_director_prompt(parent_a, parent_b, child_item, surface, constraints)
        raw = llm_client(system, payload, VFX_LLM_DIRECTOR_MAX_TOKENS, VFX_LLM_DIRECTOR_TEMPERATURE, VFX_LLM_DIRECTOR_TIMEOUT)
        manifest = validate_or_repair(raw, "standalone_fallback", base_messages=None)
        if isinstance(manifest, dict) and manifest.get("slots"):
            debug["vfxLlmDirectorMode"] = "standalone_fallback"
            debug["vfxPath"] = "llm_director"
            return manifest
        final_reason = debug.get("vfxLlmDirectorStandaloneFallbackReason") or "standalone_invalid_or_empty_output"
        debug["vfxLlmDirectorStandaloneFallbackReason"] = final_reason
        debug["vfxLlmDirectorFinalFallbackReason"] = final_reason
        debug["vfxLlmDirectorFallbackReason"] = final_reason
        debug["vfxPath"] = "legacy_recipe_fallback"
        return None
    except Exception as e:
        debug["vfxLlmDirectorError"] = repr(e)
        debug["vfxLlmDirectorFinalFallbackReason"] = "exception"
        debug["vfxLlmDirectorFallbackReason"] = "exception"
        debug["vfxPath"] = "legacy_recipe_fallback"
        return None


# =============================================================================
# NAV: VFX_MANIFEST_PIPELINE
# =============================================================================
def _vfx_seed_int(*parts: Any) -> int:
    return int(stable_hash(*parts, length=12), 16) & 0x7fffffff


def _vfx_unit(seed: int, salt: str) -> float:
    return (_vfx_seed_int(seed, salt) % 100000) / 99999.0


def _vfx_pick(seed: int, salt: str, values: list[Any], fallback: Any = 0) -> Any:
    if not values:
        return fallback
    return values[_vfx_seed_int(seed, salt) % len(values)]


def _vfx_lerp_range(seed: int, salt: str, value: Any, fallback: float) -> float:
    if isinstance(value, list) and len(value) >= 2:
        try:
            lo = float(value[0]); hi = float(value[1])
            if hi < lo:
                lo, hi = hi, lo
            return lo + (hi - lo) * _vfx_unit(seed, salt)
        except Exception:
            return fallback
    try:
        return float(value)
    except Exception:
        return fallback


def _vfx_default_importance(event: Any, renderer: Any = "") -> str:
    e = str(event or "").lower()
    r = str(renderer or "").lower()
    if e in {"hit", "impact", "onhit"} or "impact" in r or "flash" in r:
        return "core"
    if "afterimage" in r or "trail" in r or "ribbon" in r or "beam" in r or "field" in r:
        return "secondary"
    if "ambient" in r or "mote" in r or "smoke" in r or "sound" in r or "light" in r:
        return "accent"
    if "actor" in r or "orbital" in r:
        return "luxury"
    return "secondary"


def _vfx_default_visual_cost(renderer: Any, density: float = 0.35) -> float:
    r = str(renderer or "").lower()
    base = 0.18
    if "impact" in r or "burst" in r or "ring" in r:
        base = 0.42
    if "ribbon" in r or "history" in r or "trail" in r:
        base = 0.34
    if "ambient" in r or "mote" in r or "smoke" in r:
        base = 0.28
    if "actor" in r or "orbital" in r or "field" in r:
        base = 0.58
    if "beam" in r:
        base = 0.46
    try:
        return max(0.0, min(1.0, base + float(density or 0) * 0.28))
    except Exception:
        return base


def _vfx_default_signature_weight(event: Any, renderer: Any = "") -> float:
    e = str(event or "").lower()
    r = str(renderer or "").lower()
    if e in {"hit", "impact", "onhit"} or "impact" in r or "ring" in r:
        return 0.72
    if "ribbon" in r or "beam" in r or "field" in r:
        return 0.58
    if "actor" in r or "orbital" in r:
        return 0.52
    if "ambient" in r or "mote" in r or "smoke" in r:
        return 0.30
    return 0.45


def _vfx_event_stage(event: Any, renderer: Any = "") -> str:
    e = str(event or "").lower()
    r = str(renderer or "").lower()
    if e in {"hit", "impact", "onhit"}:
        return "impact"
    if e in {"kill", "expire", "decay"}:
        return "decay"
    if e in {"active", "slash", "beam"} or "tip" in r or "ribbon" in r or "ghost" in r:
        return "active"
    if e in {"spawn", "windup"}:
        return "windup"
    return "loop"


def _vfx_default_backend(event: Any, renderer: Any = "") -> str:
    e = str(event or "").lower()
    r = str(renderer or "").lower()
    if "beam" in r or "ribbon" in r or "tip" in r:
        return "Primitive"
    if "afterimage" in r or "stamp" in r or "ghost" in r or "field" in r or "flash" in r or "ring" in r:
        return "Sprite"
    if e in {"hit", "impact", "onhit", "kill", "expire", "decay"}:
        return "Baked"
    if "mote" in r or "spark" in r or "smoke" in r or "ambient" in r:
        return "Realtime"
    return "Auto"


def _vfx_default_anchor(event: Any, renderer: Any = "") -> str:
    e = str(event or "").lower()
    r = str(renderer or "").lower()
    if e in {"hit", "impact", "onhit"}:
        return "hitPoint"
    if "tip" in r or "ribbon" in r or "slash" in r:
        return "tipHistory"
    if "beam" in r:
        return "velocity"
    if "field" in r:
        return "field"
    return "self"



def _vfx_infer_channel(renderer: Any, event: Any = "") -> str:
    r = str(renderer or "").lower()
    e = str(event or "").lower()
    if "sound" in r:
        return "sound"
    if "light" in r:
        return "light"
    if e in {"hit", "impact", "onhit"}:
        if any(w in r for w in ("mote", "spark", "shard", "smoke", "particle")):
            return "impactParticles"
        return "impactShape"
    if e in {"kill", "expire", "decay"}:
        return "impactShape" if any(w in r for w in ("ring", "flash", "impact", "burst")) else "decaySmoke"
    if any(w in r for w in ("afterimage", "tiptrail", "ribbon", "stamp", "ghost", "trail", "history", "primitive")):
        return "motionTrail"
    if any(w in r for w in ("field", "orbital", "aura", "glow")):
        return "coreGlow"
    if any(w in r for w in ("ambient", "mote", "smoke", "spark")):
        return "ambientParticles"
    return "motionTrail"


def _vfx_infer_emission_mode(renderer: Any, event: Any = "") -> str:
    r = str(renderer or "").lower()
    e = str(event or "").lower()
    if "orbit" in r or "orbital" in r:
        return "orbit"
    if e in {"hit", "impact", "onhit"}:
        return "ring" if "ring" in r else "burst"
    if e in {"kill", "expire", "decay"}:
        return "residue"
    if "beam" in r or "trail" in r or "wake" in r:
        return "wake"
    return "wake"


def _vfx_infer_lane(slot: dict[str, Any]) -> str:
    lane = str(slot.get("lane") or "auto").strip().lower()
    if lane in {"primary", "support", "accent", "ornament", "cue"}:
        return lane
    imp = str(slot.get("importance") or "").strip().lower()
    channel = str(slot.get("channel") or _vfx_infer_channel(slot.get("renderer"), slot.get("event")))
    renderer = str(slot.get("renderer") or "").lower()
    if channel in {"light", "sound"} or "light" in renderer or "sound" in renderer:
        return "cue"
    if imp == "core":
        return "primary"
    if imp == "secondary":
        return "support"
    if imp == "luxury":
        return "ornament"
    if imp == "accent":
        return "accent"
    if "ring" in renderer or "flash" in renderer:
        return "support"
    if "mote" in renderer or "spark" in renderer or "smoke" in renderer:
        return "accent"
    return "primary"


def _vfx_renderer_family(renderer: Any) -> str:
    r = str(renderer or "").lower()
    for key in ("afterimage", "tiptrail", "history", "ribbon", "stamp", "ghost", "wavy", "cloth", "beam", "field", "orbit", "ring", "flash", "burst", "mote", "light", "sound", "smoke"):
        if key in r:
            return key
    return r[:24] or "generic"


def _vfx_renderer_kind(renderer: Any) -> str:
    """Canonical renderer id for runtime dispatch. Fuzzy matching stays in Python/generator;
    generated manifests should not force C# to classify renderer strings again.
    """
    r = str(renderer or "").strip().lower().replace("_", "").replace("-", "")
    if not r:
        return "none"
    if "sound" in r:
        return "soundCue"
    if "light" in r:
        return "lightCue"
    if "afterimage" in r:
        return "projectileAfterimage"
    if "stamp" in r:
        return "spriteStampTrail"
    if "tiptrail" in r:
        return "tipTrail"
    if "history" in r or "primitive" in r or "ribbon" in r:
        return "historyRibbon"
    if "ghost" in r:
        return "ghostArc"
    if "wavy" in r or "cloth" in r:
        return "wavyStrip"
    if "beam" in r:
        return "beamLine"
    if "field" in r:
        return "fieldPulse"
    if "orbital" in r or "orbit" in r:
        return "orbitingMotes"
    if "actor" in r or "playerghost" in r:
        return "actorAfterimage"
    if "ring" in r:
        return "impactRing"
    if "child" in r or "mote" in r:
        return "childMotes"
    if "flash" in r or "burst" in r or "impact" in r:
        return "impactSprite"
    return "none"


def _vfx_event_group(event: Any) -> str:
    e = str(event or "").lower()
    if e in {"hit", "impact", "onhit"}:
        return "hit"
    if e in {"kill", "expire", "decay"}:
        return "kill"
    return "live"


def _vfx_score_number(value: Any, fallback: float = 0.0) -> float:
    try:
        if isinstance(value, list):
            vals = [float(x) for x in value[:2]]
            return sum(vals) / max(1, len(vals))
        return float(value)
    except Exception:
        return fallback


def _vfx_slot_score(slot: dict[str, Any]) -> float:
    imp = str(slot.get("importance") or "secondary").lower()
    score = {"core": 100.0, "secondary": 50.0, "accent": 20.0, "luxury": 5.0}.get(imp, 25.0)
    score += _vfx_score_number(slot.get("signatureWeight"), 0.0) * 20.0
    score -= _vfx_score_number(slot.get("visualCost"), 0.0) * 10.0
    score += _vfx_score_number(slot.get("density"), 0.0) * 3.0
    if str(slot.get("source") or "").lower() == "authoredcue":
        # Explicit model-authored VFX cues should survive recipe/background slots when
        # they compete for the same visual lane. This is still visual-only: it does
        # not bypass slot caps, gameplay validation, or renderer sanitization.
        score += 40.0
    if slot.get("channel") in {"light", "sound"}:
        score += 8.0
    return score


def _vfx_max_channel_count(group: str, channel: str, magnitude_class: str) -> int:
    if channel in {"light", "sound"}:
        return 1
    large = magnitude_class in {"large", "signature"}
    signature = magnitude_class == "signature"
    if group == "live" and channel == "motionTrail":
        return 3 if signature else (2 if large else 1)
    if group == "live" and channel == "coreGlow":
        return 2 if signature else 1
    if group == "live" and channel == "ambientParticles":
        return 2 if large else 1
    if group == "hit" and channel == "impactShape":
        return 3 if signature else (2 if large else 1)
    if group == "hit" and channel == "impactParticles":
        return 2 if large else 1
    if group == "kill" and channel in {"decaySmoke", "impactShape"}:
        return 3 if signature else 2
    return 1


def _vfx_arbitrate_slots(slots: list[dict[str, Any]], magnitude_class: str) -> list[dict[str, Any]]:
    """Scene composer: allow Calamity-like layered slots, but only across distinct lanes.

    Old v0.3.29 logic was intentionally anti-kasha: one main slot per visual channel.
    That was too strict for references like Terratomere, where a crescent, light streak,
    motes and impact flash coexist. v0.3.30 keeps channel caps, but separates lanes:
    primary/support/accent/ornament/cue.
    """
    selected: dict[tuple[str, str, str], dict[str, Any]] = {}
    channel_counts: dict[tuple[str, str], int] = {}
    used_families: set[tuple[str, str, str]] = set()

    for slot in sorted([x for x in slots if isinstance(x, dict)], key=_vfx_slot_score, reverse=True):
        group = _vfx_event_group(slot.get("event"))
        channel = str(slot.get("channel") or _vfx_infer_channel(slot.get("renderer"), slot.get("event")))
        lane = _vfx_infer_lane(slot)
        family = _vfx_renderer_family(slot.get("renderer"))
        lane_key = (group, channel, lane)
        channel_key = (group, channel)
        fam_key = (group, channel, family)

        if fam_key in used_families and channel not in {"light", "sound"}:
            continue

        max_count = _vfx_max_channel_count(group, channel, magnitude_class)
        current = channel_counts.get(channel_key, 0)

        if lane_key not in selected:
            if current >= max_count:
                # Replace weakest non-primary lane in this channel only if the new slot is better.
                candidates = [(k, v) for k, v in selected.items() if k[0] == group and k[1] == channel]
                if not candidates:
                    continue
                def replace_score(pair: tuple[tuple[str, str, str], dict[str, Any]]) -> float:
                    k, v = pair
                    score = _vfx_slot_score(v)
                    if k[2] == "primary":
                        score += 25.0
                    return score
                weakest_key, weakest = min(candidates, key=replace_score)
                if _vfx_slot_score(slot) <= _vfx_slot_score(weakest):
                    continue
                selected.pop(weakest_key, None)
                current -= 1
            selected[lane_key] = slot | {"lane": lane, "channel": channel}
            channel_counts[channel_key] = current + 1
            used_families.add(fam_key)
            continue

        if _vfx_slot_score(slot) > _vfx_slot_score(selected[lane_key]):
            selected[lane_key] = slot | {"lane": lane, "channel": channel}
            used_families.add(fam_key)

    out = list(selected.values())
    out.sort(key=_vfx_slot_score, reverse=True)
    return out


def _vfx_motif_from_data(data: dict[str, Any], words: set[str], pattern: str) -> dict[str, Any]:
    element = "neutral"
    probes = [
        ("fire", {"fire", "flame", "ember", "burn"}),
        ("frost", {"ice", "frost", "snow", "crystal"}),
        ("shadow", {"shadow", "void", "dark", "curse", "ghost", "soul"}),
        ("toxic", {"toxic", "poison", "acid", "slime", "goo"}),
        ("blood", {"blood", "red", "flesh"}),
        ("holy", {"holy", "light", "gold", "star", "solar"}),
        ("metal", {"metal", "iron", "steel", "coin", "gear"}),
    ]
    for name, ws in probes:
        if words & ws:
            element = name
            break
    shape = "beam" if "beam" in pattern or "laser" in pattern else "field" if "field" in pattern else "slash" if "slash" in pattern else "shard"
    if words & {"ring", "circle", "rune"}:
        shape = "ring"
    elif words & {"smoke", "cloud", "mist"}:
        shape = "smoke"
    motion = "orbit" if "orbit" in pattern or "orbit" in words else "pulse" if "field" in pattern else "forward"
    rhythm = 1.35 if words & {"snappy", "quick", "fast"} else 0.75 if words & {"slow", "delayed"} else 1.0
    chaos = 0.6 if words & {"chaotic", "ragged", "broken", "frayed", "wild"} else 0.25
    return {"element": element, "shapeLanguage": shape, "motionLanguage": motion, "paletteRole": "primary", "rhythm": round(rhythm, 2), "chaos": round(chaos, 2)}

def _vfx_magnitude_class(value: float) -> str:
    v = max(0.0, min(1.0, float(value or 0.0)))
    if v < 0.22:
        return "tiny"
    if v < 0.42:
        return "small"
    if v < 0.66:
        return "normal"
    if v < 0.86:
        return "large"
    return "signature"


def _vfx_compute_effect_magnitude(recipe: dict[str, Any], power: float, seed: int | str | None = None, data: dict[str, Any] | None = None) -> float:
    """Item-driven VFX magnitude.

    v0.3.26 deliberately separates item effect magnitude from render quality.
    Terraria does not need Low/Medium/High/Ultra as an art axis; magnitude is
    derived from item power/recipe cost/novelty-ish debug hints plus stable seed.
    """
    cost = str(recipe.get("cost") or "medium").lower()
    cost_bias = {"tiny": -0.18, "low": -0.12, "medium": 0.0, "normal": 0.0, "high": 0.13, "signature": 0.24, "ultra": 0.30}.get(cost, 0.0)
    try:
        pwr = float(power or 1.0)
    except Exception:
        pwr = 1.0
    # powerBudget in this project is not a Terraria damage number; keep it soft and capped.
    power_bias = max(-0.16, min(0.28, (pwr - 1.0) * 0.18))
    debug = (data or {}).get("debug") if isinstance((data or {}).get("debug"), dict) else {}
    gameplay = (data or {}).get("gameplay") if isinstance((data or {}).get("gameplay"), dict) else {}
    novelty_raw = debug.get("novelty") or debug.get("noveltyScore") or gameplay.get("novelty") or gameplay.get("noveltyScore") or 0.0
    try:
        novelty_bias = max(0.0, min(0.14, float(novelty_raw) * 0.08))
    except Exception:
        novelty_bias = 0.0
    slot_count = len(recipe.get("slots") or [])
    structural_bias = max(-0.06, min(0.12, (slot_count - 2) * 0.018))
    stable_seed = _vfx_seed_int(seed or "magnitude", recipe.get("id"), pwr, cost)
    jitter = (_vfx_unit(stable_seed, "mag") - 0.5) * max(0.0, VFX_MAGNITUDE_JITTER)
    value = 0.48 + cost_bias + power_bias + novelty_bias + structural_bias + jitter
    mundane = _vfx_mundane_duplicate_profile(data or {}, power=pwr)
    if mundane.get("enabled"):
        value = min(value - 0.18, 0.34)
    return round(max(0.08, min(1.0, value)), 3)


def _vfx_budget_for_recipe(recipe: dict[str, Any], power: float, seed: int | str | None = None, data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Emergency budget, not a graphics-quality preset.

    Render quality is always Full. Budget numbers are emergency caps and are scaled
    by effectMagnitude so weak items do not get signature-sized particle spam while
    rare/high-power items can still look large.
    """
    magnitude = _vfx_compute_effect_magnitude(recipe, power, seed, data)
    budget_class = _vfx_magnitude_class(magnitude)
    # v0.3.26: these are true emergency ceilings, not art-direction sliders.
    # Do not shrink the cap for weak/common items: recipe selection, slot density,
    # effectMagnitude and baked tape size already define how "large" the VFX is.
    # The cap only catches runaway manifests or pathological recipe combinations.
    spawn_mult = round(max(0.35, min(3.25, 0.60 + magnitude * 1.85)), 3)
    budget = {
        "renderQuality": VFX_RENDER_QUALITY,
        "quality": VFX_RENDER_QUALITY,  # compat: old C# reads Budget.Quality, but runtime no longer gates by it.
        "effectMagnitude": magnitude,
        "visualBudgetClass": budget_class,
        "emergencyCap": True,
        "maxParticlesPerTick": max(0, VFX_EMERGENCY_MAX_PARTICLES_PER_TICK),
        "maxParticlesTotal": max(0, VFX_EMERGENCY_MAX_PARTICLES_TOTAL),
        "maxDrawCalls": max(0, VFX_EMERGENCY_MAX_DRAW_CALLS),
        "spawnRateMultiplier": spawn_mult,
        "enableSoftGlow": True,
        "enablePointSparks": True,
        "enablePersistentSmoke": True,
    }
    return budget

def _vfx_playback_mode_for_recipe(recipe: dict[str, Any]) -> str:
    explicit = str(recipe.get("playbackMode") or recipe.get("preferredMode") or "").strip()
    if explicit:
        return explicit
    slots = recipe.get("slots") if isinstance(recipe.get("slots"), list) else []
    backends = {str(x.get("backend") or _vfx_default_backend(x.get("event"), x.get("renderer"))).lower() for x in slots if isinstance(x, dict)}
    if "baked" in backends and ("realtime" in backends or "primitive" in backends or "sprite" in backends):
        return "Hybrid"
    if "baked" in backends:
        return "Baked"
    if "realtime" in backends or "primitive" in backends:
        return "Realtime"
    return "Auto"


def _vfx_words(text: str) -> set[str]:
    return {w for w in re.split(r"[^a-zA-Zа-яА-ЯёЁ0-9]+", (text or "").lower()) if len(w) >= 3}




def _vfx_deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Tiny JSON-object merge for slot macros. Dict values merge; other values override."""
    out = dict(base or {})
    for key, value in (override or {}).items():
        if key == "macro":
            continue
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _vfx_deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _vfx_expand_slot_macro(slot: Any, recipe_id: str = "") -> dict[str, Any] | None:
    """Expand one slot. Supports {"macro": "name", ...overrides} and plain slot dicts.

    This intentionally keeps macro expansion in Python/generation time, not in C# runtime.
    The final vfxManifest remains frozen and contains only compiled concrete slots.
    """
    if isinstance(slot, str):
        slot = {"macro": slot}
    if not isinstance(slot, dict):
        return None
    macro_id = str(slot.get("macro") or "").strip()
    if not macro_id:
        return dict(slot)
    macro = VFX_SLOT_MACROS.get(macro_id)
    if not isinstance(macro, dict):
        # Keep a harmless debug-ish slot out; linter will report the missing macro through recipe expansion reports.
        return {k: v for k, v in slot.items() if k != "macro"}
    expanded = _vfx_deep_merge(macro, slot)
    expanded["macroId"] = macro_id
    return expanded


def _vfx_expand_recipe_macros(recipe: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of recipe with useMacros/macro slots expanded into concrete slots."""
    if not isinstance(recipe, dict):
        return {}
    out = dict(recipe)
    slots: list[dict[str, Any]] = []
    for macro_ref in recipe.get("useMacros") or []:
        expanded = _vfx_expand_slot_macro(macro_ref, str(recipe.get("id") or ""))
        if expanded:
            slots.append(expanded)
    for raw in recipe.get("slots") or []:
        expanded = _vfx_expand_slot_macro(raw, str(recipe.get("id") or ""))
        if expanded:
            slots.append(expanded)
    out["slots"] = slots
    out["expandedFromMacros"] = bool(recipe.get("useMacros") or any(isinstance(x, dict) and x.get("macro") for x in (recipe.get("slots") or [])))
    return out


def get_vfx_recipes(expand_macros: bool = True) -> list[dict[str, Any]]:
    global _VFX_EXPANDED_RECIPE_CACHE
    if not expand_macros:
        return VFX_MORPH_RECIPES_RAW
    if _VFX_EXPANDED_RECIPE_CACHE is None:
        _VFX_EXPANDED_RECIPE_CACHE = [_vfx_expand_recipe_macros(r) for r in VFX_MORPH_RECIPES_RAW]
    return _VFX_EXPANDED_RECIPE_CACHE


def compact_vfx_macro_card(macro_id: str, macro: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": macro_id,
        "event": macro.get("event", ""),
        "stage": macro.get("stage", ""),
        "backend": macro.get("backend", ""),
        "renderer": macro.get("renderer", ""),
        "textureRole": macro.get("textureRole", ""),
        "particleRole": macro.get("particleRole", ""),
        "scale": macro.get("scale"),
        "density": macro.get("density"),
        "duration": macro.get("duration"),
        "variants": macro.get("variants", []),
    }

def _vfx_available_roles(data: dict[str, Any]) -> set[str]:
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    roles: set[str] = set()
    if attack.get("projectileSpritePath") or attack.get("projectileSpritePrompt") or visual.get("projectileImagePrompt"):
        roles.add("projectile")
    if attack.get("impactSpritePath") or attack.get("impactSpritePrompt") or visual.get("impactImagePrompt"):
        roles.add("impact")
    if attack.get("childSpritePath") or attack.get("childSpritePrompt") or visual.get("childImagePrompt"):
        roles.add("child")
    if attack.get("fieldSpritePath") or attack.get("fieldSpritePrompt") or visual.get("fieldImagePrompt"):
        roles.add("field")
    return roles



def _vfx_manifest_from_parent_item(item: dict[str, Any]) -> dict[str, Any]:
    """Best-effort extraction of a frozen VFX manifest from a generated parent item.

    Parent manifests are data, not live logic. We only read their public slots/motif/magnitude and
    transform them into small support/accent layers for the child result.
    """
    if not isinstance(item, dict):
        return {}
    direct = item.get("vfxManifest") or item.get("VfxManifest")
    if isinstance(direct, dict):
        return direct
    attack = item.get("attack") if isinstance(item.get("attack"), dict) else item.get("Attack") if isinstance(item.get("Attack"), dict) else {}
    raw = ""
    if isinstance(attack, dict):
        raw = str(attack.get("vfxManifestJson") or attack.get("VfxManifestJson") or "")
    if not raw and isinstance(item.get("debug"), dict):
        raw = str(item["debug"].get("vfxManifest") or "")
    if raw.strip().startswith("{"):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _vfx_parent_profile_from_item(item: dict[str, Any], index: int = 0) -> dict[str, Any]:
    name = name_of(item)
    tags = set(tags_of(item))
    try:
        rarity = int(float(item_field(item, "rare", item_field(item, "rarity", 0)) or 0))
    except Exception:
        rarity = 0
    try:
        damage = float(item_num(item, "damage", 0))
    except Exception:
        damage = 0.0
    try:
        use_time = float(item_num(item, "useTime", item_num(item, "useAnimation", 30)))
    except Exception:
        use_time = 30.0
    prof: dict[str, Any] = {}
    try:
        prof = source_weapon_profile(item)
    except Exception:
        prof = {}
    projectile = prof.get("projectileProfile") if isinstance(prof.get("projectileProfile"), dict) else effective_projectile_profile_of(item)
    behavior = set(str(x) for x in (prof.get("behaviorTags") or projectile_behavior_tags(item)) if str(x))
    manifest = _vfx_manifest_from_parent_item(item)
    manifest_slots = [x for x in (manifest.get("slots") or []) if isinstance(x, dict)] if isinstance(manifest, dict) else []
    manifest_mag = 0.0
    if isinstance(manifest, dict):
        try:
            manifest_mag = float(manifest.get("effectMagnitude") or 0.0)
        except Exception:
            manifest_mag = 0.0
    effect_tags: set[str] = set()
    suggested: set[str] = set()
    if damage > 0:
        effect_tags.add("weapon")
    if damage >= 25 or rarity >= 3:
        effect_tags.add("strong_parent")
    if item_num(item, "shoot", 0) > 0:
        effect_tags.update({"projectile", "travel"}); suggested.add("projectileAfterimage")
    if item_bool(item, "channel"):
        effect_tags.update({"channel", "beam", "sustained"}); suggested.add("beamLine")
    if item_bool(item, "noMelee"):
        effect_tags.add("projectile_delivery")
    if str(item_field(item, "damageClass", "")).lower() in {"melee", "meleenospeed", "melee damage"} or (damage > 0 and item_num(item, "shoot", 0) <= 0):
        effect_tags.update({"slash", "held"}); suggested.add("tipTrail")
    if isinstance(projectile, dict) and projectile:
        if proj_num(projectile, "light", 0) > 0:
            effect_tags.add("light"); suggested.add("lightCue")
        if proj_num(projectile, "extraUpdates", 0) > 0:
            effect_tags.add("fast")
        if proj_num(projectile, "penetrate", 1) == -1 or proj_num(projectile, "penetrate", 1) > 1:
            effect_tags.add("pierce"); suggested.add("historyRibbon")
        if not proj_bool(projectile, "tileCollide"):
            effect_tags.add("phase")
        if proj_bool(projectile, "usesLocalNPCImmunity") or proj_bool(projectile, "usesIDStaticNPCImmunity"):
            effect_tags.add("multihit"); suggested.add("impactSpriteBurst")
        if proj_bool(projectile, "minion") or proj_bool(projectile, "sentry"):
            effect_tags.add("summoned")
        ai_style = int(proj_num(projectile, "aiStyle", 0))
        if ai_style > 0:
            effect_tags.add(f"aiStyle_{ai_style}")
    for t in behavior:
        effect_tags.add(t)
        tl = t.lower()
        if any(x in tl for x in ["homing", "boomerang", "return"]):
            suggested.add("orbitalMotes")
        if any(x in tl for x in ["beam", "laser"]):
            suggested.add("beamLine")
        if any(x in tl for x in ["trail", "oldpos", "extra_updates"]):
            suggested.add("historyRibbon")
    if manifest_slots:
        effect_tags.add("generated_vfx_parent")
        for slot in manifest_slots:
            renderer = str(slot.get("renderer") or "")
            if renderer:
                suggested.add(renderer)
            ch = str(slot.get("channel") or "")
            if ch:
                effect_tags.add("channel_" + ch)
    runtime_signals = item.get("parentVfxSignals") if isinstance(item.get("parentVfxSignals"), dict) else {}
    # Do not infer VFX inheritance from parent names/tokens. Names still go to LLM/art prompts,
    # but parent VFX inheritance is driven by mechanical/runtime facts only.
    if isinstance(runtime_signals, dict) and runtime_signals:
        for t in runtime_signals.get("effectTags") or []:
            if str(t): effect_tags.add("runtime_" + str(t))
        for r in runtime_signals.get("suggestedRenderers") or []:
            if str(r): suggested.add(str(r))
    score = 0.0
    score += min(0.28, damage / 180.0)
    score += min(0.20, max(0, rarity) / 30.0)
    try:
        score += min(0.22, float(prof.get("effectiveDpsSignal") or 0.0) / 250.0)
    except Exception:
        pass
    score += min(0.16, len(behavior) * 0.025)
    if item_num(item, "shoot", 0) > 0: score += 0.08
    if item_bool(item, "channel"): score += 0.10
    if isinstance(projectile, dict) and projectile:
        if proj_num(projectile, "light", 0) > 0: score += 0.06
        if proj_num(projectile, "extraUpdates", 0) > 0: score += 0.04
        if proj_num(projectile, "penetrate", 1) == -1 or proj_num(projectile, "penetrate", 1) > 1: score += 0.05
        if not proj_bool(projectile, "tileCollide"): score += 0.04
        if proj_bool(projectile, "usesLocalNPCImmunity") or proj_bool(projectile, "usesIDStaticNPCImmunity"): score += 0.06
    if manifest_slots:
        score += min(0.42, 0.16 + manifest_mag * 0.24 + len(manifest_slots) * 0.015)
    if isinstance(runtime_signals, dict) and runtime_signals:
        try:
            score = max(score, float(runtime_signals.get("specialScore") or 0.0))
        except Exception:
            pass
        if runtime_signals.get("hasProjectileEmission"):
            score += 0.05
        if runtime_signals.get("hasSustainedUse") or runtime_signals.get("hasBeamLikeProfile"):
            score += 0.06
        if runtime_signals.get("hasGeneratedManifest"):
            score += 0.12
    score = max(0.0, min(1.0, score))
    return {
        "index": index,
        "name": name,
        "identity": item_identity(item),
        "generatedDepth": generation_depth(item),
        "damage": round(damage, 3),
        "rarity": rarity,
        "useTime": round(use_time, 3),
        "specialScore": round(score, 3),
        "notable": bool(score >= VFX_PARENT_EFFECT_STRONG_THRESHOLD or manifest_slots),
        "effectTags": sorted(effect_tags)[:48],
        "suggestedRenderers": sorted(suggested)[:20],
        "parentRuntimeSignals": runtime_signals if isinstance(runtime_signals, dict) else {},
        "weaponProfile": {k: prof.get(k) for k in ["damage", "damageClass", "shoot", "shootSpeed", "channel", "aiStyle", "piercePotential", "lifetime", "extraUpdates", "localImmunity", "effectiveDpsSignal"] if k in prof},
        "manifestSummary": {
            "hasManifest": bool(manifest_slots),
            "recipeId": str(manifest.get("recipeId") or "") if isinstance(manifest, dict) else "",
            "effectMagnitude": round(manifest_mag, 3),
            "visualBudgetClass": str(manifest.get("visualBudgetClass") or "") if isinstance(manifest, dict) else "",
            "slotCount": len(manifest_slots),
            "motif": manifest.get("motif") if isinstance(manifest.get("motif"), dict) else {},
        },
        "manifestSlots": manifest_slots[:10],
    }


def _vfx_parent_effect_profile(data: dict[str, Any], parent_a: dict[str, Any] | None = None, parent_b: dict[str, Any] | None = None) -> dict[str, Any]:
    if not VFX_PARENT_EFFECT_INHERITANCE:
        return {"enabled": False}
    meta = data.setdefault("recipeMeta", {}) if isinstance(data, dict) else {}
    if not isinstance(meta, dict):
        meta = {}
    items = [x for x in (parent_a, parent_b) if isinstance(x, dict) and x]
    if not items and isinstance(meta.get("parentVfxEffectProfile"), dict):
        return meta["parentVfxEffectProfile"]
    if not items:
        return {"enabled": False, "reason": "no_parent_items_available"}
    parents = [_vfx_parent_profile_from_item(item, i) for i, item in enumerate(items)]
    max_score = max([float(p.get("specialScore") or 0.0) for p in parents] or [0.0])
    same_identity = len(parents) >= 2 and parents[0].get("identity") and parents[0].get("identity") == parents[1].get("identity")
    same_name = len(parents) >= 2 and str(parents[0].get("name") or "").strip().lower() == str(parents[1].get("name") or "").strip().lower()
    generated_manifest_parent = any((p.get("manifestSummary") or {}).get("hasManifest") for p in parents)
    tags = sorted({t for p in parents for t in (p.get("effectTags") or [])})[:80]
    renderers = sorted({r for p in parents for r in (p.get("suggestedRenderers") or [])})[:36]
    profile = {
        "enabled": True,
        "sameParent": bool(same_identity or same_name),
        "sameIdentity": bool(same_identity),
        "sameName": bool(same_name),
        "maxSpecialScore": round(max_score, 3),
        "notable": bool(max_score >= VFX_PARENT_EFFECT_STRONG_THRESHOLD or generated_manifest_parent),
        "generatedManifestParent": bool(generated_manifest_parent),
        "effectTags": tags,
        "suggestedRenderers": renderers,
        "parents": [{k: v for k, v in p.items() if k != "manifestSlots"} for p in parents],
    }
    meta["parentVfxEffectProfile"] = profile
    data["recipeMeta"] = meta
    return profile


def _vfx_parent_effect_tag_set(profile: dict[str, Any]) -> set[str]:
    if not isinstance(profile, dict) or not profile.get("enabled"):
        return set()
    tags = {str(x).lower() for x in (profile.get("effectTags") or []) if str(x)}
    renderers = {str(x).lower() for x in (profile.get("suggestedRenderers") or []) if str(x)}
    return tags | renderers


def _vfx_parent_effect_recipe_bonus(recipe: dict[str, Any], profile: dict[str, Any]) -> tuple[float, list[str]]:
    if not isinstance(profile, dict) or not profile.get("enabled") or not profile.get("notable"):
        return 0.0, []
    tags = _vfx_parent_effect_tag_set(profile)
    if not tags:
        return 0.0, []
    raw_slots = [x for x in (recipe.get("slots") or []) if isinstance(x, dict)]
    slot_renderers = {_vfx_renderer_family(str(s.get("renderer") or "")).lower() for s in raw_slots}
    slot_channels = {str(s.get("channel") or _vfx_infer_channel(s.get("renderer"), s.get("event"))).lower() for s in raw_slots}
    bonus = 0.0
    reasons: list[str] = []
    if any(x in tags for x in {"slash", "held", "tiptrail", "historyribbon"}) and (slot_renderers & {"tiptrail", "historyribbon", "ghostarc"}):
        bonus += 22.0; reasons.append("parent_slash_renderer_match")
    if any(x in tags for x in {"projectile", "travel", "projectileafterimage"}) and (slot_renderers & {"projectileafterimage", "spritestamptrail"}):
        bonus += 17.0; reasons.append("parent_projectile_renderer_match")
    if any(x in tags for x in {"beam", "channel", "beamline"}) and ("beamline" in slot_renderers or "beam" in " ".join(slot_renderers)):
        bonus += 24.0; reasons.append("parent_beam_renderer_match")
    if any(x in tags for x in {"multihit", "pierce", "impactspriteburst", "impactshape"}) and ("impactshape" in slot_channels or "impactspriteburst" in slot_renderers):
        bonus += 18.0; reasons.append("parent_impact_renderer_match")
    if any(x in tags for x in {"light", "lightcue"}) and ("lightcue" in slot_renderers or "light" in slot_channels):
        bonus += 10.0; reasons.append("parent_light_cue_match")
    score = float(profile.get("maxSpecialScore") or 0.0)
    if score >= 0.70 and str(recipe.get("cost") or "") in {"high", "signature", "ultra"}:
        bonus += 12.0; reasons.append("strong_parent_allows_heavy_recipe")
    if str(recipe.get("id") or "").startswith("mundane_"):
        bonus -= 110.0; reasons.append("parent_effect_blocks_mundane_recipe")
    return bonus * VFX_PARENT_EFFECT_WEIGHT, reasons


def _vfx_transform_parent_slot_for_child(slot: dict[str, Any], source: str, seed: int, order: int) -> dict[str, Any]:
    out = dict(slot)
    renderer = str(out.get("renderer") or "ambientMotes")
    event = str(out.get("event") or "travel")
    # Parent effects become support/accent layers; the child result still owns the primary composition.
    out["source"] = f"parentEffect:{source}"
    out["importance"] = "accent" if order else "secondary"
    out["lane"] = "accent" if order else "support"
    out["channel"] = out.get("channel") or _vfx_infer_channel(renderer, event)
    out["backend"] = out.get("backend") or _vfx_default_backend(event, renderer)
    out["anchor"] = out.get("anchor") or _vfx_default_anchor(event, renderer)
    try: out["density"] = max(0.05, min(0.48, float(out.get("density") or 0.25) * 0.72))
    except Exception: out["density"] = 0.22
    try: out["alpha"] = max(0.16, min(0.62, float(out.get("alpha") or 0.38) * 0.82))
    except Exception: out["alpha"] = 0.32
    try: out["scale"] = max(0.45, min(2.35, float(out.get("scale") or 1.0) * (0.82 + _vfx_unit(seed, f"parentscale{order}") * 0.26)))
    except Exception: out["scale"] = 1.0
    try: out["signatureWeight"] = max(0.05, min(0.55, float(out.get("signatureWeight") or 0.22) * 0.65))
    except Exception: out["signatureWeight"] = 0.22
    try: out["visualCost"] = max(0.04, min(0.42, float(out.get("visualCost") or 0.18) * 0.66))
    except Exception: out["visualCost"] = 0.16
    out.pop("bakedCommands", None)
    out.pop("bakedClipId", None)
    out.pop("bakedClipHash", None)
    out.pop("bakedCommandCount", None)
    return out


def _vfx_parent_inherited_raw_slots(profile: dict[str, Any], pattern: str, roles: set[str], magnitude_class: str, seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(profile, dict) or not profile.get("enabled") or not profile.get("notable"):
        return [], []
    max_slots = max(0, min(6, VFX_PARENT_EFFECT_MAX_INHERITED_SLOTS))
    if max_slots <= 0:
        return [], []
    raw: list[dict[str, Any]] = []
    debug: list[dict[str, Any]] = []
    # Prefer actual generated-parent manifest slots when present.
    for parent in profile.get("parents") or []:
        pass
    # The public profile intentionally strips manifestSlots from debug. Re-read them from recipeMeta cache if present.
    meta_profile = profile
    # If attach_hybrid_vfx_manifest has raw parent profiles in memory, they are stored in _rawParentSlots.
    for slot in meta_profile.get("_rawParentSlots") or []:
        if isinstance(slot, dict):
            raw.append(_vfx_transform_parent_slot_for_child(slot, "manifest", seed, len(raw)))
            if len(raw) >= max_slots:
                break
    tags = _vfx_parent_effect_tag_set(profile)
    def add(slot: dict[str, Any], reason: str) -> None:
        nonlocal raw, debug
        if len(raw) >= max_slots:
            return
        slot = dict(slot)
        slot.setdefault("source", f"parentEffect:{reason}")
        raw.append(slot)
        debug.append({"reason": reason, "renderer": slot.get("renderer"), "event": slot.get("event"), "channel": slot.get("channel", "")})
    if "projectile" in roles and any(x in tags for x in {"slash", "held", "tiptrail", "historyribbon", "strong_parent"}) and pattern in {"slash_holdout", "beam_slash", "basic"}:
        add({"event":"active", "renderer":"historyRibbon", "textureRole":"projectile", "backend":"Primitive", "channel":"motionTrail", "lane":"support", "importance":"secondary", "scale":[0.9,1.65], "density":[0.18,0.48], "duration":[10,24], "alpha":[0.22,0.58], "visualCost":[0.12,0.36], "signatureWeight":[0.22,0.55]}, "slash_history")
    if "projectile" in roles and any(x in tags for x in {"projectile", "travel", "projectileafterimage", "fast"}):
        add({"event":"travel", "renderer":"projectileAfterimage", "textureRole":"projectile", "backend":"Sprite", "channel":"motionTrail", "lane":"support", "importance":"secondary", "scale":[0.75,1.28], "density":[0.12,0.38], "duration":[6,16], "alpha":[0.18,0.46], "visualCost":[0.08,0.28], "signatureWeight":[0.12,0.42]}, "projectile_afterimage")
    if "impact" in roles and any(x in tags for x in {"multihit", "pierce", "strong_parent", "generated_vfx_parent", "impactspriteburst"}):
        add({"event":"hit", "renderer":"impactSpriteBurst", "textureRole":"impact", "particleRole":"child", "backend":"Baked", "channel":"impactShape", "lane":"support", "importance":"secondary", "scale":[1.25,2.65], "density":[0.18,0.55], "duration":[6,15], "alpha":[0.38,0.82], "visualCost":[0.12,0.42], "signatureWeight":[0.20,0.56]}, "impact_inherited")
    if any(x in tags for x in {"beam", "channel", "beamline"}) and "projectile" in roles:
        add({"event":"active", "renderer":"beamLine", "textureRole":"projectile", "backend":"Primitive", "channel":"motionTrail", "lane":"support", "importance":"secondary", "scale":[0.75,1.55], "density":[0.16,0.42], "duration":[10,24], "alpha":[0.18,0.48], "visualCost":[0.10,0.34], "signatureWeight":[0.18,0.50]}, "beam_inherited")
    if any(x in tags for x in {"light", "lightcue"}):
        add({"event":"active", "renderer":"lightCue", "textureRole":"projectile", "backend":"Realtime", "channel":"light", "lane":"cue", "importance":"accent", "scale":[0.8,1.7], "density":[0.08,0.22], "duration":[8,22], "alpha":[0.2,0.55], "visualCost":[0.03,0.10], "signatureWeight":[0.10,0.25]}, "light_inherited")
    raw = raw[:max_slots]
    return raw, debug

def _vfx_mundane_duplicate_profile(data: dict[str, Any], pattern: str = "", words: set[str] | None = None, power: float = 1.0) -> dict[str, Any]:
    """Detect boring same-parent / low-novelty fusions and clamp VFX composition.

    This is deliberately not a semantic VFX classifier. It does not map copper/dagger/wood to
    visual effects. It only says: if the craft is basically the same low-tier parent twice, do
    not add runner-up/procedural fireworks just because the generic composer can.
    """
    if not VFX_MUNDANE_DUPLICATE_GUARD or not isinstance(data, dict):
        return {"enabled": False}
    meta = data.get("recipeMeta") if isinstance(data.get("recipeMeta"), dict) else {}
    debug = data.get("debug") if isinstance(data.get("debug"), dict) else {}
    gameplay = data.get("gameplay") if isinstance(data.get("gameplay"), dict) else {}
    parent_names = [str(meta.get("parentA") or data.get("parentA") or "").strip().lower(), str(meta.get("parentB") or data.get("parentB") or "").strip().lower()]
    identities = meta.get("parentIdentities") if isinstance(meta.get("parentIdentities"), list) else []
    same_identity = len(identities) >= 2 and str(identities[0] or "") == str(identities[1] or "") and bool(str(identities[0] or ""))
    same_name = bool(parent_names[0] and parent_names[0] == parent_names[1])
    try:
        depths = [int(float(x or 0)) for x in (meta.get("parentGeneratedDepths") or [])]
    except Exception:
        depths = []
    generated_parent = any(x > 0 for x in depths)
    novelty_raw = debug.get("novelty") or debug.get("noveltyScore") or gameplay.get("novelty") or gameplay.get("noveltyScore") or meta.get("noveltyBudget") or 0.0
    try:
        novelty = float(novelty_raw or 0.0)
    except Exception:
        novelty = 0.0
    try:
        pwr = float(power or 1.0)
    except Exception:
        pwr = 1.0
    w = set(words or set())
    explosive_or_signature_words = {"explosive", "explosion", "nova", "legendary", "signature", "ultra", "mythic", "boss", "calamity", "cataclysm"}
    explicit_big = bool(w & explosive_or_signature_words)
    parent_vfx_profile = meta.get("parentVfxEffectProfile") if isinstance(meta.get("parentVfxEffectProfile"), dict) else {}
    parent_effect_notable = bool(parent_vfx_profile.get("notable")) and float(parent_vfx_profile.get("maxSpecialScore") or 0.0) >= VFX_PARENT_EFFECT_STRONG_THRESHOLD
    if (same_identity or same_name) and parent_effect_notable:
        return {"enabled": False, "sameParent": True, "parentEffectful": True, "reason": "same_parent_has_observable_vfx_or_weapon_effects", "parentEffectScore": round(float(parent_vfx_profile.get("maxSpecialScore") or 0.0), 3)}
    # Same generated parent can be a recursive power item; don't clamp it blindly.
    enabled = (same_identity or same_name) and not generated_parent and not explicit_big and pwr <= 1.18 and novelty <= 0.34
    if not enabled:
        return {"enabled": False, "sameParent": bool(same_identity or same_name), "generatedParent": generated_parent, "novelty": round(novelty, 3), "power": round(pwr, 3)}
    return {
        "enabled": True,
        "sameParent": bool(same_identity or same_name),
        "sameIdentity": bool(same_identity),
        "sameName": bool(same_name),
        "generatedParent": False,
        "novelty": round(novelty, 3),
        "power": round(pwr, 3),
        "maxSlots": max(1, VFX_MUNDANE_MAX_SLOTS),
        "reason": "same_low_novelty_parent_pair",
    }


def _vfx_trim_mundane_slots(slots: list[dict[str, Any]], profile: dict[str, Any]) -> list[dict[str, Any]]:
    if not profile.get("enabled"):
        return slots
    max_slots = max(1, int(profile.get("maxSlots") or VFX_MUNDANE_MAX_SLOTS or 3))
    # Keep one readable motion layer, one impact shape, and at most one cue/accent.
    preferred = []
    for slot in sorted([x for x in slots if isinstance(x, dict)], key=_vfx_slot_score, reverse=True):
        group = _vfx_event_group(slot.get("event"))
        channel = str(slot.get("channel") or _vfx_infer_channel(slot.get("renderer"), slot.get("event")))
        renderer = str(slot.get("renderer") or "")
        if channel in {"ambientParticles", "decaySmoke"}:
            continue
        if group == "live" and channel != "motionTrail" and channel not in {"light", "sound"}:
            continue
        if group == "hit" and channel not in {"impactShape", "light", "sound"}:
            continue
        if group == "kill" and channel not in {"impactShape", "light", "sound"}:
            continue
        if any(((_vfx_event_group(s.get("event")), str(s.get("channel") or _vfx_infer_channel(s.get("renderer"), s.get("event")))) == (group, channel)) for s in preferred):
            continue
        # Downshift density/alpha/scale a bit but do not make it invisible.
        slot = dict(slot)
        slot["source"] = str(slot.get("source") or "recipe") + ":mundaneClamped"
        slot["importance"] = "core" if not preferred else "secondary"
        slot["lane"] = "primary" if not preferred else "support"
        try: slot["density"] = max(0.05, min(0.34, float(slot.get("density") or 0.18)))
        except Exception: slot["density"] = 0.16
        try: slot["alpha"] = max(0.18, min(0.56, float(slot.get("alpha") or 0.38)))
        except Exception: slot["alpha"] = 0.38
        try: slot["scale"] = max(0.55, min(1.55, float(slot.get("scale") or 1.0)))
        except Exception: slot["scale"] = 1.0
        if renderer.lower() in {"impactring", "ghostarc", "orbitalmotes"}:
            continue
        preferred.append(slot)
        if len(preferred) >= max_slots:
            break
    if preferred:
        return preferred
    return slots[:max_slots]


def _vfx_color_hex(seed: int, salt: str, fallback: str = "") -> str:
    palettes = [
        "#78FF7A", "#DDF8FF", "#FFD36A", "#FF6A6A", "#9A7CFF", "#6AF5FF", "#FFFFFF", "#6AFFA6",
    ]
    if fallback:
        return fallback
    return palettes[_vfx_seed_int(seed, salt) % len(palettes)]


_VFX_PARTICLE_ADDRESS_CATALOG: dict[str, dict[str, Any]] = {
    "pl:glow": {
        "kind": "quad",
        "blend": "additive",
        "layer": "BeforeProjectiles",
        "aliases": ["glow", "softGlow", "additiveGlow", "soulGlow", "magicGlow", "beamGlow"],
        "notes": "Soft additive quads for beams, magic ribbons, core glow and luminous baked tape.",
    },
    "pl:shard": {
        "kind": "quad",
        "blend": "alpha",
        "layer": "BeforeProjectiles",
        "aliases": ["shard", "debris", "fragment", "burst", "hitBurst"],
        "notes": "Material-looking quad particles for impact chunks, fragment bursts and heavier hit debris.",
    },
    "pl:smoke": {
        "kind": "quad",
        "blend": "alpha",
        "layer": "BeforeProjectiles",
        "aliases": ["smoke", "ash", "cloud", "decay", "residue"],
        "notes": "Longer-lived alpha quads for decay, smoke, residue and field haze.",
    },
    "pl:spark": {
        "kind": "point",
        "blend": "additive",
        "layer": "BeforeProjectiles",
        "aliases": ["spark", "point", "glint", "star", "twinkle"],
        "notes": "Cheap additive point particles for sparks, glints, star specks and high-count accents.",
    },
    "dust": {
        "kind": "fallback",
        "blend": "alpha",
        "layer": "BeforeProjectiles",
        "aliases": ["vanillaDust", "fallback"],
        "notes": "Explicit vanilla Dust fallback. Use only when ParticleLibrary routing is not desired.",
    },
}


def _vfx_particle_address_catalog() -> dict[str, Any]:
    return {
        "schema": "infini.vfx.particle_address_catalog.v0",
        "default": "auto",
        "systems": _VFX_PARTICLE_ADDRESS_CATALOG,
        "guideline": "Recipes should set particleSystemId explicitly when they care about material: pl:glow, pl:shard, pl:smoke, pl:spark. Missing/auto ids are resolved from renderer/channel/event.",
    }


def _vfx_canonical_particle_address(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("_", "-").replace(" ", "-")
    if not raw or raw in {"auto", "default"}:
        return "auto"
    aliases: dict[str, str] = {}
    for canonical, meta in _VFX_PARTICLE_ADDRESS_CATALOG.items():
        aliases[canonical.lower()] = canonical
        for alias in meta.get("aliases") or []:
            aliases[str(alias).strip().lower().replace("_", "-").replace(" ", "-")] = canonical
    aliases.update({
        "particlelibrary:glow": "pl:glow",
        "particlelibrary:shard": "pl:shard",
        "particlelibrary:smoke": "pl:smoke",
        "particlelibrary:spark": "pl:spark",
        "vanilla:dust": "dust",
    })
    return aliases.get(raw, raw if raw.startswith("pl:") else "auto")


def _vfx_resolve_particle_system_id(raw: dict[str, Any] | None, renderer: str, event: str, channel: str = "", blend: str = "", emission_mode: str = "") -> str:
    raw = raw or {}
    explicit = _vfx_canonical_particle_address(raw.get("particleSystemId") or raw.get("particleSystem") or raw.get("particleAddress"))
    if explicit not in {"", "auto"}:
        return explicit
    r = str(renderer or "").lower()
    e = str(event or "").lower()
    c = str(channel or "").lower()
    b = str(blend or "").lower()
    m = str(emission_mode or "").lower()
    if "light" in r or c == "light":
        return "pl:glow"
    if "sound" in r or c == "sound":
        return "dust"
    if any(x in m for x in ("residue", "smoke")) or any(x in r for x in ("smoke", "decay", "cloud", "residue")) or c == "decaysmoke":
        return "pl:smoke"
    if any(x in r for x in ("spark", "glint", "star")) or "spark" in m:
        return "pl:spark"
    if ("mote" in r or "particle" in r) and c == "ambientparticles":
        return "pl:spark"
    if ("mote" in r or "particle" in r) and c == "decaysmoke":
        return "pl:smoke"
    if any(x in r for x in ("flash", "pulse", "field")):
        return "pl:glow"
    if "ring" in r and ("add" in b or c == "coreglow" or e in {"hit", "impact", "onhit"}):
        return "pl:glow"
    if any(x in r for x in ("shard", "debris", "burst")) or c == "impactparticles":
        return "pl:shard"
    if "add" in b or any(x in r for x in ("glow", "beam", "ribbon", "trail")) or c == "coreglow":
        return "pl:glow"
    if e in {"hit", "impact", "onhit"}:
        return "pl:shard"
    if e in {"kill", "expire", "decay"}:
        return "pl:smoke"
    if c == "ambientparticles":
        return "pl:spark"
    return "pl:glow"


def _vfx_baked_command_count(renderer: str, density: float, duration: int) -> int:
    r = str(renderer or "").lower()
    if any(x in r for x in ("flash", "ring", "light", "sound")):
        return max(1, min(4, int(round(1 + density * 3))))
    if any(x in r for x in ("burst", "mote", "spark", "smoke", "shard")):
        return max(3, min(18, int(round(4 + density * 20))))
    if any(x in r for x in ("trail", "ribbon", "stamp", "afterimage")):
        return max(2, min(12, int(round(2 + density * 12))))
    return max(1, min(8, int(round(1 + density * 8))))


def _vfx_should_bake_slot(raw: dict[str, Any], event: str, renderer: str, backend: str) -> bool:
    if raw.get("bake") is False or raw.get("baked") is False:
        return False
    if raw.get("bakedCommands"):
        return False
    b = str(backend or "").lower()
    e = str(event or "").lower()
    r = str(renderer or "").lower()
    if b in {"baked", "hybrid"}:
        return True
    if e in {"hit", "impact", "onhit", "kill", "expire", "decay"}:
        return True
    return any(x in r for x in ("burst", "smoke", "spark", "mote", "shard", "flash", "ring"))


def _vfx_bake_slot_commands(raw: dict[str, Any], seed: int, renderer: str, event: str, backend: str, density: float, duration: int, alpha: float, scale: float, spread: float) -> list[dict[str, Any]]:
    """Compile a lightweight baked spawn tape into the manifest.

    These commands are not semantic VFX. They are precomputed spawn events for the runtime
    to replay at deterministic ticks. Role textures/colors remain chosen by the manifest slot.
    """
    explicit = raw.get("bakedCommands")
    if isinstance(explicit, list):
        out = []
        for i, cmd in enumerate(explicit[:64]):
            if isinstance(cmd, dict):
                c = dict(cmd)
                c.setdefault("tick", 0)
                c.setdefault("particleSystemId", _vfx_resolve_particle_system_id(c, renderer, event, str(raw.get("channel") or ""), str(raw.get("blend") or ""), str(raw.get("emissionMode") or "")))
                c.setdefault("seedBucket", i)
                out.append(c)
        return out
    if not _vfx_should_bake_slot(raw, event, renderer, backend):
        return []
    count = _vfx_baked_command_count(renderer, density, duration)
    r = str(renderer or "").lower()
    out: list[dict[str, Any]] = []
    # Spread in local-space units. Runtime multiplies by projectile dimensions/scale.
    max_tick = max(1, min(120, duration))
    for i in range(count):
        cmd_seed = _vfx_seed_int(seed, renderer, event, "cmd", i)
        u = _vfx_unit(cmd_seed, "u")
        v = _vfx_unit(cmd_seed, "v")
        angle = (2.0 * math.pi) * u
        radial = (0.15 + 0.85 * v) * (0.35 + spread)
        # Trails bias backwards in local X, bursts are radial.
        if any(x in r for x in ("trail", "ribbon", "stamp", "afterimage")):
            local_x = -radial * (0.45 + i / max(1, count - 1))
            local_y = (v - 0.5) * (0.35 + spread * 0.45)
            vel_x = -0.20 - spread * 0.35 * u
            vel_y = (v - 0.5) * 0.55
            tick = int(round((i / max(1, count - 1)) * max_tick * 0.75))
        else:
            local_x = math.cos(angle) * radial
            local_y = math.sin(angle) * radial
            vel_x = math.cos(angle) * (0.35 + spread * 1.25)
            vel_y = math.sin(angle) * (0.35 + spread * 1.25)
            tick = int(round(_vfx_unit(cmd_seed, "tick") * max_tick * 0.75))
        out.append({
            "tick": max(0, min(max_tick, tick)),
            "particleSystemId": _vfx_resolve_particle_system_id(raw, renderer, event, str(raw.get("channel") or ""), str(raw.get("blend") or ""), str(raw.get("emissionMode") or "")),
            "textureRole": str(raw.get("particleRole") or raw.get("textureRole") or ""),
            "localX": round(local_x, 3),
            "localY": round(local_y, 3),
            "velocityX": round(vel_x, 3),
            "velocityY": round(vel_y, 3),
            "startColor": _vfx_color_hex(cmd_seed, "start"),
            "endColor": "#00000000",
            "scaleX": round(max(0.08, min(4.0, scale * (0.18 + _vfx_unit(cmd_seed, "sx") * 0.55))), 3),
            "scaleY": round(max(0.08, min(4.0, scale * (0.18 + _vfx_unit(cmd_seed, "sy") * 0.55))), 3),
            "scaleVelocityX": round(-0.002 - _vfx_unit(cmd_seed, "svx") * 0.018, 4),
            "scaleVelocityY": round(-0.002 - _vfx_unit(cmd_seed, "svy") * 0.018, 4),
            "rotation": round(angle, 3),
            "rotationVelocity": round((_vfx_unit(cmd_seed, "rv") - 0.5) * 0.25, 4),
            "lifespan": max(4, min(90, int(round(6 + duration * (0.35 + _vfx_unit(cmd_seed, "life") * 0.9))))),
            "alpha": round(max(0.02, min(1.0, alpha * (0.45 + _vfx_unit(cmd_seed, "a") * 0.55))), 3),
            "seedBucket": int(cmd_seed % 100000000),
        })
    return sorted(out, key=lambda x: int(x.get("tick", 0)))


def _vfx_baked_clip_meta(recipe_seed: int, slot_index: int, renderer: str, event: str, commands: list[dict[str, Any]]) -> dict[str, Any]:
    if not commands:
        return {"bakedClipId": "", "bakedClipHash": "", "bakedCommandCount": 0}
    compact = json.dumps(commands, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha1(compact.encode("utf-8")).hexdigest()[:16]
    safe_renderer = re.sub(r"[^a-zA-Z0-9_]+", "_", str(renderer or "clip")).strip("_").lower()[:32] or "clip"
    safe_event = re.sub(r"[^a-zA-Z0-9_]+", "_", str(event or "event")).strip("_").lower()[:16] or "event"
    return {
        "bakedClipId": f"{safe_event}_{safe_renderer}_{slot_index}_{digest[:8]}",
        "bakedClipHash": digest,
        "bakedCommandCount": len(commands),
    }

def _vfx_compile_slot(raw: dict[str, Any], seed: int, slot_index: int, power_budget: float, effect_magnitude: float = 0.5) -> dict[str, Any]:
    slot_seed = _vfx_seed_int(seed, raw.get("renderer", "slot"), slot_index)
    variants = raw.get("variants") if isinstance(raw.get("variants"), list) else []
    renderer = str(raw.get("renderer") or "projectileAfterimage")
    event = str(raw.get("event") or "tick")
    scale = _vfx_lerp_range(slot_seed, "scale", raw.get("scale"), 1.0)
    density = _vfx_lerp_range(slot_seed, "density", raw.get("density"), 0.35)
    duration = int(round(_vfx_lerp_range(slot_seed, "duration", raw.get("duration"), 10)))
    alpha = _vfx_lerp_range(slot_seed, "alpha", raw.get("alpha"), 0.65)
    spread = _vfx_lerp_range(slot_seed, "spread", raw.get("spread"), 0.5)
    jitter = _vfx_lerp_range(slot_seed, "jitter", raw.get("jitter"), 0.35)
    phase_offset = _vfx_lerp_range(slot_seed, "phaseOffset", raw.get("phaseOffset"), 0.0)
    budget_weight = _vfx_lerp_range(slot_seed, "budgetWeight", raw.get("budgetWeight"), 1.0)
    start_tick = int(round(_vfx_lerp_range(slot_seed, "startTick", raw.get("startTick"), 0)))
    repeat_every = int(round(_vfx_lerp_range(slot_seed, "repeatEvery", raw.get("repeatEvery"), 0)))
    # Small power injection is allowed here; gameplay balance is not. Visual scale remains capped.
    visual_power = max(0.55, min(1.85, 0.72 + float(effect_magnitude or 0.5) * 0.86 + float(power_budget or 1.0) * 0.04))
    backend = str(raw.get("backend") or _vfx_default_backend(event, renderer))
    renderer_kind = str(raw.get("rendererKind") or _vfx_renderer_kind(renderer))
    event_group = str(raw.get("eventGroup") or _vfx_event_group(event))
    blend = str(raw.get("blend") or ("additive" if renderer_kind in {"lightCue", "beamLine"} or any(w in renderer.lower() for w in ("glow", "light", "spark", "beam")) else "alpha"))
    channel = str(raw.get("channel") or _vfx_infer_channel(renderer, event))
    importance = str(raw.get("importance") or _vfx_default_importance(event, renderer))
    lane = str(raw.get("lane") or _vfx_infer_lane({**raw, "renderer": renderer, "event": event, "importance": importance, "channel": channel}))
    emission_mode = str(raw.get("emissionMode") or _vfx_infer_emission_mode(renderer, event))
    particle_system_id = _vfx_resolve_particle_system_id(raw, renderer, event, channel, blend, emission_mode)
    baked_commands = _vfx_bake_slot_commands(raw, slot_seed, renderer, event, backend, density, duration, alpha, scale, spread)
    baked_meta = _vfx_baked_clip_meta(seed, slot_index, renderer, event, baked_commands)
    return {
        "event": event,
        "eventGroup": event_group,
        "stage": str(raw.get("stage") or _vfx_event_stage(event, renderer)),
        "source": str(raw.get("source") or "recipe"),
        "backend": backend,
        "renderer": renderer,
        "rendererKind": renderer_kind,
        "textureRole": str(raw.get("textureRole") or "projectile"),
        "particleRole": str(raw.get("particleRole") or raw.get("textureRole") or "child"),
        "anchor": str(raw.get("anchor") or _vfx_default_anchor(event, renderer)),
        "blend": blend,
        "layer": str(raw.get("layer") or "BeforeProjectiles"),
        "channel": channel,
        "lane": lane,
        "emissionMode": emission_mode,
        "particleSystemId": particle_system_id,
        "fadeIn": round(max(0.0, min(0.95, _vfx_lerp_range(slot_seed, "fadeIn", raw.get("fadeIn"), 0.15))), 3),
        "fadeOut": round(max(0.0, min(0.95, _vfx_lerp_range(slot_seed, "fadeOut", raw.get("fadeOut"), 0.35))), 3),
        "curve": str(raw.get("curve") or "smooth"),
        "slotSeed": int(_vfx_seed_int(seed, "slot", slot_index, renderer, event)),
        "variant": int(_vfx_pick(slot_seed, "variant", variants, 0) or 0),
        "startTick": max(0, min(600, start_tick)),
        "repeatEvery": max(0, min(600, repeat_every)),
        "scale": round(max(0.05, min(8.0, scale * visual_power)), 3),
        "density": round(max(0.0, min(1.0, density)), 3),
        "duration": max(1, min(240, duration)),
        "alpha": round(max(0.0, min(1.0, alpha)), 3),
        "spread": round(max(0.0, min(3.0, spread)), 3),
        "jitter": round(max(0.0, min(2.0, jitter)), 3),
        "phaseOffset": round(max(-2.0, min(2.0, phase_offset)), 3),
        "budgetWeight": round(max(0.05, min(8.0, budget_weight)), 3),
        # v0.3.26: minQuality is deprecated/compat only. Slots are no longer design-gated by graphics presets.
        "minQuality": str(raw.get("minQuality") or raw.get("quality") or "Full"),
        "importance": str(raw.get("importance") or _vfx_default_importance(event, renderer)),
        "visualCost": round(max(0.0, min(1.0, _vfx_lerp_range(slot_seed, "visualCost", raw.get("visualCost"), _vfx_default_visual_cost(renderer, density)))), 3),
        "signatureWeight": round(max(0.0, min(1.0, _vfx_lerp_range(slot_seed, "signatureWeight", raw.get("signatureWeight"), _vfx_default_signature_weight(event, renderer)))), 3),
        "bakedClipId": baked_meta["bakedClipId"],
        "bakedClipHash": baked_meta["bakedClipHash"],
        "bakedCommandCount": baked_meta["bakedCommandCount"],
        "bakedCommands": baked_commands,
    }



def _vfx_family_key(slot: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _vfx_event_group(slot.get("event")),
        str(slot.get("channel") or _vfx_infer_channel(slot.get("renderer"), slot.get("event"))),
        _vfx_renderer_family(slot.get("renderer")),
    )


def _vfx_slot_similarity_key(slot: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        _vfx_event_group(slot.get("event")),
        str(slot.get("channel") or _vfx_infer_channel(slot.get("renderer"), slot.get("event"))),
        str(slot.get("lane") or _vfx_infer_lane(slot)),
        _vfx_renderer_family(slot.get("renderer")),
    )


def _vfx_demote_blended_raw_slot(raw: dict[str, Any], source_recipe_id: str, seed: int, order: int) -> dict[str, Any]:
    """Turn a runner-up recipe slot into support/accent material.

    This is the compromise between one selected recipe and JSON swamp: we borrow only
    secondary visual jobs from runner-up recipes, then let normal arbitration/budgeting
    keep or discard them. Gameplay is untouched.
    """
    slot = dict(raw)
    slot["source"] = f"blend:{source_recipe_id}"
    slot["importance"] = "accent" if order % 2 else "secondary"
    slot["lane"] = "accent" if order % 2 else "support"
    slot["signatureWeight"] = [0.22, 0.56]
    slot["visualCost"] = [0.12, 0.46]
    # Slightly reduce density so blended material reads as support, not a second main effect.
    if "density" in slot:
        d = slot["density"]
        if isinstance(d, list) and len(d) == 2:
            slot["density"] = [max(0.03, float(d[0]) * 0.55), max(0.08, float(d[1]) * 0.72)]
        else:
            try: slot["density"] = max(0.04, min(0.55, float(d) * 0.70))
            except Exception: pass
    else:
        slot["density"] = [0.10, 0.38]
    if "alpha" not in slot:
        slot["alpha"] = [0.22, 0.62]
    if "duration" in slot:
        dur = slot["duration"]
        if isinstance(dur, list) and len(dur) == 2:
            slot["duration"] = [max(2, int(float(dur[0]) * 0.75)), max(3, int(float(dur[1]) * 0.88))]
    slot["phaseOffset"] = [_vfx_unit(seed, f"blend_phase_{order}") * 0.35, _vfx_unit(seed, f"blend_phase_b_{order}") * 0.65]
    return slot


def _vfx_blend_runner_up_slots(top: list[tuple[float, dict[str, Any], list[str]]], selected_id: str, seed: int, base_raw_slots: list[dict[str, Any]], magnitude_class: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not VFX_RECIPE_BLEND_ENABLED or not top or VFX_PROCEDURAL_MAX_EXTRA_SLOTS <= 0:
        return [], []
    max_slots = max(0, min(VFX_PROCEDURAL_MAX_EXTRA_SLOTS, 2 if magnitude_class in {"tiny", "small"} else 4 if magnitude_class == "normal" else 5))
    if max_slots <= 0:
        return [], []
    used = {_vfx_slot_similarity_key(x) for x in base_raw_slots if isinstance(x, dict)}
    extras: list[dict[str, Any]] = []
    debug: list[dict[str, Any]] = []
    order = 0
    for score, recipe, reasons in top[1:max(1, VFX_PROCEDURAL_BLEND_CANDIDATES) + 1]:
        rid = str(recipe.get("id") or "")
        if rid == selected_id:
            continue
        raw_slots = [x for x in (recipe.get("slots") or []) if isinstance(x, dict)]
        # Prefer non-core hit particles / support motion / ambient layers from runner-up recipes.
        raw_slots.sort(key=lambda x: (_vfx_slot_score({**x, "channel": _vfx_infer_channel(x.get("renderer"), x.get("event")), "lane": _vfx_infer_lane(x)}), str(x.get("renderer"))), reverse=True)
        for raw in raw_slots:
            channel = _vfx_infer_channel(raw.get("renderer"), raw.get("event"))
            event_group = _vfx_event_group(raw.get("event"))
            if channel in {"sound", "light"}:
                continue
            # Do not borrow second primary shape from another recipe unless the item is large/signature.
            if magnitude_class not in {"large", "signature"} and channel in {"impactShape", "motionTrail"} and event_group in {"hit", "live"}:
                if len(extras) >= 1:
                    continue
            candidate = _vfx_demote_blended_raw_slot(raw, rid, seed, order)
            key = _vfx_slot_similarity_key(candidate)
            if key in used:
                continue
            used.add(key)
            extras.append(candidate)
            debug.append({"recipeId": rid, "renderer": candidate.get("renderer"), "event": candidate.get("event"), "channel": channel, "score": round(float(score), 3)})
            order += 1
            if len(extras) >= max_slots:
                return extras, debug
    return extras, debug


def _vfx_procedural_raw_slot_pool(pattern: str, roles: set[str], motif: dict[str, Any], magnitude_class: str, seed: int) -> list[dict[str, Any]]:
    """Small procedural composer: not a semantic parser, not a full recipe selector.

    It only adds generic structural layers that are safe for attackPattern/role availability:
    streaks, secondary rings, motes, decay, beam accent, field pulse. Actual art still comes
    from generated role sprites and the selected recipe.
    """
    large = magnitude_class in {"large", "signature"}
    signature = magnitude_class == "signature"
    pattern_l = str(pattern or "").lower()
    out: list[dict[str, Any]] = []
    if "projectile" in roles:
        if any(x in pattern_l for x in ["slash", "beam_slash"]):
            out.append({"event": "active", "renderer": "historyRibbon", "textureRole": "projectile", "channel": "motionTrail", "lane": "support", "importance": "secondary", "density": [0.22, 0.48], "scale": [0.75, 1.35], "alpha": [0.26, 0.58], "duration": [10, 28], "spread": [0.45, 1.05], "source": "procedural:slash_support_ribbon"})
            out.append({"event": "active", "renderer": "beamLine", "textureRole": "projectile", "channel": "motionTrail", "lane": "accent", "importance": "accent", "density": [0.10, 0.34], "scale": [0.65, 1.20], "alpha": [0.18, 0.46], "duration": [5, 16], "spread": [0.25, 0.75], "source": "procedural:slash_light_streak"})
        elif "beam" in pattern_l or "laser" in pattern_l:
            out.append({"event": "beam", "renderer": "beamLine", "textureRole": "projectile", "channel": "motionTrail", "lane": "primary", "importance": "core", "density": [0.30, 0.72], "scale": [1.0, 1.85], "alpha": [0.45, 0.85], "duration": [8, 28], "spread": [0.25, 0.90], "source": "procedural:beam_core_line"})
            out.append({"event": "beam", "renderer": "ambientMotes", "textureRole": "child", "particleRole": "child", "channel": "ambientParticles", "lane": "accent", "importance": "accent", "emissionMode": "wake", "density": [0.12, 0.34], "scale": [0.5, 1.1], "alpha": [0.22, 0.52], "duration": [8, 20], "repeatEvery": [2, 5], "source": "procedural:beam_side_sparks"})
        else:
            out.append({"event": "travel", "renderer": "spriteStampTrail", "textureRole": "projectile", "channel": "motionTrail", "lane": "support", "importance": "secondary", "density": [0.18, 0.46], "scale": [0.65, 1.25], "alpha": [0.22, 0.55], "duration": [8, 22], "source": "procedural:travel_stamp_support"})
    if "impact" in roles:
        out.append({"event": "hit", "renderer": "impactRing", "textureRole": "impact", "particleRole": "child", "channel": "impactShape", "lane": "support", "importance": "secondary", "density": [0.18, 0.50], "scale": [0.9, 2.2 if large else 1.55], "alpha": [0.30, 0.72], "duration": [6, 18], "spread": [0.35, 1.15], "source": "procedural:impact_secondary_ring"})
        out.append({"event": "hit", "renderer": "impactSpriteFlash", "textureRole": "impact", "particleRole": "child", "channel": "impactShape", "lane": "accent", "importance": "accent", "density": [0.08, 0.24], "scale": [0.85, 1.85], "alpha": [0.25, 0.68], "duration": [4, 12], "source": "procedural:impact_snap_flash"})
    if "child" in roles or "impact" in roles:
        out.append({"event": "hit", "renderer": "childSpriteMotes", "textureRole": "impact", "particleRole": "child", "channel": "impactParticles", "lane": "accent", "importance": "accent", "emissionMode": "cone", "density": [0.18, 0.58 if large else 0.38], "scale": [0.45, 1.15], "alpha": [0.28, 0.72], "duration": [10, 32], "spread": [0.55, 1.65], "source": "procedural:impact_child_motes"})
        if signature:
            out.append({"event": "kill", "renderer": "ambientMotes", "textureRole": "impact", "particleRole": "child", "channel": "decaySmoke", "lane": "accent", "importance": "accent", "emissionMode": "spiral", "density": [0.14, 0.42], "scale": [0.65, 1.45], "alpha": [0.20, 0.54], "duration": [18, 52], "spread": [0.75, 1.85], "source": "procedural:signature_spiral_decay"})
    if "field" in roles or "field" in pattern_l:
        out.append({"event": "loop", "renderer": "fieldPulse", "textureRole": "field", "particleRole": "child", "channel": "coreGlow", "lane": "primary", "importance": "core", "density": [0.22, 0.60], "scale": [0.95, 2.25], "alpha": [0.28, 0.72], "duration": [20, 60], "spread": [0.55, 1.35], "source": "procedural:field_core_pulse"})
    # A tiny light cue makes layered recipes read cleaner, but only as cue and only for large-ish effects.
    if large:
        out.append({"event": "hit", "renderer": "lightCue", "textureRole": "impact", "channel": "light", "lane": "cue", "importance": "accent", "density": [0.10, 0.25], "scale": [0.8, 1.6], "alpha": [0.35, 0.8], "duration": [4, 10], "source": "procedural:impact_light_cue"})
    return out


def _vfx_add_procedural_slots(base_raw_slots: list[dict[str, Any]], pattern: str, roles: set[str], motif: dict[str, Any], magnitude_class: str, seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not VFX_PROCEDURAL_COMPOSE or VFX_PROCEDURAL_MAX_EXTRA_SLOTS <= 0:
        return [], []
    max_slots = max(0, min(VFX_PROCEDURAL_MAX_EXTRA_SLOTS, 1 if magnitude_class in {"tiny", "small"} else 3 if magnitude_class == "normal" else 5))
    if max_slots <= 0:
        return [], []
    base_keys = {_vfx_slot_similarity_key(x) for x in base_raw_slots if isinstance(x, dict)}
    pool = _vfx_procedural_raw_slot_pool(pattern, roles, motif, magnitude_class, seed)
    # Weighted but stable. Prefer different channels/lanes/families from existing base slots.
    scored: list[tuple[float, dict[str, Any]]] = []
    for idx, raw in enumerate(pool):
        key = _vfx_slot_similarity_key(raw)
        if key in base_keys:
            continue
        chance = VFX_PROCEDURAL_CHANCE
        u = _vfx_unit(seed, f"proc_chance_{idx}_{raw.get('renderer')}")
        if u > chance and magnitude_class not in {"large", "signature"}:
            continue
        score = _vfx_slot_score({**raw, "channel": raw.get("channel") or _vfx_infer_channel(raw.get("renderer"), raw.get("event")), "lane": raw.get("lane") or _vfx_infer_lane(raw)})
        # Stable jitter so the same item does not always use the same procedural accent.
        score += (_vfx_unit(seed, f"proc_score_{idx}") - 0.5) * 18.0
        scored.append((score, raw))
    scored.sort(key=lambda x: x[0], reverse=True)
    chosen: list[dict[str, Any]] = []
    debug: list[dict[str, Any]] = []
    used = set(base_keys)
    for score, raw in scored:
        key = _vfx_slot_similarity_key(raw)
        if key in used:
            continue
        used.add(key)
        chosen.append(raw)
        debug.append({"renderer": raw.get("renderer"), "event": raw.get("event"), "channel": raw.get("channel"), "lane": raw.get("lane"), "source": raw.get("source"), "score": round(score, 3)})
        if len(chosen) >= max_slots:
            break
    return chosen, debug



def _vfx_runtime_plan_direct_manifest(data: dict[str, Any], recipe_key_value: str, reroll_salt: Any = "") -> dict[str, Any] | None:
    if not VFX_RUNTIME_INTENT_FIRST:
        return None
    rp = data.get("runtimePlan") if isinstance(data.get("runtimePlan"), dict) else {}
    has_runtime_plan = isinstance(rp, dict) and bool(rp)
    calls = rp.get("engineCalls") if isinstance(rp.get("engineCalls"), list) else []
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    if not attack.get("enabled"):
        return None
    if has_runtime_plan and not calls:
        calls = []
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    vi = rp.get("visualIntent") if isinstance(rp.get("visualIntent"), dict) else {}
    power = float(attack.get("powerBudget") or data.get("gameplay", {}).get("powerBudget") or 1.0) if isinstance(data.get("gameplay"), dict) else float(attack.get("powerBudget") or 1.0)
    seed = _vfx_seed_int(recipe_key_value, data.get("id"), "runtime_intent", reroll_salt)
    effect = str(attack.get("effect") or "none").lower()
    onhit = str(attack.get("onHit") or "none").lower()
    split_count = int(float(attack.get("splitCount") or 0))
    trail_len = int(float(attack.get("trailLength") or 0))
    burst_cap = int(float(attack.get("burstDustCap") or 0))
    slots_raw: list[dict[str, Any]] = []
    authored_raw, authored_debug = _vfx_authored_cue_raw_slots(data)
    slots_raw.extend(authored_raw)
    # Travel slot: small by default; no parent-inherited beam/history ribbons.
    if trail_len > 0 and effect not in {"none", ""}:
        slots_raw.append({
            "event": "travel", "renderer": "projectileAfterimage", "textureRole": "projectile",
            "variants": [0, 1], "scale": [0.65, 1.05], "density": [0.10, 0.24], "duration": [5, min(18, max(6, trail_len))],
            "alpha": [0.18, 0.42], "stage": "loop", "backend": "Sprite", "anchor": "self", "blend": "alpha",
            "layer": "BeforeProjectiles", "budgetWeight": [0.45, 0.9], "source": "runtimePlan:travel"
        })
    # Hit feedback is a contact flash/chips/dust unless the LLM explicitly requested real child projectiles.
    if onhit not in {"none", ""} or burst_cap > 0 or str(vi.get("impact") or visual.get("impactVfx") or "").strip():
        slots_raw.append({
            "event": "hit", "renderer": "impactSpriteFlash", "textureRole": "impact",
            "variants": [0, 1], "scale": [0.85, min(1.75, 0.98 + power * 0.20)], "density": [0.10, 0.26], "duration": [6, 13],
            "alpha": [0.45, 0.86], "stage": "impact", "backend": "Sprite", "anchor": "hitPoint", "blend": "alpha",
            "layer": "BeforeProjectiles", "budgetWeight": [0.60, 1.05], "source": "runtimePlan:impact_readable_flash_v0.4.174"
        })
    if False and split_count > 0 and attack.get("maxChildProjectiles", 0):
        # v0.4.8: real gameplay children are visible by themselves. Do not duplicate them
        # with VFX childSpriteMotes, or 3 authored shards look like 9+ fragments on screen.
        pass
    # v0.4.3: runtimePlan presence is authoritative even if it requests no visible VFX.
    # Return an empty tiny manifest instead of falling back to legacy recipe roulette.
    effect_mag = 0.0 if not slots_raw else max(0.08, min(0.38 if power <= 1.8 else 0.48, 0.12 + power * 0.08 + split_count * 0.015))
    budget = {
        "renderQuality": VFX_RENDER_QUALITY, "quality": VFX_RENDER_QUALITY, "effectMagnitude": round(effect_mag, 3),
        "visualBudgetClass": "small" if effect_mag < 0.42 else "normal", "emergencyCap": True,
        "maxParticlesPerTick": min(VFX_EMERGENCY_MAX_PARTICLES_PER_TICK, 80),
        "maxParticlesTotal": min(VFX_EMERGENCY_MAX_PARTICLES_TOTAL, 1800),
        "maxDrawCalls": min(VFX_EMERGENCY_MAX_DRAW_CALLS, 90),
        "spawnRateMultiplier": 0.0 if effect_mag <= 0 else (0.65 if power <= 1.8 else 0.9),
        "enableSoftGlow": effect in {"star", "flame", "electric", "lunar", "holy", "shadow"},
        "enablePointSparks": effect not in {"none", "dust", "sand", "smoke"},
        "enablePersistentSmoke": False,
    }
    slots = [_vfx_compile_slot(slot, seed, i, power, effect_mag) for i, slot in enumerate(slots_raw)]
    slots = _vfx_arbitrate_slots(slots, str(budget.get("visualBudgetClass") or "small"))
    provenance = attack.get("runtimeAuthoringProvenance") if isinstance(attack.get("runtimeAuthoringProvenance"), dict) else {}
    effect_lineage = {
        "mode": "runtime_plan_direct",
        "gameplayChildren": provenance.get("gameplayChildren", {}),
        "pureVfx": provenance.get("pureVfx", {}),
        "fieldSources": provenance.get("fieldSources", {}),
        "note": "VFX slots here are visual execution of runtimePlan intent; real damaging children are only those reported under gameplayChildren.",
    }
    manifest = {
        "schema": "infini.vfx.hybrid.v14",
        "recipeId": "runtime_intent_v0_4_8",
        "playbackMode": "Hybrid",
        "seed": seed,
        "confidence": 0.88,
        "effectMagnitude": round(effect_mag, 3),
        "visualBudgetClass": budget["visualBudgetClass"],
        "motif": _vfx_motif_from_data(data, _vfx_words(" ".join(str(x or "") for x in [data.get("name"), visual.get("vfxIntent"), attack.get("vfxIntent"), vi.get("vfxIntent")])) , str(attack.get("pattern") or "thrown_simple")),
        "overlayPolicy": "LocalOnly",
        "budget": budget,
        "slots": slots,
        "debug": {
            "composition": {
                "mode": "runtime_plan_direct_authored_cues" if authored_raw else "runtime_plan_direct", "baseRecipeId": "runtime_intent_v0_4_8",
                "preArbitrationSlotCount": len(slots_raw), "postArbitrationSlotCount": len(slots),
                "authoredCueSlots": authored_debug,
                "runtimePlanFunctions": [str(c.get("fn") or "") for c in calls if isinstance(c, dict)],
            },
            "pattern": str(attack.get("pattern") or attack.get("attackPattern") or ""),
            "roles": sorted(_vfx_available_roles(data)),
            "selectedScore": 1000.0,
            "selectedReasons": ["runtimePlan.engineCalls present", "legacy recipe selector bypassed", "authored visual cues compiled" if authored_raw else ("empty runtime VFX is allowed" if not slots_raw else "runtime VFX slots compiled")],
            "effectLineage": effect_lineage,
            "topCandidates": [], "wordProbe": [],
            "rerollSalt": str(reroll_salt or data.get("recipeMeta", {}).get("vfxRerollSalt", "") or ""),
        },
    }
    return manifest



def _vfx_authored_cue_event(raw: Any) -> str:
    e = str(raw or "").strip()
    return {
        "while_held": "active",
        "while_equipped": "active",
        "on_use": "active",
        "on_alt_use": "active",
        "on_projectile_impact": "hit",
        "on_hit": "hit",
    }.get(e, e if e in {"travel", "active", "tick", "hit", "kill", "expire"} else "active")


def _vfx_authored_cue_raw_slots(data: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Convert model-authored visual_effect_cue contracts into raw VFX slots.

    This is intentionally a narrow visual-only bridge: it does not infer cues from prose
    and does not create gameplay. The model must author visual_effect_cue explicitly.
    """
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    kit = data.get("visualKit") if isinstance(data.get("visualKit"), dict) else {}
    raw_cues: list[Any] = []
    for source in (attack, kit, visual, data):
        cues = source.get("vfxCues") if isinstance(source, dict) else None
        if isinstance(cues, list):
            raw_cues.extend(cues)
    if not raw_cues:
        return [], []
    surface = vfx_director_surface()
    allowed_renderer = set(surface["rendererKind"])
    allowed_channel = set(surface["channel"])
    allowed_lane = set(surface["lane"])
    allowed_roles = set(surface["textureRole"])
    allowed_emission = set(surface["emissionMode"])
    allowed_particles = set(surface["particleSystemId"])
    out: list[dict[str, Any]] = []
    debug: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for idx, cue in enumerate(raw_cues[:10]):
        if not isinstance(cue, dict):
            continue
        ev = _vfx_authored_cue_event(cue.get("event"))
        renderer = str(cue.get("rendererKind") or cue.get("renderer") or "").strip()
        if renderer not in allowed_renderer:
            renderer = "impactRing" if ev in {"hit", "kill", "expire"} else "projectileAfterimage"
        channel = str(cue.get("channel") or "").strip()
        if channel not in allowed_channel:
            channel = "impactShape" if ev in {"hit", "kill", "expire"} else "motionTrail"
        lane = str(cue.get("lane") or "").strip()
        if lane not in allowed_lane:
            lane = "primary" if idx == 0 else "accent"
        texture_role = str(cue.get("textureRole") or "projectile").strip()
        if texture_role not in allowed_roles:
            texture_role = "projectile"
        particle_role = str(cue.get("particleRole") or texture_role).strip()
        if particle_role not in allowed_roles:
            particle_role = "child"
        emission = str(cue.get("emissionMode") or "").strip()
        if emission not in allowed_emission:
            emission = "ring" if channel in {"impactShape", "impactParticles"} else "wake"
        pid = str(cue.get("particleSystemId") or "").strip()
        if pid not in allowed_particles:
            pid = "pl:glow" if channel in {"coreGlow", "light"} else "pl:spark"
        key = (ev, renderer, channel, lane)
        if key in seen:
            continue
        seen.add(key)
        def n(name: str, fallback: float) -> Any:
            try:
                value = cue.get(name)
                return fallback if value in (None, "") else float(value)
            except Exception:
                return fallback
        slot = {
            "event": ev,
            "renderer": renderer,
            "rendererKind": renderer,
            "backend": "Auto",
            "textureRole": texture_role,
            "particleRole": particle_role,
            "anchor": str(cue.get("anchor") or ("hitPoint" if ev in {"hit", "kill", "expire"} else "self")),
            "channel": channel,
            "lane": lane,
            "emissionMode": emission,
            "blend": str(cue.get("blend") or ("additive" if channel in {"coreGlow", "light"} or renderer in {"beamLine", "lightCue"} else "alpha")),
            "particleSystemId": pid,
            "scale": max(0.15, min(5.0, n("scale", 1.0))),
            "density": max(0.0, min(1.0, n("density", 0.35))),
            "duration": int(max(3, min(120, round(n("duration", 16))))),
            "alpha": max(0.0, min(1.0, n("alpha", 0.65))),
            "spread": max(0.0, min(2.0, n("spread", 0.6))),
            "jitter": max(0.0, min(1.5, n("jitter", 0.25))),
            "startTick": int(max(0, min(120, round(n("startTick", 0))))),
            "repeatEvery": int(max(0, min(120, round(n("repeatEvery", 0))))),
            "importance": str(cue.get("importance") or ("core" if lane == "primary" else "accent")),
            "source": "authoredCue",
            "signatureWeight": 0.72 if lane == "primary" else 0.36,
            "visualCost": 0.22 if lane == "primary" else 0.12,
        }
        out.append(slot)
        debug.append({"event": ev, "rendererKind": renderer, "channel": channel, "lane": lane, "particleSystemId": pid, "note": str(cue.get("note") or "")[:80]})
    return out[:8], debug[:8]

def attach_hybrid_vfx_manifest(data: dict[str, Any], recipe_key_value: str, reroll_salt: Any = "", parent_a: dict[str, Any] | None = None, parent_b: dict[str, Any] | None = None, llm_director: Any = None) -> dict[str, Any]:
    """v0.3.16: dirty hybrid VFX selector.

    This intentionally combines mechanical filters, weak LLM hints, recipe ranges and
    stable seed mutation, then freezes the result into attack.vfxManifestJson.
    C# runtime only executes the manifest; it must not parse prompt prose every tick.
    """
    if not VFX_SELECTOR_ENABLED:
        return data
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    if not attack.get("enabled"):
        return data
    direct_manifest = _vfx_runtime_plan_direct_manifest(data, recipe_key_value, reroll_salt)
    if isinstance(direct_manifest, dict):
        data["vfxManifest"] = direct_manifest
        attack["vfxManifestJson"] = json.dumps(direct_manifest, ensure_ascii=False, separators=(",", ":"))
        data["attack"] = attack
        data.setdefault("debug", {})["vfxManifest"] = json.dumps(direct_manifest, ensure_ascii=False)[:12000]
        data.setdefault("debug", {})["vfxPath"] = "runtime_plan_direct_empty" if not direct_manifest.get("slots") else "runtime_plan_direct"
        return data
    force_recipe_id = str((data.get("recipeMeta") or {}).get("vfxForcedRecipeId") or (data.get("debug") or {}).get("vfxForcedRecipeId") or "").strip()
    forced_recipe = _vfx_find_recipe(force_recipe_id) if force_recipe_id else None
    if forced_recipe is not None:
        return _vfx_manifest_from_recipe(data, forced_recipe, recipe_key_value, reroll_salt, forced=True)
    director_manifest = try_llm_vfx_director(parent_a, parent_b, data, recipe_key_value, llm_director)
    if isinstance(director_manifest, dict) and director_manifest.get("slots"):
        data["vfxManifest"] = director_manifest
        attack["vfxManifestJson"] = json.dumps(director_manifest, ensure_ascii=False, separators=(",", ":"))
        data["attack"] = attack
        data.setdefault("debug", {})["vfxManifest"] = json.dumps(director_manifest, ensure_ascii=False)[:12000]
        data.setdefault("debug", {})["vfxLlmDirector"] = "used"
        data.setdefault("debug", {})["vfxPath"] = "llm_director"
        return data
    if VFX_LLM_DIRECTOR_ENABLED:
        data.setdefault("debug", {})["vfxLlmDirector"] = data.setdefault("debug", {}).get("vfxLlmDirectorError") or "fallback"
    data.setdefault("debug", {}).setdefault("vfxPath", "legacy_recipe_fallback")
    # All dirty selection/randomness must freeze at generation/reroll time.
    # selector_key is allowed to change only when the user explicitly rerolls VFX.
    selector_key = f"{recipe_key_value}|vfxsalt={str(reroll_salt or data.get('recipeMeta', {}).get('vfxRerollSalt', '') or '')}"
    if not get_vfx_recipes():
        data.setdefault("debug", {})["vfxSelectorError"] = "no vfx_morph_recipes.json recipes loaded"
        return data
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    kit = data.get("visualKit") if isinstance(data.get("visualKit"), dict) else {}
    pattern = str(attack.get("pattern") or attack.get("attackPattern") or "basic").strip() or "basic"
    roles = _vfx_available_roles(data)
    if not roles:
        roles.add("projectile")
    parent_effect_profile = _vfx_parent_effect_profile(data, parent_a, parent_b)
    # Keep raw generated-parent slots only in transient memory for composition; the frozen manifest/debug
    # stores the compact public profile, not full parent manifests.
    if isinstance(parent_effect_profile, dict) and isinstance(parent_a, dict):
        raw_parent_slots = []
        for parent_item in [x for x in (parent_a, parent_b) if isinstance(x, dict)]:
            pm = _vfx_manifest_from_parent_item(parent_item)
            raw_parent_slots.extend([x for x in (pm.get("slots") or []) if isinstance(x, dict)][:4])
        if raw_parent_slots:
            parent_effect_profile = dict(parent_effect_profile)
            parent_effect_profile["_rawParentSlots"] = raw_parent_slots[:8]
    parent_effect_words = " ".join(str(x) for x in ((parent_effect_profile.get("effectTags") if isinstance(parent_effect_profile, dict) else []) or []) + ((parent_effect_profile.get("suggestedRenderers") if isinstance(parent_effect_profile, dict) else []) or []))
    text_parts = [
        data.get("name"), data.get("tooltip"), parent_effect_words,
        kit.get("styleGuide"), kit.get("silhouetteSummary"), kit.get("vfxIntent"),
        kit.get("projectileVfx"), kit.get("impactVfx"), kit.get("childVfx"), kit.get("fieldVfx"),
        visual.get("vfxIntent"), visual.get("projectileVfx"), visual.get("impactVfx"), visual.get("childVfx"), visual.get("fieldVfx"),
        visual.get("vfxScaleHint"), visual.get("vfxRhythmHint"), visual.get("vfxAvoid"), _stringish(visual.get("vfxMaterialHints"), ""),
        attack.get("vfxIntent"), attack.get("projectileVfx"), attack.get("impactVfx"), attack.get("childVfx"), attack.get("fieldVfx"),
        attack.get("vfxScaleHint"), attack.get("vfxRhythmHint"), attack.get("vfxAvoid"), _stringish(attack.get("vfxMaterialHints"), ""),
        attack.get("projectileSpritePrompt"), attack.get("impactSpritePrompt"), attack.get("childSpritePrompt"), attack.get("fieldSpritePrompt"),
        attack.get("visualAnimationPlan"), attack.get("projectileTrail"), attack.get("projectileImpact"), attack.get("projectileChild"), attack.get("toyIdentity"), attack.get("specialRule"),
    ]
    words = _vfx_words(" ".join(str(x or "") for x in text_parts))
    power = float(attack.get("powerBudget") or data.get("gameplay", {}).get("powerBudget") or 1.0) if isinstance(data.get("gameplay"), dict) else float(attack.get("powerBudget") or 1.0)
    mundane_profile = _vfx_mundane_duplicate_profile(data, pattern, words, power)
    scored: list[tuple[float, dict[str, Any], list[str]]] = []
    for recipe in get_vfx_recipes():
        rid = str(recipe.get("id") or "")
        patterns = {str(x) for x in (recipe.get("compatiblePatterns") or [])}
        forbidden = {str(x) for x in (recipe.get("forbiddenPatterns") or [])}
        if pattern in forbidden:
            continue
        if patterns and pattern not in patterns and "basic" not in patterns:
            continue
        required = {str(x) for x in (recipe.get("requiredRoles") or []) if str(x)}
        if required and not required.issubset(roles):
            continue
        optional = {str(x) for x in (recipe.get("optionalRoles") or []) if str(x)}
        hints = _vfx_words(" ".join(str(x) for x in (recipe.get("hints") or [])))
        overlap = len(words & hints)
        score = 100.0
        reasons = [f"pattern:{pattern}", "roles:" + "/".join(sorted(roles))]
        if pattern in patterns:
            score += 80.0; reasons.append("exact_pattern")
        if "basic" in patterns and pattern not in patterns:
            score += 15.0; reasons.append("basic_compatible")
        if required:
            score += 24.0 * len(required); reasons.append("required_roles_ok")
        if optional:
            present_optional = len(optional & roles)
            score += 13.0 * present_optional
            if present_optional:
                reasons.append(f"optional_roles:{present_optional}")
        if overlap:
            score += min(70.0, overlap * 7.5 * VFX_SELECTOR_HINT_WEIGHT)
            reasons.append(f"hint_overlap:{overlap}")
        parent_bonus, parent_reasons = _vfx_parent_effect_recipe_bonus(recipe, parent_effect_profile)
        if parent_bonus:
            score += parent_bonus
            reasons.extend(parent_reasons[:3])
        raw_recipe_slots = [x for x in (recipe.get("slots") or []) if isinstance(x, dict)]
        slot_count = len(raw_recipe_slots)
        renderers = [str(x.get("renderer") or "") for x in raw_recipe_slots]
        unique_renderers = len({r.lower() for r in renderers if r})
        if unique_renderers >= 3:
            score += VFX_SELECTOR_NOVELTY_WEIGHT
            reasons.append(f"renderer_variety:{unique_renderers}")
        cost = str(recipe.get("cost") or "medium")
        if cost == "high" and power < 0.85:
            score -= 18.0; reasons.append("high_cost_penalty")
        if cost == "low" and power > 1.35:
            score -= 6.0; reasons.append("low_cost_on_high_power")
        if mundane_profile.get("enabled"):
            if rid.startswith("mundane_") or cost in {"tiny", "low"}:
                score += 70.0; reasons.append("mundane_guard_prefers_small_recipe")
            if cost in {"high", "signature", "ultra"}:
                score -= 145.0; reasons.append("mundane_guard_blocks_heavy_recipe")
            if slot_count > 3:
                score -= (slot_count - 3) * 24.0; reasons.append("mundane_guard_slot_count_penalty")
        jitter = (_vfx_unit(_vfx_seed_int(selector_key, rid), "selector") - 0.5) * VFX_SELECTOR_JITTER
        score += jitter
        scored.append((score, recipe, reasons))
    if not scored:
        # Mechanical fallback manifest: still frozen, but intentionally simple.
        fallback = {
            "schema": "infini.vfx.hybrid.v14",
            "recipeId": "fallback_afterimage_flash",
            "playbackMode": "Auto",
            "seed": _vfx_seed_int(selector_key, "vfx_fallback"),
            "confidence": 0.15,
            "budget": _vfx_budget_for_recipe({"cost": "low"}, power, selector_key, data),
            "slots": [
                {"event": "travel", "renderer": "projectileAfterimage", "textureRole": "projectile", "particleRole": "child", "variant": 0, "scale": 0.9, "density": 0.18, "duration": 8, "alpha": 0.28, "spread": 0.5},
                {"event": "hit", "renderer": "impactSpriteFlash", "textureRole": "impact", "particleRole": "child", "variant": 0, "scale": 1.4, "density": 0.2, "duration": 7, "alpha": 0.55, "spread": 0.5},
            ],
            "debug": {"reason": "no compatible recipe", "pattern": pattern, "roles": sorted(roles)},
        }
        data["vfxManifest"] = fallback
        attack["vfxManifestJson"] = json.dumps(fallback, ensure_ascii=False, separators=(",", ":"))
        data["attack"] = attack
        return data
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:max(1, VFX_SELECTOR_TOP)]
    # Weighted deterministic pick from top candidates, so the best usually wins but recipes do not collapse.
    # Mundane duplicate guard intentionally disables this extra roulette: copper dagger + copper dagger
    # should choose the safest top recipe, not a runner-up with more spectacle.
    selected_score, selected, selected_reasons = top[0]
    if not mundane_profile.get("enabled"):
        total = sum(max(1.0, x[0] - top[-1][0] + 1.0) for x in top)
        cursor = _vfx_unit(_vfx_seed_int(selector_key, "vfx_pick"), "pick") * total
        acc = 0.0
        for score, recipe, reasons in top:
            weight = max(1.0, score - top[-1][0] + 1.0)
            acc += weight
            if cursor <= acc:
                selected_score, selected, selected_reasons = score, recipe, reasons
                break
    seed = _vfx_seed_int(selector_key, selected.get("id"), data.get("id"), pattern)
    budget = _vfx_budget_for_recipe(selected, power, seed, data)
    effect_magnitude = float(budget.get("effectMagnitude") or 0.5)
    budget_class = str(budget.get("visualBudgetClass") or "normal")
    motif = _vfx_motif_from_data(data, words, pattern)
    base_raw_slots = [x for x in (selected.get("slots") or []) if isinstance(x, dict)]
    if mundane_profile.get("enabled"):
        blended_raw, blended_debug = [], []
        procedural_raw, procedural_debug = [], []
    else:
        blended_raw, blended_debug = _vfx_blend_runner_up_slots(top, str(selected.get("id") or ""), seed, base_raw_slots, budget_class)
        procedural_raw, procedural_debug = _vfx_add_procedural_slots(base_raw_slots + blended_raw, pattern, roles, motif, budget_class, seed)
    inherited_raw, inherited_debug = _vfx_parent_inherited_raw_slots(parent_effect_profile, pattern, roles, budget_class, seed)
    authored_raw, authored_debug = _vfx_authored_cue_raw_slots(data)
    if mundane_profile.get("enabled"):
        inherited_raw, inherited_debug = [], []
    composed_raw_slots = authored_raw + base_raw_slots + blended_raw + procedural_raw + inherited_raw
    pre_arbitration_slot_count = len(composed_raw_slots)
    slots = [_vfx_compile_slot(slot, seed, i, power, effect_magnitude) for i, slot in enumerate(composed_raw_slots) if isinstance(slot, dict)]
    slots = _vfx_arbitrate_slots(slots, budget_class)
    slots = _vfx_trim_mundane_slots(slots, mundane_profile)
    if not slots:
        slots = [{"event": "travel", "renderer": "projectileAfterimage", "textureRole": "projectile", "particleRole": "child", "variant": 0, "scale": 0.9, "density": 0.18, "duration": 8, "alpha": 0.28, "spread": 0.5, "source": "fallback"}]
    top_debug = [[str(r.get("id")), round(float(score), 3), reasons[:6]] for score, r, reasons in top]
    confidence = max(0.05, min(0.98, (selected_score - (top[-1][0] if len(top) > 1 else selected_score - 20.0)) / 90.0 + 0.45))
    provenance = attack.get("runtimeAuthoringProvenance") if isinstance(attack.get("runtimeAuthoringProvenance"), dict) else {}
    effect_lineage = {
        "mode": "recipe_selector",
        "selectedRecipeId": str(selected.get("id") or "unknown"),
        "gameplayChildren": provenance.get("gameplayChildren", {}),
        "pureVfx": provenance.get("pureVfx", {}),
        "fieldSources": provenance.get("fieldSources", {}),
        "note": "VFX slots are selected visual execution, not gameplay-authoring source of truth.",
    }
    manifest = {
        "schema": "infini.vfx.hybrid.v14",
        "recipeId": str(selected.get("id") or "unknown"),
        "playbackMode": _vfx_playback_mode_for_recipe(selected),
        "seed": seed,
        "confidence": round(confidence, 3),
        "effectMagnitude": effect_magnitude,
        "visualBudgetClass": budget.get("visualBudgetClass"),
        "motif": motif,
        "parentEffectProfile": {k: v for k, v in parent_effect_profile.items() if k != "_rawParentSlots"} if isinstance(parent_effect_profile, dict) else {},
        "overlayPolicy": "LocalOnly",
        "budget": budget,
        "slots": slots,
        "debug": {
            "composition": {
                "mode": "authored_cues_plus_recipe" if authored_debug else ("mundane_guard" if mundane_profile.get("enabled") else ("recipe_blend_plus_procedural" if (blended_debug or procedural_debug) else "recipe_only")),
                "baseRecipeId": str(selected.get("id") or "unknown"),
                "preArbitrationSlotCount": pre_arbitration_slot_count,
                "postArbitrationSlotCount": len(slots),
                "blendedSlots": blended_debug,
                "proceduralSlots": procedural_debug,
                "authoredCueSlots": authored_debug,
                "inheritedParentSlots": inherited_debug,
                "mundaneProfile": mundane_profile,
                "parentEffectProfile": {k: v for k, v in parent_effect_profile.items() if k != "_rawParentSlots"} if isinstance(parent_effect_profile, dict) else {},
            },
            "pattern": pattern,
            "roles": sorted(roles),
            "selectedScore": round(float(selected_score), 3),
            "selectedReasons": selected_reasons[:10],
            "topCandidates": top_debug if VFX_SELECTOR_DEBUG else [],
            "wordProbe": sorted(list(words))[:40] if VFX_SELECTOR_DEBUG else [],
            "rerollSalt": str(reroll_salt or data.get("recipeMeta", {}).get("vfxRerollSalt", "") or ""),
            "effectLineage": effect_lineage,
        }
    }
    data["vfxManifest"] = manifest
    attack["vfxManifestJson"] = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"))
    data["attack"] = attack
    data.setdefault("debug", {})["vfxManifest"] = json.dumps(manifest, ensure_ascii=False)[:12000]
    return data




def _vfx_find_recipe(recipe_id: str) -> dict[str, Any] | None:
    rid = str(recipe_id or "").strip()
    if not rid:
        return None
    for recipe in get_vfx_recipes():
        if str(recipe.get("id") or "") == rid:
            return recipe
    return None


def _vfx_manifest_from_recipe(data: dict[str, Any], recipe: dict[str, Any], recipe_key_value: str, reroll_salt: Any = "", forced: bool = False) -> dict[str, Any]:
    attack = data.setdefault("attack", {}) if isinstance(data.get("attack"), dict) else data.setdefault("attack", {})
    pattern = normalize_attack_pattern(attack.get("pattern") or attack.get("attackPattern") or attack.get("Pattern") or "basic")
    selector_key = f"{recipe_key_value}|vfxsalt={str(reroll_salt or data.get('recipeMeta', {}).get('vfxRerollSalt', '') or '')}"
    power = float(attack.get("powerBudget") or data.get("gameplay", {}).get("powerBudget") or 1.0) if isinstance(data.get("gameplay"), dict) else float(attack.get("powerBudget") or 1.0)
    seed = _vfx_seed_int(selector_key, recipe.get("id"), data.get("id"), pattern)
    budget = _vfx_budget_for_recipe(recipe, power, seed, data)
    effect_magnitude = float(budget.get("effectMagnitude") or 0.5)
    slots = [_vfx_compile_slot(slot, seed, i, power, effect_magnitude) for i, slot in enumerate(recipe.get("slots") or []) if isinstance(slot, dict)]
    slots = _vfx_arbitrate_slots(slots, str(budget.get("visualBudgetClass") or "normal"))
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    kit = data.get("visualKit") if isinstance(data.get("visualKit"), dict) else {}
    words = _vfx_words(" ".join(str(x or "") for x in [data.get("name"), data.get("tooltip"), kit.get("styleGuide"), kit.get("vfxIntent"), visual.get("vfxIntent"), attack.get("vfxIntent"), attack.get("projectileSpritePrompt"), attack.get("impactSpritePrompt"), attack.get("visualAnimationPlan")]))
    provenance = attack.get("runtimeAuthoringProvenance") if isinstance(attack.get("runtimeAuthoringProvenance"), dict) else {}
    effect_lineage = {
        "mode": "forced_recipe" if forced else "direct_recipe",
        "selectedRecipeId": str(recipe.get("id") or "unknown"),
        "gameplayChildren": provenance.get("gameplayChildren", {}),
        "pureVfx": provenance.get("pureVfx", {}),
        "fieldSources": provenance.get("fieldSources", {}),
        "note": "VFX slots are recipe-selected visuals, not gameplay-authoring source of truth.",
    }
    manifest = {
        "schema": "infini.vfx.hybrid.v14",
        "recipeId": str(recipe.get("id") or "unknown"),
        "playbackMode": _vfx_playback_mode_for_recipe(recipe),
        "seed": seed,
        "confidence": 0.99 if forced else 0.72,
        "effectMagnitude": effect_magnitude,
        "visualBudgetClass": budget.get("visualBudgetClass"),
        "motif": _vfx_motif_from_data(data, words, pattern),
        "overlayPolicy": "LocalOnly",
        "budget": budget,
        "slots": slots,
        "debug": {
            "composition": {
                "mode": "forced_recipe" if forced else "direct_recipe",
                "baseRecipeId": str(recipe.get("id") or "unknown"),
                "preArbitrationSlotCount": len(recipe.get("slots") or []),
                "postArbitrationSlotCount": len(slots),
                "blendedSlots": [],
                "proceduralSlots": [],
            },
            "pattern": pattern,
            "roles": sorted(_vfx_available_roles(data)),
            "selectedScore": 999.0 if forced else 0.0,
            "selectedReasons": ["forced_recipe" if forced else "direct_recipe"],
            "topCandidates": [],
            "wordProbe": [],
            "rerollSalt": str(reroll_salt or data.get("recipeMeta", {}).get("vfxRerollSalt", "") or ""),
            "effectLineage": effect_lineage,
        }
    }
    data["vfxManifest"] = manifest
    attack["vfxManifestJson"] = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"))
    data["attack"] = attack
    data.setdefault("debug", {})["vfxManifest"] = json.dumps(manifest, ensure_ascii=False)[:12000]
    return data


def compact_vfx_recipe_card(recipe: dict[str, Any]) -> dict[str, Any]:
    slots = recipe.get("slots") if isinstance(recipe.get("slots"), list) else []
    return {
        "id": recipe.get("id", ""),
        "compatiblePatterns": recipe.get("compatiblePatterns", []),
        "requiredRoles": recipe.get("requiredRoles", []),
        "optionalRoles": recipe.get("optionalRoles", []),
        "forbiddenPatterns": recipe.get("forbiddenPatterns", []),
        "cost": recipe.get("cost", "medium"),
        "playbackMode": _vfx_playback_mode_for_recipe(recipe),
        "hints": recipe.get("hints", []),
        "slotCount": len(slots),
        "renderers": [str(x.get("renderer", "")) for x in slots if isinstance(x, dict)],
        "backends": sorted({str(x.get("backend") or _vfx_default_backend(x.get("event"), x.get("renderer"))) for x in slots if isinstance(x, dict)}),
        "stages": sorted({str(x.get("stage") or _vfx_event_stage(x.get("event"), x.get("renderer"))) for x in slots if isinstance(x, dict)}),
        "bakedEligibleSlots": sum(1 for x in slots if isinstance(x, dict) and _vfx_should_bake_slot(x, str(x.get("event") or ""), str(x.get("renderer") or ""), str(x.get("backend") or _vfx_default_backend(x.get("event"), x.get("renderer"))))),
        "expandedFromMacros": bool(recipe.get("expandedFromMacros")),
        "useMacros": recipe.get("useMacros", []),
        "macroIds": sorted({str(x.get("macroId")) for x in slots if isinstance(x, dict) and x.get("macroId")}),
    }

VFX_MAGNITUDE_CLASSES = {
    "tiny": {"range": [0.00, 0.22], "meaning": "barely magical / cheap / utility item", "expected": "core silhouette + small hit"},
    "small": {"range": [0.22, 0.42], "meaning": "minor generated effect", "expected": "short trail + readable hit"},
    "normal": {"range": [0.42, 0.66], "meaning": "default generated weapon VFX", "expected": "main trail + impact + light residue"},
    "large": {"range": [0.66, 0.86], "meaning": "rare/weird/high-power VFX", "expected": "layered trail + bigger impact + decay"},
    "signature": {"range": [0.86, 1.00], "meaning": "signature item effect", "expected": "full stack; emergency caps only"},
}

def _vfx_layer_kind_for_renderer(renderer: Any) -> str:
    r = str(renderer or "").lower()
    if "sound" in r:
        return "SoundCueLayer"
    if "light" in r:
        return "LightCueLayer"
    if "actor" in r or "playerghost" in r:
        return "ActorAfterimageLayer"
    if "ribbon" in r or "trail" in r or "beam" in r or "tip" in r or "history" in r:
        return "PrimitiveTrailLayer"
    if "afterimage" in r or "ghost" in r or "stamp" in r or "field" in r or "wavy" in r or "cloth" in r:
        return "SpriteGhostLayer"
    if "ambient" in r or "mote" in r or "spark" in r or "smoke" in r or "particle" in r or "burst" in r or "ring" in r:
        return "ParticleBurstLayer"
    return "ParticleEmitterLayer"

def _vfx_slot_cost_estimate(slot: dict[str, Any]) -> dict[str, Any]:
    density = float(slot.get("density") or 0.0)
    duration = int(float(slot.get("duration") or 1))
    weight = float(slot.get("budgetWeight") or 1.0)
    renderer = str(slot.get("renderer") or "")
    layer = _vfx_layer_kind_for_renderer(renderer)
    draw_calls = 0
    particles = 0
    if layer in {"PrimitiveTrailLayer", "SpriteGhostLayer", "ActorAfterimageLayer"}:
        draw_calls = max(1, int(round(1 + density * 12)))
    if layer in {"ParticleBurstLayer", "ParticleEmitterLayer"}:
        particles = max(1, int(round((2 + density * 28) * weight)))
    if layer == "LightCueLayer":
        draw_calls = 0
    if layer == "SoundCueLayer":
        draw_calls = 0
    baked = slot.get("bakedCommands") if isinstance(slot.get("bakedCommands"), list) else []
    return {
        "layerKind": layer,
        "estimatedDrawCalls": draw_calls,
        "estimatedParticles": particles + len(baked),
        "duration": duration,
        "bakedCommands": len(baked),
    }

def vfx_manifest_effect_stack(manifest: dict[str, Any]) -> dict[str, Any]:
    slots = [s for s in (manifest.get("slots") or []) if isinstance(s, dict)]
    rows = []
    stage_groups: dict[str, list[dict[str, Any]]] = {}
    backend_groups: dict[str, list[dict[str, Any]]] = {}
    kind_groups: dict[str, list[dict[str, Any]]] = {}
    total_draw = 0
    total_particles = 0
    for idx, slot in enumerate(slots):
        cost = _vfx_slot_cost_estimate(slot)
        stage = str(slot.get("stage") or _vfx_event_stage(slot.get("event"), slot.get("renderer")))
        backend = str(slot.get("backend") or _vfx_default_backend(slot.get("event"), slot.get("renderer")))
        row = {
            "index": idx,
            "event": slot.get("event"),
            "stage": stage,
            "backend": backend,
            "renderer": slot.get("renderer"),
            "layerKind": cost["layerKind"],
            "textureRole": slot.get("textureRole"),
            "particleRole": slot.get("particleRole"),
            "duration": slot.get("duration"),
            "density": slot.get("density"),
            "scale": slot.get("scale"),
            "estimatedDrawCalls": cost["estimatedDrawCalls"],
            "estimatedParticles": cost["estimatedParticles"],
            "bakedCommands": cost["bakedCommands"],
            "minQuality": slot.get("minQuality", "Low"),
        }
        rows.append(row)
        stage_groups.setdefault(stage, []).append(row)
        backend_groups.setdefault(backend, []).append(row)
        kind_groups.setdefault(cost["layerKind"], []).append(row)
        total_draw += int(cost["estimatedDrawCalls"])
        total_particles += int(cost["estimatedParticles"])
    return {
        "schema": "infini.vfx.effect_stack.v0",
        "recipeId": manifest.get("recipeId"),
        "manifestSchema": manifest.get("schema"),
        "playbackMode": manifest.get("playbackMode"),
        "slotCount": len(rows),
        "estimatedDrawCalls": total_draw,
        "estimatedParticles": total_particles,
        "byStage": {k: len(v) for k, v in stage_groups.items()},
        "byBackend": {k: len(v) for k, v in backend_groups.items()},
        "byLayerKind": {k: len(v) for k, v in kind_groups.items()},
        "layers": rows,
    }

VFX_KNOWN_RENDERERS = {
    "projectileafterimage", "spritestamptrail", "tiptrail", "historyribbon", "primitiveribbon",
    "ghostarc", "beamline", "fieldpulse", "impactspriteflash", "impactspriteburst", "impactring",
    "childspritemotes", "ambientmotes", "orbitalmotes", "wavystrip", "cloth", "lightcue", "soundcue",
    "genericparticles", "genericsmoke", "smokeparticles", "sparkparticles", "actorafterimage", "playerghost",
}

VFX_KNOWN_EVENTS = {"spawn", "windup", "tick", "travel", "active", "slash", "beam", "loop", "hit", "impact", "onhit", "kill", "expire", "decay"}

VFX_KNOWN_BACKENDS = {"auto", "baked", "realtime", "primitive", "sprite", "particle", "hybrid"}

VFX_KNOWN_ROLES = {"projectile", "impact", "child", "particle", "mote", "field", "trail", "self"}

VFX_KNOWN_CHANNELS = {"motionTrail", "coreGlow", "ambientParticles", "impactShape", "impactParticles", "decaySmoke", "light", "sound"}

VFX_KNOWN_LANES = {"auto", "primary", "support", "accent", "ornament", "cue"}

VFX_KNOWN_EMISSION_MODES = {"auto", "wake", "orbit", "residue", "burst", "cone", "ring", "spiral", "point"}

def _vfx_slot_value_range_ok(value: Any, name: str, lo: float, hi: float) -> list[str]:
    issues: list[str] = []
    if isinstance(value, list):
        if len(value) != 2:
            issues.append(f"{name}: range list should have 2 values")
        vals = value[:2]
    else:
        vals = [value]
    for v in vals:
        try:
            f = float(v)
            if f < lo or f > hi:
                issues.append(f"{name}: {f} outside recommended {lo}..{hi}")
        except Exception:
            issues.append(f"{name}: non-numeric value {v!r}")
    return issues

def _vfx_lint_slot(slot: dict[str, Any], idx: int, recipe_id: str = "") -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    renderer = str(slot.get("renderer") or "").strip()
    event = str(slot.get("event") or "").strip().lower()
    backend = str(slot.get("backend") or _vfx_default_backend(event, renderer)).strip().lower()
    texture_role = str(slot.get("textureRole") or "projectile").strip().lower()
    particle_role = str(slot.get("particleRole") or "").strip().lower()
    renderer_key = renderer.lower()
    if not renderer:
        errors.append("missing renderer")
    elif renderer_key not in VFX_KNOWN_RENDERERS and not any(k in renderer_key for k in VFX_KNOWN_RENDERERS):
        warnings.append(f"unknown renderer '{renderer}' (runtime may ignore it)")
    if event not in VFX_KNOWN_EVENTS:
        errors.append(f"unknown event '{event}'")
    if backend not in VFX_KNOWN_BACKENDS:
        warnings.append(f"unknown backend '{backend}'")
    if texture_role and texture_role not in VFX_KNOWN_ROLES:
        warnings.append(f"unusual textureRole '{texture_role}'")
    if particle_role and particle_role not in VFX_KNOWN_ROLES:
        warnings.append(f"unusual particleRole '{particle_role}'")
    channel = slot.get("channel") or _vfx_infer_channel(renderer, event)
    if channel not in VFX_KNOWN_CHANNELS:
        warnings.append(f"unknown channel '{channel}'")
    lane = str(slot.get("lane") or _vfx_infer_lane(slot))
    if lane not in VFX_KNOWN_LANES:
        warnings.append(f"unknown lane '{lane}'")
    emission_mode = str(slot.get("emissionMode") or _vfx_infer_emission_mode(renderer, event))
    if emission_mode not in VFX_KNOWN_EMISSION_MODES:
        warnings.append(f"unknown emissionMode '{emission_mode}'")
    # minQuality/quality is deprecated in v0.3.26, but old macro data may still carry it.
    # Linter stays quiet so legacy recipes do not drown real errors.
    importance = str(slot.get("importance") or "").strip().lower()
    if importance and importance not in {"core", "secondary", "accent", "luxury"}:
        warnings.append(f"unknown importance '{importance}'")
    for name, lo, hi in [("visualCost", 0.0, 1.0), ("signatureWeight", 0.0, 1.0), ("fadeIn", 0.0, 0.95), ("fadeOut", 0.0, 0.95)]:
        if name in slot:
            warnings.extend(_vfx_slot_value_range_ok(slot.get(name), name, lo, hi))
    for name, lo, hi in [("scale", 0.05, 8.0), ("density", 0.0, 1.0), ("alpha", 0.0, 1.0), ("spread", 0.0, 3.0), ("jitter", 0.0, 2.0), ("budgetWeight", 0.05, 8.0)]:
        if name in slot:
            warnings.extend(_vfx_slot_value_range_ok(slot.get(name), name, lo, hi))
    if "duration" in slot:
        warnings.extend(_vfx_slot_value_range_ok(slot.get("duration"), "duration", 1, 240))
    baked = slot.get("bakedCommands") if isinstance(slot.get("bakedCommands"), list) else []
    if baked and backend in {"realtime", "primitive", "sprite"}:
        warnings.append("slot has bakedCommands but backend is realtime/primitive/sprite")
    if len(baked) > 180:
        warnings.append(f"large bakedCommands list: {len(baked)}")
    for j, cmd in enumerate(baked[:220]):
        if not isinstance(cmd, dict):
            errors.append(f"bakedCommands[{j}] is not an object")
            continue
        for n in ["tick", "localX", "localY", "velocityX", "velocityY", "scaleX", "scaleY", "lifespan", "alpha"]:
            if n not in cmd:
                continue
            # keep broad ranges matching C# Normalize.
            ranges = {
                "tick": (0, 600), "localX": (-8, 8), "localY": (-8, 8),
                "velocityX": (-12, 12), "velocityY": (-12, 12), "scaleX": (0.03, 8),
                "scaleY": (0.03, 8), "lifespan": (1, 240), "alpha": (0, 1),
            }
            lo, hi = ranges[n]
            try:
                f = float(cmd.get(n))
                if f < lo or f > hi:
                    warnings.append(f"bakedCommands[{j}].{n}={f} outside {lo}..{hi}")
            except Exception:
                warnings.append(f"bakedCommands[{j}].{n} non-numeric")
    return {"index": idx, "renderer": renderer, "event": event, "backend": backend, "errors": errors, "warnings": warnings}

def _vfx_lint_recipe(recipe: dict[str, Any]) -> dict[str, Any]:
    rid = str(recipe.get("id") or "")
    errors: list[str] = []
    warnings: list[str] = []
    if not rid:
        errors.append("missing recipe id")
    patterns = recipe.get("compatiblePatterns") or []
    if not isinstance(patterns, list) or not patterns:
        warnings.append("missing compatiblePatterns")
    slots = recipe.get("slots") or []
    if not isinstance(slots, list) or not slots:
        errors.append("recipe has no slots")
        slots = []
    if len(slots) > 9:
        warnings.append(f"recipe has many slots: {len(slots)}")
    slot_reports = []
    for i, slot in enumerate(slots):
        if not isinstance(slot, dict):
            slot_reports.append({"index": i, "errors": ["slot is not object"], "warnings": []})
            continue
        rep = _vfx_lint_slot(slot, i, rid)
        slot_reports.append(rep)
        errors.extend([f"slot[{i}]: {x}" for x in rep["errors"]])
        warnings.extend([f"slot[{i}]: {x}" for x in rep["warnings"]])
    return {"id": rid, "ok": not errors, "errors": errors, "warnings": warnings, "slotReports": slot_reports}



def _vfx_timeline_from_manifest(manifest: dict[str, Any], max_ticks: int = 180) -> dict[str, Any]:
    """Build a compact per-tick timeline preview from a frozen manifest.

    This is a debug/authoring helper, not runtime logic. It makes baked/realtime
    stage problems visible without opening the game.
    """
    slots = [s for s in (manifest.get("slots") or []) if isinstance(s, dict)]
    frames: dict[int, list[dict[str, Any]]] = {}
    max_seen = 0
    for idx, slot in enumerate(slots):
        event = str(slot.get("event") or "tick")
        stage = str(slot.get("stage") or _vfx_event_stage(event, slot.get("renderer")))
        renderer = str(slot.get("renderer") or "")
        start = max(0, int(float(slot.get("startTick") or 0)))
        duration = max(1, int(float(slot.get("duration") or 1)))
        repeat = max(0, int(float(slot.get("repeatEvery") or 0)))
        backend = str(slot.get("backend") or "Auto")
        min_quality = str(slot.get("minQuality") or "Low")
        # Realtime/live slots are sampled at start/repeat ticks so authors can see they exist.
        if event.lower() in {"tick", "travel", "active", "slash", "beam", "loop", "windup", "spawn"}:
            ticks = [start]
            if repeat > 0:
                ticks = list(range(start, min(max_ticks, start + duration), repeat))[:32]
            elif duration > 1:
                ticks = sorted({start, start + duration // 2, start + duration - 1})
            for tick in ticks:
                max_seen = max(max_seen, tick)
                frames.setdefault(tick, []).append({
                    "slot": idx,
                    "kind": "sample",
                    "event": event,
                    "stage": stage,
                    "renderer": renderer,
                    "backend": backend,
                    "minQuality": min_quality,
                })
        cmds = slot.get("bakedCommands") if isinstance(slot.get("bakedCommands"), list) else []
        for cidx, cmd in enumerate(cmds):
            if not isinstance(cmd, dict):
                continue
            tick = start + max(0, int(float(cmd.get("tick") or 0)))
            if tick > max_ticks:
                continue
            max_seen = max(max_seen, tick)
            frames.setdefault(tick, []).append({
                "slot": idx,
                "cmd": cidx,
                "kind": "baked",
                "event": event,
                "stage": stage,
                "renderer": renderer,
                "backend": backend,
                "particleSystemId": cmd.get("particleSystemId", "dust"),
                "alpha": cmd.get("alpha"),
                "lifespan": cmd.get("lifespan"),
                "minQuality": min_quality,
            })
    compact = [{"tick": tick, "events": frames[tick]} for tick in sorted(frames.keys())[:max_ticks]]
    return {
        "schema": "infini.vfx.timeline_preview.v0",
        "recipeId": manifest.get("recipeId"),
        "manifestSchema": manifest.get("schema"),
        "playbackMode": manifest.get("playbackMode"),
        "durationEstimate": max_seen + 1,
        "frameCount": len(compact),
        "eventsTotal": sum(len(x["events"]) for x in compact),
        "frames": compact,
    }



__all__ = [
    name for name in globals()
    if name.startswith("VFX_")
    or name.startswith("_vfx")
    or name in {
        "attach_hybrid_vfx_manifest",
        "build_vfx_director_prompt",
        "build_vfx_director_weak_hints",
        "try_llm_vfx_director",
        "vfx_director_surface",
        "get_vfx_effect_name_bank",
        "vfx_director_name_bank",
        "get_vfx_recipes",
        "vfx_manifest_effect_stack",
    }
]
