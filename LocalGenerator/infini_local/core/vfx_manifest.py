from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

from infini_local.core.effect_catalog import normalize_attack_pattern
from infini_local.core.item_identity_tools import (
    _stringish,
    dict_get_ci,
    fingerprint_of,
    generation_depth,
    generated_data_of,
    item_bool,
    item_field,
    item_identity,
    item_num,
    name_of,
    slug,
    stable_hash,
    tags_of,
)
from infini_local.core.vfx_composition import (
    _VFX_PARTICLE_ADDRESS_CATALOG,
    _vfx_add_procedural_slots,
    _vfx_arbitrate_slots,
    _vfx_authored_cue_event,
    _vfx_authored_cue_raw_slots,
    _vfx_available_roles,
    _vfx_baked_clip_meta,
    _vfx_baked_command_count,
    _vfx_bake_slot_commands,
    _vfx_blend_runner_up_slots,
    _vfx_budget_for_recipe,
    _vfx_canonical_particle_address,
    _vfx_color_hex,
    _vfx_compile_slot,
    _vfx_compute_effect_magnitude,
    _vfx_default_anchor,
    _vfx_default_backend,
    _vfx_default_importance,
    _vfx_default_signature_weight,
    _vfx_default_visual_cost,
    _vfx_demote_blended_raw_slot,
    _vfx_event_group,
    _vfx_event_stage,
    _vfx_family_key,
    _vfx_infer_channel,
    _vfx_infer_emission_mode,
    _vfx_infer_lane,
    _vfx_lerp_range,
    _vfx_magnitude_class,
    _vfx_manifest_from_parent_item,
    _vfx_max_channel_count,
    _vfx_motif_from_data,
    _vfx_mundane_duplicate_profile,
    _vfx_parent_effect_profile,
    _vfx_parent_effect_recipe_bonus,
    _vfx_parent_effect_tag_set,
    _vfx_parent_inherited_raw_slots,
    _vfx_parent_profile_from_item,
    _vfx_particle_address_catalog,
    _vfx_pick,
    _vfx_playback_mode_for_recipe,
    _vfx_procedural_raw_slot_pool,
    _vfx_resolve_particle_system_id,
    _vfx_renderer_family,
    _vfx_renderer_kind,
    _vfx_runtime_plan_direct_manifest,
    _vfx_score_number,
    _vfx_seed_int,
    _vfx_should_bake_slot,
    _vfx_slot_score,
    _vfx_slot_similarity_key,
    _vfx_transform_parent_slot_for_child,
    _vfx_trim_mundane_slots,
    _vfx_unit,
    _vfx_words,
)
from infini_local.core.vfx_director_context import (
    _vfx_clean_tag,
    _vfx_collect_legacy_hint_tags,
    _vfx_director_name_tokens,
    _vfx_director_runtime_auto_features,
    _vfx_director_tag_packet,
    _vfx_generated_authored_tags,
    _vfx_list_strings,
    _vfx_semantic_expansion_for_director,
    _vfx_weak_hint_confidence,
    build_vfx_director_weak_hints,
)
from infini_local.core.vfx_director_prompt import (
    _vfx_compact_child_for_director,
    _vfx_compact_item_for_director,
    _vfx_planner_continuation_from_item,
    _vfx_text_for_name_bank,
    build_vfx_director_continuation_messages,
    build_vfx_director_continuation_payload,
    build_vfx_director_prompt,
    get_vfx_effect_name_bank,
    vfx_director_name_bank,
)
from infini_local.core.vfx_director_contract import (
    _vfx_director_check_enum,
    _vfx_director_check_number,
    _vfx_director_enum,
    _vfx_director_enum_required,
    _vfx_director_error,
    _vfx_director_error_fields,
    _vfx_director_number_required,
    _vfx_director_repair_prompt,
    _vfx_director_validation_report,
    _vfx_director_warning,
    _vfx_float,
    _vfx_int,
    _vfx_particle_id_is_explicit,
    vfx_director_surface,
)
from infini_local.core.vfx_projectile_profile import (
    effective_projectile_profile_of,
    proj_bool,
    proj_num,
    projectile_behavior_tags,
    projectile_profile_of,
    source_weapon_profile,
)
from infini_local.core.vfx_recipe_library import (
    _vfx_deep_merge,
    _vfx_expand_recipe_macros,
    _vfx_expand_slot_macro,
    compact_vfx_macro_card,
    get_vfx_recipes,
)
from infini_local.core.vfx_lint_timeline import (
    VFX_KNOWN_BACKENDS,
    VFX_KNOWN_CHANNELS,
    VFX_KNOWN_EMISSION_MODES,
    VFX_KNOWN_EVENTS,
    VFX_KNOWN_LANES,
    VFX_KNOWN_RENDERERS,
    VFX_KNOWN_ROLES,
    VFX_MAGNITUDE_CLASSES,
    _vfx_layer_kind_for_renderer,
    _vfx_lint_recipe,
    _vfx_lint_slot,
    _vfx_slot_cost_estimate,
    _vfx_slot_value_range_ok,
    _vfx_timeline_from_manifest,
    vfx_manifest_effect_stack,
)
from infini_local.core.vfx_manifest_config import (
    DATA_DIR,
    ROOT,
    VFX_EFFECT_NAME_BANK_MAX_CARDS,
    VFX_EFFECT_NAME_BANK_MAX_NAMES,
    VFX_EFFECT_NAME_BANK_PATH,
    VFX_EMERGENCY_MAX_DRAW_CALLS,
    VFX_EMERGENCY_MAX_PARTICLES_PER_TICK,
    VFX_EMERGENCY_MAX_PARTICLES_TOTAL,
    VFX_LLM_DIRECTOR_ENABLED,
    VFX_LLM_DIRECTOR_MAX_SLOTS,
    VFX_LLM_DIRECTOR_MAX_TOKENS,
    VFX_LLM_DIRECTOR_REPAIR_ATTEMPTS,
    VFX_LLM_DIRECTOR_TEMPERATURE,
    VFX_LLM_DIRECTOR_TIMEOUT,
    VFX_LLM_WEAK_HINTS_CONFIDENCE_CAP,
    VFX_LLM_WEAK_HINTS_ENABLED,
    VFX_LLM_WEAK_HINTS_MAX,
    VFX_MAGNITUDE_JITTER,
    VFX_MORPH_LIBRARY,
    VFX_MORPH_RECIPES,
    VFX_MORPH_RECIPES_RAW,
    VFX_MUNDANE_DUPLICATE_GUARD,
    VFX_MUNDANE_MAX_SLOTS,
    VFX_PARENT_EFFECT_INHERITANCE,
    VFX_PARENT_EFFECT_MAX_INHERITED_SLOTS,
    VFX_PARENT_EFFECT_STRONG_THRESHOLD,
    VFX_PARENT_EFFECT_WEIGHT,
    VFX_PROCEDURAL_BLEND_CANDIDATES,
    VFX_PROCEDURAL_CHANCE,
    VFX_PROCEDURAL_COMPOSE,
    VFX_PROCEDURAL_MAX_EXTRA_SLOTS,
    VFX_RECIPE_BLEND_ENABLED,
    VFX_RENDER_QUALITY,
    VFX_RUNTIME_INTENT_FIRST,
    VFX_SELECTOR_DEBUG,
    VFX_SELECTOR_ENABLED,
    VFX_SELECTOR_HINT_WEIGHT,
    VFX_SELECTOR_JITTER,
    VFX_SELECTOR_NOVELTY_WEIGHT,
    VFX_SELECTOR_TOP,
    VFX_SLOT_MACRO_LIBRARY,
    VFX_SLOT_MACROS,
    load_json_file,
)


# AGENT MAP: Python VFX manifest authoring/normalization contract.
# Public facade for VFX manifest assembly. Config/data/env ownership lives in
# vfx_manifest_config.py; optional LLM Director context helpers live in
# vfx_director_context.py. Keep gameplay out of motif/effect prose; combat
# behavior belongs in explicit runtime fields compiled by the runtime_authoring package.


# VFX config constants are imported from vfx_manifest_config.py. Recipe macros
# are imported from vfx_recipe_library.py and still expand lazily there.




# VFX Director prompt/name-bank helpers live in vfx_director_prompt.py.

def _vfx_validate_director_output(raw: dict[str, Any], data: dict[str, Any], recipe_key_value: str, parent_a: dict[str, Any] | None = None, parent_b: dict[str, Any] | None = None) -> dict[str, Any] | None:
    report = _vfx_director_validation_report(raw)
    if not report.get("valid"):
        return None
    if not isinstance(raw, dict):
        return None
    surface = vfx_director_surface()
    raw_slots = raw.get("slots")
    if not isinstance(raw_slots, list) or not raw_slots:
        return None
    max_slots = max(2, min(8, VFX_LLM_DIRECTOR_MAX_SLOTS))
    raw_slots = [s for s in raw_slots if isinstance(s, dict)][:max_slots]
    if not raw_slots:
        return None

    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    pattern = normalize_attack_pattern(attack.get("pattern") or attack.get("attackPattern") or "basic")
    power = float(attack.get("powerBudget") or data.get("gameplay", {}).get("powerBudget") or 1.0) if isinstance(data.get("gameplay"), dict) else float(attack.get("powerBudget") or 1.0)
    seed = _vfx_seed_int(recipe_key_value, data.get("id"), "llm_vfx_director")
    if "effectMagnitude" not in raw:
        return None
    try:
        effect_magnitude = float(raw.get("effectMagnitude"))
    except Exception:
        return None
    if not math.isfinite(effect_magnitude) or effect_magnitude < 0.0 or effect_magnitude > 1.0:
        return None
    budget_class = str(raw.get("visualBudgetClass") or "").strip()
    if budget_class not in {"tiny", "small", "normal", "large", "signature"}:
        return None
    budget = _vfx_budget_for_recipe({"id": "llm_vfx_director", "cost": "medium"}, power, seed, data)
    budget["effectMagnitude"] = effect_magnitude
    budget["visualBudgetClass"] = budget_class

    compiled_raw: list[dict[str, Any]] = []
    explicit_particle_count = 0
    for i, slot in enumerate(raw_slots):
        if "bakedCommands" in slot:
            return None

        # Strict Director contract: if Gemma gives an invalid/missing enum or out-of-range numeric
        # field, reject the Director manifest and let the deterministic VFX pipeline take over.
        # We do not silently replace bad enum values with inferred defaults here.
        rk = _vfx_director_enum_required(slot, "rendererKind", surface["rendererKind"])
        if not rk and "renderer" in slot:
            # compatibility: accept renderer only when it is already a canonical rendererKind value.
            rk = _vfx_director_enum(slot.get("renderer"), surface["rendererKind"])
        ev = _vfx_director_enum_required(slot, "event", surface["events"])
        backend = _vfx_director_enum_required(slot, "backend", surface["backend"])
        texture_role = _vfx_director_enum_required(slot, "textureRole", surface["textureRole"])
        particle_role = _vfx_director_enum_required(slot, "particleRole", surface["particleRole"])
        anchor = _vfx_director_enum_required(slot, "anchor", surface["anchor"])
        channel = _vfx_director_enum_required(slot, "channel", surface["channel"])
        lane = _vfx_director_enum_required(slot, "lane", surface["lane"])
        emission_mode = _vfx_director_enum_required(slot, "emissionMode", surface["emissionMode"])
        blend = _vfx_director_enum_required(slot, "blend", surface["blend"])
        particle_system_id = _vfx_director_enum_required(slot, "particleSystemId", surface["particleSystemId"])
        if not all([rk, ev, backend, texture_role, particle_role, anchor, channel, lane, emission_mode, blend, particle_system_id]):
            return None

        scale = _vfx_director_number_required(slot, "scale", 0.15, 5.0)
        density = _vfx_director_number_required(slot, "density", 0.0, 1.0)
        duration = _vfx_director_number_required(slot, "duration", 3, 120, integer=True)
        alpha = _vfx_director_number_required(slot, "alpha", 0.0, 1.0)
        spread = _vfx_director_number_required(slot, "spread", 0.0, 2.0)
        jitter = _vfx_director_number_required(slot, "jitter", 0.0, 1.5)
        budget_weight = _vfx_director_number_required(slot, "budgetWeight", 0.1, 4.0)
        signature_weight = _vfx_director_number_required(slot, "signatureWeight", 0.0, 1.0)
        visual_cost = _vfx_director_number_required(slot, "visualCost", 0.0, 1.0)
        fade_in = _vfx_director_number_required(slot, "fadeIn", 0.0, 0.8)
        fade_out = _vfx_director_number_required(slot, "fadeOut", 0.0, 0.8)
        phase_offset = _vfx_director_number_required(slot, "phaseOffset", -1.0, 1.0) if "phaseOffset" in slot else 0.0
        if any(x is None for x in [scale, density, duration, alpha, spread, jitter, budget_weight, signature_weight, visual_cost, fade_in, fade_out, phase_offset]):
            return None

        # Director must make an explicit particle material choice.
        if _vfx_particle_id_is_explicit(particle_system_id):
            explicit_particle_count += 1

        compiled_raw.append({
            "event": ev,
            "renderer": rk,
            "rendererKind": rk,
            "backend": backend,
            "textureRole": texture_role,
            "particleRole": particle_role,
            "anchor": anchor,
            "channel": channel,
            "lane": lane,
            "emissionMode": emission_mode,
            "blend": blend,
            "particleSystemId": particle_system_id,
            "scale": scale,
            "density": density,
            "duration": duration,
            "alpha": alpha,
            "spread": spread,
            "jitter": jitter,
            "phaseOffset": phase_offset,
            "budgetWeight": budget_weight,
            "signatureWeight": signature_weight,
            "visualCost": visual_cost,
            "fadeIn": fade_in,
            "fadeOut": fade_out,
            "source": "llmDirector",
        })

    slots = [_vfx_compile_slot(slot, seed, i, power, effect_magnitude) for i, slot in enumerate(compiled_raw)]
    slots = _vfx_arbitrate_slots(slots, budget_class)
    if not slots:
        return None
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    kit = data.get("visualKit") if isinstance(data.get("visualKit"), dict) else {}
    words = _vfx_words(" ".join(str(x or "") for x in [data.get("name"), data.get("tooltip"), raw.get("identity"), kit.get("styleGuide"), visual.get("styleGuide"), attack.get("toyIdentity"), attack.get("projectileTrail"), attack.get("projectileImpact")]))
    provenance = attack.get("runtimeAuthoringProvenance") if isinstance(attack.get("runtimeAuthoringProvenance"), dict) else {}
    effect_lineage = {
        "mode": "llm_vfx_director",
        "gameplayChildren": provenance.get("gameplayChildren", {}),
        "pureVfx": provenance.get("pureVfx", {}),
        "fieldSources": provenance.get("fieldSources", {}),
        "note": "VFX slots are visual execution of authored VFX intent; real damaging children are only those reported under gameplayChildren.",
    }
    manifest = {
        "schema": "infini.vfx.hybrid.v14",
        "recipeId": "llm_vfx_director",
        "playbackMode": "Hybrid",
        "seed": seed,
        "confidence": 0.84,
        "effectMagnitude": effect_magnitude,
        "visualBudgetClass": budget_class,
        "motif": _vfx_motif_from_data(data, words, pattern),
        "parentEffectProfile": {k: v for k, v in _vfx_parent_effect_profile(data, parent_a, parent_b).items() if k != "_rawParentSlots"},
        "overlayPolicy": "LocalOnly",
        "budget": budget,
        "slots": slots,
        "debug": {
            "composition": {
                "mode": "llm_vfx_director",
                "identity": str(raw.get("identity") or "")[:240],
                "preArbitrationSlotCount": len(compiled_raw),
                "postArbitrationSlotCount": len(slots),
                "explicitParticleSystemSlots": explicit_particle_count,
                "directorEnumMode": "strict",
                "blendedSlots": [],
                "proceduralSlots": [],
            },
            "pattern": pattern,
            "roles": sorted(_vfx_available_roles(data)),
            "selectedReasons": ["llm_director_validated", "fallback_pipeline_available_if_invalid"],
            "topCandidates": [],
            "wordProbe": sorted(list(words))[:40] if VFX_SELECTOR_DEBUG else [],
        }
    }
    return manifest


def try_llm_vfx_director(parent_a: dict[str, Any] | None, parent_b: dict[str, Any] | None, child_item: dict[str, Any], recipe_key_value: str, llm_client: Any = None) -> dict[str, Any] | None:
    """Optional Gemma E4B VFX Director pass.

    Primary mode is continuation of the original item-generation chat: because
    OpenAI-compatible APIs are stateless, server.py stores the original planner
    messages in the child item and this function explicitly resends them.
    If that hidden continuation data is absent/invalid, we fall back to the old
    standalone director request; if that fails too, the old procedural VFX pipeline runs.
    """
    if not VFX_LLM_DIRECTOR_ENABLED or llm_client is None:
        return None
    constraints = {
        "attackPattern": (child_item.get("attack") or {}).get("pattern") if isinstance(child_item.get("attack"), dict) else "basic",
        "noBakedCommands": True,
        "slots": [2, max(2, VFX_LLM_DIRECTOR_MAX_SLOTS)],
    }
    surface = vfx_director_surface()
    system = (
        "You are a VFX director for a Terraria/tModLoader generated item. "
        "Return ONLY one JSON object. No markdown. No reasoning. "
        "Use only the listed VFX surface enums and ranges. Author concrete slot parameters; do not invent code names. "
        "Do not output prose explanations or keys outside the provided JSON contract."
    )
    debug = child_item.setdefault("debug", {})
    try:
        input_packet = build_vfx_director_prompt(parent_a, parent_b, child_item, surface, constraints).get("vfxInputPacket", {})
        weak_hints = input_packet.get("weakHints") if isinstance(input_packet, dict) else []
        if not isinstance(weak_hints, list):
            weak_hints = []
        debug["vfxLlmDirectorInputPacket"] = json.dumps(input_packet, ensure_ascii=False)[:12000]
        debug["vfxWeakHintsEnabled"] = bool(VFX_LLM_WEAK_HINTS_ENABLED)
        debug["vfxWeakHintsCount"] = len(weak_hints)
        debug["vfxWeakHints"] = json.dumps(weak_hints, ensure_ascii=False)[:4000]
    except Exception:
        debug["vfxWeakHintsEnabled"] = bool(VFX_LLM_WEAK_HINTS_ENABLED)
        debug["vfxWeakHintsCount"] = 0
        pass

    def validate_or_repair(raw: Any, mode: str, base_messages: list[dict[str, str]] | None = None) -> dict[str, Any] | None:
        def _reason_key() -> str:
            if mode == "planner_chat_continuation":
                return "vfxLlmDirectorContinuationFallbackReason"
            if mode == "standalone_fallback":
                return "vfxLlmDirectorStandaloneFallbackReason"
            return "vfxLlmDirectorUnknownModeFallbackReason"

        def _set_mode_fallback(reason: str) -> None:
            debug[_reason_key()] = reason
            debug["vfxLlmDirectorLastFallbackReason"] = reason

        report = _vfx_director_validation_report(raw)
        debug["vfxLlmDirectorValidationErrorCount"] = len(report.get("errors", []))
        debug["vfxLlmDirectorValidationFields"] = _vfx_director_error_fields(report)
        debug["vfxLlmDirectorRepairAttempts"] = 0
        debug["vfxLlmDirectorRepairEnabled"] = max(0, VFX_LLM_DIRECTOR_REPAIR_ATTEMPTS)
        if report.get("valid"):
            manifest = _vfx_validate_director_output(raw, child_item, recipe_key_value, parent_a, parent_b)
            if isinstance(manifest, dict) and manifest.get("slots"):
                comp = manifest.setdefault("debug", {}).setdefault("composition", {})
                comp["repairAttempted"] = False
                comp["validationErrorCountBeforeRepair"] = 0
                comp["weakHintsEnabled"] = bool(VFX_LLM_WEAK_HINTS_ENABLED)
                comp["weakHintsCount"] = int(debug.get("vfxWeakHintsCount") or 0)
                comp["weakHints"] = json.loads(debug.get("vfxWeakHints") or "[]") if isinstance(debug.get("vfxWeakHints"), str) else []
                comp["vfxPath"] = "llm_director"
                return manifest
            _set_mode_fallback("valid_contract_but_compile_failed")
            return None

        if VFX_LLM_DIRECTOR_REPAIR_ATTEMPTS <= 0:
            _set_mode_fallback("invalid_director_output_repair_disabled")
            debug["vfxLlmDirectorValidationReport"] = json.dumps(report, ensure_ascii=False)[:6000]
            return None

        repair_raw: Any = raw
        last_report = report
        for attempt in range(1, max(0, VFX_LLM_DIRECTOR_REPAIR_ATTEMPTS) + 1):
            debug["vfxLlmDirectorRepairAttempts"] = attempt
            debug["vfxLlmDirectorRepairFields"] = _vfx_director_error_fields(last_report)
            repair_payload = _vfx_director_repair_prompt(repair_raw, last_report, surface)
            if base_messages:
                repair_messages = list(base_messages) + [
                    {"role": "assistant", "content": json.dumps(repair_raw, ensure_ascii=False, separators=(",", ":"))},
                    {"role": "user", "content": json.dumps(repair_payload, ensure_ascii=False, separators=(",", ":"))},
                ]
                repair_raw = llm_client("", {}, VFX_LLM_DIRECTOR_MAX_TOKENS, VFX_LLM_DIRECTOR_TEMPERATURE, VFX_LLM_DIRECTOR_TIMEOUT, messages=repair_messages)
            else:
                repair_raw = llm_client(system, repair_payload, VFX_LLM_DIRECTOR_MAX_TOKENS, VFX_LLM_DIRECTOR_TEMPERATURE, VFX_LLM_DIRECTOR_TIMEOUT)
            last_report = _vfx_director_validation_report(repair_raw)
            debug["vfxLlmDirectorRepairLastErrorCount"] = len(last_report.get("errors", []))
            debug["vfxLlmDirectorRepairLastFields"] = _vfx_director_error_fields(last_report)
            if last_report.get("valid"):
                manifest = _vfx_validate_director_output(repair_raw, child_item, recipe_key_value, parent_a, parent_b)
                if isinstance(manifest, dict) and manifest.get("slots"):
                    comp = manifest.setdefault("debug", {}).setdefault("composition", {})
                    comp["repairAttempted"] = True
                    comp["repairAttempts"] = attempt
                    comp["validationErrorCountBeforeRepair"] = len(report.get("errors", []))
                    comp["repairedFields"] = _vfx_director_error_fields(report)
                    comp["weakHintsEnabled"] = bool(VFX_LLM_WEAK_HINTS_ENABLED)
                    comp["weakHintsCount"] = int(debug.get("vfxWeakHintsCount") or 0)
                    comp["weakHints"] = json.loads(debug.get("vfxWeakHints") or "[]") if isinstance(debug.get("vfxWeakHints"), str) else []
                    comp["vfxPath"] = "llm_director"
                    debug["vfxLlmDirectorRepairStatus"] = "success"
                    return manifest
                _set_mode_fallback("repair_valid_contract_but_compile_failed")
                return None

        debug["vfxLlmDirectorRepairStatus"] = "failed"
        _set_mode_fallback("invalid_after_repair")
        debug["vfxLlmDirectorValidationReport"] = json.dumps(last_report, ensure_ascii=False)[:6000]
        return None

    try:
        messages = build_vfx_director_continuation_messages(child_item, parent_a, parent_b, surface, constraints)
        if messages:
            raw = llm_client("", {}, VFX_LLM_DIRECTOR_MAX_TOKENS, VFX_LLM_DIRECTOR_TEMPERATURE, VFX_LLM_DIRECTOR_TIMEOUT, messages=messages)
            manifest = validate_or_repair(raw, "planner_chat_continuation", base_messages=messages)
            if isinstance(manifest, dict) and manifest.get("slots"):
                debug["vfxLlmDirectorMode"] = "planner_chat_continuation"
                debug["vfxLlmDirectorContinuationMessages"] = len(messages)
                debug["vfxPath"] = "llm_director"
                return manifest
            debug["vfxLlmDirectorContinuationFallback"] = debug.get("vfxLlmDirectorContinuationFallbackReason") or "invalid_or_empty_output"
        else:
            debug["vfxLlmDirectorContinuationFallbackReason"] = "missing_planner_chat_history"
            debug["vfxLlmDirectorContinuationFallback"] = "missing_planner_chat_history"

        # Legacy fallback: standalone VFX director prompt with compact parent/child cards.
        payload = build_vfx_director_prompt(parent_a, parent_b, child_item, surface, constraints)
        raw = llm_client(system, payload, VFX_LLM_DIRECTOR_MAX_TOKENS, VFX_LLM_DIRECTOR_TEMPERATURE, VFX_LLM_DIRECTOR_TIMEOUT)
        manifest = validate_or_repair(raw, "standalone_fallback", base_messages=None)
        if isinstance(manifest, dict) and manifest.get("slots"):
            debug["vfxLlmDirectorMode"] = "standalone_fallback"
            debug["vfxPath"] = "llm_director"
            return manifest
        final_reason = debug.get("vfxLlmDirectorStandaloneFallbackReason") or "standalone_invalid_or_empty_output"
        debug["vfxLlmDirectorStandaloneFallbackReason"] = final_reason
        debug["vfxLlmDirectorFinalFallbackReason"] = final_reason
        debug["vfxLlmDirectorFallbackReason"] = final_reason
        debug["vfxPath"] = "legacy_recipe_fallback"
        return None
    except Exception as e:
        debug["vfxLlmDirectorError"] = repr(e)
        debug["vfxLlmDirectorFinalFallbackReason"] = "exception"
        debug["vfxLlmDirectorFallbackReason"] = "exception"
        debug["vfxPath"] = "legacy_recipe_fallback"
        return None


# =============================================================================
# NAV: VFX_MANIFEST_PIPELINE
# =============================================================================

def attach_hybrid_vfx_manifest(data: dict[str, Any], recipe_key_value: str, reroll_salt: Any = "", parent_a: dict[str, Any] | None = None, parent_b: dict[str, Any] | None = None, llm_director: Any = None) -> dict[str, Any]:
    """v0.3.16: dirty hybrid VFX selector.

    This intentionally combines mechanical filters, weak LLM hints, recipe ranges and
    stable seed mutation, then freezes the result into attack.vfxManifestJson.
    C# runtime only executes the manifest; it must not parse prompt prose every tick.
    """
    if not VFX_SELECTOR_ENABLED:
        return data
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    if not attack.get("enabled"):
        return data
    direct_manifest = _vfx_runtime_plan_direct_manifest(data, recipe_key_value, reroll_salt)
    if isinstance(direct_manifest, dict):
        data["vfxManifest"] = direct_manifest
        attack["vfxManifestJson"] = json.dumps(direct_manifest, ensure_ascii=False, separators=(",", ":"))
        data["attack"] = attack
        data.setdefault("debug", {})["vfxManifest"] = json.dumps(direct_manifest, ensure_ascii=False)[:12000]
        data.setdefault("debug", {})["vfxPath"] = "runtime_plan_direct_empty" if not direct_manifest.get("slots") else "runtime_plan_direct"
        return data
    force_recipe_id = str((data.get("recipeMeta") or {}).get("vfxForcedRecipeId") or (data.get("debug") or {}).get("vfxForcedRecipeId") or "").strip()
    forced_recipe = _vfx_find_recipe(force_recipe_id) if force_recipe_id else None
    if forced_recipe is not None:
        return _vfx_manifest_from_recipe(data, forced_recipe, recipe_key_value, reroll_salt, forced=True)
    director_manifest = try_llm_vfx_director(parent_a, parent_b, data, recipe_key_value, llm_director)
    if isinstance(director_manifest, dict) and director_manifest.get("slots"):
        data["vfxManifest"] = director_manifest
        attack["vfxManifestJson"] = json.dumps(director_manifest, ensure_ascii=False, separators=(",", ":"))
        data["attack"] = attack
        data.setdefault("debug", {})["vfxManifest"] = json.dumps(director_manifest, ensure_ascii=False)[:12000]
        data.setdefault("debug", {})["vfxLlmDirector"] = "used"
        data.setdefault("debug", {})["vfxPath"] = "llm_director"
        return data
    if VFX_LLM_DIRECTOR_ENABLED:
        data.setdefault("debug", {})["vfxLlmDirector"] = data.setdefault("debug", {}).get("vfxLlmDirectorError") or "fallback"
    data.setdefault("debug", {}).setdefault("vfxPath", "legacy_recipe_fallback")
    # All dirty selection/randomness must freeze at generation/reroll time.
    # selector_key is allowed to change only when the user explicitly rerolls VFX.
    selector_key = f"{recipe_key_value}|vfxsalt={str(reroll_salt or data.get('recipeMeta', {}).get('vfxRerollSalt', '') or '')}"
    if not get_vfx_recipes():
        data.setdefault("debug", {})["vfxSelectorError"] = "no vfx_morph_recipes.json recipes loaded"
        return data
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    kit = data.get("visualKit") if isinstance(data.get("visualKit"), dict) else {}
    pattern = str(attack.get("pattern") or attack.get("attackPattern") or "basic").strip() or "basic"
    roles = _vfx_available_roles(data)
    if not roles:
        roles.add("projectile")
    parent_effect_profile = _vfx_parent_effect_profile(data, parent_a, parent_b)
    # Keep raw generated-parent slots only in transient memory for composition; the frozen manifest/debug
    # stores the compact public profile, not full parent manifests.
    if isinstance(parent_effect_profile, dict) and isinstance(parent_a, dict):
        raw_parent_slots = []
        for parent_item in [x for x in (parent_a, parent_b) if isinstance(x, dict)]:
            pm = _vfx_manifest_from_parent_item(parent_item)
            raw_parent_slots.extend([x for x in (pm.get("slots") or []) if isinstance(x, dict)][:4])
        if raw_parent_slots:
            parent_effect_profile = dict(parent_effect_profile)
            parent_effect_profile["_rawParentSlots"] = raw_parent_slots[:8]
    parent_effect_words = " ".join(str(x) for x in ((parent_effect_profile.get("effectTags") if isinstance(parent_effect_profile, dict) else []) or []) + ((parent_effect_profile.get("suggestedRenderers") if isinstance(parent_effect_profile, dict) else []) or []))
    text_parts = [
        data.get("name"), data.get("tooltip"), parent_effect_words,
        kit.get("styleGuide"), kit.get("silhouetteSummary"), kit.get("vfxIntent"),
        kit.get("projectileVfx"), kit.get("impactVfx"), kit.get("childVfx"), kit.get("fieldVfx"),
        visual.get("vfxIntent"), visual.get("projectileVfx"), visual.get("impactVfx"), visual.get("childVfx"), visual.get("fieldVfx"),
        visual.get("vfxScaleHint"), visual.get("vfxRhythmHint"), visual.get("vfxAvoid"), _stringish(visual.get("vfxMaterialHints"), ""),
        attack.get("vfxIntent"), attack.get("projectileVfx"), attack.get("impactVfx"), attack.get("childVfx"), attack.get("fieldVfx"),
        attack.get("vfxScaleHint"), attack.get("vfxRhythmHint"), attack.get("vfxAvoid"), _stringish(attack.get("vfxMaterialHints"), ""),
        attack.get("projectileSpritePrompt"), attack.get("impactSpritePrompt"), attack.get("childSpritePrompt"), attack.get("fieldSpritePrompt"),
        attack.get("visualAnimationPlan"), attack.get("projectileTrail"), attack.get("projectileImpact"), attack.get("projectileChild"), attack.get("toyIdentity"), attack.get("specialRule"),
    ]
    words = _vfx_words(" ".join(str(x or "") for x in text_parts))
    power = float(attack.get("powerBudget") or data.get("gameplay", {}).get("powerBudget") or 1.0) if isinstance(data.get("gameplay"), dict) else float(attack.get("powerBudget") or 1.0)
    mundane_profile = _vfx_mundane_duplicate_profile(data, pattern, words, power)
    scored: list[tuple[float, dict[str, Any], list[str]]] = []
    for recipe in get_vfx_recipes():
        rid = str(recipe.get("id") or "")
        patterns = {str(x) for x in (recipe.get("compatiblePatterns") or [])}
        forbidden = {str(x) for x in (recipe.get("forbiddenPatterns") or [])}
        if pattern in forbidden:
            continue
        if patterns and pattern not in patterns and "basic" not in patterns:
            continue
        required = {str(x) for x in (recipe.get("requiredRoles") or []) if str(x)}
        if required and not required.issubset(roles):
            continue
        optional = {str(x) for x in (recipe.get("optionalRoles") or []) if str(x)}
        hints = _vfx_words(" ".join(str(x) for x in (recipe.get("hints") or [])))
        overlap = len(words & hints)
        score = 100.0
        reasons = [f"pattern:{pattern}", "roles:" + "/".join(sorted(roles))]
        if pattern in patterns:
            score += 80.0; reasons.append("exact_pattern")
        if "basic" in patterns and pattern not in patterns:
            score += 15.0; reasons.append("basic_compatible")
        if required:
            score += 24.0 * len(required); reasons.append("required_roles_ok")
        if optional:
            present_optional = len(optional & roles)
            score += 13.0 * present_optional
            if present_optional:
                reasons.append(f"optional_roles:{present_optional}")
        if overlap:
            score += min(70.0, overlap * 7.5 * VFX_SELECTOR_HINT_WEIGHT)
            reasons.append(f"hint_overlap:{overlap}")
        parent_bonus, parent_reasons = _vfx_parent_effect_recipe_bonus(recipe, parent_effect_profile)
        if parent_bonus:
            score += parent_bonus
            reasons.extend(parent_reasons[:3])
        raw_recipe_slots = [x for x in (recipe.get("slots") or []) if isinstance(x, dict)]
        slot_count = len(raw_recipe_slots)
        renderers = [str(x.get("renderer") or "") for x in raw_recipe_slots]
        unique_renderers = len({r.lower() for r in renderers if r})
        if unique_renderers >= 3:
            score += VFX_SELECTOR_NOVELTY_WEIGHT
            reasons.append(f"renderer_variety:{unique_renderers}")
        cost = str(recipe.get("cost") or "medium")
        if cost == "high" and power < 0.85:
            score -= 18.0; reasons.append("high_cost_penalty")
        if cost == "low" and power > 1.35:
            score -= 6.0; reasons.append("low_cost_on_high_power")
        if mundane_profile.get("enabled"):
            if rid.startswith("mundane_") or cost in {"tiny", "low"}:
                score += 70.0; reasons.append("mundane_guard_prefers_small_recipe")
            if cost in {"high", "signature", "ultra"}:
                score -= 145.0; reasons.append("mundane_guard_blocks_heavy_recipe")
            if slot_count > 3:
                score -= (slot_count - 3) * 24.0; reasons.append("mundane_guard_slot_count_penalty")
        jitter = (_vfx_unit(_vfx_seed_int(selector_key, rid), "selector") - 0.5) * VFX_SELECTOR_JITTER
        score += jitter
        scored.append((score, recipe, reasons))
    if not scored:
        # Mechanical fallback manifest: still frozen, but intentionally simple.
        fallback = {
            "schema": "infini.vfx.hybrid.v14",
            "recipeId": "fallback_afterimage_flash",
            "playbackMode": "Auto",
            "seed": _vfx_seed_int(selector_key, "vfx_fallback"),
            "confidence": 0.15,
            "budget": _vfx_budget_for_recipe({"cost": "low"}, power, selector_key, data),
            "slots": [
                {"event": "travel", "renderer": "projectileAfterimage", "textureRole": "projectile", "particleRole": "child", "variant": 0, "scale": 0.9, "density": 0.18, "duration": 8, "alpha": 0.28, "spread": 0.5},
                {"event": "hit", "renderer": "impactSpriteFlash", "textureRole": "impact", "particleRole": "child", "variant": 0, "scale": 1.4, "density": 0.2, "duration": 7, "alpha": 0.55, "spread": 0.5},
            ],
            "debug": {"reason": "no compatible recipe", "pattern": pattern, "roles": sorted(roles)},
        }
        data["vfxManifest"] = fallback
        attack["vfxManifestJson"] = json.dumps(fallback, ensure_ascii=False, separators=(",", ":"))
        data["attack"] = attack
        return data
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:max(1, VFX_SELECTOR_TOP)]
    # Weighted deterministic pick from top candidates, so the best usually wins but recipes do not collapse.
    # Mundane duplicate guard intentionally disables this extra roulette: copper dagger + copper dagger
    # should choose the safest top recipe, not a runner-up with more spectacle.
    selected_score, selected, selected_reasons = top[0]
    if not mundane_profile.get("enabled"):
        total = sum(max(1.0, x[0] - top[-1][0] + 1.0) for x in top)
        cursor = _vfx_unit(_vfx_seed_int(selector_key, "vfx_pick"), "pick") * total
        acc = 0.0
        for score, recipe, reasons in top:
            weight = max(1.0, score - top[-1][0] + 1.0)
            acc += weight
            if cursor <= acc:
                selected_score, selected, selected_reasons = score, recipe, reasons
                break
    seed = _vfx_seed_int(selector_key, selected.get("id"), data.get("id"), pattern)
    budget = _vfx_budget_for_recipe(selected, power, seed, data)
    effect_magnitude = float(budget.get("effectMagnitude") or 0.5)
    budget_class = str(budget.get("visualBudgetClass") or "normal")
    motif = _vfx_motif_from_data(data, words, pattern)
    base_raw_slots = [x for x in (selected.get("slots") or []) if isinstance(x, dict)]
    if mundane_profile.get("enabled"):
        blended_raw, blended_debug = [], []
        procedural_raw, procedural_debug = [], []
    else:
        blended_raw, blended_debug = _vfx_blend_runner_up_slots(top, str(selected.get("id") or ""), seed, base_raw_slots, budget_class)
        procedural_raw, procedural_debug = _vfx_add_procedural_slots(base_raw_slots + blended_raw, pattern, roles, motif, budget_class, seed)
    inherited_raw, inherited_debug = _vfx_parent_inherited_raw_slots(parent_effect_profile, pattern, roles, budget_class, seed)
    authored_raw, authored_debug = _vfx_authored_cue_raw_slots(data)
    if mundane_profile.get("enabled"):
        inherited_raw, inherited_debug = [], []
    composed_raw_slots = authored_raw + base_raw_slots + blended_raw + procedural_raw + inherited_raw
    pre_arbitration_slot_count = len(composed_raw_slots)
    slots = [_vfx_compile_slot(slot, seed, i, power, effect_magnitude) for i, slot in enumerate(composed_raw_slots) if isinstance(slot, dict)]
    slots = _vfx_arbitrate_slots(slots, budget_class)
    slots = _vfx_trim_mundane_slots(slots, mundane_profile)
    if not slots:
        slots = [{"event": "travel", "renderer": "projectileAfterimage", "textureRole": "projectile", "particleRole": "child", "variant": 0, "scale": 0.9, "density": 0.18, "duration": 8, "alpha": 0.28, "spread": 0.5, "source": "fallback"}]
    top_debug = [[str(r.get("id")), round(float(score), 3), reasons[:6]] for score, r, reasons in top]
    confidence = max(0.05, min(0.98, (selected_score - (top[-1][0] if len(top) > 1 else selected_score - 20.0)) / 90.0 + 0.45))
    provenance = attack.get("runtimeAuthoringProvenance") if isinstance(attack.get("runtimeAuthoringProvenance"), dict) else {}
    effect_lineage = {
        "mode": "recipe_selector",
        "selectedRecipeId": str(selected.get("id") or "unknown"),
        "gameplayChildren": provenance.get("gameplayChildren", {}),
        "pureVfx": provenance.get("pureVfx", {}),
        "fieldSources": provenance.get("fieldSources", {}),
        "note": "VFX slots are selected visual execution, not gameplay-authoring source of truth.",
    }
    manifest = {
        "schema": "infini.vfx.hybrid.v14",
        "recipeId": str(selected.get("id") or "unknown"),
        "playbackMode": _vfx_playback_mode_for_recipe(selected),
        "seed": seed,
        "confidence": round(confidence, 3),
        "effectMagnitude": effect_magnitude,
        "visualBudgetClass": budget.get("visualBudgetClass"),
        "motif": motif,
        "parentEffectProfile": {k: v for k, v in parent_effect_profile.items() if k != "_rawParentSlots"} if isinstance(parent_effect_profile, dict) else {},
        "overlayPolicy": "LocalOnly",
        "budget": budget,
        "slots": slots,
        "debug": {
            "composition": {
                "mode": "authored_cues_plus_recipe" if authored_debug else ("mundane_guard" if mundane_profile.get("enabled") else ("recipe_blend_plus_procedural" if (blended_debug or procedural_debug) else "recipe_only")),
                "baseRecipeId": str(selected.get("id") or "unknown"),
                "preArbitrationSlotCount": pre_arbitration_slot_count,
                "postArbitrationSlotCount": len(slots),
                "blendedSlots": blended_debug,
                "proceduralSlots": procedural_debug,
                "authoredCueSlots": authored_debug,
                "inheritedParentSlots": inherited_debug,
                "mundaneProfile": mundane_profile,
                "parentEffectProfile": {k: v for k, v in parent_effect_profile.items() if k != "_rawParentSlots"} if isinstance(parent_effect_profile, dict) else {},
            },
            "pattern": pattern,
            "roles": sorted(roles),
            "selectedScore": round(float(selected_score), 3),
            "selectedReasons": selected_reasons[:10],
            "topCandidates": top_debug if VFX_SELECTOR_DEBUG else [],
            "wordProbe": sorted(list(words))[:40] if VFX_SELECTOR_DEBUG else [],
            "rerollSalt": str(reroll_salt or data.get("recipeMeta", {}).get("vfxRerollSalt", "") or ""),
            "effectLineage": effect_lineage,
        }
    }
    data["vfxManifest"] = manifest
    attack["vfxManifestJson"] = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"))
    data["attack"] = attack
    data.setdefault("debug", {})["vfxManifest"] = json.dumps(manifest, ensure_ascii=False)[:12000]
    return data




def _vfx_find_recipe(recipe_id: str) -> dict[str, Any] | None:
    rid = str(recipe_id or "").strip()
    if not rid:
        return None
    for recipe in get_vfx_recipes():
        if str(recipe.get("id") or "") == rid:
            return recipe
    return None


def _vfx_manifest_from_recipe(data: dict[str, Any], recipe: dict[str, Any], recipe_key_value: str, reroll_salt: Any = "", forced: bool = False) -> dict[str, Any]:
    attack = data.setdefault("attack", {}) if isinstance(data.get("attack"), dict) else data.setdefault("attack", {})
    pattern = normalize_attack_pattern(attack.get("pattern") or attack.get("attackPattern") or attack.get("Pattern") or "basic")
    selector_key = f"{recipe_key_value}|vfxsalt={str(reroll_salt or data.get('recipeMeta', {}).get('vfxRerollSalt', '') or '')}"
    power = float(attack.get("powerBudget") or data.get("gameplay", {}).get("powerBudget") or 1.0) if isinstance(data.get("gameplay"), dict) else float(attack.get("powerBudget") or 1.0)
    seed = _vfx_seed_int(selector_key, recipe.get("id"), data.get("id"), pattern)
    budget = _vfx_budget_for_recipe(recipe, power, seed, data)
    effect_magnitude = float(budget.get("effectMagnitude") or 0.5)
    slots = [_vfx_compile_slot(slot, seed, i, power, effect_magnitude) for i, slot in enumerate(recipe.get("slots") or []) if isinstance(slot, dict)]
    slots = _vfx_arbitrate_slots(slots, str(budget.get("visualBudgetClass") or "normal"))
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    kit = data.get("visualKit") if isinstance(data.get("visualKit"), dict) else {}
    words = _vfx_words(" ".join(str(x or "") for x in [data.get("name"), data.get("tooltip"), kit.get("styleGuide"), kit.get("vfxIntent"), visual.get("vfxIntent"), attack.get("vfxIntent"), attack.get("projectileSpritePrompt"), attack.get("impactSpritePrompt"), attack.get("visualAnimationPlan")]))
    provenance = attack.get("runtimeAuthoringProvenance") if isinstance(attack.get("runtimeAuthoringProvenance"), dict) else {}
    effect_lineage = {
        "mode": "forced_recipe" if forced else "direct_recipe",
        "selectedRecipeId": str(recipe.get("id") or "unknown"),
        "gameplayChildren": provenance.get("gameplayChildren", {}),
        "pureVfx": provenance.get("pureVfx", {}),
        "fieldSources": provenance.get("fieldSources", {}),
        "note": "VFX slots are recipe-selected visuals, not gameplay-authoring source of truth.",
    }
    manifest = {
        "schema": "infini.vfx.hybrid.v14",
        "recipeId": str(recipe.get("id") or "unknown"),
        "playbackMode": _vfx_playback_mode_for_recipe(recipe),
        "seed": seed,
        "confidence": 0.99 if forced else 0.72,
        "effectMagnitude": effect_magnitude,
        "visualBudgetClass": budget.get("visualBudgetClass"),
        "motif": _vfx_motif_from_data(data, words, pattern),
        "overlayPolicy": "LocalOnly",
        "budget": budget,
        "slots": slots,
        "debug": {
            "composition": {
                "mode": "forced_recipe" if forced else "direct_recipe",
                "baseRecipeId": str(recipe.get("id") or "unknown"),
                "preArbitrationSlotCount": len(recipe.get("slots") or []),
                "postArbitrationSlotCount": len(slots),
                "blendedSlots": [],
                "proceduralSlots": [],
            },
            "pattern": pattern,
            "roles": sorted(_vfx_available_roles(data)),
            "selectedScore": 999.0 if forced else 0.0,
            "selectedReasons": ["forced_recipe" if forced else "direct_recipe"],
            "topCandidates": [],
            "wordProbe": [],
            "rerollSalt": str(reroll_salt or data.get("recipeMeta", {}).get("vfxRerollSalt", "") or ""),
            "effectLineage": effect_lineage,
        }
    }
    data["vfxManifest"] = manifest
    attack["vfxManifestJson"] = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"))
    data["attack"] = attack
    data.setdefault("debug", {})["vfxManifest"] = json.dumps(manifest, ensure_ascii=False)[:12000]
    return data


def compact_vfx_recipe_card(recipe: dict[str, Any]) -> dict[str, Any]:
    slots = recipe.get("slots") if isinstance(recipe.get("slots"), list) else []
    return {
        "id": recipe.get("id", ""),
        "compatiblePatterns": recipe.get("compatiblePatterns", []),
        "requiredRoles": recipe.get("requiredRoles", []),
        "optionalRoles": recipe.get("optionalRoles", []),
        "forbiddenPatterns": recipe.get("forbiddenPatterns", []),
        "cost": recipe.get("cost", "medium"),
        "playbackMode": _vfx_playback_mode_for_recipe(recipe),
        "hints": recipe.get("hints", []),
        "slotCount": len(slots),
        "renderers": [str(x.get("renderer", "")) for x in slots if isinstance(x, dict)],
        "backends": sorted({str(x.get("backend") or _vfx_default_backend(x.get("event"), x.get("renderer"))) for x in slots if isinstance(x, dict)}),
        "stages": sorted({str(x.get("stage") or _vfx_event_stage(x.get("event"), x.get("renderer"))) for x in slots if isinstance(x, dict)}),
        "bakedEligibleSlots": sum(1 for x in slots if isinstance(x, dict) and _vfx_should_bake_slot(x, str(x.get("event") or ""), str(x.get("renderer") or ""), str(x.get("backend") or _vfx_default_backend(x.get("event"), x.get("renderer"))))),
        "expandedFromMacros": bool(recipe.get("expandedFromMacros")),
        "useMacros": recipe.get("useMacros", []),
        "macroIds": sorted({str(x.get("macroId")) for x in slots if isinstance(x, dict) and x.get("macroId")}),
    }

# VFX lint/effect-stack/timeline helpers live in vfx_lint_timeline.py.

__all__ = [
    name for name in globals()
    if name.startswith("VFX_")
    or name.startswith("_vfx")
    or name in {
        "attach_hybrid_vfx_manifest",
        "build_vfx_director_prompt",
        "build_vfx_director_weak_hints",
        "try_llm_vfx_director",
        "vfx_director_surface",
        "get_vfx_effect_name_bank",
        "vfx_director_name_bank",
        "get_vfx_recipes",
        "vfx_manifest_effect_stack",
    }
]
