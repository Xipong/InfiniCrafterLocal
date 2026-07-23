from __future__ import annotations

from typing import Any

from infini_local.core.runtime_family_policy import keeps_item_body_damage_lane


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _token(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _compact_number(value: Any) -> str:
    number = _number(value, 0.0)
    return str(int(number)) if number.is_integer() else f"{number:.2f}".rstrip("0").rstrip(".")


def compiled_runtime_tooltip(data: dict[str, Any]) -> str:
    """Describe only final executable fields.

    Free-form author prose is intentionally excluded.  The formatter neither infers
    mechanics from names nor verifies natural language; it projects the final wire
    contract that the C# runtime actually consumes.
    """
    gameplay_raw = data.get("gameplay")
    attack_raw = data.get("attack")
    accessory_raw = data.get("accessory")
    armor_raw = data.get("armor")
    gameplay: dict[str, Any] = gameplay_raw if isinstance(gameplay_raw, dict) else {}
    attack: dict[str, Any] = attack_raw if isinstance(attack_raw, dict) else {}
    accessory: dict[str, Any] = accessory_raw if isinstance(accessory_raw, dict) else {}
    armor: dict[str, Any] = armor_raw if isinstance(armor_raw, dict) else {}

    kind = _token(gameplay.get("kind") or data.get("category") or "generic")
    clauses: list[str] = []

    tool_parts: list[str] = []
    for label, key in (("pick", "pickPower"), ("axe", "axePower"), ("hammer", "hammerPower")):
        value = int(_number(gameplay.get(key), 0.0))
        if value > 0:
            tool_parts.append(f"{label} {value}")
    if tool_parts:
        clauses.append("tool " + "/".join(tool_parts))

    damage = int(_number(gameplay.get("damage"), 0.0))
    attack_enabled = bool(attack.get("enabled"))
    family = _token(attack.get("runtimeFamily") or "none")
    delivery = _token(attack.get("delivery"))
    body_lane = bool(
        damage > 0
        and attack_enabled
        and attack.get("disableItemMeleeHitbox") is False
        and (family == "swing" or keeps_item_body_damage_lane(family, delivery))
    )
    if attack_enabled:
        if family == "swing":
            action = "item hitbox"
        elif body_lane:
            action = f"item hitbox + {family} projectile"
        else:
            action = f"{family} projectile"
        details: list[str] = []
        shots = max(1, int(_number(attack.get("shotCount"), 1.0)))
        if family != "swing" and shots > 1:
            details.append(f"{shots} shots")
        movement = _token(attack.get("movement"))
        if family != "swing" and movement and movement != "none":
            details.append(movement.replace("_", " "))
        pierce = int(_number(attack.get("pierce"), 1.0))
        if family != "swing" and pierce == -1:
            details.append("infinite pierce")
        elif family != "swing" and pierce > 1:
            details.append(f"{pierce} total hits")
        on_hit = _token(attack.get("onHit"))
        if on_hit and on_hit != "none":
            details.append("on hit: " + on_hit.replace("_", " "))
        clauses.append(action + (" (" + ", ".join(details) + ")" if details else ""))
    elif body_lane:
        clauses.append("item hitbox")

    if bool(accessory.get("enabled")):
        effects: list[str] = []
        for label, key in (("defense", "defense"), ("max life", "maxLife"), ("max mana", "maxMana")):
            value = int(_number(accessory.get(key), 0.0))
            if value:
                effects.append(f"{label} {value:+d}")
        if _number(accessory.get("lightStrength"), 0.0) > 0:
            effects.append("equipped light")
        clauses.append("accessory" + (" (" + ", ".join(effects) + ")" if effects else ""))

    if bool(armor.get("enabled")):
        effects = []
        defense = int(_number(armor.get("defense"), 0.0))
        if defense:
            effects.append(f"defense {defense:+d}")
        if _number(armor.get("lightStrength"), 0.0) > 0:
            effects.append("equipped light")
        slot = _token(armor.get("armorSlot")) or "piece"
        clauses.append(f"{slot} armor" + (" (" + ", ".join(effects) + ")" if effects else ""))

    heal_life = int(_number(gameplay.get("healLife"), 0.0))
    heal_mana = int(_number(gameplay.get("healMana"), 0.0))
    if heal_life > 0:
        clauses.append(f"restores {heal_life} life")
    if heal_mana > 0:
        clauses.append(f"restores {heal_mana} mana")

    if bool(gameplay.get("consumable")):
        stack = int(_number(gameplay.get("maxStack"), 1.0))
        clauses.append(f"consumable stack {max(1, stack)}")

    if not clauses:
        clauses.append(f"{kind} runtime")
    return "Executable: " + "; ".join(clauses[:6]) + "."


__all__ = ["compiled_runtime_tooltip"]
