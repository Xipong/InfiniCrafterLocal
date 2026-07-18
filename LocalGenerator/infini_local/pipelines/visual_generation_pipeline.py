from __future__ import annotations

import copy
import json
import traceback
from typing import Any

from infini_local.core.boundary_models import canonical_visual_kit_view

from infini_local.core.env_utils import env_float, env_int
from infini_local.core.llm_config import USE_LLM
from infini_local.core.llm_json_tools import parse_first_valid_llm_json
from infini_local.core.llm_stage_messages import agent_handoff, stage_chat_message
from infini_local.pipelines.combine_genome_contract import is_llm_planner
from infini_local.pipelines.combine_validation import _stringish
from infini_local.pipelines.author_item_contract import (
    project_provider_nullable_optionals_to_local,
)
from infini_local.pipelines.item_power_knowledge import tags_of
from infini_local.pipelines.llm_transport import (
    active_llm_provider,
    apply_llm_common_options,
    llm_chat_json,
    llm_json_response_format,
    resolve_llm_model,
    visual_director_max_tokens,
)
from infini_local.pipelines.pipeline_visual_config import VISUAL_ASSET_MODE, VISUAL_DIRECTOR_LLM
from infini_local.pipelines.result_identity_policy import required_anchors_from

from infini_local.pipelines.visual_prompt_contracts import (
    asset_negative_prompt,
    image_backend_is_zimage,
    image_backend_uses_semantic_prompt_contract,
    sprite_background_positive_clause,
    role_visual_prompt_guard,
    role_contract_prompt_clause,
)

from infini_local.pipelines.visual_director_contract import (
    visual_director_output_contract,
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
from infini_local.storage.trace_runtime import log_event, trace_event


def _accepted_visual_intent(data: dict[str, Any]) -> dict[str, Any]:
    runtime_plan_value = data.get("runtimePlan")
    if not isinstance(runtime_plan_value, dict):
        return {}
    visual_intent_value = runtime_plan_value.get("visualIntent")
    return visual_intent_value if isinstance(visual_intent_value, dict) else {}


def anime_reference_opportunity(data: dict[str, Any]) -> str:
    """Allow anime references only when an upstream visual contract explicitly asks."""
    visual_intent = _accepted_visual_intent(data)
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    for authored in (visual_intent.get("animeReference"), visual.get("animeReference")):
        if isinstance(authored, dict):
            strength = str(authored.get("strength") or "").strip().lower()
            if strength in {"subtle", "strong"}:
                return strength
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
            "Write one coherent 40-100 word subject-first description. Build the physical topology before style: explicit class and count, global silhouette and view, functional parts joined with relationship verbs, then materials, localized decoration and light, pixel-art finish, and background. Avoid legacy Stable Diffusion tag soup.",
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
    visual_intent = _accepted_visual_intent(data)
    authored = sanitize_visual_palette(visual_intent.get("palette") or [], limit=8)
    if authored:
        return sanitize_visual_palette(authored + proposed, limit=8), "planner_authored_first"
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
    # A missing palette stays unspecified.  The Visual Director may author one from
    # its physical evidence; code must not infer colors from category/name/tag prose.
    visual["palette"] = visual.get("palette") or []
    visual["style"] = "terraria_item_sprite"
    visual.setdefault("preferredCanvasSize", 32)
    visual.setdefault("inventoryScale", 1.0)
    visual.setdefault("worldScale", 1.0)
    visual.setdefault("drawOffsetX", 0)
    visual.setdefault("drawOffsetY", 0)
    visual["negativePrompt"] = asset_negative_prompt("item")
    llm_authored_product = is_llm_planner(data)
    visual_intent = _accepted_visual_intent(data)
    planner_item_prompt = str(visual_intent.get("item") or "").strip()
    if planner_item_prompt and llm_authored_product:
        visual["imagePrompt"] = sanitize_image_prompt_background(planner_item_prompt)
        debug["visualPromptSource"] = "planner_authored"
    elif llm_authored_product:
        visual.pop("imagePrompt", None)
        visual.pop("itemPrompt", None)
        debug["visualPromptSource"] = "awaiting_visual_director"
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
    canvas = int(visual.get("preferredCanvasSize") or 32)
    parts = [
        "Terraria-like pixel-art inventory item sprite",
        sprite_background_positive_clause(),
        "show the authored physical item role and arrangement",
        role_contract_prompt_clause("item", canvas),
    ]
    if anchors:
        parts.append("author-required visible anchors: " + ", ".join(anchors[:8]))
    if parent_context:
        parts.append("nonbinding parent visual context: " + ", ".join(parent_context[:10]))
    if palette:
        parts.append("palette: " + ", ".join(palette[:6]))
    if visual.get("topology"):
        parts.append("authored topology: " + str(visual["topology"]))
    if visual.get("partCountMin") is not None and visual.get("partCountMax") is not None:
        parts.append(
            "authored significant body count: "
            + f"{int(visual['partCountMin'])}-{int(visual['partCountMax'])}"
        )
    if visual.get("parts"):
        parts.append("authored parts: " + ", ".join(str(part) for part in visual["parts"][:8]))
    if visual.get("arrangement"):
        parts.append("authored arrangement: " + str(visual["arrangement"]))
    parts.append("no scene, no character, no text")
    return ", ".join(parts)


def _validated_visual_director_kit(
    content: str,
    data: dict[str, Any],
    anime_opportunity: str,
) -> tuple[dict[str, Any], list[str], dict[str, Any] | None]:
    obj = parse_first_valid_llm_json(content)
    if not isinstance(obj, dict):
        raise ValueError("visual director returned a non-object JSON value")
    obj = project_provider_nullable_optionals_to_local(
        obj,
        visual_kit_response_schema(),
    )
    boundary_repairs: list[str] = []
    if not isinstance(obj.get("visualKit"), dict):
        raise ValueError("visual director visualKit must be a JSON object")
    kit = copy.deepcopy(obj["visualKit"])
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
            if role_hint != "item" or not image_backend_uses_semantic_prompt_contract():
                cleaned = role_visual_prompt_guard(role_hint, cleaned, data)
            kit[prompt_key] = cleaned[:1400] if cleaned else ""

    for text_key in [
        "styleGuide", "silhouetteSummary", "itemSilhouetteContract", "vfxIntent",
        "projectileVfx", "impactVfx", "childVfx", "fieldVfx", "vfxAvoid",
    ]:
        if kit.get(text_key):
            kit[text_key] = str(kit[text_key])[:700]

    requested_anime_reference = kit.get("animeReference")
    anime_reference = _sanitize_anime_reference(requested_anime_reference, anime_opportunity)
    if requested_anime_reference is not None and anime_reference is None:
        raise ValueError(
            "visualKit.animeReference was not authorized by the authored visual intent "
            "or exceeded its permitted strength"
        )
    if anime_reference:
        kit["animeReference"] = anime_reference
        if kit.get("itemIconPrompt"):
            kit["itemIconPrompt"] = _append_anime_reference_to_prompt(
                kit["itemIconPrompt"],
                anime_reference,
            )
    else:
        kit.pop("animeReference", None)

    kit = canonical_visual_kit_view(kit)
    all_kit_errors = visual_kit_usefulness_errors(kit) + visual_kit_projection_errors(kit, data)
    if all_kit_errors:
        raise ValueError("visual director output is structurally valid but unusable: " + "; ".join(all_kit_errors))
    return kit, boundary_repairs, anime_reference


def apply_visual_director(data: dict[str, Any], a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any]) -> dict[str, Any]:
    """v0.3.9: LLM art director pass.

    The planner writes the toy. This pass turns that toy into a sprite asset pack:
    item icon, projectile, child/echo, impact and field/trap. It is deliberately
    separate from balance so the art prompt is not rebuilt into generic bolts.
    """
    llm_authored_product = is_llm_planner(data)
    if llm_authored_product:
        # A prior/cache VisualKit is not evidence that this Director transaction
        # succeeded. Only this invocation may install the accepted kit.
        data.pop("visualKit", None)
    if not USE_LLM:
        data.setdefault("debug", {})["visualDirectorStatus"] = "skipped_llm_disabled"
        return data
    if not VISUAL_DIRECTOR_LLM:
        data.setdefault("debug", {})["visualDirectorStatus"] = "skipped_director_disabled"
        return data
    if not llm_authored_product:
        data.setdefault("debug", {})["visualDirectorStatus"] = "skipped_non_llm_planner"
        return data
    if VISUAL_ASSET_MODE not in {"full", "all", "projectile", "visualpack", "assetpack"}:
        data.setdefault("debug", {})["visualDirectorStatus"] = "skipped_by_visual_asset_mode"
        return data
    content = ""
    model_name = ""
    transport_debug: dict[str, Any] = {}
    message_mode = ""
    visual_director_retry_count = 0
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
                'The root object must contain exactly one key named "visualKit". Return exactly {"visualKit": {...}}; never emit VisualKit fields directly at the root.',
                "Return one JSON object matching the supplied schema; no markdown or analysis.",
                "Do not change gameplay, delivery, runtime families, counts, timing, or stats.",
                "The planner's authored final-item topology is authoritative. Preserve its physical class, subject count, continuous bodies, attachments, and intentional separations exactly as authored.",
                "Build role-separated assets. Item is the inventory/held object, projectile is one authored moving-body texture, impact is a momentary effect, child is one authored child body, and field is one authored persistent decal/rune/cloud body.",
                "Runtime shotCount, spread, and splitCount do not authorize rewriting the authored visual topology. Keep explicit bundles or multi-part bodies when authored.",
                "Use bakedAssets as the only asset-mode decision surface. Prompt text alone never requests a PNG.",
                "Use particle_vfx for dust, sparks, smoke, glints, simple trails, and short bursts; use baked_sprite only for a distinct body, decal, rune, cloud, or child entity that runtime can consume.",
                "Item icons and projectile bodies are isolated sprites on solid #ff00ff, not scenes, rooms, placement previews, characters, or UI.",
                "Keep the authored fantasy visible with concrete shape, proportions, materials, and foreground colors; avoid generic weapon/orb/bolt collapse.",
                "For itemIconPrompt, write one coherent natural-language paragraph in this order: physical class and count; global silhouette and one view; functional parts and how they connect using explicit relationship verbs; materials and base colors; compact decoration at an exact location; restrained local lighting; pixel-art style and background. Express topology as connected geometry, never as a loose list of nouns.",
                "Decorative motifs remain localized surface or inset details inside the authored physical structure.",
                "Anime homage and decorative interface motifs must remain localized as engraved, inset, or painted surface details on the item body; never author floating UI, HUD overlays, text, or detached glyph panels.",
                "negativePrompt must not contradict allowed positive subject, material, color, or localized motif decisions; remove an invalid positive role motif rather than weakening the item/projectile no-UI guard.",
                "Z-Image prompts are subject-first visual descriptions, not Stable Diffusion tag lists. No masterpiece/8K/meta labels.",
                "Write concise VFX hints with no code and no numeric particle counts.",
                anime_rule,
            ],
            "item": visual_director_context(data, a, b, ca, cb),
            "animeReferenceOpportunity": {
                "enabled": anime_opportunity in {"subtle", "strong"},
                "optional": True,
                "maximumStrength": anime_opportunity,
                "frequencyPolicy": "enabled only by explicit authored visual intent; most recipes receive none",
            },
            "fieldGuide": {
                "styleGuide": "one shared authored art-direction sentence used by every role",
                "palette": "foreground named colors only",
                "itemSilhouetteContract": "one compact positive sentence stating global silhouette, part count, proportions, attachment points, and which bodies are continuous or intentionally separate",
                "rolePrompts": "itemIconPrompt, projectileSpritePrompt, impactSpritePrompt, childSpritePrompt, fieldSpritePrompt",
                "bakedAssets": "exact JSON object of role objects, never an array and never a string mode. Example: {\"projectile\":{\"mode\":\"baked_sprite\",\"reason\":\"distinct moving body\",\"distinctFromItem\":true},\"impact\":{\"mode\":\"particle_vfx\",\"reason\":\"momentary sparks\"}}. reuse_item_sprite and distinctFromItem are projectile-only; impact, child, and field use none, particle_vfx, or baked_sprite. Role prompts above are canonical",
                "vfx": "concise vfxIntent/projectileVfx/impactVfx/childVfx/fieldVfx plus scale, rhythm, materials, and avoid notes",
                "lists": "animationPlan, assetDependencies, qualityNotes, vfxMaterialHints must remain JSON arrays",
                "negativePrompt": "one optional shared backend negative prompt; keep empty for Z-Image",
            },
            "outputContract": visual_director_output_contract(),
        }
        if anime_opportunity in {"subtle", "strong"}:
            payload["fieldGuide"]["animeReference"] = (
                f"optional; strength subtle or strong but never above {anime_opportunity}; "
                "name one source and 1-3 concrete motifs"
            )
        payload["agentHandoff"] = agent_handoff(
            previous_speaker="pipeline_orchestrator",
            current_speaker="visual_director_context",
            next_speaker="visual_director",
            cause_by="visual_asset_prompt_authoring",
            artifact_source="item",
        )
        model_name = resolve_llm_model()
        visual_system = (
            f"You direct pixel-art assets for {backend_name} in a Terraria-like generated-item mod. "
            "The visual_director_context payload.item is the authoritative current accepted item truth. "
            "Write coherent subject-first visual descriptions, not legacy SD tag recipes. Establish physical class, count, silhouette, view, and connected functional parts before materials, decoration, light, style, and background. "
            "Preserve authored subject, state, colors, materials, and topology. Use only authored glow, magic, energy, child motes, and material effects. "
            'The root object must contain exactly one key named "visualKit". Return exactly {"visualKit": {...}} and never place itemIconPrompt, bakedAssets, or other VisualKit fields at the root.'
        )
        visual_user_content = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        messages = [
            stage_chat_message("system", "visual_director_contract", visual_system),
            stage_chat_message("user", "visual_director_context", visual_user_content),
        ]
        message_mode = "authoritative_stage_dossier_v31"
        req = {
            "model": model_name,
            "messages": messages,
            "temperature": env_float("INFINI_VISUAL_DIRECTOR_TEMPERATURE", 0.42, lo=0.0, hi=1.2),
            "max_tokens": visual_director_max_tokens(),
            "response_format": llm_json_response_format(
                "infini_visual_director",
                schema=visual_kit_response_schema(),
                strict=True,
            ),
        }
        req = apply_llm_common_options(
            req,
            model_name=model_name,
            default_max_tokens=visual_director_max_tokens(),
        )
        trace_event(
            "prompt",
            "LLM:visual_director",
            "Visual director request",
            {
                "provider": active_llm_provider(),
                "model": model_name,
                "temperature": req.get("temperature"),
                "maxTokens": req.get("max_tokens"),
                "reasoning": req.get("reasoning"),
                "reasoningEffort": req.get("reasoning_effort"),
                "messageMode": message_mode,
                "messages": [
                    {"role": message.get("role"), "name": message.get("name"), "chars": len(str(message.get("content") or ""))}
                    for message in req.get("messages") or []
                    if isinstance(message, dict)
                ],
            },
            prompt=req.get("messages"),
        )
        raw = llm_chat_json(req, timeout=env_int("INFINI_LLM_TIMEOUT", 95))
        transport_debug = raw.get("_debug") if isinstance(raw, dict) and isinstance(raw.get("_debug"), dict) else {}
        content = raw["choices"][0]["message"]["content"]
        trace_event(
            "response",
            "LLM:visual_director",
            "Visual director response",
            {"model": model_name, "chars": len(str(content)), "transport": transport_debug},
            response=content,
        )
        try:
            kit, boundary_repairs, anime_reference = _validated_visual_director_kit(
                str(content), data, anime_opportunity
            )
        except Exception as first_contract_error:
            visual_director_retry_count = 1
            correction_payload = {
                "task": "Replace your invalid Visual Director response with one object matching requiredSchema exactly.",
                "validationError": repr(first_contract_error),
                "requiredSchema": visual_kit_response_schema(),
                "rules": [
                    "Return {\"visualKit\": {...}} only.",
                    "bakedAssets is an object, never an array.",
                    "Each bakedAssets role is an object with mode/reason/distinctFromItem fields; never a mode string or alias.",
                    "Do not add item or vfx roles inside bakedAssets.",
                    "Do not change the item design; repair only the contract shape.",
                ],
            }
            retry_req = copy.deepcopy(req)
            retry_req["messages"] = [
                *messages,
                stage_chat_message("assistant", "visual_director", str(content)[:10000]),
                stage_chat_message(
                    "user",
                    "visual_director_context",
                    json.dumps(correction_payload, ensure_ascii=False, separators=(",", ":")),
                ),
            ]
            retry_req["temperature"] = min(float(req.get("temperature") or 0.0), 0.2)
            trace_event(
                "prompt",
                "LLM:visual_director_retry",
                "Visual director scoped structural repair request",
                {"provider": active_llm_provider(), "model": model_name, "attempt": 1},
                prompt=retry_req.get("messages"),
            )
            retry_raw = llm_chat_json(retry_req, timeout=env_int("INFINI_LLM_TIMEOUT", 95))
            retry_transport_debug = retry_raw.get("_debug") if isinstance(retry_raw, dict) else None
            transport_debug = retry_transport_debug if isinstance(retry_transport_debug, dict) else {}
            content = retry_raw["choices"][0]["message"]["content"]
            trace_event(
                "response",
                "LLM:visual_director_retry",
                "Visual director scoped structural repair response",
                {"model": model_name, "chars": len(str(content)), "attempt": 1, "transport": transport_debug},
                response=content,
            )
            kit, boundary_repairs, anime_reference = _validated_visual_director_kit(
                str(content), data, anime_opportunity
            )

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
        working_debug["visualDirectorRetryCount"] = visual_director_retry_count
        working_debug["visualDirectorMessageMode"] = message_mode
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
        visual_candidate = data.get("visual")
        visual_existing: dict[str, Any] = visual_candidate if isinstance(visual_candidate, dict) else {}
        attack_candidate = data.get("attack")
        attack_existing: dict[str, Any] = attack_candidate if isinstance(attack_candidate, dict) else {}
        fallback_prompts = {
            "item": str(visual_existing.get("imagePrompt") or ""),
            "projectile": str(
                visual_existing.get("projectileImagePrompt")
                or attack_existing.get("projectileSpritePrompt")
                or ""
            ),
            "impact": str(
                visual_existing.get("impactImagePrompt")
                or attack_existing.get("impactSpritePrompt")
                or ""
            ),
            "child": str(
                visual_existing.get("childImagePrompt")
                or attack_existing.get("childSpritePrompt")
                or ""
            ),
            "field": str(
                visual_existing.get("fieldImagePrompt")
                or attack_existing.get("fieldSpritePrompt")
                or ""
            ),
        }
        debug["visualDirectorError"] = repr(e)
        debug["visualDirectorStatus"] = "visual_director_degraded"
        debug["visualDirectorRetryCount"] = visual_director_retry_count
        debug["visualDirectorFallbackPrompts"] = fallback_prompts
        if model_name:
            debug["visualDirectorModel"] = model_name
        if content:
            debug["visualDirectorRejectedRawOutput"] = content[:10000]
        trace_event(
            "error",
            "LLM:visual_director",
            "Visual director degraded to existing authored prompts",
            {"model": model_name, "retryCount": visual_director_retry_count},
            prompt=fallback_prompts,
            error=repr(e),
        )
        log_event("warn", "visual director failed", {"error": repr(e), "trace": traceback.format_exc()})
    return data
