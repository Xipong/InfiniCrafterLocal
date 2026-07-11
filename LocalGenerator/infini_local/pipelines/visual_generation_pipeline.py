from __future__ import annotations

import json
import traceback
from typing import Any

from infini_local.core.boundary_models import validate_visual_kit_boundary

from infini_local.core.env_utils import env_float, env_int
from infini_local.core.item_identity_tools import name_of
from infini_local.core.llm_config import USE_LLM
from infini_local.core.llm_json_tools import parse_first_valid_llm_json
from infini_local.pipelines.combine_balance import size_profile_for, stat_profile_for
from infini_local.pipelines.combine_genome_contract import is_llm_planner
from infini_local.pipelines.combine_validation import _stringish
from infini_local.pipelines.item_power_knowledge import tags_of
from infini_local.pipelines.llm_transport import (
    llm_chat_json,
    llm_json_response_format,
    resolve_llm_model,
    visual_director_max_tokens,
)
from infini_local.pipelines.pipeline_visual_config import VISUAL_ASSET_MODE, VISUAL_DIRECTOR_LLM
from infini_local.pipelines.result_identity_policy import palette_from, required_anchors_from

from infini_local.pipelines.visual_prompt_contracts import (
    asset_negative_prompt,
    sprite_background_positive_clause,
    role_visual_prompt_guard,
    sanitize_projectile_family_prompt,
    role_contract_prompt_clause,
)

from infini_local.pipelines.visual_asset_plan import (
    _asset_mode_from_value,
    apply_visual_asset_runtime_gates,
)
from infini_local.services.visual_asset_pipeline import (
    sanitize_image_prompt_background,
    sanitize_visual_palette,
    strip_conflicting_sprite_prompt_bits,
)
from infini_local.storage.trace_runtime import log_event






def attach_visual(data: dict[str, Any], a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any]) -> dict[str, Any]:
    visual = data.setdefault("visual", {})
    tags = set(data.get("tags", [])) | tags_of(a) | tags_of(b)
    anchors = visual.get("requiredAnchors") or required_anchors_from(ca, cb, tags)
    visual["requiredAnchors"] = list(dict.fromkeys(anchors))[:10]
    visual["palette"] = visual.get("palette") or palette_from(tags)
    visual["style"] = "terraria_item_sprite"
    stage = stat_profile_for(a, b, tags)
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
                "Item icon should be one inventory-readable object: weapons/tools as one handheld object, armor as one wearable piece, accessories as one compact wearable/charm, potions as one container. Do not draw emitted projectiles, impact bursts, target markers or fields beside it unless physically integrated. Furniture/placeable parents may appear as parts or integrated cues, not automatically as a full placed tile scene.",
                "Weapon topology: describe one continuous weapon object. Unless itemSilhouetteContract explicitly requires a paired or double-ended construction, use one primary grip/handle/hilt assembly only; do not duplicate handles, guards, pommels, triggers, stocks, or grip sections. Two-handed means one longer shared grip, not two separate handles.",
                "Projectile sprite prompt describes the moving hit object texture; preserve weird authored forms, but do not change gameplay delivery/runtime in art text.",
                "Impact sprite prompt is effect-only: dust, smoke, sparks, fragments, flash, ring, splash or debris burst; do not describe a persistent weapon/item/furniture body there.",
                "Palette is foreground-only; do not list #ff00ff/background/canvas as material.",
                "One core sprite per role; code animates it. shotCount/spread/splitCount are runtime multiplicity: projectileSpritePrompt describes one projectile body, while childSpritePrompt describes one child body.",
                "Item-bodied attacks (returning boomerang, thrust spear, yoyo, thrown item) reuse the item sprite by default; itemIconPrompt is also the held/body sprite, so do not request or describe a separate held asset.",
                "Use visualKit.bakedAssets as the only asset-mode decision surface. Set bakedAssets.projectile.distinctFromItem=true only for an explicitly transformed flight body or a separate emitted projectile. Similarity between a sword and its emitted shard is allowed.",
                "Choose each role mode only in bakedAssets.<role>. Prompt text is not demand; only mode=baked_sprite requests a PNG. Do not add alternate asset-decision fields.",
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
                "Tethered/returning/harpoon sprites: compact moving body plus optional short local rope/chain attachment, not a full-canvas line. Flail projectile is the compact head/weight; whip projectile is a compact tip/segment accent or particle_vfx, never a pre-drawn full lash because runtime animates the tether.",
                "Do not force literal parent silhouettes into every asset; draw the authored final object. If a modded parent has no visual facts, do not invent claims of exact fidelity—use the authored child concept, mechanical facts, palette and explicit anchors.",
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
                    "runtimeFamily", "delivery", "weaponFamily", "projectileFamily", "ammoKind",
                    "projectileShape", "projectileMotion", "projectileRotation", "projectileTrail", "projectileImpact",
                    "secondaryProjectileShape", "secondaryMaterial", "secondaryTrigger", "effect", "onHit", "movement",
                    "shotCount", "spreadRadians", "splitCount", "chainCount", "channelUse", "beamWidthPx", "beamChargeTicks", "immunityCooldown"
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
                    "projectileSpritePrompt": "projectile sprite prompt",
                    "childSpritePrompt": "secondary projectile prompt or empty",
                    "impactSpritePrompt": "hit/expire prompt",
                    "fieldSpritePrompt": "field/trap/rune/cloud prompt or empty",
                    "bakedAssets": {"projectile": {"mode": "none|particle_vfx|reuse_item_sprite|baked_sprite", "prompt": "only if baked_sprite", "distinctFromItem": "boolean; true only for a transformed flight body or separate emitted object", "reason": "short"}, "impact": {"mode": "none|particle_vfx|baked_sprite", "prompt": "only if baked_sprite", "reason": "short"}, "child": {"mode": "none|particle_vfx|baked_sprite", "prompt": "only if baked_sprite", "reason": "short"}, "field": {"mode": "none|particle_vfx|baked_sprite", "prompt": "only if baked_sprite", "reason": "short"}},

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
            "temperature": env_float("INFINI_VISUAL_DIRECTOR_TEMPERATURE", 0.42, lo=0.0, hi=1.2),
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
        allowed_kit_keys = {
            "styleGuide", "palette", "silhouetteSummary", "itemSilhouetteContract",
            "itemIconPrompt", "projectileSpritePrompt", "childSpritePrompt", "impactSpritePrompt",
            "fieldSpritePrompt", "bakedAssets", "vfxIntent", "projectileVfx", "impactVfx",
            "childVfx", "fieldVfx", "vfxScaleHint", "vfxRhythmHint", "vfxMaterialHints",
            "vfxAvoid", "animationPlan", "assetDependencies", "qualityNotes", "negativePrompt",
        }
        unknown_kit_keys = sorted(str(key) for key in kit if key not in allowed_kit_keys)
        if unknown_kit_keys:
            raise ValueError(f"visualKit contains noncanonical keys: {unknown_kit_keys[:8]}")
        data["visualKit"] = kit
        # Current contract has exactly one authored asset-decision surface:
        # visualKit.bakedAssets.<role>.
        baked_assets = kit.get("bakedAssets") if isinstance(kit.get("bakedAssets"), dict) else {}
        clean_baked: dict[str, dict[str, Any]] = {}
        for role in ["projectile", "impact", "child", "field"]:
            spec = baked_assets.get(role) if isinstance(baked_assets, dict) else None
            spec = spec if isinstance(spec, dict) else {}
            mode = _asset_mode_from_value(spec.get("mode"))
            if not mode:
                continue
            row: dict[str, Any] = {"mode": mode}
            prompt = strip_conflicting_sprite_prompt_bits(spec.get("prompt") or "")
            if prompt:
                prompt = sanitize_projectile_family_prompt(data, role, prompt)
                prompt = role_visual_prompt_guard(role, prompt, data)
                row["prompt"] = prompt[:1400]
            if spec.get("reason"):
                row["reason"] = str(spec.get("reason"))[:240]
            if role == "projectile" and isinstance(spec.get("distinctFromItem"), bool):
                row["distinctFromItem"] = bool(spec.get("distinctFromItem"))
            clean_baked[role] = row
        if clean_baked:
            kit["bakedAssets"] = clean_baked
        else:
            kit.pop("bakedAssets", None)
        kit = validate_visual_kit_boundary(kit)
        data["visualKit"] = kit
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
