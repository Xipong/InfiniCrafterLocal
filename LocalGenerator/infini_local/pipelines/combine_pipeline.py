from __future__ import annotations

import base64
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
from urllib import request as urlrequest
from urllib import error as urlerror
from urllib.parse import urlencode


# AGENT MAP: main /combine pipeline spine. The important shape is:
# request payload -> parent/world context -> LLM or fallback authored data ->
# runtimePlan compile/repair -> balance/final normalize -> visual/assets ->
# deliverable GeneratedItemData. Stage labels in combine() are debug breadcrumbs;
# do not insert hidden gameplay authoring into cache, visual, or trace helpers.
def record_combine_failure(stage: str, error: BaseException | str, payload: dict[str, Any] | None, partial_data: Any, pipeline_log: list[dict[str, Any]] | None) -> None:
    """Keep the last failed craft inspectable after C# refunds ingredients.

    This is intentionally diagnostic only: it does not change craft success/failure.
    v0.4.49: users were seeing generated PNGs in cache but /combine returned 424;
    the trace must say which pipeline stage rejected the recipe.
    """
    global LAST_COMBINE_FAILURE
    LAST_COMBINE_FAILURE = failure_state.build_combine_failure(
        app_version=APP_VERSION,
        stage=stage,
        error=error,
        payload=payload,
        partial_data=partial_data,
        pipeline_log=pipeline_log,
        parent_name=name_of,
        json_slim=_json_slim,
    )
    failure_state.persist_failure(CACHE_DIR, LAST_COMBINE_FAILURE_FILE, LAST_COMBINE_FAILURE, log_event)

def clear_combine_failure(reason: str = "success") -> None:
    """Clear stale diagnostic failure state after a successful/cached craft.

    last_combine_failure.json is a debug aid, not an authoritative current
    status.  Earlier versions cleared only the in-memory dict at the start of a
    fresh combine; /trace then reloaded an old file and made a later successful
    craft look failed.
    """
    global LAST_COMBINE_FAILURE
    LAST_COMBINE_FAILURE = {}
    failure_state.clear_persisted_failure(LAST_COMBINE_FAILURE_FILE, log_event, reason)

def last_combine_failure_summary() -> dict[str, Any]:
    return failure_state.read_failure_summary(LAST_COMBINE_FAILURE, LAST_COMBINE_FAILURE_FILE)

def combine_cache_lookup(payload: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    """Return a world-scoped cached recipe without starting generation.

    This is a transport/cache helper, not a design path: it computes the exact same
    recipe key as /combine and reads the existing world recipe file only. It is used
    so a Terraria client can recover an item after an earlier long /combine request
    timed out locally but finished and wrote the recipe on the generator side.
    """
    a = payload.get("itemA") or {}
    b = payload.get("itemB") or {}
    world_id = normalize_world_id_from_payload(payload)
    world_name = str(payload.get("worldName") or "").strip()
    recipe_identity_version = str(payload.get("recipeIdentityVersion") or payload.get("recipeKeyVersion") or RECIPE_IDENTITY_VERSION)
    key = recipe_key(a, b, world_id, recipe_identity_version)
    cached = cache_get(key, world_id, world_name)
    if cached is not None and not is_deliverable_recipe_payload(cached):
        trace_event("step", "HTTP:/combine", "world recipe cache skipped non-deliverable payload", {"recipeKey": key, "sourceMode": cached.get("sourceMode") if isinstance(cached, dict) else ""})
        cached = None
    if cached is not None:
        visual_report = visual_delivery_report(cached)
        if not visual_report.get("ok"):
            trace_event("step", "HTTP:/combine", "world recipe cache skipped missing required visual asset", {"recipeKey": key, "visualDelivery": visual_report})
            cached = None
    return key, cached

def combine(payload: dict[str, Any]) -> dict[str, Any]:
    global LAST_COMBINE_FAILURE
    a = payload.get("itemA") or {}
    b = payload.get("itemB") or {}
    world_id = normalize_world_id_from_payload(payload)
    world_name = str(payload.get("worldName") or "").strip()
    recipe_identity_version = str(payload.get("recipeIdentityVersion") or payload.get("recipeKeyVersion") or RECIPE_IDENTITY_VERSION)
    key = recipe_key(a, b, world_id, recipe_identity_version)
    cached = cache_get(key, world_id, world_name)
    if cached:
        visual_report = visual_delivery_report(cached)
        if visual_report.get("ok"):
            clear_combine_failure("cache_hit_delivered")
            return sanitize_recipe_for_delivery(cached)
        trace_event("step", "COMBINE:cache", "cached recipe ignored because required visual asset is not deliverable", {"recipeKey": key, "visualDelivery": visual_report})

    ca = canonicalize(a)
    cb = canonicalize(b)
    pipeline_log: list[dict[str, Any]] = []
    data: dict[str, Any] | None = None
    clear_combine_failure("new_combine_started")

    def step(label: str, fn, *args):
        t0 = time.time()
        try:
            out = fn(*args)
            pipeline_log.append({"stage": label, "ok": True, "ms": int((time.time() - t0) * 1000)})
            return out
        except Exception as e:
            pipeline_log.append({"stage": label, "ok": False, "ms": int((time.time() - t0) * 1000), "error": repr(e)})
            partial = args[0] if args and isinstance(args[0], dict) else data
            record_combine_failure(label, e, payload, partial, pipeline_log)
            raise

    try:
        if USE_LLM:
            data = step("01_author_llm_plan", try_llm_plan, a, b, ca, cb, key)

        if data is None:
            if ALLOW_DETERMINISTIC_DEV_FALLBACK:
                data = step("01b_deterministic_dev_fallback", deterministic_plan, a, b, ca, cb, key)
                data.setdefault("debug", {})["planner"] = "deterministic_dev_fallback"
            else:
                err = PlannerUnavailable("LLM planner unavailable or returned invalid output; craft failed and ingredients must be refunded")
                record_combine_failure("01_author_llm_plan", err, payload, data, pipeline_log)
                raise err

        # Author-first pipeline. The code is deliberately not the designer here:
        # it validates shape, computes safety envelope, asks/keeps authored toy fields,
        # then generates a visible asset pack for the authored behavior.
        data = step("02_schema_validate_and_minimal_repair", validate_and_repair, data, a, b, ca, cb, key)
        data = step("03_runtime_knowledge_context", apply_item_knowledge, data, a, b, ca, cb)
        data = step("04_author_gameplay_to_runtime_envelope", attach_gameplay_and_attack, data, a, b, ca, cb)
        data = step("05_presentation_sound_from_author_intent", attach_presentation_and_sound, data)
        data = step("06_result_card_after_runtime_stats", attach_result_knowledge_card, data, a, b)
        data = step("07_item_visual_brief_preserve_author", attach_visual, data, a, b, ca, cb)
        data = step("08_visual_director_asset_pack", apply_visual_director, data, a, b, ca, cb)
        data = step("09_visual_asset_generation", maybe_generate_visual_assets, data)
        data = step("09b_visual_delivery_gate", assert_visual_delivery_ready, data)
        data = step("10_hybrid_vfx_manifest", attach_hybrid_vfx_manifest, data, key, "", a, b, call_llm_vfx_director if USE_LLM else None)
        data = step("11_generated_parent_summary", attach_generated_parent_summary, data)
        data = step("12_final_normalize", final_normalize, data)
        data.setdefault("recipeMeta", {})["worldScoped"] = True
        data.setdefault("recipeMeta", {})["worldId"] = world_id
        data.setdefault("recipeMeta", {})["worldName"] = world_name
        data.setdefault("recipeMeta", {})["recipeKey"] = key
        data.setdefault("debug", {})["cacheScope"] = "world"
        data.setdefault("debug", {})["recipeIdentityVersion"] = recipe_identity_version
        data.setdefault("debug", {})["worldId"] = world_id
        data.setdefault("debug", {})["worldRecipesDir"] = str(world_recipe_dir(world_id))
        data.setdefault("debug", {})["pipelineProfile"] = VISUAL_PIPELINE_PROFILE
        data.setdefault("debug", {})["pipelineLog"] = json.dumps(pipeline_log, ensure_ascii=False)
        data = asset_sync_service.attach_asset_sync_meta(data, asset_public_base_url=ASSET_PUBLIC_BASE_URL)
        data = world_storage.attach_recipe_health(
            data,
            app_version=APP_VERSION,
            contract_versions=contract_versions_payload(),
            visual_report=visual_delivery_report(data),
        )
        data = sanitize_recipe_for_delivery(data)
        cache_put(key, a, b, data, world_id, world_name)
        clear_combine_failure("fresh_combine_success")
        return data
    except Exception as e:
        if not LAST_COMBINE_FAILURE:
            record_combine_failure("unknown", e, payload, data, pipeline_log)
        raise

def deterministic_plan(a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], key: str) -> dict[str, Any]:
    """Run the explicit dev-only fallback planner.

    Normal gameplay must not use this path unless
    INFINI_ALLOW_DETERMINISTIC_DEV_FALLBACK=1 is set.  The semantic fallback
    table lives in dev_fallback.py so server.py remains the authored LLM/runtime
    transport and validation shell.
    """
    import dev_fallback

    return dev_fallback.deterministic_plan(a, b, ca, cb, key, _dev_fallback_helpers())


def _dev_fallback_helpers() -> dict[str, Any]:
    """Return only the helper surface the explicit dev fallback is allowed to use."""
    return {
        "APP_VERSION": APP_VERSION,
        "ENGINE_RUNTIME_API_VERSION": ENGINE_RUNTIME_API_VERSION,
        "canonical_for_result": canonical_for_result,
        "category_policy": category_policy,
        "choose_result_category": choose_result_category,
        "creative_result_name": creative_result_name,
        "inh_for_parent": inh_for_parent,
        "name_of": name_of,
        "palette_from": palette_from,
        "recipe_meta": recipe_meta,
        "rep": rep,
        "rep_for_parent": rep_for_parent,
        "required_anchors_from": required_anchors_from,
        "stable_hash": stable_hash,
        "tags_of": tags_of,
    }

def clean_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9А-Яа-яЁё]+", "", s) or "Item"

def theme_word(tags: set[str]) -> str:
    # Non-final fallback word only; final result names are produced by creative_result_name().
    if "star" in tags: return "Astral"
    if "slime" in tags or "gel" in tags: return "Gelatinous"
    if "wire" in tags or "electric" in tags: return "Electric"
    if "daybloom" in tags or "flower" in tags: return "Blooming"
    if "shadow" in tags or "night" in tags: return "Umbral"
    if "fire" in tags: return "Ember"
    if "ice" in tags or "frost" in tags: return "Frost"
    if "technology" in tags or "circuit" in tags: return "Circuit"
    if "dirt" in tags or "earth" in tags: return "Loam"
    if "stone" in tags: return "Stonebound"
    if "sand" in tags: return "Sandy"
    if "lunar" in tags or "moon" in tags: return "Moonlit"
    if "gun" in tags or "rifle" in tags: return "Locksteel"
    if "sword" in tags or "blade" in tags: return "Edgewise"
    return "Patchwork"

def title_words(text: str) -> str:
    parts = re.findall(r"[A-Za-zА-Яа-яЁё0-9']+", str(text or ""))
    return " ".join(w[:1].upper() + w[1:] for w in parts)

def bad_result_name(name: Any, a: dict[str, Any] | None = None, b: dict[str, Any] | None = None) -> bool:
    n = str(name or "").strip()
    if len(n) < 3 or len(n) > 48:
        return True
    if any(p.search(n) for p in BAD_NAME_PATTERNS):
        return True
    low = n.lower().strip()
    parent_names = {name_of(x).lower().strip() for x in (a or {}, b or {}) if isinstance(x, dict)}
    if low in parent_names:
        return True
    if low in {"item", "generated item", "unknown", "thing", "object"}:
        return True
    return False

def choose_from(options: list[str], key: str, *parts: Any) -> str:
    if not options:
        return "Patchwork"
    h = int(stable_hash(key, *parts, length=8), 16)
    return options[h % len(options)]

def name_noun_for(category: str, tags: set[str], a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any]) -> str:
    category = normalize_category(category)
    if category == "ammo":
        if "bullet" in tags or "gun" in tags: return "Rounds"
        if "arrow" in tags or "bow" in tags: return "Arrows"
        return "Shots"
    if category in {"technology", "placeable_station"}: return "Engine"
    if category == "furniture": return "Relic"
    if category == "tool":
        if "pickaxe" in tags: return "Pick"
        if "axe" in tags or "chainsaw" in tags: return "Cutter"
        if "hammer" in tags: return "Hammer"
        return "Tool"
    if category == "accessory":
        if "boots" in tags: return "Treads"
        if "shield" in tags: return "Ward"
        if "wings" in tags: return "Wings"
        if "emblem" in tags: return "Emblem"
        return "Charm"
    if category == "potion": return "Draught"
    if category == "armor": return "Plate"
    if "gun" in tags or "rifle" in tags: return choose_from(["Rifle", "Carbine", "Handcannon", "Lock"], "noun", name_of(a), name_of(b))
    if "bow" in tags: return choose_from(["Bow", "String", "Greatbow"], "noun", name_of(a), name_of(b))
    if "staff" in tags or "wand" in tags or "magic" in tags: return choose_from(["Staff", "Wand", "Focus", "Scepter"], "noun", name_of(a), name_of(b))
    if "summon" in tags: return choose_from(["Totem", "Bell", "Idol", "Sigil"], "noun", name_of(a), name_of(b))
    if "sword" in tags or "blade" in tags or category == "weapon": return choose_from(["Blade", "Edge", "Saber", "Cleaver"], "noun", name_of(a), name_of(b))
    for c in (ca, cb):
        head = str(c.get("headNoun") or "").strip()
        if head and head.lower() not in {"item", "material", "generic"}:
            return title_words(head)
    return "Relic"

def name_prefixes_for(tags: set[str]) -> list[str]:
    pool: list[str] = []
    if "star" in tags or "lunar" in tags or "moon" in tags:
        pool += ["Stargrazed", "Comet-Bent", "Moon-Scarred", "Falling-Light", "Astral"]
    if "slime" in tags or "gel" in tags:
        pool += ["Gelbound", "Slimeglass", "Jelly-Sealed", "Ooze-Kissed"]
    if "wire" in tags or "electric" in tags or "circuit" in tags or "technology" in tags:
        pool += ["Sparkwired", "Copper-Spark", "Voltaic", "Circuit-Bitten"]
    if "dirt" in tags or "earth" in tags or "stone" in tags or "sand" in tags:
        pool += ["Loamforged", "Claybitten", "Stone-Sunk", "Dustbound"]
    if "fire" in tags or "ember" in tags:
        pool += ["Emberwake", "Ash-Loaded", "Cinderborn"]
    if "ice" in tags or "frost" in tags:
        pool += ["Rimecut", "Frostlocked", "Cold-Sewn"]
    if "shadow" in tags or "night" in tags:
        pool += ["Umbral", "Night-Bent", "Blackglass", "Dusk-Eaten"]
    if "flower" in tags or "daybloom" in tags or "plant" in tags:
        pool += ["Bloomwake", "Petal-Sewn", "Sunroot", "Verdant"]
    if "bar" in tags or "ore" in tags or "alloy" in tags or "material" in tags:
        pool += ["Alloyed", "Forge-Spliced", "Tempered", "Graft-Made"]
    if not pool:
        pool += ["Miscast", "Patchwork", "Crooked", "Borrowed", "Oddly-Forged", "Secondhand"]
    return pool

def creative_result_name(a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], category: str, tags: set[str], key: str) -> str:
    prefix = choose_from(name_prefixes_for(tags), key, "prefix", sorted(tags), category)
    noun = name_noun_for(category, tags, a, b, ca, cb)
    patterns = [f"{prefix} {noun}", f"{noun} of {prefix.replace('-', ' ')}", f"{prefix} {noun}"]
    name = choose_from(patterns, key, "pattern", name_of(a), name_of(b), category)
    name = re.sub(r"\s+", " ", name).strip()
    if bad_result_name(name, a, b):
        name = f"{prefix} {noun}"
    return name[:48].strip()

def repair_name_if_needed(data: dict[str, Any], a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], key: str) -> dict[str, Any]:
    tags = set(str(t).lower() for t in data.get("tags", [])) | tags_of(a) | tags_of(b)
    category = normalize_category(data.get("category", data.get("gameplay", {}).get("kind", "generic")))
    old = str(data.get("name") or "")
    if not bad_result_name(old, a, b):
        return data

    debug = data.setdefault("debug", {})
    planner = str(debug.get("planner") or "")

    # Important boundary: if the main LLM planner failed and we are already in
    # deterministic mode, do NOT spend another request on a name-only repair.
    # There is only one text LLM. Sprite generation is a separate image backend,
    # not a fallback brain for naming/mechanics.
    new_name = None
    if USE_LLM and (planner == "llm" or planner.startswith("llm_")):
        new_name = try_llm_name_repair(data, a, b, ca, cb, key, tags, category)

    if not new_name or bad_result_name(new_name, a, b):
        if planner == "llm" or planner.startswith("llm_"):
            raise PlannerUnavailable("LLM returned a service/invalid item name and name repair failed; craft failed and ingredients must be refunded")
        new_name = creative_result_name(a, b, ca, cb, category, tags, key)
        repair_source = "deterministic_dev_name_fallback"
    else:
        repair_source = "llm_name_repair"

    data["name"] = new_name
    debug["nameRepair"] = json.dumps({"from": old, "to": new_name, "source": repair_source, "planner": planner}, ensure_ascii=False)
    data["canonical"] = canonical_for_result(new_name, category, list(tags))
    return data

def try_llm_name_repair(data: dict[str, Any], a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], key: str, tags: set[str], category: str) -> str | None:
    try:
        model_name = resolve_llm_model()
        req = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": "Return STRICT JSON only. Create one flavorful Terraria-like item name. Do not use Infini, Generated, Hybrid, Combined, or a bare parent name."},
                {"role": "user", "content": json.dumps({
                    "parentA": name_of(a),
                    "parentB": name_of(b),
                    "category": category,
                    "tags": sorted(tags)[:24],
                    "concept": data.get("tooltip") or data.get("mergeMode") or "combined item",
                    "badName": data.get("name"),
                    "shape": {"a": ca.get("headNoun"), "b": cb.get("headNoun")},
                    "required": {"name": "short flavorful English item name, 2-5 words"},
                }, ensure_ascii=False)},
            ],
            "temperature": 0.45,
            "max_tokens": 160,
            "response_format": llm_json_response_format("infini_name"),
        }
        raw = llm_chat_json(req, timeout=10)
        content = raw["choices"][0]["message"]["content"]
        obj = parse_first_valid_llm_json(content)
        n = str(obj.get("name") or "").strip()
        return n or None
    except Exception as e:
        log_event("warn", "LLM name repair failed", {"error": repr(e)})
        return None

def normalize_category(category: Any) -> str:
    c = str(category or "generic").lower().strip()
    aliases = {
        "placeable": "furniture",
        "station": "placeable_station",
        "crafting_station": "placeable_station",
        "device": "technology",
        "trinket": "accessory",
        "acc": "accessory",
        # Do not alias generic consumable to potion. v0.4 runtime has separate
        # stackable generated consumable weapons; potion is only for healing/buff items.
        "consumable_item": "consumable",
        "stack_consumable": "consumable",
        "thrown_stack": "consumable",
    }
    c = aliases.get(c, c)
    return c if c in ALLOWED_CATEGORIES else "generic"

def parent_primary_category(item: dict[str, Any]) -> str:
    """Stable primary role for parent context.

    Important: Terraria Item.material means "can be used in recipes later", not
    "this item is primarily a material". Many weapons/tools are material=true.
    Treat material as a secondary craftability flag unless no stronger role fits.
    """
    t = tags_of(item)
    damage = int(item_num(item, "damage", 0))
    pick = int(item_num(item, "pickPower", item_num(item, "pick", 0)))
    axe = int(item_num(item, "axePower", item_num(item, "axe", 0)))
    hammer = int(item_num(item, "hammerPower", item_num(item, "hammer", 0)))
    create_tile = int(item_num(item, "createTile", -1))
    create_wall = int(item_num(item, "createWall", -1))

    if item_bool(item, "accessory") or ("accessory" in t and damage <= 0):
        return "accessory"
    if t & ARMOR_HINT_TAGS or item_num(item, "defense", 0) > 0:
        return "armor"
    if pick > 0 or axe > 0 or hammer > 0 or t & TOOL_HINT_TAGS:
        return "tool"
    if damage > 0 or ("weapon" in t and not (item_bool(item, "consumable") and damage <= 0)):
        return "weapon"
    if t & AMMO_HINT_TAGS or item_num(item, "ammo", 0) > 0:
        return "ammo"
    if item_num(item, "healLife", 0) > 0 or item_num(item, "healMana", 0) > 0 or item_num(item, "buffType", 0) > 0 or "potion" in t:
        return "potion"
    if item_bool(item, "consumable") and item_num(item, "shoot", 0) > 0:
        return "consumable"
    if create_tile >= 0 or create_wall >= 0 or t & PLACEABLE_HINT_TAGS:
        return "furniture"
    if item_bool(item, "consumable") and not item_bool(item, "material"):
        return "consumable"
    if item_bool(item, "material") or "material" in t:
        return "material"
    return "generic"

def is_weapon_like_parent(item: dict[str, Any]) -> bool:
    """Runtime category pressure helper.

    Generated weapons keep being weapons when used in later weapon chains. This is not
    a creativity judgment; it prevents a playthrough chain from randomly losing its
    main combat item to a non-weapon category just because a stable hash sampled a
    rare lane. Explicit accessory/tool/ammo/armor parents can still pull the result
    sideways through category_policy.
    """
    gd = generated_data_of(item)
    gp = gd.get("gameplay") if isinstance(gd.get("gameplay"), dict) else {}
    if normalize_category(gd.get("category")) == "weapon" or normalize_category(gp.get("kind")) == "weapon":
        return True
    t = tags_of(item)
    return item_num(item, "damage") > 0 or item_num(item, "shoot") > 0 or "weapon" in t

def _weighted_choice(weights: dict[str, float], seed: str) -> str:
    clean = {normalize_category(k): max(0.0, float(v)) for k, v in weights.items() if normalize_category(k) != "generic"}
    clean = {k: v for k, v in clean.items() if v > 0}
    if not clean:
        return "generic"
    total = sum(clean.values())
    roll = int(stable_hash("weighted", seed, CATEGORY_SALT, length=12), 16) / float(16 ** 12)
    cursor = roll * total
    for key, weight in sorted(clean.items()):
        cursor -= weight
        if cursor <= 0:
            return key
    return sorted(clean)[-1]

def _policy_seed(a: dict[str, Any], b: dict[str, Any], key: str | None = None) -> str:
    if key:
        return str(key)
    return stable_hash(item_identity(a), item_identity(b), CATEGORY_SALT, length=24)

def category_policy(tags: set[str], a: dict[str, Any], b: dict[str, Any], key: str | None = None) -> dict[str, Any]:
    """Controlled randomness: high creativity, but no category freefall.

    The old v1.6 policy was too deterministic: default + allowed. This version adds a
    sampled intent lane. The LLM does not freely choose category; it receives a sampled
    category target that can be normal, twist, or rare-but-grounded.
    """
    ca0, cb0 = parent_primary_category(a), parent_primary_category(b)
    cats = {ca0, cb0} - {"generic"}
    parent_damage = max(int(a.get("damage") or 0), int(b.get("damage") or 0))
    min_damage = min(int(a.get("damage") or 0), int(b.get("damage") or 0))
    max_rare = max(int(a.get("rare") or 0), int(b.get("rare") or 0))
    max_depth = max(generation_depth(a), generation_depth(b))
    recursive_pair = max_depth > 0
    weapon_like_count = sum(1 for x in (a, b) if is_weapon_like_parent(x))
    generated_weapon_chain = recursive_pair and weapon_like_count >= 2
    generated_weapon_spine = any(generation_depth(x) > 0 and is_weapon_like_parent(x) for x in (a, b))
    accessory_signal = len(tags & ACCESSORY_HINT_TAGS)
    strong_accessory_signal = len(tags & STRONG_ACCESSORY_TAGS)
    tool_signal = len(tags & TOOL_HINT_TAGS)
    ammo_signal = len(tags & AMMO_HINT_TAGS)
    armor_signal = len(tags & ARMOR_HINT_TAGS)
    has_accessory = "accessory" in cats or strong_accessory_signal > 0
    has_tool = "tool" in cats or tool_signal > 0
    # Ammo tags may appear from projectile behavior (arrow/bullet), but that does not mean
    # the parent item itself is ammunition. Only an actual ammo parent may pull a weapon
    # chain into ammo.
    has_ammo = "ammo" in cats
    has_armor = "armor" in cats or armor_signal > 0
    # Terraria tools/armor/accessories often have damage, but damage alone should not
    # convert them into weapon pressure. Actual weapon category or weapon tag is stronger.
    damage_only_weapon = parent_damage > 0 and not (has_tool or has_accessory or has_armor or has_ammo)
    has_weapon = "weapon" in cats or "weapon" in tags or damage_only_weapon
    has_placeable = bool(tags & PLACEABLE_HINT_TAGS)
    has_tech = bool(tags & {"technology", "circuit", "wire", "electric", "vr", "headset"})
    has_magic = bool(tags & {"magic", "mana", "star", "fallen_star", "fallen star", "crystal", "shadow"})
    has_slime = bool(tags & {"slime", "gel"})
    has_pet = "pet" in cats or "pet" in tags or "minipet" in tags
    seed = _policy_seed(a, b, key)
    roll = int(stable_hash("lane", seed, CATEGORY_SALT, length=12), 16) / float(16 ** 12)
    creativity = CATEGORY_CREATIVITY

    reasons: list[str] = [f"parents={ca0}+{cb0}", f"damage={parent_damage}", f"depth={max_depth}", f"creativity={creativity:.2f}", f"roll={roll:.3f}"]
    default = "generic"
    allowed: set[str] = {"generic"}
    creative_allowed: set[str] = set()
    weights: dict[str, float] = {}
    locked = False

    if has_weapon:
        weapon_pressure = parent_damage + max_rare * 8 + (10 if tags & WEAPON_UPGRADE_TAGS else 0) + (6 if has_magic else 0)
        accessory_pressure = strong_accessory_signal * 12 + (8 if "accessory" in cats else 0)
        tool_pressure = tool_signal * 11 + (8 if "tool" in cats else 0)
        ammo_pressure = ammo_signal * 12 + (8 if "ammo" in cats else 0)
        armor_pressure = armor_signal * 10 + (8 if "armor" in cats else 0)
        default = "weapon"
        allowed = {"weapon"}
        creative_allowed = {"weapon"}
        weights = {"weapon": max(35.0, weapon_pressure + 20.0)}
        reasons.append(f"weapon_pressure={weapon_pressure}")

        # Direct grounded transmutations: visible parent/category signal exists.
        if has_accessory:
            allowed.add("accessory"); creative_allowed.add("accessory")
            weights["accessory"] = 10 + accessory_pressure
            reasons.append(f"accessory_pressure={accessory_pressure}")
        if has_tool:
            allowed.add("tool"); creative_allowed.add("tool")
            weights["tool"] = 9 + tool_pressure
            reasons.append(f"tool_pressure={tool_pressure}")
        if has_ammo and ("ranged" in tags or "gun" in tags or "bow" in tags or ammo_signal >= 2):
            allowed.add("ammo"); creative_allowed.add("ammo")
            weights["ammo"] = 8 + ammo_pressure
        if has_armor:
            allowed.add("armor"); creative_allowed.add("armor")
            weights["armor"] = 7 + armor_pressure

        # Rare but still semantic twists. These are deliberately not always default.
        if has_magic and parent_damage <= 90:
            creative_allowed.add("summon")
            weights["summon"] = 3 + min(18, max_rare * 2 + parent_damage * 0.06)
        if has_tech and parent_damage <= 75:
            creative_allowed.add("technology")
            weights["technology"] = 4 + (8 if has_tech else 0)
        if has_pet and parent_damage <= 70:
            creative_allowed.add("pet")
            weights["pet"] = 2 + (6 if has_slime else 0)
        if has_placeable and parent_damage <= 40:
            creative_allowed.add("placeable_station")
            weights["placeable_station"] = 3 + (6 if has_placeable else 0)

        # Generated combat chains have inertia, not a hard lock. A recursive weapon used
        # as an upgrade spine should usually remain combat-capable, but it may still drift
        # into grounded outcomes when the other parent or the concept supports it: summon
        # weapons, ammo, tools, stations, etc. This prevents both category freefall and the
        # opposite mistake: forcing every recursive chain back to plain weapon forever.
        if generated_weapon_chain or generated_weapon_spine:
            weights["weapon"] = max(weights.get("weapon", 80.0), weapon_pressure + 52.0)
            # Magic/star/shadow parents can rarely transmute a weapon spine into a summon-class
            # combat outcome. attach_gameplay_and_attack maps selected "summon" to a combat
            # item with summon damage, not to a nonfunctional generic object.
            if has_magic or "summon" in tags:
                creative_allowed.add("summon")
                weights["summon"] = max(weights.get("summon", 0.0), 4.0 + min(12.0, max_rare * 1.2 + parent_damage * 0.025))
            # Actual ammo/tool/placeable parent signals are allowed to pull the chain sideways.
            # Mere projectile-profile tags such as arrow/bullet do not set has_ammo.
            if has_ammo:
                creative_allowed.add("ammo"); allowed.add("ammo")
                weights["ammo"] = max(weights.get("ammo", 0.0), 10.0 + ammo_pressure)
            if has_tool:
                creative_allowed.add("tool"); allowed.add("tool")
                weights["tool"] = max(weights.get("tool", 0.0), 10.0 + tool_pressure)
            if has_placeable:
                creative_allowed.add("placeable_station")
                # A strong combat spine can still become a station if a real station/block parent
                # is present, but the chance is small instead of forbidden.
                station_weight = 2.0 + (7.0 if has_placeable else 0.0) / (1.0 + max(0.0, parent_damage - 40.0) / 140.0)
                weights["placeable_station"] = max(weights.get("placeable_station", 0.0), station_weight)
            reasons.append("generated combat spine has inertia, not lock")

        # Strong plain weapons should be heavily biased toward combat, but not hard-locked.
        # If another real parent supplies a grounded transmutation signal, the sampled lane may
        # still accept it. Without such a signal creative_allowed usually contains only weapon.
        if parent_damage >= 60 and not recursive_pair and not (has_accessory or has_tool or has_ammo or has_magic or has_tech or has_placeable):
            weights["weapon"] = max(weights.get("weapon", 80.0), weapon_pressure + 35.0)
            reasons.append("strong plain weapon biased to weapon")
    elif has_accessory:
        default = "accessory"; allowed = {"accessory"}; creative_allowed = {"accessory"}; weights = {"accessory": 60}
        if tags & {"emblem", "glove", "claw", "spike", "tooth"}:
            creative_allowed.add("weapon"); allowed.add("weapon"); weights["weapon"] = 18
        if has_magic:
            creative_allowed.add("summon"); weights["summon"] = 8
    elif has_tool:
        default = "tool"; allowed = {"tool"}; creative_allowed = {"tool"}; weights = {"tool": 60}
        if tags & {"axe", "hammer", "pickaxe", "drill", "chainsaw"}:
            allowed.add("weapon"); creative_allowed.add("weapon"); weights["weapon"] = 20 + parent_damage
    elif has_ammo:
        default = "ammo"; allowed = {"ammo"}; creative_allowed = {"ammo"}; weights = {"ammo": 60}
        if tags & {"rocket", "bullet", "arrow", "explosive"}:
            allowed.add("weapon"); creative_allowed.add("weapon"); weights["weapon"] = 14
    elif has_armor:
        default = "armor"; allowed = {"armor", "accessory"}; creative_allowed = {"armor", "accessory"}; weights = {"armor": 50, "accessory": 18}
    elif "potion" in tags or "consumable" in tags:
        default = "potion"; allowed = {"potion"}; creative_allowed = {"potion"}; weights = {"potion": 60}
        if has_magic:
            creative_allowed.add("accessory"); weights["accessory"] = 5
    elif has_tech:
        default = "technology"; allowed = {"technology", "placeable_station", "furniture"}; creative_allowed = set(allowed); weights = {"technology": 44, "placeable_station": 22, "furniture": 12}
    elif "material" in tags and not (tags & {"chair", "workbench", "bench", "furniture", "crafting_station"}):
        default = "material"; allowed = {"material"}; creative_allowed = {"material", "accessory", "weapon", "placeable_station"}; weights = {"material": 62, "accessory": 5, "weapon": 7, "placeable_station": 4 if has_placeable else 1}
    elif has_placeable:
        default = "furniture"; allowed = {"furniture", "placeable_station"}; creative_allowed = set(allowed); weights = {"furniture": 45, "placeable_station": 18}

    allowed = {normalize_category(x) for x in allowed if normalize_category(x) != "generic"} or {normalize_category(default)}
    creative_allowed = {normalize_category(x) for x in creative_allowed if normalize_category(x) != "generic"} or set(allowed)
    default = normalize_category(default if default != "generic" else sorted(allowed)[0])

    # Lane selection. More creativity means fewer stable results and more twist/rare results.
    effective_creativity = min(1.0, creativity + 0.06 * max_depth)
    stable_threshold = max(0.42, 0.86 - 0.42 * effective_creativity)
    twist_threshold = max(stable_threshold, min(0.96, stable_threshold + 0.10 + 0.28 * effective_creativity))
    if locked or len(creative_allowed) <= 1:
        lane = "stable"
        selected = default
    elif roll < stable_threshold:
        lane = "stable"
        selected = default
    elif roll < twist_threshold:
        lane = "twist"
        candidate_weights = {k: v for k, v in weights.items() if k in allowed}
        if len(candidate_weights) <= 1:
            candidate_weights = {k: v for k, v in weights.items() if k in creative_allowed}
        selected = _weighted_choice(candidate_weights, seed + ":twist")
        if selected == "generic":
            selected = default
    else:
        lane = "rare"
        candidate_weights = {k: max(1.0, weights.get(k, 4.0)) for k in creative_allowed}
        # In rare lane, downweight the default so surprise can actually happen.
        if default in candidate_weights and len(candidate_weights) > 1:
            candidate_weights[default] *= 0.28
        selected = _weighted_choice(candidate_weights, seed + ":rare")
        if selected == "generic":
            selected = default

    return {
        "default": default,
        "selected": normalize_category(selected),
        "lane": lane,
        "allowed": sorted(allowed),
        "creativeAllowed": sorted(creative_allowed),
        "locked": bool(locked),
        "enforceSampled": bool(CATEGORY_ENFORCE_SAMPLED),
        "parentCategories": [ca0, cb0],
        "recursivePair": bool(recursive_pair),
        "maxGenerationDepth": int(max_depth),
        "reason": "; ".join(reasons),
        "weights": {k: round(float(v), 2) for k, v in sorted(weights.items())},
    }

def choose_result_category(tags: set[str], a: dict[str, Any], b: dict[str, Any], key: str | None = None) -> str:
    return str(category_policy(tags, a, b, key).get("selected") or category_policy(tags, a, b, key)["default"])

def coerce_category_by_policy(requested: Any, tags: set[str], a: dict[str, Any], b: dict[str, Any], key: str | None = None) -> tuple[str, dict[str, Any]]:
    policy = category_policy(tags, a, b, key)
    requested_norm = normalize_category(requested)
    selected_target = normalize_category(policy.get("selected") or policy.get("default"))
    allowed = set(policy.get("allowed") or []) | set(policy.get("creativeAllowed") or [])
    if CATEGORY_ENFORCE_SAMPLED:
        selected = selected_target
        if requested_norm != selected_target:
            policy["repair"] = f"category '{requested_norm}' replaced by sampled intent '{selected_target}' ({policy.get('lane')})"
    else:
        selected = requested_norm if requested_norm in allowed else selected_target
        if selected != requested_norm:
            policy["repair"] = f"category '{requested_norm}' is outside grounded categories {sorted(allowed)}; repaired to '{selected}'"
        elif selected != policy.get("default"):
            policy["transmutation"] = f"accepted grounded category '{selected}' over default '{policy['default']}'"
    policy["requested"] = requested_norm
    policy["final"] = selected
    return selected, policy

def canonical_for_result(name: str, category: str, tags: list[str]) -> dict[str, Any]:
    tagset = set(tags)
    head = guess_head(name, tagset)
    hard = sorted(t for t in tagset if t in HARD_TAGS)
    soft = sorted(t for t in tagset if t not in hard)
    return {
        "headNoun": head,
        "modifiers": [],
        "material": "wood" if "wood" in tagset else "",
        "class": category,
        "shapeAnchors": sorted(set([head] + VISUAL_SYNONYMS.get(head, []))),
        "visualAnchors": sorted(set(required_anchors_from_tags(tagset) or [name])),
        "hardTags": hard,
        "softTags": soft,
    }

def rep(parent: str, mode: str, importance: str, visual_anchor: str, placement: str) -> dict[str, Any]:
    return {"parent": parent, "mode": mode, "importance": importance, "visualAnchor": visual_anchor, "placement": placement, "rationale": "preserve parent provenance"}

def rep_for_parent(item: dict[str, Any], c: dict[str, Any], importance: str) -> dict[str, Any]:
    va = (c.get("visualAnchors") or [name_of(item)])[0]
    return rep(name_of(item), "visual", importance, va, "visible in item icon")

def inh_for_parent(item: dict[str, Any], c: dict[str, Any], role: str) -> dict[str, Any]:
    return {
        "parent": name_of(item),
        "role": role,
        "preservedFeatures": list(dict.fromkeys((c.get("hardTags") or []) + ([c.get("headNoun")] if c.get("headNoun") else []))),
        "visualAnchors": c.get("visualAnchors") or [name_of(item)],
        "gameplayAnchors": [],
        "lossPolicy": "preserve_hard_tags",
    }

def required_anchors_from(ca: dict[str, Any], cb: dict[str, Any], tags: set[str]) -> list[str]:
    anchors: list[str] = []
    anchors.extend(ca.get("visualAnchors") or [])
    anchors.extend(cb.get("visualAnchors") or [])
    anchors.extend(required_anchors_from_tags(tags))
    return list(dict.fromkeys(anchors))[:8]

def required_anchors_from_tags(tags: set[str]) -> list[str]:
    anchors = []
    for tag in tags:
        anchors.extend(VISUAL_SYNONYMS.get(tag, []))
    return list(dict.fromkeys(anchors))

def palette_from(tags: set[str]) -> list[str]:
    colors = []
    for t in tags:
        colors.extend(PALETTES.get(t, []))
    return list(dict.fromkeys(colors))[:6] or ["gray", "white"]

def apply_family_locks_to_genome(g: dict[str, Any], a: dict[str, Any], b: dict[str, Any], data: dict[str, Any], stage: dict[str, Any]) -> dict[str, Any]:
    """Universal execution guardrails for an LLM-authored combat genome.

    This function must not decide that a concrete source item "should" become a special
    family. It only clamps authored fields that can break gameplay, performance or sync.
    Normal authored values inside the broad corridor are preserved.
    """
    before = dict(g)
    power = max(0.5, float(stage.get("powerBudget") or 1.0))

    def _num(key: str, default: float) -> float:
        try:
            v = float(g.get(key) if g.get(key) not in (None, "") else default)
            return v if math.isfinite(v) else default
        except Exception:
            return default

    # Universal power/performance corridor. No parent-name exceptions, no semantic rewrites.
    g["shotCount"] = min(max(1, int(round(_num("shotCount", 1)))), 6)
    raw_pierce = int(round(_num("pierce", 0)))
    if raw_pierce == -1:
        g["pierce"] = -1
        g["shotCount"] = min(int(g.get("shotCount") or 1), 2)
        g["lifetimeTicks"] = min(max(25, int(round(_num("lifetimeTicks", 90)))), 300)
        g["extraUpdates"] = min(max(0, int(round(_num("extraUpdates", 0)))), 1)
    else:
        g["pierce"] = min(max(0, raw_pierce), 8)
        g["lifetimeTicks"] = min(max(25, int(round(_num("lifetimeTicks", 90)))), 540)
        g["extraUpdates"] = min(max(0, int(round(_num("extraUpdates", 0)))), 2)

    # AoE is allowed when authored, including magical/aura-style effects. The cap is a
    # broad technical/progression envelope, not a source-family permission check.
    aoe_cap = 2.0 + min(3.25, power * 0.58)
    g["aoeRadiusTiles"] = min(max(0.0, _num("aoeRadiusTiles", 0.0)), aoe_cap)
    g["rangeTiles"] = min(max(4.0, _num("rangeTiles", 35.0)), 105.0)
    g["homingStrength"] = min(max(0.0, _num("homingStrength", 0.0)), 0.68)

    if before != g:
        try:
            data.setdefault("debug", {})["runtimeSafetyClamps"] = json.dumps({
                "before": {k: before.get(k) for k in ["shotCount", "pierce", "aoeRadiusTiles", "lifetimeTicks", "rangeTiles", "extraUpdates", "homingStrength"]},
                "after": {k: g.get(k) for k in ["shotCount", "pierce", "aoeRadiusTiles", "lifetimeTicks", "rangeTiles", "extraUpdates", "homingStrength"]},
                "basis": "universal numeric safety corridor; no item-family semantic routing",
            }, ensure_ascii=False)
        except Exception:
            pass
    return g

def _stringish(x: Any, fallback: str = "") -> str:
    if x is None:
        return fallback
    if isinstance(x, (list, tuple)):
        return "; ".join(str(v) for v in x if str(v).strip()) or fallback
    if isinstance(x, dict):
        return json.dumps(x, ensure_ascii=False, separators=(",", ":"))
    return str(x)

def validate_and_repair(data: dict[str, Any], a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], key: str) -> dict[str, Any]:
    data.setdefault("schemaVersion", 1)
    data.setdefault("id", "g_" + stable_hash(key, data.get("name", ""), length=16))
    data.setdefault("recipeKey", key)
    data.setdefault("parentA", name_of(a))
    data.setdefault("parentB", name_of(b))
    data.setdefault("sourceMode", "generated")
    data.setdefault("mergeMode", "literal")
    data["category"] = normalize_category(data.get("category", "generic"))
    data.setdefault("tags", [])
    data.setdefault("canonical", canonical_for_result(data.get("name", "Generated Item"), data.get("category", "generic"), data.get("tags", [])))
    data.setdefault("sourceRepresentation", [])
    data.setdefault("inheritance", [])
    data.setdefault("lossBudget", {})
    data.setdefault("visual", {})
    data.setdefault("gameplay", {})
    data.setdefault("accessory", {})
    data.setdefault("attack", {})
    data.setdefault("debug", {})
    if "itemKnowledge" not in data:
        data["itemKnowledge"] = build_item_knowledge(a, b, ca, cb)
    if LLM_RUNTIME_AUTHORING and runtime_plan(data):
        policy_for_meta = {"mode": "llm_runtime_result_kind", "selected": normalize_category(data.get("category", "generic")), "default": normalize_category(data.get("category", "generic")), "allowed": [normalize_category(data.get("category", "generic"))], "creativeAllowed": [normalize_category(data.get("category", "generic"))]}
    else:
        policy_for_meta = category_policy(set(str(t).lower() for t in data.get("tags", [])) | tags_of(a) | tags_of(b), a, b, key)
    meta = data.get("recipeMeta") if isinstance(data.get("recipeMeta"), dict) else {}
    repaired_meta = recipe_meta(a, b, set(str(t).lower() for t in data.get("tags", [])) | tags_of(a) | tags_of(b), policy_for_meta)
    repaired_meta.update(meta)
    # These fields are authoritative and should not be dropped by the LLM.
    repaired_meta["universalRecipe"] = True
    repaired_meta["generationDepth"] = max(generation_depth(a), generation_depth(b)) + 1
    repaired_meta["parentGeneratedDepths"] = [generation_depth(a), generation_depth(b)]
    data["recipeMeta"] = repaired_meta
    data["debug"]["generationDepth"] = str(repaired_meta["generationDepth"])
    data["debug"]["recipeCoherence"] = str(repaired_meta.get("recipeCoherence", ""))

    # Force parent representation if planner dropped it.
    existing_parents = {x.get("parent") for x in data.get("inheritance", []) if isinstance(x, dict)}
    for item, c, role in [(a, ca, "base_shape"), (b, cb, "influence")]:
        if name_of(item) not in existing_parents:
            data["inheritance"].append(inh_for_parent(item, c, role))
    existing_rep = {x.get("parent") for x in data.get("sourceRepresentation", []) if isinstance(x, dict)}
    for item, c, imp in [(a, ca, "primary"), (b, cb, "secondary")]:
        if name_of(item) not in existing_rep:
            data["sourceRepresentation"].append(rep_for_parent(item, c, imp))

    # Hard tag preservation belongs only to non-runtime fallback. In runtime-authoring mode,
    # parent tags are raw context, not semantic tags injected after the LLM already authored it.
    parent_hard = set(ca.get("hardTags") or []) | set(cb.get("hardTags") or [])
    tags = set(str(t).lower() for t in data.get("tags", []))
    if not (LLM_RUNTIME_AUTHORING and runtime_plan(data)):
        tags |= parent_hard
    data["tags"] = sorted(tags)

    requested_category = data.get("category", "generic")
    gameplay = data.setdefault("gameplay", {})
    if gameplay.get("kind"):
        requested_category = gameplay.get("kind")
    if LLM_RUNTIME_AUTHORING and runtime_plan(data):
        selected_category, policy = llm_runtime_result_kind_policy(data, requested_category, tags, a, b, key)
    elif is_llm_planner(data):
        selected_category, policy = llm_category_without_router(data, requested_category, tags, a, b, key)
    else:
        selected_category, policy = coerce_category_by_policy(requested_category, tags, a, b, key)
    data["category"] = selected_category
    gameplay["kind"] = selected_category
    data.setdefault("debug", {})["categoryPolicy"] = json.dumps(policy, ensure_ascii=False)
    # Names must be item names, not mod/service labels. The LLM owns naming when enabled;
    # deterministic fallback only repairs empty/service-looking names.
    data = repair_name_if_needed(data, a, b, ca, cb, key)
    if LLM_RUNTIME_AUTHORING:
        data = repair_runtime_plan_if_needed(data, a, b, ca, cb, key)
    data = normalize_runtime_authoring_fields(data)
    if LLM_RUNTIME_AUTHORING:
        # repair_runtime_plan_if_needed() may already have recorded an actual repair
        # result.  Do not overwrite it with the legacy-genome skip note; in runtime
        # authoring mode we skip only the old attack.genome repair loop, not the
        # runtimePlan validation/repair path above.
        data.setdefault("debug", {}).setdefault(
            "runtimeRepairPath",
            "not_needed: runtimePlan.engineCalls is the authored source; legacy attack.genome repair skipped",
        )
    else:
        data = repair_llm_combat_genome_if_needed(data, a, b, ca, cb, key)
    if data["category"] == "accessory":
        data.setdefault("accessory", {})["enabled"] = True
        data.setdefault("attack", {})["enabled"] = False

    # Required visual anchors must include hard visual anchors.
    visual = data.setdefault("visual", {})
    anchors = list(visual.get("requiredAnchors") or [])
    for c in [ca, cb]:
        for t in c.get("hardTags") or []:
            anchors.extend(VISUAL_SYNONYMS.get(t, []))
        anchors.extend(c.get("visualAnchors") or [])
    visual["requiredAnchors"] = list(dict.fromkeys([a for a in anchors if a]))[:10]
    raw_palette = visual.get("palette")
    if isinstance(raw_palette, list) and raw_palette:
        visual["palette"] = [str(x) for x in raw_palette if str(x).strip()][:8]
    else:
        visual["palette"] = palette_from(tags)
    visual.setdefault("objectType", slug(data.get("name", "generated_item")))
    if isinstance(data.get("attack"), dict) and data["attack"].get("genome") is None:
        data["attack"]["genome"] = {}
    data["canonical"] = canonical_for_result(data.get("name", "Generated Item"), data.get("category", "generic"), list(tags))
    score = preservation_score(data, ca, cb)
    visual["preservationScore"] = score
    if score < 0.65:
        data["debug"]["repair"] = "low preservation; source anchors forcibly injected"
    return data

def preservation_score(data: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any]) -> float:
    required = set(ca.get("hardTags") or []) | set(cb.get("hardTags") or [])
    if not required:
        return 1.0
    hay = " ".join(json.dumps(x, ensure_ascii=False).lower() for x in [data.get("tags"), data.get("inheritance"), data.get("visual"), data.get("name")])
    hit = sum(1 for t in required if t.lower() in hay)
    return round(hit / max(1, len(required)), 3)

def item_power_score(item: dict[str, Any]) -> float:
    signal = mechanic_signal_power(item)
    score = float(signal.get("score") or 0)
    depth = generation_depth(item)
    tags = tags_of(item)
    n = lower_name(item)
    # Name tags are still hints, but no longer a rarity substitute.
    if any(x in n for x in ["copper", "tin", "wood", "wooden"]): score -= 3
    if any(x in n for x in ["demonite", "crimtane", "molten", "hellstone", "night"]): score += 8
    if any(x in n for x in ["cobalt", "palladium", "mythril", "orichalcum", "adamantite", "titanium"]): score += 18
    if any(x in n for x in ["hallowed", "chlorophyte", "terra", "true"]): score += 30
    if any(x in n for x in ["lunar", "solar", "vortex", "nebula", "stardust", "zenith", "meowmere"]): score += 55
    if tags & {"star", "lunar", "solar", "vortex", "nebula", "stardust"}: score += 8
    if tags & {"magic", "mana"}: score += 4
    if tags & {"shadow", "void", "night"}: score += 5
    if tags & {"technology", "wire", "electric", "circuit"}: score += 4
    if tags & {"dirt", "earth", "stone", "sand", "block"}: score += 1
    if "material" in tags and item_num(item, "damage") == 0 and not str(signal.get("basis", "")).startswith("mechanics"):
        # Materials are allowed to carry huge tier power (Calamity-like bars can outrank vanilla endgame weapons),
        # but they transfer as crafting-tier power, not raw damage.
        rb = signal.get("rarityBaseline") if isinstance(signal.get("rarityBaseline"), dict) else {}
        if float(rb.get("convertedPower") or 0) >= 180:
            score *= 1.0
        else:
            score *= 0.72
    score += min(depth, 20) * RECURSIVE_POWER_GROWTH * 8.0
    return max(0.0, score)

def tier_rank(tier: Any) -> int:
    t = str(tier or "unknown")
    if t.endswith("_influenced"):
        t = t[:-11]
    return int(TIER_RANK.get(t, -1))

def influenced_tier(tier: str) -> str:
    tier = str(tier or "unknown")
    if tier in MODDED_HIGH_TIERS:
        return tier + "_influenced"
    return tier

def universal_parent_relation(strong_card: dict[str, Any], weak_card: dict[str, Any], tags: set[str]) -> dict[str, Any]:
    """Runtime-safe parent relation.

    This deliberately avoids hand-authored recipe graphs for specific mods/items.
    It only uses observable/card-level properties: category, tier score, source mod,
    broad tags, and whether a high-tier material has a credible non-trivial anchor.
    """
    s_cat = normalize_category(strong_card.get("category") or "generic")
    w_cat = normalize_category(weak_card.get("category") or "generic")
    s_power = float(strong_card.get("powerScore") or 0)
    w_power = float(weak_card.get("powerScore") or 0)
    s_sig = strong_card.get("signals") if isinstance(strong_card.get("signals"), dict) else {}
    w_sig = weak_card.get("signals") if isinstance(weak_card.get("signals"), dict) else {}
    s_mod = str(s_sig.get("sourceMod") or "Terraria")
    w_mod = str(w_sig.get("sourceMod") or "Terraria")
    same_nonvanilla_source = bool(s_mod and w_mod and s_mod == w_mod and s_mod.lower() != "terraria")
    same_family = s_cat == w_cat
    material_with_item = {s_cat, w_cat} & {"material"} and ({s_cat, w_cat} & {"weapon", "tool", "armor", "accessory"})
    high_pair = min(s_power, w_power) >= VANILLA_ENDGAME_POWER * 0.72
    high_material = max(s_power, w_power) >= VANILLA_ENDGAME_POWER and {s_cat, w_cat} & {"material"}
    thematic = bool(tags & {"cosmic", "lunar", "solar", "vortex", "nebula", "stardust", "shadow", "void", "star", "fire", "ice", "frost", "electric", "technology", "plant", "earth"})

    if material_with_item and high_material and (same_nonvanilla_source or thematic or min(s_power, w_power) >= TIER_DEFAULT_POWER.get("post_plantera", 185)):
        quality = "high_tier_material_with_credible_item"
        strength = 0.86
    elif s_cat == "material" and w_cat == "material" and high_pair and (same_nonvanilla_source or thematic):
        quality = "high_tier_material_blend"
        strength = 0.84
    elif same_family and min(s_power, w_power) >= TIER_DEFAULT_POWER.get("hardmode_early", 105):
        quality = "same_role_synergy"
        strength = 0.72
    elif same_nonvanilla_source and min(s_power, w_power) >= TIER_DEFAULT_POWER.get("pre_hardmode_late", 55):
        quality = "same_mod_soft_synergy"
        strength = 0.58
    else:
        quality = "loose_mix"
        strength = 0.0
    return {
        "quality": quality,
        "strength": round(strength, 3),
        "sameNonVanillaSource": same_nonvanilla_source,
        "strongCategory": s_cat,
        "weakCategory": w_cat,
        "strongSourceMod": s_mod,
        "weakSourceMod": w_mod,
        "runtimeOnly": True,
    }

def recipe_power_transfer(cards: list[dict[str, Any]], scores: list[float], tags: set[str]) -> dict[str, Any]:
    """How much of a parent tier can actually become the result.

v2.7 distinction:
    - parentTier says how advanced the strongest parent is;
    - resultTier says how advanced the produced item really is.

    This prevents high-rarity modded material + Wood from becoming full endgame gear,
    while still allowing a strong weapon/tool/accessory base to act as a credible anchor.
    """
    if len(cards) < 2:
        return {"quality": "single", "resultTier": "unknown", "resultPowerScore": 1, "strongestTier": "unknown", "weakestTier": "unknown", "powerMultiplier": 1.0, "weakAnchor": False}
    ordered = sorted(zip(cards, scores), key=lambda x: float(x[1] or 0), reverse=True)
    strong_card, strong_score = ordered[0]
    weak_card, weak_score = ordered[1]
    strong_tier = str(strong_card.get("tier") or "unknown")
    weak_tier = str(weak_card.get("tier") or "unknown")
    strong_cat = normalize_category(strong_card.get("category") or "generic")
    weak_cat = normalize_category(weak_card.get("category") or "generic")
    strong_rank = tier_rank(strong_tier)
    weak_rank = tier_rank(weak_tier)
    strong_score = float(strong_score or 0)
    weak_score = float(weak_score or 0)

    strong_is_high_modded = strong_tier in MODDED_HIGH_TIERS or strong_rank >= TIER_RANK.get("post_moonlord", 13)
    weak_is_basic = weak_score < 55 or weak_rank <= TIER_RANK.get("pre_boss", 3)
    weak_is_vanilla_endgameish = weak_rank >= TIER_RANK.get("lunar", 11) or float((weak_card.get("signals") or {}).get("damage") or 0) >= 150
    weapon_catalyst = weak_cat == "weapon" and weak_is_vanilla_endgameish
    same_family = strong_cat == weak_cat
    material_with_item = {strong_cat, weak_cat} & {"material"} and ({strong_cat, weak_cat} & {"weapon", "tool", "armor", "accessory"})
    thematic = bool(tags & {"cosmic", "lunar", "auric", "yharon", "devourer", "exodium", "miracle", "shadow", "void", "star", "draedon", "exo", "calamity"})
    recipe_relation = universal_parent_relation(strong_card, weak_card, tags)
    recipe_quality = str(recipe_relation.get("quality") or "")

    if strong_is_high_modded and recipe_quality in {"high_tier_material_with_credible_item", "high_tier_material_blend", "same_role_synergy", "same_mod_soft_synergy"}:
        quality = recipe_quality
        result_tier = strong_tier
        if recipe_quality == "high_tier_material_blend":
            multiplier, weak_factor = 0.90, 0.10
        elif recipe_quality == "high_tier_material_with_credible_item":
            multiplier, weak_factor = 0.88, 0.09
        else:
            multiplier, weak_factor = 0.94, 0.13
    elif strong_is_high_modded and weak_is_basic and not weapon_catalyst:
        quality = "diluted_weak_anchor"
        result_tier = influenced_tier(strong_tier)
        multiplier = 0.52
        weak_factor = 0.035
    elif strong_is_high_modded and weapon_catalyst:
        # Zenith is vanilla-endgame, not Calamity-endgame, but it is a very strong weapon base/catalyst.
        quality = "high_modded_material_plus_vanilla_endgame_catalyst"
        result_tier = strong_tier
        multiplier = 0.90
        weak_factor = 0.08
    elif strong_is_high_modded and material_with_item:
        quality = "high_modded_material_transfers_through_item"
        result_tier = strong_tier if weak_score >= VANILLA_ENDGAME_POWER * 0.55 or thematic else influenced_tier(strong_tier)
        multiplier = 0.80 if result_tier.endswith("_influenced") else 0.88
        weak_factor = 0.07
    elif recipe_quality in {"same_role_synergy", "same_mod_soft_synergy"} and strong_score >= TIER_DEFAULT_POWER.get("hardmode_early", 105):
        quality = recipe_quality
        result_tier = strong_tier
        multiplier = 0.92
        weak_factor = 0.12
    elif weak_score < strong_score * 0.20:
        quality = "asymmetric"
        result_tier = influenced_tier(strong_tier) if strong_is_high_modded else strong_tier
        multiplier = 0.68 if strong_is_high_modded else 0.78
        weak_factor = 0.06
    elif same_family or material_with_item or thematic:
        quality = "strong_synergy"
        result_tier = strong_tier
        multiplier = 0.94
        weak_factor = 0.14
    else:
        quality = "mixed"
        result_tier = strong_tier
        multiplier = 0.84
        weak_factor = 0.10

    result_power = max(1.0, strong_score * multiplier + weak_score * weak_factor)
    return {
        "quality": quality,
        "strongestTier": strong_tier,
        "weakestTier": weak_tier,
        "resultTier": result_tier,
        "strongestPowerScore": round(strong_score, 2),
        "weakestPowerScore": round(weak_score, 2),
        "resultPowerScore": round(result_power, 2),
        "powerMultiplier": round(multiplier, 3),
        "weakFactor": round(weak_factor, 3),
        "weakAnchor": bool(weak_is_basic and strong_score > 180),
        "weaponCatalyst": bool(weapon_catalyst),
        "recipeRelation": recipe_relation,
        "note": "High modded rarity tiers can outrank vanilla endgame; weak/basic anchors dilute result tier unless runtime metadata shows a credible anchor."
    }



def vanilla_like_weapon_envelope(stage: dict[str, Any] | str | None) -> dict[str, float]:
    return weapon_envelope_for_bucket(stage, extra_endgame_aliases=MODDED_HIGH_TIERS)


def clamp_vanilla_like_weapon_damage(
    raw_damage: int,
    max_parent_damage: int,
    stage: dict[str, Any],
    *,
    use_time: int | None = None,
    shot_count: int = 1,
    cost_multiplier: float = 1.0,
    raise_floor: bool = True,
) -> int:
    if raw_damage <= 0:
        return 0
    env = vanilla_like_weapon_envelope(stage)
    transfer = stage.get("powerTransfer") if isinstance(stage.get("powerTransfer"), dict) else {}
    weak_anchor = bool(transfer.get("weakAnchor"))
    catalyst = stage.get("catalystPressure") if isinstance(stage.get("catalystPressure"), dict) else {}
    catalyst_pressure = float(catalyst.get("pressure") or 0.0)

    stage_min = int(env["min"])
    stage_max = int(env["max"])
    # Parent inertia: generated upgrades should not randomly collapse, but weak/basic
    # anchors cannot multiply a strong weapon endlessly.
    if max_parent_damage > 0 and not weak_anchor:
        stage_min = min(max(stage_min, int(max_parent_damage * (0.42 + min(0.30, catalyst_pressure * 0.10)))), stage_max)
        stage_max = max(stage_max, int(max_parent_damage * (1.80 + min(0.55, catalyst_pressure * 0.14))) + 18)
    elif max_parent_damage > 0 and weak_anchor:
        stage_max = min(stage_max, max(max_parent_damage + int(env["weak_bonus"]), int(max_parent_damage * 1.32) + 12))

    # Fast/multishot authored weapons are bounded mostly by DPS, not by raw hit damage.
    if use_time is not None and use_time > 0:
        shots = max(1, min(8, int(shot_count or 1)))
        use = max(6.0, float(use_time))
        # `behavior_cost_multiplier` already includes shot_count pressure.  For DPS
        # comparison we count actual shots once, then apply only the non-shot part of
        # the cost as a mechanic pressure multiplier.  Older code divided by cost here,
        # which accidentally made expensive authored mechanics *easier* to keep at high
        # damage.
        shot_cost = 1.0 + max(0.0, shots - 1.0) * 0.55
        pressure_cost = max(0.55, min(2.75, float(cost_multiplier or 1.0) / max(1.0, shot_cost)))
        effective_dps = raw_damage * shots * 60.0 / use * pressure_cost
        dps_cap = float(env["dps"])
        if max_parent_damage > 0 and not weak_anchor:
            parent_use = max(6.0, float(stage.get("sourceFastestUseTime") or use_time))
            dps_cap = max(dps_cap, max_parent_damage * 60.0 / parent_use * 1.72)
        if weak_anchor:
            dps_cap *= 1.04
        if effective_dps > dps_cap:
            raw_damage = max(1, int(dps_cap * use / (60.0 * shots * pressure_cost)))

    floor = stage_min if raise_floor else 1
    return int(max(1, min(max(raw_damage, floor), stage_max)))

def stat_profile_for(a: dict[str, Any], b: dict[str, Any], tags: set[str]) -> dict[str, Any]:
    damages = [int(a.get("damage") or 0), int(b.get("damage") or 0)]
    rares = [int(a.get("rare") or 0), int(b.get("rare") or 0)]
    values = [int(a.get("value") or 0), int(b.get("value") or 0)]
    cards = [infer_item_card(a), infer_item_card(b)]
    rarity_baselines = [rarity_baseline_signal(a, tags_of(a), parent_primary_category(a)), rarity_baseline_signal(b, tags_of(b), parent_primary_category(b))]
    knowledge_scores = [float(c.get("powerScore") or 0) for c in cards]
    rarity_scores = [float(rarity_baselines[0].get("convertedPower") or 0), float(rarity_baselines[1].get("convertedPower") or 0)]
    scores = [max(item_power_score(a), knowledge_scores[0], rarity_scores[0]), max(item_power_score(b), knowledge_scores[1], rarity_scores[1])]
    transfer = recipe_power_transfer(cards, scores, tags)
    def _theme_only_parent(item: dict[str, Any]) -> bool:
        tg = tags_of(item)
        return (
            item_num(item, "damage", 0) <= 0
            and item_num(item, "shoot", 0) <= 0
            and (item_num(item, "createTile", -1) >= 0 or bool(tg & {"plant", "flower", "furniture", "placeable", "sunflower", "подсолн"}))
        )
    one_theme_parent = (_theme_only_parent(a) and item_num(b, "damage", 0) > 0) or (_theme_only_parent(b) and item_num(a, "damage", 0) > 0)
    catalyst = pair_catalyst_pressure(a, b)
    catalyst_pressure = float(catalyst.get("pressure") or 0.0)
    max_damage = max(damages)
    min_damage = min([d for d in damages if d > 0] or [0])
    second_damage = min_damage if max_damage != min_damage else (damages[0] if damages[0] else damages[1])
    synergy = 0
    if tags & {"star", "lunar", "solar", "vortex", "nebula", "stardust"}: synergy += 10
    if tags & {"wire", "electric", "technology", "circuit"}: synergy += 6
    if tags & {"night", "shadow", "void"}: synergy += 8
    if tags & {"fire", "hellstone", "ice", "frost", "poison", "spore"}: synergy += 5
    if tags & {"dirt", "earth", "stone", "sand", "block"}: synergy += 2
    derived = max(float(transfer.get("resultPowerScore") or 0), max(scores) * 0.42 + min(scores) * 0.10 + synergy) + synergy
    if one_theme_parent and max_damage <= 18:
        derived = min(derived, 48.0)
    # Recursive generated items may become more complex, but depth alone must not staircase
    # weak early items into mech/plantera tiers.
    max_depth = max(generation_depth(a), generation_depth(b))
    if max_depth > 0 and max_damage <= 18:
        derived = min(derived, 54.0)  # at most pre-boss for weak recursive chains
    elif max_depth > 0 and max_damage <= 32:
        derived = min(derived, 84.0)  # at most late pre-hardmode for modest recursive chains
    # Broad serious-material lift. This is route/progression pressure, not a named recipe.
    if max_damage > 0 and catalyst_pressure > 0:
        derived += catalyst_pressure * 30.0
    if max_damage > 0:
        derived_damage = max_damage + int(second_damage * 0.28) + 5 + int((derived ** 0.5) * 0.72)
        if catalyst_pressure > 0:
            derived_damage += int(max(1, max_damage) * (0.12 + 0.14 * catalyst_pressure))
    else:
        derived_damage = 0
    # soft anti-spike: weak non-weapon ingredient should not drag a good weapon down, but also should not double it.
    damage_cap = max(12, max_damage + max(12, int(max_damage * (0.58 + 0.24 * catalyst_pressure))) + synergy) if max_damage > 0 else 0
    # A Calamity-tier material can raise a vanilla weapon base, but weak anchors still do not create a full-tier weapon.
    strongest_material_power = max([float(c.get("powerScore") or 0) for c in cards if c.get("category") == "material" or c.get("signals", {}).get("isMaterial")] or [0.0])
    if max_damage > 0 and strongest_material_power > VANILLA_ENDGAME_POWER:
        quality = str(transfer.get("quality") or "")
        lift_mul = 0.24 if "vanilla_endgame_catalyst" in quality else 0.12 if not str(transfer.get("resultTier", "")).endswith("_influenced") else 0.05
        material_lift = int(max(0.0, strongest_material_power - VANILLA_ENDGAME_POWER) * lift_mul)
        derived_damage += int(material_lift * 0.62)
        damage_cap = max(damage_cap, max_damage + max(10, material_lift))
    if max_damage > 0:
        derived_damage = clamp(derived_damage, max(1, max_damage + 1), damage_cap)
    power_budget = 0.95 + min(5.6, derived / 50.0)
    if derived < 16: hint = "wood"
    elif derived < 32: hint = "early"
    elif derived < 55: hint = "pre_boss"
    elif derived < 85: hint = "pre_hardmode_late"
    elif derived < 125: hint = "hardmode_early"
    elif derived < 175: hint = "mech"
    elif derived < 235: hint = "plantera"
    elif derived < 310: hint = "lunar"
    else: hint = "endgame"
    strongest_tiers = {str(c.get("tier", "")) for c in cards}
    transfer_tier = str(transfer.get("resultTier") or "")
    if transfer_tier in MODDED_HIGH_TIERS or transfer_tier.endswith("_influenced"):
        hint = "endgame"
    elif strongest_tiers & {"endgame", "post_moonlord", "superboss", "devourer", "auric", "exo_yharon_plus", "shadowspec", "calamity_red_prefix"}:
        hint = "endgame"
    elif "lunar" in strongest_tiers and hint not in {"endgame", "lunar"}:
        hint = "lunar"
    elif strongest_tiers & {"post_plantera", "post_golem"} and hint in {"wood", "early", "pre_boss", "pre_hardmode_late", "hardmode_early", "mech"}:
        hint = "plantera"
    return {
        "name": hint,
        "balanceMode": "stat_and_knowledge_derived",
        "scores": [round(scores[0], 2), round(scores[1], 2)],
        "knowledgePowerScores": [round(knowledge_scores[0], 2), round(knowledge_scores[1], 2)],
        "knowledgeTiers": [cards[0].get("tier", "unknown"), cards[1].get("tier", "unknown")],
        "powerTransfer": transfer,
        "catalystPressure": catalyst,
        "rarityBaselineScores": [round(rarity_scores[0], 2), round(rarity_scores[1], 2)],
        "rarityBaselines": rarity_baselines,
        "sourceDamage": damages,
        "sourceFastestUseTime": min([float(item_num(x, "useTime", 999)) for x in (a, b) if item_num(x, "damage") > 0] or [float("inf")]),
        "sourceRarity": rares,
        "sourceValue": values,
        "parentGeneratedDepths": [generation_depth(a), generation_depth(b)],
        "recipeCoherence": recipe_coherence(tags, a, b),
        "derivedPower": round(derived, 2),
        "derivedDamage": int(derived_damage),
        "powerBudget": round(power_budget, 2),
        "balanceEnvelope": vanilla_like_weapon_envelope(hint),
        "rarity": max(0, min(13, max(rares) + (1 if derived > 85 else 0) + (1 if derived > 175 else 0))),
        "value": max(values) + int(derived * 65) + 100,
        "useTime": clamp(30 - int(power_budget * 2.45), 13, 34),
        "speed": round(6.75 + min(7.25, power_budget * 1.15), 2),
        "pierce": 1 + int(power_budget >= 1.65) + int(power_budget >= 2.75) + int(power_budget >= 4.1) + int(power_budget >= 5.3),
        "mana": clamp(4 + int(power_budget * 1.25), 0, 18),
    }

def stage_profile_for(a: dict[str, Any], b: dict[str, Any], tags: set[str]) -> dict[str, Any]:
    # v1.3: kept as compatibility wrapper. The real driver is parent stat profile, not a hard stage table.
    return stat_profile_for(a, b, tags)

def canvas_tier_for(name: str, tags: set[str], kind: str, stage: dict[str, Any]) -> dict[str, Any]:
    name_l = name.lower()
    head_small = any(x in name_l for x in ["shortsword", "dagger", "knife", "needle", "coin", "seed", "potion", "gem", "shard"])
    head_large = any(x in name_l for x in ["zenith", "night", "edge", "great", "grand", "giant", "station", "computer", "workbench", "throne"])
    power = float(stage.get("powerBudget", 1.0))
    if kind == "weapon":
        if head_small and power < 2.0:
            canvas = 32
        elif head_large or power >= 3.25:
            canvas = 64
        elif ("sword" in tags or "blade" in tags or "staff" in tags or "bow" in tags or "gun" in tags or power >= 1.8):
            canvas = 48
        else:
            canvas = 32
    elif kind in {"furniture", "technology", "placeable_station"}:
        canvas = 64 if head_large else 48
    else:
        canvas = 32
    visual_mass = {32: 0, 48: 1, 64: 2}[canvas]
    return {"canvas": canvas, "visualMass": visual_mass}

def size_profile_for(name: str, tags: set[str], kind: str, stage: dict[str, Any] | None = None) -> dict[str, Any]:
    stage = stage or {"powerBudget": 1.0, "name": "early"}
    canvas = canvas_tier_for(name, tags, kind, stage)
    visual_mass = canvas["visualMass"]
    power = float(stage.get("powerBudget", 1.0))
    if kind == "weapon":
        item_scale = 1.0 + 0.12 * visual_mass
        hitbox_scale = 1.0 + 0.10 * visual_mass + min(power, 4.8) * 0.035
        projectile_scale = 1.0 + 0.14 * visual_mass
    else:
        item_scale = 1.0 + 0.06 * visual_mass
        hitbox_scale = 1.0
        projectile_scale = 1.0
    return {
        "oversized": visual_mass,
        "itemScale": round(item_scale, 3),
        "inventoryScale": round(1.0 + 0.08 * visual_mass, 3),
        "worldScale": round(1.0 + 0.10 * visual_mass, 3),
        "preferredCanvasSize": canvas["canvas"],
        "projectileScale": round(max(projectile_scale, 1.08) if kind == "weapon" else projectile_scale, 3),
        # Visual/readability floor: even low-tier generated weapon projectiles should not
        # look smaller than vanilla starter attacks. Keep gameplay conservative, but stop
        # emitting 12px specks from readable weapon sprites.
        "projectileWidth": 16 + 4 * visual_mass if kind == "weapon" else 14,
        "projectileHeight": 16 + 4 * visual_mass if kind == "weapon" else 14,
        "hitboxScale": round(hitbox_scale, 3),
        "explosionRadius": 0,
        "holdoutOffsetX": -3 * visual_mass if kind == "weapon" else 0,
        "holdoutOffsetY": -2 * visual_mass if kind == "weapon" else 0,
    }

def balanced_damage(max_parent_damage: int, tags: set[str], stage: dict[str, Any]) -> int:
    if "weapon" not in tags and max_parent_damage <= 0:
        return 0
    raw = max(1, int(stage.get("derivedDamage") or max_parent_damage + 4))
    return clamp_vanilla_like_weapon_damage(raw, max_parent_damage, stage)

def _normalize_authored_enum_value(value: Any, allowed: dict[str, int] | set[str], field: str = "") -> str:
    v = str(value or "").lower().strip().replace("-", "_").replace(" ", "_")
    if allowed is MOVEMENT_CODE or field == "movement":
        v = MOVEMENT_ALIASES.get(v, v)
    elif allowed is EFFECT_CODE or field == "effect":
        v = EFFECT_ALIASES.get(v, v)
    elif allowed is ONHIT_CODE or field == "onHit":
        v = ONHIT_ALIASES.get(v, v)
    elif allowed is DELIVERY_VALUES or field == "delivery":
        v = DELIVERY_ALIASES.get(v, v)
    elif allowed is RUNTIME_FAMILY_VALUES or field == "runtimeFamily":
        v = "returning" if v in {"boomerang", "chakram", "returning_throw", "glaive_throw"} else DELIVERY_ALIASES.get(v, v)
    return v

def safe_enum(value: Any, allowed: dict[str, int], fallback: str) -> tuple[str, int]:
    v = _normalize_authored_enum_value(value, allowed)
    if v in allowed:
        return v, allowed[v]
    return fallback, allowed[fallback]

def proposed_attack_genome(data: dict[str, Any]) -> dict[str, Any]:
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    genome = attack.get("genome") if isinstance(attack.get("genome"), dict) else {}
    # runtimePlan compiler is authoritative. Flat attack fields fill only numeric/presentation gaps;
    # deprecated prose/script fields are intentionally not copied into executable genome.
    merged = dict(genome)
    for k in ["attackPattern", "pattern", "movement", "effect", "onHit", "shotCount", "spreadRadians", "pierce", "aoeRadiusTiles", "homingStrength", "lifetimeTicks", "extraUpdates", "rangeTiles", "reliability", "selfLockTicks", "missPunish", "useTimeTicks", "runtimeFamily", "delivery", "weaponFamily", "weaponSubfamily", "attackPatternTags", "projectileFamily", "ammoKind", "projectileShape", "projectileMotion", "projectileTrail", "projectileImpact", "soundUseSearchQuery", "soundImpactSearchQuery"]:
        if k in attack and k not in merged:
            merged[k] = attack[k]
    if LLM_RUNTIME_AUTHORING:
        merged.update(runtime_plan_to_attack_genome_patch(data))
    return merged

def combat_genome_required_for(data: dict[str, Any]) -> bool:
    """Return True when an LLM result needs an executable combat genome.

    This is not a creativity check. It only decides whether a result is combat-capable
    and therefore must provide concrete mechanics. Summon counts as combat here.
    """
    if not is_llm_planner(data):
        return False
    category = normalize_category(data.get("category", "generic"))
    gameplay = data.get("gameplay") if isinstance(data.get("gameplay"), dict) else {}
    kind = normalize_category(gameplay.get("kind", category))
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    return category in COMBAT_CATEGORIES or kind in COMBAT_CATEGORIES or bool(attack.get("enabled"))

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
    enum_checks: list[tuple[str, dict[str, int] | set[str]]] = [
        ("delivery", DELIVERY_VALUES),
        ("movement", MOVEMENT_CODE),
        ("effect", EFFECT_CODE),
        ("onHit", ONHIT_CODE),
    ]
    for field, allowed in enum_checks:
        if field not in proposed or proposed.get(field) in (None, ""):
            continue
        value = _normalize_authored_enum_value(proposed.get(field), allowed, field)
        if isinstance(allowed, dict):
            ok = value in allowed
        else:
            ok = value in allowed
        if not ok:
            defects.append(f"unsupported attack.genome.{field}={proposed.get(field)!r}")

    # Required numeric fields must be parseable numbers. Out-of-range numbers are later
    # hard-clamped for engine safety; non-numeric values require LLM repair.
    for field in [
        "useTimeTicks", "shotCount", "pierce", "aoeRadiusTiles", "lifetimeTicks",
        "rangeTiles", "reliability", "selfLockTicks", "missPunish",
    ]:
        if field not in proposed or proposed.get(field) in (None, ""):
            continue
        try:
            x = float(proposed.get(field))
            if not math.isfinite(x):
                raise ValueError("not finite")
        except Exception:
            defects.append(f"non-numeric attack.genome.{field}={proposed.get(field)!r}")

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

    known = set(LLM_REQUIRED_GENOME_FIELDS) | set(LLM_OPTIONAL_GENOME_DEFAULTS) | {"spreadRadians", "homingStrength", "extraUpdates"}
    for key, value in src.items():
        if key in known:
            genome[key] = value
    attack["enabled"] = True

def try_llm_genome_repair(data: dict[str, Any], a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], key: str, defects: list[str], attempt: int) -> dict[str, Any] | None:
    """Ask the same LLM to fill only missing/malformed combat genome fields.

    This is not a deterministic fallback and not a second critic model. It is the same
    planner being asked to choose concrete mechanics it omitted. If it fails, gameplay
    craft refunds instead of code inventing the missing knobs.
    """
    try:
        model_name = resolve_llm_model()
        existing = proposed_attack_genome(data)
        user = {
            "task": "Repair only missing/malformed attack.genome fields. Return JSON only.",
            "important": [
                "Keep name, tooltip, category, parents, and visual concept.",
                "Pick concrete mechanics now; code will not invent them.",
                "Use weapon-family fields and executable numbers, not prose tags.",
                "Strong ideas need costs: slower useTime, selfLock, missPunish, low reliability, no AoE, or low shotCount.",
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
            "parents": [
                llm_parent_card(a, ca),
                llm_parent_card(b, cb),
            ],
            "allowed": {
                "delivery": ["swing", "thrust", "spear", "stab", "rapier", "shortsword", "shoot", "bow", "gun", "launcher", "cast", "staff", "wand", "book", "throw", "boomerang", "summon", "minion", "sentry"],
                "movement": "straight|gravity_arc|drift|orbit|boomerang|bounce|sine_homing|phase|accelerate|spiral|returning_glaive|expanding_wave|flail_tether|yoyo_hover|whip_lash",
                "effect": "none|dust|electric|slime|star|flame|frost|leaf|shadow|poison|blood|honey|sand|lunar|heal|holy|smoke",
                "onHit": "none|burst|split|chain|burn|frostburn|poison|shadowflame|starburst|starfall|aura_pulse|spore_cloud|mini_missiles|vortex_spawn|blackhole|radial_beams|lightning_arc|heal",
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
        system = (
            "Repair incomplete combat genomes for this Terraria-like item generator. "
            "Return JSON only. Fill missing/malformed fields with concrete values. "
            "You are the same planner, not a validator or fallback."
        )
        req = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            "temperature": 0.15,
            "max_tokens": 900,
            "response_format": llm_json_response_format("infini_genome_repair"),
        }
        raw = llm_chat_json(req, timeout=16)
        content = raw["choices"][0]["message"]["content"]
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

def is_llm_planner(data: dict[str, Any]) -> bool:
    debug = data.get("debug") if isinstance(data.get("debug"), dict) else {}
    planner = str(debug.get("planner") or "").lower()
    return planner == "llm" or planner.startswith("llm_") or "llm" in planner

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

def _require_authored_enum(proposed: dict[str, Any], field: str, allowed: dict[str, int] | set[str]) -> tuple[str, int | None]:
    raw = proposed.get(field)
    v = _normalize_authored_enum_value(raw, allowed, field)
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
    delivery, _ = _require_authored_enum(proposed, "delivery", DELIVERY_VALUES)
    movement, mcode = _require_authored_enum(proposed, "movement", MOVEMENT_CODE)
    effect, ecode = _require_authored_enum(proposed, "effect", EFFECT_CODE)
    onhit, hcode = _require_authored_enum(proposed, "onHit", ONHIT_CODE)

    # Required numeric fields: authored by the LLM, hard-clamped only for engine sanity.
    runtime_family = _normalize_authored_enum_value(proposed.get("runtimeFamily"), RUNTIME_FAMILY_VALUES, "runtimeFamily")
    if runtime_family not in RUNTIME_FAMILY_VALUES or runtime_family == "none":
        # Legacy combat-genome compatibility only: accept exact delivery family as light repair.
        runtime_family = "thrust" if delivery in {"thrust", "spear"} else delivery if delivery in RUNTIME_FAMILY_VALUES else "none"
        if runtime_family == "none":
            raise PlannerUnavailable("LLM planner did not author attack.genome.runtimeFamily and delivery was not an exact runtime family; craft failed and ingredients must be refunded")
    g: dict[str, Any] = {
        "runtimeFamily": runtime_family,
        "delivery": delivery,
        "movement": movement, "movementCode": int(mcode),
        "effect": effect, "effectCode": int(ecode),
        "onHit": onhit, "onHitCode": int(hcode),
    }
    for field in [
        "useTimeTicks", "shotCount", "pierce", "aoeRadiusTiles", "lifetimeTicks",
        "rangeTiles", "reliability", "selfLockTicks", "missPunish",
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

    # Preserve only authored presentation strings. Prose/script-like behavior fields are not executable.
    for field in ["projectileShape", "projectileMotion", "projectileTrail", "projectileImpact", "weaponFamily", "weaponSubfamily", "projectileFamily", "ammoKind", "runtimeFamily", "projectileSizePolicy", "soundUseSearchQuery", "soundImpactSearchQuery"]:
        if field in proposed and proposed.get(field) not in (None, ""):
            g[field] = str(proposed.get(field))[:260 if field not in {"soundUseSearchQuery", "soundImpactSearchQuery"} else 160]
    if isinstance(proposed.get("attackPatternTags"), list):
        g["attackPatternTags"] = [str(x)[:40] for x in proposed.get("attackPatternTags")[:12] if x not in (None, "")]

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
    if is_llm_planner(data):
        return llm_authored_weapon_genome(data, a, b, stage)

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
    proposed_delivery = _normalize_authored_enum_value(proposed.get("delivery"), DELIVERY_VALUES, "delivery")
    if proposed_delivery in DELIVERY_VALUES and proposed_delivery != "none":
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
    movement, mcode = safe_enum(proposed.get("movement"), MOVEMENT_CODE, movement)
    effect, ecode = safe_enum(proposed.get("effect"), EFFECT_CODE, effect)
    onhit, hcode = safe_enum(proposed.get("onHit"), ONHIT_CODE, onhit)

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
    reliability = clamp_float(proposed.get("reliability"), 0.45, 1.25, 0.95 if delivery in {"shoot", "cast"} else 0.82)
    self_lock = clamp_float(proposed.get("selfLockTicks"), 0, 120, max(0.0, base_use - 40.0) * 0.35)
    miss_punish = clamp_float(proposed.get("missPunish"), 0.0, 1.0, 0.55 if base_use >= 70 else 0.15)

    genome = {
        "delivery": delivery,
        "movement": movement, "movementCode": mcode,
        "effect": effect, "effectCode": ecode,
        "onHit": onhit, "onHitCode": hcode,
        "shotCount": shot_count, "spreadRadians": round(spread, 3),
        "pierce": pierce, "aoeRadiusTiles": round(aoe_tiles, 3), "homingStrength": round(homing, 3),
        "lifetimeTicks": lifetime, "extraUpdates": extra_updates, "rangeTiles": round(range_tiles, 2),
        "reliability": round(reliability, 3), "selfLockTicks": round(self_lock, 2), "missPunish": round(miss_punish, 3),
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
    # Convert current derived damage into a rough DPS envelope, then let cadence/cost buy burst.
    base_dps = max(4.0, base_damage * 60.0 / max(10.0, float(stage.get("useTime", 24))))
    if use_time >= 60:
        # Slow weapons may hit hard, but not linearly forever.
        burst_bonus = 1.0 + min(0.45, (use_time - 60) / 220.0)
    else:
        burst_bonus = 1.0
    hit_damage = int(max(1.0, base_dps * use_time / 60.0 * burst_bonus / cost))

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
        use_time=use_time,
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


def _equipment_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _equipment_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


_ACCESSORY_COST_WEIGHTS: dict[str, float] = {
    "genericDamage": 42.0,
    "meleeDamage": 42.0,
    "rangedDamage": 42.0,
    "magicDamage": 42.0,
    "summonDamage": 42.0,
    "genericCrit": 0.75,
    "attackSpeed": 38.0,
    "knockback": 8.0,
    "movementSpeed": 18.0,
    "maxRunSpeed": 14.0,
    "jumpSpeed": 16.0,
    "endurance": 115.0,
    "manaCostReduction": 62.0,
    "ammoSaveChance": 62.0,
    "armorPenetration": 1.05,
    "aggro": 0.12,
    "defense": 0.95,
    "maxLife": 0.08,
    "maxMana": 0.055,
    "lifeRegen": 1.6,
    "manaRegen": 1.35,
    "minionSlots": 12.0,
    "sentrySlots": 12.0,
    "lightStrength": 2.0,
}

_ARMOR_PIECE_COST_WEIGHTS: dict[str, float] = {
    "defense": 0.92,
    "genericDamage": 38.0,
    "meleeDamage": 38.0,
    "rangedDamage": 38.0,
    "magicDamage": 38.0,
    "summonDamage": 38.0,
    "genericCrit": 0.62,
    "attackSpeed": 34.0,
    "knockback": 7.0,
    "movementSpeed": 14.0,
    "maxRunSpeed": 12.0,
    "jumpSpeed": 12.0,
    "endurance": 110.0,
    "manaCostReduction": 54.0,
    "ammoSaveChance": 54.0,
    "armorPenetration": 0.95,
    "maxLife": 0.075,
    "maxMana": 0.052,
    "lifeRegen": 1.45,
    "manaRegen": 1.2,
    "minionSlots": 11.0,
    "sentrySlots": 11.0,
    "lightStrength": 1.8,
}

_SET_BONUS_COST_WEIGHTS: dict[str, float] = {
    "setBonusGenericDamage": 48.0,
    "setBonusMeleeDamage": 48.0,
    "setBonusRangedDamage": 48.0,
    "setBonusMagicDamage": 48.0,
    "setBonusSummonDamage": 48.0,
    "setBonusGenericCrit": 0.8,
    "setBonusMovementSpeed": 20.0,
    "setBonusLifeRegen": 1.8,
    "setBonusManaRegen": 1.45,
    "setBonusMinionSlots": 13.0,
    "setBonusSentrySlots": 13.0,
    "setBonusEndurance": 125.0,
    "setBonusArmorPenetration": 1.08,
}

_ACCESSORY_BOOLEAN_COSTS: dict[str, float] = {
    "fallDamageImmune": 1.0,
    "waterWalk": 1.15,
    "lavaImmune": 5.5,
}

_ARMOR_BOOLEAN_COSTS: dict[str, float] = {
    "fallDamageImmune": 1.0,
    "waterWalk": 1.0,
    "lavaImmune": 4.75,
}


def _equipment_budget_base(stage: dict[str, Any], *, kind: str, slot: str = "", set_bonus: bool = False) -> float:
    power = max(1.0, min(7.5, _equipment_float(stage.get("powerBudget"), 1.0)))
    rarity = max(0, min(12, _equipment_int(stage.get("rarity"), 0)))
    depths = stage.get("parentGeneratedDepths") if isinstance(stage.get("parentGeneratedDepths"), list) else []
    depth_bonus = min(4.0, max((_equipment_int(x, 0) for x in depths), default=0) * 0.8)
    if kind == "accessory":
        return 18.0 + power * 8.2 + rarity * 1.45 + depth_bonus
    if set_bonus:
        return 16.0 + power * 7.0 + rarity * 1.35 + depth_bonus
    slot_factor = {"head": 0.92, "body": 1.12, "legs": 1.0}.get(slot, 1.0)
    return (20.0 + power * 8.8 + rarity * 1.55 + depth_bonus) * slot_factor


def _equipment_cost(stats: dict[str, Any], weights: dict[str, float], booleans: dict[str, float] | None = None) -> tuple[float, list[str]]:
    cost = 0.0
    active: list[str] = []
    for field, weight in weights.items():
        value = stats.get(field)
        amount = abs(_equipment_float(value, 0.0))
        if amount > 0:
            cost += amount * weight
            active.append(field)
    for field, weight in (booleans or {}).items():
        if bool(stats.get(field)):
            cost += weight
            active.append(field)
    return cost, active


def _scale_equipment_fields(stats: dict[str, Any], fields: list[str], scale: float, reason: str, source: str) -> list[dict[str, Any]]:
    clamps: list[dict[str, Any]] = []
    for field in fields:
        raw = stats.get(field)
        if isinstance(raw, bool) or raw in (None, "", 0, 0.0):
            continue
        if isinstance(raw, int) and not isinstance(raw, bool):
            final: Any = int(round(float(raw) * scale))
            if raw > 0:
                final = max(0, final)
            elif raw < 0:
                final = min(0, final)
        else:
            final = round(float(raw) * scale, 3)
        if final != raw:
            stats[field] = final
            clamps.append(ClampRecord(field=field, raw=raw, final=final, kind="balance", reason=reason, source=source).to_dict())
    return clamps


def apply_accessory_soft_budget(stats: dict[str, Any], stage: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Soft total-stat budget for accessories; no prompt-word routing."""
    acc = dict(stats)
    budget = _equipment_budget_base(stage, kind="accessory")
    raw_cost, active = _equipment_cost(acc, _ACCESSORY_COST_WEIGHTS, _ACCESSORY_BOOLEAN_COSTS)
    reasons: list[str] = []
    if raw_cost > budget:
        reasons.append("total_stat_budget")
    if _equipment_float(acc.get("endurance"), 0.0) > 0.0 and raw_cost > budget * 0.72:
        reasons.append("endurance_pressure")
    if len(active) >= 7 and raw_cost > budget * 0.86:
        reasons.append("all_in_one_accessory")
    scale = 1.0 if raw_cost <= budget or raw_cost <= 0 else max(0.18, min(1.0, budget / raw_cost))
    clamps: list[dict[str, Any]] = []
    if scale < 0.999:
        clamps.extend(_scale_equipment_fields(acc, list(_ACCESSORY_COST_WEIGHTS), scale, "total_stat_budget", "accessory_soft_budget"))
        # High-cost binary immunities are bounded only when the item is trying to do everything.
        if "all_in_one_accessory" in reasons and bool(acc.get("lavaImmune")) and raw_cost > budget * 1.25:
            raw = acc.get("lavaImmune")
            acc["lavaImmune"] = False
            clamps.append(ClampRecord(field="lavaImmune", raw=raw, final=False, kind="balance", reason="all_in_one_accessory", source="accessory_soft_budget").to_dict())
    final_cost, final_active = _equipment_cost(acc, _ACCESSORY_COST_WEIGHTS, _ACCESSORY_BOOLEAN_COSTS)
    report = {
        "schema": "infini.equipment-budget.v1",
        "kind": "accessory",
        "budget": round(budget, 3),
        "rawCost": round(raw_cost, 3),
        "finalCost": round(final_cost, 3),
        "scale": round(scale, 4),
        "activeFields": active[:24],
        "finalActiveFields": final_active[:24],
        "reasons": sorted(set(reasons)),
        "clamps": clamps,
    }
    return acc, report


def apply_armor_soft_budget(stats: dict[str, Any], stage: dict[str, Any], slot: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Soft total-stat budget for armor piece + separate set bonus budget."""
    armor = dict(stats)
    piece_budget = _equipment_budget_base(stage, kind="armor", slot=slot)
    set_budget = _equipment_budget_base(stage, kind="armor", slot=slot, set_bonus=True)
    piece_cost, piece_active = _equipment_cost(armor, _ARMOR_PIECE_COST_WEIGHTS, _ARMOR_BOOLEAN_COSTS)
    set_cost, set_active = _equipment_cost(armor, _SET_BONUS_COST_WEIGHTS, {})
    reasons: list[str] = []
    clamps: list[dict[str, Any]] = []
    piece_scale = 1.0 if piece_cost <= piece_budget or piece_cost <= 0 else max(0.2, min(1.0, piece_budget / piece_cost))
    set_scale = 1.0 if set_cost <= set_budget or set_cost <= 0 else max(0.2, min(1.0, set_budget / set_cost))
    if piece_scale < 0.999:
        reasons.append("total_stat_budget")
        if _equipment_float(armor.get("endurance"), 0.0) > 0.0:
            reasons.append("endurance_pressure")
        clamps.extend(_scale_equipment_fields(armor, list(_ARMOR_PIECE_COST_WEIGHTS), piece_scale, "total_stat_budget", "armor_soft_budget"))
    if set_scale < 0.999:
        reasons.append("set_bonus_pressure")
        clamps.extend(_scale_equipment_fields(armor, list(_SET_BONUS_COST_WEIGHTS), set_scale, "set_bonus_pressure", "armor_soft_budget"))
    final_piece_cost, final_piece_active = _equipment_cost(armor, _ARMOR_PIECE_COST_WEIGHTS, _ARMOR_BOOLEAN_COSTS)
    final_set_cost, final_set_active = _equipment_cost(armor, _SET_BONUS_COST_WEIGHTS, {})
    report = {
        "schema": "infini.equipment-budget.v1",
        "kind": "armor",
        "slot": slot,
        "pieceBudget": round(piece_budget, 3),
        "setBonusBudget": round(set_budget, 3),
        "rawPieceCost": round(piece_cost, 3),
        "rawSetBonusCost": round(set_cost, 3),
        "finalPieceCost": round(final_piece_cost, 3),
        "finalSetBonusCost": round(final_set_cost, 3),
        "pieceScale": round(piece_scale, 4),
        "setBonusScale": round(set_scale, 4),
        "pieceActiveFields": piece_active[:24],
        "setBonusActiveFields": set_active[:24],
        "finalPieceActiveFields": final_piece_active[:24],
        "finalSetBonusActiveFields": final_set_active[:24],
        "reasons": sorted(set(reasons)),
        "clamps": clamps,
    }
    return armor, report

def accessory_stats_for(tags: set[str], stage: dict[str, Any]) -> dict[str, Any]:
    power = float(stage.get("powerBudget", 1.0))
    rarity = int(stage.get("rarity", 0))
    stats: dict[str, Any] = {
        "enabled": True,
        "archetype": "hybrid",
        "defense": 0,
        "maxLife": 0,
        "maxMana": 0,
        "lifeRegen": 0,
        "manaRegen": 0,
        "movementSpeed": 0.0,
        "maxRunSpeed": 0.0,
        "jumpSpeed": 0.0,
        "genericDamage": 0.0,
        "meleeDamage": 0.0,
        "rangedDamage": 0.0,
        "magicDamage": 0.0,
        "summonDamage": 0.0,
        "genericCrit": 0.0,
        "attackSpeed": 0.0,
        "knockback": 0.0,
        "fallDamageImmune": False,
        "lavaImmune": False,
        "waterWalk": False,
        "minionSlots": 0,
    }
    if tags & {"boots", "wings", "mobility", "aglet", "anklet", "balloon", "horseshoe"}:
        stats["archetype"] = "mobility"
        stats["movementSpeed"] = round(0.05 + min(power, 5.0) * 0.028, 3)
        stats["maxRunSpeed"] = round(0.06 + min(power, 5.0) * 0.045, 3)
        if tags & {"wings", "balloon", "horseshoe"}:
            stats["jumpSpeed"] = round(0.05 + min(power, 4.5) * 0.028, 3)
            stats["fallDamageImmune"] = True
    if tags & {"shield", "defense", "guard", "armor"}:
        stats["archetype"] = "defense" if stats["archetype"] == "hybrid" else "hybrid"
        stats["defense"] = max(stats["defense"], max(1, int(2 + power * 1.25 + rarity * 0.55)))
        if power >= 2.0:
            stats["maxLife"] = 20
    if tags & {"emblem", "charm", "ring", "band", "amulet", "weapon", "damage"}:
        stats["archetype"] = "damage" if stats["archetype"] == "hybrid" else "hybrid"
        dmg = round(0.035 + min(power, 5.2) * 0.024, 3)
        if "melee" in tags or "sword" in tags or "glove" in tags:
            stats["meleeDamage"] = dmg
            stats["attackSpeed"] = round(min(0.18, dmg * 0.9), 3)
        elif "ranged" in tags or "gun" in tags or "bow" in tags:
            stats["rangedDamage"] = dmg
            stats["genericCrit"] = round(min(7.0, 1.0 + power * 1.25), 2)
        elif "magic" in tags or "mana" in tags or "staff" in tags or "wand" in tags:
            stats["magicDamage"] = dmg
            stats["maxMana"] = 30 if power >= 1.5 else 15
            stats["manaRegen"] = 3 if power >= 2.0 else 1
        elif "summon" in tags or "minion" in tags:
            stats["summonDamage"] = dmg
            if power >= 2.3:
                stats["minionSlots"] = 1
        else:
            stats["genericDamage"] = round(dmg * 0.9, 3)
    if tags & {"fire", "hellstone"} and power >= 2.3:
        stats["lavaImmune"] = True
    if tags & {"water", "ocean", "flipper"}:
        stats["waterWalk"] = True
    return stats

def armor_slot_from_authoring(data: dict[str, Any], tags: set[str], runtime_stats: dict[str, Any]) -> str:
    raw = str(runtime_stats.get("armorSlot") or (data.get("armor") or {}).get("slot") or "").strip().lower().replace("-", "_").replace(" ", "_")
    if raw in {"head", "helmet", "helm", "hood", "hat", "mask"}:
        return "head"
    if raw in {"legs", "leg", "leggings", "greaves", "pants", "boots"}:
        return "legs"
    if raw in {"body", "chest", "chestplate", "breastplate", "shirt", "robe", "torso"}:
        return "body"
    name = str(data.get("name") or "").lower()
    all_text = name + " " + " ".join(sorted(tags))
    if any(x in all_text for x in ["helmet", "helm", "hood", "hat", "mask"]):
        return "head"
    if any(x in all_text for x in ["leggings", "greaves", "pants", "boots"]):
        return "legs"
    return "body"

def armor_stats_for(tags: set[str], stage: dict[str, Any], slot: str) -> dict[str, Any]:
    power = float(stage.get("powerBudget", 1.0))
    rarity = int(stage.get("rarity", 0))
    slot_factor = {"head": 0.72, "body": 1.0, "legs": 0.82}.get(slot, 1.0)
    defense = max(1, int(round((1.5 + power * 2.25 + rarity * 0.70) * slot_factor)))
    stats: dict[str, Any] = {
        "enabled": True,
        "slot": slot,
        "setKey": "",
        "archetype": "hybrid",
        "defense": defense,
        "maxLife": 0,
        "maxMana": 0,
        "lifeRegen": 0,
        "manaRegen": 0,
        "movementSpeed": 0.0,
        "maxRunSpeed": 0.0,
        "jumpSpeed": 0.0,
        "genericDamage": 0.0,
        "meleeDamage": 0.0,
        "rangedDamage": 0.0,
        "magicDamage": 0.0,
        "summonDamage": 0.0,
        "genericCrit": 0.0,
        "attackSpeed": 0.0,
        "knockback": 0.0,
        "fallDamageImmune": False,
        "lavaImmune": False,
        "waterWalk": False,
        "minionSlots": 0,
        "lightStrength": 0.0,
        "lightColorName": "",
        "setBonusText": "",
        "setBonusGenericDamage": 0.0,
        "setBonusMeleeDamage": 0.0,
        "setBonusRangedDamage": 0.0,
        "setBonusMagicDamage": 0.0,
        "setBonusSummonDamage": 0.0,
        "setBonusGenericCrit": 0.0,
        "setBonusMovementSpeed": 0.0,
        "setBonusLifeRegen": 0,
        "setBonusManaRegen": 0,
        "setBonusMinionSlots": 0,
    }
    dmg = round(0.026 + min(power, 5.2) * 0.017, 3)
    if tags & {"melee", "sword", "blade", "warrior"}:
        stats["archetype"] = "melee"
        if slot == "head": stats["meleeDamage"] = dmg
        if slot == "body": stats["attackSpeed"] = round(min(0.14, dmg * 0.76), 3)
        if slot == "legs": stats["movementSpeed"] = round(min(0.16, dmg * 1.35), 3)
    elif tags & {"ranged", "gun", "bow", "bullet", "arrow"}:
        stats["archetype"] = "ranged"
        if slot == "head": stats["rangedDamage"] = dmg
        if slot == "body": stats["genericCrit"] = round(min(7.0, 1.0 + power * 1.25), 2)
        if slot == "legs": stats["movementSpeed"] = round(min(0.10, dmg), 3)
    elif tags & {"magic", "mana", "staff", "wand", "spell"}:
        stats["archetype"] = "magic"
        if slot == "head": stats["magicDamage"] = dmg
        if slot == "body": stats["maxMana"] = 30 if power >= 1.5 else 15
        if slot == "legs": stats["manaRegen"] = 1 if power < 2.5 else 3
    elif tags & {"summon", "minion", "sentry"}:
        stats["archetype"] = "summon"
        if slot == "head": stats["summonDamage"] = dmg
        if slot == "body" and power >= 2.2: stats["minionSlots"] = 1
        if slot == "legs": stats["movementSpeed"] = round(min(0.10, dmg), 3)
    elif tags & {"boots", "wings", "mobility", "aglet", "anklet"}:
        stats["archetype"] = "mobility"
        stats["movementSpeed"] = round(0.04 + min(power, 5.0) * 0.024, 3)
        if slot == "legs": stats["maxRunSpeed"] = round(0.06 + min(power, 5.0) * 0.036, 3)
    elif tags & {"defense", "shield", "guard", "armor"}:
        stats["archetype"] = "defense"
        if power >= 2.0 and slot == "body": stats["maxLife"] = 20
    if tags & {"fire", "hellstone", "lava"} and power >= 2.3:
        stats["lavaImmune"] = slot == "body"
    if tags & {"water", "ocean", "flipper"}:
        stats["waterWalk"] = slot == "legs"
    if tags & {"light", "star", "holy", "lunar", "glow"}:
        stats["lightStrength"] = round(min(0.85, 0.14 + power * 0.085), 3)
        stats["lightColorName"] = "gold" if "star" in tags or "holy" in tags else "blue"
    return stats

def build_result_item_card(data: dict[str, Any], a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    gp = data.get("gameplay") if isinstance(data.get("gameplay"), dict) else {}
    k = data.get("itemKnowledge") if isinstance(data.get("itemKnowledge"), dict) else {}
    tags = set(str(t).lower() for t in data.get("tags", []) if str(t).strip())
    stage_tier = str(gp.get("stage") or "unknown")
    strongest_tier = str(k.get("strongestTier") or "unknown")
    try:
        parent_power = float(k.get("strongestPowerScore") or 0)
    except Exception:
        parent_power = 0.0
    stage_power = float(TIER_DEFAULT_POWER.get(stage_tier, 0))
    strongest_tier_power = float(TIER_DEFAULT_POWER.get(strongest_tier, 0))
    transfer = gp.get("powerTransfer") if isinstance(gp.get("powerTransfer"), dict) else {}
    # Keep Calamity/custom parent tiers visible, but distinguish full transfer from weak-anchor influence.
    tier = str(transfer.get("resultTier") or (strongest_tier if strongest_tier_power > stage_power * 1.08 else stage_tier))
    try:
        budget_power = float(gp.get("powerBudget") or 1.0) * 55.0
    except Exception:
        budget_power = 55.0
    try:
        damage_power = float(gp.get("damage") or 0) * 1.05
    except Exception:
        damage_power = 0.0
    depth = int((data.get("recipeMeta") or {}).get("generationDepth") or 1)
    transfer_power = float(transfer.get("resultPowerScore") or 0.0)
    transfer_quality = str(transfer.get("quality") or "")
    diluted_transfer = transfer_quality in {"diluted_weak_anchor", "asymmetric"} or str(tier).endswith("_influenced")
    parent_factor = 0.38 if diluted_transfer else 0.82
    budget_factor = 0.82 if diluted_transfer else 1.0
    if depth > 1:
        # powerBudget prices active behavior/complexity; do not let recursive generated parents
        # become stronger tier anchors solely because they have projectiles, split, VFX or uptime.
        budget_factor = min(budget_factor, 0.58)
    power = max(transfer_power, parent_power * parent_factor, budget_power * budget_factor, damage_power) + min(20.0, depth * 2.0)
    if tier not in MODDED_HIGH_TIERS and not str(tier).endswith("_influenced"):
        stage_soft_ceiling = max(
            stage_power * (1.55 if depth <= 1 else 1.35),
            transfer_power * 1.12,
            damage_power * (2.35 if depth <= 1 else 2.05),
            parent_power * parent_factor + 14.0,
        ) + min(14.0, depth * 1.75)
        power = min(power, max(stage_soft_ceiling, damage_power, transfer_power, stage_power))
    if data.get("category") in {"material", "generic"} and damage_power <= 0:
        # Materials/generic results preserve tier influence, but weak-anchor recipes should not become full Calamity-tier gear.
        if transfer_power > 0:
            power = max(power, transfer_power)
        else:
            power = max(power, parent_power * (0.42 if diluted_transfer else 0.72))
    return {
        "name": str(data.get("name") or "Generated Item"),
        "identity": "generated:" + str(data.get("id") or ""),
        "category": normalize_category(str(data.get("category") or gp.get("kind") or "generic")),
        "tier": tier,
        "powerScore": round(max(1.0, power), 2),
        "confidence": 0.74,
        "sourceHint": "generated result card from gameplay + parent knowledge",
        "tags": sorted(tags),
        "generatedDepth": depth,
        "signals": {
            "parentStrongestPower": parent_power,
            "gameplayBudgetPower": round(budget_power, 2),
            "damagePower": round(damage_power, 2),
            "basis": "result_card",
            "powerTransfer": transfer,
        },
    }

def attach_result_knowledge_card(data: dict[str, Any], a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    k = data.setdefault("itemKnowledge", {})
    if not isinstance(k, dict):
        k = {}
        data["itemKnowledge"] = k
    k["resultCard"] = build_result_item_card(data, a, b)
    data.setdefault("debug", {})["resultKnowledgeCard"] = json.dumps(k["resultCard"], ensure_ascii=False)
    return data

def parent_combo_looks_like_bow(a: dict[str, Any], b: dict[str, Any], tags: set[str], data: dict[str, Any]) -> bool:
    text = " ".join(str(x or "") for x in [
        a.get("name"), b.get("name"), a.get("internalName"), b.get("internalName"),
        data.get("name"), data.get("tooltip"), data.get("sourceReading"),
    ]).lower()
    return bool("bow" in tags or "arrow" in tags or "bow" in text or int(item_num(a, "useAmmo", 0)) == 40 or int(item_num(b, "useAmmo", 0)) == 40)

def projectile_family_text(data: dict[str, Any], a: dict[str, Any] | None = None, b: dict[str, Any] | None = None) -> str:
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    concept = data.get("concept") if isinstance(data.get("concept"), dict) else {}
    chunks = [
        data.get("name"), data.get("tooltip"), data.get("parentA"), data.get("parentB"),
        concept.get("fantasy"), concept.get("mergeLogic"), concept.get("weirdTwist"),
        attack.get("weaponFamily"), attack.get("projectileFamily"), attack.get("projectileShape"), attack.get("projectileMotion"), attack.get("projectileTrail"),
        visual.get("imagePrompt"), visual.get("projectileImagePrompt"), visual.get("impactImagePrompt"), visual.get("silhouetteSummary"),
        " ".join(str(x) for x in (data.get("tags") or [])),
    ]
    for item in (a or {}, b or {}):
        chunks.extend([item.get("name"), item.get("internalName"), item.get("fullName"), " ".join(str(x) for x in (item.get("tags") or []))])
        try:
            proj = effective_projectile_profile_of(item)
            if isinstance(proj, dict):
                chunks.extend([proj.get("internalName"), proj.get("fullName"), proj.get("sourceItemInternalName")])
        except Exception:
            pass
    return " ".join(str(x or "") for x in chunks).lower()

def _explicit_visual_family_value(data: dict[str, Any]) -> str:
    raw = str(data.get("projectileVisualFamily") or data.get("projectileVisualFamilyHint") or "").strip().lower().replace("-", "_")
    aliases = {
        "throwing_star": "shuriken_star",
        "disc": "round_disc",
        "disk": "round_disc",
    }
    return aliases.get(raw, raw)

def infer_projectile_visual_family(data: dict[str, Any], a: dict[str, Any] | None = None, b: dict[str, Any] | None = None) -> str:
    """Return a visual-orientation family for generated projectile sprites.

    This is not gameplay routing: executable behavior still comes from runtimePlan.
    The fallback only uses authored runtime family fields and raw projectile facts to keep
    arrows/darts/bolts side-on instead of vertical inventory-icon sprites.
    """
    explicit = _explicit_visual_family_value(data)
    allowed = {"linear_side", "shuriken_star", "round_disc", "spark_mote", "orb_rune", "generic_projectile"}
    if explicit in allowed:
        return explicit
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    weapon_family = str(attack.get("weaponFamily") or attack.get("projectileFamily") or "").lower()
    runtime_family = str(attack.get("runtimeFamily") or attack.get("delivery") or "").lower()
    if weapon_family in {"bow", "crossbow", "repeater", "gun", "shotgun", "blowgun", "dart", "launcher", "harpoon"}:
        return "linear_side"
    if runtime_family in {"shoot", "throw"}:
        for parent in (a or {}, b or {}):
            try:
                fam = parent_projectile_family(effective_projectile_profile_of(parent))
            except Exception:
                fam = ""
            if fam == "linear_side":
                return "linear_side"
    return "generic_projectile"

def parent_projectile_family(proj: dict[str, Any]) -> str:
    """Internal raw-shape bucket for diagnostics only.

    Uses explicit raw projectile booleans/aiStyle buckets where available; does not inspect
    item names for semantic routing.
    """
    if not isinstance(proj, dict):
        return "generic_projectile"
    ai_style = int(_pnum(proj, "aiStyle", -1))
    if _pbool(proj, "arrow") or ai_style == 1:
        return "linear_side"
    if _pbool(proj, "minion"):
        return "minion"
    if _pbool(proj, "sentry"):
        return "sentry"
    if _pbool(proj, "ownerHitCheck") or ai_style in {19, 20, 161, 165, 190}:
        return "held_hitbox"
    return "generic_projectile"

def choose_parent_projectile_size_reference(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Aggregate raw parent projectile size floors without semantic family routing.

    This helper deliberately does not take desired runtime/projectile family. The parent
    projectile data is only a readability floor for width/height/scale; movement,
    delivery, prompt shape and gameplay remain authored by runtimePlan. If both parents
    have projectile facts, preserve the largest raw width, height and scale independently
    so a high-scale small projectile cannot hide a wider/taller sibling.
    """
    candidates: list[dict[str, Any]] = []
    for item, label in ((a, "A"), (b, "B")):
        try:
            proj = effective_projectile_profile_of(item)
        except Exception:
            proj = {}
        if isinstance(proj, dict) and proj:
            c = dict(proj)
            c["__parent"] = label
            c["__family"] = parent_projectile_family(c)
            candidates.append(c)
    if not candidates:
        return {}

    def num(proj: dict[str, Any], key: str, default: float = 0.0) -> float:
        try:
            return float(proj.get(key) if proj.get(key) is not None else default)
        except Exception:
            return default

    width_source = max(candidates, key=lambda p: num(p, "width", 0.0))
    height_source = max(candidates, key=lambda p: num(p, "height", 0.0))
    scale_source = max(candidates, key=lambda p: num(p, "scale", 1.0))
    primary = max(candidates, key=lambda p: (num(p, "width", 0.0) * num(p, "height", 0.0) * max(0.1, num(p, "scale", 1.0))))

    out = dict(primary)
    out["__parent"] = "max" if len(candidates) > 1 else str(primary.get("__parent") or "?")
    out["__family"] = str(primary.get("__family") or parent_projectile_family(primary))
    out["__basis"] = "max raw parent projectile width/height/scale"
    out["__sources"] = {
        "width": str(width_source.get("__parent") or "?"),
        "height": str(height_source.get("__parent") or "?"),
        "scale": str(scale_source.get("__parent") or "?"),
        "primary": str(primary.get("__parent") or "?"),
    }
    out["__candidates"] = [
        {
            "parent": str(p.get("__parent") or "?"),
            "internalName": str(p.get("internalName") or ""),
            "fullName": str(p.get("fullName") or ""),
            "family": str(p.get("__family") or ""),
            "aiStyle": int(num(p, "aiStyle", 0.0)),
            "width": int(num(p, "width", 0.0)),
            "height": int(num(p, "height", 0.0)),
            "scale": round(num(p, "scale", 1.0), 3),
        }
        for p in candidates
    ]
    out["width"] = int(num(width_source, "width", 0.0))
    out["height"] = int(num(height_source, "height", 0.0))
    out["scale"] = round(num(scale_source, "scale", 1.0), 3)
    return out

def apply_parent_projectile_affordance(genome: dict[str, Any], a: dict[str, Any], b: dict[str, Any], tags: set[str], data: dict[str, Any], damage_class: str) -> dict[str, Any]:
    """Expose raw parent projectile size facts without silently authoring size.

    Parent projectile width/height/scale are useful context, but generated projectile
    dimensions belong to the LLM/runtimePlan. By default this helper only writes debug
    provenance. It applies parent size floors only when the authored genome explicitly
    opts in through use_affordance.projectileSizePolicy.
    """
    delivery = str(genome.get("delivery") or "").lower()
    if delivery not in {"shoot", "throw", "cast"}:
        return genome
    parent_proj = choose_parent_projectile_size_reference(a, b)
    if not parent_proj:
        return genome

    size_policy = str(genome.get("projectileSizePolicy") or "authored").strip().lower().replace("-", "_")
    apply_floor = size_policy in {"inherit_parent_floor", "inherit_parent_max"}
    debug_payload = {
        "parent": parent_proj.get("__parent", "?"),
        "internalName": parent_proj.get("internalName", ""),
        "fullName": parent_proj.get("fullName", ""),
        "aiStyle": int(float(parent_proj.get("aiStyle") or 0)),
        "width": int(float(parent_proj.get("width") or 0)),
        "height": int(float(parent_proj.get("height") or 0)),
        "scale": float(parent_proj.get("scale") or 1.0),
        "basis": str(parent_proj.get("__basis") or "raw parent projectile dimensions only"),
        "sources": parent_proj.get("__sources") if isinstance(parent_proj.get("__sources"), dict) else {},
        "candidates": parent_proj.get("__candidates") if isinstance(parent_proj.get("__candidates"), list) else [],
        "projectileSizePolicy": size_policy,
        "appliedToGenome": bool(apply_floor),
    }
    if not apply_floor:
        debug_payload["note"] = "reference only; LLM did not opt into parent projectile size floor"
    try:
        data.setdefault("debug", {})["parentProjectileRef"] = json.dumps(debug_payload, ensure_ascii=False)
    except Exception:
        pass
    if not apply_floor:
        return genome
    try:
        pw = int(float(parent_proj.get("width") or 0))
        ph = int(float(parent_proj.get("height") or 0))
        ps = float(parent_proj.get("scale") or 1.0)
        if pw > 0:
            genome["projectileWidth"] = max(pw, int(float(genome.get("projectileWidth") or 0) or 0))
        if ph > 0:
            genome["projectileHeight"] = max(ph, int(float(genome.get("projectileHeight") or 0) or 0))
        if ps > 0:
            genome["projectileScale"] = round(max(ps, float(genome.get("projectileScale") or 1.0)), 3)
    except Exception:
        pass
    return genome

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

def attach_gameplay_and_attack(data: dict[str, Any], a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any]) -> dict[str, Any]:
    tags = set(data.get("tags", [])) | tags_of(a) | tags_of(b)
    gp = data.setdefault("gameplay", {})
    attack = data.setdefault("attack", {})
    requested_kind = gp.get("kind") or data.get("category") or choose_result_category(tags, a, b, data.get("recipeKey"))
    if LLM_RUNTIME_AUTHORING and runtime_plan(data):
        kind, policy = llm_runtime_result_kind_policy(data, requested_kind, tags, a, b, data.get("recipeKey"))
    elif is_llm_planner(data):
        kind, policy = llm_category_without_router(data, requested_kind, tags, a, b, data.get("recipeKey"))
    else:
        kind, policy = coerce_category_by_policy(requested_kind, tags, a, b, data.get("recipeKey"))
    data["category"] = kind
    gp["kind"] = kind
    data.setdefault("debug", {})["categoryPolicyFinal"] = json.dumps(policy, ensure_ascii=False)
    max_parent_damage = max(int(a.get("damage") or 0), int(b.get("damage") or 0))
    stage = stat_profile_for(a, b, tags)
    stage_name = stage["name"]
    gp["powerTransfer"] = stage.get("powerTransfer", {})

    # v0.4.8: disambiguate three stack modes before category routing disables attack.
    # - weapon: normal generated weapon, stack 1
    # - consumable_weapon: stackable thrown/shot item using GeneratedProjectile
    # - actual_ammo: Terraria ammo skin/stat mode via item.ammo, reduced custom runtime support
    runtime_stats = find_call(data, "set_item_stats") if LLM_RUNTIME_AUTHORING else {}
    runtime_result_kind = str(runtime_stats.get("resultKind") or "").strip().lower().replace("-", "_")
    runtime_ammo_for = str(runtime_stats.get("ammoFor") or gp.get("ammoFor") or "").strip().lower()
    runtime_has_primary = bool(all_calls(data, "shoot_projectile")) if LLM_RUNTIME_AUTHORING else False
    supported_actual_ammo = runtime_ammo_for in {"arrow", "arrows", "bullet", "bullets"}
    if runtime_ammo_for and not supported_actual_ammo:
        gp["unsupportedAmmoFor"] = runtime_ammo_for
        runtime_ammo_for = ""
    runtime_consumable_weapon = bool(LLM_RUNTIME_AUTHORING and runtime_plan(data) and runtime_result_kind in {"ammo", "consumable_weapon", "thrown_stack"} and not runtime_ammo_for and runtime_has_primary)
    runtime_actual_ammo = bool(LLM_RUNTIME_AUTHORING and runtime_result_kind == "ammo" and supported_actual_ammo)
    if runtime_consumable_weapon:
        kind = "weapon"
        data["category"] = "weapon"
        gp["kind"] = "weapon"
        gp["runtimeOutputKind"] = "consumable_weapon"
        gp["consumable"] = True
        try:
            authored_stack = int(float(runtime_stats.get("maxStack") or gp.get("maxStack") or 99))
        except Exception:
            authored_stack = 99
        try:
            authored_yield = int(float(runtime_stats.get("craftYield") or gp.get("craftYield") or min(50, authored_stack)))
        except Exception:
            authored_yield = min(50, authored_stack)
        gp["maxStack"] = max(25, min(999, authored_stack))
        gp["craftYield"] = max(25, min(int(gp["maxStack"]), authored_yield))
    elif runtime_actual_ammo:
        gp["runtimeOutputKind"] = "actual_ammo"
        gp["actualAmmoMode"] = "vanilla_projectile_basic; generated split/onHit runtime is not used by bow/gun ammo yet"

    explicit_non_weapon = kind in NON_WEAPON_CATEGORIES and kind != "generic"
    is_weapon = (kind in COMBAT_CATEGORIES) or (not explicit_non_weapon and ("weapon" in tags or max_parent_damage > 0))
    size = size_profile_for(str(data.get("name", "generated item")), tags, "weapon" if is_weapon else kind, stage)

    if kind == "armor" or data.get("category") == "armor":
        data["category"] = "armor"
        slot = armor_slot_from_authoring(data, tags, runtime_stats)
        armor = armor_stats_for(tags, stage, slot)
        armor.update(data.get("armor") or {})
        if isinstance(runtime_stats, dict):
            if runtime_stats.get("armorSlot") not in (None, ""):
                armor["slot"] = armor_slot_from_authoring(data, tags, runtime_stats)
            if runtime_stats.get("defense") not in (None, ""):
                defense_val = _num(runtime_stats.get("defense"), None)
                if defense_val is not None:
                    armor["defense"] = max(0, min(80, int(round(defense_val))))
        armor["enabled"] = True
        armor["slot"] = armor.get("slot") if armor.get("slot") in {"head", "body", "legs"} else slot
        armor, armor_budget_report = apply_armor_soft_budget(armor, stage, str(armor.get("slot") or slot))
        data.setdefault("debug", {})["armorBudgetReport"] = json.dumps(armor_budget_report, ensure_ascii=False)
        data["armor"] = armor
        gp.update({
            "kind": "armor", "stage": stage_name, "powerBudget": stage["powerBudget"], "damageClass": "generic", "damage": 0,
            "knockback": 0, "useTime": 10, "useAnimation": 10, "useStyle": 0, "autoReuse": False,
            "consumable": False, "manaCost": 0, "rarity": max(int(a.get("rare") or 0), int(b.get("rare") or 0), min(8, int(stage["rarity"]))),
            "value": max(max(int(a.get("value") or 0), int(b.get("value") or 0)) + 100, int(stage["value"] * 0.72)),
            "maxStack": 1, "width": 24, "height": 24, "itemScale": 1.0
        })
        attack.update({"enabled": False})
        data.setdefault("debug", {})["armorGeneration"] = json.dumps({"slot": armor.get("slot"), "setKey": armor.get("setKey", ""), "rule": "Generated armor uses dedicated Head/Body/Legs proxy ModItem types; C# writes Item.defense and UpdateEquip modifiers."}, ensure_ascii=False)
    elif kind == "accessory" or data.get("category") == "accessory":
        data["category"] = "accessory"
        acc = accessory_stats_for(tags, stage)
        acc.update(data.get("accessory") or {})
        acc["enabled"] = True
        acc, accessory_budget_report = apply_accessory_soft_budget(acc, stage)
        data.setdefault("debug", {})["accessoryBudgetReport"] = json.dumps(accessory_budget_report, ensure_ascii=False)
        data["accessory"] = acc
        gp.update({
            "kind": "accessory", "stage": stage_name, "powerBudget": stage["powerBudget"], "damageClass": "generic", "damage": 0,
            "knockback": 0, "useTime": 10, "useAnimation": 10, "useStyle": 0, "autoReuse": False,
            "consumable": False, "manaCost": 0, "rarity": max(int(a.get("rare") or 0), int(b.get("rare") or 0), min(8, int(stage["rarity"]))),
            "value": max(max(int(a.get("value") or 0), int(b.get("value") or 0)) + 100, int(stage["value"] * 0.65)),
            "maxStack": 1, "width": 24, "height": 24, "itemScale": 1.0
        })
        attack.update({"enabled": False})
    elif is_weapon:
        # Terraria summon weapons are still combat items. Internal category stays "weapon"
        # so GeneratedItem keeps attack handling, while gameplay.damageClass carries summon.
        data["category"] = "weapon"
        requested_dc = str(gp.get("damageClass") or "").lower()
        if kind == "summon" or requested_dc == "summon":
            damage_class = "summon"
        elif requested_dc in {"melee", "ranged", "magic", "generic", "modded"}:
            damage_class = requested_dc if requested_dc != "modded" else "generic"
        else:
            # Last-resort raw fallback only: use the highest-damage parent class if present.
            parent_candidates = sorted(
                [a, b],
                key=lambda it: int(item_num(it, "damage", 0)),
                reverse=True,
            )
            parent_dc = str(item_field(parent_candidates[0], "damageClass", "") or "").lower() if parent_candidates else ""
            damage_class = parent_dc if parent_dc in {"melee", "ranged", "magic", "summon", "generic"} else "generic"
        genome = weapon_genome_for(data, a, b, tags, stage, damage_class)
        numbers = weapon_numbers_from_genome(max_parent_damage, tags, stage, genome)
        delivery = str(genome.get("delivery") or "swing")
        pattern, pattern_source = normalize_authored_attack_pattern(genome, attack, damage_class, allow_fallback=not is_llm_planner(data))
        genome["attackPattern"] = pattern
        genome["attackPatternSource"] = pattern_source
        genome = apply_parent_projectile_affordance(genome, a, b, tags, data, damage_class)
        delivery = str(genome.get("delivery") or delivery)
        runtime_family = str(genome.get("runtimeFamily") or "none")
        use_style = 5 if runtime_family in {"thrust", "returning", "shoot", "cast", "throw", "summon", "flail", "yoyo", "whip"} or damage_class in {"magic", "ranged", "summon"} else 1
        gp.update({
            "kind": "weapon",
            "categoryIntent": kind,
            "stage": stage_name,
            "powerBudget": stage["powerBudget"],
            "damageClass": damage_class,
            "damage": authored_weapon_damage(gp, int(numbers["damage"]), max_parent_damage, stage, genome, data.setdefault("debug", {}).setdefault("authorPreservingValidation", {})),
            "knockback": round(authored_num(gp, "knockback", 2.0 + min(stage["powerBudget"], 3.8) * 0.42 + (0.8 if int(numbers["useTime"]) >= 60 else 0.0), 0.0, 12.0), 2),
            "useTime": authored_int(gp, "useTime", int(numbers["useTime"]), 6, 150),
            "useAnimation": authored_int(gp, "useAnimation", int(numbers["useAnimation"]), 6, 150),
            "useStyle": authored_int(gp, "useStyle", use_style, 0, 5),
            "autoReuse": bool(gp.get("autoReuse", stage["derivedPower"] > 12 and int(numbers["useTime"]) <= 45)),
            "manaCost": authored_int(gp, "manaCost", int(stage["mana"]) if damage_class == "magic" else 0, 0, 80),
            "rarity": authored_int(gp, "rarity", max(int(a.get("rare") or 0), int(b.get("rare") or 0), int(stage["rarity"])), -1, 12),
            "value": authored_int(gp, "value", max(max(int(a.get("value") or 0), int(b.get("value") or 0)) + 150, int(stage["value"])), 0, max(100, int(stage["value"] * 3 + 5000))),
            "consumable": bool(gp.get("consumable", False)) if gp.get("runtimeOutputKind") == "consumable_weapon" else False,
            "maxStack": authored_int(gp, "maxStack", 50 if gp.get("runtimeOutputKind") == "consumable_weapon" else 1, 1, 999) if gp.get("runtimeOutputKind") == "consumable_weapon" else 1,
            "craftYield": authored_int(gp, "craftYield", 50 if gp.get("runtimeOutputKind") == "consumable_weapon" else 1, 1, 999),
            "width": authored_int(gp, "width", 28 + size["oversized"] * 4, 10, 96),
            "height": authored_int(gp, "height", 28 + size["oversized"] * 4, 10, 96),
            "itemScale": size["itemScale"],
            "holdoutOffsetX": size["holdoutOffsetX"],
            "holdoutOffsetY": size["holdoutOffsetY"],
        })
        aoe_damage_radius_px = int(float(genome.get("aoeRadiusTiles") or 0) * 16)
        impact_vfx_radius_px = int(float(genome.get("impactVfxRadiusPx") or max(size.get("explosionRadius", 0), aoe_damage_radius_px)))
        contact_forgiveness_px = int(float(genome.get("contactForgivenessPx") or (min(14, max(0, aoe_damage_radius_px // 6)) if str(genome.get("onHit") or "") in {"burst", "starburst", "aura_pulse"} else 0)))
        attack.update({
            "enabled": True,
            "stage": stage_name,
            "powerBudget": stage["powerBudget"],
            "runtimeFamily": runtime_family,
            "delivery": delivery,
            "weaponFamily": str(genome.get("weaponFamily") or ""),
            "weaponSubfamily": str(genome.get("weaponSubfamily") or ""),
            "attackPatternTags": list(genome.get("attackPatternTags") or []) if isinstance(genome.get("attackPatternTags"), list) else [],
            "projectileFamily": str(genome.get("projectileFamily") or ""),
            "ammoKind": str(genome.get("ammoFor") or genome.get("ammoKind") or gp.get("ammoFor") or ""),
            "pattern": pattern,
            "patternSource": str(genome.get("attackPatternSource") or pattern_source),
            "runtimePlanAuthored": bool(LLM_RUNTIME_AUTHORING and runtime_plan(data)),
            "movement": genome["movement"], "movementCode": int(genome["movementCode"]),
            "effect": genome["effect"], "effectCode": int(genome["effectCode"]),
            "onHit": genome["onHit"], "onHitCode": int(genome["onHitCode"]),
            "shotCount": int(genome["shotCount"]),
            "spreadRadians": float(genome["spreadRadians"]),
            "procMode": 1 if genome["movementCode"] == 13 else 2 if genome["movementCode"] == 11 else 3 if genome["movementCode"] == 12 else 0,
            "splitCount": max(0, min(8, int(float(genome.get("splitCount") or 0)))),
            "chainCount": max(0, min(6, int(float(genome.get("chainCount") or (2 if genome["onHit"] in {"chain", "lightning_arc"} else 0))))),
            "bounceCount": 2 if genome["movement"] in {"bounce", "boomerang", "returning_glaive"} else 0,
            "genome": genome,
            "speed": round(float(genome.get("speed") or stage["speed"]), 2),
            "lifetime": int(genome["lifetimeTicks"]),
            # Runtime C# treats this as total projectile hit budget.
            # 0/1 = one hit; -1 = explicitly infinite/persistent. Older builds added +1,
            # which made ordinary authored pierce=1 shots hit twice.
            "pierce": -1 if int(genome["pierce"]) == -1 else max(1, int(genome["pierce"])),
            "scale": 1.0,
            "projectileWidth": int(float(genome.get("projectileWidth") or size["projectileWidth"])),
            "projectileHeight": int(float(genome.get("projectileHeight") or size["projectileHeight"])),
            "projectileScale": float(genome.get("projectileScale") or size["projectileScale"]),
            "hitboxScale": max(size["hitboxScale"], 1.0 + min(1.25, float(genome.get("aoeRadiusTiles") or 0) * 0.10)),
            "explosionRadius": max(size["explosionRadius"], impact_vfx_radius_px),
            "impactVfxRadiusPx": max(0, min(192, impact_vfx_radius_px)),
            "aoeDamageRadiusPx": max(0, min(160, aoe_damage_radius_px)),
            "contactForgivenessPx": max(0, min(32, contact_forgiveness_px)),
            "extraUpdates": int(genome["extraUpdates"]),
            "tileCollide": False if int(genome["movementCode"]) in {8, 11, 12, 13, 15, 16, 17, 18} else True,
            # Local immunity must never default to -1 for generated damaging projectiles;
            # with finite pierce this could re-hit the same NPC while still overlapping.
            "immunityCooldown": max(10, int(10 + float(genome.get("aoeRadiusTiles") or 0) * 2)),
            "trailLength": int(float(genome.get("trailLength") if genome.get("trailLength") is not None else (10 if genome["effect"] in {"star", "shadow", "electric", "flame", "lunar"} else 4))),
            "maxChildProjectiles": int(genome.get("maxChildProjectiles") or 0),
            "maxChildDepth": int(genome.get("maxChildDepth") or 0),
            "dustSpawnDenom": int(genome.get("dustSpawnDenom") if genome.get("dustSpawnDenom") is not None else (0 if bool(LLM_RUNTIME_AUTHORING and runtime_plan(data)) else 3)),
            "burstDustCap": int(genome.get("burstDustCap") if genome.get("burstDustCap") is not None else (0 if bool(LLM_RUNTIME_AUTHORING and runtime_plan(data)) else 20)),
            "debuffHint": str(genome.get("debuffHint") or ""),
            "debuffTime": int(float(genome.get("debuffTime") or 0)),
            "secondaryMaterial": str(genome.get("secondaryMaterial") or ""),
            "secondaryProjectileShape": str(genome.get("secondaryProjectileShape") or ""),
            "engineMetrics": genome.get("engineMetrics") or estimate_engine_metrics(genome, stage),
            "projectileShape": genome.get("projectileShape") or attack.get("projectileShape") or (data.get("projectileGenome") if isinstance(data.get("projectileGenome"), dict) else {}).get("shape", ""),
            "projectileMotion": genome.get("projectileMotion") or attack.get("projectileMotion") or (data.get("projectileGenome") if isinstance(data.get("projectileGenome"), dict) else {}).get("motionFeel", ""),
            "projectileTrail": genome.get("projectileTrail") or attack.get("projectileTrail") or (data.get("projectileGenome") if isinstance(data.get("projectileGenome"), dict) else {}).get("trail", ""),
            "projectileImpact": genome.get("projectileImpact") or attack.get("projectileImpact") or (data.get("projectileGenome") if isinstance(data.get("projectileGenome"), dict) else {}).get("impact", ""),
            "primaryColorName": str(genome.get("primaryColorName") or attack.get("primaryColorName") or ""),
            "runtimeLightStrength": round(float(genome.get("runtimeLightStrength") or 0.0), 3),
            "mobilityMode": str(gp.get("mobilityMode") or genome.get("mobilityMode") or ""),
            "mobilityRangeTiles": int(float(gp.get("mobilityRangeTiles") or genome.get("mobilityRangeTiles") or 0)),
            "mobilityCooldownTicks": int(float(gp.get("mobilityCooldownTicks") or genome.get("mobilityCooldownTicks") or 0)),
            "mobilitySafeTileOnly": bool(gp.get("mobilitySafeTileOnly", genome.get("mobilitySafeTileOnly", True))),
            "soundUseSearchQuery": str(genome.get("soundUseSearchQuery") or ""),
            "soundImpactSearchQuery": str(genome.get("soundImpactSearchQuery") or ""),
        })
        data.setdefault("accessory", {"enabled": False})
    elif kind == "tool":
        data["category"] = "tool"
        tool_power = max(35, min(230, int(28 + stage["derivedPower"] * 4 + max_parent_damage * 1.2)))
        parent_pick_signal = "pickaxe" in tags or "drill" in tags or _parent_tool_power(a, "pickPower", "pick") > 0 or _parent_tool_power(b, "pickPower", "pick") > 0
        parent_axe_signal = "axe" in tags or "chainsaw" in tags or _parent_tool_power(a, "axePower", "axe") > 0 or _parent_tool_power(b, "axePower", "axe") > 0
        parent_hammer_signal = "hammer" in tags or _parent_tool_power(a, "hammerPower", "hammer") > 0 or _parent_tool_power(b, "hammerPower", "hammer") > 0
        inferred_pick = tool_power if parent_pick_signal else 0
        inferred_axe = max(8, tool_power // 5) if parent_axe_signal else 0
        inferred_hammer = max(20, min(120, tool_power)) if parent_hammer_signal else 0
        pick = authored_int(gp, "pickPower", inferred_pick, 0, 230) if parent_pick_signal else 0
        axe = authored_int(gp, "axePower", inferred_axe, 0, 50) if parent_axe_signal else 0
        hammer = authored_int(gp, "hammerPower", inferred_hammer, 0, 120) if parent_hammer_signal else 0
        data.setdefault("debug", {})["toolMerge"] = json.dumps({
            "parentSignals": {"pick": parent_pick_signal, "axe": parent_axe_signal, "hammer": parent_hammer_signal},
            "inferred": {"pickPower": inferred_pick, "axePower": inferred_axe, "hammerPower": inferred_hammer},
            "final": {"pickPower": pick, "axePower": axe, "hammerPower": hammer},
            "rule": "tool stats are executable only from raw parent tool signals; weapons/projectiles do not get tile-edit powers",
        }, ensure_ascii=False)
        damage_class = "melee"
        gp.update({
            "kind": "tool", "stage": stage_name, "powerBudget": stage["powerBudget"], "damageClass": damage_class,
            "damage": max(4, int(max_parent_damage * 0.75 + max(1, int(stage.get("derivedDamage") or max_parent_damage or 4)) * 0.25)),
            "knockback": round(2.0 + min(stage["powerBudget"], 3.0) * 0.35, 2),
            "useTime": authored_int(gp, "useTime", max(12, int(stage["useTime"] + 2)), 10, 150),
            "useAnimation": authored_int(gp, "useAnimation", max(12, int(stage["useTime"] + 2)), 10, 150),
            "useStyle": 1, "autoReuse": True, "manaCost": 0,
            "rarity": max(int(a.get("rare") or 0), int(b.get("rare") or 0), int(stage["rarity"])),
            "value": max(max(int(a.get("value") or 0), int(b.get("value") or 0)) + 100, int(stage["value"] * 0.85)),
            "maxStack": 1, "width": 28, "height": 28, "itemScale": size["itemScale"],
            "pickPower": pick, "axePower": axe, "hammerPower": hammer,
        })
        attack.update({"enabled": False})
        data.setdefault("accessory", {"enabled": False})
    elif kind == "potion" or "potion" in tags or "consumable" in tags:
        data["category"] = "potion"
        potion_profile = _bounded_parent_potion_stats(a, b)
        heal_life = authored_int(gp, "healLife", int(potion_profile.get("healLife") or 0), 0, 200)
        heal_mana = authored_int(gp, "healMana", int(potion_profile.get("healMana") or 0), 0, 200)
        buff_code = authored_int(gp, "buffCode", int(potion_profile.get("buffCode") or 0), 0, 1024)
        buff_time = authored_int(gp, "buffTime", int(potion_profile.get("buffTime") or 0), 0, 60 * 60 * 6)
        if buff_code > 0 and buff_time <= 0:
            buff_time = max(60 * 10, int(potion_profile.get("buffTime") or 60 * 30))
        extra_buffs = gp.get("extraBuffs") if isinstance(gp.get("extraBuffs"), list) else potion_profile.get("extraBuffs", [])
        if not isinstance(extra_buffs, list):
            extra_buffs = []
        if buff_code > 0 and not any(isinstance(b, dict) and int(float(b.get("buffCode") or b.get("buffType") or 0)) == buff_code for b in extra_buffs):
            extra_buffs = [{"buffCode": buff_code, "buffTime": buff_time}] + list(extra_buffs)
        if heal_life <= 0 and heal_mana <= 0 and buff_code <= 0:
            # Generic consumable fallback: mild regeneration, not semantic source inference.
            buff_code = 2
            buff_time = 60 * 20
            potion_profile.setdefault("debug", {})["fallback"] = "generic_regeneration_no_parent_potion_channels"
        data.setdefault("debug", {})["potionMerge"] = json.dumps(potion_profile.get("debug", {}), ensure_ascii=False)
        gp.update({
            "kind": "potion", "stage": stage_name, "powerBudget": stage["powerBudget"], "damageClass": "generic", "damage": 0, "useStyle": 2,
            "consumable": True,
            "maxStack": authored_int(gp, "maxStack", 30, 1, 999),
            "rarity": min(3, max(1, int(stage["rarity"]))), "value": max(80, int(stage["value"] * 0.18)),
            "useTime": authored_int(gp, "useTime", 17, 10, 60), "useAnimation": authored_int(gp, "useAnimation", 17, 10, 60),
            "width": 20, "height": 26, "healLife": heal_life, "healMana": heal_mana, "buffCode": buff_code, "buffTime": buff_time, "extraBuffs": extra_buffs[:4], "itemScale": 1.0
        })
        attack.update({"enabled": False})
        data.setdefault("accessory", {"enabled": False})
    else:
        generic_kind = kind if kind != "generic" else data.get("category", "generic")
        generic_kind = normalize_category(generic_kind)
        data["category"] = generic_kind
        size = size_profile_for(str(data.get("name", "generated item")), tags, generic_kind, stage)
        gp.update({
            "kind": generic_kind, "stage": stage_name, "powerBudget": stage["powerBudget"], "damageClass": "generic", "damage": 0, "useStyle": 1,
            "maxStack": 99 if generic_kind in ["material", "generic", "ammo"] else 1,
            "rarity": max(int(a.get("rare") or 0), int(b.get("rare") or 0), min(4, int(stage["rarity"]))),
            "value": max(int(a.get("value") or 0), int(b.get("value") or 0)) + 50,
            "width": 24, "height": 24, "itemScale": size["itemScale"]
        })
        attack.update({"enabled": False})
        data.setdefault("accessory", {"enabled": False})

    data.setdefault("debug", {})["statProfile"] = json.dumps(stage, ensure_ascii=False)
    data.setdefault("debug", {})["sizeProfile"] = json.dumps(size, ensure_ascii=False)
    data.setdefault("debug", {})["finalCategory"] = data.get("category", "generic")
    attach_balance_report(data, stage)
    return data

def clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(n)))

def movement_for(tags: set[str], stage: dict[str, Any]) -> tuple[str, int]:
    """Non-runtime fallback default only. Runtime authoring should supply movement explicitly."""
    return "straight", MOVEMENT_CODE["straight"]

def effect_for(tags: set[str], stage: dict[str, Any]) -> tuple[str, int]:
    """Non-runtime fallback default only. Runtime authoring should supply effect explicitly."""
    return "dust", EFFECT_CODE["dust"]

def onhit_for(tags: set[str], stage: dict[str, Any]) -> tuple[str, int]:
    """Non-runtime fallback default only. Runtime authoring should supply onHit explicitly."""
    return "none", ONHIT_CODE["none"]

def presentation_from_genome(data: dict[str, Any]) -> dict[str, Any]:
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    genome = attack.get("genome") if isinstance(attack.get("genome"), dict) else attack
    delivery = str(genome.get("delivery") or attack.get("delivery") or "none")
    runtime_family = str(genome.get("runtimeFamily") or attack.get("runtimeFamily") or "none")
    pattern = str(genome.get("attackPattern") or attack.get("pattern") or "").lower()
    movement = str(genome.get("movement") or attack.get("movement") or "straight")
    effect = str(genome.get("effect") or attack.get("effect") or "dust")
    onhit = str(genome.get("onHit") or attack.get("onHit") or "none")
    visual_text = " ".join(str(attack.get(k, "")) for k in ["weaponFamily", "projectileFamily", "projectileShape", "projectileMotion", "projectileTrail", "projectileImpact", "visualMode"]).lower()
    profile = EFFECT_PRESENTATION.get(effect, EFFECT_PRESENTATION.get(effect.replace("fire", "flame"), EFFECT_PRESENTATION["dust"]))
    if pattern == "laser_beam" or movement == "beam" or ("beam" in visual_text and "slash" not in visual_text):
        attack_mode = "beam"
    elif pattern in {"beam_slash", "beam_slash_burst"}:
        attack_mode = "slash_plus_projectile"
    elif pattern == "spear_thrust" or runtime_family == "thrust":
        attack_mode = "spear_thrust"
    elif pattern == "flail_tether" or movement == "flail_tether" or runtime_family == "flail":
        attack_mode = "flail_tether"
    elif pattern == "yoyo_hover" or movement == "yoyo_hover" or runtime_family == "yoyo":
        attack_mode = "yoyo_hover"
    elif pattern == "whip_lash" or movement == "whip_lash" or runtime_family == "whip":
        attack_mode = "whip_lash"
    elif pattern == "slash_holdout" or runtime_family == "swing":
        attack_mode = "slash_plus_projectile" if movement not in {"none", "straight"} or pattern == "slash_holdout" else "slash_arc"
    elif pattern == "falling_projectile" or movement in {"rain", "falling", "fall", "gravity_arc"} and ("fall" in visual_text or "rain" in visual_text or "meteor" in visual_text or "starfall" in visual_text):
        attack_mode = "falling_projectile"
    elif movement in {"orbit", "spiral"} or "orbit" in visual_text:
        attack_mode = "orbiting_projectile"
    else:
        attack_mode = "projectile"

    shape = str(attack.get("projectileShape") or "").strip()
    if not shape:
        if "knife" in visual_text or "blade" in visual_text:
            shape = "knife"
        elif "shuriken" in visual_text or "star" in visual_text:
            shape = "shuriken"
        elif "banner" in visual_text or "flag" in visual_text:
            shape = "banner_knife" if "knife" in visual_text else "banner"
        elif "rune" in visual_text or "glyph" in visual_text:
            shape = "rune"
        elif "lantern" in visual_text:
            shape = "lantern"
        elif "bottle" in visual_text or "potion" in visual_text or "vial" in visual_text:
            shape = "bottle"
        elif "orb" in visual_text or "bomb" in visual_text:
            shape = "orb"
        elif runtime_family == "swing":
            shape = "crescent"
        elif movement in {"orbit", "spiral"}:
            shape = "disc"
        else:
            shape = "bolt"

    trail = str(attack.get("projectileTrail") or "").strip() or profile["trail"]
    impact = str(attack.get("projectileImpact") or "").strip() or profile["impact"]
    color = profile["color"]
    return {
        "schema": "presentationGenome.v1",
        "palette": data.get("visual", {}).get("palette") or [color, "white"],
        "heldSprite": {
            "family": "weapon" if data.get("category") == "weapon" else str(data.get("category") or "generic"),
            "silhouette": "spear" if runtime_family == "thrust" else "flail" if runtime_family == "flail" else "yoyo" if runtime_family == "yoyo" else "whip" if runtime_family == "whip" else "staff" if runtime_family == "cast" else "sword" if runtime_family == "swing" else shape,
            "sizeClass": "large" if float(genome.get("rangeTiles") or 0) >= 80 else "medium",
            "accent": color,
        },
        "attackVisual": {
            "mode": attack_mode,
            "movement": movement,
            "effect": effect,
            "onHit": onhit,
            "arcStyle": "straight_thrust" if runtime_family == "thrust" else "chain_tether" if runtime_family == "flail" else "hover_tether" if runtime_family == "yoyo" else "lash" if runtime_family == "whip" else "wide_crescent" if runtime_family == "swing" else "none",
            "flash": impact,
            "glow": effect not in {"none", "dust", "sand", "smoke"} or "glow" in visual_text or "light" in visual_text,
        },
        "projectileVisual": {
            "enabled": bool(attack.get("enabled")),
            "shape": shape,
            "trailStyle": trail,
            "color": color,
            "frames": 1,
        },
        "impactVisual": {"style": impact, "size": "large" if float(genome.get("aoeRadiusTiles") or 0) >= 3 else "medium" if onhit != "none" else "small", "color": color},
        "trailVisual": {"style": trail, "density": round(min(0.95, 0.2 + float(genome.get("extraUpdates") or 0) * 0.16 + float(genome.get("shotCount") or 1) * 0.04), 2), "color": color},
    }

def sound_profile_from_genome(data: dict[str, Any]) -> dict[str, Any]:
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    genome = attack.get("genome") if isinstance(attack.get("genome"), dict) else attack
    delivery = str(genome.get("delivery") or attack.get("delivery") or "none")
    runtime_family = str(genome.get("runtimeFamily") or attack.get("runtimeFamily") or "none")
    effect = str(genome.get("effect") or attack.get("effect") or "dust")
    onhit = str(genome.get("onHit") or attack.get("onHit") or "none")
    tag_text = " ".join(str(x) for x in (attack.get("attackPatternTags") or []) if x not in (None, "")) if isinstance(attack.get("attackPatternTags"), list) else str(attack.get("attackPatternTags") or "")
    text = " ".join(str(attack.get(k, "")) for k in ["soundUse", "soundImpact", "weaponFamily", "weaponSubfamily", "projectileFamily", "projectileImpact", "impactStyle", "soundUseSearchQuery", "soundImpactSearchQuery"]).lower()
    text = (text + " " + tag_text.lower()).strip()
    effect_profile = EFFECT_PRESENTATION.get(effect, EFFECT_PRESENTATION["dust"])
    subfamily = str(attack.get("weaponSubfamily") or attack.get("weaponFamily") or "").lower()
    use = subfamily if subfamily else ("gun" if runtime_family == "shoot" else "magic" if runtime_family == "cast" else "summon" if runtime_family == "summon" else "swing" if runtime_family in {"swing", "thrust", "flail", "yoyo", "whip"} else "soft")
    if "cloth" in text or "banner" in text: use = "soft"
    if "glass" in text or "chime" in text: use = "crystal"
    if "potion" in text or "heal" in text: use = "potion"
    explosive_effect = effect in {"explosion", "flame", "fire", "smoke"} and float(genome.get("aoeRadiusTiles") or 0) >= 0.75
    impact = "explosion" if explosive_effect else effect_profile["sound"]
    if "cloth" in text or "snap" in text: impact = "soft"
    if "heal" in text or "potion" in text: impact = "potion"
    if "glass" in text or "chime" in text: impact = "crystal"
    return {
        "schema": "soundProfile.v1",
        "use": use,
        "impact": impact,
        "effectLayer": effect_profile["sound"],
        "volume": 0.85,
        "pitch": 0.1 if effect in {"star", "electric", "crystal"} else -0.08 if runtime_family in {"swing", "thrust"} else 0.0,
        "variation": 0.18,
    }

def attach_presentation_and_sound(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data.get("presentationGenome"), dict) or not data.get("presentationGenome"):
        data["presentationGenome"] = presentation_from_genome(data)
    if not isinstance(data.get("soundProfile"), dict) or not data.get("soundProfile"):
        data["soundProfile"] = sound_profile_from_genome(data)
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    if attack.get("enabled"):
        pg = data.get("presentationGenome") or {}
        sp = data.get("soundProfile") or {}
        av = pg.get("attackVisual", {}) if isinstance(pg.get("attackVisual"), dict) else {}
        pv = pg.get("projectileVisual", {}) if isinstance(pg.get("projectileVisual"), dict) else {}
        iv = pg.get("impactVisual", {}) if isinstance(pg.get("impactVisual"), dict) else {}
        tv = pg.get("trailVisual", {}) if isinstance(pg.get("trailVisual"), dict) else {}
        attack["visualMode"] = str(av.get("mode") or "projectile")
        attack["trailStyle"] = str(tv.get("style") or pv.get("trailStyle") or "dust")
        attack["impactStyle"] = str(iv.get("style") or "small_flash")
        palette = pg.get("palette") if isinstance(pg.get("palette"), list) else []
        attack["primaryColorName"] = str(attack.get("primaryColorName") or pv.get("color") or (palette[0] if palette else ("dull" if bool(LLM_RUNTIME_AUTHORING and runtime_plan(data)) else "white")))
        attack["useSoundProfile"] = str(sp.get("use") or "soft")
        attack["impactSoundProfile"] = str(sp.get("impact") or sp.get("effectLayer") or "soft")
        attack["soundPitch"] = round(float(sp.get("pitch") or 0.0), 3)
        attack["soundVolume"] = round(float(sp.get("volume") or 0.85), 3)
        if not attack.get("soundUseSearchQuery"):
            q_bits = [attack.get("weaponSubfamily"), attack.get("weaponFamily"), attack.get("projectileFamily"), attack.get("movement"), attack.get("effect"), attack.get("useSoundProfile")]
            q_bits.extend(attack.get("attackPatternTags") or [] if isinstance(attack.get("attackPatternTags"), list) else [])
            attack["soundUseSearchQuery"] = " ".join(str(x).replace("_", " ") for x in q_bits if x not in (None, "", []))[:160]
        if not attack.get("soundImpactSearchQuery"):
            q_bits = [attack.get("weaponSubfamily"), attack.get("weaponFamily"), attack.get("projectileFamily"), attack.get("movement"), attack.get("effect"), attack.get("onHit"), attack.get("impactSoundProfile")]
            q_bits.extend(attack.get("attackPatternTags") or [] if isinstance(attack.get("attackPatternTags"), list) else [])
            attack["soundImpactSearchQuery"] = " ".join(str(x).replace("_", " ") for x in q_bits if x not in (None, "", []))[:160]
        data["attack"] = attack
    return data

# =============================================================================
# Explicit pipeline dependencies
# =============================================================================
from infini_local.core.balance_report import attach_balance_report
from infini_local.core.result_models import ClampRecord
from infini_local.core.balance_policy import weapon_envelope_for_bucket

from infini_local.pipelines.pipeline_support import (
    ACCESSORY_HINT_TAGS,
    ALLOWED_CATEGORIES,
    ALLOW_DETERMINISTIC_DEV_FALLBACK,
    AMMO_HINT_TAGS,
    APP_VERSION,
    ARMOR_HINT_TAGS,
    ASSET_PUBLIC_BASE_URL,
    BAD_NAME_PATTERNS,
    CACHE_DIR,
    CATEGORY_CREATIVITY,
    CATEGORY_ENFORCE_SAMPLED,
    CATEGORY_SALT,
    COMBAT_CATEGORIES,
    DELIVERY_ALIASES,
    DELIVERY_VALUES,
    EFFECT_ALIASES,
    EFFECT_CODE,
    EFFECT_PRESENTATION,
    HARD_TAGS,
    LAST_COMBINE_FAILURE,
    LAST_COMBINE_FAILURE_FILE,
    LLM_NUMERIC_GENOME_LIMITS,
    LLM_OPTIONAL_GENOME_DEFAULTS,
    LLM_REQUIRED_GENOME_FIELDS,
    LLM_RUNTIME_AUTHORING,
    MODDED_HIGH_TIERS,
    MOVEMENT_ALIASES,
    MOVEMENT_CODE,
    NON_WEAPON_CATEGORIES,
    ONHIT_ALIASES,
    ONHIT_CODE,
    PALETTES,
    PLACEABLE_HINT_TAGS,
    PlannerUnavailable,
    RECIPE_IDENTITY_VERSION,
    RECURSIVE_POWER_GROWTH,
    RUNTIME_FAMILY_VALUES,
    STRONG_ACCESSORY_TAGS,
    TIER_DEFAULT_POWER,
    TIER_RANK,
    TOOL_HINT_TAGS,
    USE_LLM,
    VANILLA_ENDGAME_POWER,
    VISUAL_PIPELINE_PROFILE,
    VISUAL_SYNONYMS,
    WEAPON_UPGRADE_TAGS,
    _json_slim,
    all_calls,
    apply_item_knowledge,
    asset_sync_service,
    attach_generated_parent_summary,
    attach_hybrid_vfx_manifest,
    behavior_cost_multiplier,
    build_item_knowledge,
    cache_get,
    cache_put,
    canonicalize,
    contract_versions_payload,
    clamp_float,
    estimate_engine_metrics,
    failure_state,
    final_normalize,
    find_call,
    generated_data_of,
    generation_depth,
    guess_head,
    infer_attack_pattern_from_runtime,
    infer_item_card,
    is_deliverable_recipe_payload,
    item_bool,
    item_field,
    item_identity,
    item_num,
    log_event,
    lower_name,
    mechanic_signal_power,
    name_of,
    normalize_world_id_from_payload,
    pair_catalyst_pressure,
    parse_first_valid_llm_json,
    rarity_baseline_signal,
    recipe_coherence,
    recipe_key,
    recipe_meta,
    resolve_attack_pattern,
    runtime_plan,
    sanitize_genome_engine,
    sanitize_recipe_for_delivery,
    slug,
    stable_hash,
    tags_of,
    trace_event,
    world_recipe_dir,
    world_storage,
)

from infini_local.pipelines.llm_authoring_pipeline import (
    authored_int,
    authored_num,
    authored_weapon_damage,
    call_llm_vfx_director,
    llm_category_without_router,
    llm_chat_json,
    llm_json_response_format,
    llm_runtime_result_kind_policy,
    normalize_runtime_authoring_fields,
    repair_runtime_plan_if_needed,
    resolve_llm_model,
    runtime_plan_to_attack_genome_patch,
    try_llm_plan,
)

from infini_local.pipelines.parent_context_pipeline import (
    _pbool,
    _pnum,
    effective_projectile_profile_of,
    llm_parent_card,
    parent_weapon_profiles,
    proj_bool,
)

from infini_local.pipelines.visual_generation_pipeline import (
    apply_visual_director,
    attach_visual,
    assert_visual_delivery_ready,
    maybe_generate_visual_assets,
    visual_delivery_report,
)
