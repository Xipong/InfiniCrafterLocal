from __future__ import annotations

"""Developer-only deterministic fallback planner.

This module is intentionally not part of normal InfiniCraft item authoring.
Production gameplay should use the LLM-authored runtimePlan path; this fallback
exists only for local smoke tests and emergency offline development when
INFINI_ALLOW_DETERMINISTIC_DEV_FALLBACK=1 is explicitly set.

The fallback keeps its semantic examples and plan builders outside server.py so
the main HTTP/combine pipeline remains an authored LLM/runtime transport,
validation and delivery shell.
"""

import json
from typing import Any, Mapping


def _h(helpers: Mapping[str, Any], name: str) -> Any:
    return helpers[name]


def _base_spec(helpers: Mapping[str, Any], result_id: str, key: str, a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], name: str, tooltip: str, merge: str, source: str, category: str, tags: list[str]) -> dict[str, Any]:
    name_of = _h(helpers, "name_of")
    canonical_for_result = _h(helpers, "canonical_for_result")
    rep_for_parent = _h(helpers, "rep_for_parent")
    inh_for_parent = _h(helpers, "inh_for_parent")
    recipe_meta = _h(helpers, "recipe_meta")
    category_policy = _h(helpers, "category_policy")
    engine_runtime_api_version = _h(helpers, "ENGINE_RUNTIME_API_VERSION")
    app_version = _h(helpers, "APP_VERSION")
    return {
        "schemaVersion": 1,
        "runtimeApiVersion": engine_runtime_api_version,
        "id": result_id,
        "recipeKey": key,
        "name": name,
        "parentA": name_of(a),
        "parentB": name_of(b),
        "tooltip": tooltip,
        "mergeMode": merge,
        "sourceMode": source,
        "category": category,
        "tags": sorted(set(tags)),
        "canonical": canonical_for_result(name, category, tags),
        "sourceRepresentation": [
            rep_for_parent(a, ca, "primary"),
            rep_for_parent(b, cb, "secondary"),
        ],
        "inheritance": [
            inh_for_parent(a, ca, "base_shape" if ca.get("headNoun") not in ["item", "material"] else "influence"),
            inh_for_parent(b, cb, "attachment" if cb.get("headNoun") in ["wire", "headset"] else "influence"),
        ],
        "lossBudget": {
            "requiredParentPresence": 2,
            "maxDroppedHardTags": 0 if merge in ["literal", "lexicalized_literal"] else 1,
            "mustPreserveHeadNounFromAtLeastOneParent": True,
            "mustPreserveMaterialIfPresent": merge in ["literal", "lexicalized_literal"],
            "minPreservationScore": 0.65,
        },
        "visual": {},
        "presentationGenome": {},
        "soundProfile": {},
        "gameplay": {},
        "attack": {},
        "recipeMeta": recipe_meta(a, b, set(tags), category_policy(set(tags), a, b, key)),
        "debug": {"planner": "deterministic", "version": app_version},
    }


def _weapon_plan(helpers: Mapping[str, Any], result_id: str, key: str, a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], tags: set[str]) -> dict[str, Any]:
    creative_result_name = _h(helpers, "creative_result_name")
    required_anchors_from = _h(helpers, "required_anchors_from")
    palette_from = _h(helpers, "palette_from")
    name = creative_result_name(a, b, ca, cb, "weapon", tags | {"weapon"}, key)
    data = _base_spec(helpers, result_id, key, a, b, ca, cb, name, "A generated weapon whose attack profile was synthesized separately", "literal", "generated", "weapon", sorted(tags | {"weapon"}))
    data["visual"] = {"objectType": "generated_weapon", "requiredAnchors": required_anchors_from(ca, cb, tags), "palette": palette_from(tags)}
    return data


def _tool_plan(helpers: Mapping[str, Any], result_id: str, key: str, a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], tags: set[str]) -> dict[str, Any]:
    creative_result_name = _h(helpers, "creative_result_name")
    required_anchors_from = _h(helpers, "required_anchors_from")
    palette_from = _h(helpers, "palette_from")
    category_policy = _h(helpers, "category_policy")
    if "pickaxe" in tags or "drill" in tags:
        suffix = "Drill" if "drill" in tags else "Pickaxe"
    elif "hammer" in tags:
        suffix = "Hammer"
    elif "axe" in tags or "chainsaw" in tags:
        suffix = "Chainsaw" if "chainsaw" in tags else "Axe"
    else:
        suffix = "Tool"
    name = creative_result_name(a, b, ca, cb, "tool", tags | {"tool", suffix.lower()}, key)
    data = _base_spec(helpers, result_id, key, a, b, ca, cb, name, "A generated utility tool with inherited traits.", "functional", "generated", "tool", sorted(tags | {"tool"}))
    data["gameplay"] = {"kind": "tool"}
    data["visual"] = {"objectType": "generated_tool", "requiredAnchors": required_anchors_from(ca, cb, tags | {"tool"}), "palette": palette_from(tags | {"tool"})}
    data["debug"]["categoryDecision"] = json.dumps(category_policy(tags | {"tool"}, a, b, key), ensure_ascii=False)
    return data


def _accessory_plan(helpers: Mapping[str, Any], result_id: str, key: str, a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], tags: set[str]) -> dict[str, Any]:
    creative_result_name = _h(helpers, "creative_result_name")
    required_anchors_from = _h(helpers, "required_anchors_from")
    palette_from = _h(helpers, "palette_from")
    category_policy = _h(helpers, "category_policy")
    if "boots" in tags or "mobility" in tags:
        name = creative_result_name(a, b, ca, cb, "accessory", tags | {"boots"}, key)
        tooltip = "A generated accessory that converts item power into movement."
    elif "shield" in tags or "defense" in tags:
        name = creative_result_name(a, b, ca, cb, "accessory", tags | {"shield"}, key)
        tooltip = "A generated accessory that preserves defensive traits from its parents."
    elif "emblem" in tags or "damage" in tags or "weapon" in tags:
        name = creative_result_name(a, b, ca, cb, "accessory", tags | {"emblem"}, key)
        tooltip = "A generated accessory that channels weapon traits into passive power."
    else:
        name = creative_result_name(a, b, ca, cb, "accessory", tags | {"accessory"}, key)
        tooltip = "A generated accessory shaped by both parent items."
    data = _base_spec(helpers, result_id, key, a, b, ca, cb, name, tooltip, "functional", "generated", "accessory", sorted(tags | {"accessory"}))
    data["gameplay"] = {"kind": "accessory"}
    data["attack"] = {"enabled": False}
    data["visual"] = {"objectType": "generated_accessory", "requiredAnchors": required_anchors_from(ca, cb, tags | {"accessory"}), "palette": palette_from(tags | {"accessory"})}
    data["debug"]["categoryDecision"] = json.dumps(category_policy(tags | {"accessory"}, a, b, key), ensure_ascii=False)
    return data


def deterministic_plan(a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], key: str, helpers: Mapping[str, Any]) -> dict[str, Any]:
    name_of = _h(helpers, "name_of")
    tags_of = _h(helpers, "tags_of")
    stable_hash = _h(helpers, "stable_hash")
    rep = _h(helpers, "rep")
    choose_result_category = _h(helpers, "choose_result_category")
    creative_result_name = _h(helpers, "creative_result_name")

    tags = tags_of(a) | tags_of(b)
    result_id = "g_" + stable_hash(key, "result", length=16)

    # Known / near-vanilla resolver. These can be expanded with a full Terraria item database later.
    if {"sun", "flower"} <= tags or "sunflower" in tags:
        return _base_spec(helpers, result_id, key, a, b, ca, cb, "Sunflower", "Can be placed", "literal", "vanilla_match", "furniture", ["sunflower", "flower", "plant", "placeable"])

    if "chair" in tags and "wire" in tags:
        data = _base_spec(helpers, result_id, key, a, b, ca, cb, "Electric Chair", "Shocking seating arrangement", "lexicalized_literal", "generated", "furniture", ["chair", "wood", "wire", "electric", "furniture"])
        data["sourceRepresentation"] = [
            rep(name_of(a), "visual", "primary" if "chair" in tags_of(a) else "secondary", "wooden chair silhouette" if "chair" in tags_of(a) else "visible wire", "main object" if "chair" in tags_of(a) else "wrapped around chair"),
            rep(name_of(b), "visual", "primary" if "chair" in tags_of(b) else "secondary", "wooden chair silhouette" if "chair" in tags_of(b) else "visible wire", "main object" if "chair" in tags_of(b) else "wrapped around chair"),
        ]
        data["visual"] = {"objectType": "electric_chair", "requiredAnchors": ["wooden chair as main silhouette", "visible wires wrapped around chair", "small yellow sparks"], "palette": ["brown", "dark_gray", "yellow"]}
        return data

    if {"daybloom"} <= tags and (name_of(a).lower() == name_of(b).lower() or "potion" in tags or "flower" in tags):
        data = _base_spec(helpers, result_id, key, a, b, ca, cb, "Daybloom Potion", "A potion with healing properties", "literal", "generated", "potion", ["daybloom", "flower", "potion", "consumable", "plant"])
        data["visual"] = {"objectType": "daybloom_potion", "requiredAnchors": ["glass potion bottle", "yellow daybloom petals", "green plant accent"], "palette": ["yellow", "green", "white"]}
        return data

    if "circuit" in tags and ("workbench" in tags or "bench" in tags):
        data = _base_spec(helpers, result_id, key, a, b, ca, cb, "Computer", "A compact machine for processing information", "functional", "generated", "technology", ["computer", "technology", "circuit", "workbench", "screen"])
        data["visual"] = {"objectType": "computer", "requiredAnchors": ["small monitor", "green circuit detail", "wooden workbench influence"], "palette": ["dark_gray", "green", "cyan", "brown"]}
        return data

    if "vr" in tags and "chair" in tags:
        data = _base_spec(helpers, result_id, key, a, b, ca, cb, "Gaming Station", "A setup for immersive play", "functional", "generated", "placeable_station", ["gaming_station", "vr", "headset", "chair", "technology", "screen"])
        data["visual"] = {"objectType": "gaming_station", "requiredAnchors": ["wooden chair", "visible VR headset", "small monitor", "cyan screen glow"], "palette": ["brown", "dark_gray", "cyan", "purple"]}
        return data

    # Generic semantic merge. Category is selected before stat generation; parent damage does not force weapon.
    chosen_category = choose_result_category(tags, a, b, key)
    if chosen_category == "accessory":
        return _accessory_plan(helpers, result_id, key, a, b, ca, cb, tags)
    if chosen_category == "weapon":
        return _weapon_plan(helpers, result_id, key, a, b, ca, cb, tags)
    if chosen_category == "potion" or ("flower" in tags and "bottle" in tags):
        return _base_spec(helpers, result_id, key, a, b, ca, cb, creative_result_name(a, b, ca, cb, "potion", tags | {"potion", "consumable"}, key), "A strange blended potion", "literal", "generated", "potion", sorted(tags | {"potion", "consumable"}))
    if chosen_category == "tool":
        return _tool_plan(helpers, result_id, key, a, b, ca, cb, tags)
    if chosen_category == "ammo":
        return _base_spec(helpers, result_id, key, a, b, ca, cb, creative_result_name(a, b, ca, cb, "ammo", tags | {"ammo"}, key), "Generated ammunition with inherited traits", "functional", "generated", "ammo", sorted(tags | {"ammo"}))
    if chosen_category == "armor":
        return _base_spec(helpers, result_id, key, a, b, ca, cb, creative_result_name(a, b, ca, cb, "armor", tags | {"armor"}, key), "A generated defensive item", "functional", "generated", "armor", sorted(tags | {"armor"}))
    if chosen_category in {"technology", "furniture", "placeable_station"}:
        return _base_spec(helpers, result_id, key, a, b, ca, cb, creative_result_name(a, b, ca, cb, chosen_category, tags | {"device"}, key), "A locally generated device", "functional", "generated", chosen_category, sorted(tags | {"device"}))
    return _base_spec(helpers, result_id, key, a, b, ca, cb, creative_result_name(a, b, ca, cb, "generic", tags | {"generated"}, key), "A locally generated hybrid item", "literal", "generated", "generic", sorted(tags | {"generated"}))
