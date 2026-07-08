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

from infini_local.core.env_utils import env_bool, env_float, env_int, env_str, env_first, env_path
from urllib import request as urlrequest
from urllib import error as urlerror
from urllib.parse import urlencode
from infini_local.pipelines.visual_soul import (
    _clamp01,
    _hex_from_rgb,
    _rgb_to_hsv01,
    _rgba_pixels,
    analyze_visual_soul_from_sprite,
    attach_visual_soul_from_sprite,
    visual_soul_archetype,
    visual_soul_tooltip,
)

from infini_local.pipelines.visual_prompt_contracts import (
    asset_negative_prompt,
    chroma_rgb,
    chroma_name,
    sprite_background_positive_clause,
    sprite_background_negative_clause,
    image_backend_is_zimage,
    zimage_positive_only_enabled,
    zimage_role_description,
    zimage_positive_guard_clause,
    _is_generated_usable_gear,
    _compact_prompt_append,
    _blade_shape_needs_fused_contour_guard,
    _item_blade_guard_context,
    _prompt_probe,
    _append_item_role_guard_once,
    _strip_item_role_guard_fragments,
    _authored_item_silhouette_contract,
    _prepend_prompt_contracts,
    role_visual_prompt_guard,
    _authored_tether_context,
    authored_tether_like,
    tether_sprite_guard_required,
    _scrub_tether_sprite_body_prompt,
    tether_visual_prompt_guard,
    family_prompt_clause,
    sanitize_projectile_family_prompt,
    zimage_subject_sentence,
    zimage_item_identity_sentence,
    item_name_prompt_clause,
    sprite_contract_for,
    role_contract_prompt_clause,
    role_style_prefix,
    normalize_asset_prompt,
    projectile_visual_blob,
    is_tiny_projectile_visual,
    is_melee_arc_projectile_visual,
    effective_projectile_canvas,
    compact_visual_words,
    build_projectile_image_prompt,
    build_impact_image_prompt,
    build_child_image_prompt,
    build_field_image_prompt,
    _BLADE_SUBJECT_RE,
    _FUSED_BLADE_RISK_RE,
    _ITEM_USABLE_GEAR_GUARD,
    _ITEM_USABLE_PARTS_GUARD,
)

from infini_local.pipelines.visual_asset_plan import (
    should_generate_child_asset,
    should_generate_field_asset,
    _visual_kit,
    _role_baked_asset_spec,
    _role_asset_prompt,
    _asset_mode_from_value,
    compiled_child_projectile_needs_sprite,
    authored_asset_mode,
    visual_asset_runtime_gate,
    apply_visual_asset_runtime_gates,
    legacy_projectile_baked_sprite_fallback,
    build_visual_asset_plan,
)

from infini_local.pipelines.visual_asset_manifest import (
    _asset_sha256,
    _asset_descriptor,
    sprite_contract_for_asset,
    _compact_text,
    _parent_manifest_summary,
    _asset_manifest_entry,
    write_visual_manifest,
)

from infini_local.pipelines.visual_delivery_gate import (
    VisualDeliveryBlocked,
    _sprite_status_is_usable,
    _item_sprite_status_is_usable,
    _asset_path_exists,
    visual_delivery_report,
    assert_visual_delivery_ready,
)

from infini_local.pipelines.visual_sprite_generation import (
    maybe_generate_sprite,
    _validation_reasons,
    refit_processed_sprite_to_contract,
    generate_visual_asset,
    maybe_generate_visual_assets,
)

from infini_local.pipelines.pipeline_support import (
    Image,
    ImageDraw,
    APP_VERSION,
    BG_COLOR,
    BG_REMOVE_MODE,
    CHILD_ICON_TARGET_FILL,
    CHILD_SPRITE_CANVAS,
    FIELD_ICON_TARGET_FILL,
    FIELD_SPRITE_CANVAS,
    GENERATE_VARIANTS,
    IMAGE_BACKEND,
    IMPACT_ICON_TARGET_FILL,
    IMPACT_SPRITE_CANVAS,
    ITEM_ICON_TARGET_FILL,
    LLM_RUNTIME_AUTHORING,
    PROJECTILE_ICON_TARGET_FILL,
    PROJECTILE_SPRITE_CANVAS,
    REMOVE_BG,
    SDCPP_MODEL,
    SDCPP_SERVER_COMMAND_TEMPLATE,
    SDCPP_SERVER_EXTRA_ARGS,
    SPRITE_DIR,
    SPRITE_EFFECT_CORE_ALPHA_THRESHOLD,
    SPRITE_ITEM_CORE_ALPHA_THRESHOLD,
    SPRITE_RETRIES,
    USE_LLM,
    VISUAL_ALLOW_PROCEDURAL_FALLBACK,
    VISUAL_ASSET_MODE,
    VISUAL_DIRECTOR_LLM,
    VISUAL_GENERATE_CHILD_FIELD_IMAGES,
    VISUAL_GENERATE_IMPACT_IMAGES,
    VISUAL_GENERATE_PROJECTILE_IMAGES,
    VISUAL_PIPELINE_PROFILE,
    VISUAL_REQUIRE_ITEM_SPRITE,
    VISUAL_REQUIRE_ZIMAGE_BACKEND,
    VISUAL_STRICT_AI_AUTHORSHIP,
    WORLD_RECIPES_DIR,
    ZIMAGE_POSITIVE_ONLY,
    ZIMAGE_PROMPT_CONTRACT,
    _env_float,
    asset_sync_service,
    compact_zimage_asset_prompt,
    log_event,
    name_of,
    parse_first_valid_llm_json,
    runtime_plan,
    sanitize_image_prompt_background,
    sanitize_projectile_prompt_multiplicity,
    sanitize_visual_palette,
    sprite_status_from_raw_path,
    strip_conflicting_sprite_prompt_bits,
    tags_of,
    trace_event,
    visual_asset_pipeline,
    zimage_palette_sentence,
    zimage_pe_clean_text,
    zimage_text_policy_sentence,
)

from infini_local.pipelines.combine_validation import (
    _stringish,
)
from infini_local.pipelines.combine_genome_contract import (
    is_llm_planner,
)
from infini_local.pipelines.result_identity_policy import (
    palette_from,
    required_anchors_from,
)
from infini_local.pipelines.combine_balance import (
    size_profile_for,
    stage_profile_for,
)
from infini_local.pipelines.projectile_affordance import (
    infer_projectile_visual_family,
)

from infini_local.pipelines.image_backend_pipeline import (
    generate_a1111,
    generate_comfyui,
    generate_image_api,
    generate_sdcpp,
)

from infini_local.pipelines.llm_transport import (
    llm_chat_json,
    llm_json_response_format,
    resolve_llm_model,
    visual_director_max_tokens,
)

from infini_local.pipelines.sprite_postprocess import (
    build_retry_prompt_from_validation,
    pick_best_sprite,
    postprocess_sprite,
    sprite_validation_fatal,
    validate_processed_sprite,
)






def attach_visual(data: dict[str, Any], a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any]) -> dict[str, Any]:
    visual = data.setdefault("visual", {})
    tags = set(data.get("tags", [])) | tags_of(a) | tags_of(b)
    anchors = visual.get("requiredAnchors") or required_anchors_from(ca, cb, tags)
    visual["requiredAnchors"] = list(dict.fromkeys(anchors))[:10]
    visual["palette"] = visual.get("palette") or palette_from(tags)
    visual["style"] = "terraria_item_sprite"
    stage = stage_profile_for(a, b, tags)
    size = size_profile_for(str(data.get("name", "generated item")), tags, data.get("gameplay", {}).get("kind") or data.get("category") or "generic", stage)
    visual.setdefault("preferredCanvasSize", size["preferredCanvasSize"])
    visual.setdefault("inventoryScale", size["inventoryScale"])
    visual.setdefault("worldScale", size["worldScale"])
    visual.setdefault("drawOffsetX", 0)
    visual.setdefault("drawOffsetY", 0)
    visual["negativePrompt"] = asset_negative_prompt("item")
    authored_prompt = str(visual.get("imagePrompt") or "").strip()
    if authored_prompt and is_llm_planner(data):
        visual["imagePrompt"] = sanitize_image_prompt_background(authored_prompt)
    else:
        visual["imagePrompt"] = sanitize_image_prompt_background(build_image_prompt(data, visual))
        if isinstance(data.get("presentationGenome"), dict):
            pg = data["presentationGenome"]
            visual["imagePrompt"] += ", coherent with " + str((pg.get("heldSprite") or {}).get("silhouette", "item")) + " and " + str((pg.get("attackVisual") or {}).get("effect", "neutral")) + " attack visuals"
    visual.setdefault("spriteStatus", "prompt_only")
    return data

def build_image_prompt(data: dict[str, Any], visual: dict[str, Any]) -> str:
    anchors = [str(a) for a in visual.get("requiredAnchors", []) if str(a).strip()]
    palette = [str(c).replace("_", " ") for c in visual.get("palette", []) if str(c).strip()]
    name = data.get("name", "generated item")
    canvas = int(visual.get("preferredCanvasSize") or 32)
    large_hint = "slightly oversized sprite allowed" if canvas >= 64 else "standard item sprite scale"
    parts = [
        "pixel art game item icon",
        "Terraria-like item sprite",
        sprite_background_positive_clause(),
        "centered single object",
        "simple readable silhouette",
        "limited palette",
        large_hint,
        role_contract_prompt_clause("item", canvas),
        f"target canvas feeling: {canvas}x{canvas}",
        f"item concept: {name}",
    ]
    if anchors:
        parts.append("must visibly include: " + ", ".join(anchors[:8]))
    if palette:
        parts.append("palette: " + ", ".join(palette[:6]))
    parts.append("no scene, no character, no text")
    return ", ".join(parts)



































































































def apply_visual_director(data: dict[str, Any], a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any]) -> dict[str, Any]:
    """v0.3.9: LLM art director pass.

    The planner writes the toy. This pass turns that toy into a sprite asset pack:
    item icon, projectile, child/echo, impact and field/trap. It is deliberately
    separate from balance so the art prompt is not rebuilt into generic bolts.
    """
    if not (USE_LLM and VISUAL_DIRECTOR_LLM and is_llm_planner(data)):
        return data
    if VISUAL_ASSET_MODE not in {"full", "all", "projectile", "visualpack", "assetpack"}:
        return data
    try:
        concept = data.get("concept") if isinstance(data.get("concept"), dict) else {}
        attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
        visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
        payload = {
            "task": "Create a coherent pixel-art visual asset pack for this generated Terraria-like toy. Do not change gameplay stats.",
            "zImageAssumption": "For Z-Image Turbo, write PE-style final visual descriptions: preserve subject, quantity, action, state, colors and material identity; describe composition and texture as objective visual facts; do not rely on a negative prompt.",
            "rules": [
                "Return one JSON object; no markdown or analysis.",
                "Build role-separated assets, not one copied generic prompt.",
                "Each sprite prompt describes one pixel asset on solid #ff00ff, not a scene.",
                "Item icon for a usable gear result should read as one handheld/carriable object; furniture/placeable parents may appear as parts or integrated cues, not automatically as a full placed tile scene.",
                "Projectile sprite prompt describes the moving hit object texture; preserve weird authored forms, but do not change gameplay delivery/runtime in art text.",
                "Impact sprite prompt is effect-only: dust, smoke, sparks, fragments, flash, ring, splash or debris burst; do not describe a persistent weapon/item/furniture body there.",
                "Palette is foreground-only; do not list #ff00ff/background/canvas as material.",
                "One core sprite per role; code animates it.",
                "Distinct roles should look distinct when present.",
                "Choose asset modes yourself. Prompt text is not demand; only mode=baked_sprite requests a PNG.",
                "Ordinary melee, arrows/bullets, and simple hits usually use particle_vfx or none for impact.",
                "Use ParticleLibrary/Dust/runtime VFX for sparks, dust, glints, smoke, small bursts, trails, and simple fields. Use baked_sprite only for a real separate body/decal/rune/cloud/child entity.",
                "Keep the fantasy visible; avoid generic sword/wand/orb/bolt collapse.",
                "Use named foreground colors and concrete shape/material words.",
                "Keep the object large in frame along at least one axis; no frame/border wording.",
                "Projectile prompts preserve the authored object; use canonical gameplay view only when supported by object or parent projectile facts.",
                "Projectile prompts describe the moving hit texture; do not change gameplay/delivery based on visual words.",
                "Impact prompts describe only a short hit/expire effect: burst, puff, ring, splash, dust, sparks, shards, or fragments. Do not draw the item/weapon/furniture body inside impact.",
                "Effects are accents unless authored as the body.",
                "Z-Image prompts: subject first, then shape, materials, palette, and minimal sprite constraints.",
                "For item icons, write one itemSilhouetteContract sentence: concrete proportions/parts/readability for this exact generated object; do not use a generic weapon class label alone.",
                "No SD tags, negative-prompt blocks, masterpiece/8K/meta labels.",
                "If exact text must appear, quote it; otherwise use no text/logos/UI marks.",
                "Tethered/returning/harpoon sprites: compact moving body plus optional short local rope/chain attachment, not a full-canvas line.",
                "Do not force literal parent silhouettes into every asset; draw the authored final object.",
                "Write short VFX intent lines as plain visual hints, not code.",
                "VFX hints may use scale/tempo/material words, but no numeric particle counts.",
            ],
            "item": {
                "name": data.get("name"),
                "tooltip": data.get("tooltip"),
                "category": data.get("category"),
                "parents": [name_of(a), name_of(b)],
                "concept": concept,
                "runtimeAffordance": data.get("runtimeAffordance") if isinstance(data.get("runtimeAffordance"), dict) else {},
                "attack": {k: attack.get(k) for k in [
                    "delivery", "weaponFamily", "projectileFamily", "ammoKind",
                    "projectileShape", "projectileMotion", "projectileRotation", "projectileTrail", "projectileImpact", "secondaryProjectileShape", "secondaryMaterial", "effect", "onHit", "movement"
                ]},
                "existingVisual": {k: visual.get(k) for k in ["objectType", "requiredAnchors", "palette", "imagePrompt", "projectileImagePrompt", "impactImagePrompt"]},
            },
            "requiredJsonShape": {
                "visualKit": {
                    "styleGuide": "shared art direction in one sentence",
                    "palette": ["named colors"],
                    "silhouetteSummary": "main readable shape",
                    "itemSilhouetteContract": "one sentence: exact item icon proportions, required readable parts, and forbidden near-miss silhouettes for this generated object",
                    "itemIconPrompt": "item sprite prompt",
                    "heldSpritePrompt": "held sprite prompt or same as item",
                    "projectileSpritePrompt": "projectile sprite prompt",
                    "childSpritePrompt": "child/spark/mote prompt or empty",
                    "impactSpritePrompt": "hit/expire prompt",
                    "fieldSpritePrompt": "field/trap/rune/cloud prompt or empty",
                    "bakedAssets": {"projectile": {"mode": "none|particle_vfx|baked_sprite", "prompt": "only if baked_sprite", "reason": "short"}, "impact": {"mode": "none|particle_vfx|baked_sprite", "prompt": "only if baked_sprite", "reason": "short"}, "child": {"mode": "none|particle_vfx|baked_sprite", "prompt": "only if baked_sprite", "reason": "short"}, "field": {"mode": "none|particle_vfx|baked_sprite", "prompt": "only if baked_sprite", "reason": "short"}},
                    "assetModes": {"projectile": "none|particle_vfx|baked_sprite", "impact": "none|particle_vfx|baked_sprite", "child": "none|particle_vfx|baked_sprite", "field": "none|particle_vfx|baked_sprite"},
                    "projectileAssetMode": "none|particle_vfx|baked_sprite",
                    "impactAssetMode": "none|particle_vfx|baked_sprite",
                    "childAssetMode": "none|particle_vfx|baked_sprite",
                    "fieldAssetMode": "none|particle_vfx|baked_sprite",
                    "vfxIntent": "max 12 words: overall runtime VFX intent, e.g. large impact burst, short ragged trail",
                    "projectileVfx": "max 10 words: travel/active VFX hint",
                    "impactVfx": "max 10 words: hit/expire VFX hint",
                    "childVfx": "max 10 words: child/echo VFX hint, or empty string",
                    "fieldVfx": "max 10 words: field/trap VFX hint, or empty string",
                    "vfxScaleHint": "one of tiny, small, normal, large, huge; visual scale may differ from projectile size",
                    "vfxRhythmHint": "one of slow, normal, snappy, delayed, pulsing",
                    "vfxMaterialHints": ["3-8 plain words: smoke, shards, sparks, cloth, goo, frost, star, shadow, etc."],
                    "vfxAvoid": "short note about what VFX should avoid, or empty string",
                    "animationPlan": ["short visible beats, e.g. launch, travel, hit, expire"],
                    "assetDependencies": ["which gameplay event uses which asset"],
                    "qualityNotes": ["how to keep silhouettes distinct in game"],
                    "negativePrompt": "empty for Z-Image; optional only for non-Z-Image"
                }
            }
        }
        model_name = resolve_llm_model()
        req = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": "You direct pixel-art assets for Z-Image in a Terraria-like generated-item mod. Write concise final visual descriptions, not SD/negative-prompt recipes. Preserve authored subject, count, action, state, colors, and materials. Do not add unauthored glow, magic, energy, child motes, or material effects. Return one JSON object."},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))},
            ],
            "temperature": _env_float("INFINI_VISUAL_DIRECTOR_TEMPERATURE", 0.42, 0.0, 1.2),
            "max_tokens": visual_director_max_tokens(),
            "response_format": llm_json_response_format("infini_visual_director"),
        }
        raw = llm_chat_json(req, timeout=env_int("INFINI_LLM_TIMEOUT", 95))
        content = raw["choices"][0]["message"]["content"]
        obj = parse_first_valid_llm_json(content)
        kit = obj.get("visualKit") if isinstance(obj, dict) and isinstance(obj.get("visualKit"), dict) else obj if isinstance(obj, dict) else {}
        if not isinstance(kit, dict):
            return data
        # v0.4.49: keep the manifest honest too.  The old code mapped sanitized prompts
        # into visual/attack, but left visualKit itself with side-view/halo/dark-background
        # wording, making debug manifests look worse than the actual generated prompt.
        for prompt_key, role_hint in [
            ("itemIconPrompt", "item"),
            ("heldSpritePrompt", "item"),
            ("projectileSpritePrompt", "projectile"),
            ("childSpritePrompt", "child"),
            ("impactSpritePrompt", "impact"),
            ("fieldSpritePrompt", "field"),
            ("negativePrompt", "generic"),
        ]:
            if kit.get(prompt_key):
                cleaned = strip_conflicting_sprite_prompt_bits(kit.get(prompt_key) or "")
                cleaned = sanitize_projectile_family_prompt(data, role_hint, cleaned)
                cleaned = role_visual_prompt_guard(role_hint, cleaned, data)
                if cleaned:
                    kit[prompt_key] = cleaned
        for text_key in ["styleGuide", "silhouetteSummary", "itemSilhouetteContract", "silhouetteContract", "shapeContract", "itemShapeContract", "vfxIntent", "projectileVfx", "impactVfx", "childVfx", "vfxAvoid"]:
            if kit.get(text_key):
                kit[text_key] = sanitize_projectile_family_prompt(data, "projectile" if "projectile" in text_key.lower() else "item", str(kit.get(text_key)))[:700]
        data["visualKit"] = kit
        # Preserve explicit model decisions about whether a role needs a baked PNG.
        # build_visual_asset_plan() treats GUI flags as allow-gates, not force-generate.
        mode_map = kit.get("assetModes") if isinstance(kit.get("assetModes"), dict) else {}
        normalized_modes = {}
        for role in ["projectile", "impact", "child", "field"]:
            mode = _asset_mode_from_value(mode_map.get(role) if isinstance(mode_map, dict) else "") or _asset_mode_from_value(kit.get(f"{role}AssetMode")) or _asset_mode_from_value(kit.get(f"{role}SpriteMode"))
            if mode:
                normalized_modes[role] = mode
                kit[f"{role}AssetMode"] = mode
        baked_assets = kit.get("bakedAssets") if isinstance(kit.get("bakedAssets"), dict) else {}
        if isinstance(baked_assets, dict):
            clean_baked = {}
            for role in ["projectile", "impact", "child", "field"]:
                spec = baked_assets.get(role)
                if isinstance(spec, dict):
                    mode = _asset_mode_from_value(spec.get("mode") or spec.get("assetMode") or spec.get("enabled"))
                    prompt = strip_conflicting_sprite_prompt_bits(spec.get("prompt") or spec.get("spritePrompt") or spec.get("imagePrompt") or "")
                    if mode:
                        clean_baked[role] = {"mode": mode}
                        if prompt:
                            prompt = sanitize_projectile_family_prompt(data, role, prompt)
                            prompt = role_visual_prompt_guard(role, prompt, data)
                            clean_baked[role]["prompt"] = prompt[:1400]
                        if spec.get("reason"):
                            clean_baked[role]["reason"] = str(spec.get("reason"))[:240]
                        normalized_modes[role] = mode
                        kit[f"{role}AssetMode"] = mode
            if clean_baked:
                kit["bakedAssets"] = clean_baked
                kit["assetModes"] = normalized_modes
        if normalized_modes:
            kit["assetModes"] = normalized_modes
        apply_visual_asset_runtime_gates(data, kit)
        data.setdefault("debug", {})["visualDirectorRawOutput"] = content[:10000]
        data["debug"]["visualDirectorModel"] = model_name
        visual = data.setdefault("visual", {})
        attack = data.setdefault("attack", {})
        if kit.get("palette"):
            cleaned_palette = sanitize_visual_palette(kit.get("palette") or [], limit=8)
            if cleaned_palette:
                kit["palette"] = cleaned_palette
                visual["palette"] = cleaned_palette
            else:
                kit.pop("palette", None)
        neg = str(kit.get("negativePrompt") or "").strip()
        if neg:
            visual["negativePrompt"] = neg
        mapping = [
            (visual, "imagePrompt", "itemIconPrompt"),
            (visual, "projectileImagePrompt", "projectileSpritePrompt"),
            (visual, "impactImagePrompt", "impactSpritePrompt"),
            (visual, "childImagePrompt", "childSpritePrompt"),
            (visual, "fieldImagePrompt", "fieldSpritePrompt"),
            (attack, "projectileSpritePrompt", "projectileSpritePrompt"),
            (attack, "impactSpritePrompt", "impactSpritePrompt"),
            (attack, "childSpritePrompt", "childSpritePrompt"),
            (attack, "fieldSpritePrompt", "fieldSpritePrompt"),
        ]
        for dst, dst_key, src_key in mapping:
            val = strip_conflicting_sprite_prompt_bits(kit.get(src_key) or "")
            if val:
                dst[dst_key] = val[:1400]
        if kit.get("silhouetteSummary"):
            visual["silhouetteSummary"] = str(kit.get("silhouetteSummary"))[:700]
        for contract_key in ("itemSilhouetteContract", "silhouetteContract", "shapeContract", "itemShapeContract"):
            if kit.get(contract_key):
                visual["itemSilhouetteContract"] = str(kit.get(contract_key))[:700]
                break
        # v0.3.16: dirty VFX selector hints authored in the same visual-director pass as Z-Image prompts.
        for src_key, dst_key in [
            ("vfxIntent", "vfxIntent"),
            ("projectileVfx", "projectileVfx"),
            ("impactVfx", "impactVfx"),
            ("childVfx", "childVfx"),
            ("fieldVfx", "fieldVfx"),
            ("vfxScaleHint", "vfxScaleHint"),
            ("vfxRhythmHint", "vfxRhythmHint"),
            ("vfxAvoid", "vfxAvoid"),
        ]:
            val = str(kit.get(src_key) or "").strip()
            if val:
                visual[dst_key] = val[:700]
                attack[dst_key] = val[:700]
        if kit.get("animationPlan"):
            attack["visualAnimationPlan"] = _stringish(kit.get("animationPlan"), "")[:1200]
        if kit.get("assetDependencies"):
            visual["assetDependencies"] = _stringish(kit.get("assetDependencies"), "")[:1400]
        if kit.get("qualityNotes"):
            visual["qualityNotes"] = _stringish(kit.get("qualityNotes"), "")[:1400]
        if kit.get("vfxMaterialHints"):
            material_hints = [str(x).strip() for x in (kit.get("vfxMaterialHints") or []) if str(x).strip()][:12]
            if material_hints:
                visual["vfxMaterialHints"] = material_hints
                attack["vfxMaterialHints"] = material_hints
        data["attack"] = attack
        data["visual"] = visual
    except Exception as e:
        data.setdefault("debug", {})["visualDirectorError"] = repr(e)
        log_event("warn", "visual director failed", {"error": repr(e), "trace": traceback.format_exc()})
    return data
