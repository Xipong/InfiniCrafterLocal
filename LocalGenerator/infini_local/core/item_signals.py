from __future__ import annotations

"""Stable item-signal vocabulary used by generated-item classification.

This module owns static tag sets and visual synonym hints. It has no environment
reads, filesystem setup, HTTP imports, LLM imports, or runtime side effects.
"""

import re
from typing import Any

from infini_local.core.item_identity_tools import fingerprint_of

HARD_TAGS = {
    "chair", "wood", "wire", "vr", "headset", "sword", "blade", "bow", "gun", "wand", "staff", "flower", "daybloom",
    "star", "bottle", "bench", "workbench", "circuit", "computer", "potion", "gel", "slime",
    "accessory", "boots", "wings", "shield", "emblem", "charm", "ring", "band", "amulet", "glove", "balloon",
    "pickaxe", "hammer", "axe", "drill", "chainsaw", "arrow", "bullet", "rocket", "armor",
    "dirt", "earth", "stone", "sand", "block", "mud", "clay", "ore", "bar", "material", "coin",
}

VISUAL_SYNONYMS = {
    "vr": ["VR headset", "black visor", "goggles"],
    "headset": ["headset", "visor"],
    "chair": ["chair silhouette", "seat", "backrest", "legs"],
    "wood": ["wooden texture", "brown wood"],
    "wire": ["visible wire", "cable", "thin dark wire"],
    "electric": ["small yellow sparks", "electric arcs"],
    "star": ["small star", "starlight glow"],
    "flower": ["flower petals", "plant stem"],
    "daybloom": ["yellow flower", "daybloom petals"],
    "circuit": ["green circuit board", "tiny electronic traces"],
    "workbench": ["wooden work bench", "crafting table"],
    "computer": ["small monitor", "keyboard", "screen glow"],
    "potion": ["glass potion bottle", "colored liquid"],
    "slime": ["gel blob", "slime coating"],
    "sword": ["sword blade", "hilt"],
    "gun": ["gun barrel", "handle"],
    "bow": ["bow limbs", "string"],
    "wand": ["magic wand", "small gem"],
    "staff": ["magic staff", "ornament"],
    "accessory": ["small wearable trinket", "polished charm"],
    "boots": ["pair of boots", "small winged soles"],
    "wings": ["small wings", "feathered silhouette"],
    "shield": ["small shield", "guard plate"],
    "emblem": ["emblem badge", "glowing insignia"],
    "charm": ["small charm", "dangling talisman"],
    "ring": ["small ring", "gem setting"],
    "glove": ["single glove", "clawed gauntlet"],
    "balloon": ["round balloon", "floating string"],
    "tool": ["tool head", "handle"],
    "pickaxe": ["pickaxe head", "tool handle"],
    "hammer": ["hammer head", "short handle"],
    "axe": ["axe blade", "long handle"],
    "drill": ["drill bit", "metal body"],
    "chainsaw": ["chain teeth", "saw body"],
    "grappling_hook": ["hook claw", "small chain"],
    "ammo": ["small projectile stack", "compact ammo bundle"],
    "armor": ["armor plate", "helmet silhouette"],
    "dirt": ["dirt block", "brown soil"],
    "earth": ["earthy chunks", "brown soil"],
    "stone": ["stone block", "gray rock"],
    "sand": ["sand block", "pale grains"],
    "block": ["small block", "square tile"],
    "material": ["raw material chunk", "ingredient piece"],
    "coin": ["small coin", "metal disc"],
}


def knowledge_key(name: str) -> str:
    key = name.lower().strip()
    key = key.replace("’", "'").replace("_", " ").replace("-", " ")
    key = re.sub(r"\s+", " ", key)
    return key


def wire_identity_names(item: dict[str, Any]) -> set[str]:
    fp = fingerprint_of(item)
    raw = {
        item.get("name"),
        item.get("internalName"),
        item.get("fullName"),
        fp.get("internalName"),
        fp.get("fullName"),
    }
    out: set[str] = set()
    for x in raw:
        if not x:
            continue
        text = str(x)
        out.add(knowledge_key(text))
        out.add(knowledge_key(text.replace("/", " ").replace(":", " ")))
        # Split common PascalCase internal names: LuminiteBar -> luminite bar.
        pascal = re.sub(r"(?<!^)([A-Z])", r" \1", text)
        out.add(knowledge_key(pascal))
    return {x for x in out if x}


__all__ = ["HARD_TAGS", "VISUAL_SYNONYMS", "knowledge_key", "wire_identity_names"]
