from __future__ import annotations

import copy
from typing import Any


from infini_local.core.item_identity_tools import (
    generated_data_of,
    item_field,
    name_of,
)
from infini_local.pipelines.context.parents import (
    _compact_keep,
    _dedupe_projectile_profile,
    compact_ammo_profile,
    compact_item_raw_for_llm,
    compact_projectile_profile,
    compact_vanilla_flags_for_llm,
    effective_projectile_profile_of,
    projectile_profile_of,
    native_item_context_from_dump,
)

# LLM parent packet owner. Extraction lives in parents; identity
# primitives come directly from their defining module. No derived-card alternative.


def _native_sprite_reference_for_llm(value: Any) -> dict[str, Any]:
    """Copy loaded texture/UI-frame facts, never a collider or inferred display size."""
    if not isinstance(value, dict) or value.get("source") not in {"TextureAssets.Item", "TextureAssets.Projectile"}:
        return {}
    width, height = value.get("textureWidthPx"), value.get("textureHeightPx")
    if any(type(dimension) is not int or not 1 <= dimension <= 2_147_483_647 for dimension in (width, height)):
        return {}
    observation = {"source": value["source"], "textureWidthPx": width, "textureHeightPx": height}
    if value["source"] == "TextureAssets.Projectile":
        if value.get("frameLayout") != "unknown_custom_draw_possible":
            return {}
        observation["frameLayout"] = value["frameLayout"]
        return observation
    frame = value.get("currentFrame")
    if isinstance(frame, dict) and frame.get("source") in ("texture_bounds", "draw_animation"):
        numbers: list[Any] = [frame.get(key) for key in ("xPx", "yPx", "widthPx", "heightPx")]
        x, y, w, h = numbers
        if (all(type(number) is int for number in (x, y, w, h))
                and x >= 0 and y >= 0 and w > 0 and h > 0
                and x + w <= width and y + h <= height
                and (frame["source"] != "texture_bounds" or (x, y, w, h) == (0, 0, width, height))):
            observation["currentFrame"] = {key: frame[key] for key in ("source", "xPx", "yPx", "widthPx", "heightPx")}
    return copy.deepcopy(observation)


# Accepted appearance only: omit PNG paths, URLs, image-job/status/score data and
# derived classifications. These values are copied, never interpreted as design.
_PARENT_VISUAL_FIELDS = (
    "role", "assetMode", "visualProjectRef", "prompt", "imagePrompt", "negativePrompt",
    "silhouette", "visualIdentity", "palette", "preferredCanvasSize", "renderSizePx",
    "forwardAngleDegrees", "inventoryScale", "worldScale", "scale", "grip",
    "drawOffsetX", "drawOffsetY", "accessoryMount", "equipOverlayPrompt",
)


def _accepted_visual_facts(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    facts = {key: copy.deepcopy(value[key]) for key in _PARENT_VISUAL_FIELDS if key in value}
    size = facts.get("renderSizePx")
    if "renderSizePx" in facts and not (type(size) is int and 1 <= size <= 512):
        facts.pop("renderSizePx")
    return facts


def raw_parent_card_for_llm(item: dict[str, Any], *, include_visual_reference: bool = False,
                          prefer_readable_source: bool = True) -> dict[str, Any]:
    """Compact parent card for the LLM.

    The packet contains raw source fields or exact accepted generated runtime facts.
    It never adds code-derived semantics, behavior digests, categories or tags.
    Visual consumers may opt into read-only accepted appearance and calibration:
    loaded native texture/UI-frame pixels or generated root/entity identity,
    silhouette, palette, grip, canvas/axis and scales. Missing facts stay unknown;
    no appearance becomes a gameplay choice or required child dimension.
    """
    item = native_item_context_from_dump(item)
    item_raw = compact_item_raw_for_llm(item)
    cross_mod_identity = {
        "sourceMod": str(item_field(item, "sourceMod", "Terraria")),
        "fullName": str(item_field(item, "fullName", "")),
        "shootProjectileFullName": str(item_field(item, "shootProjectileFullName", "")),
    }
    cross_mod_identity = {k: v for k, v in cross_mod_identity.items() if _compact_keep(v)}
    card: dict[str, Any] = {
        "name": name_of(item),
        "internalName": str(item_field(item, "internalName", "")),
        "sourceMod": str(item_field(item, "sourceMod", "Terraria")),
        "raw": {"item": item_raw},
    }
    if cross_mod_identity:
        card["raw"]["crossModIdentity"] = cross_mod_identity
    if isinstance(item.get("runtimeDumpItemProvenance"), dict):
        card["raw"]["runtimeDumpProvenance"] = copy.deepcopy(item["runtimeDumpItemProvenance"])
    vanilla_flags = compact_vanilla_flags_for_llm(item)
    if vanilla_flags:
        card["raw"]["vanillaFlags"] = vanilla_flags
    gd = generated_data_of(item)
    if include_visual_reference and not isinstance(item.get("generatedData"), dict):
        sprite_reference = _native_sprite_reference_for_llm(item.get("spriteReferenceRaw"))
        if sprite_reference and sprite_reference["source"] == "TextureAssets.Item":
            card["raw"]["spriteReference"] = sprite_reference
    direct: dict[str, Any] = {}
    effective: dict[str, Any] = {}
    ammo: dict[str, Any] = {}
    if not gd:
        direct = compact_projectile_profile(projectile_profile_of(item), prefer_readable_source=prefer_readable_source)
        effective = compact_projectile_profile(effective_projectile_profile_of(item), prefer_readable_source=prefer_readable_source)
        ammo = compact_ammo_profile(item, prefer_readable_source=prefer_readable_source)
        if include_visual_reference:
            for target, profile in ((direct, projectile_profile_of(item)),
                                    (effective, effective_projectile_profile_of(item))):
                reference = _native_sprite_reference_for_llm(profile.get("spriteReferenceRaw"))
                if reference and reference["source"] == "TextureAssets.Projectile":
                    target["spriteReference"] = reference
    if direct:
        card["raw"]["directProjectile"] = direct
    if effective:
        card["raw"]["effectiveProjectile"] = effective

    if ammo:
        if direct:
            _dedupe_projectile_profile(card["raw"], "effectiveProjectile", "directProjectile", direct)
            _dedupe_projectile_profile(ammo, "projectileRaw", "directProjectile", direct)
            _dedupe_projectile_profile(ammo, "weaponShootFieldProjectileRaw", "directProjectile", direct)
        elif effective:
            _dedupe_projectile_profile(ammo, "projectileRaw", "effectiveProjectile", effective)
            _dedupe_projectile_profile(ammo, "weaponShootFieldProjectileRaw", "effectiveProjectile", effective)
        if ammo:
            card["raw"]["ammo"] = ammo
    elif direct:
        _dedupe_projectile_profile(card["raw"], "effectiveProjectile", "directProjectile", direct)

    if isinstance(gd, dict) and gd:
        runtime_raw = gd.get("runtimeProgram", {})
        runtime_raw = runtime_raw if isinstance(runtime_raw, dict) else {}
        summary_raw = gd.get("generatedParentSummary", {})
        runtime = copy.deepcopy(runtime_raw)
        summary = summary_raw if isinstance(summary_raw, dict) else {}
        # Read-only identity projection, not authoring/lowering: preserve every
        # accepted mechanical value, binding/event ID, zero, false and empty list.
        # Appearance has a separate Visual-only handoff below; never let it
        # become Author context or replace exact mechanics with a prose summary.
        for entity in runtime.get("entities") or []:
            if isinstance(entity, dict):
                entity.pop("visual", None)
        generated_parent = {"runtimeProgram": runtime}
        for key in ("id", "recipeKey", "gameplay", "accessory", "armor"):
            value = gd.get(key)
            if value is not None:
                generated_parent[key] = copy.deepcopy(value)
        if summary:
            generated_parent["summary"] = {key: copy.deepcopy(summary.get(key)) for key in (
                "schema", "name", "identity", "description", "playerExperience",
            ) if _compact_keep(summary.get(key))}
        if include_visual_reference:
            visual = _accepted_visual_facts(gd.get("visual", {}))
            if visual:
                generated_parent["visual"] = visual
            # Exact entity IDs and kinds remain alongside their own accepted
            # appearance; do not select one parent entity or fill inherited data.
            for source, entity in zip(runtime_raw.get("entities") or [], runtime.get("entities") or []):
                if isinstance(source, dict) and isinstance(entity, dict):
                    appearance = _accepted_visual_facts(source.get("visual"))
                    if appearance:
                        entity["visual"] = appearance
        card["raw"]["generatedParent"] = generated_parent
    # Do not send section bookkeeping or token-byte metadata to the LLM; the raw object keys are enough.
    # The field selection above owns the card shape. Source records and the
    # accepted generated contract are literal, not input for a recursive scrub.
    return {k: v for k, v in card.items() if _compact_keep(v)}

__all__ = ["raw_parent_card_for_llm"]
