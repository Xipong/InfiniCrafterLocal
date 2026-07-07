from __future__ import annotations

from typing import Any
import re

# Stable ids shared by the planner JSON and GeneratedProjectile runtime.
# Keep this list small: Gemma should choose from a menu, not read a full design bible.
ATTACK_PATTERN_IDS: tuple[str, ...] = (
    "thrown_simple",
    "ranged_projectile",
    "magic_projectile",
    "summon_projectile",
    "slash_holdout",
    "spear_thrust",
    "beam_slash",
    "beam_slash_burst",
    "impact_burst",
    "spawner_on_hit",
    "laser_beam",
    "falling_projectile",
    "orbiting_projectile",
    "field_trap",
)

# Short one-line hints for the main planner prompt.
_PATTERN_HINTS: dict[str, str] = {
    "thrown_simple": "one moving projectile; rotation/trail/hit spark",
    "ranged_projectile": "ranged launched projectile; technical adapter, not thrown animation",
    "magic_projectile": "cast magic projectile; technical adapter, not thrown animation",
    "summon_projectile": "summon/minion-like projectile; technical adapter, not thrown animation",
    "slash_holdout": "held melee swing; code arc; one hit line",
    "spear_thrust": "held spear/lance thrust; owner-checked polearm extension; no free-flight bolt unless a secondary projectile is authored",
    "beam_slash": "swing plus beam/streak layer or one child",
    "beam_slash_burst": "Calamity-like swing + beams + impact burst",
    "impact_burst": "projectile/hit becomes short AoE burst",
    "spawner_on_hit": "hit marker spawns capped follow-up motes/slashes",
    "laser_beam": "one line beam; length + line collision",
    "falling_projectile": "skyfall/rain-style projectile; gravity arc; ground splash/impact",
    "orbiting_projectile": "satellite/orbiting weapon or mote",
    "field_trap": "placed rune/cloud/field ticking in area",
}

# Retrieval cards: richer than hints, but still tiny. The main prompt only receives top-K.
_PATTERN_CARDS: dict[str, dict[str, Any]] = {
    "thrown_simple": {
        "useWhen": "knife, dart, shard, arrow, bullet, simple thrown/fired object",
        "code": "1 projectile sprite; rotate by velocity; dust trail; hit spark",
        "zImage": "projectile core only; no animation sheet",
        "assetRoles": ["projectile", "impact"],
        "tags": ["throw", "thrown", "knife", "dart", "arrow", "bullet", "shard", "bolt", "projectile", "ranged"],
    },
    "ranged_projectile": {
        "useWhen": "bow/gun/launcher projectile where source identity is ranged, even if onHit splits/chains",
        "code": "same lean projectile executor as thrown_simple; item use/damage class remain ranged",
        "zImage": "projectile core only",
        "assetRoles": ["projectile", "impact"],
        "tags": ["ranged", "bow", "gun", "launcher", "arrow", "bullet", "projectile"],
    },
    "magic_projectile": {
        "useWhen": "staff/spell/cast projectile where source identity is magic, even if onHit splits/chains",
        "code": "same lean projectile executor as thrown_simple; item use/damage class remain magic/cast",
        "zImage": "spell projectile core only",
        "assetRoles": ["projectile", "impact"],
        "tags": ["magic", "spell", "staff", "cast", "projectile"],
    },
    "summon_projectile": {
        "useWhen": "summon/minion-like launched entity represented by the lean generated projectile executor",
        "code": "same lean projectile executor; item use/damage class remain summon",
        "zImage": "summon projectile/minion core only",
        "assetRoles": ["projectile", "impact"],
        "tags": ["summon", "minion", "sentry", "projectile"],
    },
    "spear_thrust": {
        "summary": "Held spear/lance/polearm thrust: one owner-checked projection that extends from the player and retracts.",
        "useWhen": "spear, lance, pike, halberd, polearm, trident, stab/thrust melee",
        "code": "1 held projectile director; straight thrust; line collision; no thrown/free-flight behavior by default",
        "zImage": "held spear projection body; runtime rotates and extends it from the player",
        "assetRoles": ["item", "projectile", "impact"],
        "tags": ["thrust", "spear", "lance", "polearm", "stab", "melee", "holdout"],
    },
    "slash_holdout": {
        "useWhen": "sword, scythe, axe, melee swing, held blade, cloth/banner on weapon",
        "code": "1 held projectile director; timed swing; line collision; PreDraw slash/ghosts",
        "zImage": "item/held blade core; code draws arc, ghosts, cloth motion",
        "assetRoles": ["item", "projectile", "impact"],
        "tags": ["swing", "melee", "sword", "blade", "scythe", "axe", "slash", "holdout", "banner", "cloth"],
    },
    "beam_slash": {
        "useWhen": "blade that emits an energy streak/beam but no huge explosion",
        "code": "held/slash director plus beam line/trail; child only if gameplay needs it",
        "zImage": "core blade + optional slim beam/streak texture",
        "assetRoles": ["item", "projectile", "impact"],
        "tags": ["beam", "slash", "streak", "energy", "terra", "blade", "relic", "magic_blade"],
    },
    "beam_slash_burst": {
        "useWhen": "late-game Calamity-like blade: swing, beams, impact burst, mini spectacle",
        "code": "held director; primitive slash; 1-4 capped beams; burst phase; dust/ghost draw layers",
        "zImage": "core weapon, projectile/beam motif, impact burst seed; code does animation",
        "assetRoles": ["item", "projectile", "impact", "child"],
        "tags": ["terrablade", "terra", "calamity", "beam", "burst", "explosion", "late", "endgame", "relic", "slash"],
    },
    "impact_burst": {
        "useWhen": "bomb, orb, heavy bullet, spell that blooms on hit/expire",
        "code": "projectile enters burst phase; expanding hit radius; rings/dust in PreDraw",
        "zImage": "projectile core + impact flash; not a full 520px sheet",
        "assetRoles": ["projectile", "impact"],
        "tags": ["burst", "explosion", "explode", "bomb", "orb", "aoe", "impact", "nova", "blast"],
    },
    "spawner_on_hit": {
        "useWhen": "curse/mark/bleed/electric effect that continues briefly after hit",
        "code": "on hit create tiny capped controller or use local timer; never unbounded loops",
        "zImage": "small child mote/slash/spark only if visible; most copies are draw-only",
        "assetRoles": ["projectile", "child", "impact"],
        "tags": ["mark", "curse", "bleed", "chain", "echo", "mote", "slash_creator", "onhit", "spawner", "electric"],
    },
    "laser_beam": {
        "useWhen": "continuous ray, prism, deathray, hitscan line",
        "code": "1 beam projectile; length scan; line collision; draw begin/middle/end or line layers",
        "zImage": "small muzzle/core/beam texture; code stretches the beam",
        "assetRoles": ["projectile", "impact"],
        "tags": ["laser", "ray", "beam", "prism", "deathray", "channel", "hitscan", "line"],
    },
    "falling_projectile": {
        "useWhen": "falling star, meteor, rain, sky-drop, mortar, thrown object meant to fall into the target",
        "code": "1 gravity-arc projectile; falling visual mode; ground/impact splash; no animation sheet",
        "zImage": "small falling core/projectile plus optional impact seed; code handles fall/trail/splash",
        "assetRoles": ["projectile", "impact"],
        "tags": ["falling", "fall", "rain", "starfall", "meteor", "sky", "drop", "mortar", "falling_projectile"],
    },
    "orbiting_projectile": {
        "useWhen": "summon, satellite, orbiting shard, protective mote, aura companion",
        "code": "orbit/follow controller; target acquisition; capped child visuals",
        "zImage": "one small orbiting mote/shard; code duplicates around owner/target",
        "assetRoles": ["projectile", "child"],
        "tags": ["summon", "orbit", "satellite", "minion", "companion", "mote", "aura", "shield"],
    },
    "field_trap": {
        "useWhen": "rune, cloud, trap, puddle, lingering ground/area effect",
        "code": "stationary field timer; area collision/ticks; dust rings; owner guard for damage",
        "zImage": "flat rune/cloud/field tile-like sprite; code pulses it",
        "assetRoles": ["field", "impact"],
        "tags": ["field", "trap", "rune", "cloud", "puddle", "zone", "sigil", "ground", "area"],
    },
}

_ALIASES: dict[str, str] = {
    "basic": "thrown_simple",
    "projectile": "thrown_simple",
    "bolt": "thrown_simple",
    "shot": "thrown_simple",
    "throw": "thrown_simple",
    "thrown": "thrown_simple",
    "knife": "thrown_simple",
    "slash": "slash_holdout",
    "slash_arc": "slash_holdout",
    "holdout": "slash_holdout",
    "held": "slash_holdout",
    "spear": "spear_thrust",
    "lance": "spear_thrust",
    "polearm": "spear_thrust",
    "pike": "spear_thrust",
    "trident": "spear_thrust",
    "stab": "spear_thrust",
    "thrust": "spear_thrust",
    "held_blade": "slash_holdout",
    "swing": "slash_holdout",
    "beam": "laser_beam",
    "laser": "laser_beam",
    "ray": "laser_beam",
    "deathray": "laser_beam",
    "falling_projectile": "falling_projectile",
    "falling": "falling_projectile",
    "fall": "falling_projectile",
    "skyfall": "falling_projectile",
    "starfall": "falling_projectile",
    "meteor": "falling_projectile",
    "rain": "falling_projectile",
    "projectile_rain": "falling_projectile",
    "beam_slash": "beam_slash",
    "beam_slash_burst": "beam_slash_burst",
    "slash_burst": "beam_slash_burst",
    "terra_blade": "beam_slash_burst",
    "terrablade": "beam_slash_burst",
    "impact": "impact_burst",
    "burst": "impact_burst",
    "explosion": "impact_burst",
    "explode": "impact_burst",
    "spawner": "spawner_on_hit",
    "slash_creator": "spawner_on_hit",
    "on_hit_spawner": "spawner_on_hit",
    "onhit_spawner": "spawner_on_hit",
    "orbit": "orbiting_projectile",
    "orbiting": "orbiting_projectile",
    "satellite": "orbiting_projectile",
    "field": "field_trap",
    "trap": "field_trap",
    "rune": "field_trap",
    "cloud": "field_trap",
}


def _norm(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_").replace(":", "_")


def normalize_attack_pattern(value: Any) -> str | None:
    raw = _norm(value)
    if not raw:
        return None
    raw = _ALIASES.get(raw, raw)
    if raw in ATTACK_PATTERN_IDS:
        return raw
    return None


def _words(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, dict):
        value = " ".join(str(k) + " " + str(v) for k, v in value.items())
    elif isinstance(value, (list, tuple, set)):
        value = " ".join(str(v) for v in value)
    text = str(value).lower().replace("_", " ").replace("-", " ")
    return set(re.findall(r"[a-zа-яё0-9]+", text))


def select_pattern_cards(context: Any = None, max_cards: int = 4) -> list[dict[str, Any]]:
    """Return top-K compact pattern cards for a recipe/concept.

    This is the light-library path: Gemma gets only relevant cards, not the whole VFX doc.
    """
    words = _words(context)
    scored: list[tuple[float, str, dict[str, Any]]] = []
    for pid, card in _PATTERN_CARDS.items():
        tags = set(card.get("tags") or []) | _words(card.get("useWhen"))
        score = float(len(words & tags))
        # Keep simple options visible unless context strongly asks for spectacle.
        if pid == "thrown_simple":
            score += 0.25
        if pid == "spear_thrust" and words & {"spear", "lance", "polearm", "pike", "trident", "stab", "thrust"}:
            score += 2
        if pid == "slash_holdout" and words & {"sword", "blade", "melee", "swing", "banner", "cloth"}:
            score += 1.2
        if pid == "beam_slash_burst" and words & {"terra", "calamity", "endgame", "boss", "relic", "explosion"}:
            score += 1.4
        if pid == "laser_beam" and words & {"beam", "laser", "ray", "prism"}:
            score += 1.2
        scored.append((score, pid, card))
    scored.sort(key=lambda x: (-x[0], ATTACK_PATTERN_IDS.index(x[1])))
    out: list[dict[str, Any]] = []
    for score, pid, card in scored[:max(1, max_cards)]:
        out.append({
            "id": pid,
            "useWhen": card["useWhen"],
            "code": card["code"],
            "zImage": card["zImage"],
            "assetRoles": card["assetRoles"],
        })
    return out


def attack_pattern_contract_for_llm(context: Any = None, max_cards: int = 4) -> dict[str, Any]:
    """Tiny prompt payload for planner models.

    The verbose archetype library cost too many tokens. This returns an enum plus
    only a few retrieved cards, enough to choose but not enough to drown Gemma.
    """
    return {
        "rule": "choose exactly one attackPattern id. If unsure, still choose; do not invent ids.",
        "allIds": list(ATTACK_PATTERN_IDS),
        "candidateCards": select_pattern_cards(context, max_cards=max_cards),
    }


def fallback_attack_pattern(delivery: Any = None, damage_class: Any = None) -> str:
    """Dev/self-test fallback only. Real LLM crafts should be repaired by the model."""
    d = _norm(delivery)
    dc = _norm(damage_class)
    if d in {"thrust", "spear"}:
        return "spear_thrust"
    if d == "swing" or dc == "melee":
        return "slash_holdout"
    if d in {"summon"} or dc == "summon":
        return "orbiting_projectile"
    return "thrown_simple"


def resolve_attack_pattern(value: Any, *, delivery: Any = None, damage_class: Any = None, allow_fallback: bool = True) -> tuple[str | None, str]:
    normalized = normalize_attack_pattern(value)
    if normalized:
        return normalized, "authored"
    if allow_fallback:
        return fallback_attack_pattern(delivery, damage_class), "dev_fallback"
    return None, "needs_llm_repair"


def pattern_card(pattern_id: str) -> dict[str, Any]:
    pid = normalize_attack_pattern(pattern_id) or "thrown_simple"
    card = _PATTERN_CARDS[pid]
    return {"id": pid, **{k: card[k] for k in ["useWhen", "code", "zImage", "assetRoles"]}}
