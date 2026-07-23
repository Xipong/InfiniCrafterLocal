from __future__ import annotations

import math
import re
from typing import Any

from infini_local.core.env_utils import env_int
from infini_local.core.runtime_authoring.normalize import runtime_plan
from infini_local.pipelines import pipeline_visual_config as visual_config
from infini_local.services.visual_asset_pipeline import (
    compact_prompt_parts,
    compact_zimage_asset_prompt,
    sanitize_image_prompt_background,
    sanitize_visual_palette,
    strip_conflicting_sprite_prompt_bits,
    truncate_prompt_at_boundary,
    zimage_palette_sentence,
    zimage_pe_clean_text,
    zimage_text_policy_sentence,
)


# AGENT MAP: visual prompt contracts and sprite role/canvas shaping.
# This module may alter image prompts/contracts only; gameplay routing stays in
# runtime_authoring/combine layers.

def asset_negative_prompt(role: str = "item") -> str:
    # Z-Image Turbo does not use negative prompts as a reliable CFG channel;
    # technical exclusions are injected into the positive prompt instead.
    if image_backend_uses_semantic_prompt_contract():
        return ""
    base = sprite_background_negative_clause()
    if role == "projectile":
        return base + ", full inventory icon, large weapon held by character"
    if role == "impact":
        return base + ", full weapon, held weapon, blade, hilt, handle, furniture object, inventory item icon, placed object, persistent object"
    if role in {"child", "field"}:
        return base + ", full weapon, inventory item icon"
    if role == "equip_overlay":
        return base + ", inventory icon, full armor sheet, character, mannequin, multiple poses, UI slot frame"
    return base

def chroma_rgb() -> tuple[int, int, int]:
    if visual_config.BG_COLOR in {"green", "lime", "greenscreen"}:
        return (0, 255, 0)
    if visual_config.BG_COLOR in {"blue"}:
        return (0, 0, 255)
    if visual_config.BG_COLOR in {"white"}:
        return (255, 255, 255)
    if visual_config.BG_COLOR in {"black"}:
        return (0, 0, 0)
    return (255, 0, 255)

def chroma_name() -> str:
    r, g, b = chroma_rgb()
    if (r, g, b) == (255, 0, 255):
        return "pure flat magenta background (#ff00ff)"
    if (r, g, b) == (0, 255, 0):
        return "pure flat green background (#00ff00)"
    if (r, g, b) == (255, 255, 255):
        return "pure flat white background (#ffffff)"
    if (r, g, b) == (0, 0, 0):
        return "pure flat black background (#000000)"
    return f"pure flat background color rgb({r},{g},{b})"

def sprite_background_positive_clause() -> str:
    # Prefer a magenta key over requesting alpha/transparency. Local postprocess owns alpha.
    if visual_config.REMOVE_BG and visual_config.BG_REMOVE_MODE in {"chroma", "floodfill"}:
        return f"on a perfectly solid untextured {chroma_name()}, authored foreground components separated from background, no floor, no cast shadow, no gradient"
    if visual_config.REMOVE_BG and visual_config.BG_REMOVE_MODE == "rembg":
        return "on a plain solid magenta key background (#ff00ff), no scene, no floor, no cast shadow"
    return "on a perfectly solid untextured pure flat magenta background (#ff00ff), object fully separated from background, no floor, no cast shadow, no gradient"

def sprite_background_negative_clause() -> str:
    if visual_config.REMOVE_BG and visual_config.BG_REMOVE_MODE in {"chroma", "floodfill"}:
        return "scenery, room, landscape, floor, ground, pedestal, UI frame, text, watermark, character, hands, gradient, textured background, cast shadow, transparent checkerboard, transparency preview, glass background"
    return "scene, background, scenery, room, landscape, character holding item, hands, UI frame, text, watermark, shadow on floor, realistic render, 3d render, blurry, anti-aliased edges"

def image_backend_is_zimage() -> bool:
    """True when the configured image backend should use the Z-Image prompt contract.

    Keep this as backend metadata. It must never route item behavior or weapon
    family. ``auto`` detects Z-Image/Z-Image-Turbo sd.cpp configs; ``1`` forces
    the PE-style positive prompt contract for sd.cpp; ``0`` disables it.
    """
    if (visual_config.IMAGE_BACKEND or "").lower() != "sdcpp":
        return False
    mode = visual_config.ZIMAGE_PROMPT_CONTRACT
    if mode in {"0", "false", "off", "no", "disabled", "disable"}:
        return False
    if mode in {"1", "true", "on", "yes", "force", "forced"}:
        return True
    hay = " ".join([visual_config.SDCPP_MODEL, visual_config.SDCPP_SERVER_COMMAND_TEMPLATE, visual_config.SDCPP_SERVER_EXTRA_ARGS]).lower().replace("_", "-")
    return "z-image" in hay or "zimage" in hay

def image_backend_uses_semantic_prompt_contract() -> bool:
    """Use concise subject-first prompts for modern Qwen-text-encoder flow models.

    Z-Image and FLUX.2 Klein both respond better to objective natural-language
    descriptions than to the legacy comma-tag recipe.  This is image-backend metadata
    only and never changes gameplay or asset-role routing.
    """
    if image_backend_is_zimage():
        return True
    if (visual_config.IMAGE_BACKEND or "").lower() != "sdcpp":
        return False
    hay = " ".join([
        visual_config.SDCPP_MODEL,
        visual_config.SDCPP_SERVER_COMMAND_TEMPLATE,
        visual_config.SDCPP_SERVER_EXTRA_ARGS,
    ]).lower().replace("_", "-")
    return any(token in hay for token in ("flux-2", "flux2", "flux.2"))

def zimage_positive_only_enabled() -> bool:
    return bool(image_backend_is_zimage() and visual_config.ZIMAGE_POSITIVE_ONLY)

def zimage_role_description(role: str, canvas: int) -> str:
    """Concrete role sentence for Z-Image Turbo prompts.

    Keep the opening sentence simple and object-focused. Do not inject tiny-size
    readability advice here; the model already renders to a large canvas and the
    postprocess stage handles the final bake.
    """
    r = (role or "item").lower()
    if r == "projectile":
        return "A Terraria-like pixel-art projectile sprite."
    if r == "impact":
        return "A Terraria-like pixel-art hit impact sprite."
    if r == "child":
        return "A Terraria-like pixel-art secondary projectile sprite."
    if r == "field":
        return "A Terraria-like pixel-art field, rune, cloud, or trap-mark sprite."
    if r == "equip_overlay":
        return "A Terraria-like pixel-art single-pose wearable equipment overlay sprite."
    return "A Terraria-like pixel-art item sprite."

def zimage_positive_guard_clause(role: str, data: dict[str, Any] | None = None) -> str:
    """Positive-only technical guard for Z-Image Turbo.

    Keep only the minimal technical instructions that improve sprite extraction:
    a flat chroma background, visible authored components kept within the sprite
    bounds, and a readable physical footprint.
    """
    r = (role or "item").lower()
    base = (
        "Flat #ff00ff magenta chroma-key background. "
        "Show only the described sprite role. "
        "Keep authored visible components inside the sprite bounds with a thin clear edge. "
        "Let the authored physical arrangement span a readable portion of the canvas. "
        "Use crisp hard pixel edges, a limited palette, and a clean silhouette."
    )
    if r == "projectile":
        return base + " Preserve every explicitly authored projectile body, beam, tether, and trail; add no un-authored geometry."
    if r == "impact":
        return base + " Show the authored momentary impact effect only."
    if r == "field":
        return base + " Show the authored field, rune, cloud, or trap-mark texture only."
    if r == "child":
        return base + " Show the authored child-projectile body only."
    if r == "equip_overlay":
        return base + " Show one centered wearable overlay for the player draw layer, not an inventory icon or armor sheet."
    return base + " Show the authored item inventory sprite only."

def _is_generated_usable_gear(data: dict[str, Any]) -> bool:
    """True for generated outputs that are used/held/equipped, not placed as scenes.

    This is visual prompt hygiene only.  It must not route gameplay families or
    change resultKind/runtimeFamily.  The intent is to keep an item icon for a
    usable object from becoming a full tile/room/placeable scene when one parent
    is furniture or a placeable material.
    """
    category = str(data.get("category") or "").lower()
    gameplay = data.get("gameplay") if isinstance(data.get("gameplay"), dict) else {}
    runtime_kind = str(gameplay.get("runtimeOutputKind") or gameplay.get("kind") or "").lower()
    rp = runtime_plan(data)
    result_kind = str(rp.get("resultKind") or "").lower() if isinstance(rp, dict) else ""
    hay = " ".join([category, runtime_kind, result_kind])
    return any(x in hay for x in ["weapon", "tool", "accessory", "potion", "ammo", "consumable_weapon"])


def _explicit_result_kind(data: dict[str, Any]) -> str:
    """Read the already-authored output kind for item-icon framing only."""
    if not isinstance(data, dict):
        return ""
    rp = runtime_plan(data)
    gameplay = data.get("gameplay") if isinstance(data.get("gameplay"), dict) else {}
    return str(
        (rp.get("resultKind") if isinstance(rp, dict) else "")
        or gameplay.get("runtimeOutputKind")
        or gameplay.get("kind")
        or data.get("category")
        or ""
    ).strip().lower()


def _item_output_kind_visual_guard(data: dict[str, Any]) -> str:
    """One short framing rule from resultKind; authored text owns morphology."""
    kind = _explicit_result_kind(data)
    gameplay = data.get("gameplay") if isinstance(data.get("gameplay"), dict) else {}
    armor = data.get("armor") if isinstance(data.get("armor"), dict) else {}
    slot = str(armor.get("armorSlot") or gameplay.get("armorSlot") or "").strip().lower()
    if kind == "armor":
        slot_words = {"head": "head-slot", "body": "body-slot", "legs": "leg-slot"}.get(slot, "authored")
        return f"inventory icon of the authored {slot_words} armor item only; no character, mannequin, full armor set, room, or action scene"
    if kind == "accessory":
        return "inventory icon of the authored equippable accessory only; no character wearing it and no full outfit"
    if kind == "potion":
        return "inventory icon of the authored consumable item only; no consuming character or scene"
    if kind == "furniture":
        return "inventory icon of the authored placeable furniture item only; no furnished room, floor plan, environment, character, or placement preview"
    if kind == "material":
        return "inventory icon of the authored crafting material only; no mining scene, landscape, or workshop"
    if kind == "ammo":
        return "inventory icon of the authored ammo item only; no firing weapon, shooter, or battle scene"
    if kind == "tool":
        return "inventory icon of the authored tool item only; no user, mining scene, tree, wall, or harvested environment"
    return ""


def _compact_prompt_append(prompt: str, addition: str, *, limit: int = 1800) -> str:
    p = re.sub(r"\s+", " ", str(prompt or "").strip())
    add = re.sub(r"\s+", " ", str(addition or "").strip())
    if not add:
        return truncate_prompt_at_boundary(p, limit)
    probe = re.sub(r"[^a-z0-9]+", " ", p.lower()).strip()
    add_probe = re.sub(r"[^a-z0-9]+", " ", add.lower()).strip()
    if add_probe and add_probe not in probe:
        p = (p.rstrip(" ,.;") + ", " + add).strip()
    return truncate_prompt_at_boundary(p, limit)

_ITEM_USABLE_GEAR_GUARD = (
    "one usable inventory asset composition; preserve authored part count and intentional gaps; "
    "keep every authored physical part readable inside the canvas; depict the authored final item as a handheld or carriable usable item inventory sprite composition, not a placed tile, room scene, floor layout, "
    "furniture placement preview, pedestal, or environment; preserve authored literal, attached, fused, disassembled, "
    "or separate-but-associated parent components inside the sprite"
)

def _prompt_probe(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()

def _append_item_role_guard_once(prompt: str) -> str:
    """Keep one generic item-role guard without redesigning the authored object."""
    p = _strip_item_role_guard_fragments(prompt)
    probe = _prompt_probe(p)
    if "one usable inventory asset composition" not in probe:
        return _compact_prompt_append(p, _ITEM_USABLE_GEAR_GUARD)
    return truncate_prompt_at_boundary(p, 1800)

def _strip_item_role_guard_fragments(prompt: str) -> str:
    """Remove old/duplicated generated-item role boilerplate before adding one canonical guard."""
    p = str(prompt or "")
    p = re.sub(re.escape(_ITEM_USABLE_GEAR_GUARD), " ", p, flags=re.IGNORECASE)
    p = re.sub(
        r"\bone\s+usable\s+inventory\s+asset\s+composition\s*[;,.]\s*"
        r"preserve\s+authored\s+part\s+count\s+and\s+intentional\s+gaps\s*[;,.]\s*"
        r"keep\s+every\s+authored\s+physical\s+part\s+readable\s+inside\s+the\s+canvas\s*[;,.]?",
        " ",
        p,
        flags=re.IGNORECASE,
    )
    p = re.sub(
        r"\s*depict\s+the\s+authored\s+final\s+item\s+as\s+a\s+handheld\s+or\s+carriable\s+usable\s+item\s+inventory\s+sprite\s+composition,\s*"
        r"not\s+a\s+placed\s+tile,\s*room\s+scene,\s*floor\s+layout,\s*furniture\s+placement\s+preview,\s*pedestal,\s*or\s+environment;?\s*"
        r"preserve\s+authored\s+literal,\s*attached,\s*fused,\s*disassembled,\s*or\s+separate-but-associated\s+parent\s+components\s+inside\s+the\s+sprite",
        " ",
        p,
        flags=re.IGNORECASE,
    )
    stop = r"(?=\s*,?\s*depict one handheld|\s*\.\s*Flat #ff00ff|\s*\.\s*Color scheme|\s*\.\s*without letters|$)"
    full_guard = (
        r"\s*,?\s*(?:depict\s+one\s+(?:connected\s+)?handheld\s+or\s+carriable(?:\s+usable)?\s+item\s+object|depict\s+the\s+authored\s+final\s+item\s+as\s+one\s+(?:handheld\s+or\s+carriable\s+usable\s+item\s+)?inventory\s+sprite\s+composition),\s*"
        r"not\s+(?:a\s+placed\s+tile|a\s+room\s+scene)(?:(?!depict\s+(?:one\s+handheld|the\s+authored\s+final)).){0,760}?"
        r"(?:silhouette\s+cues\s+integrated\s+into\s+the\s+item|same\s+readable\s+item\s+silhouette\s+when\s+authored|parent\s+components\s+inside\s+the\s+sprite)\s*[.;,]?"
    )
    partial_guard = (
        r"\s*,?\s*(?:depict\s+one\s+(?:connected\s+)?handheld\s+or\s+carriable(?:\s+usable)?\s+item\s+object|depict\s+the\s+authored\s+final\s+item\s+as\s+one\s+(?:handheld\s+or\s+carriable\s+usable\s+item\s+)?inventory\s+sprite\s+composition),\s*"
        r"not\s+(?:a\s+placed\s+tile|a\s+room\s+scene)(?:(?!depict\s+(?:one\s+handheld|the\s+authored\s+final)).){0,420}?"
        r"(?:pedestal\s*,?\s*or\s+environment|furniture\s+placement\s+preview\s*,?\s*or\s+environment|environment)\s*[.;,]?"
    )
    p = re.sub(full_guard + stop, " ", p, flags=re.IGNORECASE)
    p = re.sub(partial_guard + stop, " ", p, flags=re.IGNORECASE)
    p = re.sub(r"\s+", " ", p)
    p = re.sub(r"\s*,\s*,+", ", ", p)
    return p.strip(" ,.;")

def _authored_item_silhouette_contract(data: dict[str, Any]) -> str:
    """Return an LLM/data-authored item silhouette contract; no hard-coded weapon taxonomy."""
    if not isinstance(data, dict):
        return ""
    plan = runtime_plan(data)
    intent = plan.get("visualIntent") if isinstance(plan, dict) and isinstance(plan.get("visualIntent"), dict) else {}
    topology = str(intent.get("topology") or "").strip()
    parts = [str(part).strip() for part in (intent.get("parts") or []) if str(part).strip()]
    arrangement = str(intent.get("arrangement") or "").strip()
    if topology and parts and arrangement:
        # These values are an authored physical contract. Keep them literal rather
        # than selecting a preferred fusion, grip count, or family silhouette.
        return compact_visual_words(
            f"Topology: {topology}. Physical parts: {', '.join(parts[:8])}. Arrangement: {arrangement}",
            700,
        )
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    kit = data.get("visualKit") if isinstance(data.get("visualKit"), dict) else {}
    for source in (kit, visual):
        for key in (
            "itemSilhouetteContract",
            "silhouetteContract",
            "shapeContract",
            "itemShapeContract",
            "iconShapeContract",
        ):
            raw = source.get(key) if isinstance(source, dict) else ""
            if str(raw or "").strip():
                cleaned = strip_conflicting_sprite_prompt_bits(str(raw))
                cleaned = zimage_pe_clean_text(cleaned)
                cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.;")
                if cleaned:
                    return compact_visual_words(cleaned, 360)
    return ""

def _prepend_prompt_contracts(prompt: str, clauses: list[str], *, limit: int = 1800) -> str:
    p = re.sub(r"\s+", " ", str(prompt or "").strip())
    for clause in reversed([c for c in clauses if str(c).strip()]):
        add = re.sub(r"\s+", " ", str(clause).strip())
        if _prompt_probe(add) not in _prompt_probe(p):
            p = (add.rstrip(" ,.;") + ", " + p.lstrip(" ,.;")).strip()
    return truncate_prompt_at_boundary(p, limit)

def role_visual_prompt_guard(role: str, prompt: str, data: dict[str, Any]) -> str:
    """Small, role-local visual guard with no gameplay routing.

    The guard never rewrites delivery/runtime/result kind.  It only tells the
    image model what this asset slot is allowed to depict: item = one usable
    object, projectile = moving hit body, impact = short effect.  This keeps
    creative weirdness while preventing common role leakage like full furniture
    scenes in weapon icons or weapon-shaped impact sprites.
    """
    r = (role or "item").lower()
    p = str(prompt or "")
    if r == "item":
        if _is_generated_usable_gear(data):
            p = _append_item_role_guard_once(p)
        p = _prepend_prompt_contracts(
            p,
            [
                _authored_item_silhouette_contract(data),
                _item_output_kind_visual_guard(data),
            ],
        )
        attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
        if bool(attack.get("enabled")):
            p = _compact_prompt_append(
                p,
                "inventory item asset only; do not draw its emitted projectile, child projectile, overhead marker, impact burst, trail, target, enemy, or attack scene beside the item",
            )
        return p[:1800]
    if r == "impact":
        return _compact_prompt_append(
            p,
            "depict only a momentary hit effect: dust, smoke, sparks, splash, shards, fragments, ring, puff, flash, or debris burst; no persistent item icon, no held weapon body, no handle, no blade, no furniture object, no placed object",
        )
    if r == "projectile":
        attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
        visual_candidate = data.get("visual")
        visual: dict[str, Any] = visual_candidate if isinstance(visual_candidate, dict) else {}
        falling = (
            str(attack.get("onHit") or "").lower() == "overhead_barrage"
            or str(attack.get("runtimeFamily") or "").lower() == "overhead_barrage"
        )
        extra = "role contract: projectile body; same weapon shape may be reused when that is the actual hit body, but use attack-frame/projectile-body framing, not inventory-view framing"
        authored_family = str(visual.get("projectileVisualFamily") or "").strip()
        authored_orientation = str(visual.get("projectileOrientation") or "").strip()
        if authored_family:
            extra += "; authored projectile visual family: " + authored_family
        if authored_orientation:
            extra += "; authored projectile orientation: " + authored_orientation
        if falling:
            extra += "; overhead-descending hit body; preserve the authored arrow, shard, meteor, star, spear, or other projectile form; not a decorative background field"
        return _compact_prompt_append(
            p,
            "depict the moving hit object texture only; keep the authored projectile subject intact; not a placed object, not a room scene; " + extra,
        )
    if r == "child":
        return _compact_prompt_append(
            p,
            "role contract: child damaging projectile or mote body only; runtime spawns any authored copies; not a decorative background sparkle field, not an impact burst, not the inventory weapon icon",
        )
    return p[:1800]

def family_prompt_clause(data: dict[str, Any], role: str, canvas: int) -> str:
    """Return only role geometry; authored prompts own physical shape and orientation."""
    return role_contract_prompt_clause(role, canvas)

def sanitize_projectile_family_prompt(data: dict[str, Any], role: str, prompt: str) -> str:
    """Final technical prompt guard for sprite assets.

    Physical form belongs to the authored role prompt. This hook remains a stable
    boundary for callers but intentionally performs no family or prose routing.
    """
    return str(prompt or "")[:1800]

def zimage_subject_sentence(role: str, authored_prompt: str, fantasy: str) -> str:
    """PE-style invariant subject sentence.

    Keep subject/count/action/state/material words in the model-authored prompt.
    Supporting fantasy is useful for item/projectile identity, but impact sprites
    must stay effect-only: adding the full item fantasy there tends to leak the
    weapon/item body into the hit flash.
    """
    r = (role or "item").lower()
    subject = zimage_pe_clean_text(authored_prompt)
    fantasy = "" if r == "impact" else zimage_pe_clean_text(fantasy)
    if subject and fantasy and fantasy.lower() not in subject.lower():
        return f"The main visual subject is {subject}. It visually represents {fantasy}."
    if subject:
        return f"The main visual subject is {subject}."
    if fantasy:
        return f"The main visual subject is {fantasy}."
    if r == "impact":
        return "The main visual subject is one compact hit effect burst."
    return f"The main visual subject is the authored {r} sprite asset."


def role_supporting_fantasy(role: str, data: dict[str, Any], fantasy: str) -> str:
    """Use supporting fantasy only for the item; role prompts own other bodies."""
    return fantasy if (role or "item").lower() == "item" else ""


def zimage_item_identity_sentence(role: str, data: dict[str, Any]) -> str:
    """Name the generated item in the prompt without asking for drawn text.

    The image model was sometimes receiving only a generic object description, so
    different recursive items with related parents collapsed into near-identical
    sprites. This is visual identity context only; text rendering remains banned.
    """
    if (role or "item").lower() != "item" or not isinstance(data, dict):
        return ""
    name = compact_visual_words(data.get("name") or "", 90)
    if not name:
        return ""
    return f"The generated item is named {name}; use the name only as identity context, without drawn letters or labels."

def item_name_prompt_clause(role: str, data: dict[str, Any]) -> str:
    if (role or "item").lower() != "item" or not isinstance(data, dict):
        return ""
    name = compact_visual_words(data.get("name") or "", 90)
    return f"generated item name: {name}; do not draw letters or labels" if name else ""


def _semantic_item_prompt(
    data: dict[str, Any],
    authored_prompt: str,
    shared_style: str,
    palette_words: str,
    *,
    limit: int,
) -> str:
    """Build one model-authored, topology-first item prompt for Qwen flow models.

    The validated Visual Director description and silhouette contract stay authoritative.
    Python adds only backend framing (palette, pixel finish, margin, chroma background),
    never a category-specific silhouette or object-name router.
    """
    visual_raw = data.get("visual")
    visual: dict[str, Any] = visual_raw if isinstance(visual_raw, dict) else {}
    item_prompt = str(visual.get("itemPrompt") or "").strip()
    visual_kit_raw = data.get("visualKit")
    visual_kit: dict[str, Any] = visual_kit_raw if isinstance(visual_kit_raw, dict) else {}
    director_prompt = str(visual_kit.get("itemIconPrompt") or "").strip()
    final_wrapper = str(visual.get("finalItemPrompt") or "").strip()
    authored_input = str(authored_prompt or "").strip()
    if director_prompt:
        appearance = director_prompt
    elif authored_input and authored_input != final_wrapper:
        appearance = authored_input
    else:
        appearance = item_prompt or str(data.get("name") or "authored item")
    appearance = _strip_item_role_guard_fragments(appearance)
    appearance = zimage_pe_clean_text(strip_conflicting_sprite_prompt_bits(appearance)).strip(" ,.;")
    silhouette = _authored_item_silhouette_contract(data).strip(" ,.;")
    if silhouette and appearance.casefold() == silhouette.casefold():
        appearance = ""

    foreground = compact_visual_words(palette_words, 360).strip(" ,.;")
    parts = [
        silhouette,
        appearance,
        shared_style,
        f"Foreground colors and materials use {foreground}" if foreground else "",
        "Crisp Terraria-like hand-drawn pixel art with hard edges, readable clusters, a limited palette, and a clean silhouette",
        "One usable inventory asset composition; preserve authored part count and intentional gaps; keep every authored physical part readable inside the canvas",
        "Flat #ff00ff magenta chroma-key background",
    ]
    return compact_zimage_asset_prompt(parts, "item", limit=limit)


def sprite_contract_for(role: str, target_size: int = 32) -> dict[str, Any]:
    role = (role or "item").lower()
    size = max(16, min(96, int(target_size or 32)))
    table: dict[str, dict[str, Any]] = {
        "item": {
            "targetFill": visual_config.ITEM_ICON_TARGET_FILL,
            "minFill": 0.82,
            "maxFill": 0.98,
            "coreAlphaThreshold": visual_config.SPRITE_ITEM_CORE_ALPHA_THRESHOLD,
            "marginPx": 1 if size <= 32 else 2,
            "cropPadPx": 1,
            "maxEdgeTouch": 0.08,
            "promptFillWords": "the authored item arrangement should span a readable portion of the canvas with a thin clear edge",
            "promptPoseWords": "compose it as an inventory item sprite showing its authored physical arrangement",
        },
        "projectile": {
            "targetFill": visual_config.PROJECTILE_ICON_TARGET_FILL,
            "minFill": 0.68,
            "maxFill": 0.96,
            "coreAlphaThreshold": visual_config.SPRITE_EFFECT_CORE_ALPHA_THRESHOLD,
            "marginPx": 1 if size <= 32 else 2,
            "cropPadPx": 1,
            "maxEdgeTouch": 0.10,
            "promptFillWords": "the authored projectile geometry should span a readable portion of the canvas with a thin clear edge",
            "promptPoseWords": "compose the moving projectile in canonical local +X pose: leading tip or nose faces screen-right, tail or trail faces screen-left; this local texture is later rotated to any world-space travel direction",
        },
        "impact": {
            "targetFill": visual_config.IMPACT_ICON_TARGET_FILL,
            "minFill": 0.52,
            "maxFill": 0.95,
            "coreAlphaThreshold": visual_config.SPRITE_EFFECT_CORE_ALPHA_THRESHOLD,
            "marginPx": 1 if size <= 32 else 2,
            "cropPadPx": 1,
            "maxEdgeTouch": 0.18,
            "promptFillWords": "the authored impact effect should span a readable portion of the canvas with a thin clear edge",
            "promptPoseWords": "compose it as the momentary impact effect, without an item or weapon body",
        },
        "child": {
            "targetFill": visual_config.CHILD_ICON_TARGET_FILL,
            "minFill": 0.48,
            "maxFill": 0.90,
            "coreAlphaThreshold": visual_config.SPRITE_EFFECT_CORE_ALPHA_THRESHOLD,
            "marginPx": 1 if size <= 32 else 2,
            "cropPadPx": 1,
            "maxEdgeTouch": 0.14,
            "promptFillWords": "the authored child body should remain legible within the canvas with a thin clear edge",
            "promptPoseWords": "compose the child damaging body, not an impact or inventory item; if elongated, use canonical local +X with its leading tip screen-right because this local texture is later rotated to any world-space travel direction",
        },
        "field": {
            "targetFill": visual_config.FIELD_ICON_TARGET_FILL,
            "minFill": 0.62,
            "maxFill": 0.98,
            "coreAlphaThreshold": visual_config.SPRITE_EFFECT_CORE_ALPHA_THRESHOLD,
            "marginPx": 1 if size <= 32 else 2,
            "cropPadPx": 1,
            "maxEdgeTouch": 0.14,
            "promptFillWords": "the authored field arrangement should span a readable portion of the canvas with a thin clear edge",
            "promptPoseWords": "compose it as the persistent field, rune, cloud, or trap-mark texture",
        },
        "equip_overlay": {
            "targetFill": visual_config.ITEM_ICON_TARGET_FILL,
            "minFill": 0.48,
            "maxFill": 0.92,
            "coreAlphaThreshold": visual_config.SPRITE_EFFECT_CORE_ALPHA_THRESHOLD,
            "marginPx": 2,
            "cropPadPx": 1,
            "maxEdgeTouch": 0.10,
            "promptFillWords": "the authored wearable overlay should remain centered and readable with a thin clear edge",
            "promptPoseWords": "compose one isolated single-pose equipment overlay for the player draw layer, not an inventory icon or armor sheet",
        },
    }
    spec = dict(table.get(role, table["item"]))
    target_fill = max(0.40, min(0.98, float(spec["targetFill"])))
    margin = max(0, int(spec["marginPx"]))
    spec["role"] = role
    spec["size"] = size
    spec["targetLongAxisPx"] = max(4, min(size - margin * 2, int(round(size * target_fill))))
    spec["minLongAxisPx"] = max(3, int(math.floor(size * float(spec["minFill"]))))
    spec["maxLongAxisPx"] = max(spec["minLongAxisPx"], min(size, int(math.ceil(size * float(spec["maxFill"])))))
    # v0.4.49: effect extent must not be stricter than the accepted core long-axis.
    # The old value (size - margin*2) rejected perfectly usable diagonal/X-shaped
    # icons at 45px on a 48px canvas, causing an unnecessary placeholder fallback.
    spec["maxEffectLongAxisPx"] = max(int(spec.get("maxLongAxisPx") or size), int(spec["targetLongAxisPx"]))
    return spec

def role_contract_prompt_clause(role: str, canvas: int) -> str:
    spec = sprite_contract_for(role, canvas)
    return f"{spec['promptPoseWords']}, {spec['promptFillWords']}"

def role_style_prefix(role: str, canvas: int) -> str:
    role = (role or "item").lower()
    bg = sprite_background_positive_clause()
    contract = role_contract_prompt_clause(role, canvas)
    if role == "item":
        return f"pixel art inventory item icon for a Terraria-like mod, {bg}, {contract}"
    if role == "projectile":
        return f"pixel art flying projectile sprite for a Terraria-like mod, {bg}, {contract}"
    if role == "impact":
        return f"pixel art hit impact flash sprite, {bg}, momentary impact effect only, {contract}"
    if role == "child":
        return f"pixel art secondary projectile sprite, {bg}, child damaging body only, {contract}"
    if role == "field":
        return f"pixel art ground field/trap/rune/cloud sprite, {bg}, flat world effect, {contract}"
    if role == "equip_overlay":
        return f"pixel art single-pose wearable equipment overlay emblem for a Terraria-like player draw layer, {bg}, centered isolated overlay only, no character and no spritesheet, {contract}"
    return f"pixel art sprite asset, {bg}, {contract}"

def normalize_asset_prompt(data: dict[str, Any], role: str, prompt: str, canvas: int) -> str:
    """Make every visual job explicit and role-separated.

    The visual director is allowed to be creative, but image backends need strict
    role framing.  For Z-Image Turbo we deliberately put all technical sprite
    constraints into the positive prompt and avoid relying on negative_prompt/CFG.
    """
    role = (role or "item").lower()
    authored_input = str(prompt or "")
    prompt = sanitize_image_prompt_background(re.sub(r"\s+", " ", str(prompt or "")).strip())
    # Runtime shot/split counts do not rewrite authored visual topology. The role
    # contract already tells the image model that this file is one projectile texture;
    # an explicitly authored bundle or multi-part projectile remains allowed.
    prompt = sanitize_projectile_family_prompt(data, role, prompt)
    visual_raw = data.get("visual")
    kit_raw = data.get("visualKit")
    visual: dict[str, Any] = visual_raw if isinstance(visual_raw, dict) else {}
    kit: dict[str, Any] = kit_raw if isinstance(kit_raw, dict) else {}
    shared_style = compact_visual_words(kit.get("styleGuide") or visual.get("styleGuide") or "", 260)
    palette = sanitize_visual_palette(visual.get("palette") or [], limit=8)
    palette_words = ", ".join(str(x).replace("_", " ") for x in palette[:6] if str(x).strip())
    concept_raw = data.get("concept")
    concept: dict[str, Any] = concept_raw if isinstance(concept_raw, dict) else {}
    fantasy = role_supporting_fantasy(
        role,
        data,
        compact_visual_words(concept.get("fantasy") or data.get("tooltip") or data.get("name"), 180),
    )
    if not prompt:
        if role == "projectile":
            prompt = build_projectile_image_prompt(data)
        elif role == "impact":
            prompt = build_impact_image_prompt(data)
        elif role == "child":
            prompt = build_child_image_prompt(data)
        elif role == "field":
            prompt = build_field_image_prompt(data)
        elif role == "equip_overlay":
            prompt = str(kit.get("equipOverlayPrompt") or "single wearable equipment overlay emblem")
        else:
            prompt = str(visual.get("imagePrompt") or data.get("name") or "generated item")

    semantic_contract = image_backend_uses_semantic_prompt_contract()
    if not (semantic_contract and role == "item"):
        prompt = role_visual_prompt_guard(role, prompt, data)

    if semantic_contract:
        # Modern Qwen-text-encoder flow models: feed one final objective visual
        # description, not a legacy Stable Diffusion comma-tag recipe.
        semantic_limit = env_int("INFINI_ZIMAGE_PROMPT_LIMIT", 1800)
        if role == "item":
            return _semantic_item_prompt(
                data,
                authored_input,
                shared_style,
                palette_words,
                limit=semantic_limit,
            )
        role_clause = family_prompt_clause(data, role, canvas) if role == "projectile" else role_contract_prompt_clause(role, canvas)
        semantic_parts = [
            zimage_role_description(role, canvas),
            zimage_item_identity_sentence(role, data),
            zimage_subject_sentence(role, prompt, fantasy),
            (f"Shared authored art direction: {shared_style}." if shared_style else ""),
            role_clause,
            zimage_palette_sentence(palette_words),
            zimage_text_policy_sentence(data),
            zimage_positive_guard_clause(role, data),
        ]
        return compact_zimage_asset_prompt(semantic_parts, role, limit=semantic_limit)

    parts = [
        role_style_prefix(role, canvas),
        f"asset role: {role}",
        item_name_prompt_clause(role, data),
        f"item fantasy: {fantasy}" if fantasy else "",
        prompt,
        (f"shared authored art direction: {shared_style}" if shared_style else ""),
        f"palette: {palette_words}" if palette_words else "palette: limited high-contrast named colors",
        ("preserve every explicitly authored projectile body, beam, tether, and trail; add no un-authored geometry" if role == "projectile" else ""),
        "crisp hard pixel edges, limited palette, no antialiasing look, no UI frame, no text, no character, no scenery, keep unused area pure magenta key (#ff00ff)",
    ]
    return compact_prompt_parts(parts, limit=2200, separator=", ")

def effective_projectile_canvas(data: dict[str, Any]) -> int:
    """Choose canvas from authored visual preference or explicit physical dimensions."""
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    kit = data.get("visualKit") if isinstance(data.get("visualKit"), dict) else {}
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    base = max(16, min(64, int(visual_config.PROJECTILE_SPRITE_CANVAS or 32)))
    explicit_canvas = kit.get("projectileCanvasSize") or visual.get("projectileCanvasSize")
    if isinstance(explicit_canvas, (int, float)):
        return max(16, min(64, int(explicit_canvas)))
    pw = int(float(attack.get("projectileWidth") or 0) or 0)
    ph = int(float(attack.get("projectileHeight") or 0) or 0)
    major = max(pw, ph)
    if major >= 32:
        return max(base, 64)
    if major >= 16:
        return max(base, 48)
    return base

def compact_visual_words(value: Any, limit: int = 180) -> str:
    text = str(value or "").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:limit]

def build_projectile_image_prompt(data: dict[str, Any]) -> str:
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    pg = data.get("projectileGenome") if isinstance(data.get("projectileGenome"), dict) else {}
    concept = data.get("concept") if isinstance(data.get("concept"), dict) else {}
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    projectile_canvas = effective_projectile_canvas(data)
    shape = attack.get("projectileShape") or pg.get("shape") or (data.get("presentationGenome", {}).get("projectileVisual", {}) if isinstance(data.get("presentationGenome"), dict) else {}).get("shape") or "custom projectile"
    trail = attack.get("projectileTrail") or pg.get("trail") or "readable small trail"
    impact = attack.get("projectileImpact") or pg.get("impact") or "small impact"
    motion = attack.get("projectileMotion") or pg.get("motionFeel") or attack.get("movement") or "distinct motion"
    palette = visual.get("palette") or (data.get("presentationGenome", {}).get("palette") if isinstance(data.get("presentationGenome"), dict) else []) or [attack.get("primaryColorName") or "white"]
    palette_words = ", ".join(str(x).replace("_", " ") for x in palette[:6] if str(x).strip())
    anchors = visual.get("requiredAnchors") or []
    anchor_words = ", ".join(str(x) for x in anchors[:5] if str(x).strip())
    return ", ".join([
        "pixel art projectile sprite for a Terraria-like mod",
        sprite_background_positive_clause(),
        "authored moving projectile geometry only; preserve explicitly authored body, beam, tether, and trail; add no un-authored geometry",
        f"readable projectile silhouette filling the useful area of a {projectile_canvas}x{projectile_canvas} sprite target",
        "limited palette, crisp hard edges",
        family_prompt_clause(data, "projectile", projectile_canvas),
        f"projectile shape: {compact_visual_words(shape, 90)}",
        f"motion feel: {compact_visual_words(motion, 90)}",
        f"trail identity: {compact_visual_words(trail, 90)}",
        f"impact theme: {compact_visual_words(impact, 90)}",
        f"item fantasy: {compact_visual_words(concept.get('fantasy') or data.get('name'), 120)}",
        f"must echo: {anchor_words}" if anchor_words else "must have a unique non-generic silhouette",
        f"palette: {palette_words}" if palette_words else "palette: readable high contrast",
    ])

def build_impact_image_prompt(data: dict[str, Any]) -> str:
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    pg = data.get("projectileGenome") if isinstance(data.get("projectileGenome"), dict) else {}
    impact = attack.get("projectileImpact") or pg.get("impact") or attack.get("impactStyle") or "small magical hit flash"
    expire = pg.get("onExpireVisual") or attack.get("impactStyle") or "short-lived puff"
    color = attack.get("primaryColorName") or "white"
    return ", ".join([
        "pixel art impact flash sprite for a Terraria-like projectile",
        sprite_background_positive_clause(),
        "small effect burst only, no weapon, no character, no scene",
        "readable 16x16 to 32x32 effect silhouette",
        "limited particles, crisp pixels",
        role_contract_prompt_clause("impact", visual_config.IMPACT_SPRITE_CANVAS),
        f"impact: {compact_visual_words(impact, 120)}",
        f"miss or expire residue: {compact_visual_words(expire, 120)}",
        f"main color: {str(color).replace('_',' ')}",
    ])

def build_child_image_prompt(data: dict[str, Any]) -> str:
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    concept = data.get("concept") if isinstance(data.get("concept"), dict) else {}
    child = attack.get("secondaryProjectileShape") or attack.get("secondaryMaterial") or attack.get("projectileFamily") or "one secondary projectile related to the item"
    color = attack.get("primaryColorName") or ", ".join(str(x) for x in (visual.get("palette") or [])[:3]) or "white"
    return ", ".join([
        "pixel art child projectile sprite for a Terraria-like mod",
        sprite_background_positive_clause(),
        "authored child-projectile geometry only; preserve explicitly authored body, beam, tether, and trail; add no un-authored geometry",
        "readable 12x12 to 24x24 silhouette",
        "crisp hard pixels, limited palette",
        role_contract_prompt_clause("child", visual_config.CHILD_SPRITE_CANVAS),
        f"child/echo identity: {compact_visual_words(child, 140)}",
        f"parent item fantasy: {compact_visual_words(concept.get('fantasy') or data.get('name'), 120)}",
        f"main color: {str(color).replace('_',' ')}",
    ])

def build_field_image_prompt(data: dict[str, Any]) -> str:
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    concept = data.get("concept") if isinstance(data.get("concept"), dict) else {}
    field = " ".join(str(attack.get(k) or "") for k in ["impactStyle", "projectileImpact", "visualMode"])
    color = attack.get("primaryColorName") or "white"
    return ", ".join([
        "pixel art ground field/trap/rune/cloud sprite for a Terraria-like mod",
        sprite_background_positive_clause(),
        "flat magical field effect only, no item, no character, no scene",
        "readable 24x24 to 32x32 silhouette, can be rune circle, small cloud, puddle, trap mark, or dust patch",
        "crisp pixels, limited particles",
        role_contract_prompt_clause("field", visual_config.FIELD_SPRITE_CANVAS),
        f"field/trap identity: {compact_visual_words(field, 180)}",
        f"item fantasy: {compact_visual_words(concept.get('fantasy') or data.get('name'), 120)}",
        f"main color: {str(color).replace('_',' ')}",
    ])


__all__ = [
    "asset_negative_prompt",
    "chroma_rgb",
    "chroma_name",
    "sprite_background_positive_clause",
    "sprite_background_negative_clause",
    "image_backend_is_zimage",
    "image_backend_uses_semantic_prompt_contract",
    "zimage_positive_only_enabled",
    "zimage_role_description",
    "zimage_positive_guard_clause",
    "_is_generated_usable_gear",
    "_compact_prompt_append",
    "_prompt_probe",
    "_append_item_role_guard_once",
    "_strip_item_role_guard_fragments",
    "_authored_item_silhouette_contract",
    "_prepend_prompt_contracts",
    "role_visual_prompt_guard",
    "family_prompt_clause",
    "sanitize_projectile_family_prompt",
    "zimage_subject_sentence",
    "zimage_item_identity_sentence",
    "item_name_prompt_clause",
    "sprite_contract_for",
    "role_contract_prompt_clause",
    "role_style_prefix",
    "normalize_asset_prompt",
    "effective_projectile_canvas",
    "compact_visual_words",
    "build_projectile_image_prompt",
    "build_impact_image_prompt",
    "build_child_image_prompt",
    "build_field_image_prompt",
    "_ITEM_USABLE_GEAR_GUARD",
]
