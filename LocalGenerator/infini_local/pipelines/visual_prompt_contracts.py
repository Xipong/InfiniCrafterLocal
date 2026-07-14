from __future__ import annotations

import json
import math
import re
from typing import Any

from infini_local.core.env_utils import env_int
from infini_local.core.runtime_family_policy import (
    ITEM_BODIED_PROJECTILE_RUNTIME_FAMILIES,
    canonical_runtime_family,
)
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
from infini_local.pipelines.projectile_affordance import infer_projectile_visual_family


# AGENT MAP: visual prompt contracts and sprite role/canvas shaping.
# This module may alter image prompts/contracts only; gameplay routing stays in
# runtime_authoring/combine layers.

_TETHER_GUARD_RUNTIME_FAMILIES = frozenset({"returning", "flail", "yoyo", "whip"})
_EMITTED_SPEAR_FORM_RUNTIME_FAMILIES = frozenset({"cast", "shoot", "throw"})
_ITEM_FANTASY_PROJECTILE_FAMILIES = ITEM_BODIED_PROJECTILE_RUNTIME_FAMILIES | frozenset({"flail", "whip"})

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
        return f"on a perfectly solid untextured {chroma_name()}, object fully separated from background, no floor, no cast shadow, no gradient"
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
    return "A Terraria-like pixel-art item sprite."

def zimage_positive_guard_clause(role: str, data: dict[str, Any] | None = None) -> str:
    """Positive-only technical guard for Z-Image Turbo.

    Keep only the minimal technical instructions that improve sprite extraction:
    flat chroma background, one subject, full subject inside the frame, and the
    subject spanning most of the canvas on at least one axis.
    """
    r = (role or "item").lower()
    base = (
        "Flat #ff00ff magenta chroma-key background. "
        "Show only the described sprite subject, fully inside the frame. "
        "Let the subject span most of the canvas along at least one axis. "
        "Use crisp hard pixel edges, a limited palette, and a clean silhouette."
    )
    if r == "projectile":
        if isinstance(data, dict) and tether_sprite_guard_required(data, "projectile"):
            return base + " If rope, cord, chain, or tether detail is present, keep it as a short local attachment on the projectile body."
        return base + " Show one authored projectile texture/composition only; preserve an explicitly authored connected bundle or multi-part body."
    if r == "impact":
        return base + " Show one compact impact burst only."
    if r == "field":
        return base + " Show one authored field texture/composition only; preserve its explicitly authored connected parts."
    if r == "child":
        return base + " Show one authored child-projectile texture/composition only; preserve an explicitly authored connected multi-part body."
    return base + " Show only the item sprite."

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
    """One short inventory-icon rule from explicit resultKind, never prose inference."""
    kind = _explicit_result_kind(data)
    gameplay = data.get("gameplay") if isinstance(data.get("gameplay"), dict) else {}
    armor = data.get("armor") if isinstance(data.get("armor"), dict) else {}
    slot = str(armor.get("armorSlot") or gameplay.get("armorSlot") or "").strip().lower()
    if kind == "armor":
        slot_words = {"head": "head armor or helmet", "body": "body armor or chest piece", "legs": "leg armor or greaves"}.get(slot, "single armor piece")
        return f"inventory icon of one {slot_words} only; no character, mannequin, full armor set, room, or action scene"
    if kind == "accessory":
        return "inventory icon of one compact equippable accessory or charm only; no character wearing it and no full outfit"
    if kind == "potion":
        return "inventory icon of one potion bottle, vial, flask, or compact consumable container only; no drinking character or scene"
    if kind == "furniture":
        return "inventory icon of one placeable furniture object only; no furnished room, floor plan, environment, character, or placement preview"
    if kind == "material":
        return "inventory icon of one representative crafting material object or compact readable stack only; no mining scene, landscape, or workshop"
    if kind == "ammo":
        return "inventory icon of one representative ammo body or compact ammo stack only; no firing weapon, shooter, or battle scene"
    if kind == "tool":
        return "inventory icon of one handheld tool only; no user, mining scene, tree, wall, or harvested environment"
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
    "depict the authored final item as one handheld or carriable usable item inventory sprite composition, not a placed tile, room scene, floor layout, "
    "furniture placement preview, pedestal, or environment; preserve authored literal, attached, fused, disassembled, "
    "or separate-but-associated parent components inside the sprite"
)

def _prompt_probe(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()

def _append_item_role_guard_once(prompt: str) -> str:
    """Keep one generic item-role guard without redesigning the authored object."""
    p = _strip_item_role_guard_fragments(prompt)
    probe = _prompt_probe(p)
    if "authored final item as one handheld or carriable usable item inventory sprite composition" not in probe:
        return _compact_prompt_append(p, _ITEM_USABLE_GEAR_GUARD)
    return truncate_prompt_at_boundary(p, 1800)

def _strip_item_role_guard_fragments(prompt: str) -> str:
    """Remove old/duplicated generated-item role boilerplate before adding one canonical guard."""
    p = str(prompt or "")
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
        falling = (
            str(attack.get("onHit") or "").lower() == "overhead_barrage"
            or str(attack.get("runtimeFamily") or "").lower() == "overhead_barrage"
        )
        extra = "role contract: projectile body; same weapon shape may be reused when that is the actual hit body, but use attack-frame/projectile-body framing, not inventory-view framing"
        if falling:
            extra += "; overhead-descending hit body; preserve the authored arrow, shard, meteor, star, spear, or other projectile form; not a decorative background field"
        return _compact_prompt_append(
            p,
            "depict the moving hit object texture only; keep the authored projectile subject intact; not a placed object, not a room scene; " + extra,
        )
    if r == "child":
        return _compact_prompt_append(
            p,
            "role contract: one child damaging projectile or mote body only; runtime spawns any authored copies; not a decorative background sparkle field, not an impact burst, not the inventory weapon icon",
        )
    return p[:1800]

def _authored_tether_context(data: dict[str, Any]) -> str:
    chunks: list[str] = []
    for key in ("name", "tooltip", "category"):
        chunks.append(str(data.get(key) or ""))
    concept = data.get("concept") if isinstance(data.get("concept"), dict) else {}
    for key in ("fantasy", "mergeLogic", "weirdTwist"):
        chunks.append(str(concept.get(key) or ""))
    rp = runtime_plan(data)
    if isinstance(rp, dict):
        chunks.append(json.dumps(rp, ensure_ascii=False)[:4000])
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    for key in ("runtimeFamily", "delivery", "weaponFamily", "projectileFamily", "movement", "projectileShape", "projectileMotion", "projectileTrail", "projectileImpact"):
        chunks.append(str(attack.get(key) or ""))
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    for key in ("imagePrompt", "projectileImagePrompt", "impactImagePrompt"):
        chunks.append(str(visual.get(key) or ""))
    return " ".join(chunks).lower()

def authored_tether_like(data: dict[str, Any]) -> bool:
    ctx = _authored_tether_context(data)
    words = ("rope", "tether", "cord", "chain", "harpoon", "anchor", "reel", "returning_glaive", "snap back", "snaps back", "retract", "reels back")
    return any(w in ctx for w in words)

def tether_sprite_guard_required(data: dict[str, Any], role: str) -> bool:
    """Return True only when a sprite-body guard is technically needed.

    Rope/chain words alone are not enough: a rope item icon or decorative chain
    should keep its authored silhouette.  The guard is only for small projectile
    body textures whose long tether/cord is represented by gameplay/VFX state.
    """
    r = (role or "").lower()
    if r != "projectile":
        return False
    if not authored_tether_like(data):
        return False
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    runtime_family = canonical_runtime_family(attack.get("runtimeFamily"))
    movement = str(attack.get("movement") or attack.get("pattern") or attack.get("attackPattern") or "").lower()
    pattern = str(attack.get("pattern") or attack.get("attackPattern") or "").lower()
    delivery = str(attack.get("delivery") or "").lower()
    weapon_family = str(attack.get("weaponFamily") or "").lower()
    projectile_family = str(attack.get("projectileFamily") or "").lower()
    family_blob = weapon_family + " " + projectile_family + " " + movement
    explicit_tether_family = any(w in family_blob for w in ["harpoon", "flail", "yoyo", "whip", "anchor", "return"])
    return (
        runtime_family in _TETHER_GUARD_RUNTIME_FAMILIES
        or movement in {"flail_tether", "yoyo_hover", "whip_lash", "returning_glaive", "boomerang"}
        or pattern == "spear_thrust" and delivery == "thrust"
        or runtime_family in {"throw", "shoot"} and explicit_tether_family
        or delivery in {"throw", "returning"} and explicit_tether_family
    )

def _scrub_tether_sprite_body_prompt(prompt: str, role: str) -> str:
    """Remove only full-canvas/off-canvas tether instructions.

    This is deliberately light-touch.  It preserves a visible local rope/chain
    detail when that detail helps the sprite read better, but prevents Z-Image
    from turning a projectile texture into a long line across the whole canvas.
    """
    p = str(prompt or "")
    if (role or "").lower() != "projectile":
        return p
    replacements = [
        (r"\bthin\s+taut\s+rope\s+tether\s+line\s+extending\s+left\b", "short local rope attachment at the base"),
        (r"\bthin\s+(?:taut|taught)\s+rope\s+line\s+back\s+to\s+the\s+player\b", "short local rope attachment at the base"),
        (r"\btrailing\s+a\s+thin\s+(?:taut|taught)\s+rope\s+line\s+back\s+to\s+the\s+player\b", "with a short rope loop at the base"),
        (r"\b(?:rope|chain|cord|tether)\s+line\s+extending\s+(?:left|right|back)\b", "short local tether attachment"),
        (r"\b(?:rope|chain|cord|tether)\s+back\s+to\s+the\s+player\b", "short local tether attachment"),
        (r"\boff[- ]canvas\s+(?:rope|chain|cord|tether)\b", "small coil attached to the body"),
        (r"\bfull[- ]screen\s+(?:rope|chain|cord|tether)\b", "short local rope or chain detail"),
    ]
    for pat, repl in replacements:
        p = re.sub(pat, repl, p, flags=re.IGNORECASE)
    return p

def tether_visual_prompt_guard(role: str, prompt: str, data: dict[str, Any]) -> str:
    """Minimal Z-Image guard for tethered projectile-body sprites.

    It does not route item families and it does not rewrite rope/chain items.
    It only keeps tiny projectile-body PNGs from becoming full-canvas tether
    drawings, which hurts bbox validation and in-game readability.
    """
    p = str(prompt or "")
    if not tether_sprite_guard_required(data, role):
        return p
    p = _scrub_tether_sprite_body_prompt(p, role)
    guard = "visible rope, cord, or chain may appear as a short local attachment, loop, nub, or compact coil attached to the main projectile body; keep the main projectile silhouette readable and keep all tether detail inside the canvas"
    guard_probe = re.sub(r"[^a-z0-9]+", " ", guard.lower()).strip()
    prompt_probe = re.sub(r"[^a-z0-9]+", " ", p.lower()).strip()
    if guard_probe not in prompt_probe:
        p = (p.rstrip(" ,.;") + ", " + guard).strip()
    return p[:1800]

def family_prompt_clause(data: dict[str, Any], role: str, canvas: int) -> str:
    if (role or "").lower() != "projectile":
        return role_contract_prompt_clause(role, canvas)
    family = infer_projectile_visual_family(data)
    spec = sprite_contract_for("projectile", canvas)
    fill = spec.get("promptFillWords", "the projectile body should fill most of the canvas")
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    runtime_family = canonical_runtime_family(attack.get("runtimeFamily"))
    pattern = str(attack.get("pattern") or attack.get("attackPattern") or "").lower()
    projectile_family = str(attack.get("projectileFamily") or "").lower()
    spear_form = any(w in projectile_family for w in ["spear", "lance", "pike", "trident", "glaive", "halberd", "naginata"])
    if runtime_family == "thrust" or pattern == "spear_thrust":
        return ", ".join([
            "held close-range thrust projection texture matching the authored projectile body",
            "aligned for a forward stab or short lunge when the authored body has a clear long axis",
            "one projection texture only; keep unusual authored forms readable rather than forcing a spear or polearm silhouette",
            str(fill),
        ])
    if runtime_family in _EMITTED_SPEAR_FORM_RUNTIME_FAMILIES and spear_form:
        return ", ".join([
            "free-flying spear/lance-shaped projectile body in a flight pose",
            "short readable spearhead or spectral lance aligned along its flight axis",
            "empty magenta canvas around the projectile body",
            "one authored projectile texture; preserve an explicitly authored connected bundle or multi-part body inside that texture",
            str(fill),
        ])
    if runtime_family == "flail" or pattern == "flail_tether":
        return ", ".join([
            "compact flail or mace head projectile body",
            "optional short local chain segment attached to the head",
            "render the authored flail projectile body as one texture; preserve explicitly authored connected heads or parts",
            str(fill),
        ])
    if runtime_family == "yoyo" or pattern == "yoyo_hover":
        return ", ".join([
            "compact circular yoyo body sprite",
            "optional short local string nub attached to the yoyo",
            "render the authored yoyo projectile body as one texture; preserve explicitly authored connected parts",
            str(fill),
        ])
    if runtime_family == "whip" or pattern == "whip_lash":
        return ", ".join([
            "compact whip tip or short lash segment body",
            "render the authored whip projectile accent as one texture; preserve explicitly authored connected parts",
            str(fill),
        ])
    if family == "linear_side":
        return ", ".join([
            "canonical side-view gameplay projectile, long axis horizontal left-to-right",
            "tip/nose points right in the texture because the game rotates projectile sprites at runtime",
            "not a vertical inventory icon, not a tiny upright arrow",
            "one authored projectile texture; preserve an explicitly authored connected bundle or multi-part body inside that texture",
            str(fill),
        ])
    if family == "spark_mote":
        return ", ".join([
            "compact spark or ember-like body if the authored projectile is a small spark",
            "one authored projectile texture; preserve an explicitly authored connected bundle or multi-part body inside that texture",
            str(fill),
        ])
    return role_contract_prompt_clause(role, canvas)

def sanitize_projectile_family_prompt(data: dict[str, Any], role: str, prompt: str) -> str:
    """Final technical prompt guard for sprite assets.

    The guard is minimal and role-aware: form/material/family words stay authored;
    only full-canvas tether text is compressed into a local visible detail when the
    executable family says this is a tethered projectile body.
    """
    p = tether_visual_prompt_guard(role, str(prompt or ""), data)
    return p[:1800]

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
    return f"The main visual subject is one {r} sprite asset."


def role_supporting_fantasy(role: str, data: dict[str, Any], fantasy: str) -> str:
    """Keep launcher fantasy out of emitted-body prompts without hiding thrown weapons."""
    r = (role or "item").lower()
    if r == "item":
        return fantasy
    if r != "projectile":
        return ""
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    runtime_family = canonical_runtime_family(attack.get("runtimeFamily"))
    return fantasy if runtime_family in _ITEM_FANTASY_PROJECTILE_FAMILIES else ""


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
        "The complete item is fully visible, floating freely with empty magenta margin on every side",
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
            "promptFillWords": "the item body should span most of the canvas along its width or height while staying fully inside the frame",
            "promptPoseWords": "compose it as a clean Terraria-style item sprite",
        },
        "projectile": {
            "targetFill": visual_config.PROJECTILE_ICON_TARGET_FILL,
            "minFill": 0.68,
            "maxFill": 0.96,
            "coreAlphaThreshold": visual_config.SPRITE_EFFECT_CORE_ALPHA_THRESHOLD,
            "marginPx": 1 if size <= 32 else 2,
            "cropPadPx": 1,
            "maxEdgeTouch": 0.10,
            "promptFillWords": "the projectile body should span most of the canvas along its width or height while staying fully inside the frame",
            "promptPoseWords": "compose it as one clean projectile sprite in gameplay view",
        },
        "impact": {
            "targetFill": visual_config.IMPACT_ICON_TARGET_FILL,
            "minFill": 0.52,
            "maxFill": 0.95,
            "coreAlphaThreshold": visual_config.SPRITE_EFFECT_CORE_ALPHA_THRESHOLD,
            "marginPx": 1 if size <= 32 else 2,
            "cropPadPx": 1,
            "maxEdgeTouch": 0.18,
            "promptFillWords": "the burst shape should span most of the canvas along its width or height while staying fully inside the frame",
            "promptPoseWords": "single compact effect burst only, no item or weapon body",
        },
        "child": {
            "targetFill": visual_config.CHILD_ICON_TARGET_FILL,
            "minFill": 0.48,
            "maxFill": 0.90,
            "coreAlphaThreshold": visual_config.SPRITE_EFFECT_CORE_ALPHA_THRESHOLD,
            "marginPx": 1 if size <= 32 else 2,
            "cropPadPx": 1,
            "maxEdgeTouch": 0.14,
            "promptFillWords": "the child body should span a large visible portion of the canvas while staying fully inside the frame",
            "promptPoseWords": "one tiny separate object only",
        },
        "field": {
            "targetFill": visual_config.FIELD_ICON_TARGET_FILL,
            "minFill": 0.62,
            "maxFill": 0.98,
            "coreAlphaThreshold": visual_config.SPRITE_EFFECT_CORE_ALPHA_THRESHOLD,
            "marginPx": 1 if size <= 32 else 2,
            "cropPadPx": 1,
            "maxEdgeTouch": 0.14,
            "promptFillWords": "the field mark should span most of the canvas along its width or height while staying fully inside the frame",
            "promptPoseWords": "single field effect only",
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
        return f"pixel art inventory item icon for a Terraria-like mod, {bg}, one object only, {contract}"
    if role == "projectile":
        return f"pixel art flying projectile sprite for a Terraria-like mod, {bg}, {contract}"
    if role == "impact":
        return f"pixel art hit impact flash sprite, {bg}, small effect only, {contract}"
    if role == "child":
        return f"pixel art secondary projectile sprite, {bg}, tiny separate object, {contract}"
    if role == "field":
        return f"pixel art ground field/trap/rune/cloud sprite, {bg}, flat world effect, {contract}"
    return f"pixel art sprite asset, {bg}, one object, {contract}"

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
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    kit = data.get("visualKit") if isinstance(data.get("visualKit"), dict) else {}
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
        else:
            prompt = str(visual.get("imagePrompt") or data.get("name") or "generated item")

    semantic_contract = image_backend_uses_semantic_prompt_contract()
    if not (semantic_contract and role == "item"):
        prompt = role_visual_prompt_guard(role, prompt, data)

    if semantic_contract:
        # Modern Qwen-text-encoder flow models: feed one final objective visual
        # description, not a legacy Stable Diffusion comma-tag recipe.
        semantic_limit = env_int("INFINI_ZIMAGE_PROMPT_LIMIT", 1800 if image_backend_is_zimage() else 2200)
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
        ((role_style_prefix(role, canvas) if role != "projectile" else (f"pixel art held spear/thrust projection sprite for a Terraria-like mod, {sprite_background_positive_clause()}, readable {'16x16 to 32x32' if canvas <= 32 else '32x32 to 64x64'} silhouette, {family_prompt_clause(data, role, canvas)}" if str((data.get("attack") if isinstance(data.get("attack"), dict) else {}).get("runtimeFamily") or "") == "thrust" else f"pixel art flying projectile sprite for a Terraria-like mod, {sprite_background_positive_clause()}, readable {'16x16 to 32x32' if canvas <= 32 else '32x32 to 64x64'} silhouette, {family_prompt_clause(data, role, canvas)}"))),
        f"asset role: {role}",
        item_name_prompt_clause(role, data),
        f"item fantasy: {fantasy}" if fantasy else "",
        prompt,
        (f"shared authored art direction: {shared_style}" if shared_style else ""),
        f"palette: {palette_words}" if palette_words else "palette: limited high-contrast named colors",
        ("one authored projectile texture only; if the authored subject is a bundle, cluster, swarm, or fan, keep it as one readable projectile bundle rather than separate copies" if role == "projectile" else ""),
        "crisp hard pixel edges, limited palette, no antialiasing look, no UI frame, no text, no character, no scenery, centered single readable asset, keep unused area pure magenta key (#ff00ff)",
    ]
    return compact_prompt_parts(parts, limit=2200, separator=", ")

def projectile_visual_blob(data: dict[str, Any]) -> str:
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    gameplay = data.get("gameplay") if isinstance(data.get("gameplay"), dict) else {}
    tags = data.get("tags") if isinstance(data.get("tags"), list) else []
    parents = []
    for key in ("parentA", "parentB"):
        p = data.get(key) if isinstance(data.get(key), dict) else {}
        parents.append(str(p.get("name") or p.get("internalName") or p.get("fullName") or ""))
    fields = [
        data.get("name"), data.get("category"), gameplay.get("kind"), gameplay.get("damageClass"),
        " ".join(str(t) for t in tags), " ".join(parents),
        visual.get("imagePrompt"), visual.get("projectileImagePrompt"),
        attack.get("projectileSpritePrompt"), attack.get("projectileShape"), attack.get("projectileMotion"),
        attack.get("projectileTrail"), attack.get("weaponFamily"), attack.get("projectileFamily"), attack.get("pattern"), attack.get("attackPattern"),
    ]
    return " ".join(str(x or "") for x in fields).lower()

def is_tiny_projectile_visual(data: dict[str, Any]) -> bool:
    blob = projectile_visual_blob(data)
    tiny_words = {"bullet", "pellet", "dart", "needle", "seed", "coin", "bb", "mote", "spark", "particle", "droplet", "tiny", "small shard", "micro"}
    melee_words = {"sword", "blade", "slash", "cut", "swipe", "stab", "thrust", "shortsword", "broadsword", "glaive", "spear", "lance", "scythe", "axe"}
    return any(w in blob for w in tiny_words) and not any(w in blob for w in melee_words)

def is_melee_arc_projectile_visual(data: dict[str, Any]) -> bool:
    blob = projectile_visual_blob(data)
    return any(w in blob for w in ["sword", "blade", "slash", "cut", "swipe", "stab", "thrust", "shortsword", "broadsword", "glaive", "spear", "lance", "scythe", "axe"])

def effective_projectile_canvas(data: dict[str, Any]) -> int:
    """Choose a readable projectile sprite canvas without changing balance tier.

    Canvas is visual resolution, not progression/medium-tier semantics. A wooden sword
    may stay early/cheap, but a sword/slash projectile should still be readable and not
    appear smaller than the starter Copper Shortsword attack.
    """
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    base = max(16, min(64, int(visual_config.PROJECTILE_SPRITE_CANVAS or 32)))
    item_canvas = max(16, min(64, int(visual.get("preferredCanvasSize") or 32)))
    pw = int(float(attack.get("projectileWidth") or 0) or 0)
    ph = int(float(attack.get("projectileHeight") or 0) or 0)
    major = max(pw, ph)
    if is_tiny_projectile_visual(data):
        # bullets/sparks/darts may legitimately stay 32.
        return base
    if is_melee_arc_projectile_visual(data):
        # Sword/slash/thrust family: readability floor is 48 even for wooden-tier items.
        return max(base, 48, item_canvas if item_canvas >= 48 else 0)
    if major >= 21:
        return max(base, 64 if item_canvas >= 64 else 48)
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
        "one authored projectile texture/composition, no item card, no player, no scene; preserve an explicitly authored connected bundle or multi-part body",
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
        "one authored child-projectile texture/composition, no item card, no player, no scene; preserve explicitly authored connected parts",
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
    "_authored_tether_context",
    "authored_tether_like",
    "tether_sprite_guard_required",
    "_scrub_tether_sprite_body_prompt",
    "tether_visual_prompt_guard",
    "family_prompt_clause",
    "sanitize_projectile_family_prompt",
    "zimage_subject_sentence",
    "zimage_item_identity_sentence",
    "item_name_prompt_clause",
    "sprite_contract_for",
    "role_contract_prompt_clause",
    "role_style_prefix",
    "normalize_asset_prompt",
    "projectile_visual_blob",
    "is_tiny_projectile_visual",
    "is_melee_arc_projectile_visual",
    "effective_projectile_canvas",
    "compact_visual_words",
    "build_projectile_image_prompt",
    "build_impact_image_prompt",
    "build_child_image_prompt",
    "build_field_image_prompt",
    "_ITEM_USABLE_GEAR_GUARD",
]
