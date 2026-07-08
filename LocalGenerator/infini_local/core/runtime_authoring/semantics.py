from __future__ import annotations

import re
from typing import Any

from infini_local.core.runtime_authoring.common import _clamp, _enum, _norm_name, _num
from infini_local.core.runtime_authoring.schema import (
    DELIVERIES,
    EFFECTS,
    MOVEMENTS,
    RUNTIME_FAMILIES,
    TERRARIA_WEAPON_FAMILY_GROUPS,
    _family_group,
    _runtime_family_affordances,
)

# Small effect ontology, not a per-item exception list.
# Parent knowledge should eventually expose canonical effect capabilities directly
# (burn/poison/frostburn/shadowflame). Until then, a tiny alias layer maps common
# elemental trait words to existing runtime onHit values without reading prompt prose.
PARENT_EFFECT_TRAIT_ALIASES: dict[str, str] = {
    "flaming": "burn",
    "fire": "burn",
    "burning": "burn",
    "burn": "burn",
    "poison": "poison",
    "poisoned": "poison",
    "venom": "poison",
    "toxic": "poison",
    "frostburn": "frostburn",
    "frost": "frostburn",
    "shadowflame": "shadowflame",
}


def _iter_parent_tags(data: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    knowledge = data.get("itemKnowledge") if isinstance(data.get("itemKnowledge"), dict) else {}
    for parent in knowledge.get("parents") or []:
        if not isinstance(parent, dict):
            continue
        for tag in parent.get("tags") or []:
            t = _norm_name(tag)
            if t:
                tags.append(t)
        signals = parent.get("signals") if isinstance(parent.get("signals"), dict) else {}
        mech = signals.get("mechanicPower") if isinstance(signals.get("mechanicPower"), dict) else {}
        behavior = mech.get("weaponBehavior") if isinstance(mech.get("weaponBehavior"), dict) else {}
        for tag in behavior.get("behaviorTags") or []:
            t = _norm_name(tag)
            if t:
                tags.append(t)
    return list(dict.fromkeys(tags))


def _parent_grounded_onhit(data: dict[str, Any]) -> tuple[str, str]:
    """Return a parent-backed elemental on-hit effect, if unambiguous.

    This never reads free-form prompt/tooltip and therefore does not become category
    keyword routing. It only preserves concrete mechanics already present in parent
    runtime/knowledge tags. The alias map is deliberately tiny; broad item-specific
    behavior should come from richer parent probes, not a growing exception table.
    """
    for tag in _iter_parent_tags(data):
        if tag in PARENT_EFFECT_TRAIT_ALIASES:
            return PARENT_EFFECT_TRAIT_ALIASES[tag], tag
    return "", ""


def _material_color_name(materials: list[str], fallback: str = "dull") -> str:
    blob = " ".join(str(x or "").lower() for x in materials)
    if any(w in blob for w in ["wood", "sawdust", "bark", "splinter", "дерев"]): return "wood brown"
    if any(w in blob for w in ["copper", "bronze", "мед"]): return "copper orange"
    if any(w in blob for w in ["iron", "steel", "metal", "silver", "wire", "металл"]): return "metal gray"
    if any(w in blob for w in ["stone", "rock", "slate", "кам"]): return "stone gray"
    if any(w in blob for w in ["sand", "sawdust", "dust"]): return "sand tan"
    if any(w in blob for w in ["slime", "gel"]): return "slime green"
    if any(w in blob for w in ["fire", "flame", "ember"]): return "flame orange"
    if any(w in blob for w in ["electric", "lightning", "spark"]): return "cyan electric"
    if any(w in blob for w in ["shadow", "corrupt", "void"]): return "shadow purple"
    if any(w in blob for w in ["holy", "star", "lunar"]): return "gold star"
    return fallback


def _material_effect_hint(materials: list[str]) -> str | None:
    blob = " ".join(str(x or "").lower() for x in materials)
    if any(w in blob for w in ["wood", "sawdust", "bark", "stone", "rock", "metal", "copper", "iron", "sand", "dust", "гряз", "дерев", "кам"]):
        return "dust"
    if any(w in blob for w in ["slime", "gel"]): return "slime"
    if any(w in blob for w in ["fire", "flame", "ember"]): return "flame"
    if any(w in blob for w in ["electric", "lightning", "spark"]): return "electric"
    if any(w in blob for w in ["shadow", "corrupt", "void"]): return "shadow"
    if any(w in blob for w in ["poison", "toxic"]): return "poison"
    if any(w in blob for w in ["holy", "star", "lunar"]): return "star"
    return None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool): return value
    s = _norm_name(value)
    return s in {"1", "true", "yes", "y", "visual", "visual_only"}


def _semantic_param_copy(params: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k in keys:
        if k in params and params.get(k) not in (None, ""):
            out[k] = params.get(k)
    return out


_WEAPON_SUBFAMILY_ALIASES: dict[str, str] = {
    "short_sword": "shortsword", "short sword": "shortsword", "broad_sword": "broadsword",
    "sword": "broadsword", "greatsword": "broadsword", "rapier": "shortsword",
    "jousting_lance": "lance", "rocket_launcher": "launcher", "spell_book": "magic_book",
    "book": "magic_book", "spellbook": "magic_book", "wand": "magic_staff", "staff": "magic_staff",
    "rod": "magic_staff", "beam_staff": "laser_staff", "channelled_beam": "laser_staff", "channeled_beam": "laser_staff",
    "minion": "summon_staff", "pet_attack": "summon_staff", "turret": "sentry_staff", "sentry": "sentry_staff",
}

def _weapon_subfamily_from_fields(*, family: Any = "", projectile_family: Any = "", runtime_family: Any = "", delivery: Any = "", ammo: Any = "", explicit: Any = "") -> str:
    explicit_norm = _norm_name(explicit)
    if explicit_norm:
        return _WEAPON_SUBFAMILY_ALIASES.get(explicit_norm, explicit_norm)[:48]
    f = _norm_name(family)
    pf = _norm_name(projectile_family)
    rt = _norm_name(runtime_family)
    dlv = _norm_name(delivery)
    am = _norm_name(ammo)
    text = " ".join(x for x in [f, pf, rt, dlv, am] if x)
    if not text:
        return ""
    for key, value in _WEAPON_SUBFAMILY_ALIASES.items():
        if key in {f, pf, dlv, am} or key in text:
            return value
    if any(x in text for x in ["shotgun", "boomstick", "onyx"]): return "shotgun"
    if any(x in text for x in ["sniper", "sdmg"]): return "sniper"
    if any(x in text for x in ["chain_gun", "chaingun", "gatligator"]): return "chain_gun"
    if "dart" in text: return "dart_weapon"
    if any(x in text for x in ["blowpipe", "blowgun"]): return "blowgun"
    if "harpoon" in text: return "harpoon"
    if "bow" in text or "arrow" in text: return "bow"
    if "gun" in text or "bullet" in text or "pistol" in text or "rifle" in text: return "gun"
    if "launcher" in text or "rocket" in text or "missile" in text: return "launcher"
    if "whip" in text or "lash" in text: return "whip"
    if "yoyo" in text: return "yoyo"
    if "flail" in text or "mace" in text or "chain" in text: return "flail"
    if any(x in text for x in ["spear", "lance", "trident", "pike", "glaive", "halberd"]): return "spear"
    if any(x in text for x in ["boomerang", "chakram", "disc"]): return "boomerang"
    if rt == "cast": return "magic_staff"
    if rt == "summon": return "summon_staff"
    if rt == "swing": return "broadsword"
    return f[:48] if f else pf[:48]

def _attack_pattern_tags_from_patch(patch: dict[str, Any], *sources: dict[str, Any]) -> list[str]:
    raw: list[str] = []
    for src in sources:
        val = src.get("attackPatternTags") or src.get("patternTags")
        if isinstance(val, list):
            raw.extend(str(x) for x in val if x not in (None, ""))
        elif isinstance(val, str) and val.strip():
            raw.extend(x.strip() for x in val.replace(";", ",").split(","))
    blob = " ".join(str(src.get(k, "")) for src in [patch, *sources] for k in [
        "weaponFamily", "weaponSubfamily", "projectileFamily", "projectileShape", "projectileMotion",
        "projectileTrail", "projectileImpact", "movement", "effect", "onHit", "delivery"
    ]).lower()
    token_blob = " " + re.sub(r"[^a-z0-9]+", " ", blob).strip() + " "

    def has_semantic_needle(needle: str) -> bool:
        phrase = re.sub(r"[^a-z0-9]+", " ", str(needle).lower()).strip()
        return bool(phrase) and f" {phrase} " in token_blob
    candidates: list[tuple[str, list[str]]] = [
        ("falling_star", ["falling", "starfall", "star_wrath", "star wrath", "meteor"]),
        ("beam", ["beam", "laser", "prism", "ray"]),
        ("shotgun_spread", ["shotgun", "spread", "scatter"]),
        ("multi_arrow", ["multi_arrow", "volley", "phantasm", "tsunami", "arrow rain"]),
        ("homing_orb", ["homing", "orb", "arcanum", "spirit flame"]),
        ("splinter_burst", ["splinter", "shard", "fragment"]),
        ("bee_swarm", ["bee", "honey", "beenade"]),
        ("chain_flail", ["flail", "chain", "mace", "anchor"]),
        ("whip_lash", ["whip", "lash"]),
        ("summon_sentry", ["sentry", "turret", "hydra", "portal"]),
        ("growing_minion", ["dragon", "stardust dragon", "segment"]),
        ("bounce", ["bounce", "ricochet"]),
        ("boomerang_return", ["boomerang", "returning", "returning_glaive"]),
        ("explosive", ["explosion", "explode", "rocket", "grenade", "blast"]),
        ("elemental_debuff", ["burn", "frostburn", "poison", "shadowflame", "bleed"]),
    ]
    for tag, needles in candidates:
        if any(has_semantic_needle(n) for n in needles):
            raw.append(tag)
    out: list[str] = []
    for value in raw:
        tag = _norm_name(value)
        if tag and tag not in out:
            out.append(tag[:40])
        if len(out) >= 12:
            break
    return out

def _sound_query_from_patch(patch: dict[str, Any], *, impact: bool) -> str:
    bits = [
        patch.get("weaponSubfamily"), patch.get("weaponFamily"), patch.get("projectileFamily"),
        patch.get("movement"), patch.get("effect"), patch.get("onHit") if impact else patch.get("delivery"),
    ]
    bits.extend(patch.get("attackPatternTags") or [])
    words = [str(x).replace("_", " ").strip() for x in bits if x not in (None, "", [])]
    suffix = "impact hit" if impact else "use cast swing release"
    return (" ".join(dict.fromkeys(words)) + " " + suffix).strip()[:160]

def _apply_armor_slot_budget(armor: dict[str, Any]) -> None:
    slot = _norm_name(armor.get("slot")) or "body"
    # Soft Terraria-ish distribution: head carries class identity, body carries bulk, legs carry mobility.
    if slot == "head":
        caps = {"defense": 24, "movementSpeed": 0.18, "maxRunSpeed": 0.35, "jumpSpeed": 0.8, "endurance": 0.08}
    elif slot == "legs":
        caps = {"defense": 26, "genericDamage": 0.14, "meleeDamage": 0.16, "rangedDamage": 0.16, "magicDamage": 0.16, "summonDamage": 0.16, "endurance": 0.08}
    else:
        caps = {"defense": 42, "movementSpeed": 0.18, "maxRunSpeed": 0.45, "jumpSpeed": 1.0, "genericCrit": 12, "endurance": 0.18}
    clamped: dict[str, Any] = {}
    for field, cap in caps.items():
        if field in armor and isinstance(armor.get(field), (int, float)) and armor[field] > cap:
            clamped[field] = {"from": armor[field], "to": cap}
            armor[field] = int(cap) if isinstance(cap, int) else round(float(cap), 3)
    if clamped:
        armor["slotBudgetClamps"] = clamped


def _expand_semantic_runtime_call(fn: str, params: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Lower explicit Terraria-family engine calls into the compact runtime executor.

    This is not name aliasing: the planner authors a weapon family (spear/flail/yoyo/whip,
    bow/gun/launcher, staff/book, minion/sentry), then this compiler emits the small set
    of executable runtime fields the current C# runtime actually supports.
    """
    fn = _norm_name(fn)
    p = dict(params or {})
    family = _norm_name(p.get("family") or p.get("weaponFamily") or p.get("projectileFamily") or p.get("archetype"))
    common = _semantic_param_copy(p, [
        "movement", "effect", "speed", "rangeTiles", "lifetimeTicks", "shotCount", "spreadRadians",
        "pierce", "extraUpdates", "homingStrength", "useTimeTicks", "reliability",
        "selfLockTicks", "missPunish", "projectileShape", "projectileMotion",
        "projectileTrail", "projectileImpact", "damageMultiplier", "runtimeFamily",
        "weaponSubfamily", "attackPatternTags", "soundUseSearchQuery", "soundImpactSearchQuery",
    ])

    if fn == "perform_melee_attack":
        group = _family_group(family)
        if group == "thrust":
            common.update({"runtimeFamily": "thrust", "delivery": "thrust", "movement": common.get("movement") or "straight", "weaponFamily": family or "spear"})
            common.setdefault("projectileMotion", "held thrust")
        elif group == "returning":
            common.update({"runtimeFamily": "returning", "delivery": "throw", "movement": "boomerang", "weaponFamily": family or "boomerang"})
        elif group == "flail":
            common.update({"runtimeFamily": "flail", "delivery": "flail", "movement": "flail_tether", "weaponFamily": family or "flail"})
            common.setdefault("projectileMotion", "chain-tethered flail head")
        elif group == "yoyo":
            common.update({"runtimeFamily": "yoyo", "delivery": "yoyo", "movement": "yoyo_hover", "weaponFamily": "yoyo"})
            common.setdefault("projectileMotion", "channelled yoyo hover")
        elif group == "whip":
            common.update({"runtimeFamily": "whip", "delivery": "whip", "movement": "whip_lash", "weaponFamily": "whip"})
            common.setdefault("projectileMotion", "summon whip lash")
        else:
            common.update({"runtimeFamily": "swing", "delivery": "swing", "movement": common.get("movement") or "straight", "weaponFamily": family or "broadsword"})
        return [("shoot_projectile", common)]

    if fn == "fire_ranged_weapon":
        group = _family_group(family)
        if family in {"launcher", "rocket_launcher", "rocket", "missile_launcher"}:
            common.setdefault("movement", "proximity_missile")
        elif family in {"harpoon"}:
            common.setdefault("movement", "returning_glaive")
        else:
            common.setdefault("movement", "straight")
        common.update({"runtimeFamily": "shoot", "delivery": "shoot", "weaponFamily": family or "ranged", "projectileFamily": family or "ranged"})
        if p.get("ammoFor") not in (None, ""):
            common["ammoFor"] = p.get("ammoFor")
        return [("shoot_projectile", common)]

    if fn == "cast_magic_weapon":
        raw_projectile_family = _norm_name(p.get("projectileFamily"))
        if family in {"channelled_beam", "channeled_beam", "beam_staff", "laser_staff"}:
            common.setdefault("movement", "phase")
        else:
            common.setdefault("movement", "straight")

        # Important Terraria-style split: cast context decides the executor.  The
        # family/projectileFamily text is only carrier/form identity.  Do not encode
        # material+shape compounds (crystal_spear/light_spear/etc.) as magic families:
        # the same phrase may be authored as melee, thrown, ranged, or magic depending
        # on the explicit engine call/runtimeFamily/damageClass.
        projectile_form = raw_projectile_family
        weapon_family = family if _family_group(family) == "magic" else "magic"
        if family in TERRARIA_WEAPON_FAMILY_GROUPS.get("thrust", set()):
            projectile_form = projectile_form or family
        elif not projectile_form:
            # Generic form extraction only for authored cast context.  This is not a
            # runtime-family repair; it merely preserves spear/lance/glaive-shaped spell
            # visuals without deciding that those words are magic by themselves.
            if family.endswith("_spear") or "spear" in family:
                projectile_form = "spear"
            elif family.endswith("_lance") or "lance" in family:
                projectile_form = "lance"
            elif family.endswith("_glaive") or "glaive" in family:
                projectile_form = "glaive"

        common.update({"runtimeFamily": "cast", "delivery": "cast", "weaponFamily": weapon_family or "magic", "projectileFamily": projectile_form or "magic"})
        return [("shoot_projectile", common)]

    if fn == "summon_combat_entity":
        common.setdefault("movement", "orbit" if family in {"minion", "pet_attack"} else "drift")
        common.update({"runtimeFamily": "summon", "delivery": "summon", "weaponFamily": family or "minion", "projectileFamily": family or "summon"})
        return [("shoot_projectile", common)]

    return [(fn, p)]


def _runtime_family_from_fields(delivery: Any, movement: Any, weapon_family: Any = "", projectile_family: Any = "", explicit: Any = "") -> str:
    """Return explicit runtimeFamily only.

    This helper intentionally no longer performs broad behavior inference.  New
    runtime authoring must use runtimeFamily; the separate light repair below is
    the only permitted rescue path for small/local models.
    """
    explicit_norm = _enum(explicit, RUNTIME_FAMILIES, None)
    return explicit_norm if explicit_norm and explicit_norm != "none" else "none"


def _runtime_family_group_to_executor(group: str) -> str:
    if group == "thrust": return "thrust"
    if group == "returning": return "returning"
    if group in {"flail", "yoyo", "whip"}: return group
    if group == "ranged": return "shoot"
    if group == "magic": return "cast"
    if group == "summon": return "summon"
    return ""


def light_repair_runtime_family_from_fields(params: dict[str, Any]) -> tuple[str, str]:
    """Tiny, explicit, auditable repair for small models.

    This is deliberately weaker than legacy inference: it only accepts exact
    weaponFamily groups, exact delivery family words, or movement values that are
    already one-to-one executor opcodes. projectileFamily is deliberately excluded:
    it is projectile form, not an executable family signal.  If signals conflict, it
    returns none and the craft fails/asks LLM repair.
    """
    if not isinstance(params, dict):
        return "none", ""
    explicit = _enum(params.get("runtimeFamily"), RUNTIME_FAMILIES, None)
    if explicit and explicit != "none":
        return explicit, "authored_runtimeFamily"

    signals: list[tuple[str, str]] = []
    # Tiny repair treats weaponFamily as the executable weapon family.  projectileFamily
    # is only emitted projectile FORM (e.g. a magic spell can launch a spear-shaped
    # projectile), so it must not make a cast/shoot spell become a held spear.
    group = _family_group(params.get("weaponFamily"))
    fam = _runtime_family_group_to_executor(group)
    if fam:
        signals.append((fam, "weaponFamily"))

    d = _enum(params.get("delivery"), DELIVERIES, None)
    if d in {"swing", "shoot", "cast", "throw", "summon", "flail", "yoyo", "whip"}:
        signals.append((d, "delivery"))
    elif d in {"thrust", "spear"}:
        signals.append(("thrust", "delivery"))

    m = _enum(params.get("movement"), MOVEMENTS, None)
    movement_map = {
        "boomerang": "returning",
        "returning_glaive": "returning",
        "flail_tether": "flail",
        "yoyo_hover": "yoyo",
        "whip_lash": "whip",
    }
    if m in movement_map:
        signals.append((movement_map[m], "movement"))

    unique = sorted({fam for fam, _src in signals if fam and fam != "none"})
    if len(unique) != 1:
        return "none", ""
    srcs = "+".join(src for fam, src in signals if fam == unique[0])
    return unique[0], f"light:{srcs}"

__all__ = ['_iter_parent_tags', '_parent_grounded_onhit', '_material_color_name', '_material_effect_hint', '_truthy', '_semantic_param_copy', '_weapon_subfamily_from_fields', '_attack_pattern_tags_from_patch', '_sound_query_from_patch', '_apply_armor_slot_budget', '_expand_semantic_runtime_call', '_runtime_family_from_fields', '_runtime_family_group_to_executor', 'light_repair_runtime_family_from_fields']
