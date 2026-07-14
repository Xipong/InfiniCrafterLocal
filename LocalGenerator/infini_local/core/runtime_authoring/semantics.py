from __future__ import annotations

from typing import Any

from infini_local.core.runtime_authoring.common import _enum, _norm_name
from infini_local.core.runtime_executor_vocabulary import MOVEMENTS
from infini_local.core.runtime_family_policy import CANONICAL_RUNTIME_FAMILIES as RUNTIME_FAMILIES
from infini_local.core.runtime_authoring.schema import (
    TERRARIA_WEAPON_FAMILY_GROUPS,
    _family_group,
)
from infini_local.core.runtime_authoring.vocabulary import DELIVERIES

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
    bow/gun/launcher, staff/book, temporary helper), then this compiler emits the small set
    of executable runtime fields the current C# runtime actually supports.
    """
    fn = _norm_name(fn)
    p = dict(params or {})
    family = _norm_name(p.get("family") or p.get("weaponFamily") or p.get("projectileFamily") or p.get("archetype"))
    common = _semantic_param_copy(p, [
        "movement", "effect", "speed", "rangeTiles", "lifetimeTicks", "shotCount", "spreadRadians",
        "pierce", "extraUpdates", "homingStrength", "beamWidthPx", "beamChargeTicks", "chargeTicks", "chargePowerMultiplier", "delayTicks", "immunityCooldown", "useTimeTicks", "useAnimationTicks",
        "projectileShape", "projectileMotion",
        "projectileTrail", "projectileImpact", "damageMultiplier", "runtimeFamily",
        "soundUseCatalogId", "soundImpactCatalogId", "soundVolume", "soundPitch", "soundPitchVariance",
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
        # Keep delivery mechanics separate from projectile theme.  The exact
        # overhead_barrage family selects the finite spawn-above-target executor,
        # while projectileFamily remains the authored arrow/shard/rocket/etc. form.
        # No item name, tooltip or ammo word selects this mechanic.
        raw_projectile_family = _norm_name(p.get("projectileFamily"))
        overhead_barrage = family == "overhead_barrage"
        charge_release = family == "charge_release"
        if charge_release:
            common.setdefault("movement", "straight")
            common.update({"runtimeFamily": "charge_release", "delivery": "shoot", "weaponFamily": _norm_name(p.get("weaponFamily")) or "ranged", "projectileFamily": raw_projectile_family or "projectile", "chargeTicks": p.get("chargeTicks", 45), "chargePowerMultiplier": p.get("chargePowerMultiplier", 1.6)})
        elif overhead_barrage:
            common.setdefault("movement", "phase")
            common.update({
                "runtimeFamily": "overhead_barrage",
                "delivery": "shoot",
                "weaponFamily": _norm_name(p.get("weaponFamily")) or "ranged",
                "projectileFamily": raw_projectile_family or "projectile",
                "delayTicks": p.get("delayTicks") if p.get("delayTicks") not in (None, "") else p.get("chargeTicks", 30),
            })
        elif not charge_release:
            if family in {"launcher", "rocket_launcher", "rocket", "missile_launcher"}:
                common.setdefault("movement", "proximity_missile")
            elif family in {"harpoon"}:
                common.setdefault("movement", "returning_glaive")
            else:
                common.setdefault("movement", "straight")
            common.update({
                "runtimeFamily": "shoot",
                "delivery": "shoot",
                "weaponFamily": family or "ranged",
                "projectileFamily": raw_projectile_family or family or "ranged",
            })
        if p.get("ammoFor") not in (None, ""):
            common["ammoFor"] = p.get("ammoFor")
        return [("shoot_projectile", common)]

    if fn == "cast_magic_weapon":
        raw_projectile_family = _norm_name(p.get("projectileFamily"))
        # Only an explicit channelled-beam family selects the persistent held-beam
        # executor.  A beam_staff/laser_staff may still fire ordinary bolt/projectile
        # casts, so those taxonomy words must not silently choose gameplay.
        beam_family = family in {"channelled_beam", "channeled_beam"}
        charge_release = family == "charge_release"
        overhead_barrage = family == "overhead_barrage"
        if beam_family or charge_release or overhead_barrage:
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

        common.update({
            "runtimeFamily": "beam" if beam_family else ("charge_release" if charge_release else ("overhead_barrage" if overhead_barrage else "cast")),
            "delivery": "cast",
            "weaponFamily": weapon_family or "magic",
            "projectileFamily": "beam" if beam_family else ((projectile_form or "projectile") if (charge_release or overhead_barrage) else (projectile_form or "magic")),
        })
        if beam_family:
            common["channelUse"] = True
            common.setdefault("beamWidthPx", 14)
            if p.get("chargeTicks") not in (None, ""):
                common["beamChargeTicks"] = p.get("chargeTicks")
            if p.get("immunityCooldown") not in (None, ""):
                common["immunityCooldown"] = p.get("immunityCooldown")
        elif charge_release:
            common["chargeTicks"] = p.get("chargeTicks", 45)
            common["chargePowerMultiplier"] = p.get("chargePowerMultiplier", 1.6)
            common["channelUse"] = True
        elif overhead_barrage:
            common["delayTicks"] = p.get("delayTicks") if p.get("delayTicks") not in (None, "") else p.get("chargeTicks", 30)
            common.setdefault("shotCount", 3)
            common.setdefault("secondaryDamageMultiplier", 0.55)
            common.setdefault("secondaryLifetimeTicks", 75)
        return [("shoot_projectile", common)]

    if fn == "deploy_sentry":
        sentry = _semantic_param_copy(p, ["placement", "attackIntervalTicks", "targetRangeTiles", "helperLifetimeTicks", "shotCount", "speed", "spreadRadians", "movement", "effect", "onHit", "projectileShape", "secondaryProjectileShape", "secondaryLifetimeTicks", "projectileTrail", "projectileImpact", "soundUseCatalogId", "soundImpactCatalogId", "soundVolume", "soundPitch", "soundPitchVariance"])
        sentry.update({"runtimeFamily": "sentry", "delivery": "summon", "weaponFamily": "sentry", "projectileFamily": "sentry", "sentryPlacement": p.get("placement", "grounded"), "sentryAttackIntervalTicks": p.get("attackIntervalTicks", 45), "sentryTargetRangeTiles": p.get("targetRangeTiles", 30), "sentryLifetimeTicks": p.get("helperLifetimeTicks", 3600)})
        return [("shoot_projectile", sentry)]

    if fn == "spawn_temporary_helper_projectile":
        common.setdefault("movement", "orbit" if family in {"orbiter", "wisp", "pet_attack"} else "drift")
        common.update({"runtimeFamily": "summon", "delivery": "summon", "weaponFamily": family or "orbiter", "projectileFamily": family or "temporary_helper"})
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

__all__ = ['_iter_parent_tags', '_parent_grounded_onhit', '_truthy', '_semantic_param_copy', '_apply_armor_slot_budget', '_expand_semantic_runtime_call', '_runtime_family_from_fields', '_runtime_family_group_to_executor', 'light_repair_runtime_family_from_fields']
