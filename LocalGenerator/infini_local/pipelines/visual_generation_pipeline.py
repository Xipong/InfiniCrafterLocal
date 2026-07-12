from __future__ import annotations

import copy
import json
import traceback
from typing import Any

from infini_local.core.boundary_models import canonical_visual_kit_view

from infini_local.core.env_utils import env_float, env_int
from infini_local.core.item_identity_tools import stable_hash
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
    image_backend_is_zimage,
    image_backend_uses_semantic_prompt_contract,
    sprite_background_positive_clause,
    role_visual_prompt_guard,
    sanitize_projectile_family_prompt,
    role_contract_prompt_clause,
)

from infini_local.pipelines.visual_director_contract import (
    visual_director_context,
    visual_kit_projection_errors,
    visual_kit_response_schema,
    visual_kit_usefulness_errors,
)

from infini_local.services.visual_asset_pipeline import (
    sanitize_image_prompt_background,
    sanitize_visual_palette,
    strip_conflicting_sprite_prompt_bits,
)
from infini_local.storage.trace_runtime import log_event


def anime_reference_opportunity(data: dict[str, Any]) -> str:
    """Return a stable, deliberately rare visual-reference budget for one recipe."""
    seed = str(data.get("recipeKey") or data.get("id") or data.get("name") or "generated-item")
    roll = int(stable_hash("anime-reference-opportunity-v1", seed, length=8), 16) % 1000
    if roll < 20:
        return "strong"
    if roll < 120:
        return "subtle"
    return "none"


def _sanitize_anime_reference(value: Any, maximum_strength: str) -> dict[str, Any] | None:
    if maximum_strength not in {"subtle", "strong"} or not isinstance(value, dict):
        return None
    strength = str(value.get("strength") or "").strip().lower()
    if strength not in {"subtle", "strong"}:
        return None
    if maximum_strength == "subtle" and strength == "strong":
        return None
    source = " ".join(str(value.get("source") or "").split())[:160]
    raw_motifs = value.get("motifs")
    if not isinstance(raw_motifs, list):
        return None
    motifs = [" ".join(str(item).split())[:120] for item in raw_motifs if str(item).strip()][:3]
    blocked_motif_fragments = (
        "character portrait",
        "official artwork",
        "screenshot",
        "copied logo",
        "title text",
        "direct asset replica",
    )
    if not source or not motifs or any(
        blocked in motif.casefold()
        for motif in motifs
        for blocked in blocked_motif_fragments
    ):
        return None
    return {"strength": strength, "source": source, "motifs": motifs}


def _append_anime_reference_to_prompt(prompt: Any, reference: dict[str, Any]) -> str:
    """Project an accepted visual-only reference into the actual item prompt."""
    base = " ".join(str(prompt or "").split())
    source = str(reference.get("source") or "").strip()
    motifs = [str(item).strip() for item in (reference.get("motifs") or []) if str(item).strip()]
    if not source or not motifs:
        return base[:1400]
    folded = base.casefold()
    if source.casefold() in folded and all(motif.casefold() in folded for motif in motifs):
        return base[:1400]
    strength = str(reference.get("strength") or "subtle").strip().lower()
    intensity = "clear but original" if strength == "strong" else "subtle original"
    clause = f"{intensity} visual homage inspired by {source}, expressed through {', '.join(motifs)}"
    available = 1400 - len(clause) - 2
    if not base or available <= 0:
        return clause[:1400]
    return f"{base[:available].rstrip(' ,;')}, {clause}"


def _visual_director_backend_profile() -> tuple[str, str]:
    if image_backend_is_zimage():
        return (
            "Z-Image Turbo",
            "Write concise subject-first objective visual descriptions. Preserve subject, quantity, action, state, colors, and material identity; do not rely on a negative prompt.",
        )
    if image_backend_uses_semantic_prompt_contract():
        return (
            "modern flow image model (FLUX.2/Qwen-text-encoder style)",
            "Write concise subject-first objective visual descriptions with concrete shape, materials, and palette. Avoid legacy Stable Diffusion tag soup.",
        )
    return (
        "configured image backend",
        "Write concise final sprite descriptions with concrete shape, materials, palette, role, and composition.",
    )


def _merge_visual_director_palette(
    data: dict[str, Any],
    existing_palette: Any,
    proposed_palette: Any,
) -> tuple[list[str], str]:
    """Preserve explicit planner palette; otherwise let the art director decide.

    This uses provenance only. It does not inspect materials, parent types, item names,
    or decide how the parents should be fused. A fallback palette is context, not a
    hard visual rule; an explicitly authored planner palette is part of the authored
    item and therefore stays first.
    """
    existing = sanitize_visual_palette(existing_palette or [], limit=8)
    proposed = sanitize_visual_palette(proposed_palette or [], limit=8)
    debug = data.get("debug") if isinstance(data.get("debug"), dict) else {}
    source = str(debug.get("visualPaletteSource") or "")
    if source == "planner_authored":
        return sanitize_visual_palette(existing + proposed, limit=8), "planner_authored_first"
    if proposed:
        return proposed, "visual_director_authored"
    return existing, "fallback_preserved"


def attach_visual(data: dict[str, Any], a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any]) -> dict[str, Any]:
    visual = data.setdefault("visual", {})
    debug = data.setdefault("debug", {})
    tags = set(data.get("tags", [])) | tags_of(a) | tags_of(b)
    visual["requiredAnchors"] = list(dict.fromkeys(
        str(x).strip() for x in (visual.get("requiredAnchors") or []) if str(x).strip()
    ))[:10]
    if not isinstance(visual.get("parentVisualContext"), list):
        visual["parentVisualContext"] = required_anchors_from(ca, cb, tags)[:16]
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
        debug["visualPromptSource"] = "planner_authored"
    else:
        visual["imagePrompt"] = sanitize_image_prompt_background(build_image_prompt(data, visual))
        debug["visualPromptSource"] = "code_fallback"
        if isinstance(data.get("presentationGenome"), dict):
            pg = data["presentationGenome"]
            visual["imagePrompt"] += ", coherent with " + str((pg.get("heldSprite") or {}).get("silhouette", "item")) + " and " + str((pg.get("attackVisual") or {}).get("effect", "neutral")) + " attack visuals"
    visual.setdefault("spriteStatus", "prompt_only")
    return data

def build_image_prompt(data: dict[str, Any], visual: dict[str, Any]) -> str:
    anchors = [str(a) for a in visual.get("requiredAnchors", []) if str(a).strip()]
    parent_context = [str(a) for a in visual.get("parentVisualContext", []) if str(a).strip()]
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
        parts.append("author-required visible anchors: " + ", ".join(anchors[:8]))
    if parent_context:
        parts.append("nonbinding parent visual context: " + ", ".join(parent_context[:10]))
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
    if not USE_LLM:
        data.setdefault("debug", {})["visualDirectorStatus"] = "skipped_llm_disabled"
        return data
    if not VISUAL_DIRECTOR_LLM:
        data.setdefault("debug", {})["visualDirectorStatus"] = "skipped_director_disabled"
        return data
    if not is_llm_planner(data):
        data.setdefault("debug", {})["visualDirectorStatus"] = "skipped_non_llm_planner"
        return data
    if VISUAL_ASSET_MODE not in {"full", "all", "projectile", "visualpack", "assetpack"}:
        data.setdefault("debug", {})["visualDirectorStatus"] = "skipped_by_visual_asset_mode"
        return data
    content = ""
    model_name = ""
    transport_debug: dict[str, Any] = {}
    try:
        anime_opportunity = anime_reference_opportunity(data)
        anime_rule = (
            "This recipe has a rare optional anime-reference opportunity. You may decline it. "
            f"If used, animeReference.strength must not exceed {anime_opportunity}; name one source and use concrete visual motifs only. "
            "Keep the item original: no character portrait, copied logo, title text, or direct asset replica. Weave the homage into the relevant sprite prompts."
            if anime_opportunity in {"subtle", "strong"}
            else "Do not introduce named anime, manga, character, or franchise references for this recipe."
        )
        backend_name, backend_contract = _visual_director_backend_profile()
        payload = {
            "task": "Create a coherent pixel-art visual asset pack for this generated Terraria-like toy. Do not change gameplay stats.",
            "imageBackend": backend_name,
            "imageBackendContract": backend_contract,
            "rules": [
                "Return one JSON object matching the supplied schema; no markdown or analysis.",
                "Do not change gameplay, delivery, runtime families, counts, timing, or stats.",
                "The planner owns the visual fusion. Preserve its literal, attached, fused, disassembled, multi-part, or unusual topology; do not force or remove a parent object.",
                "Build role-separated assets. Item is the inventory/held object, projectile is one authored moving-body texture, impact is a momentary effect, child is one authored child body, and field is one authored persistent decal/rune/cloud body.",
                "Runtime shotCount, spread, and splitCount do not authorize rewriting the authored visual topology. Keep explicit bundles or multi-part bodies when authored.",
                "Use bakedAssets as the only asset-mode decision surface. Prompt text alone never requests a PNG.",
                "Use particle_vfx for dust, sparks, smoke, glints, simple trails, and short bursts; use baked_sprite only for a distinct body, decal, rune, cloud, or child entity that runtime can consume.",
                "Item icons and projectile bodies are isolated sprites on solid #ff00ff, not scenes, rooms, placement previews, characters, or UI.",
                "Keep the authored fantasy visible with concrete shape, proportions, materials, and foreground colors; avoid generic weapon/orb/bolt collapse.",
                "For itemIconPrompt, write one concrete itemSilhouetteContract for this exact generated object, without replacing it with a generic class label.",
                "Z-Image prompts are subject-first visual descriptions, not Stable Diffusion tag lists. No masterpiece/8K/meta labels.",
                "Write concise VFX hints with no code and no numeric particle counts.",
                anime_rule,
            ],
            "item": visual_director_context(data, a, b, ca, cb),
            "animeReferenceOpportunity": {
                "enabled": anime_opportunity in {"subtle", "strong"},
                "optional": True,
                "maximumStrength": anime_opportunity,
                "frequencyPolicy": "rare deterministic recipe opportunity; most recipes receive none",
            },
            "fieldGuide": {
                "styleGuide": "one shared authored art-direction sentence used by every role",
                "palette": "foreground named colors only",
                "itemSilhouetteContract": "exact proportions, readable parts, and near-miss silhouettes for the authored final item",
                "rolePrompts": "itemIconPrompt, projectileSpritePrompt, impactSpritePrompt, childSpritePrompt, fieldSpritePrompt",
                "bakedAssets": "per-role delivery mode/reason only: none, particle_vfx, reuse_item_sprite, or baked_sprite; role prompts above are canonical",
                "vfx": "concise vfxIntent/projectileVfx/impactVfx/childVfx/fieldVfx plus scale, rhythm, materials, and avoid notes",
                "lists": "animationPlan, assetDependencies, qualityNotes, vfxMaterialHints must remain JSON arrays",
                "negativePrompt": "one optional shared backend negative prompt; keep empty for Z-Image",
            },
        }
        if anime_opportunity in {"subtle", "strong"}:
            payload["fieldGuide"]["animeReference"] = (
                f"optional; strength subtle or strong but never above {anime_opportunity}; "
                "name one source and 1-3 concrete motifs"
            )
        model_name = resolve_llm_model()
        req = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": f"You direct pixel-art assets for {backend_name} in a Terraria-like generated-item mod. Write concise final visual descriptions, not legacy SD tag recipes. Preserve authored subject, count, action, state, colors, and materials. Do not add unauthored glow, magic, energy, child motes, or material effects. Return one JSON object."},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))},
            ],
            "temperature": env_float("INFINI_VISUAL_DIRECTOR_TEMPERATURE", 0.42, lo=0.0, hi=1.2),
            "max_tokens": visual_director_max_tokens(),
            "response_format": llm_json_response_format(
                "infini_visual_director",
                schema=visual_kit_response_schema(),
                strict=True,
            ),
        }
        raw = llm_chat_json(req, timeout=env_int("INFINI_LLM_TIMEOUT", 95))
        transport_debug = raw.get("_debug") if isinstance(raw, dict) and isinstance(raw.get("_debug"), dict) else {}
        content = raw["choices"][0]["message"]["content"]
        obj = parse_first_valid_llm_json(content)
        if not isinstance(obj, dict):
            raise ValueError("visual director returned a non-object JSON value")
        boundary_repairs: list[str] = []
        if isinstance(obj.get("visualKit"), dict):
            kit = copy.deepcopy(obj["visualKit"])
        elif "visualKit" not in obj:
            # Backward-compatible wrapper repair only. Values are preserved exactly;
            # the strict VisualKit boundary still validates every field below.
            kit = copy.deepcopy(obj)
            boundary_repairs.append("root_object_wrapped_as_visualKit")
        else:
            raise ValueError("visual director visualKit must be a JSON object")
        # Strict shape validation also performs bounded legacy migrations such as
        # singleton string lists and bakedAssets.<role>.prompt -> canonical role prompt.
        # It never invents visual content or chooses parent fusion.
        kit = canonical_visual_kit_view(kit, repairs=boundary_repairs)

        for prompt_key, role_hint in [
            ("itemIconPrompt", "item"),
            ("projectileSpritePrompt", "projectile"),
            ("childSpritePrompt", "child"),
            ("impactSpritePrompt", "impact"),
            ("fieldSpritePrompt", "field"),
        ]:
            if kit.get(prompt_key):
                cleaned = strip_conflicting_sprite_prompt_bits(kit[prompt_key])
                cleaned = sanitize_projectile_family_prompt(data, role_hint, cleaned)
                cleaned = role_visual_prompt_guard(role_hint, cleaned, data)
                kit[prompt_key] = cleaned[:1400] if cleaned else ""

        for text_key in [
            "styleGuide", "silhouetteSummary", "itemSilhouetteContract", "vfxIntent",
            "projectileVfx", "impactVfx", "childVfx", "fieldVfx", "vfxAvoid",
        ]:
            if kit.get(text_key):
                role_hint = "projectile" if "projectile" in text_key.lower() else "item"
                kit[text_key] = sanitize_projectile_family_prompt(data, role_hint, kit[text_key])[:700]

        anime_reference = _sanitize_anime_reference(kit.get("animeReference"), anime_opportunity)
        if anime_reference:
            kit["animeReference"] = anime_reference
            if kit.get("itemIconPrompt"):
                kit["itemIconPrompt"] = _append_anime_reference_to_prompt(
                    kit["itemIconPrompt"],
                    anime_reference,
                )
        else:
            kit.pop("animeReference", None)

        # Sanitizers may shorten strings but must not change the contract shape.
        # Canonicalization also removes legacy duplicate bakedAssets role prompts.
        kit = canonical_visual_kit_view(kit)
        all_kit_errors = visual_kit_usefulness_errors(kit) + visual_kit_projection_errors(kit, data)
        if all_kit_errors:
            raise ValueError("visual director output is structurally valid but unusable: " + "; ".join(all_kit_errors))

        # Full transaction: Visual Director output is projected into a deep copy and
        # committed only after every palette/gate/mapping step succeeds. A late error
        # must not leave half-updated visual, attack, debug, or visualKit state behind.
        working = copy.deepcopy(data)
        working_debug = working.setdefault("debug", {})
        working_debug.pop("visualDirectorError", None)
        working["visualKit"] = kit
        working_debug["visualDirectorRawOutput"] = content[:10000]
        if boundary_repairs:
            working_debug["visualDirectorBoundaryRepairs"] = boundary_repairs
        else:
            working_debug.pop("visualDirectorBoundaryRepairs", None)
        working_debug["visualDirectorModel"] = model_name
        working_debug["visualDirectorStatus"] = "validated_and_applied"
        working_debug["visualDirectorContextChars"] = len(json.dumps(payload.get("item") or {}, ensure_ascii=False))
        if transport_debug:
            working_debug["visualDirectorTransport"] = transport_debug

        visual = working.setdefault("visual", {})
        attack = working.setdefault("attack", {})
        if kit.get("palette"):
            cleaned_palette, palette_policy = _merge_visual_director_palette(
                working,
                visual.get("palette"),
                kit.get("palette"),
            )
            if cleaned_palette:
                kit["palette"] = cleaned_palette
                visual["palette"] = cleaned_palette
                working_debug["visualDirectorPalettePolicy"] = palette_policy
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
        if anime_reference and visual.get("imagePrompt"):
            visual["imagePrompt"] = _append_anime_reference_to_prompt(
                visual["imagePrompt"],
                anime_reference,
            )

        if kit.get("styleGuide"):
            visual["styleGuide"] = str(kit.get("styleGuide"))[:700]
        if kit.get("silhouetteSummary"):
            visual["silhouetteSummary"] = str(kit.get("silhouetteSummary"))[:700]
        if kit.get("itemSilhouetteContract"):
            visual["itemSilhouetteContract"] = str(kit.get("itemSilhouetteContract"))[:700]

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

        working["attack"] = attack
        working["visual"] = visual
        data.clear()
        data.update(working)
    except Exception as e:
        # No projection touched the original data unless the transaction completed.
        debug = data.setdefault("debug", {})
        debug["visualDirectorError"] = repr(e)
        debug["visualDirectorStatus"] = "rejected_fallback_to_existing_visual"
        if model_name:
            debug["visualDirectorModel"] = model_name
        if content:
            debug["visualDirectorRejectedRawOutput"] = content[:10000]
        log_event("warn", "visual director failed", {"error": repr(e), "trace": traceback.format_exc()})
    return data
