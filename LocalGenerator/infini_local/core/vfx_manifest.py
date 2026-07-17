from __future__ import annotations

import json
import math
from typing import Any

from infini_local.core.json_debug import bounded_json_dumps
from infini_local.core.boundary_models import validate_vfx_manifest_boundary

from infini_local.core.effect_catalog import normalize_attack_pattern
from infini_local.core.llm_stage_messages import agent_handoff, planner_history_state, stage_chat_message
from infini_local.core.vfx_composition_primitives import (
    _vfx_arbitrate_slots,
    _vfx_available_roles,
    _vfx_budget_for_recipe,
    _vfx_default_backend,
    _vfx_event_stage,
    _vfx_motif_from_data,
    _vfx_playback_mode_for_recipe,
    _vfx_seed_int,
    _vfx_unit,
)
from infini_local.core.vfx_composition_parent import (
    _vfx_manifest_from_parent_item,
    _vfx_parent_effect_profile,
    _vfx_parent_inherited_raw_slots,
)
from infini_local.core.vfx_runtime_slots import (
    _vfx_add_procedural_slots,
    _vfx_authored_cue_raw_slots,
    _vfx_blend_runner_up_slots,
    _vfx_compile_slot,
    _vfx_runtime_plan_direct_manifest,
    _vfx_should_bake_slot,
)
from infini_local.core.vfx_director_prompt import (
    VFX_DIRECTOR_SYSTEM,
    build_vfx_director_handoff_messages,
    build_vfx_director_prompt,
)
from infini_local.core.vfx_director_contract import (
    _vfx_director_enum_required,
    _vfx_director_error_fields,
    _vfx_director_number_required,
    _vfx_director_repair_prompt,
    _vfx_director_validation_report,
    _vfx_particle_id_is_explicit,
    vfx_director_surface,
)
from infini_local.core.vfx_recipe_library import get_vfx_recipes
from infini_local.storage.trace_runtime import log_event
from infini_local.core.vfx_manifest_config import (
    VFX_LLM_DIRECTOR_ENABLED,
    VFX_LLM_DIRECTOR_MAX_SLOTS,
    VFX_LLM_DIRECTOR_MAX_TOKENS,
    VFX_LLM_DIRECTOR_REPAIR_ATTEMPTS,
    VFX_LLM_DIRECTOR_TEMPERATURE,
    VFX_LLM_DIRECTOR_TIMEOUT,
    VFX_SELECTOR_DEBUG,
    VFX_SELECTOR_ENABLED,
    VFX_SELECTOR_JITTER,
    VFX_SELECTOR_NOVELTY_WEIGHT,
    VFX_SELECTOR_TOP,
)


# PRODUCT POLICY: the LLM VFX Director is the preferred presentation author, but VFX
# is not important enough to discard an otherwise valid LLM-authored item.  After one
# bounded same-request VFX repair is exhausted, generation keeps the item and uses the
# stable procedural recipe selector as a visual safety net.  This safety net never owns
# gameplay.  Every transition into it must emit ``infini.vfx-fallback-trace.v1`` so a
# bad Director response, lost history, legacy standalone failure, or compile failure is
# visible in events.ndjson instead of being hidden behind a merely acceptable manifest.
#
# AGENT MAP: Python VFX manifest authoring/normalization contract.
# Owns VFX manifest assembly. Config/data/env ownership lives in
# vfx_manifest_config.py; optional LLM Director context helpers live in
# vfx_director_context.py. Keep gameplay out of motif/effect prose; combat
# behavior belongs in explicit runtime fields compiled by the runtime_authoring package.


# VFX config constants are imported from vfx_manifest_config.py. Recipe macros
# are imported from vfx_recipe_library.py and still expand lazily there.




# VFX Director prompt/name-bank helpers live in vfx_director_prompt.py.

VFX_FALLBACK_POLICY = "llm_vfx_optional_then_procedural_safety_net"


def _log_vfx_fallback_policy(
    data: dict[str, Any],
    recipe_key_value: str,
    *,
    history_state: str,
    request_mode: str,
    failure_phase: str,
    reason: str,
) -> None:
    """Emit one structured warning before the procedural VFX safety net takes over."""
    debug_value = data.get("debug")
    debug: dict[str, Any] = debug_value if isinstance(debug_value, dict) else {}
    validation_fields = debug.get("vfxLlmDirectorRepairLastFields") or debug.get("vfxLlmDirectorValidationFields") or []
    log_event("warn", "VFX Director fallback policy activated", {
        "schema": "infini.vfx-fallback-trace.v1",
        "policy": VFX_FALLBACK_POLICY,
        "recipeKey": str(recipe_key_value or ""),
        "itemId": str(data.get("id") or ""),
        "itemName": str(data.get("name") or ""),
        "historyState": str(history_state or "unknown"),
        "requestMode": str(request_mode or "unknown"),
        "failurePhase": str(failure_phase or "unknown"),
        "reason": str(reason or "unknown"),
        "validationFields": [str(field) for field in validation_fields],
        "repairAttempts": int(debug.get("vfxLlmDirectorRepairAttempts") or 0),
        "fallbackTarget": "procedural_vfx_recipe_selector",
    })


def _log_vfx_fallback_selected(data: dict[str, Any], recipe_key_value: str, manifest: dict[str, Any]) -> None:
    """Record the concrete procedural manifest that masked the Director failure."""
    debug_value = data.get("debug")
    debug: dict[str, Any] = debug_value if isinstance(debug_value, dict) else {}
    if str(debug.get("vfxPath") or "") != "deterministic_recipe_fallback":
        return
    manifest_debug_value = manifest.get("debug")
    manifest_debug: dict[str, Any] = manifest_debug_value if isinstance(manifest_debug_value, dict) else {}
    composition_value = manifest_debug.get("composition")
    composition: dict[str, Any] = composition_value if isinstance(composition_value, dict) else {}
    slots_value = manifest.get("slots")
    slots: list[Any] = slots_value if isinstance(slots_value, list) else []
    log_event("info", "VFX procedural safety net selected manifest", {
        "schema": "infini.vfx-fallback-selected.v1",
        "policy": VFX_FALLBACK_POLICY,
        "recipeKey": str(recipe_key_value or ""),
        "itemId": str(data.get("id") or ""),
        "itemName": str(data.get("name") or ""),
        "failureReason": str(debug.get("vfxLlmDirectorFinalFallbackReason") or debug.get("vfxLlmDirectorFallbackReason") or "unknown"),
        "recipeId": str(manifest.get("recipeId") or "unknown"),
        "slotCount": len(slots),
        "compositionMode": str(composition.get("mode") or manifest_debug.get("reason") or "recipe_only"),
    })


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
            "rendererKind": rk,
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
        "motif": _vfx_motif_from_data(data, set(), str(pattern or "basic")),
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
            "wordProbe": [],
        }
    }
    return manifest


def try_llm_vfx_director(parent_a: dict[str, Any] | None, parent_b: dict[str, Any] | None, child_item: dict[str, Any], recipe_key_value: str, llm_client: Any = None) -> dict[str, Any] | None:
    """Optional Gemma E4B VFX Director pass.

    Product policy: VFX is optional presentation, not the main authored gameplay feature.
    Valid Planner provenance gates a self-contained V3.1 VFX dossier. ``VFX repair``
    appends the invalid Director artifact plus exact validator feedback and asks for a
    corrected manifest. ``VFX standalone`` is different: it is
    a fresh two-message VFX request with compact parent/current-item cards, allowed only
    for genuine legacy data whose Planner history never existed.  It is never a second
    live-continuation attempt.

    If the bounded repair fails, keep the valid item and invoke the stable procedural VFX
    recipe selector as a cosmetic safety net.  This selector never owns gameplay.  The
    exact failure phase/reason is emitted to events.ndjson before it takes over.
    """
    if not VFX_LLM_DIRECTOR_ENABLED or llm_client is None:
        return None
    constraints = {
        "attackPattern": (child_item.get("attack") or {}).get("pattern") if isinstance(child_item.get("attack"), dict) else "basic",
        "noBakedCommands": True,
        "slots": [2, max(2, VFX_LLM_DIRECTOR_MAX_SLOTS)],
    }
    surface = vfx_director_surface()
    system = VFX_DIRECTOR_SYSTEM
    debug = child_item.setdefault("debug", {})
    try:
        input_packet = build_vfx_director_prompt(parent_a, parent_b, child_item, surface, constraints).get("vfxInputPacket", {})
        debug["vfxLlmDirectorInputPacket"] = bounded_json_dumps(input_packet, max_chars=12000)
    except Exception:
        pass

    def validate_or_repair(raw: Any, mode: str, base_messages: list[dict[str, str]] | None = None) -> dict[str, Any] | None:
        def _reason_key() -> str:
            if mode == "authoritative_stage_dossier_v31":
                return "vfxLlmDirectorHistoryFallbackReason"
            if mode == "legacy_no_history_standalone":
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
                comp["vfxPath"] = "llm_director"
                return manifest
            _set_mode_fallback("valid_contract_but_compile_failed")
            return None

        if VFX_LLM_DIRECTOR_REPAIR_ATTEMPTS <= 0:
            _set_mode_fallback("invalid_director_output_repair_disabled")
            debug["vfxLlmDirectorValidationReport"] = bounded_json_dumps(report, max_chars=6000)
            return None

        repair_raw: Any = raw
        last_report = report
        for attempt in range(1, max(0, VFX_LLM_DIRECTOR_REPAIR_ATTEMPTS) + 1):
            debug["vfxLlmDirectorRepairAttempts"] = attempt
            debug["vfxLlmDirectorRepairFields"] = _vfx_director_error_fields(last_report)
            repair_payload = _vfx_director_repair_prompt(repair_raw, last_report, surface)
            repair_payload["agentHandoff"] = agent_handoff(
                previous_speaker="vfx_director",
                current_speaker="vfx_validator",
                next_speaker="vfx_director",
                cause_by="vfx_contract_validation_failed",
                artifact_source="vfx_director.manifest",
            )
            if base_messages:
                repair_messages = list(base_messages) + [
                    stage_chat_message("assistant", "vfx_director", json.dumps(repair_raw, ensure_ascii=False, separators=(",", ":"))),
                    stage_chat_message("user", "vfx_validator", json.dumps(repair_payload, ensure_ascii=False, separators=(",", ":"))),
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
                    comp["vfxPath"] = "llm_director"
                    debug["vfxLlmDirectorRepairStatus"] = "success"
                    return manifest
                _set_mode_fallback("repair_valid_contract_but_compile_failed")
                return None

        debug["vfxLlmDirectorRepairStatus"] = "failed"
        _set_mode_fallback("invalid_after_repair")
        debug["vfxLlmDirectorValidationReport"] = bounded_json_dumps(last_report, max_chars=6000)
        return None

    try:
        history_state = planner_history_state(child_item)
        live_planner = str((child_item.get("debug") or {}).get("planner") or "") == "llm_author_first"
        messages = build_vfx_director_handoff_messages(child_item, parent_a, parent_b, surface, constraints)
        if messages:
            raw = llm_client(system, {}, VFX_LLM_DIRECTOR_MAX_TOKENS, VFX_LLM_DIRECTOR_TEMPERATURE, VFX_LLM_DIRECTOR_TIMEOUT, messages=messages)
            manifest = validate_or_repair(raw, "authoritative_stage_dossier_v31", base_messages=messages)
            if isinstance(manifest, dict) and manifest.get("slots"):
                debug["vfxLlmDirectorMode"] = "authoritative_stage_dossier_v31"
                debug["vfxLlmDirectorHistoryMessages"] = len(messages)
                debug["vfxPath"] = "llm_director"
                return manifest
            debug["vfxLlmDirectorHistoryFallback"] = debug.get("vfxLlmDirectorHistoryFallbackReason") or "invalid_or_empty_output"
            debug["vfxLlmDirectorFinalFallbackReason"] = debug["vfxLlmDirectorHistoryFallback"]
            debug["vfxLlmDirectorFallbackReason"] = debug["vfxLlmDirectorHistoryFallback"]
            debug["vfxPath"] = "deterministic_recipe_fallback"
            continuation_reason = str(debug["vfxLlmDirectorHistoryFallback"])
            continuation_attempts = int(debug.get("vfxLlmDirectorRepairAttempts") or 0)
            continuation_phase = (
                "repair_exhausted"
                if continuation_attempts > 0
                else ("compile_failed" if "compile_failed" in continuation_reason else "initial_validation")
            )
            _log_vfx_fallback_policy(
                child_item,
                recipe_key_value,
                history_state=history_state,
                request_mode="authoritative_stage_dossier_v31",
                failure_phase=continuation_phase,
                reason=continuation_reason,
            )
            return None
        if history_state == "malformed" or (history_state == "absent" and live_planner):
            reason = (
                "malformed_attributed_planner_history_fail_closed"
                if history_state == "malformed"
                else "missing_live_planner_history_fail_closed"
            )
            debug["vfxLlmDirectorHistoryFallbackReason"] = reason
            debug["vfxLlmDirectorHistoryFallback"] = reason
            debug["vfxLlmDirectorFinalFallbackReason"] = reason
            debug["vfxLlmDirectorFallbackReason"] = reason
            debug["vfxPath"] = "deterministic_recipe_fallback"
            _log_vfx_fallback_policy(
                child_item,
                recipe_key_value,
                history_state=history_state,
                request_mode="not_called_history_gate",
                failure_phase="history_gate",
                reason=reason,
            )
            return None
        else:
            debug["vfxLlmDirectorHistoryFallbackReason"] = "missing_attributed_planner_history"
            debug["vfxLlmDirectorHistoryFallback"] = "missing_attributed_planner_history"

        # Explicit legacy/no-history VFX request with compact exact parent/child cards.
        payload = build_vfx_director_prompt(parent_a, parent_b, child_item, surface, constraints)
        raw = llm_client(system, payload, VFX_LLM_DIRECTOR_MAX_TOKENS, VFX_LLM_DIRECTOR_TEMPERATURE, VFX_LLM_DIRECTOR_TIMEOUT)
        manifest = validate_or_repair(raw, "legacy_no_history_standalone", base_messages=None)
        if isinstance(manifest, dict) and manifest.get("slots"):
            debug["vfxLlmDirectorMode"] = "legacy_no_history_standalone"
            debug["vfxPath"] = "llm_director"
            return manifest
        final_reason = debug.get("vfxLlmDirectorStandaloneFallbackReason") or "standalone_invalid_or_empty_output"
        debug["vfxLlmDirectorStandaloneFallbackReason"] = final_reason
        debug["vfxLlmDirectorFinalFallbackReason"] = final_reason
        debug["vfxLlmDirectorFallbackReason"] = final_reason
        debug["vfxPath"] = "deterministic_recipe_fallback"
        standalone_attempts = int(debug.get("vfxLlmDirectorRepairAttempts") or 0)
        standalone_phase = (
            "standalone_repair_exhausted"
            if standalone_attempts > 0
            else ("standalone_compile_failed" if "compile_failed" in final_reason else "standalone_validation")
        )
        _log_vfx_fallback_policy(
            child_item,
            recipe_key_value,
            history_state=history_state,
            request_mode="legacy_no_history_standalone",
            failure_phase=standalone_phase,
            reason=str(final_reason),
        )
        return None
    except Exception as e:
        debug["vfxLlmDirectorError"] = repr(e)
        debug["vfxLlmDirectorFinalFallbackReason"] = "exception"
        debug["vfxLlmDirectorFallbackReason"] = "exception"
        debug["vfxPath"] = "deterministic_recipe_fallback"
        _log_vfx_fallback_policy(
            child_item,
            recipe_key_value,
            history_state=locals().get("history_state", "unknown"),
            request_mode="vfx_director_exception",
            failure_phase="exception",
            reason=repr(e),
        )
        return None


# =============================================================================
# NAV: VFX_MANIFEST_PIPELINE
# =============================================================================

def attach_hybrid_vfx_manifest(data: dict[str, Any], recipe_key_value: str, reroll_salt: Any = "", parent_a: dict[str, Any] | None = None, parent_b: dict[str, Any] | None = None, llm_director: Any = None) -> dict[str, Any]:
    """Freeze a VFX manifest from typed runtime facts and explicit authored VFX cues.

    Recipe selection uses compiled attack pattern, available asset roles, recipe cost,
    renderer diversity, power budget, parent manifests, and a stable reroll seed. It
    never tokenizes item names, tooltips, prompts, or free-form style prose.
    """
    if not VFX_SELECTOR_ENABLED:
        return data
    attack_value = data.get("attack")
    attack: dict[str, Any] = attack_value if isinstance(attack_value, dict) else {}
    direct_manifest = _vfx_runtime_plan_direct_manifest(data, recipe_key_value, reroll_salt)
    if isinstance(direct_manifest, dict):
        wire_manifest = validate_vfx_manifest_boundary(direct_manifest)
        data["vfxManifest"] = direct_manifest
        attack["vfxManifestJson"] = json.dumps(wire_manifest, ensure_ascii=False, separators=(",", ":"))
        data["attack"] = attack
        data.setdefault("debug", {})["vfxManifest"] = bounded_json_dumps(direct_manifest, max_chars=12000)
        data.setdefault("debug", {})["vfxPath"] = "runtime_plan_direct_empty" if not direct_manifest.get("slots") else "runtime_plan_direct"
        return data
    if not attack.get("enabled"):
        return data
    force_recipe_id = str((data.get("recipeMeta") or {}).get("vfxForcedRecipeId") or (data.get("debug") or {}).get("vfxForcedRecipeId") or "").strip()
    forced_recipe = _vfx_find_recipe(force_recipe_id) if force_recipe_id else None
    if forced_recipe is not None:
        return _vfx_manifest_from_recipe(data, forced_recipe, recipe_key_value, reroll_salt, forced=True)
    director_manifest = try_llm_vfx_director(parent_a, parent_b, data, recipe_key_value, llm_director)
    if isinstance(director_manifest, dict) and director_manifest.get("slots"):
        wire_manifest = validate_vfx_manifest_boundary(director_manifest)
        data["vfxManifest"] = director_manifest
        attack["vfxManifestJson"] = json.dumps(wire_manifest, ensure_ascii=False, separators=(",", ":"))
        data["attack"] = attack
        data.setdefault("debug", {})["vfxManifest"] = bounded_json_dumps(director_manifest, max_chars=12000)
        data.setdefault("debug", {})["vfxLlmDirector"] = "used"
        data.setdefault("debug", {})["vfxPath"] = "llm_director"
        return data
    if VFX_LLM_DIRECTOR_ENABLED:
        data.setdefault("debug", {})["vfxLlmDirector"] = data.setdefault("debug", {}).get("vfxLlmDirectorError") or "fallback"
    data.setdefault("debug", {}).setdefault("vfxPath", "deterministic_recipe_fallback")
    # All dirty selection/randomness must freeze at generation/reroll time.
    # selector_key is allowed to change only when the user explicitly rerolls VFX.
    selector_key = f"{recipe_key_value}|vfxsalt={str(reroll_salt or data.get('recipeMeta', {}).get('vfxRerollSalt', '') or '')}"
    if not get_vfx_recipes():
        data.setdefault("debug", {})["vfxSelectorError"] = "no vfx_morph_recipes.json recipes loaded"
        return data
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
    power = float(attack.get("powerBudget") or data.get("gameplay", {}).get("powerBudget") or 1.0) if isinstance(data.get("gameplay"), dict) else float(attack.get("powerBudget") or 1.0)
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
        raw_recipe_slots = [x for x in (recipe.get("slots") or []) if isinstance(x, dict)]
        slot_count = len(raw_recipe_slots)
        renderers = [str(x.get("rendererKind") or "") for x in raw_recipe_slots]
        unique_renderers = len({r.lower() for r in renderers if r})
        if unique_renderers >= 3:
            score += VFX_SELECTOR_NOVELTY_WEIGHT
            reasons.append(f"renderer_variety:{unique_renderers}")
        cost = str(recipe.get("cost") or "medium")
        if cost == "high" and power < 0.85:
            score -= 18.0; reasons.append("high_cost_penalty")
        if cost == "low" and power > 1.35:
            score -= 6.0; reasons.append("low_cost_on_high_power")
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
                {"event": "travel", "rendererKind": "projectileAfterimage", "textureRole": "projectile", "particleRole": "child", "variant": 0, "scale": 0.9, "density": 0.18, "duration": 8, "alpha": 0.28, "spread": 0.5},
                {"event": "hit", "rendererKind": "impactSprite", "rendererKind": "impactSprite", "textureRole": "impact", "particleRole": "child", "variant": 0, "scale": 1.4, "density": 0.2, "duration": 7, "alpha": 0.55, "spread": 0.5},
            ],
            "debug": {"reason": "no compatible recipe", "pattern": pattern, "roles": sorted(roles)},
        }
        data["vfxManifest"] = fallback
        attack["vfxManifestJson"] = json.dumps(fallback, ensure_ascii=False, separators=(",", ":"))
        data["attack"] = attack
        _log_vfx_fallback_selected(data, recipe_key_value, fallback)
        return data
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:max(1, VFX_SELECTOR_TOP)]
    # Weighted deterministic pick from structurally compatible candidates.
    selected_score, selected, selected_reasons = top[0]
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
    motif = _vfx_motif_from_data(data, set(), str(pattern or "basic"))
    base_raw_slots = [x for x in (selected.get("slots") or []) if isinstance(x, dict)]
    blended_raw, blended_debug = _vfx_blend_runner_up_slots(top, str(selected.get("id") or ""), seed, base_raw_slots, budget_class)
    procedural_raw, procedural_debug = _vfx_add_procedural_slots(base_raw_slots + blended_raw, pattern, roles, motif, budget_class, seed)
    inherited_raw, inherited_debug = _vfx_parent_inherited_raw_slots(parent_effect_profile, pattern, roles, budget_class, seed)
    authored_raw, authored_debug = _vfx_authored_cue_raw_slots(data)
    composed_raw_slots = authored_raw + base_raw_slots + blended_raw + procedural_raw + inherited_raw
    pre_arbitration_slot_count = len(composed_raw_slots)
    slots = [_vfx_compile_slot(slot, seed, i, power, effect_magnitude) for i, slot in enumerate(composed_raw_slots) if isinstance(slot, dict)]
    slots = _vfx_arbitrate_slots(slots, budget_class)
    if not slots:
        slots = [{"event": "travel", "rendererKind": "projectileAfterimage", "textureRole": "projectile", "particleRole": "child", "variant": 0, "scale": 0.9, "density": 0.18, "duration": 8, "alpha": 0.28, "spread": 0.5, "source": "fallback"}]
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
                "mode": "authored_cues_plus_recipe" if authored_debug else ("recipe_blend_plus_procedural" if (blended_debug or procedural_debug) else "recipe_only"),
                "baseRecipeId": str(selected.get("id") or "unknown"),
                "preArbitrationSlotCount": pre_arbitration_slot_count,
                "postArbitrationSlotCount": len(slots),
                "blendedSlots": blended_debug,
                "proceduralSlots": procedural_debug,
                "authoredCueSlots": authored_debug,
                "inheritedParentSlots": inherited_debug,
                "parentEffectProfile": {k: v for k, v in parent_effect_profile.items() if k != "_rawParentSlots"} if isinstance(parent_effect_profile, dict) else {},
            },
            "pattern": pattern,
            "roles": sorted(roles),
            "selectedScore": round(float(selected_score), 3),
            "selectedReasons": selected_reasons[:10],
            "topCandidates": top_debug if VFX_SELECTOR_DEBUG else [],
            "wordProbe": [],
            "rerollSalt": str(reroll_salt or data.get("recipeMeta", {}).get("vfxRerollSalt", "") or ""),
            "effectLineage": effect_lineage,
        }
    }
    _log_vfx_fallback_selected(data, recipe_key_value, manifest)
    manifest = validate_vfx_manifest_boundary(manifest)
    data["vfxManifest"] = manifest
    attack["vfxManifestJson"] = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"))
    data["attack"] = attack
    data.setdefault("debug", {})["vfxManifest"] = bounded_json_dumps(manifest, max_chars=12000)
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
        "motif": _vfx_motif_from_data(data, set(), str(pattern or "basic")),
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
    manifest = validate_vfx_manifest_boundary(manifest)
    data["vfxManifest"] = manifest
    attack["vfxManifestJson"] = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"))
    data["attack"] = attack
    data.setdefault("debug", {})["vfxManifest"] = bounded_json_dumps(manifest, max_chars=12000)
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
        "backends": sorted({str(x.get("backend") or _vfx_default_backend(x.get("event"), x.get("rendererKind"))) for x in slots if isinstance(x, dict)}),
        "stages": sorted({str(x.get("stage") or _vfx_event_stage(x.get("event"), x.get("rendererKind"))) for x in slots if isinstance(x, dict)}),
        "bakedEligibleSlots": sum(1 for x in slots if isinstance(x, dict) and _vfx_should_bake_slot(x, str(x.get("event") or ""), str(x.get("rendererKind") or ""), str(x.get("backend") or _vfx_default_backend(x.get("event"), x.get("rendererKind"))))),
        "expandedFromMacros": bool(recipe.get("expandedFromMacros")),
        "useMacros": recipe.get("useMacros", []),
        "macroIds": sorted({str(x.get("macroId")) for x in slots if isinstance(x, dict) and x.get("macroId")}),
    }

# VFX lint/effect-stack/timeline helpers live in vfx_lint_timeline.py.

__all__ = [
    "_vfx_validate_director_output",
    "try_llm_vfx_director",
    "attach_hybrid_vfx_manifest",
    "_vfx_find_recipe",
    "_vfx_manifest_from_recipe",
    "compact_vfx_recipe_card",
]
